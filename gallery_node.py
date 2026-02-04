import os
import json
import random
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
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "randomize_output": ("BOOLEAN", {"default": False}),
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

    def extract_positive_prompt(self, parameters_text):
        """
        Extract only the positive prompt from A1111/Civitai parameters text.
        Stops extraction when hitting any metadata phrase.
        """
        # Define the phrases that mark the end of the positive prompt
        stop_phrases = [
            "Negative prompt:",
            "Steps:",
            "Sampler:",
            "CFG scale:",
            "Seed:",
            "Size:",
            "Clip skip:",
            "Created Date:",
            "Civitai resources:",
            "Civitai metadata:"
        ]
        
        # Find the earliest occurrence of any stop phrase
        earliest_index = len(parameters_text)
        for phrase in stop_phrases:
            index = parameters_text.find(phrase)
            if index != -1 and index < earliest_index:
                earliest_index = index
        
        # Extract everything before the first stop phrase
        prompt = parameters_text[:earliest_index].strip()
        return prompt

    def process(self, directory, image, thumbnail_size=100, seed=0, randomize_output=False):
        return self._process_logic(directory, image, seed, randomize_output)

    def _process_logic(self, directory, image, seed, randomize_output):
        if not directory:
            return ("", "No directory provided")
            
        selected_image = image
        if isinstance(selected_image, (list, tuple)):
            if len(selected_image) > 0:
                selected_image = selected_image[0]
            else:
                selected_image = ""

        if randomize_output:
            if os.path.isdir(directory):
                files = [f for f in os.listdir(directory) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))]
                if files:
                    files.sort()
                    r = random.Random(seed)
                    selected_image = r.choice(files)
                else:
                    return ("", f"No images found in {directory}")
            else:
                return ("", f"Directory not found: {directory}")

        if not selected_image:
            return ("", "No image selected")

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
                        # Get EXIF IFD (sub-directory) which contains UserComment
                        exif_ifd = exif.get_ifd(0x8769)  # 0x8769 is the EXIF IFD pointer
                        
                        # Priority list: (Tag ID, Name, Target Key)
                        # Main IFD tags
                        target_tags = {
                            270: "ImageDescription", 
                            271: "Make", 
                            0x0110: "Model", 
                            0x8298: "Copyright"
                        }
                        
                        # EXIF IFD tags (including UserComment)
                        exif_ifd_tags = {
                            0x9286: "UserComment"
                        }
                        
                        debug_log.append(f"Main EXIF tags found: {list(exif.keys())}")
                        if exif_ifd:
                            debug_log.append(f"EXIF IFD tags found: {list(exif_ifd.keys())}")
                        
                        # Process both main EXIF and EXIF IFD tags
                        all_tags = [(key, val, target_tags[key]) for key, val in exif.items() if key in target_tags]
                        if exif_ifd:
                            all_tags.extend([(key, val, exif_ifd_tags[key]) for key, val in exif_ifd.items() if key in exif_ifd_tags])
                        
                        for key, val, tag_name in all_tags:
                            # Decode Bytes
                            val_str = ""
                            if isinstance(val, bytes):
                                try:
                                    # Handle EXIF UserComment encoding prefixes
                                    if tag_name == "UserComment":
                                        # Try UTF-16LE first (common for Civitai UserComment), then UTF-8
                                        try:
                                            # Check if it looks like UTF-16LE (every other byte is \x00 for ASCII chars)
                                            if len(val) > 10 and val[1:20:2].count(b'\x00'[0]) > 5:
                                                val_str = val.decode('utf-16le', errors='ignore').replace('\x00', '')
                                            else:
                                                val_str = val.decode('utf-8', errors='ignore').replace('\x00', '')
                                        except:
                                            val_str = val.decode('utf-8', errors='ignore').replace('\x00', '')
                                    
                                    elif val.startswith(b'ASCII\0\0\0'):
                                        val_str = val[8:].decode('utf-8')
                                    elif val.startswith(b'UNICODE\0'):
                                        val_str = val[8:].decode('utf-16')
                                    elif val.startswith(b'Exif\0\0'):
                                        val_str = val[6:].decode('utf-8')
                                    
                                except:
                                    val_str = str(val)
                            else:
                                val_str = str(val)
                            
                            debug_log.append(f"Exif {tag_name} found. Length: {len(val_str)}")
                            
                            # Special handling for UserComment - extract only the positive prompt
                            if tag_name == "UserComment":
                                # Remove EXIF encoding marker prefixes if present
                                for prefix in ['UNICODE', 'ASCII', 'JIS', 'UNDEFINED']:
                                    if val_str.startswith(prefix):
                                        val_str = val_str[len(prefix):].lstrip()
                                        debug_log.append(f"  -> Stripped '{prefix}' prefix from UserComment")
                                        break
                                
                                debug_log.append(f"  -> UserComment raw content: {val_str[:100]}...")
                                
                                # Try to parse as JSON (for newer Civitai format with extraMetadata)
                                extracted_prompt = None
                                try:
                                    usercomment_json = json.loads(val_str)
                                    if isinstance(usercomment_json, dict):
                                        # Check for extraMetadata field (newer Civitai format)
                                        if "extraMetadata" in usercomment_json:
                                            extra_meta_str = usercomment_json["extraMetadata"]
                                            # Parse the nested JSON string
                                            extra_meta = json.loads(extra_meta_str)
                                            if "prompt" in extra_meta:
                                                extracted_prompt = extra_meta["prompt"]
                                                debug_log.append(f"  -> Extracted prompt from extraMetadata.prompt")
                                except (json.JSONDecodeError, TypeError):
                                    # Not JSON, treat as plain text
                                    pass
                                
                                # If we didn't find JSON prompt, extract from plain text
                                if not extracted_prompt:
                                    extracted_prompt = self.extract_positive_prompt(val_str)
                                
                                if extracted_prompt:
                                    info["usercomment_prompt"] = extracted_prompt
                                    debug_log.append(f"  -> Extracted prompt from UserComment: {len(extracted_prompt)} chars")
                                continue
                            
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

                                    # If the tag is "ImageDescription", "Copyright"
                                    # and contains "nodes" & "links", assume it is the WORKFLOW
                                    if tag_name in ["ImageDescription", "Copyright"]:
                                        if "nodes" in potential_json and "links" in potential_json:
                                             if "workflow" not in info:
                                                 info["workflow"] = val_str
                                                 debug_log.append(f"  -> Used {tag_name} content as 'workflow'")
                                                 
                            except json.JSONDecodeError:
                                pass

                except Exception as ex:
                    debug_log.append(f"Error reading Exif: {ex}")

                text_output = ""
                
                # 0. Try UserComment first (Civitai images)
                if "usercomment_prompt" in info:
                    debug_log.append("Found extracted prompt from UserComment (Civitai format).")
                    text_output += f"{info['usercomment_prompt']}\n"
                    return (text_output, "\n".join(debug_log))
                
                # 1. Try Automatic1111 "parameters"
                if "parameters" in info:
                    debug_log.append("Found 'parameters' in metadata (A1111 format).")
                    # Extract only the positive prompt by stopping at metadata phrases
                    extracted_prompt = self.extract_positive_prompt(info['parameters'])
                    text_output += f"{extracted_prompt}\n"
                    debug_log.append(f"Extracted prompt length: {len(extracted_prompt)} chars")
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


