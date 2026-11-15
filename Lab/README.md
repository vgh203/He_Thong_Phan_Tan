# 🧪 Practical Labs — Hệ Thống Phân Tán

**Sinh viên:** Võ Gia Huy — N23DCCN163  
**Lớp:** D23CQCNPMN02-N  
**Môn học:** Hệ Thống Phân Tán

---

## 📋 Danh sách Lab

| Lab | Chủ đề | Công nghệ | Trạng thái |
|-----|--------|-----------|------------|
| [Lab 1](./Lab1/) | Architecting Latency Hiding | Python · Flask · JavaScript | ✅ Hoàn thành |
| [Lab 2](./Lab2/) | Mini-DHT Registry & Messaging (Chord) | Python · TCP Sockets · Flask | ✅ Hoàn thành |
| [Lab 3](./Lab3/) | Logical Clock Simulator | Python · Threading | ✅ Hoàn thành |
| [Lab 4](./Lab4/) | Distributed Leader Election (Bully Algorithm) | Python · TCP Sockets | ✅ Hoàn thành |
| [Lab 5](./Lab5/) | Two-Phase Commit + WAL + Crash Recovery | Python · TCP Sockets · fsync | ✅ Hoàn thành |
| [Lab 7](./Lab7/) | Client-Centric Consistency Session Proxy | Python · Vector Clocks | ✅ Hoàn thành |
| [Lab 8](./Lab8/) | Distributed Gossip & Quorum Simulator | Python · TCP Sockets · Multiprocessing | ✅ Hoàn thành |
| [Lab 9](./Lab9/) | Secure RPC & KDC Authentication Proxy | Python · AES-CBC · HMAC-SHA256 · Sockets | ✅ Hoàn thành |
| [Lab 10](./Lab10/) | Secure Group Multicast & ABAC Policy Simulator | Python · LKH Binary Tree · AES-GCM · ABAC | ✅ Hoàn thành |

---

## 🔍 Tóm tắt từng Lab

### 🔹 Lab 1 — Architecting Latency Hiding
> *Lecture 01 — The Illusion of One*

Xây dựng form đăng ký client-server để minh hoạ kỹ thuật **Latency Hiding**:
- **Task 1**: Form server-side, mỗi lần submit lỗi phải chờ ~1 giây (giả lập WAN round-trip).
- **Task 2**: Chuyển logic validate về JavaScript phía client → phản hồi lỗi tức thì (<5 ms).
- **Task 3**: Ánh xạ cải tiến với **Fallacy #2 của Peter Deutsch** — *"Latency is zero"*.

```
Lab1/
├── app.py            # Flask server + route /register với time.sleep(1)
├── templates/
│   └── index.html    # Form + toggle Local Validation + đo performance.now()
└── README.md
```

---

### 🔹 Lab 2 — Mini-DHT Registry & Messaging (Chord)
> *Lecture 02 — Naming & Flat Name Resolution*

Hệ thống **Chord DHT** thu nhỏ với finger table O(log N) và web UI trực quan:
- Tìm kiếm phân tán O(log N) qua TCP RPC (JSON over TCP).
- Fault-tolerant: `stabilize`, `fix_fingers`, `check_predecessor` chạy nền.
- Mô phỏng đổi IP node và vẫn gửi tin nhắn thành công.

```
Lab2/
├── chord/            # config, utils, finger_table, network, node
├── frontend/         # Giao diện web hiển thị ring + finger table
├── web_app.py        # REST API + server web
├── run_node.py       # Khởi động node qua terminal
└── run_client.py     # Client terminal
```

---

### 🔹 Lab 3 — Logical Clock Simulator
> *Lecture 03 — Synchronization & Logical Clocks*

Mô phỏng **Lamport Clock** và **Vector Clock** trên 3 tiến trình song song (P₀, P₁, P₂):
- Giao tiếp qua thread-safe queues.
- Tự động phát hiện và log **xung đột đồng thời** (concurrent conflict).

