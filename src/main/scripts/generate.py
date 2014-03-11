import collections
import itertools
import json
import os
import shutil
import urllib2
import xml.etree.ElementTree as ET
import sys


ALL_JSON_URL = "http://schema.rdfs.org/all.json"
TARGET_DIR = "../../../tmp"
XS_URL = "http://www.w3.org/2001/XMLSchema"


ET.register_namespace("xs", XS_URL)

ParsedType = collections.namedtuple(
    'ParsedType',
    ['name', 'url', 'specific_properties', 'ancestors', 'comment_plain'])


def _xs(element_name):
    return "{%s}%s" % (XS_URL, element_name)



# Source: http://code.activestate.com/recipes/578272-topological-sort/
#
# Copyright (c) 2012 Sam Denton
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

def toposort(data):
    """Dependencies are expressed as a dictionary whose keys are items
and whose values are a set of dependent items. Output is a list of
sets in topological order. The first set consists of items with no
dependences, each subsequent set consists of items that depend upon
items in the preceeding sets.

>>> print '\\n'.join(repr(sorted(x)) for x in toposort({
...     2: set([11]),
...     9: set([11,8]),
...     10: set([11,3]),
...     11: set([7,5]),
...     8: set([7,3]),
...     }) )
[3, 5, 7]
[8, 11]
[2, 9, 10]

"""

    from functools import reduce

    # Ignore self dependencies.
    for k, v in data.items():
        v.discard(k)
    # Find all items that don't depend on anything.
    extra_items_in_deps = reduce(set.union, data.itervalues()) - set(data.iterkeys())
    # Add empty dependences where needed
    data.update({item:set() for item in extra_items_in_deps})
    while True:
        ordered = set(item for item, dep in data.iteritems() if not dep)
        if not ordered:
            break
        yield ordered
        data = {item: (dep - ordered)
                for item, dep in data.iteritems()
                if item not in ordered}
    assert not data, "Cyclic dependencies exist among these items:\n%s" % '\n'.join(repr(x) for x in data.iteritems())


class SchemaTerms(object):
    def __init__(self, data):
        self.property_types = {}
        self.property_docs = {}
        self.type_urls = {}
        self.data = data
        self.setup()

    def setup(self):
        for prop in self.data["properties"].values():
            key = prop["id"]
            doc = prop["comment_plain"]
            self.property_docs[key] = doc

            ranges = set(prop["ranges"])
            if set(["Number"]) == ranges:
                self.property_types[key] = "xs:float"
            elif set(["Date"]) == ranges:
                self.property_types[key] = "xs:date"
            elif set(["DateTime"]) == ranges:
                self.property_types[key] = "xs:dateTime"
            elif set(["Boolean"]) == ranges:
                self.property_types[key] = "xs:boolean"
            elif set(["Time"]) == ranges:
                self.property_types[key] = "xs:time"
            elif set(["URL"]) == ranges:
                self.property_types[key] = "xs:anyURI"
            else:
                self.property_types[key] = "xs:string"

        self.type_urls = dict([(item_type["id"], item_type["url"])
                               for item_type in self.data["types"].values()])

    def __iter__(self):
        for type_data in self.data['types'].values():
            props = [(prop, self.property_types[prop], self.property_docs[prop])
                     for prop in type_data['specific_properties']]
            types = [(t, self.type_urls[t]) for t in type_data['ancestors']]
            yield ParsedType(url=type_data['url'],
                             name=type_data['id'],
                             specific_properties=props,
                             ancestors=types,
                             comment_plain=type_data['comment_plain'])


def munge_element_name(prop_name):
    """
    Nuxeo and Nuxeo Studio use prefixes and suffixes internally.  This
    function prepends or appends characters to avoid collisions.
    """
    return prop_name + "_" if prop_name.endswith("Type") else prop_name


