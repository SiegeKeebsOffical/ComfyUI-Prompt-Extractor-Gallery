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
        max-width: 90vw;
        max-height: 90vh;
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
    .gravity-gallery-item-wrapper {
        position: relative;
        width: 100%;
        aspect-ratio: 1;
    }
    .gravity-gallery-item-rating {
        position: absolute;
        bottom: 4px;
        left: 4px;
        background: rgba(0,0,0,0.7);
        color: #ffca28;
        font-size: 10px;
        padding: 0 4px;
        border-radius: 2px;
        pointer-events: none;
    }
    .gravity-gallery-controls {
        position: sticky;
        top: 0;
        background: #111;
        padding: 4px;
        margin-bottom: 4px;
        border-bottom: 1px solid #333;
        display: flex;
        gap: 4px;
        z-index: 10;
        align-items: center;
    }
    .gravity-gallery-controls select {
        background: #222;
        color: white;
        border: 1px solid #444;
        font-size: 10px;
        padding: 2px;
    }
    .gravity-gallery-controls button {
        background: #333;
        color: white;
        border: 1px solid #444;
        font-size: 10px;
        padding: 2px 6px;
        cursor: pointer;
        transition: background 0.2s, border-color 0.2s;
    }
    .gravity-gallery-controls button:hover {
        background: #444;
        border-color: #555;
    }
    .gravity-gallery-controls .sort-direction-btn {
        font-size: 14px;
        padding: 0px 6px;
        min-width: 24px;
    }
    .gravity-gallery-controls .sort-direction-btn:active {
        background: #555;
    }
