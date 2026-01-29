import os
import json
from PIL import Image, ExifTags
import folder_paths

class GravityGalleryNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "directory": ("STRING", {"default": ""}),
                "thumbnail_size": ("INT", {"default": 190, "min": 50, "max": 500, "step": 10}),
                "image": ([""],),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_string", "debug_info")
    FUNCTION = "process"
    CATEGORY = "Gravity"
    
    # Bypass validation since the image list is dynamic
    @classmethod
    def VALIDATE_INPUTS(s, directory, thumbnail_size, image):
        return True
        
    def get_node_input(self, node_id, input_key, prompt_json, visited=None):
        if visited is None:
            visited = set()
        
        if node_id in visited:
            return None # Cycle detected
        visited.add(node_id)
        
        if node_id not in prompt_json:
            return None
            
        node = prompt_json[node_id]
        inputs = node.get("inputs", {})
        
        # If the specific input key isn't there, we can't find it
        if input_key not in inputs:
            return None
            
        val = inputs[input_key]
        
        # If it's a raw string/int/float, return it
        if isinstance(val, (str, int, float, bool)):
             return str(val)
             
        # If it's a link: [node_id, slot_index]
        if isinstance(val, list) and len(val) == 2:
            source_node_id = str(val[0])
            
            # Recursive lookup
            if source_node_id in prompt_json:
                source_node = prompt_json[source_node_id]
                source_inputs = source_node.get("inputs", {})
                
                # Common value keys for primitives or string nodes
                for key in ["text", "string", "value", "string_field", "prompt"]:
                    if key in source_inputs:
                        res = self.get_node_input(source_node_id, key, prompt_json, visited)
                        if res: 
                            return res
                            
            return f"<Link to Node {source_node_id}>"
            
        return str(val)

    def process(self, directory, image, thumbnail_size=100):
        if not directory or not image:
            return ("", "No image data")
            
        selected_image = image
        if isinstance(selected_image, (list, tuple)):
            selected_image = selected_image[0]

        image_path = os.path.join(directory, selected_image)

        if not os.path.exists(image_path):
            return (f"Error: File not found {image_path}", f"Path checked: {image_path}")

        debug_log = []
        try:
            with Image.open(image_path) as img:
                info = img.info.copy() # Copy so we can modify it
                
                # WEBP Handling: Extract Metadata from Exif Tags
                # ComfyUI often saves metadata in:
                # 270 (0x010e) ImageDescription -> Full Workflow
                # 271 (0x010f) Make -> Prompt / Generation Nodes
                # 0x0110 Model -> Prompt
                # 0x8298 Copyright -> Workflow
                # 0x9286 UserComment -> Workflow/Prompt
                try:
                    exif = img.getexif()
                    if exif:
                        # Priority list: (Tag ID, Name, Target Key)
                        # We process them in order so later ones can overwrite if needed, or we check if empty.
                        # Actually, better to check all and populate what's missing.
                        target_tags = {
                            270: "ImageDescription", 
                            271: "Make", 
                            0x0110: "Model", 
                            0x8298: "Copyright", 
                            0x9286: "UserComment"
                        }
                        
                        for key, val in exif.items():
                            if key in target_tags:
                                tag_name = target_tags[key]
                                
                                # Decode Bytes
                                val_str = ""
                                if isinstance(val, bytes):
                                    try:
                                        if val.startswith(b'ASCII\0\0\0'):
                                            val_str = val[8:].decode('utf-8')
                                        elif val.startswith(b'UNICODE\0'):
                                            val_str = val[8:].decode('utf-16')
                                        elif val.startswith(b'Exif\0\0'):
                                            val_str = val[6:].decode('utf-8')
                                        else:
                                            val_str = val.decode('utf-8', errors='ignore').replace('\x00', '')
                                    except:
                                        val_str = str(val)
                                else:
                                    val_str = str(val)
                                
                                debug_log.append(f"Exif {tag_name} found. Length: {len(val_str)}")
                                
                                # Remove "Workflow:" or "Prompt:" prefixes
                                if val_str.startswith("Workflow:"):
                                    val_str = val_str[9:].strip()
                                elif val_str.startswith("Prompt:"):
                                    val_str = val_str[7:].strip()
                                
                                # Attempt JSON Parse
                                try:
                                    potential_json = json.loads(val_str)
                                    if isinstance(potential_json, dict):
                                        # Strategy: Populate generic keys if found in JSON
                                        # But also respect the tag's semantic meaning
                                        
                                        # If JSON explicitly has "prompt" or "workflow" keys, use them.
                                        if "prompt" in potential_json:
                                            info["prompt"] = json.dumps(potential_json["prompt"])
                                            debug_log.append(f"  -> Found 'prompt' key inside {tag_name}")
                                        if "workflow" in potential_json:
                                            info["workflow"] = json.dumps(potential_json["workflow"])
                                            debug_log.append(f"  -> Found 'workflow' key inside {tag_name}")
                                        
                                        # If the tag is strictly "Make" or "Model", and the JSON looks like a node map
                                        # (keys are IDs), assume it is the PROMPT
                                        if tag_name in ["Make", "Model"]:
                                            # Verification it looks like a prompt map
                                            is_node_map = True
                                            if len(potential_json) > 0:
                                                 for k, v in potential_json.items():
                                                     if not isinstance(v, dict) or "inputs" not in v:
                                                         is_node_map = False
                                                         break
                                            
                                            if is_node_map:
                                                 if "prompt" not in info: # Don't overwrite if we found explicit "prompt" key earlier
                                                     info["prompt"] = val_str
                                                     debug_log.append(f"  -> Used {tag_name} content as 'prompt'")

                                        # If the tag is "ImageDescription", "Copyright", "UserComment" 
                                        # and contains "nodes" & "links", assume it is the WORKFLOW
                                        if tag_name in ["ImageDescription", "Copyright", "UserComment"]:
                                            if "nodes" in potential_json and "links" in potential_json:
                                                 if "workflow" not in info:
                                                     info["workflow"] = val_str
                                                     debug_log.append(f"  -> Used {tag_name} content as 'workflow'")
                                                     
                                except json.JSONDecodeError:
                                    pass

                except Exception as ex:
                    debug_log.append(f"Error reading Exif: {ex}")

                text_output = ""
                
                # 1. Try Automatic1111 "parameters"
                if "parameters" in info:
                    debug_log.append("Found 'parameters' in metadata (A1111 format).")
                    text_output += f"{info['parameters']}\n"
                    return (text_output, "\n".join(debug_log))

                # 2. Try ComfyUI "prompt"
                if "prompt" in info:
                    debug_log.append("Found 'prompt' in metadata (ComfyUI format). Parsing JSON...")
                    try:
                        prompt_json = json.loads(info["prompt"])
                        found_texts = []
                        
                        # Debug: list all nodes types
                        if isinstance(prompt_json, dict):
                            node_types = [d.get("class_type") for d in prompt_json.values() if isinstance(d, dict)]
                            debug_log.append(f"Nodes found: {node_types}")

                            for node_id, node_data in prompt_json.items():
                                class_type = node_data.get("class_type", "")
                                
                                # We look for nodes that generate text for conditioning
                                if "CLIPTextEncode" in class_type or "Text" in class_type or "String" in class_type:
                                    debug_log.append(f"Inspecting Node {node_id} ({class_type})...")
                                    
                                    # Try to find 'text' input
                                    resolved_text = self.get_node_input(node_id, "text", prompt_json)
                                    if not resolved_text:
                                         # Try 'string' or 'value'
                                         resolved_text = self.get_node_input(node_id, "string", prompt_json)
                                    if not resolved_text:
                                         resolved_text = self.get_node_input(node_id, "value", prompt_json)

                                    if resolved_text and isinstance(resolved_text, str) and resolved_text.strip():
                                         if "<Link" not in resolved_text: # specific validation
                                             if resolved_text not in found_texts: # Simple deduplication
                                                 found_texts.append(resolved_text)
                                                 debug_log.append(f"  -> Extracted: {resolved_text[:50]}...")
                                             else:
                                                 debug_log.append(f"  -> Duplicate skipped: {resolved_text[:20]}...")
                                         else:
                                             debug_log.append(f"  -> Unresolved Link: {resolved_text}")
                                    else:
                                        debug_log.append("  -> No text value found.")
                        
                        if found_texts:
                            text_output += "\n---\n".join(found_texts)
                        else:
                             text_output += f"Raw Prompt Data:\n{info['prompt']}\n"
                             debug_log.append("No valid text found in target nodes. Returning raw dump.")
                             
                    except json.JSONDecodeError:
                        text_output += f"Prompt (Raw):\n{info['prompt']}\n"
                        debug_log.append("JSON Decode Error on prompt metadata.")
                
                if not text_output and "workflow" in info:
                     text_output += "Workflow metadata found but no prompt text extracted."
                     debug_log.append("Only 'workflow' metadata found.")

                if not text_output:
                    debug_log.append("No metadata found.")
                    return ("No standard prompt metadata found.", "\n".join(debug_log))
                
                return (text_output, "\n".join(debug_log))
                
        except Exception as e:
            return (f"Error reading image: {e}", f"Exception: {str(e)}")

NODE_CLASS_MAPPINGS = {
    "GravityGalleryNode": GravityGalleryNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GravityGalleryNode": "Gravity Gallery Prompt Extractor"
}