class NuxeoType(object):
    LIST_TYPES_URI = "http://courseload.com/nuxeo/listTypes"
    LIST_TYPES_PATH = "listTypes.xsd"

    def __init__(self, type_data, tree):
        self.type_data = type_data
        self.tree = tree

    def write_xsd(self, output_file_name):
        schema = ET.Element(_xs("schema"),
                            attrib={"targetNamespace": self.type_data.url,
                                    "xmlns:lt" : NuxeoType.LIST_TYPES_URI})

        ET.SubElement(schema, _xs("import"),
                      attrib={"namespace": NuxeoType.LIST_TYPES_URI,
                              "schemaLocation": NuxeoType.LIST_TYPES_PATH})

        for type_name, type_url in self.type_data.ancestors:
            ET.SubElement(schema, _xs("import"),
                          attrib={"namespace": type_url,
                                  "schemaLocation": type_name + ".xsd"})

        schema_elements = (prop for prop in self.type_data.specific_properties
                           if (self.type_data.name,
                               prop[0]) not in self.tree.skipped)

        for prop_name, prop_type, prop_doc in schema_elements:
            if (self.type_data.name, prop_name) in self.tree.multiples:
                prop_type = 'lt:textList'
            el = ET.SubElement(schema, _xs("element"),
                               attrib={"name": munge_element_name(prop_name),
                                       "type": prop_type})
            ann = ET.SubElement(el, _xs("annotation"))
            doc = ET.SubElement(ann, _xs("documentation"))
            doc.text = prop_doc

        ET.ElementTree(schema).write(output_file_name, xml_declaration=True,
                                     encoding="utf-8")

    def is_descendant(self, type_name):
        result = type_name in [x[0] for x in self.type_data.ancestors]
        return result or self.type_data.name in (type_name, 'Thing')

    def dependencies(self):
        return (self.type_data.name, set(x[0] for x in self.type_data.ancestors))


