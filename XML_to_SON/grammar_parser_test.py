import xml.etree.ElementTree as ET
import re
import json
import os.path
import argparse
import re
import os
import shutil

processed_facilities = {}
processed_regions = {}
processed_institutions = {}

facilities = []
regions = []
institutions = []
highlighter_items = ['simulation', ' control ', ' archetypes ',' facility ', ' region ', ' recipe ']

class highlighter:
    def __init__(self):
        self.rgb_dict = {'black': [0,0,0],
                         'white': [255, 255, 255],
                         'red': [255, 0, 0],
                         'lime': [0, 255, 0],
                         'blue': [0, 0, 255],
                         'yellow': [255, 255, 0],
                         'cyan': [0, 255, 255],
                         'magenta': [255, 0, 255],
                         'silver': [192, 192, 192],
                         'orange': [255, 130, 0], 
                         'olive': [0, 128, 0]}
        self.highlight_str = self.make_basic_son() 

    def highlight_maker(self, name, word, bold = False, italic = False, background = False, alpha = 10, color='blue'):
        s = f"""rule("{name}") {{
pattern = "{word}"
bold = {bold}
italic = {italic}
foreground {{
    red = {self.rgb_dict[color][0]}
    green = {self.rgb_dict[color][1]}
    blue = {self.rgb_dict[color][2]}
}}       
        """
        if background != False:
            s += f"""background {{
    red = {self.rgb_dict[background][0]}
    green = {self.rgb_dict[background][1]}
    blue = {self.rgb_dict[background][2]}
    alpha = {alpha}
}}
"""
        s += """}
        """
        return s
    
    def make_basic_son(self):
        highlight_str = ''
        for i in highlighter_items:
            highlight_str += self.highlight_maker(i, i, bold=True)
        highlight_str += self.highlight_maker('equal', "=" , background = 'silver', color='black', alpha=150)
        highlight_str += self.highlight_maker('Comment', "%.*" , color = 'olive', italic=True)
        # The next line (rule for Quoted String) was hardcoded as it was very intricate to handle quotation marks. 
        # The highlighter is only valid if the pattern appears exactly as below (no more or less quotation marks).
        highlight_str += '''rule("Quoted string") {
pattern = """'[^']*'|"[^"]*"""" 
bold = true
foreground {
    red = 255
    green = 130
    blue = 0
    }
background {
    red = 255
    green = 130
    blue = 0
    alpha = 25
    }
}'''
        return highlight_str

