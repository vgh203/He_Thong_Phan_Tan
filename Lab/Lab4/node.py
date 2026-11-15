import socket
import json
import threading
import time
from transport import send_json, send_async

class BullyNode:
    def __init__(self, node_id, host='127.0.0.1', base_port=5000, total_nodes=5):
        self.node_id = node_id
        self.host = host
        self.port = base_port + node_id
        self.total_nodes = total_nodes
        self.peers = {i: (host, base_port + i) for i in range(1, total_nodes + 1)}
        
        self.leader_id = total_nodes  # Ban đầu leader mặc định là node có ID cao nhất (P5)
        self.is_alive = True
        self.running = True
        self.state = 'NORMAL'  # NORMAL, ELECTING, WAIT_COORDINATOR, LEADER
        
        self.lock = threading.Lock()
        self.election_timer = None
        self.server_socket = None
        
        # Start server listener
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()
        
        # Start heartbeat monitoring thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    def _log(self, msg):
        print(f"[P{self.node_id}] {msg}")

    def _listen(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            self.server_socket.settimeout(0.5)
            
            while self.running:
                try:
                    conn, _ = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                    
                if not self.is_alive:
                    conn.close()
                    continue
                    
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
        except Exception as e:
            if self.running:
                self._log(f"Listener error: {e}")

    def _handle_client(self, conn):
        try:
            conn.settimeout(1.0)
            data = b''
            while self.running and self.is_alive:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b'\n' in data:
                    break
            
            if not data or not self.is_alive:
                conn.close()
                return
                
            line = data.decode('utf-8').strip()
            if not line:
                conn.close()
                return
                
            msg = json.loads(line)
            response = self._process_message(msg)
            if response:
                payload = (json.dumps(response) + '\n').encode('utf-8')
                conn.sendall(payload)
        except Exception:
            pass
        finally:
            conn.close()

    def _process_message(self, msg):
        if not self.is_alive:
            return None
            
        mtype = msg.get('type')
        sender = msg.get('sender')
        
        if mtype == 'HEARTBEAT':
            return {'type': 'HEARTBEAT_ACK', 'sender': self.node_id}
            
        elif mtype == 'ELECTION':
            self._log(f"Received ELECTION from P{sender} -> Replying OK")
            # Nút có ID cao hơn phản hồi OK và bắt đầu bầu chọn nếu chưa
            with self.lock:
                if self.state != 'ELECTING' and self.state != 'LEADER':
                    threading.Thread(target=self.start_election, daemon=True).start()
            return {'type': 'OK', 'sender': self.node_id}
            
        elif mtype == 'COORDINATOR':
            new_leader = msg.get('leader')
            with self.lock:
                self.leader_id = new_leader
                self.state = 'NORMAL'
            self._log(f"Acknowledged new Leader P{new_leader}")
            return {'type': 'ACK', 'sender': self.node_id}
            
        return None

    def _heartbeat_loop(self):
        failed_attempts = 0
        while self.running:
            time.sleep(0.5)
            if not self.is_alive:
                continue
                
            with self.lock:
                current_leader = self.leader_id
                current_state = self.state
                
            # Nếu bản thân là Leader hoặc đang trong quá trình bầu cử thì không cần kiểm tra heartbeat
            if current_leader == self.node_id or current_state in ['ELECTING', 'WAIT_COORDINATOR']:
                failed_attempts = 0
                continue
                
            # Gửi heartbeat tới leader
            l_host, l_port = self.peers[current_leader]
            ack = send_json(l_host, l_port, {'type': 'HEARTBEAT', 'sender': self.node_id}, timeout=0.4)
            
            if ack and ack.get('type') == 'HEARTBEAT_ACK':
                failed_attempts = 0
            else:
                failed_attempts += 1
                if failed_attempts >= 3:
                    self._log(f"Timeout detected! Initiating Election...")
                    failed_attempts = 0
                    threading.Thread(target=self.start_election, daemon=True).start()

    def start_election(self):
        with self.lock:
            if not self.is_alive:
                return
            self.state = 'ELECTING'
            
        self._log(f"Starting Bully Election...")
        higher_nodes = [i for i in range(self.node_id + 1, self.total_nodes + 1)]
        
        if not higher_nodes:
            # Không có node nào cao hơn -> Tự xưng leader ngay lập tức
            self._declare_leader()
            return
            
        received_ok = False
        for hid in higher_nodes:
            h_host, h_port = self.peers[hid]
            self._log(f"Sending ELECTION to higher node P{hid}")
            resp = send_json(h_host, h_port, {'type': 'ELECTION', 'sender': self.node_id}, timeout=0.8)
            if resp and resp.get('type') == 'OK':
                self._log(f"Received OK from P{hid}")
                received_ok = True
                
        if not received_ok:
            # Không có node cao hơn nào phản hồi OK -> Bản thân là node cao nhất còn sống!
            highest = higher_nodes[-1] if higher_nodes else self.node_id
            self._log(f"Timeout waiting for P{highest} -> NEW LEADER!")
            self._declare_leader()
        else:
            # Đã nhận ít nhất 1 OK từ node cao hơn -> Chờ COORDINATOR
            with self.lock:
                self.state = 'WAIT_COORDINATOR'
            self._log("Waiting for COORDINATOR announcement from higher node...")
            # Chờ tối đa 2.5s, nếu không thấy leader mới thông báo thì khởi động bầu cử lại
            time.sleep(2.5)
            with self.lock:
                if self.state == 'WAIT_COORDINATOR':
                    self._log("Timeout waiting for COORDINATOR! Restarting election...")
                    threading.Thread(target=self.start_election, daemon=True).start()

    def _declare_leader(self):
        with self.lock:
            if not self.is_alive:
                return
            self.leader_id = self.node_id
            self.state = 'LEADER'
            
        self._log(f"*** BECOMING LEADER! Broadcasting COORDINATOR to cluster ***")
        others = [f"P{pid}" for pid in range(1, self.total_nodes + 1) if pid != self.node_id]
        self._log(f"Broadcast COORDINATOR victory to {', '.join(others)}")
        for pid in range(1, self.total_nodes + 1):
            if pid != self.node_id:
                p_host, p_port = self.peers[pid]
                send_async(p_host, p_port, {'type': 'COORDINATOR', 'leader': self.node_id, 'sender': self.node_id})

    def crash(self):
        """Giả lập tiến trình bị crash / tắt đột ngột."""
        with self.lock:
            self.is_alive = False
            self.state = 'DEAD'
        print(f"[SYSTEM] Active Leader P{self.node_id} terminated.")

    def stop(self):
        self.running = False
        self.is_alive = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
