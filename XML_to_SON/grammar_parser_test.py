import xml.etree.ElementTree as ET
import re
import pprint
import json
import os.path
import argparse

def get_element_type(node):
    for child in node:
        if child.tag.endswith("data") and "type" in child.attrib:
            xml_type = child.attrib['type']
            return conversion_dict.get(xml_type, 'Unknown')
    return None

def process_element(node, parent_attrib=None):
    if parent_attrib is None:
        parent_attrib = {}
    ele_dict = {}
    name = node.attrib.get('name') 
    ele_dict[name] = {}

    if not parent_attrib:
        ele_dict[name]['minOccurs'] = 1
        ele_dict[name]['maxOccurs'] = 1

    element_type = get_element_type(node)
    if element_type:
        ele_dict[name]['ValType'] = element_type
    else:
        for child in node:
            if child.tag.endswith("text"):
                ele_dict[name]['ValType'] = "String"
                break

    for child in node:
        child_attrib = {}
        if child.tag.endswith("choice"):
            choice_str = handle_choice_element(child)
            if choice_str:
                ele_dict[name]['ChildExactlyOne'] = f"{choice_str}"
            break
        if child.tag not in {f"{ns}zeroOrMore", f"{ns}oneOrMore", f"{ns}optional"}:
            child_attrib = {'minOccurs': 1, 'maxOccurs': 1}
        ele_dict[name].update(process_node(child, child_attrib))

    ele_dict[name].update(parent_attrib)

    return ele_dict

def process_node(node, add_attrib={}):
            
    node_dict = {}
    if node.tag.endswith("element"):
        node_dict.update(process_element(node, add_attrib))
    elif node.tag.endswith("optional"):
        for child in node:
            node_dict.update(process_node(child, {'minOccurs': 0, 'maxOccurs': 1}))
    elif node.tag.endswith("zeroOrMore"):
        for child in node:
            node_dict.update(process_node(child, {'minOccurs': 0}))
    elif node.tag.endswith("oneOrMore"):
        for child in node:
            node_dict.update(process_node(child, {'minOccurs': 1}))
    else:
        for child in node:
            node_dict.update(process_node(child))

    return node_dict

def generate_child_exactly_one_line(entity_type):
        if entity_type == "facility":
            options = facilities
        elif entity_type == "region":
            options = regions
        elif entity_type == "institution":
            options = institutions
        else:
            options = []
        return f"ChildExactlyOne=[{'|'.join(options)}]"

def handle_choice_element(node):
    choices = []
    for child in node:
        if child.tag == f"{ns}element":
            name = child.attrib.get('name', 'Unknown')
            choices.append(name)

    
    if node.text:
        processed_schemas = None
        if '@Facility_REFS@' in node.text:
            processed_schemas = processed_facilities
            replacement_text = generate_child_exactly_one_line('facility')
            node.text = node.text.replace('@Facility_REFS@', replacement_text)
            return f"[{' '.join(facilities)}]"
        elif '@Region_REFS@' in node.text:
            processed_schemas = processed_regions
            replacement_text = generate_child_exactly_one_line('region')
            node.text = node.text.replace('@Region_REFS@', replacement_text)
            return f"[{' '.join(regions)}]"
        elif '@Inst_REFS@' in node.text:
            processed_schemas = processed_institutions
            replacement_text = generate_child_exactly_one_line('institution')
            node.text = node.text.replace('@Inst_REFS@', replacement_text)
            return f"[{' '.join(institutions)}]"
        
    if choices:
        return f"[{' '.join(choices)}]"
    return ""

def process_schema_from_mjson(xml_string, element_name):
    root = ET.fromstring(xml_string)
    processed_content = process_node(root)
    
    return {element_name: processed_content}

def integrate_detailed_schemas(final_json, processed_facilities, processed_regions, processed_institutions):
    for facility_name, facility_config in processed_facilities.items():
        if "facility" in final_json["simulation"] and facility_name in final_json["simulation"]["facility"]["config"]["ChildExactlyOne"]:
            new_facility_config = {"InputTmpl": '"'+facility_name+'"'}
            new_facility_config.update(facility_config)
            final_json["simulation"]["facility"]["config"][facility_name] = new_facility_config

    for region_name, region_config in processed_regions.items():
        if "region" in final_json["simulation"] and region_name in final_json["simulation"]["region"]["config"]["ChildExactlyOne"]:
            new_region_config = {"InputTmpl": '"' + region_name + '"'}
            new_region_config.update(region_config)
            final_json["simulation"]["region"]["config"][region_name] = new_region_config

    for institution_name, institution_config in processed_institutions.items():
        if "region" in final_json["simulation"] and institution_name in final_json["simulation"]["region"]["institution"]["config"]["ChildExactlyOne"]:
            new_institution_config = {"InputTmpl": '"' + institution_name + '"'}
            new_institution_config.update(institution_config)
            final_json["simulation"]["region"]["institution"]["config"][institution_name] = new_institution_config

    return final_json

def custom_format(value):
    val_str = json.dumps(value)
    val_str = re.sub(r'^"|"$', '', val_str)
    val_str = val_str.replace('\\"', '"')
    return val_str

def custom_serialize(obj, key_name="simulation", indent=0):
    lines = []
    base_indent = " " * indent
    child_indent = " " * (indent + 4)

    lines.append(f"{base_indent}{key_name}={{")

    for key, value in obj.items():
        if isinstance(value, dict):
            nested = custom_serialize(value, key, indent + 4)
            lines.append(nested)
        else:
            val_str = custom_format(value)
            lines.append(f"{child_indent}{key}={val_str}")

    lines.append(f"{base_indent}}}")

    return "\n".join(lines)