class NuxeoTypeTree(object):
    CORE_TYPES_NAME = "com.courseload.nuxeo.schemadotorg.coreTypes"
    CORE_TYPES_FILE = "core-types-contrib.xml"
    DOC_TYPES_NAME = "com.courseload.nuxeo.schemadotorg.types"
    DOC_TYPES_FILE = "ecm-types-contrib.xml"
    UI_TYPES_NAME = "com.courseload.nuxeo.schemadotorg.ecm.types"
    UI_TYPES_FILE = "ui-types-contrib.xml"
    TYPES_DIR = "osgi"
    SCHEMA_DIR = "schema"
    ICON_FILE = "icon_mappings.txt"
    MULTIPLES_FILE = "valid_multiples.txt"
    SKIPPED_FILE = "skip_fields.txt"

    def __init__(self, terms, parent_type_name, target_dir):
        self.nuxeo_types = [NuxeoType(term, self) for term in terms]
        self.load_icons()
        self.load_multiples()
        self.load_skipped()
        self.parent_type_name = parent_type_name
        self.target_dir = target_dir
        self.schema_dir = os.path.join(target_dir, NuxeoTypeTree.SCHEMA_DIR)
        self.types_dir = os.path.join(target_dir, NuxeoTypeTree.TYPES_DIR)
        os.makedirs(self.schema_dir)
        os.makedirs(self.types_dir)

    def load_icons(self):
        result = {}
        with open(NuxeoTypeTree.ICON_FILE) as input_file:
            for line in input_file:
                name, small_icon, large_icon = line.split()
                result[name] = (name, small_icon, large_icon)
        self.icons = result

    def load_multiples(self):
        result = []
        with open(NuxeoTypeTree.MULTIPLES_FILE) as input_file:
            for line in input_file:
                key = line.split()
                result.append(tuple(key))
        self.multiples = set(result)

    def load_skipped(self):
        result = []
        with open(NuxeoTypeTree.SKIPPED_FILE) as input_file:
            for line in input_file:
                key = line.split()
                result.append(tuple(key))
        self.skipped = set(result)

    def get_icons(self, type_data):
        if type_data.name in self.icons:
            return self.icons[type_data.name]
        else:
            for ancestor_name in reversed([ancestor[0]
                                           for ancestor in type_data.ancestors]):
                if ancestor_name in self.icons:
                    return self.icons[ancestor_name]
        return (type_data.name, '', '')

    def generate(self):
        generated_types = {}

        for nuxeo_type in self.nuxeo_types:
            if nuxeo_type.is_descendant(self.parent_type_name):
                xsd_path = os.path.join(self.schema_dir, '%s.xsd' %
                                        nuxeo_type.type_data.name)
                nuxeo_type.write_xsd(xsd_path)
                generated_types[nuxeo_type.type_data.name] = nuxeo_type

        deps = dict(x.dependencies() for x in generated_types.values())
        order = list(itertools.chain(*toposort(deps)))
        ordered_types = [generated_types[x] for x in order]
        self.generate_schema_contrib(ordered_types)
        self.generate_doctype_contrib(ordered_types)
        self.generate_ui_contrib(list(t for t in ordered_types
                                      if t.type_data.name in self.icons))

    def write_xml(self, path, node):
        ET.ElementTree(node).write(path, xml_declaration=True, encoding="utf-8")

    def generate_schema_contrib(self, generated_types):
        component = ET.Element(
            "component",
            attrib={"name": NuxeoTypeTree.CORE_TYPES_NAME})
        extension = ET.SubElement(
            component,
            "extension",
            attrib={"target": "org.nuxeo.ecm.core.schema.TypeService",
                    "point": "schema"})
        ET.SubElement(extension, "schema",
                      attrib={"name": "listTypes",
                              "src": "schema/listTypes.xsd"})
        for generated_type in generated_types:
            name = generated_type.type_data.name
            ET.SubElement(
                extension,
                "schema",
                attrib={"name": name,
                        "src": "schema/%s.xsd" % name,
                        "prefix": name.lower()})

        self.write_xml(
            os.path.join(self.types_dir, NuxeoTypeTree.CORE_TYPES_FILE),
            component)

    def generate_doctype_contrib(self, generated_types):
        component = ET.Element(
            "component",
            attrib={"name": NuxeoTypeTree.DOC_TYPES_NAME})

        require = ET.SubElement(
            component,
            "require")
        require.text = NuxeoTypeTree.CORE_TYPES_NAME

        extension = ET.SubElement(
            component,
            "extension",
            attrib={"target": "org.nuxeo.ecm.core.schema.TypeService",
                    "point": "doctype"})

        for generated_type in generated_types:
            ancestor_names = (a[0] for a in generated_type.type_data.ancestors)
            doctype = ET.SubElement(
                extension,
                "doctype",
                attrib={"name": generated_type.type_data.name,
                        "extends": "File"})
            for schema in itertools.chain(['common', 'dublincore'],
                                          ancestor_names):
                ET.SubElement(
                    doctype,
                    "schema",
                    attrib={"name": schema})
            ET.SubElement(
                doctype,
                "schema",
                attrib={"name": generated_type.type_data.name})

        self.write_xml(
            os.path.join(self.types_dir, NuxeoTypeTree.DOC_TYPES_FILE),
            component)

    def generate_ui_contrib(self, generated_types):
        component = ET.Element(
            "component",
            attrib={"name": NuxeoTypeTree.UI_TYPES_NAME})
        require = ET.SubElement(
            component,
            "require")
        require.text = "org.nuxeo.ecm.platform.types"

        extension = ET.SubElement(
            component,
            "extension",
            attrib={"target": "org.nuxeo.ecm.platform.types.TypeService",
                    "point": "types"})

        for generated_type in generated_types:
            type_data = generated_type.type_data
            _, small_icon, large_icon = self.get_icons(type_data)
            type_el = ET.SubElement(
                extension,
                "type",
                attrib={"id": type_data.name})
            ET.SubElement(type_el, "icon").text = small_icon
            ET.SubElement(type_el, "bigIcon").text = large_icon
            ET.SubElement(type_el, "label").text = type_data.name
            ET.SubElement(type_el, "description").text = type_data.comment_plain
            ET.SubElement(type_el, "category").text = "SimpleDocument"
            ET.SubElement(type_el, "default-view").text = "view_documents"
            layouts = ET.SubElement(type_el, "layouts",
                attrib={"mode": "any"})
            ET.SubElement(layouts, "layout").text = "creative_work"

        for container in ["Folder", "Workspace"]:
            ct = ET.SubElement(extension, "type", attrib={"id": container})
            st = ET.SubElement(ct, "subtypes")
            for generated_type in generated_types:
                ET.SubElement(st, "type").text = generated_type.type_data.name

        self.write_xml(
            os.path.join(self.types_dir, NuxeoTypeTree.UI_TYPES_FILE),
            component)


def main(root_type):
    shutil.rmtree(TARGET_DIR, ignore_errors=True)
    os.makedirs(TARGET_DIR)
    data = json.load(urllib2.urlopen(ALL_JSON_URL))
    schema_terms = SchemaTerms(data)
    nuxeo_types = NuxeoTypeTree(schema_terms, root_type, TARGET_DIR)
    nuxeo_types.generate()


if __name__ == "__main__":
    root_type = sys.argv[1] if len(sys.argv) > 1 else 'CreativeWork'
    main(root_type)
