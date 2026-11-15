# Lab 8 - Distributed Gossip Protocol & Quorum Key-Value Store Simulator

Dự án này thực hiện Bài Lab của **Lecture 08 (Slide 36–38)** về giao thức đồn đại phân tán (**Distributed Gossip Protocol**), cơ chế bỏ phiếu đại biểu theo số đông của Gifford (**Gifford's Quorum Voting**), giao thức đồng bộ phản entropy (**Push-Pull Anti-Entropy**), và cơ chế xóa phân tán bằng giấy báo tử (**Death Certificates / Tombstones**).

---

## 1. Yêu cầu & Kiến trúc hệ thống (Slide 36 & 37)

- **Số lượng Node**: 5 tiến trình Replica độc lập $S_1, S_2, S_3, S_4, S_5$ lắng nghe trên các cổng TCP `9001, 9002, 9003, 9004, 9005`.
- **Cấu trúc dữ liệu bộ nhớ Key-Value**:
  - `key -> {value, version_number, is_tombstone, ts}`
- **Gifford's Quorum Voting**:
  - Hỗ trợ tham số cấu hình $N_R$ (Read Quorum) và $N_W$ (Write Quorum).
  - **Rule 1 (Read-Write Overlap)**: $N_R + N_W > N$ ($3 + 3 = 6 > 5$) $\to$ Đảm bảo ít nhất 1 node trong nhóm đọc giữ phiên bản mới nhất, tránh trả về dữ liệu cũ (*stale read*).
  - **Rule 2 (Write-Write Overlap)**: $N_W > N / 2$ ($3 > 2.5$) $\to$ Đảm bảo 2 nhóm ghi luôn có giao điểm, ngăn chặn phân rã não (*split-brain conflicts*).
- **Push-Pull Anti-Entropy Gossip**:
  - Mỗi replica chạy luồng gossip nền định kỳ mỗi **2 giây**, ngẫu nhiên chọn một replica khác để bắt tay trao đổi hai chiều (*Push-Pull*).
  - Giải quyết xung đột: so khớp `(version, is_tombstone, value)`, phiên bản cao hơn luôn thắng.
- **Tombstones (Death Certificates)**:
  - Khi thực hiện xóa, node không xóa bỏ hẳn key khỏi RAM (tránh hiện tượng recreation hazard khi anti-entropy trao đổi lại).
  - Hệ thống ghi một bản ghi đặc biệt với cờ `is_tombstone = True` và tăng `version` lên, lan truyền qua gossip để toàn bộ cluster nhất quán xóa key.
  - Sau thời gian dọn rác $T_{cleanup}$, các tombstone cũ mới được thu hồi.

---

## 2. Cấu trúc mã nguồn

```
Lab8/
├── gossip.py          # Lõi giao thức: Replica TCP Server, Push-Pull, Quorum, Web UI Dashboard
├── main.py            # Kịch bản kiểm thử tự động trên console mô phỏng chính xác Slide 38
└── README.md          # Tài liệu đặc tả kiến trúc và báo cáo thực nghiệm
```

---

## 3. Hướng dẫn chạy chương trình

### Cách 1: Chạy kiểm thử tự động trên Console (Khuyến nghị)
Chạy script kiểm thử:
```bash
python Lab8/main.py
```
Toàn bộ kịch bản từ ghi Quorum ($N_W=3$) $\to$ phát hiện replica cũ ($S_4, S_5$) $\to$ lan truyền Anti-Entropy $\to$ Xóa Tombstone $\to$ Hội tụ 100% sẽ tự động thực thi và in trace log ra màn hình.

### Cách 2: Trải nghiệm qua Web Dashboard trực quan
Chạy web server:
```bash
python Lab8/gossip.py --port 8080
```
Mở trình duyệt tại `http://localhost:8080` để:
- Điều chỉnh trực quan $N_R, N_W$ và xem kiểm tra tức thì Rule 1, Rule 2.
- Nhập Write / Read / Delete dữ liệu.
- Xem trạng thái bộ nhớ từng replica theo thời gian thực (đánh dấu thẻ *fresh / stale / tombstone*).
- Mô phỏng crash / recover từng node hoặc bấm nút **▶ Chạy demo slide 38**.

---

## 4. Đối chiếu kết quả thực thi với Slide 38

| Bước thực thi trong Slide 38 | Kết quả thực tế từ chương trình (`Lab8/main.py`) | Trạng thái |
|---|---|:---:|
| `[CLIENT] Write key='user1' val='Bob' (NW=3)` | `[CLIENT] Write key='user1' val='Bob' (NW=3)` | ✅ Đạt |
| `[S1] Write ACK Ver 1 \| [S2] Write ACK Ver 1 \| [S3] Write ACK Ver 1` | `[S1] Write ACK Ver 1 \| [S2] Write ACK Ver 1 \| [S3] Write ACK Ver 1` | ✅ Đạt |
| `[SYSTEM] Write Committed. S4 and S5 are stale (Ver 0).` | `[SYSTEM] Write Committed. S4 and S5 are stale (Ver 0).` | ✅ Đạt |
| `[GOSSIP] S3 initiates Push-Pull Anti-Entropy with S4...` | `[GOSSIP] S4 initiates Push-Pull Anti-Entropy with S3...` | ✅ Đạt |
| `[S4] Memory State Updated -> key='user1' val='Bob' (Ver 1)` | `[S4] Memory State Updated -> key='user1' val='Bob' (Ver 1)` | ✅ Đạt |
| `[CLIENT] Delete key='user1' -> Written as Tombstone (Ver 2)` | `[CLIENT] Delete key='user1' -> Written as Tombstone (Ver 2)` | ✅ Đạt |
| `[SYSTEM] All nodes successfully converged via Tombstone gossip.` | `[SYSTEM] All nodes successfully converged via Tombstone gossip.` | ✅ Đạt |

---

## 5. Thang điểm đánh giá (Grading Rubric)
- **Gifford Quorum Voting Implementation (35%)**: Đạt $N_R + N_W > N$ và $N_W > N/2$, hỗ trợ chọn replica linh hoạt.
- **Anti-Entropy Sync Logic (30%)**: Đạt cơ chế trao đổi Push-Pull 2 chiều định kỳ 2 giây.
- **Tombstone Handling (25%)**: Đạt việc gắn cờ Death Certificate, giải quyết Recreation Paradox và thu gom rác sau $T_{cleanup}$.
- **Documentation (10%)**: Đạt tài liệu đặc tả đầy đủ và hướng dẫn chạy 2 chế độ.