def get_element_type(node):
    
    conversion_dict = {
        'string': 'String',
        'nonNegativeInteger': 'Int',
        'boolean': 'Int',
        'double': 'Real',
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
    
    for child in node:
        if child.tag.endswith("data") and "type" in child.attrib:
            xml_type = child.attrib['type']
            return conversion_dict.get(xml_type, 'Unknown')
    return None

def process_element(node, parent_attrib={}):
    ele_dict = {}
    name = node.attrib.get('name')
    formatted_name = f'"{name}"' if "-" in name else name
    ele_dict[formatted_name] = {}

    if not parent_attrib:
        ele_dict[formatted_name]['MinOccurs'] = 1
        ele_dict[formatted_name]['MaxOccurs'] = 1

    element_type = get_element_type(node)
    if element_type:
        ele_dict[formatted_name]['ValType'] = element_type
    else:
        for child in node:
            if child.tag.endswith("text"):
                ele_dict[formatted_name]['ValType'] = "String"
                break

    for child in node:
        child_attrib = {}
        if child.tag.endswith("choice"):
            choice_str, processed_choices = handle_choice_element(child)
            if choice_str:
                ele_dict[formatted_name]['ChildAtMostOne'] = f"{choice_str}"
                ele_dict[formatted_name].update(processed_choices)
            break
        if child.tag not in {f"{ns}zeroOrMore", f"{ns}oneOrMore", f"{ns}optional"}:
            child_attrib = {'MinOccurs': 1, 'MaxOccurs': 1}
        ele_dict[formatted_name].update(process_node(child, child_attrib))

    ele_dict[formatted_name].update(parent_attrib)

    return ele_dict

def process_node(node, add_attrib={}):
            
    node_dict = {}
    if node.tag.endswith("element"):
        node_dict.update(process_element(node, add_attrib))
    elif node.tag.endswith("optional"):
        for child in node:
            node_dict.update(process_node(child, {'MinOccurs': 0, 'MaxOccurs': 1}))
    elif node.tag.endswith("zeroOrMore"):
        for child in node:
            node_dict.update(process_node(child, {'MinOccurs': 0}))
    elif node.tag.endswith("oneOrMore"):
        for child in node:
            node_dict.update(process_node(child, {'MinOccurs': 1}))
    else:
        for child in node:
            node_dict.update(process_node(child))

    return node_dict

def replace_text (text):
    if text.startswith("@Facility"):
        list = facilities
    elif text.startswith("@Region"):
        list = regions
    elif text.startswith("@Inst"):
        list = institutions
    replacement_text = f"ChildAtMostOne=[{'|'.join(list)}]"
    text = text.replace(text,replacement_text)
    return list

def handle_choice_element(node):
    choices = []
    processed_choices = {} 
    for child in node:
        if child.tag.endswith("element"):
            name = child.attrib.get('name', 'Unknown')
            formatted_name = f'"{name}"' if "-" in name else name
            choices.append(formatted_name)
            processed_choices.update(process_node(child, {}))
    
    if node.text.split() != []:
        text = ''.join(node.text.split())
        list = replace_text(text)  
        return f"[{' '.join(list)}]", {}
        
    choice_str = f"[{' '.join(choices)}]" if choices else ""
    return choice_str, processed_choices

def process_schema_from_mjson(xml_string, element_name):
    root = ET.fromstring(xml_string)
    processed_content = process_node(root)
    return {element_name: processed_content}

def integrate_detailed_schemas(final_json, processed_facilities, processed_regions, processed_institutions):
    for agent_type, agent_list in [ ('facility', processed_facilities), ('region', processed_regions) ]:
        if agent_type in final_json["simulation"]:
            for agent_name, agent_config in agent_list.items():
                if agent_name in final_json["simulation"][agent_type]["config"]["ChildAtMostOne"]:
                    new_agent_config = {"InputTmpl": f"{agent_name}", "MaxOccurs": 1}
                    new_agent_config.update(agent_config)
                    final_json["simulation"][agent_type]["config"][agent_name] = new_agent_config
                    
    for institution_name, institution_config in processed_institutions.items():
        if "region" in final_json["simulation"] and institution_name in final_json["simulation"]["region"]["institution"]["config"]["ChildAtMostOne"]:
            new_institution_config = {"InputTmpl": '"' + institution_name + '"'}
            new_institution_config.update(institution_config)
            final_json["simulation"]["region"]["institution"]["config"][institution_name] = new_institution_config

    simulation_dict = final_json["simulation"]
    simulation_dict["MinOccurs"] = 1
    simulation_dict["MaxOccurs"] = 1

    simulation_dict = add_child_at_least_one(simulation_dict)
    simulation_dict = add_child_at_least_one_for_region(simulation_dict)

    final_json["simulation"] = simulation_dict

    return final_json

def custom_format(value):
    val_str = json.dumps(value)
    val_str = re.sub(r'^"|"$', '', val_str)
    val_str = val_str.replace('\\"', '"')
    return val_str

def custom_serialize(obj, key_name="simulation", indent_size=0):
    lines = []
    child_indent_size = indent_size + 4
    base_indent = " " * indent_size
    child_indent = " " * (child_indent_size)

    lines.append(f"{base_indent}{key_name}={{")

    for key, value in obj.items():
        if isinstance(value, dict):
            lines.append(custom_serialize(value, key, child_indent_size + 4))
        else:
            val_str = custom_format(value)
            lines.append(f"{child_indent}{key}={val_str}")

    lines.append(f"{base_indent}}}")

    return "\n".join(lines)

def generate_doc_lines_for_key(key, value, annotations, schema_data, annotation_key, doc_indent, child_indent):
    lines = []

    if key in ['MinOccurs', 'MaxOccurs']:
        return lines

    if isinstance(value, dict) and 'val' in value:
        var_info = annotations.get(annotation_key, {}).get('vars', {}).get(key, {})
        optional = " (optional)" if value.get("MinOccurs", 1) == 0 else ""
        val_type = value.get('ValType', var_info.get('type', 'Unknown'))
        type_str = f"[{val_type}]"
        var_doc = var_info.get('doc', 'No documentation available')

        doc_lines = [f"% {optional} {type_str} {line}".strip() for line in var_doc.split('\n')]
        lines.extend([f"{doc_indent}{line}" for line in doc_lines])

        default_val = var_info.get('default', "")

        lines.append(f"{child_indent}{key} {{val = {default_val}}}\n")
        return lines

    if isinstance(value, dict) and any(isinstance(v, dict) for v in value.values()):
        lines.append(f"{child_indent}{key} {{\n")

        inner_indent = child_indent + "    "
        for sub_key, sub_value in value.items():
            nested_lines = generate_doc_lines_for_key(sub_key, sub_value, annotations, schema_data, annotation_key, doc_indent, inner_indent)
            lines.extend(nested_lines)

        lines.append(f"{child_indent}}}\n") 
        return lines

    annotation_namespace = annotations.get(annotation_key, {})
    var_info = annotation_namespace.get('vars', {}).get(key, {})
    if not isinstance(var_info, dict):
        var_info = {}

    optional = " (optional)" if isinstance(value, dict) and value.get("MinOccurs", 1) == 0 else ""
    val_type = value.get('ValType', var_info.get('type', 'Unknown')) if isinstance(value, dict) else 'Unknown'
    type_str = f"[{val_type}]"
    var_doc = var_info.get('doc', 'No documentation available')

    doc_lines = [f"% {optional} {type_str} {line}".strip() for line in var_doc.split('\n')]
    lines.extend([f"{doc_indent}{line}" for line in doc_lines])

    default_val = var_info.get('default', None)
    default_str = f" = {default_val}" if default_val is not None else " ="

    lines.append(f"{child_indent}{key}{default_str}\n")
    return lines

def custom_serialize_for_template(obj, annotations, schema_data, key_name):
    lines = []
    indent_size = 0
    tab = 4 * " "
    base_indent = indent_size * " "
    doc_indent = base_indent + 2 * tab
    child_indent = base_indent + tab

    cycamore_or_agent = key_name.split("_")[-3]
    archetype_name = key_name.split("_")[-1]
    matching_keys = [key for key in annotations.keys() if key.split(":")[-2] == cycamore_or_agent and key.split(":")[-1] == archetype_name]
    
    if not matching_keys:
        print(f"DEBUG: No matching keys found for key_name: {key_name}")
        print(f"DEBUG: Available keys in annotations: {list(annotations.keys())}")
        return None

    annotation_key = matching_keys[0]
    doc_string = annotations.get(annotation_key, {}).get('doc', 'No documentation available')
    doc_lines = [f'% {line}' for line in doc_string.split('\n')] + ['']
    lines.extend(doc_lines)
    lines.append(f'{base_indent}{key_name} {{')

    for key, value in obj.items():
        lines.extend(generate_doc_lines_for_key(key, value, annotations, schema_data, annotation_key, doc_indent, child_indent))

    lines.append(f'{base_indent}}}')
    lines.append('')

    return "\n".join(lines)

def save_template_for_all_schemas(processed_schemas, annotations, schema_data, template_dir="templates"):
    for key_name, schema_contents in processed_schemas.items():
        template_string = custom_serialize_for_template(schema_contents, annotations, schema_data, key_name)
        if template_string:
            filename = f"{template_dir}/{key_name}.tmpl"
            with open(filename, "w") as file:
                file.write(template_string)
        else:
            print(f"Failed to generate template for {key_name}")
            
def add_child_at_least_one(simulation_dict):
    attribute_keys = {"InputTmpl", "MinOccurs", "MaxOccurs"}
    children_without_max_occurs_one = [
        key for key, value in simulation_dict.items()
        if key not in attribute_keys and not (isinstance(value, dict) and value.get("MaxOccurs") == 1)
    ]
    if children_without_max_occurs_one:
        simulation_dict = {
            "ChildAtLeastOne": f"[{' '.join(children_without_max_occurs_one)}]",
            **simulation_dict
        } 
        for child_name in children_without_max_occurs_one:
            if child_name in simulation_dict and isinstance(simulation_dict[child_name], dict):
                simulation_dict[child_name]["InputTmpl"] = f'"{child_name}"'
            else:
                simulation_dict[child_name] = {"InputTmpl": f'"{child_name}"'}
    
    return simulation_dict

def add_child_at_least_one_for_region(simulation_dict):
    if "region" in simulation_dict:
        region_dict = simulation_dict["region"]
        region_dict["ChildAtLeastOne"] = "[institution]"

        if "institution" not in region_dict:
            region_dict["institution"] = {}
        
        region_dict["institution"]["InputTmpl"] = '"institution"'
        simulation_dict["region"] = region_dict
    
    return simulation_dict

def parse_arguments():
    parser = argparse.ArgumentParser(description='Process an XML schema file, a corresponding JSON file, an output to a specified file, and a path leading to the rte directory.')
    parser.add_argument('--xml', type=str, required=True, help='The path to the XML schema file.')
    parser.add_argument('--json', type=str, required=True, help='The path to the JSON file.')
    parser.add_argument('--output', type=str, required=True, help='The path for the output file.')
    parser.add_argument('--path', type=str, required=True, help='The path for the rte directory.')
    return parser.parse_args()

def generate_cyclus_workbench_files(workbench_rte_dir, etc_dir, cyclus_cmd):
    cyclus_dir = os.path.join(workbench_rte_dir, 'cyclus')
    if not os.path.exists(cyclus_dir):
        os.mkdir(cyclus_dir)

    schema_path = os.path.join(cyclus_dir, args.output)
    highlight_path = os.path.join(etc_dir, 'grammars', 'highlighters', 'cyclus.wbh')
    grammar_path = os.path.join(etc_dir, 'grammars', 'cyclus.wbg')

    grammar_str  = """name= Cyclus
enabled = true

parser = waspson
schema = "%s"
validator = wasp

templates = "%s"

highlighter = "%s"

extensions = [cyclus]
maxDepth = 10
""" %(schema_path, template_dir, highlight_path)
    
    #grammar file
    with open(grammar_path, 'w') as f:
        f.write(grammar_str)
    with open(schema_path.replace('.sch', '.wbg'), 'w') as f:
        f.write(grammar_str)
     
    #schema file    
    with open(schema_path, 'w') as f:
        f.write(serialized_string)
    
    #templates    
    if not os.path.exists(template_dir):
        os.mkdir(template_dir)

    #highliter file
    h_ = highlighter()
    with open(highlight_path, 'w') as f:
        f.write(h_.highlight_str)
    
def create_template_for_node(node_name, node_content, template_dir="templates"):
    template_name = node_name
    template_path = os.path.join(template_dir, f"{template_name}.tmpl")
    
    if os.path.exists(template_path):
        return
    
    template_content = generate_template_content(node_name, node_content)
    with open(template_path, "w") as template_file:
        template_file.write(template_content)
    
def generate_template_content(node_name, node_content, indent_level=0):
    indent = "    " * indent_level
    lines = [f"{indent}{node_name} {{"]

    for key, value in node_content.items():
        if key in {"MinOccurs", "MaxOccurs", "ValType", "InputTmpl"}:
            continue

        if isinstance(value, dict):
            non_ignored_keys = [
                k for k in value.keys() if k not in {"MinOccurs", "MaxOccurs", "ValType", "InputTmpl"}
            ]
            if not non_ignored_keys:
                lines.append(f"{indent}    {key} = ")
            else:
                nested_content = generate_template_content(key, value, indent_level + 1)
                lines.append(nested_content)
        else:
            lines.append(f"{indent}    {key} = ")

    lines.append(f"{indent}}}")
    
    return "\n".join(lines)

def create_templates_for_missing_nodes(final_json, template_dir="templates"):
    os.makedirs(template_dir, exist_ok=True)
    
    child_at_least_one_line = final_json["simulation"].get("ChildAtLeastOne", "")
    children = child_at_least_one_line.strip("[]").split()

    for child_name in children:
        if child_name in final_json["simulation"]:
            node_content = final_json["simulation"][child_name]
            create_template_for_node(child_name, node_content, template_dir) 
        if (" " + child_name + " ") not in highlighter_items:
            child_name_highlight = " " + child_name + " "
            highlighter_items.append(child_name_highlight)  
    
if __name__ == "__main__":    
    args = parse_arguments()
    
    tree = ET.parse(args.xml)  
    root = tree.getroot()
    ns = re.match(r'\{.*\}', root.tag).group(0) 
    simulation = root[0][0]
      
    with open(args.json, 'r') as file:
        cyclus_metadata = json.load(file) 

    for spec in cyclus_metadata["schema"]:
        element_name = "_" + spec.split(":")[1] + "__" + spec.split(":")[2]
        xml_content = cyclus_metadata["schema"][spec]
        entity_type = cyclus_metadata["annotations"][spec]["entity"]
        processed_and_wrapped = process_schema_from_mjson(xml_content, element_name)
        if entity_type == "facility":
            processed_facilities.update(processed_and_wrapped)
            facilities.append(element_name)
            highlighter_items.append(element_name)
        elif entity_type == "region":
            processed_regions.update(processed_and_wrapped)
            regions.append(element_name)
            highlighter_items.append(element_name)
        elif entity_type == "institution":
            processed_institutions.update(processed_and_wrapped)
            institutions.append(element_name)  
            highlighter_items.append(element_name)

    result = process_node(simulation)

    final_result = {"simulation": result["simulation"]}
    input_tmpl_entry = {"InputTmpl": "init_template"}
    final_result['simulation'] = {**input_tmpl_entry, **final_result['simulation']}
    
    final_result_detailed_schemas = integrate_detailed_schemas(final_result, processed_facilities, processed_regions, processed_institutions)
        
    serialized_string = custom_serialize(final_result_detailed_schemas["simulation"])   
        
    cyclus_cmd = 'cyclus'
    etc_dir = os.path.join(args.path, os.pardir, 'etc')
    template_dir = os.path.join(etc_dir, 'Templates', 'cyclus')
    create_templates_for_missing_nodes(final_result_detailed_schemas, template_dir)
    
    init_template_string= """simulation{
        
    % autocompletion can be used to call extra copies of commodity, facility, region, and recipe
    
    control {
        duration = 1234
        startmonth = 1
        startyear = 2020
        explicit_inventory=0
        dt=2629846
        decay="lazy"
    }
    
    archetypes {
        spec {
            name = "archetype name"
        }
    }


    facility {
        name="facility_name"
        config {
                % autocomplete here
                }     
    }
    
    region {
        name="region_name"
        config {
                % autocomplete here
                }
        institution {
                name="inst_name"
                config{
                        % define institution here
                        % autocomplete here
                       }
        }
        % More institutions can be called through autocomplete
    }
    
    recipe {
        
        basis="mass"
        name="natl_u"
        nuclide={comp=0.997 id="u238"}
        nuclide={comp=0.003 id="u235"}
    }
}"""

    facility_template= """facility {
        name="facility_name"
        config {
                % autocomplete here
                }     
    }"""
    
    recipe_template="""recipe {
        % this is an example
        basis="mass"
        name="natl_u"
        nuclide={comp=0.997 id="u238"}
        nuclide={comp=0.003 id="u235"}
    }"""
    
    region_template = """    region {
        name="region_name"
        config {
                % there can be multiple regions
                }
        institution {
                name="inst_name"
                initialfacilitylist {
                    entry={
                        number=1
                        prototype=proto
                                             }
                                     }
                config{
                        % define institution here
                       }
        }
    }"""
    
    institution_template = """institution {
        name="inst_name"
        config{
                % define institution here
                }
        }"""
    
    with open(template_dir+'/init_template.tmpl','w') as f:
        f.write(init_template_string)
    with open(template_dir+'/facility.tmpl','w') as f:
        f.write(facility_template)
    with open(template_dir+'/recipe.tmpl','w') as f:
        f.write(recipe_template)
    with open(template_dir+'/region.tmpl','w') as f:
        f.write(region_template)
    with open(template_dir+'/institution.tmpl','w') as f:
        f.write(institution_template)
        
    here = os.path.dirname(os.path.abspath(__file__))
    shutil.copyfile(os.path.join(here, 'cyclus.py'), os.path.join(args.path, 'cyclus.py'))
    
    generate_cyclus_workbench_files(args.path, etc_dir, cyclus_cmd=cyclus_cmd)

# These following lines create the templates and save them in a folder named "Templates"
save_template_for_all_schemas(processed_facilities, cyclus_metadata["annotations"], final_result_detailed_schemas["simulation"], template_dir)
save_template_for_all_schemas(processed_regions, cyclus_metadata["annotations"], final_result_detailed_schemas["simulation"],template_dir)
save_template_for_all_schemas(processed_institutions, cyclus_metadata["annotations"], final_result_detailed_schemas["simulation"],template_dir)