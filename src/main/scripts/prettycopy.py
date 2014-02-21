import os
import xml.dom.minidom

SOURCE_DIR = "../../../tmp"
TARGET_DIR = "../../../src/main/resources"


def pretty_copy(source_dir, target_dir):
    for filename in os.listdir(source_dir):
        data = xml.dom.minidom.parse(os.path.join(source_dir, filename))
        pretty_xml_string = data.toprettyxml().encode('UTF-8')
        with open(os.path.join(target_dir, filename), 'w') as output_file:
            output_file.write(pretty_xml_string)


if __name__ == '__main__':
    schema_target = os.path.join(TARGET_DIR, 'schema')
    osgi_target = os.path.join(TARGET_DIR, 'OSGI-INF')
    for p in [schema_target, osgi_target]:
        if not os.path.exists(p):
            os.makedirs(p)
    pretty_copy(os.path.join(SOURCE_DIR, 'schema'), schema_target)
    pretty_copy(os.path.join(SOURCE_DIR, 'osgi'), osgi_target)
