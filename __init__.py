from .gallery_node import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
import os
import mimetypes
from aiohttp import web

# We try to import server to register routes. 
# It might fail if running in a standalone test environment, which is fine for basic node testing but required for full functionality.
try:
    from server import PromptServer
    from PIL import Image
    from io import BytesIO
    
    routes = PromptServer.instance.routes

    @routes.get("/gravity/gallery/list")
    async def get_gallery_list(request):
        dir_path = request.rel_url.query.get("directory", "")
        if not dir_path:
            return web.json_response({"error": "No directory specified", "files": []})
        
        if not os.path.isdir(dir_path):
             return web.json_response({"error": "Directory not found", "files": []})

        files = []
        valid_extensions = {".png", ".jpg", ".jpeg", ".webp"}
        
        try:
            for f in os.listdir(dir_path):
                if os.path.isfile(os.path.join(dir_path, f)):
                    if os.path.splitext(f)[1].lower() in valid_extensions:
                        files.append(f)
            files.sort()
        except Exception as e:
            return web.json_response({"error": str(e), "files": []})

        return web.json_response({"files": files})

    @routes.get("/gravity/gallery/view")
    async def view_gallery_image(request):
        dir_path = request.rel_url.query.get("directory", "")
        filename = request.rel_url.query.get("filename", "")
        
        if not dir_path or not filename:
             return web.Response(status=400, text="Missing directory or filename")
             
        file_path = os.path.join(dir_path, filename)
        if not os.path.exists(file_path):
            return web.Response(status=404, text="File not found")
            
        # Security check: straightforward implementation for local tool
        return web.FileResponse(file_path)

    @routes.get("/gravity/gallery/thumbnail")
    async def view_gallery_thumbnail(request):
        dir_path = request.rel_url.query.get("directory", "")
        filename = request.rel_url.query.get("filename", "")
        size = int(request.rel_url.query.get("size", "256"))
        
        if not dir_path or not filename:
             return web.Response(status=400, text="Missing directory or filename")
             
        file_path = os.path.join(dir_path, filename)
        if not os.path.exists(file_path):
            return web.Response(status=404, text="File not found")
            
        try:
            img = Image.open(file_path)
            img.thumbnail((size, size))
            
            # Convert to RGB if necessary (e.g. for RGBA PNGs saving as JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=70)
            buffer.seek(0)
            
            return web.Response(body=buffer.read(), content_type="image/jpeg")
        except Exception as e:
             print(f"Error generating thumbnail for {filename}: {e}")
             return web.FileResponse(file_path) # Fallback to full image


except ImportError:
    print("ComfyUI Server not found. API routes for Gallery will not be registered.")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

WEB_DIRECTORY = "./web"