class GravityGalleryConfig:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "directory": ("STRING", {"default": ""}),
                "thumbnail_size": ("INT", {"default": 190, "min": 50, "max": 500, "step": 10}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "randomize_output": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("GALLERY_CONFIG",)
    RETURN_NAMES = ("gallery_config",)
    FUNCTION = "get_config"
    CATEGORY = "Gravity"

    def get_config(self, directory, thumbnail_size, seed, randomize_output):
        return ({"directory": directory, "thumbnail_size": thumbnail_size, "seed": seed, "randomize_output": randomize_output},)

class GravityGalleryMini(GravityGalleryNode):
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gallery_config": ("GALLERY_CONFIG",),
                "image": ([""],),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_string", "debug_info")
    FUNCTION = "process_small"
    CATEGORY = "Gravity"

    @classmethod
    def VALIDATE_INPUTS(s, gallery_config, image):
        return True

    def process_small(self, gallery_config, image):
        directory = gallery_config.get("directory", "")
        seed = gallery_config.get("seed", 0)
        randomize_output = gallery_config.get("randomize_output", False)
        
        return self._process_logic(directory, image, seed, randomize_output)

NODE_CLASS_MAPPINGS = {
    "GravityGalleryNode": GravityGalleryNode,
    "GravityGalleryConfig": GravityGalleryConfig,
    "GravityGalleryMini": GravityGalleryMini
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GravityGalleryNode": "Gravity Gallery Prompt Extractor",
    "GravityGalleryConfig": "Gravity Gallery Config",
    "GravityGalleryMini": "Gravity Gallery Mini"
}