```
Lab3/
├── clock_simulator.py   # 3 threads, Lamport + Vector Clock, concurrency detection
└── README.md
```

---

### 🔹 Lab 4 — Distributed Leader Election (Bully Algorithm)
> *Lecture 04 — Coordination & Election*

Mô phỏng **Bully Algorithm** trên cluster 5 node (P₁–P₅) qua TCP Sockets:
- **Heartbeat** phát hiện leader chết sau 3 lần miss ping (1.5 giây).
- Trao đổi `ELECTION → OK → COORDINATOR` cho đến khi hội tụ.
- Sau khi P₅ crash → toàn bộ node hội tụ bầu P₄ làm leader mới.

```
Lab4/
├── transport.py    # TCP socket client/server, JSON over TCP
├── node.py         # BullyNode: heartbeat, election state machine
└── main.py         # Kịch bản kiểm thử tự động toàn vòng đời cluster
```

---

### 🔹 Lab 5 — Two-Phase Commit + WAL + Crash Recovery
> *Lecture 05 — Consistency & Replication*

Hiện thực đầy đủ giao thức **2PC** với bền vững ổ đĩa (`fsync`) và tự phục hồi:
- 1 Coordinator + 3 Participants, giao tiếp TCP Sockets.
- **WAL** (`fsync` đồng bộ) đảm bảo log ghi xuống đĩa trước khi gửi tin.
- **Crash-Recovery**: node khởi động lại → đọc WAL → gửi `DECISION_QUERY` → hoàn tất.
- 3 kịch bản kiểm thử: Commit bình thường · Abort do từ chối · Crash & Recovery.

```
Lab5/
├── wal.py           # WriteAheadLog: ghi/đọc fsync
├── participant.py   # Participant: vote, WAL, pending data, recovery
├── coordinator.py   # Coordinator: 2PC engine, multicast, DECISION_QUERY
└── main.py          # Kiểm thử 3 kịch bản tích hợp
```

---

### 🔹 Lab 7 — Client-Centric Consistency Session Proxy
> *Lecture 07 — Consistency*

**Session Proxy** đứng giữa client và 3 replica, dùng **Vector Clock** đảm bảo:
- **Read-Your-Writes**: Chặn đọc từ replica stale chưa có write của chính client.
- **Monotonic Reads**: Đảm bảo thời gian logic không thụt lùi giữa các lần đọc.
- **Stale Recovery**: Proxy tự kéo write-set còn thiếu từ replica mới hơn về áp dụng.

```
Lab7/
├── replica.py    # ServerReplica: key-value store, vector clock, write log
├── proxy.py      # ClientSessionProxy: kiểm tra & tự phục hồi replica stale
└── main.py       # Kịch bản mô phỏng trace log theo Slide 38
```

---

### 🔹 Lab 8 — Distributed Gossip & Quorum Simulator
> *Lecture 08 — Consistency Protocols & Quorum Systems*

Mô phỏng **Gifford Quorum**, giao thức **Push-Pull Anti-Entropy Gossip**, và xử lý xóa phân tán bằng **Tombstones**:
- **Gifford Quorum**: Kiểm tra $N_R + N_W > N$ và $N_W > N/2$ chống stale reads và split-brain.
- **Anti-Entropy Gossip**: Chu kỳ 2 giây ngẫu nhiên trao đổi hai chiều giữa 5 replica S1..S5.
- **Tombstones (Death Certificates)**: Đánh dấu bản ghi đã xóa, chống hiện tượng recreate khi gossip.
- Hỗ trợ cả script kiểm thử tự động console (`main.py`) và giao diện Web Dashboard trực quan (`gossip.py`).

```
Lab8/
├── gossip.py     # Replica TCP Server, Push-Pull Gossip, Quorum, Web UI Dashboard
├── main.py       # Kịch bản kiểm thử console mô phỏng chính xác Slide 38
└── README.md     # Tài liệu thiết kế và hướng dẫn chạy
```

