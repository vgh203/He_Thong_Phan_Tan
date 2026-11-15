import socket
import json
import threading

def send_json(host, port, data, timeout=1.0):
    """Gửi một bản tin JSON qua TCP socket với timeout."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            payload = (json.dumps(data) + '\n').encode('utf-8')
            s.sendall(payload)
            # Nếu cần đọc response ngắn
            try:
                response = b''
                while True:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if b'\n' in response:
                        break
                if response:
                    return json.loads(response.decode('utf-8').strip())
            except socket.timeout:
                pass
            return None
    except (socket.error, ConnectionRefusedError, socket.timeout, json.JSONDecodeError):
        return None

def send_async(host, port, data):
    """Gửi bản tin trong thread nền để không block luồng xử lý chính."""
    t = threading.Thread(target=send_json, args=(host, port, data), daemon=True)
    t.start()
