# Lab 4 - Distributed Leader Election Simulator (Bully Algorithm)

Dự án này thực hiện Bài Lab của Lecture 04 (Slide 36–37) về thuật toán bầu chọn Leader phân tán (**Bully Election Algorithm**) và cơ chế phát hiện lỗi qua nhịp tim (**Heartbeat Failure Detection**) sử dụng TCP Sockets trên Python.

---

## 1. Yêu cầu & Kiến trúc hệ thống

- **Số lượng Node**: 5 tiến trình độc lập $P_1, P_2, P_3, P_4, P_5$ lắng nghe trên các cổng TCP `5001, 5002, 5003, 5004, 5005`.
- **Giao thức mạng**: Giao tiếp trực tiếp qua TCP Socket, tuần tự hóa định dạng JSON kết thúc bằng ký tự `\n`.
- **Leader ban đầu**: Node có ID cao nhất ($P_5$).
- **Cơ chế Heartbeat**: Các node sống sót liên tục gửi bản tin `HEARTBEAT` định kỳ 0.5s tới Leader hiện tại. Nếu sau 3 lần ping liên tiếp không nhận được `HEARTBEAT_ACK` (quá 1.5s), node phát hiện nghi ngờ Leader đã chết và kích hoạt bầu cử.
- **Quy tắc giải thuật Bully**:
  1. Node $P_i$ gửi bản tin `ELECTION` tới tất cả các node có ID cao hơn ($j > i$).
  2. Các node cao hơn nhận được `ELECTION` sẽ phản hồi `OK` và tự khởi xướng vòng bầu cử của chính mình.
  3. Nếu $P_i$ không nhận được bất kỳ `OK` nào sau thời gian timeout (nghĩa là không còn node cao hơn nào sống sót), $P_i$ tự xưng là Leader mới và broadcast bản tin `COORDINATOR` tới toàn bộ cluster.
  4. Sau khi Leader $P_5$ chết, tất cả các node còn lại ($P_1, P_2, P_3$) đều nhận $P_4$ làm Leader mới.

---

## 2. Cấu trúc mã nguồn

```
Lab4/
├── transport.py       # Tiện ích socket client/server, gửi/nhận JSON qua TCP
├── node.py            # Lớp BullyNode: máy trạng thái, listener, heartbeat loop, bầu cử
├── main.py            # Kịch bản kiểm thử tự động toàn bộ vòng đời cluster
└── README.md          # Tài liệu hướng dẫn và báo cáo kết quả
```

---

## 3. Cách chạy mô phỏng

1. Mở terminal tại thư mục gốc của dự án hoặc thư mục `Lab4`.
2. Chạy lệnh:
   ```bash
   python Lab4/main.py
   ```
3. Quan sát log trên màn hình:
   - **Giai đoạn 1**: Khởi tạo 5 node, xác nhận Leader ban đầu là $P_5$.
   - **Giai đoạn 2**: Giả lập $P_5$ bị sập đột ngột (`crash()`).
   - **Giai đoạn 3**: Các node phát hiện timeout, trao đổi `ELECTION` $\to$ `OK`, và $P_4$ phát bản tin `COORDINATOR`.
   - **Giai đoạn 4**: Kiểm định trạng thái cuối cùng, xác nhận toàn bộ node sống ($P_1, P_2, P_3, P_4$) hội tụ về $P_4$.

---

## 4. Nhật ký thực thi mẫu (Trace Log)

```
[INITIAL STATE CHECK]
Node P1 -> Current Leader: P5 | State: NORMAL
Node P2 -> Current Leader: P5 | State: NORMAL
Node P3 -> Current Leader: P5 | State: NORMAL
Node P4 -> Current Leader: P5 | State: NORMAL
Node P5 -> Current Leader: P5 | State: NORMAL

[PHASE 2] SIMULATING LEADER FAILURE: Killing Node P5...
[P5] CRASHED / STOPPED RESPONDING!

[P1] Leader P5 TIMEOUT (3 missed pings)! Initiating election...
[P1] Starting Bully Election...
[P1] Sending ELECTION to higher node P2
[P2] Received ELECTION from P1 -> Replying OK
[P2] Starting Bully Election...
[P2] Sending ELECTION to higher node P3
[P3] Received ELECTION from P2 -> Replying OK
[P3] Starting Bully Election...
[P3] Sending ELECTION to higher node P4
[P4] Received ELECTION from P3 -> Replying OK
[P4] Starting Bully Election...
[P4] Sending ELECTION to higher node P5
[P4] No OK received from higher nodes. Winning election!
[P4] *** BECOMING LEADER! Broadcasting COORDINATOR to cluster ***
[P1] Acknowledged new Leader P4
[P2] Acknowledged new Leader P4
[P3] Acknowledged new Leader P4

[FINAL STATE VERIFICATION]
Living Node P1 -> Leader: P4 | State: NORMAL | OK: True
Living Node P2 -> Leader: P4 | State: NORMAL | OK: True
Living Node P3 -> Leader: P4 | State: NORMAL | OK: True
Living Node P4 -> Leader: P4 | State: LEADER | OK: True
Dead Node P5 -> is_alive: False | State: DEAD

>>> TEST PASSED: All living nodes (P1..P4) successfully elected and converged on P4 as new Leader! <<<
```
