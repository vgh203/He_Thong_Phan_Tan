# Secure Group Multicast & ABAC Policy Simulator (Lab 10)

Hệ thống mô phỏng Truyền thông đa hướng nhóm bảo mật với Cây khóa phân cấp LKH (Logical Key Hierarchy) và Bộ máy kiểm soát truy cập dựa trên thuộc tính ABAC (Attribute-Based Access Control) theo nội dung **Lecture 10 (Slides 36–40)**.

---

## 📁 Cấu trúc thư mục

```
lab10/
├── crypto_utils.py       # Mã hóa & giải mã đối xứng AES-256-GCM, sinh khóa 256-bit
├── lkh_tree.py           # Cấu trúc cây LKH nhị phân (d=2, N=8, h=3) & thuật toán Rekeying
├── abac_engine.py        # Bộ máy đánh giá chính sách ABAC (Subject, Action, Time)
├── server.py             # Tiến trình Key Server (Key Graph Controller) quản lý TCP Socket
├── client.py             # Tiến trình Group Client duy trì 4 khóa đường dẫn và nhận multicast
├── simulation.py         # Kịch bản mô phỏng toàn diện & Verification Checklist (Slide 39)
├── test_lab10.py         # Bộ kiểm thử tự động pytest (7 test cases kiểm thử mật mã & API)
├── REPORT.md             # Báo cáo thiết kế kỹ thuật & đánh giá an toàn chi tiết
├── dashboard/            # Giao diện Web Dashboard tương tác trực quan
│   ├── app.py            # Backend Flask phục vụ API REST & Socket state
│   ├── templates/
│   │   └── index.html    # Giao diện HTML5 hiển thị sơ đồ cây SVG và bảng điều khiển
│   └── static/
│       ├── css/style.css # Giao diện hiện đại (Dark Theme)
│       └── js/dashboard.js # Xử lý tương tác, cập nhật sơ đồ cây thời gian thực
└── README.md
```

---

## 🚀 Hướng dẫn chạy nhanh

### 1. Chạy kịch bản mô phỏng kiểm thử chuẩn (Console Trace Log & Verification Checklist)
Khớp chính xác từng dòng nhật ký từ Slide 39:
```bash
python simulation.py
```

### 2. Chạy bộ kiểm thử tự động với Pytest
Kiểm chứng 100% tính đúng đắn của thuật toán:
```bash
pytest test_lab10.py -v
```

### 3. Khởi chạy Web Dashboard trực quan
```bash
python dashboard/app.py
```
Mở trình duyệt truy cập: **[http://localhost:5000](http://localhost:5000)** để xem:
- Sơ đồ cây LKH trực quan hóa bằng SVG (15 nút, phân tầng, mã màu trạng thái).
- Nút bấm trực quan cho `CLIENT_3 Join` (3 blocks) và `CLIENT_7 Leave` (6 blocks).
- Bộ mô phỏng phát bản tin ABAC & Ma trận giải mã của 8 thành viên.
- Kiểm thử 1-click bộ Verification Checklist.
- Console Trace Log theo thời gian thực.

### 4. Chạy độc lập qua TCP Socket trên nhiều cửa sổ Terminal
- **Cửa sổ 1 (Key Server):**
  ```bash
  python server.py --port 9999
  ```
- **Cửa sổ 2 (CLIENT_1 - Publisher):**
  ```bash
  python client.py --id CLIENT_1 --role Publisher --port 9999
  ```
- **Cửa sổ 3 (CLIENT_3 - Join vào nhóm):**
  ```bash
  python client.py --id CLIENT_3 --role Subscriber --action join --port 9999
  ```

---

## 🎯 Đáp ứng yêu cầu & Thang điểm (Slide 40)

1. **Cây khóa LKH & Dynamic Rekeying (35%):**
   - Cây nhị phân $d=2, N=8, h=3$ gồm 15 nút. Mỗi client lưu đúng $h+1=4$ khóa.
   - Khi **JOIN** (`CLIENT_3`): Cấp mới các khóa trên đường dẫn lên gốc, phát bản tin Rekey gồm đúng **$h=3$ khối khóa** mã hóa bằng khóa cũ (Đảm bảo **Forward Secrecy**).
   - Khi **LEAVE** (`CLIENT_7`): Thu hồi lá 14, phát bản tin Rekey gồm đúng **$d \times h = 2 \times 3 = 6$ khối khóa** mã hóa bằng các khóa con (Đảm bảo **Backward Secrecy**).
   - Độ phức tạp truyền tin giảm từ $O(N)$ xuống $O(\log N)$.

2. **Mã hóa & Giải mã Multicast AES-256-GCM (30%):**
   - Khóa đối xứng 256-bit, IV/Nonce 12-byte, Authentication Tag 16-byte.
   - Xác thực Verification Checklist: Thành viên rời nhóm (`CLIENT_7`) không thể giải mã thông điệp mới; thành viên mới (`CLIENT_3`) không thể giải mã thông điệp cũ.

3. **Bộ máy đánh giá chính sách ABAC (25%):**
   - Quy tắc: `ALLOW IF Client.Role == 'Publisher' AND Time >= '08:00' AND Time <= '18:00'`.
   - Ngăn chặn triệt để khi vai trò là `Subscriber` hoặc thời gian ngoài khung giờ quy định.

4. **Cấu trúc mã nguồn, Báo cáo thiết kế & Console Trace Log (10%):**
   - Console Trace Log khớp 100% mẫu Slide 39.
   - Báo cáo thiết kế đầy đủ tại `REPORT.md`.
   - Web Dashboard trực quan hóa tại `dashboard/app.py`.

