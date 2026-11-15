import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from replica import ServerReplica
from proxy import ClientSessionProxy

def run_lab7_simulation():
    print("=" * 65)
    print("LAB 7: CLIENT-CENTRIC CONSISTENCY SESSION PROXY SIMULATOR")
    print("Specification: Monotonic Reads & Read-Your-Writes Enforcement")
    print("Reference: Lect07 Slide 37-38")
    print("=" * 65)
    
    # 1. Khởi tạo 3 Replica Server: S1, S2, S3
    print("\n[SETUP] Initializing 3 Replicated Data Stores: S1, S2, S3...")
    replicas = {
        1: ServerReplica(server_id=1, total_servers=3),
        2: ServerReplica(server_id=2, total_servers=3),
        3: ServerReplica(server_id=3, total_servers=3)
    }
    proxy = ClientSessionProxy(replicas)
    
    client_id = "Client_Mobile_User_1"
    
    # ========================================================
    # TEST 1: CHẠY TRACE LOG MẪU TRÊN SLIDE 38 (READ-YOUR-WRITES)
    # ========================================================
    print("\n" + "=" * 65)
    print("[TEST 1] VERIFYING SLIDE 38 EXECUTION TRACE (Read-Your-Writes)")
    print("=" * 65)
    
    # Client ghi dữ liệu vào Server S1
    proxy.write(client_id, target_server_id=1, key="Profile Name", value="Alice", op_label="W1")
    
    # Client di chuyển và gửi yêu cầu Đọc tới Server S2 (Server S2 lúc này chưa nhận được sync, clock = (0,0,0))
    val1 = proxy.read(client_id, target_server_id=2, key="Profile Name", op_label="R1")
    assert val1 == "Alice", f"Expected 'Alice', got {val1}"
    
    # ========================================================
    # TEST 2: KIỂM ĐỊNH CAM KẾT MONOTONIC READS
    # ========================================================
    print("\n" + "=" * 65)
    print("[TEST 2] VERIFYING MONOTONIC READS ACROSS REPLICAS")
    print("=" * 65)
    
    # Server S1 có thêm một bản cập nhật từ nguồn khác
    print("[SYSTEM] External event: Updating 'Status' to 'Online' directly on Server S1...")
    replicas[1].apply_write(key="Status", value="Online", op_id="W_Ext_1")
    
    # Client đọc trạng thái mới từ S1 -> Session V_read được cập nhật
    val2 = proxy.read(client_id, target_server_id=1, key="Status", op_label="R2")
    assert val2 == "Online"
    
    # Sau đó Client di chuyển và gửi yêu cầu Đọc tới Server S3 (S3 clock vẫn đang là (0,0,0) chưa sync)
    print("\n[CLIENT] Client roams to another cell and queries stale Server S3...")
    val3 = proxy.read(client_id, target_server_id=3, key="Status", op_label="R3")
    assert val3 == "Online", f"Expected 'Online', got {val3}"
    
    print("\n" + "=" * 65)
    print("FINAL REPLICA STATE SUMMARY:")
    for sid, r in replicas.items():
        print(f"Replica S{sid} -> Vector Clock: {tuple(r.clock)} | Store: {r.store}")
    print("=" * 65)
    print(">>> ALL TESTS PASSED: Client-Centric Session Proxy guarantees successfully preserved! <<<\n")

if __name__ == "__main__":
    run_lab7_simulation()
