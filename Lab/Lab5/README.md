# Lab 5 - Two-Phase Commit (2PC) Simulator with WAL & Recovery

Dự án này thực hiện Bài Lab của Lecture 05 (Slide 53–54) về giao thức cam kết hai pha (**Two-Phase Commit - 2PC**), cơ chế ghi nhật ký phục hồi (**Write-Ahead Logging - WAL**) đồng bộ trên đĩa bền vững (`fsync`), và khả năng phục hồi tự động khi tiến trình bị sập (**Crash-Recovery Protocol**).

---

## 1. Yêu cầu & Kiến trúc hệ thống

- **Kiến trúc mạng**: 
  - 1 Coordinator (Socket Server cổng `6000`)
  - 3 Participant độc lập $P_1, P_2, P_3$ (Socket Servers cổng `6001, 6002, 6003`)
- **Lưu trữ bền vững (Stable Storage)**:
  - Mỗi node sở hữu file log riêng biệt: `wal_coordinator.log`, `wal_p1.log`, `wal_p2.log`, `wal_p3.log`.
  - Mọi thao tác ghi log đều thực hiện qua `f.flush()` và `os.fsync(f.fileno())` nhằm đảm bảo dữ liệu ghi thẳng xuống ổ đĩa trước khi gửi thông điệp mạng.
- **Quy trình 2 Pha**:
  - **Pha 1 (Prepare & Vote)**: Coordinator ghi `START_2PC`, multicast `VOTE_REQUEST`. Participant kiểm tra điều kiện; nếu đồng ý, ghi bền vững `PREPARED` vào WAL rồi trả lời `VOTE_COMMIT`; nếu từ chối, ghi `ABORTED` và trả lời `VOTE_ABORT`.
  - **Pha 2 (Global Decision)**: Nếu tất cả vote YES, Coordinator ghi bền vững `GLOBAL_COMMIT` vào WAL và multicast lệnh Commit; nếu có ít nhất 1 node từ chối hoặc timeout, Coordinator ghi và multicast `GLOBAL_ABORT`.
  - **Phục hồi (Recovery)**: Khi Participant khởi động lại sau crash, nó đọc file WAL cũ. Nếu phát hiện giao dịch đang ở trạng thái `PREPARED` (in-doubt), nó gửi `DECISION_QUERY` lên Coordinator để truy vấn quyết định chính thức và hoàn tất giao dịch.

---

## 2. Cấu trúc mã nguồn

```
Lab5/
├── wal.py             # Lớp WriteAheadLog quản lý ghi/đọc đồng bộ fsync
├── participant.py     # Lớp Participant (Socket Server, WAL, pending data, recovery)
├── coordinator.py     # Lớp Coordinator (2PC engine, multicast, WAL, DECISION_QUERY)
├── main.py            # Bộ kiểm thử tự động 3 kịch bản: Commit, Abort, Crash-Recovery
└── README.md          # Hướng dẫn và báo cáo kết quả thực nghiệm
```

---

## 3. Cách chạy kiểm thử

Chạy trực tiếp kịch bản kiểm thử tích hợp:
```bash
python Lab5/main.py
```

---

## 4. Báo cáo kết quả kiểm thử 3 kịch bản

### Kịch bản 1: Commit bình thường (Tx 101)
- Dữ liệu giao dịch: `{'account': 'Alice', 'balance': 500}`
- Toàn bộ $P_1, P_2, P_3$ đều đồng ý $\to$ Coordinator ra quyết định `GLOBAL_COMMIT`.
- Kết quả: Tất cả các node đều ghi WAL và cập nhật kho dữ liệu thành công.

### Kịch bản 2: Huỷ bỏ giao dịch do Participant từ chối (Tx 102)
- Giả lập $P_3$ kiểm tra nghiệp vụ thất bại và gửi `VOTE_ABORT`.
- Coordinator ghi `GLOBAL_ABORT` và phát lệnh Rollback.
- Kết quả: Cả 3 node đều chuyển sang trạng thái `ABORTED`, dữ liệu pending bị hủy bỏ, tính toàn vẹn được bảo toàn.

### Kịch bản 3: Chịu lỗi và Phục hồi sau sự cố (Tx 103)
- $P_2$ ghi `PREPARED` vào WAL và gửi `VOTE_COMMIT`, sau đó bị **ép tắt đột ngột (CRASH)**.
- Coordinator thu thập đủ 3 phiếu YES và quyết định `GLOBAL_COMMIT`.
- $P_2$ được khởi động lại (`REBOOT`). Nó đọc file log cũ trên đĩa, phát hiện Tx 103 đang ở trạng thái `PREPARED` (chưa biết kết quả).
- $P_2$ gửi `DECISION_QUERY` lên Coordinator $\to$ nhận được `GLOBAL_COMMIT` $\to$ áp dụng cập nhật `{'account': 'Charlie', 'balance': 1200}` vào cơ sở dữ liệu.
- Kết quả: **Thuật toán đảm bảo tính nguyên tử (Atomicity) 100% dù có lỗi crash xảy ra giữa chừng**.