---

### 🔹 Lab 9 — Secure RPC & KDC Authentication Proxy
> *Lecture 09 — Security Concepts & Authentication*

Mô phỏng kênh gọi thủ tục từ xa bảo mật (**Secure RPC**) và giao thức xác thực cấp vé **Needham-Schroeder** qua KDC:
- **KDC Authentication**: Bắt tay 5 bước Needham-Schroeder, sinh $Ticket_{Bob}$ và khóa phiên $K_{AB}$ (256-bit).
- **Secure RPC Channel**: Mã hóa AES-CBC với khóa phiên ngẫu nhiên và đệm PKCS7.
- **Integrity Verification**: Gắn mã băm HMAC-SHA256 (Encrypt-then-MAC) vào mọi payload.
- **Anti-Replay Protection**: Theo dõi Nonce để từ chối các gói tin phát lại.
- Tích hợp cả kịch bản kiểm thử tấn công (Replay Attack & Tampering) và Web Dashboard.

```
Lab9/
├── kdc.py             # KDC Daemon: quản lý khóa dài hạn và cấp vé
├── server.py          # Secure Resource Server: giải mã vé, xác thực HMAC, thực thi RPC
├── rpc_proxy.py       # Lớp SecureRPCProxy phía client
├── client.py          # Ứng dụng client mẫu
├── run_simulation.py  # Runner điều phối 3 tiến trình
├── main.py            # Entry point chạy kịch bản hoàn chỉnh
├── test_secure_rpc.py # Bộ 6 unit/integration tests tự động (pytest)
└── README.md          # Báo cáo kiến trúc chi tiết
```

---

### 🔹 Lab 10 — Secure Group Multicast & ABAC Policy Simulator
> *Lecture 10 — Security Mechanisms & Access Control*

Mô phỏng cây khóa logic (**LKH - Logical Key Hierarchy**) cho bảo mật nhóm phân tán và kiểm soát truy cập dựa trên thuộc tính (**ABAC**):
- **LKH Binary Tree**: Cây nhị phân cân bằng ($N=8$ lá, $h=3$). Cấp lại khóa khi Join tốn $h$ khối và khi Leave tốn $d \times h = 2 \times 3 = 6$ khối mã hóa ($O(\log N)$).
- **Forward & Backward Secrecy**: Đảm bảo thành viên mới vào không đọc được tin cũ, thành viên rời nhóm không đọc được tin mới.
- **ABAC Policy Engine**: Kiểm tra nghiêm ngặt 3 thuộc tính Subject (Role == Publisher), Action (Publish Multicast), và Time (08:00 - 18:00).
- **AES-256-GCM Payload**: Mã hóa dữ liệu multicast xác thực bằng Root Group Key $K_0$.

```
Lab10/
├── lkh_tree.py       # Cấu trúc cây LKH, quản lý Key Graph và thuật toán rekeying
├── crypto_utils.py   # Mã hóa AES-256-GCM có xác thực và tạo khóa 256-bit
├── abac_engine.py    # Engine đánh giá chính sách kiểm soát truy cập ABAC
├── server.py         # Key Server: Socket TCP, điều phối LKH và multicast
├── client.py         # Group Client: lưu trữ mảng khóa cục bộ và giải mã rekey
├── simulation.py     # Kịch bản mô phỏng Slide 39 và 4 bài test checklist
├── main.py           # Entry point thực thi kiểm thử tự động
├── test_lab10.py     # Bộ 7 unit/integration tests tự động (pytest)
└── README.md         # Báo cáo kỹ thuật chi tiết
```

---

## ⚙️ Yêu cầu chung

```bash
Python 3.10+
pip install flask   # Chỉ cần cho Lab 1 và Lab 2
```

Mỗi Lab chạy độc lập. Xem **README.md** trong từng thư mục để biết lệnh chạy cụ thể.
