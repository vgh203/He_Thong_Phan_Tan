import socket
import json
import threading
import time
import os
from wal import WriteAheadLog

class Coordinator:
    def __init__(self, host='127.0.0.1', port=6000, participants=None, data_dir='Lab5/data'):
        self.host = host
        self.port = port
        self.participants = participants or {1: 6001, 2: 6002, 3: 6003}
        self.wal = WriteAheadLog(os.path.join(data_dir, 'wal_coordinator.log'))
        self.decisions = {} # tx_id -> GLOBAL_COMMIT / GLOBAL_ABORT
        self.running = True
        self.lock = threading.Lock()
        
        # 1. Phục hồi trạng thái quyết định từ WAL
        self._recover_from_wal()
        
        # 2. Mở Socket Listener cho DECISION_QUERY
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(0.5)
        
        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()

    def _log(self, msg):
        print(f"[COORD] {msg}")

    def _recover_from_wal(self):
        records = self.wal.read_all()
        for r in records:
            tx_id = r.get('tx_id')
            rtype = r.get('type')
            if rtype in ['GLOBAL_COMMIT', 'GLOBAL_ABORT']:
                self.decisions[tx_id] = rtype
        self._log(f"Recovered {len(self.decisions)} transaction decision(s) from WAL.")

    def _listen(self):
        while self.running:
            try:
                conn, _ = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
                
            t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
            t.start()

    def _handle_client(self, conn):
        try:
            conn.settimeout(1.0)
            data = b''
            while self.running:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b'\n' in data:
                    break
            if not data:
                return
            msg = json.loads(data.decode('utf-8').strip())
            if msg.get('type') == 'DECISION_QUERY':
                tx_id = msg.get('tx_id')
                sender = msg.get('sender')
                with self.lock:
                    decision = self.decisions.get(tx_id, 'GLOBAL_ABORT')
                self._log(f"Received DECISION_QUERY from P{sender} for Tx {tx_id} -> Replying {decision}")
                resp = json.dumps({'decision': decision, 'tx_id': tx_id}) + '\n'
                conn.sendall(resp.encode('utf-8'))
        except Exception:
            pass
        finally:
            conn.close()

    def _send_to_participant(self, pid, message, timeout=1.5):
        port = self.participants.get(pid)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((self.host, port))
                payload = (json.dumps(message) + '\n').encode('utf-8')
                s.sendall(payload)
                resp = s.recv(1024).decode('utf-8').strip()
                if resp:
                    return json.loads(resp)
        except Exception:
            return None
        return None

    def execute_transaction(self, tx_id, data):
        # 1. Ghi START_2PC bền vững vào WAL
        self.wal.append({
            'type': 'START_2PC',
            'tx_id': tx_id,
            'participants': list(self.participants.keys()),
            'data': data
        })
        self._log(f"Tx {tx_id} Started -> Log START_2PC")
        
        # 2. Gửi VOTE_REQUEST tới tất cả Participants
        self._log(f"Multicast VOTE_REQUEST")
        votes = {}
        for pid in self.participants:
            res = self._send_to_participant(pid, {'type': 'VOTE_REQUEST', 'tx_id': tx_id, 'data': data})
            if res and res.get('type') == 'VOTE_COMMIT':
                votes[pid] = 'VOTE_COMMIT'
                self._log(f"Recv VOTE_COMMIT from P{pid}")
            else:
                votes[pid] = 'VOTE_ABORT'
                self._log(f"Recv VOTE_ABORT from P{pid}")
                
        # 3. Ra quyết định toàn cục
        if all(v == 'VOTE_COMMIT' for v in votes.values()) and len(votes) == len(self.participants):
            decision = 'GLOBAL_COMMIT'
        else:
            decision = 'GLOBAL_ABORT'
            
        with self.lock:
            self.decisions[tx_id] = decision
            
        # 4. Ghi quyết định bền vững vào WAL TRƯỚC KHI thông báo
        self.wal.append({'type': decision, 'tx_id': tx_id})
        abort_votes = [pid for pid, v in votes.items() if v == 'VOTE_ABORT']
        if decision == 'GLOBAL_ABORT' and abort_votes:
            self._log(f"Recv VOTE_ABORT -> Log GLOBAL_ABORT")
        else:
            self._log(f"All VOTE_COMMIT -> Log GLOBAL_COMMIT")
        
        # 5. Multicast quyết định tới tất cả Participants
        self._log(f"Multicast {decision}")
        for pid in self.participants:
            self._send_to_participant(pid, {'type': decision, 'tx_id': tx_id}, timeout=0.8)
        
        # 6. Summary
        if decision == 'GLOBAL_COMMIT':
            print(f"[SYSTEM] Tx {tx_id} Committed Cleanly.")
        else:
            print(f"[SYSTEM] Tx {tx_id} Aborted Cleanly.")
        return decision

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
