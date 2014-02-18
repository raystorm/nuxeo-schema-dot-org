import os
import xml.dom.minidom

SOURCE_DIR = "../../../target/generated-sources/schema"
TARGET_DIR = "../../../src/main/resources/schema"

for filename in os.listdir(SOURCE_DIR):
    data = xml.dom.minidom.parse(os.path.join(SOURCE_DIR, filename))
    pretty_xml_string = data.toprettyxml().encode('UTF-8')
    with open(os.path.join(TARGET_DIR, filename), 'w') as output_file:
        output_file.write(pretty_xml_string)
