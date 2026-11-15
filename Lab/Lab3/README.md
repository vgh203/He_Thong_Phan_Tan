# Lab 3 - Logical Clock Simulator

Bài lab này thực hiện mô phỏng đồng hồ logic (Lamport Clock và Vector Clock) trong hệ thống phân tán.

## Yêu cầu của bài Lab
- **Kiến trúc**: Triển khai 3 luồng (threads) tiến trình ($P_0, P_1, P_2$) chạy song song, giao tiếp với nhau qua các hàng đợi an toàn cho luồng (thread-safe queues).
- **Cấu trúc dữ liệu đồng hồ**:
  1. Bộ đếm số nguyên vô hướng (Scalar integer counter) cho Lamport clocks.
  2. Mảng số nguyên kích thước 3 (size 3 array) cho Vector clocks.
- **Vòng lặp sự kiện mô phỏng**: Mỗi luồng (thread) sẽ thực thi ngẫu nhiên một trong các sự kiện sau:
  1. *Sự kiện tính toán nội bộ (Internal event)*: Chỉ tăng đồng hồ nội bộ.
  2. *Sự kiện gửi tin nhắn (Message send event)*: Đính kèm timestamp hiện tại vào tin nhắn và đẩy vào queue của tiến trình đích.
  3. *Sự kiện nhận tin nhắn (Message receive event)*: Lấy tin nhắn từ queue, thực hiện gộp (merge) giá trị max của từng thành phần trong vector clock.
- **Phát hiện xung đột đồng thời (Concurrency Detection)**: Tự động in log ra màn hình khi phát hiện Vector Clock nhận được có sự xung đột đồng thời (concurrent conflict) với Vector Clock hiện tại của tiến trình.

## Cách chạy
1. Đảm bảo bạn đã cài đặt Python 3.
2. Mở terminal trong thư mục `Lab3`.
3. Chạy lệnh:
   ```bash
   python clock_simulator.py
   ```
4. Quan sát log in ra màn hình để xem các tiến trình cập nhật đồng hồ và phát hiện xung đột.
