# Lab 2 - Mini-DHT Registry và Messaging Client

Hệ thống Chord DHT thu nhỏ sử dụng TCP Sockets và finger table O(log N).

## Giới thiệu

Bài lab implement giao thức Chord DHT với các tính năng chính:

- Giao tiếp giữa các node qua TCP Sockets
- Finger table O(log N) để phân giải tên phẳng (flat name resolution)
- Fault-tolerant: client vẫn tìm và nhắn tin được với node dù IP thay đổi

## Yêu cầu

Python 3.10 trở lên. Cài Flask để chạy web frontend:

    pip install flask

## Cấu trúc thư mục

    Lab2/
        chord/
            config.py        cấu hình ring size M=6, timeouts
            utils.py         hàm hash_key và in_range
            finger_table.py  lớp NodeInfo và FingerTable
            network.py       TCP RPC qua socket
            node.py          ChordNode, logic chính
        frontend/
            index.html       giao diện web
        web_app.py           server web + REST API
        run_node.py          khởi động node qua terminal (tùy chọn)
        run_client.py        client terminal (tùy chọn)
        README.md

## Hướng dẫn demo qua Web Frontend

### Bước 1 - Khởi động server

    python web_app.py

Mở trình duyệt tại: http://localhost:8080

### Bước 2 - Tạo node đầu tiên (bootstrap)

Trong giao diện web, điền tên node (ví dụ: alice) và nhấn Tạo node.
Không chọn cổng tham gia vì đây là node đầu tiên tạo ring mới.

### Bước 3 - Thêm các node khác vào ring

Điền tên node mới (bob, carol...), chọn cổng tham gia là cổng của alice.
Nhấn Tạo node. Lặp lại để thêm nhiều node.

Chờ khoảng 10 giây để ring ổn định.

### Bước 4 - Xem finger table

Nhấn vào chip tên node ở vòng tròn hoặc danh sách.
Finger table O(log N) hiển thị ở panel bên phải.
Các đường nét đứt trên vòng tròn thể hiện các finger của node được chọn.

### Bước 5 - Gửi tin nhắn

Chọn người gửi, nhập tên người nhận và nội dung, nhấn Gửi tin nhắn.
Kết quả hiển thị trong phần Event Log phía dưới.

### Bước 6 - Mô phỏng đổi địa chỉ IP (fault tolerance)

Chọn node cần đổi địa chỉ, để trống cổng mới (tự động), nhấn Mô phỏng đổi IP.
Node tự động đăng ký lại địa chỉ mới vào DHT.
Sau khoảng 10 giây, gửi tin nhắn tới node đó vẫn thành công.

## Cách thức hoạt động

### Finger table và O(log N) routing

Mỗi node quản lý M=6 finger:

    finger[i] = successor( (node_id + 2^i) mod 64 )

Khi tìm kiếm một key, thay vì hỏi từng node (O(N)), mỗi bước
chuyển tiếp đến finger gần nhất, giảm nửa không gian tìm kiếm.
Tổng số bước tối đa là M = log2(N).

### Fault tolerance

Hàm stabilize chạy mỗi 5 giây để kiểm tra và sửa successor và predecessor.
Hàm fix_fingers chạy mỗi 7 giây để cập nhật finger table.
Hàm check_predecessor phát hiện node chết và xoá khỏi ring.
Khi node thay đổi địa chỉ, nó tự động đăng ký lại tên trong DHT.
Client luôn lookup lại DHT trước khi gửi tin nên tự động lấy được địa chỉ mới.

### Giao thức RPC

Định dạng: 4 byte big-endian (độ dài) theo sau là JSON payload qua TCP.

Loại tin và mô tả:

    FIND_SUCCESSOR   Tìm successor của một ID, O(log N)
    GET_PREDECESSOR  Lấy predecessor của node
    NOTIFY           Thông báo predecessor mới
    STORE            Lưu key-value vào node chịu trách nhiệm
    LOOKUP           Tra cứu key-value
    MESSAGE          Gửi tin nhắn tới node
    PING             Kiểm tra node còn sống
    GET_INFO         Lấy trạng thái đầy đủ của node

## Lệnh trong run_node.py (tùy chọn, không cần khi dùng web)

    status     hiển thị finger table và thông tin node
    register   đăng ký lại tên vào DHT
    quit       dừng node
