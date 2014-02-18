import collections
import json
import os
import shutil
import urllib2
import xml.etree.ElementTree as ET


ALL_JSON_URL = "http://schema.rdfs.org/all.json"
TARGET_DIR = "../../../target/generated-sources/schema"
XS_URL = "http://www.w3.org/2001/XMLSchema"

ET.register_namespace("xs", XS_URL)

ParsedType = collections.namedtuple(
    'ParsedType',
    ['name', 'url', 'specific_properties', 'ancestors'])


def _xs(element_name):
    return "{%s}%s" % (XS_URL, element_name)


class RdfsOrgParser(object):
    def __init__(self, url):
        self.url = url
        self.property_types = {}
        self.property_docs = {}
        self.type_urls = {}
        self.data = None

    def setup(self):
        self.data = json.load(urllib2.urlopen(self.url))

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

    def parse_types(self):
        self.setup()
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


def write_tree(item_type, output_file):
    schema = ET.Element(_xs("schema"),
                        attrib={"targetNamespace": item_type.url})

    for type_name, type_url in item_type.ancestors:
        ET.SubElement(schema, _xs("import"),
                      attrib={"namespace": type_url,
                              "schemaLocation": type_name + ".xsd"})

    for prop_name, prop_type, prop_doc in item_type.specific_properties:
        el = ET.SubElement(schema, _xs("element"),
                           attrib={"name": munge_element_name(prop_name),
                                   "type": prop_type})
        ann = ET.SubElement(el, _xs("annotation"))
        doc = ET.SubElement(ann, _xs("documentation"))
        doc.text = prop_doc

    ET.ElementTree(schema).write(output_file, xml_declaration=True,
                                     encoding="utf-8")


def emit_xsd(item_type):
    path = os.path.join(TARGET_DIR, "%s.xsd" % item_type.name)
    with open(path, "w") as output:
        write_tree(item_type, output)


if __name__ == "__main__":
    shutil.rmtree(TARGET_DIR)
    os.makedirs(TARGET_DIR)
    parser = RdfsOrgParser(ALL_JSON_URL)
    for datatype in parser.parse_types():
        is_creative_work = 'CreativeWork' in [x[0] for x in datatype.ancestors]
        if is_creative_work or datatype.name in ('CreativeWork', 'Thing'):
            emit_xsd(datatype)
