# Lab 1 - Architecting Latency Hiding

Dự án này thực hiện Bài Lab của Chương 1, mô phỏng lại cách che giấu độ trễ mạng (Latency Hiding) thông qua việc phân chia logic xác thực (validation) giữa Client và Server.

## Yêu cầu

- Python 3
- Flask

Cài đặt Flask nếu chưa có:
```bash
pip install flask
```

## Chạy ứng dụng

1. Mở terminal tại thư mục `Lab1`.
2. Chạy file server:
   ```bash
   python app.py
   ```
3. Truy cập vào trình duyệt tại địa chỉ: `http://127.0.0.1:5000`

## Nội dung bài Lab

### Task 1: Mô hình mạng truyền thống (High Latency)
- **Tắt** tuỳ chọn `Enable Local Validation`.
- Điền dữ liệu không hợp lệ (ví dụ: username ngắn hơn 5 ký tự) và nhấn Register.
- Quan sát độ trễ: Quá trình submit sẽ gửi request lên server. Server phản hồi sau 1 giây (được giả lập bằng `time.sleep(1)` để mô phỏng độ trễ WAN). 
- Kết quả trả về sẽ hiển thị lỗi kèm theo thời gian xử lý (khoảng >1000ms). Người dùng cảm nhận rõ độ trễ (latency penalty).

### Task 2: Che giấu độ trễ (Local Validation)
- **Bật** tuỳ chọn `Enable Local Validation`.
- Điền dữ liệu không hợp lệ và nhấn Register.
- Quan sát độ trễ: Quá trình xác thực diễn ra hoàn toàn bằng JavaScript ở phía client (trình duyệt).
- Kết quả: Lỗi được báo ngay lập tức (chỉ khoảng < 5ms). Không có request nào được gửi qua mạng, mang lại trải nghiệm tức thì (Instant Local Feedback). Hệ thống tạo ra "The Illusion of One" (ảo giác hệ thống hoạt động liền mạch như một thiết bị đơn lẻ).

### Task 3: Đánh giá và Ánh xạ với 8 False Assumptions
Mô hình "Local Validation" này giúp chúng ta giảm thiểu được Giả định sai lầm (False Assumption) nào của Peter Deutsch?

**Câu trả lời:**
Việc thực hiện Local Validation giúp giảm thiểu tác động của **Giả định số 5: "Latency is zero" (Độ trễ bằng 0)**. 
- Nếu chúng ta giả định độ trễ mạng bằng không, chúng ta sẽ tự nhiên để mọi xử lý (kể cả những kiểm tra tính hợp lệ cơ bản) cho server thực hiện. Điều này phá vỡ trải nghiệm người dùng khi phải chịu một độ trễ lớn khi truyền thông qua mạng.
- Bằng cách nhận thức được độ trễ mạng luôn tồn tại, chúng ta đã chủ động đẩy code xuống client để che giấu độ trễ (Latency Hiding). Phương pháp này giúp tránh phụ thuộc vào giao tiếp mạng (network communication) cho những tác vụ có thể giải quyết cục bộ.
