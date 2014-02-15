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
        self.type_urls = {}
        self.data = None

    def setup(self):
        self.data = json.load(urllib2.urlopen(self.url))

        for prop in self.data["properties"].values():
            key = prop["id"]
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
            props = [(prop, self.property_types[prop])
                     for prop in type_data['specific_properties']]
            types = [(t, self.type_urls[t]) for t in type_data['ancestors']]
            yield ParsedType(url=type_data['url'],
                             name=type_data['id'],
                             specific_properties=props,
                             ancestors=types)


class XmlSchemaEmitter(object):
    def __init__(self, item_type):
        self.item_type = item_type

    def create_tree(self):
        schema = ET.Element(_xs("schema"),
                            attrib={"targetNamespace": self.item_type.url})

        for type_name, type_url in self.item_type.ancestors:
            ET.SubElement(schema, _xs("import"),
                          attrib={"namespace": type_url,
                                  "schemaLocation": type_name + ".xsd"})

        for prop_name, prop_type in self.item_type.specific_properties:
            ET.SubElement(schema, _xs("element"),
                          attrib={"name": prop_name,
                                  "type": prop_type})
        return ET.ElementTree(schema)


def emit_xsd(item_type):
    emitter = XmlSchemaEmitter(item_type)
    tree = emitter.create_tree()
    path = os.path.join(TARGET_DIR, "%s.xsd" % item_type.name)
    with open(path, "w") as output:
        tree.write(output, xml_declaration=True, encoding="utf-8")


if __name__ == "__main__":
    shutil.rmtree(TARGET_DIR)
    os.makedirs(TARGET_DIR)
    parser = RdfsOrgParser(ALL_JSON_URL)
    for datatype in parser.parse_types():
        is_creative_work = 'CreativeWork' in [x[0] for x in datatype.ancestors]
        if datatype.specific_properties and (
                is_creative_work or datatype.name in ('CreativeWork', 'Thing')):
            emit_xsd(datatype)