`;
document.head.appendChild(style);

app.registerExtension({
    name: "Gravity.Gallery",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "GravityGalleryNode" || nodeData.name === "GravityGalleryMini") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                console.log(`Gravity Gallery Node (${nodeData.name}) created`);

                const node = this;
                const isMini = nodeData.name === "GravityGalleryMini";

                const getWidget = (name) => node.widgets?.find((w) => w.name === name);

                // Helper to find connected config node
                const getConfigNode = () => {
                    const input = node.inputs?.find(i => i.name === "gallery_config");
                    if (!input || input.link == null) return null;
                    const link = app.graph.links[input.link];
                    if (!link) return null;
                    return app.graph.getNodeById(link.origin_id);
                };

                // Helper to get value from either local widget or connected config
                const getConfigValue = (name) => {
                    if (isMini) {
                        const configNode = getConfigNode();
                        if (configNode) {
                            const w = configNode.widgets?.find(w => w.name === name);
                            return w ? w.value : null;
                        }
                        return null;
                    }
                    const w = getWidget(name);
                    return w ? w.value : null;
                };

                const imageWidget = getWidget("image");
                if (!imageWidget) {
                    console.error("Gravity Gallery: Could not find image widget");
                    return;
                }

                // Increase default size to accommodate gallery
                if (!isMini) {
                    node.setSize([400, 600]);
                } else {
                    node.setSize([300, 400]);
                }

                // Create DOM Element
                const galleryDiv = document.createElement("div");
                galleryDiv.className = "gravity-gallery-container";
                document.body.appendChild(galleryDiv);

                // Track state
                let currentFiles = []; // Array of {filename, rating, mtime}
                let selectedFile = imageWidget.value || "";
                let currentSort = "mtime";
                let sortAscending = false; // false = descending (newest/highest first)
                let isAlive = true;

                // Cleanup on removal
                const originalOnRemoved = node.onRemoved;
                node.onRemoved = function () {
                    isAlive = false;
                    if (originalOnRemoved) originalOnRemoved.apply(this, arguments);
                    if (galleryDiv.parentNode) galleryDiv.parentNode.removeChild(galleryDiv);
                };

                // Add Refresh Button
                node.addWidget("button", "Refresh List", null, () => {
                    updateImageList();
                });

                // Update Grid Size
                const updateGridSize = () => {
                    const size = getConfigValue("thumbnail_size") || 100;
                    galleryDiv.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
                }

                // Update Gallery Content
                const renderGallery = () => {
                    galleryDiv.innerHTML = "";
                    const dir = getConfigValue("directory");

                    if (!dir) {
                        galleryDiv.innerText = isMini ? "Connect Config Node" : "No directory selected";
                        galleryDiv.style.color = "#888";
                        galleryDiv.style.display = "flex";
                        galleryDiv.style.alignItems = "center";
                        galleryDiv.style.justifyContent = "center";
                        galleryDiv.dataset.error = "true";
                        return;
                    }

                    // Reset display style from flex (error msg) back to grid
                    galleryDiv.style.display = "grid";
                    galleryDiv.dataset.error = "false";
                    galleryDiv.style.alignItems = "initial";
                    galleryDiv.style.justifyContent = "initial";
                    updateGridSize(); // Ensure size is applied

                    // Add Controls
                    const controls = document.createElement("div");
                    controls.className = "gravity-gallery-controls";
                    controls.innerHTML = `
                        <select class="sort-select">
                            <option value="mtime">Date</option>
                            <option value="rating">Rating</option>
                            <option value="filename">Name</option>
                        </select>
                        <button class="sort-direction-btn" title="Toggle sort direction">${sortAscending ? '↑' : '↓'}</button>
                    `;
                    const select = controls.querySelector(".sort-select");
                    select.value = currentSort;
                    select.onchange = (e) => {
                        currentSort = e.target.value;
                        sortAndRender();
                    };

                    const directionBtn = controls.querySelector(".sort-direction-btn");
                    directionBtn.onclick = () => {
                        sortAscending = !sortAscending;
                        directionBtn.textContent = sortAscending ? '↑' : '↓';
                        directionBtn.title = sortAscending ? 'Ascending' : 'Descending';
                        sortAndRender();
                    };

                    galleryDiv.appendChild(controls);

                    currentFiles.forEach(fileData => {
                        const f = fileData.filename;
                        const rating = fileData.rating || 0;

                        const wrapper = document.createElement("div");
                        wrapper.className = "gravity-gallery-item-wrapper";

                        const img = document.createElement("img");
                        img.src = `/gravity/gallery/view?directory=${encodeURIComponent(dir)}&filename=${encodeURIComponent(f)}`;
                        img.className = "gravity-gallery-item";
                        if (f === selectedFile) img.classList.add("selected");

                        img.onclick = (e) => {
                            e.stopPropagation(); // Prevent passing click to canvas
                            selectedFile = f;
                            imageWidget.value = f;

                            // Visual update
                            Array.from(galleryDiv.querySelectorAll(".gravity-gallery-item")).forEach(c => c.classList.remove("selected"));
                            img.classList.add("selected");

                            // Trigger callback if needed
                            if (imageWidget.callback) imageWidget.callback(f);
                        };

                        wrapper.appendChild(img);

                        if (rating > 0) {
                            const ratingTag = document.createElement("div");
                            ratingTag.className = "gravity-gallery-item-rating";
                            ratingTag.innerText = "★ " + rating.toFixed(1);
                            wrapper.appendChild(ratingTag);
                        }

                        galleryDiv.appendChild(wrapper);
                    });
                };

                const sortAndRender = () => {
                    if (currentSort === "mtime") {
                        currentFiles.sort((a, b) => sortAscending ? a.mtime - b.mtime : b.mtime - a.mtime);
                    } else if (currentSort === "rating") {
                        currentFiles.sort((a, b) => {
                            const ratingDiff = sortAscending ? a.rating - b.rating : b.rating - a.rating;
                            return ratingDiff !== 0 ? ratingDiff : b.mtime - a.mtime; // Secondary sort by newest
                        });
                    } else if (currentSort === "filename") {
                        currentFiles.sort((a, b) => {
                            const cmp = a.filename.localeCompare(b.filename);
                            return sortAscending ? cmp : -cmp;
                        });
                    }
                    renderGallery();
                };

                const updateImageList = async () => {
                    const dir = getConfigValue("directory");
                    if (!dir) return;

                    try {
                        const response = await api.fetchApi(`/gravity/gallery/list?directory=${encodeURIComponent(dir)}`);
                        const data = await response.json();

                        if (data.files) {
                            currentFiles = data.files;
                            imageWidget.options.values = data.files.map(f => typeof f === 'string' ? f : f.filename);
                            sortAndRender();
                        }
                    } catch (e) {
                        console.error("Error fetching gallery list", e);
                        galleryDiv.textContent = "Error loading files";
                    }
                };

                const syncGallery = () => {
                    if (!isAlive || !galleryDiv) return;

                    // Visibility checks
                    const isTabVisible = document.visibilityState === "visible";
                    const isCorrectGraph = (node.graph === app.graph);
                    const isCollapsed = !!node.flags.collapsed;
                    const isHidden = !!node.flags.hidden;

                    // Basic bounding box check - is the node at least partially on screen?
                    const ds = app.canvas.ds;
                    const scale = ds.scale;
                    const offset = ds.offset;

                    const nx = node.pos[0];
                    const ny = node.pos[1];
                    const nw = node.size[0];
                    const nh = node.size[1];

                    // Screen coordinates of node
                    const screenX = (nx + offset[0]) * scale;
                    const screenY = (ny + offset[1]) * scale;
                    const screenW = nw * scale;
                    const screenH = nh * scale;

                    const isOffScreen =
                        screenX + screenW < 0 ||
                        screenY + screenH < 0 ||
                        screenX > window.innerWidth ||
                        screenY > window.innerHeight;

                    if (!isTabVisible || !isCorrectGraph || isCollapsed || isHidden || isOffScreen || scale < 0.1) {
                        if (galleryDiv.style.display !== "none") {
                            galleryDiv.style.display = "none";
                        }
                        requestAnimationFrame(syncGallery);
                        return;
                    }

                    // Restore display based on state (error or grid)
                    const targetDisplay = (galleryDiv.dataset.error === "true") ? "flex" : "grid";
                    if (galleryDiv.style.display !== targetDisplay) {
                        galleryDiv.style.display = targetDisplay;
                    }

                    // Gallery specific area - Pixel offset inside node for gallery start
                    // Mini node has fewer widgets, so move gallery up
                    const galleryYRel = isMini ? 120 : 240;

                    // Sanity check dimensions - prevent absurdly large values
                    const galleryY = screenY + (galleryYRel * scale);
                    const galleryH = Math.max(0, screenH - (galleryYRel * scale) - (10 * scale));
                    const galleryW = Math.max(0, screenW - (20 * scale));

                    // Final safety clamp for overlay
                    if (galleryW < 10 || galleryH < 10) {
                        galleryDiv.style.display = "none";
                        requestAnimationFrame(syncGallery);
                        return;
                    }

                    galleryDiv.style.left = `${screenX + 10 * scale}px`;
                    galleryDiv.style.top = `${galleryY}px`;
                    galleryDiv.style.width = `${galleryW}px`;
                    galleryDiv.style.height = `${galleryH}px`;

                    // Update grid columns based on zoom (scale)
                    const baseSize = getConfigValue("thumbnail_size") || 100;
                    const scaledSize = baseSize * scale;
                    galleryDiv.style.gridTemplateColumns = `repeat(auto-fill, minmax(${Math.max(20, scaledSize)}px, 1fr))`;

                    requestAnimationFrame(syncGallery);
                };

                // Start the loop
                syncGallery();

                // Listeners

                if (!isMini) {
                    // Hijack callback of directory to update list
                    const dirWidget = getWidget("directory");
                    const originalDirCallback = dirWidget.callback;
                    dirWidget.callback = function () {
                        if (originalDirCallback) originalDirCallback.apply(this, arguments);
                        updateImageList();
                    };

                    // Hijack callback of size widget to trigger redraw
                    const sizeWidget = getWidget("thumbnail_size");
                    const originalSizeCallback = sizeWidget.callback;
                    sizeWidget.callback = function () {
                        if (originalSizeCallback) originalSizeCallback.apply(this, arguments);
                        app.graph.setDirtyCanvas(true);
                    };
                }

                // Initial update
                setTimeout(() => {
                    const dir = getConfigValue("directory");
                    if (dir) {
                        updateImageList();
                    }
                }, 100);
            };
        }
    }
});
