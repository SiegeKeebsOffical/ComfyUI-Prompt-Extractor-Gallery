import os
from PIL import Image, PngImagePlugin
from gallery_node import GravityGalleryNode
import shutil

def test_gallery_node():
    # Setup
    test_dir = "test_gallery"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    # Create a dummy image with complex metadata (linked nodes)
    img = Image.new('RGB', (100, 100), color = 'blue')
    meta = PngImagePlugin.PngInfo()
    
    # Simulate a CLIPTextEncode (id: 10) linked to a Primitive (id: 11)
    prompt_data = {
        "10": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": ["11", 0] # Link to node 11, slot 0
            }
        },
        "11": {
            "class_type": "PrimitiveNode",
            "inputs": {
                "value": "This is a prompt from a linked node"
            }
        }
    }
    
    meta.add_text("prompt", json.dumps(prompt_data))
    
    img_name = "test_linked.png"
    img_path = os.path.join(test_dir, img_name)
    img.save(img_path, "PNG", pnginfo=meta)
    
    # Test Node Logic
    node = GravityGalleryNode()
    
    print("Testing GravityGalleryNode with Linked Inputs...")
    result = node.process(test_dir, [img_name]) 
    
    text_out = result[0]
    debug_out = result[1]
    
    print(f"Output:\n{text_out}")
    print(f"Debug Log:\n{debug_out}")
    
    assert "This is a prompt from a linked node" in text_out
    assert "Inspecting Node 10" in debug_out
    
    print("Test Passed: Linked metadata extracted successfully.")
    
    # Cleanup
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_gallery_node()
