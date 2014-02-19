import collections
import json
import os
import shutil
import urllib2
import xml.etree.ElementTree as ET


ALL_JSON_URL = "http://schema.rdfs.org/all.json"
TARGET_DIR = "../../../target/generated-sources"
XS_URL = "http://www.w3.org/2001/XMLSchema"


ET.register_namespace("xs", XS_URL)

ParsedType = collections.namedtuple(
    'ParsedType',
    ['name', 'url', 'specific_properties', 'ancestors'])


def _xs(element_name):
    return "{%s}%s" % (XS_URL, element_name)


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
                             ancestors=types)


def munge_element_name(prop_name):
    """
    Nuxeo and Nuxeo Studio use prefixes and suffixes internally.  This
    function prepends or appends characters to avoid collisions.
    """
    return prop_name + "_" if prop_name.endswith("Type") else prop_name


class NuxeoType(object):
    def __init__(self, type_data):
        self.type_data = type_data

    def write_xsd(self, output_file_name):
        schema = ET.Element(_xs("schema"),
                            attrib={"targetNamespace": self.type_data.url})

        for type_name, type_url in self.type_data.ancestors:
            ET.SubElement(schema, _xs("import"),
                          attrib={"namespace": type_url,
                                  "schemaLocation": type_name + ".xsd"})

        for prop_name, prop_type, prop_doc in self.type_data.specific_properties:
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


class NuxeoTypeTree(object):
    CORE_TYPES_NAME = "com.courseload.nuxeo.schemadotorg.coreTypes"
    CORE_TYPES_FILE = "core-types-contrib.xml"
    TYPES_DIR = "osgi"
    SCHEMA_DIR = "schema"

    def __init__(self, terms, parent_type_name, target_dir):
        self.nuxeo_types = (NuxeoType(term) for term in terms)
        self.parent_type_name = parent_type_name
        self.target_dir = target_dir
        self.schema_dir = os.path.join(target_dir, NuxeoTypeTree.SCHEMA_DIR)
        self.types_dir = os.path.join(target_dir, NuxeoTypeTree.TYPES_DIR)
        os.makedirs(self.schema_dir)
        os.makedirs(self.types_dir)

    def generate(self):
        generated_types = []

        for nuxeo_type in self.nuxeo_types:
            if nuxeo_type.is_descendant(self.parent_type_name):
                xsd_path = os.path.join(self.schema_dir, '%s.xsd' %
                                        nuxeo_type.type_data.name)
                nuxeo_type.write_xsd(xsd_path)
                generated_types.append(nuxeo_type)

        self.generate_schema_contrib(generated_types)

    def generate_schema_contrib(self, generated_types):
        component = ET.Element(
            "component",
            attrib={"name": NuxeoTypeTree.CORE_TYPES_NAME})
        extension = ET.SubElement(
            component,
            "extension",
            attrib={"target": "org.nuxeo.ecm.core.schema.TypeService",
                    "point": "schema"})

        for generated_type in generated_types:
            name = generated_type.type_data.name
            ET.SubElement(
                extension,
                "schema",
                attrib={"name": name,
                        "src": "schema/%s.xsd" % name,
                        "prefix": name.lower()})

        ET.ElementTree(component).write(
            os.path.join(self.types_dir, NuxeoTypeTree.CORE_TYPES_FILE),
            xml_declaration=True,
            encoding="utf-8")


def main():
    shutil.rmtree(TARGET_DIR, ignore_errors=True)
    os.makedirs(TARGET_DIR)
    data = json.load(urllib2.urlopen(ALL_JSON_URL))
    schema_terms = SchemaTerms(data)
    nuxeo_types = NuxeoTypeTree(schema_terms, 'CreativeWork', TARGET_DIR)
    nuxeo_types.generate()

if __name__ == "__main__":
    main()


