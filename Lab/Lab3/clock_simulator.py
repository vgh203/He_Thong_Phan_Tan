import threading
import queue
import time
import random

# Số lượng tiến trình
NUM_PROCESSES = 3

class Process(threading.Thread):
    def __init__(self, pid, queues):
        super().__init__()
        self.pid = pid                # ID của tiến trình (0, 1, 2)
        self.queues = queues          # Mảng chứa 3 queues của 3 tiến trình
        self.lamport_clock = 0        # Số nguyên (Lamport)
        self.vector_clock = [0] * NUM_PROCESSES  # Mảng size 3 (Vector)
        
    def run(self):
        # Chạy vòng lặp mô phỏng (ví dụ chạy 10 sự kiện rồi dừng)
        for _ in range(10):
            time.sleep(random.uniform(0.1, 0.5))
            
            # Chọn ngẫu nhiên loại sự kiện (1: Internal, 2: Send, 3: Receive)
            # Ưu tiên nhận tin nhắn nếu queue không trống
            if not self.queues[self.pid].empty():
                event_type = 3
            else:
                event_type = random.choice([1, 2])
            
            if event_type == 1:
                self.internal_event()
            elif event_type == 2:
                self.send_event()
            elif event_type == 3:
                self.receive_event()

    def internal_event(self):
        # 1. Tăng đồng hồ cho sự kiện nội bộ
        self.lamport_clock += 1
        self.vector_clock[self.pid] += 1
        print(f"[P{self.pid}] LOCAL EVENT  | Lamport: {self.lamport_clock} | Vector: {self.vector_clock}")

    def send_event(self):
        # 1. Cập nhật đồng hồ trước khi gửi (giống sự kiện nội bộ)
        self.lamport_clock += 1
        self.vector_clock[self.pid] += 1
        
        # 2. Chọn ngẫu nhiên 1 tiến trình đích để gửi (khác bản thân)
        target = random.choice([i for i in range(NUM_PROCESSES) if i != self.pid])
        
        # 3. Đóng gói message mang theo timestamp
        message = {
            'sender': self.pid,
            'lamport': self.lamport_clock,
            'vector': list(self.vector_clock) # Gửi bản sao của mảng
        }
        self.queues[target].put(message)
        print(f"[P{self.pid}] SEND MSG to P{target} | Lamport: {self.lamport_clock} | Vector: {self.vector_clock}")

    def receive_event(self):
        # Lấy tin nhắn từ Queue
        msg = self.queues[self.pid].get()
        recv_vector = msg['vector']
        recv_lamport = msg['lamport']
        sender = msg['sender']

        # --- CONCURRENCY DETECTION (Phát hiện xung đột đồng thời) ---
        # Hai vector clock là concurrent nếu không ai nhỏ hơn hoặc bằng ai hoàn toàn.
        is_less_than_or_eq = all(self.vector_clock[i] <= recv_vector[i] for i in range(NUM_PROCESSES))
        is_greater_than_or_eq = all(self.vector_clock[i] >= recv_vector[i] for i in range(NUM_PROCESSES))
        
        if not is_less_than_or_eq and not is_greater_than_or_eq:
            print(f"[P{self.pid}] CONFLICT DETECTED with P{sender}! Vector {self.vector_clock} || {recv_vector}")

        # --- UPDATE CLOCKS THEO THUẬT TOÁN ---
        # 1. Component-wise Max merge cho Vector Clock
        for i in range(NUM_PROCESSES):
            self.vector_clock[i] = max(self.vector_clock[i], recv_vector[i])
        
        # 2. Max merge cho Lamport Clock
        self.lamport_clock = max(self.lamport_clock, recv_lamport)
        
        # 3. Tăng đồng hồ bản thân (vì nhận tin nhắn là 1 sự kiện)
        self.vector_clock[self.pid] += 1
        self.lamport_clock += 1
        
        print(f"[P{self.pid}] RECV MSG fr P{sender} | Lamport: {self.lamport_clock} | Vector: {self.vector_clock}")

if __name__ == "__main__":
    # Khởi tạo 3 queues thread-safe
    queues = [queue.Queue() for _ in range(NUM_PROCESSES)]
    
    # Khởi tạo và chạy các Thread
    threads = [Process(i, queues) for i in range(NUM_PROCESSES)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print("Mô phỏng hoàn tất!")
