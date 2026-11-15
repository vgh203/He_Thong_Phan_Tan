import copy

class ClientSessionProxy:
    """Proxy đảm bảo các cam kết Client-Centric Consistency (Monotonic Reads & Read-Your-Writes)."""
    def __init__(self, replicas):
        self.replicas = replicas # Dict: {1: S1, 2: S2, 3: S3}
        self.sessions = {}       # client_id -> {'v_read': [...], 'v_write': [...]}

    def _get_session(self, client_id):
        if client_id not in self.sessions:
            self.sessions[client_id] = {
                'v_read': [0, 0, 0],
                'v_write': [0, 0, 0]
            }
        return self.sessions[client_id]

    def _vector_greater_or_equal(self, v_server, v_client):
        """Kiểm tra điều kiện: Mọi thành phần của v_server >= v_client."""
        return all(v_server[i] >= v_client[i] for i in range(len(v_client)))

    def write(self, client_id, target_server_id, key, value, op_label="W1"):
        """Client thực hiện thao tác GHI thông qua Proxy."""
        session = self._get_session(client_id)
        replica = self.replicas[target_server_id]
        
        print(f"[CLIENT] Write {op_label} ({key} = '{value}') -> Sent to Server S{target_server_id}")
        op, new_clock = replica.apply_write(key, value, op_id=op_label)
        
        # Cập nhật Session Write Vector của Client
        for i in range(len(session['v_write'])):
            session['v_write'][i] = max(session['v_write'][i], new_clock[i])
            
        print(f"[S{target_server_id}] Write ACK | Client V_write updated to {tuple(session['v_write'])}")
        return op

    def read(self, client_id, target_server_id, key, op_label="R1"):
        """Client thực hiện thao tác ĐỌC thông qua Proxy có kiểm tra tính nhất quán."""
        session = self._get_session(client_id)
        replica = self.replicas[target_server_id]
        
        print(f"[SYSTEM] Routing Client Read {op_label} to Server S{target_server_id}... S{target_server_id} Clock = {tuple(replica.clock)}")
        
        # 1. Kiểm tra Read-Your-Writes: Clock(Server) >= V_write(Client)
        ryw_valid = self._vector_greater_or_equal(replica.clock, session['v_write'])
        # 2. Kiểm tra Monotonic Reads: Clock(Server) >= V_read(Client)
        mr_valid = self._vector_greater_or_equal(replica.clock, session['v_read'])
        
        sync_happened = False
        sync_clock = None
        if not ryw_valid or not mr_valid:
            if not ryw_valid:
                violation_type = f"Client V_write {tuple(session['v_write'])}"
            else:
                violation_type = f"Client V_read {tuple(session['v_read'])} (Monotonic Reads Violation)"
                
            required_vector = [max(session['v_write'][i], session['v_read'][i]) for i in range(3)]
            print(f"[PROXY] Validation Failed! S{target_server_id} Clock {tuple(replica.clock)} < {violation_type}")
            
            # --- PHỤC HỒI REPLICA CŨ (Stale Replica Recovery) ---
            # Tìm replica nguồn có phiên bản mới hơn chứa các write-set cần thiết
            source_server_id = None
            missing_ops = []
            for sid, r in self.replicas.items():
                if sid != target_server_id and self._vector_greater_or_equal(r.clock, required_vector):
                    source_server_id = sid
                    missing_ops = copy.deepcopy(r.write_log)
                    break
                    
            if source_server_id and missing_ops:
                op_labels = ", ".join(op.get('op_id', 'W') for op in missing_ops)
                print(f"[PROXY] Fetching missing Write Set {op_labels} from S{source_server_id} -> Applying to S{target_server_id}...")
                new_clock = replica.sync_write_set(missing_ops)
                sync_happened = True
                sync_clock = tuple(new_clock)
            else:
                print(f"[PROXY] STALLING: No replica currently satisfies the required vector. Waiting...")
                return None
                
        # Thực hiện đọc sau khi replica đã đảm bảo nhất quán
        val, server_clock = replica.read(key)
        
        # Cập nhật Session Read Vector của Client
        for i in range(len(session['v_read'])):
            session['v_read'][i] = max(session['v_read'][i], server_clock[i])
            
        if sync_happened:
            print(f"[S{target_server_id}] State Updated to {sync_clock} | Read {op_label} Executed -> Returns '{val}'")
        else:
            print(f"[S{target_server_id}] Read {op_label} Executed -> Returns '{val}'")
            
        if not ryw_valid:
            print("[CLIENT] Read-Your-Writes Guarantee Preserved!")
        if not mr_valid:
            print("[CLIENT] Monotonic Reads Guarantee Preserved!")
            
        return val