def custom_serialize_for_template(obj, annotations, key_name, indent=0):
    lines = []
    base_indent = " " * indent
    doc_indent = " " * (indent + 8) 
    child_indent = " " * (indent + 4)

    annotation_key = f":agents:{key_name}"
    if annotation_key not in annotations:
        matching_keys = [key for key in annotations.keys() if key.endswith(key_name)]
        if matching_keys:
            annotation_key = matching_keys[0]
        else:
            print(f"No annotations  for {key_name}.")
            return ""
        
    annotation = annotations[annotation_key]

    if 'vars' not in annotation or not isinstance(annotation['vars'], dict):
        print(f"'vars' missing or not a dictionary in annotations for {key_name}.")
        return ""

    for key, value in obj.items():
        var_info = annotation['vars'].get(key, {})

        if isinstance(var_info, str):
            alias_info = annotation['vars'].get(var_info, {})
            if not isinstance(alias_info, dict):
                print(f"Alias {var_info} for {key} in {key_name} does not point to a valid dictionary.")
                continue
            var_doc = alias_info.get('doc', 'No documentation available')
        elif isinstance(var_info, dict):
            var_doc = var_info.get('doc', 'No documentation available')
        else:
            print(f"Unexpected type {type(var_info)} for {key} in {key_name}.")
            continue

    
    doc_string = annotations.get(annotation_key, {}).get('doc', 'No documentation available') #PENDING: work around streams_ in Mixer not being a dictionary.
    doc_lines = [f'%{line}' for line in doc_string.split('\n')] + ['']
    lines.extend(doc_lines)
    lines.append(f'{base_indent}{key_name} {{')

    for key, value in obj.items():
        optional = "(optional)" if value.get("minOccurs", "1") == "0" else ""
        type_str = f"[{value.get('ValType', 'Unknown')}]"
        var_doc = annotations[annotation_key].get('vars', {}).get(key, {}).get('doc', 'No documentation')
        doc_lines = [f'%{optional} {type_str} {line}' for line in var_doc.split('\n')]

        lines.extend([f"{doc_indent}{line}" for line in doc_lines])

        default_val = annotations[annotation_key].get('vars', {}).get(key, {}).get('default', '')
        default_str = " = " + (str(default_val) if default_val != '' else "")
        lines.append(f"{child_indent}{key}{default_str}\n")

    lines.append(f'{base_indent}}}')
    lines.append('') 

    return "\n".join(lines)

def save_template_for_all_schemas(processed_schemas, annotations, folder_name = "templates"):
    os.makedirs(folder_name, exist_ok=True)
    for key_name, schema_contents in processed_schemas.items():
        template_string = custom_serialize_for_template(schema_contents, annotations, key_name)
        filename = f"{folder_name}/{key_name}.tmpl"
        with open(filename, "w") as file:
            file.write(template_string)
        print(f"Template for {key_name} saved as {filename}")

if __name__ == "__main__":    
    parser = argparse.ArgumentParser(description='Process an XML schema file and a corresponding JSON file, and output to a specified file.')
    parser.add_argument('--xml', type=str, required=True, help='The path to the XML schema file.')
    parser.add_argument('--json', type=str, required=True, help='The path to the JSON file.')
    parser.add_argument('--output', type=str, required=True, help='The path for the output file.')
    args = parser.parse_args()
    
    tree = ET.parse(args.xml)  
    root = tree.getroot()
    ns = re.match(r'\{.*\}', root.tag).group(0) 
    simulation = root[0][0]
    
    conversion_dict = {
        'string': 'String',
        'nonNegativeInteger': 'Int',
        'boolean': 'Boolean',
        'double': 'double',
        'positiveInteger': 'Int',
        'float': 'Real',
        'duration': 'Int',
        'integer': 'Int',
        'nonPositiveInteger': 'Int',
        'negativeInteger': 'Int',
        'long': 'Real',
        'int': 'Int',
        'token': 'String'
    }
      
    with open(args.json, 'r') as file:
        m_json = json.load(file) 
        
    processed_facilities = {}
    processed_regions = {}
    processed_institutions = {}

    facilities = []
    regions = []
    institutions = []

    for spec in m_json["schema"]:
        element_name = spec.split(":")[-1]  
        xml_content = m_json["schema"][spec]
        entity_type = m_json["annotations"][spec]["entity"]
        entity_name = spec.split(":")[-1]
        processed_and_wrapped = process_schema_from_mjson(xml_content, element_name)
        if entity_type == "facility":
            processed_facilities.update(processed_and_wrapped)
            facilities.append(entity_name)
        elif entity_type == "region":
            processed_regions.update(processed_and_wrapped)
            regions.append(entity_name)
        elif entity_type == "institution":
            processed_institutions.update(processed_and_wrapped)
            institutions.append(entity_name)  

    result = process_node(simulation)

    final_result = {"simulation": result["simulation"]}
    
    final_result_detailed_schemas = integrate_detailed_schemas(final_result, processed_facilities, processed_regions, processed_institutions)

    # Intermediate file created to track parsing progress. 
    # with open("sample_schema_product.json", "w") as outfile:
    #     json.dump(final_result_detailed_schemas, outfile, indent=4)
        
    serialized_string = custom_serialize(final_result_detailed_schemas["simulation"])

    
    with open(args.output, "w") as sch_file:
        sch_file.write(serialized_string)

# These following lines create the templates and save them in a folder named "Templates"
# save_template_for_all_schemas(processed_facilities, m_json["annotations"])
# save_template_for_all_schemas(processed_regions, m_json["annotations"])
# save_template_for_all_schemas(processed_institutions, m_json["annotations"])