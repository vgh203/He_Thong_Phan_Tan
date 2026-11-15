import threading
import time
import logging
from flask import Flask, jsonify, request, send_from_directory
from chord.node import ChordNode

logging.basicConfig(level=logging.WARNING)

app = Flask(__name__, static_folder="frontend", static_url_path="")

_lock  = threading.Lock()
_nodes = {}
_log   = []
_port_counter = 5000


def _next_port():
    global _port_counter
    _port_counter += 1
    return _port_counter


def _add_log(event, detail=""):
    with _lock:
        _log.append({"time": time.strftime("%H:%M:%S"), "event": event, "detail": detail})
        if len(_log) > 100:
            _log.pop(0)


@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/nodes", methods=["GET"])
def list_nodes():
    result = []
    with _lock:
        items = list(_nodes.items())
    for name, node in items:
        result.append({
            "name":        node.name,
            "id":          node.id,
            "ip":          node.ip,
            "port":        node.port,
            "successor":   node.successor.to_dict() if node.successor else None,
            "predecessor": node.predecessor.to_dict() if node.predecessor else None,
        })
    return jsonify(result)


@app.route("/api/nodes", methods=["POST"])
def create_node():
    data      = request.json or {}
    name      = data.get("name", "").strip()
    port      = int(data.get("port", 0)) or _next_port()
    join_port = data.get("join_port")

    if not name:
        return jsonify({"error": "Ten node khong duoc de trong"}), 400
    with _lock:
        if name in _nodes:
            return jsonify({"error": f"Node {name} da ton tai"}), 400
    try:
        node = ChordNode("127.0.0.1", port, name)
        if join_port:
            node.start(bootstrap_ip="127.0.0.1", bootstrap_port=int(join_port))
        else:
            node.start()
        with _lock:
            _nodes[name] = node
        _add_log("Tao node", f"{name} id={node.id} port={port}")
        return jsonify({"name": name, "id": node.id, "port": port}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/nodes/<name>", methods=["DELETE"])
def delete_node(name):
    with _lock:
        node = _nodes.pop(name, None)
    if not node:
        return jsonify({"error": "Khong tim thay node"}), 404
    node.stop()
    _add_log("Dung node", name)
    return jsonify({"status": "ok"})


@app.route("/api/nodes/<name>/info", methods=["GET"])
def node_info(name):
    with _lock:
        node = _nodes.get(name)
    if not node:
        return jsonify({"error": "Khong tim thay node"}), 404
    fingers = []
    for i in range(6):
        f = node.finger_table[i]
        fingers.append({"i": i, "start": node.finger_table.starts[i], "node": f.to_dict() if f else None})
    return jsonify({
        "name": node.name, "id": node.id, "ip": node.ip, "port": node.port,
        "successor":   node.successor.to_dict() if node.successor else None,
        "predecessor": node.predecessor.to_dict() if node.predecessor else None,
        "fingers":     fingers,
        "keys":        list(node.data_store.keys()),
    })


@app.route("/api/message", methods=["POST"])
def send_msg():
    data    = request.json or {}
    sender  = data.get("from", "").strip()
    target  = data.get("to", "").strip()
    content = data.get("content", "").strip()
    if not all([sender, target, content]):
        return jsonify({"error": "Thieu thong tin"}), 400
    with _lock:
        node = _nodes.get(sender)
    if not node:
        return jsonify({"error": f"Node {sender} khong ton tai"}), 404
    ok = node.send_message(target, content)
    if ok:
        _add_log("Tin nhan", f"[{sender}] -> [{target}]: {content}")
        return jsonify({"status": "ok"})
    return jsonify({"error": f"Khong the gui toi {target}"}), 500


@app.route("/api/simulate_change", methods=["POST"])
def simulate_change():
    data     = request.json or {}
    name     = data.get("name", "").strip()
    new_port = data.get("new_port")
    with _lock:
        node = _nodes.get(name)
    if not node:
        return jsonify({"error": f"Node {name} khong ton tai"}), 404
    old_port = node.port
    with _lock:
        bootstrap = next((n for n in _nodes.values() if n.name != name), None)
    if not bootstrap:
        return jsonify({"error": "Khong con node nao de join"}), 400
    if not new_port:
        new_port = _next_port()
    new_port = int(new_port)
    node.stop()
    with _lock:
        _nodes.pop(name, None)
    time.sleep(0.5)
    new_node = ChordNode("127.0.0.1", new_port, name)
    new_node.start(bootstrap_ip="127.0.0.1", bootstrap_port=bootstrap.port)
    with _lock:
        _nodes[name] = new_node
    _add_log("Doi dia chi", f"{name}: port {old_port} -> {new_port} (id={new_node.id})")
    return jsonify({"name": name, "new_port": new_port, "new_id": new_node.id})


@app.route("/api/log", methods=["GET"])
def get_log():
    with _lock:
        return jsonify(list(_log))


if __name__ == "__main__":
    print()
    print("  Chord DHT Web App")
    print("  Mo trinh duyet: http://localhost:8080")
    print("  Nhan Ctrl+C de dung.")
    print()
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
