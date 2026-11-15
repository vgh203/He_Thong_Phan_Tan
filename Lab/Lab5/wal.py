import os
import json
import threading

class WriteAheadLog:
    """Quản lý Write-Ahead Log (WAL) bền vững trên ổ đĩa sử dụng fsync."""
    def __init__(self, log_path):
        self.log_path = log_path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        # Mở file ở chế độ append (hoặc tạo mới nếu chưa có)
        if not os.path.exists(self.log_path):
            with open(self.log_path, 'w', encoding='utf-8') as f:
                pass

    def append(self, record):
        """Ghi đồng bộ một bản ghi JSON vào log và gọi fsync."""
        with self.lock:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                line = json.dumps(record, ensure_ascii=False) + '\n'
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

    def read_all(self):
        """Đọc toàn bộ các bản ghi trong log từ trước tới nay."""
        with self.lock:
            records = []
            if not os.path.exists(self.log_path):
                return records
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            return records

    def clear(self):
        """Xóa sạch log (dùng khi reset môi trường test)."""
        with self.lock:
            with open(self.log_path, 'w', encoding='utf-8') as f:
                pass
