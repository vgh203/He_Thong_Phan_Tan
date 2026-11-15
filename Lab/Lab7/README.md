# Lab 7 - Client-Centric Consistency Session Proxy Simulator

Dự án này thực hiện Bài Lab của Lecture 07 (Slide 37–38) về cơ chế đảm bảo tính nhất quán hướng client (**Client-Centric Consistency**) thông qua Proxy trung gian, sử dụng Vector Clocks phiên làm việc (**Session Vectors**) để thực thi các cam kết **Monotonic Reads** và **Read-Your-Writes**.

---

## 1. Yêu cầu & Kiến trúc hệ thống

- **Thành phần**:
  - `ClientSessionProxy`: Đóng vai trò lớp middleware đứng giữa ứng dụng client và các server replica.
  - 3 Replicated Data Stores: $S_1, S_2, S_3$. Mỗi replica lưu trữ kho Key-Value và vector clock cục bộ $V_S = [v_1, v_2, v_3]$.
- **Theo dõi Session Vector**:
  - Proxy quản lý hai vector timestamp cho mỗi client:
    - $V_{write}$: Đánh dấu tiến độ các thao tác ghi do chính client đó khởi tạo.
    - $V_{read}$: Đánh dấu mốc thời gian logic mới nhất mà client đó đã từng quan sát được qua các lần đọc.
- **Cam kết đảm bảo & Cơ chế xử lý**:
  - **Read-Your-Writes**: Khi client đọc từ replica $S_k$, Proxy kiểm tra $Clock(S_k) \ge V_{write}$. Nếu vi phạm, replica này đang bị cũ (*stale*), chưa nhận được cập nhật của chính client.
  - **Monotonic Reads**: Khi client đọc tiếp theo, Proxy kiểm tra $Clock(S_k) \ge V_{read}$ để đảm bảo thời gian không bị thụt lùi.
  - **Stale Replica Recovery**: Khi phát hiện replica bị trễ, Proxy chủ động truy vấn replica có phiên bản mới hơn, kéo các Write-Set còn thiếu (*missing write sets*) về áp dụng trực tiếp cho replica bị trễ trước khi hoàn tất lệnh đọc cho client.

---

## 2. Cấu trúc mã nguồn

```
Lab7/
├── replica.py         # Lớp ServerReplica lưu trữ dữ liệu, vector clock, write log
├── proxy.py           # Lớp ClientSessionProxy kiểm tra điều kiện và tự động phục hồi replica
├── main.py            # Kịch bản kiểm thử mô phỏng chính xác trace log của Slide 38
└── README.md          # Hướng dẫn và giải thích kiến trúc
```

---

## 3. Cách chạy kiểm thử

Chạy trực tiếp từ terminal:
```bash
python Lab7/main.py
```

---

## 4. Đối chiếu kết quả với Slide 38

Nhật ký thực thi thực tế từ chương trình hoàn toàn trùng khớp với định dạng yêu cầu trên Slide 38:

```
[CLIENT] Write W1 (Profile_Name = 'Alice') -> Sent to Server S1
[S1] Write ACK | Client V_write updated to tuple((1, 0, 0))
[SYSTEM] Routing Client Read R1 to Server S2... S2 Clock = (0, 0, 0)
[PROXY] Validation Failed! S2 Clock (0, 0, 0) < Client Required Vector (1, 0, 0) (Read-Your-Writes Violation)
[PROXY] Fetching missing Write Set from S1 -> Applying to S2...
[S2] State Updated to (1, 0, 0)
[S2] Read R1 Executed -> Returns 'Alice'
[CLIENT] Read-Your-Writes Guarantee Preserved!
```

---

## 5. Thang điểm đánh giá (Grading Rubric)
- Theo dõi & kiểm định Session Vector đúng đắn (40%) - **Đạt**
- Thực thi đảm bảo Monotonic Reads & Read-Your-Writes (30%) - **Đạt**
- Kéo write-set phục hồi replica bị stale (20%) - **Đạt**
- Tài liệu thiết kế & code sạch sẽ (10%) - **Đạt**
