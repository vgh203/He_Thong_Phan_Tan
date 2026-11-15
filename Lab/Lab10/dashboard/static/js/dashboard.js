/**
 * dashboard.js
 * Frontend controller for Secure Group Multicast & ABAC Policy Simulator.
 */

let currentState = null;

document.addEventListener("DOMContentLoaded", () => {
    fetchState();
    setInterval(fetchState, 3000);
});

async function fetchState() {
    try {
        const res = await fetch("/api/state");
        const data = await res.json();
        if (data.status === "OK") {
            currentState = data;
            updateUI(data);
        }
    } catch (err) {
        console.error("Error fetching state:", err);
    }
}

function updateUI(data) {
    // 1. Update Root Key in header
    document.getElementById("nav-root-key").innerText = data.tree.root_key_short || "None";

    // 2. Render SVG Tree
    renderTree(data.tree, data.members);

    // 3. Render Terminal Screen
    const terminal = document.getElementById("terminal-screen");
    terminal.innerText = data.logs.join("\n");
    terminal.scrollTop = terminal.scrollHeight;

    // 4. Update Decryption Matrix if packet exists
    if (data.latest_packet) {
        document.getElementById("meta-nonce").innerText = data.latest_packet.nonce;
        document.getElementById("meta-ct").innerText = data.latest_packet.ciphertext.substring(0, 32) + "...";
    }
}

function renderTree(treeData, members) {
    const svg = document.getElementById("tree-svg");
    svg.innerHTML = ""; // Clear existing

    const width = svg.clientWidth || 900;
    const height = 340;

    // Coordinates for the 15 nodes
    // Level 0: 1 node (y = 35)
    // Level 1: 2 nodes (y = 115)
    // Level 2: 4 nodes (y = 195)
    // Level 3: 8 nodes (y = 280)
    const nodeCoords = {};

    // Helper to calculate x
    const levels = [
        [1],
        [2, 3],
        [4, 5, 6, 7],
        [8, 9, 10, 11, 12, 13, 14, 15]
    ];

    const yOffsets = [35, 115, 195, 280];

    levels.forEach((lvlNodes, lvlIndex) => {
        const count = lvlNodes.length;
        const segment = width / (count + 1);
        lvlNodes.forEach((nid, i) => {
            nodeCoords[nid] = {
                x: segment * (i + 1),
                y: yOffsets[lvlIndex]
            };
        });
    });

    // 1. Draw connecting lines (edges)
    for (let nid = 1; nid <= 7; nid++) {
        const parentCoord = nodeCoords[nid];
        const leftCoord = nodeCoords[2 * nid];
        const rightCoord = nodeCoords[2 * nid + 1];

        if (parentCoord && leftCoord) {
            svg.appendChild(createSvgLine(parentCoord.x, parentCoord.y + 15, leftCoord.x, leftCoord.y - 15));
        }
        if (parentCoord && rightCoord) {
            svg.appendChild(createSvgLine(parentCoord.x, parentCoord.y + 15, rightCoord.x, rightCoord.y - 15));
        }
    }

    // 2. Draw Nodes
    for (let nid = 1; nid <= 15; nid++) {
        const coord = nodeCoords[nid];
        const nodeInfo = treeData.nodes[nid];
        if (!coord || !nodeInfo) continue;

        let nodeClass = "node-kek";
        let title = `Node ${nid}`;
        let subtitle = nodeInfo.key_short;

        if (nid === 1) {
            nodeClass = "node-root";
            title = "Root K₀";
        } else if (nid >= 8) {
            // Leaf node for Client
            const member = members.find(m => m.leaf_id === nid);
            title = member ? member.client_id : `Leaf ${nid}`;
            if (member && member.is_active) {
                nodeClass = "node-active";
                subtitle = `${member.role} [${member.key_short}]`;
            } else if (member && !member.is_active) {
                nodeClass = "node-revoked";
                subtitle = "Revoked / Offline";
            }
        }

        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.setAttribute("class", `tree-node`);
        g.onclick = () => highlightPath(nid, members);

        const rectW = nid >= 8 ? 96 : 80;
        const rectH = 34;

        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", coord.x - rectW / 2);
        rect.setAttribute("y", coord.y - rectH / 2);
        rect.setAttribute("width", rectW);
        rect.setAttribute("height", rectH);
        rect.setAttribute("class", `node-box ${nodeClass}`);

        const textTitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
        textTitle.setAttribute("x", coord.x);
        textTitle.setAttribute("y", coord.y - 2);
        textTitle.setAttribute("class", "node-text-title");
        textTitle.textContent = title;

        const textSub = document.createElementNS("http://www.w3.org/2000/svg", "text");
        textSub.setAttribute("x", coord.x);
        textSub.setAttribute("y", coord.y + 11);
        textSub.setAttribute("class", "node-text-sub");
        textSub.textContent = subtitle;

        g.appendChild(rect);
        g.appendChild(textTitle);
        g.appendChild(textSub);
        svg.appendChild(g);
    }
}

