import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Inject CSS for the gallery
const style = document.createElement("style");
style.textContent = `
    .gravity-gallery-container {
        position: absolute;
        background: #111;
        border: 1px solid #333;
        overflow-y: auto;
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
        gap: 4px;
        padding: 4px;
        box-sizing: border-box;
        z-index: 1000;
        pointer-events: auto; /* Enable clicks */
    }
    .gravity-gallery-item {
        width: 100%;
        aspect-ratio: 1;
        object-fit: cover;
        cursor: pointer;
        opacity: 0.8;
        transition: opacity 0.2s, border-color 0.2s;
        border: 2px solid transparent;
        border-radius: 4px;
    }
    .gravity-gallery-item:hover {
        opacity: 1.0;
    }
    .gravity-gallery-item.selected {
        border-color: #4CAF50;
        opacity: 1.0;
    }
    /* Scrollbar styling */
    .gravity-gallery-container::-webkit-scrollbar {
        width: 8px;
    }
    .gravity-gallery-container::-webkit-scrollbar-track {
        background: #000;
    }
    .gravity-gallery-container::-webkit-scrollbar-thumb {
        background: #444;
        border-radius: 4px;
    }
`;
document.head.appendChild(style);

app.registerExtension({
    name: "Gravity.Gallery",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "GravityGalleryNode") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                console.log("Gravity Gallery Node created");

                const node = this;
                const dirWidget = node.widgets.find((w) => w.name === "directory");
                const imageWidget = node.widgets.find((w) => w.name === "image");
                const sizeWidget = node.widgets.find((w) => w.name === "thumbnail_size");

                if (!dirWidget || !imageWidget || !sizeWidget) {
                    console.error("Gravity Gallery: Could not find directory, image, or size widgets");
                    return;
                }

                // Increase default size to accommodate gallery
                node.setSize([400, 600]);

                // Create DOM Element
                const galleryDiv = document.createElement("div");
                galleryDiv.className = "gravity-gallery-container";
                document.body.appendChild(galleryDiv);

                // Track state
                let currentFiles = [];
                let selectedFile = imageWidget.value || "";

                // Cleanup on removal
                const onRemoved = node.onRemoved;
                node.onRemoved = function () {
                    if (onRemoved) onRemoved.apply(this, arguments);
                    if (galleryDiv.parentNode) galleryDiv.parentNode.removeChild(galleryDiv);
                };

                // Add Refresh Button
                node.addWidget("button", "Refresh List", null, () => {
                    updateImageList();
                });

                // Update Grid Size
                const updateGridSize = () => {
                    const size = sizeWidget.value || 100;
                    galleryDiv.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
                }

                // Update Gallery Content
                const renderGallery = () => {
                    galleryDiv.innerHTML = "";
                    const dir = dirWidget.value;

                    if (!dir) {
                        galleryDiv.innerText = "No directory selected";
                        galleryDiv.style.color = "#888";
                        galleryDiv.style.display = "flex";
                        galleryDiv.style.alignItems = "center";
                        galleryDiv.style.justifyContent = "center";
                        return;
                    }

                    // Reset display style from flex (error msg) back to grid
                    galleryDiv.style.display = "grid";
                    galleryDiv.style.alignItems = "initial";
                    galleryDiv.style.justifyContent = "initial";
                    updateGridSize(); // Ensure size is applied

                    currentFiles.forEach(f => {
                        const img = document.createElement("img");
                        img.src = `/gravity/gallery/view?directory=${encodeURIComponent(dir)}&filename=${encodeURIComponent(f)}`;
                        img.className = "gravity-gallery-item";
                        if (f === selectedFile) img.classList.add("selected");

                        img.onclick = (e) => {
                            e.stopPropagation(); // Prevent passing click to canvas
                            selectedFile = f;
                            imageWidget.value = f;

                            // Visual update
                            Array.from(galleryDiv.children).forEach(c => c.classList.remove("selected"));
                            img.classList.add("selected");

                            // Trigger callback if needed
                            if (imageWidget.callback) imageWidget.callback(f);
                        };

                        galleryDiv.appendChild(img);
                    });
                };

                const updateImageList = async () => {
                    const dir = dirWidget.value;
                    if (!dir) return;

                    try {
                        const response = await api.fetchApi(`/gravity/gallery/list?directory=${encodeURIComponent(dir)}`);
                        const data = await response.json();

                        if (data.files) {
                            currentFiles = data.files;
                            imageWidget.options.values = data.files;
                            renderGallery();
                        }
                    } catch (e) {
                        console.error("Error fetching gallery list", e);
                        galleryDiv.textContent = "Error loading files";
                    }
                };

                // Sync loop for position
                const onDrawForeground = node.onDrawForeground;
                node.onDrawForeground = function (ctx) {
                    if (onDrawForeground) onDrawForeground.apply(this, arguments);

                    if (!galleryDiv) return;

                    // Hide if node is collapsed or off-screen checks (simplified)
                    if (node.flags.collapsed) {
                        galleryDiv.style.display = "none";
                        return;
                    } else if (galleryDiv.style.display === "none") {
                        galleryDiv.style.display = "grid"; // Restore
                    }

                    // Calculate position
                    // Local node coords: (0, 0) is top-left of node
                    // We want to place the gallery below the inputs.
                    // Let's assume a margin from top.
                    const headerHeight = 30; // approx
                    const inputHeight = 60; // 2 inputs roughly
                    const marginY = 80; // Start below buttons

                    // Calculate Global Coordinates
                    // ctx.getTransform() gives the full transform matrix?
                    // Safer to use app.canvas.ds

                    const ds = app.canvas.ds;
                    const scale = ds.scale;
                    const offset = ds.offset;

                    // Node Position (Canvas Space)
                    const nx = node.pos[0];
                    const ny = node.pos[1];
                    const nw = node.size[0];
                    const nh = node.size[1];

                    // Screen Space
                    const x = (nx + offset[0]) * scale;
                    const y = (ny + offset[1]) * scale;
                    // Width/Height
                    const w = nw * scale;
                    const h = nh * scale;

                    // Gallery specific area
                    // We want it to fill the bottom part of the node
                    const galleryYRel = 180; // Pixel offset inside node for gallery start
                    const galleryY = y + (galleryYRel * scale);
                    const galleryH = h - (galleryYRel * scale) - (10 * scale); // 10px padding bottom
                    const galleryW = w - (20 * scale); // 10px padding sides

                    galleryDiv.style.left = `${x + 10 * scale}px`;
                    galleryDiv.style.top = `${galleryY}px`;
                    galleryDiv.style.width = `${galleryW}px`;
                    galleryDiv.style.height = `${galleryH}px`;

                    // Update grid columns based on zoom (scale)
                    // We want the columns to be "sizeWidget.value" in NODE coordinates.
                    // So in screen coordinates, that is sizeWidget.value * scale.
                    const baseSize = sizeWidget.value || 100;
                    const scaledSize = baseSize * scale;
                    galleryDiv.style.gridTemplateColumns = `repeat(auto-fill, minmax(${scaledSize}px, 1fr))`;

                    // Font size / scaling?
                    // We might not need to scale content via transform, just sizing the div is often enough 
                    // provided scrollbars work. But images might look small if zoomed out.
                    // HTML overlays usually stay 1:1 pixel ratio unless we scale them.
                    // Ideally we apply a transform scale to key it in sync with UI zoom?
                    // Actually, simple sizing is usually better for usability (UI doesn't get microscopic)
                    // BUT for "in-node" feel, it should scale.
                    // Let's try simple transform-origin top-left scaling.

                    // Approach: Set internal width/height to unscaled, then transform?
                    // Or just let natural DOM layout handle it.
                    // If we just set px width/height, the scrollbar stays constant px size (good).
                    // But images will be constant px size (bad if drilled in).
                    // Let's rely on standard browser checks.

                    // Actually, if we zoom out, the 'w' gets smaller. Grid items reflow.
                    // That's actually often Desirable for a gallery (responsive).
                };

                // Listeners

                // Hijack callback of directory to update list
                const originalDirCallback = dirWidget.callback;
                dirWidget.callback = function () {
                    if (originalDirCallback) originalDirCallback.apply(this, arguments);
                    updateImageList();
                };

                // Hijack callback of size widget to trigger redraw
                const originalSizeCallback = sizeWidget.callback;
                sizeWidget.callback = function () {
                    if (originalSizeCallback) originalSizeCallback.apply(this, arguments);
                    // Force a redraw so scale is re-applied
                    app.graph.setDirtyCanvas(true);
                };

                // Initial update
                setTimeout(() => {
                    if (dirWidget.value) {
                        updateImageList();
                    }
                }, 100);
            };
        }
    }
});
