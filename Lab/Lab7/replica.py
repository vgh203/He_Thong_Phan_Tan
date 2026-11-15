import copy
import threading

class ServerReplica:
    """Đại diện cho một kho lưu trữ dữ liệu bản sao (Replica Server)."""
    def __init__(self, server_id, total_servers=3):
        self.server_id = server_id  # 1, 2, hoặc 3
        self.total_servers = total_servers
        self.clock = [0] * total_servers  # Vector clock cục bộ
        self.store = {}                   # Key-Value data store
        self.write_log = []               # Danh sách các write operation đã áp dụng
        self.lock = threading.Lock()

    def apply_write(self, key, value, op_id=None):
        """Thực thi ghi trực tiếp tại replica này."""
        with self.lock:
            # Tăng clock của bản thân
            self.clock[self.server_id - 1] += 1
            self.store[key] = value
            op = {
                'op_id': op_id or f"W_{self.server_id}_{self.clock[self.server_id - 1]}",
                'key': key,
                'value': value,
                'clock_snapshot': list(self.clock),
                'origin_server': self.server_id
            }
            self.write_log.append(op)
            return op, list(self.clock)

    def read(self, key):
        """Đọc giá trị của key từ replica."""
        with self.lock:
            return self.store.get(key, None), list(self.clock)

    def sync_write_set(self, missing_ops):
        """Áp dụng các write-set được đồng bộ từ replica khác sang."""
        with self.lock:
            for op in missing_ops:
                self.store[op['key']] = op['value']
                # Merge vector clock theo max
                for i in range(self.total_servers):
                    self.clock[i] = max(self.clock[i], op['clock_snapshot'][i])
                if op not in self.write_log:
                    self.write_log.append(op)
            return list(self.clock)