function createSvgLine(x1, y1, x2, y2) {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    line.setAttribute("class", "tree-edge");
    return line;
}

function highlightPath(nodeId, members) {
    console.log(`Clicked node ${nodeId}`);
}

async function joinClient(clientId) {
    try {
        const res = await fetch("/api/join", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_id: clientId })
        });
        const data = await res.json();
        fetchState();
    } catch (err) {
        console.error("Join error:", err);
    }
}

async function leaveClient(clientId) {
    try {
        const res = await fetch("/api/leave", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_id: clientId })
        });
        const data = await res.json();
        fetchState();
    } catch (err) {
        console.error("Leave error:", err);
    }
}

function setTime(timeVal) {
    document.getElementById("pub-time").value = timeVal;
}

function autoFillRole() {
    const cid = document.getElementById("pub-client").value;
    const roleSelect = document.getElementById("pub-role");
    if (cid === "CLIENT_1") {
        roleSelect.value = "Publisher";
    } else {
        roleSelect.value = "Subscriber";
    }
}

async function dispatchMulticast(event) {
    event.preventDefault();
    const clientId = document.getElementById("pub-client").value;
    const role = document.getElementById("pub-role").value;
    const timeVal = document.getElementById("pub-time").value;
    const payload = document.getElementById("pub-payload").value;

    try {
        const res = await fetch("/api/publish", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                client_id: clientId,
                role: role,
                time: timeVal,
                payload: payload
            })
        });
        const data = await res.json();
        const banner = document.getElementById("abac-result-banner");
        banner.classList.remove("hidden", "passed", "denied");

        if (data.status === "OK") {
            banner.classList.add("passed");
            banner.innerHTML = `<strong>✅ ABAC PASSED:</strong> ${data.decision.reason}<br><small>Payload encrypted with current Root Key K₀ and broadcasted.</small>`;
            renderDecryptionMatrix(data.decryption_results);
        } else {
            banner.classList.add("denied");
            banner.innerHTML = `<strong>❌ ABAC DENIED:</strong> ${data.decision.reason}`;
        }

        fetchState();
    } catch (err) {
        console.error("Dispatch error:", err);
    }
}

function renderDecryptionMatrix(results) {
    if (!results) return;
    const matrix = document.getElementById("matrix-grid");
    matrix.innerHTML = "";

    Object.keys(results).forEach(cid => {
        const res = results[cid];
        const card = document.createElement("div");
        const isSuccess = res.status === "SUCCESS";
        card.className = `member-card ${isSuccess ? 'status-success' : 'status-fail'}`;

        card.innerHTML = `
            <div class="member-header">
                <span>${cid}</span>
                <span>${isSuccess ? '✅ OK' : '❌ FAIL'}</span>
            </div>
            <div class="member-result">
                ${isSuccess ? `Decrypted: "${res.text.substring(0, 18)}..."` : `${res.reason}`}
            </div>
        `;
        matrix.appendChild(card);
    });
}

async function runVerification() {
    try {
        const res = await fetch("/api/verify", { method: "POST" });
        const data = await res.json();
        const container = document.getElementById("verification-list");
        container.innerHTML = "";

        data.results.forEach(item => {
            const div = document.createElement("div");
            div.className = `check-item ${item.passed ? 'passed' : 'failed'}`;
            div.innerHTML = `
                <span class="check-icon">${item.passed ? '✅' : '❌'}</span>
                <div class="check-text">
                    <strong>${item.name}</strong>
                    <span>${item.details}</span>
                </div>
            `;
            container.appendChild(div);
        });
    } catch (err) {
        console.error("Verification error:", err);
    }
}

async function resetSimulation() {
    try {
        await fetch("/api/reset", { method: "POST" });
        fetchState();
        document.getElementById("abac-result-banner").classList.add("hidden");
        document.getElementById("matrix-grid").innerHTML = "";
    } catch (err) {
        console.error("Reset error:", err);
    }
}

