import socket
import json
import threading
import time
import os
from wal import WriteAheadLog

class Participant:
    def __init__(self, pid, host='127.0.0.1', base_port=6000, coord_port=6000, data_dir='Lab5/data'):
        self.pid = pid
        self.host = host
        self.port = base_port + pid
        self.coord_host = host
        self.coord_port = coord_port
        
        self.wal = WriteAheadLog(os.path.join(data_dir, f'wal_p{pid}.log'))
        self.data_store = {}        # Dữ liệu đã committed chính thức
        self.pending_updates = {}   # tx_id -> proposed update
        self.tx_states = {}         # tx_id -> PREPARED / COMMITTED / ABORTED
        
        self.reject_next = False
        self.fail_on_prepared = False
        self.is_alive = True
        self.running = True
        self.lock = threading.Lock()
        
        # 1. Phục hồi trạng thái từ WAL trước khi mở listener
        self._recover_from_wal()
        
        # 2. Khởi động Socket Server
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)
        
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()

    def _log(self, msg):
        print(f"[P{self.pid}] {msg}")

    def _recover_from_wal(self):
        """Khôi phục trạng thái từ Write-Ahead Log cục bộ."""
        records = self.wal.read_all()
        for r in records:
            tx_id = r.get('tx_id')
            rtype = r.get('type')
            if rtype == 'PREPARED':
                self.tx_states[tx_id] = 'PREPARED'
                self.pending_updates[tx_id] = r.get('data')
            elif rtype == 'COMMITTED':
                self.tx_states[tx_id] = 'COMMITTED'
                update = self.pending_updates.pop(tx_id, r.get('data'))
                if update:
                    self.data_store.update(update)
            elif rtype == 'ABORTED':
                self.tx_states[tx_id] = 'ABORTED'
                self.pending_updates.pop(tx_id, None)
                
        # Kiểm tra nếu có giao dịch đang ở trạng thái PREPARED (in-doubt)
        in_doubt = [tx for tx, st in self.tx_states.items() if st == 'PREPARED']
        if in_doubt:
            self._log(f"Recovery found in-doubt transaction(s): {in_doubt}. Querying Coordinator...")
            for tx_id in in_doubt:
                self._query_decision(tx_id)

    def _query_decision(self, tx_id):
        """Hỏi quyết định toàn cục từ Coordinator sau khi phục hồi."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                s.connect((self.coord_host, self.coord_port))
                req = json.dumps({'type': 'DECISION_QUERY', 'tx_id': tx_id, 'sender': self.pid}) + '\n'
                s.sendall(req.encode('utf-8'))
                
                resp_data = s.recv(1024).decode('utf-8').strip()
                if resp_data:
                    resp = json.loads(resp_data)
                    decision = resp.get('decision')
                    self._log(f"Received Coordinator decision for Tx {tx_id}: {decision}")
                    if decision == 'GLOBAL_COMMIT':
                        self._apply_commit(tx_id)
                    else:
                        self._apply_abort(tx_id)
        except Exception as e:
            self._log(f"Could not reach Coordinator for Tx {tx_id} recovery: {e}")

    def _listen(self):
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
            msg = json.loads(line)
            response = self._process_message(msg)
            if response:
                conn.sendall((json.dumps(response) + '\n').encode('utf-8'))
        except Exception:
            pass
        finally:
            conn.close()

    def _process_message(self, msg):
        with self.lock:
            if not self.is_alive:
                return None
                
            mtype = msg.get('type')
            tx_id = msg.get('tx_id')
            
            # --- PHA 1: VOTE_REQUEST ---
            if mtype == 'VOTE_REQUEST':
                data = msg.get('data', {})
                self._log(f"Received VOTE_REQUEST for Tx {tx_id} with data {data}")
                
                # Giả lập từ chối (VOTE_ABORT) nếu được cấu hình
                if self.reject_next:
                    self.reject_next = False
                    self.wal.append({'type': 'ABORTED', 'tx_id': tx_id, 'reason': 'Validation failed'})
                    self.tx_states[tx_id] = 'ABORTED'
                    self._log(f"Lock Conflict! -> Log VOTE_ABORT -> Reply VOTE_ABORT")
                    return {'type': 'VOTE_ABORT', 'tx_id': tx_id, 'sender': self.pid}
                    
                # Đồng ý: Ghi bền vững PREPARED vào WAL TRƯỚC KHI gửi VOTE_COMMIT
                self.wal.append({'type': 'PREPARED', 'tx_id': tx_id, 'data': data})
                self.pending_updates[tx_id] = data
                self.tx_states[tx_id] = 'PREPARED'
                self._log(f"Log VOTE_COMMIT -> Reply VOTE_COMMIT")
                
                # Nếu được kích hoạt mô phỏng crash ngay sau PREPARED
                if self.fail_on_prepared:
                    self.fail_on_prepared = False
                    self.crash()
                    # Trả về kết quả trước khi tắt hẳn socket
                    return {'type': 'VOTE_COMMIT', 'tx_id': tx_id, 'sender': self.pid}
                    
                return {'type': 'VOTE_COMMIT', 'tx_id': tx_id, 'sender': self.pid}
                
            # --- PHA 2: GLOBAL_COMMIT ---
            elif mtype == 'GLOBAL_COMMIT':
                self._apply_commit(tx_id)
                return {'type': 'ACK', 'tx_id': tx_id, 'sender': self.pid}
                
            # --- PHA 2: GLOBAL_ABORT ---
            elif mtype == 'GLOBAL_ABORT':
                self._apply_abort(tx_id)
                return {'type': 'ACK', 'tx_id': tx_id, 'sender': self.pid}
                
            return None

    def _apply_commit(self, tx_id):
        # Ghi durable COMMITTED vào WAL
        self.wal.append({'type': 'COMMITTED', 'tx_id': tx_id})
        self.tx_states[tx_id] = 'COMMITTED'
        update = self.pending_updates.pop(tx_id, None)
        if update:
            self.data_store.update(update)
        self._log(f"Recv GLOBAL_COMMIT -> Commit -> Reply ACK")

    def _apply_abort(self, tx_id):
        # Ghi durable ABORTED vào WAL
        self.wal.append({'type': 'ABORTED', 'tx_id': tx_id})
        self.tx_states[tx_id] = 'ABORTED'
        self.pending_updates.pop(tx_id, None)
        self._log(f"Recv GLOBAL_ABORT -> Rollback -> Reply ACK")

    def crash(self):
        """Giả lập tắt đột ngột tiến trình."""
        self.is_alive = False
        self._log("CRASHED / STOPPED!")
        try:
            self.server_socket.close()
        except Exception:
            pass

    def stop(self):
        self.running = False
        self.is_alive = False
        try:
            self.server_socket.close()
        except Exception:
            pass
