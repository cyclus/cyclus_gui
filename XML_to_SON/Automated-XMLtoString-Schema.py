# Import the required modules 
import xmltodict 
import pprint 
import json

# Open the file and read the contents 
with open('schema.xml', 'r', encoding='utf-8') as file: 
	schema = file.read() 

# Use xmltodict to parse and convert the XML document 
dictionary = xmltodict.parse(schema) 
json_d = json.dumps(dictionary)

def remove_at_symbol_from_keys(data):
	if isinstance(data, dict):
		updated_data = {}
		for key, value in data.items():
			new_key = key[1:] if key.startswith('@') else key
			updated_value = remove_at_symbol_from_keys(value)
			updated_data[new_key] = updated_value
		return updated_data
	elif isinstance(data, list):
		updated_list = []
		for item in data:
			updated_item = remove_at_symbol_from_keys(item)
			updated_list.append(updated_item)
		return updated_list
	else:
		return data

def reformat_tree(d, indent = 0):
	d = remove_at_symbol_from_keys(d)
	if isinstance(d, dict):
		for key, value in d.items():
			match key:
				case "@name":
					key = "name"
				case "@data":
					key = "data"
				case "@type":
					key = "type"
				case _:
					key = key
			if isinstance(value, (dict, list)):
				print(' ' * indent + str(key) + ':')
				reformat_tree(value, indent + 4)
			else:
				print(' ' * indent + str(key) + ': ' + str(value))
	elif isinstance(d, list):
		for item in d:
			if isinstance(item, (dict, list)):
				reformat_tree(item, indent + 4)
			else:
				print(' ' * indent + '- ' + str(item))
	
reformat_tree(dictionary)
