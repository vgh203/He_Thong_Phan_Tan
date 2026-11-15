import time
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from node import BullyNode

def run_lab4_simulation():
    print("=" * 65)
    print("LAB 4: DISTRIBUTED LEADER ELECTION SIMULATOR (BULLY ALGORITHM)")
    print("Specification: 5 Nodes (P1-P5) | Sockets TCP | Heartbeat Timeout | Leader Failover")
    print("=" * 65)
    
    # 1. Khởi động 5 node trên localhost
    print("\n[PHASE 1] Initializing 5 Nodes (P1..P5) on ports 5001..5005...")
    nodes = []
    for i in range(1, 6):
        node = BullyNode(node_id=i, host='127.0.0.1', base_port=5000, total_nodes=5)
        nodes.append(node)
        time.sleep(0.1)
        
    print("\nWaiting for initial cluster stability (All nodes pointing to Leader P5)...")
    time.sleep(2.0)
    
    print("\n[INITIAL STATE CHECK]")
    for n in nodes:
        print(f"Node P{n.node_id} -> Current Leader: P{n.leader_id} | State: {n.state}")
        
    # 2. Giả lập Leader P5 bị chết (crash)
    print("\n" + "=" * 65)
    print("[PHASE 2] SIMULATING LEADER FAILURE: Killing Node P5...")
    print("=" * 65)
    nodes[4].crash()  # P5 crash
    
    # 3. Quan sát quá trình phát hiện lỗi qua Heartbeat và Thuật toán Bully
    print("\nWatching election unfold across nodes...")
    time.sleep(6.0)
    
    # 4. Kiểm tra trạng thái hội tụ sau bầu cử
    print("\n" + "=" * 65)
    print("[FINAL STATE VERIFICATION]")
    print("=" * 65)
    all_converged = True
    for n in nodes[:4]: # P1..P4
        is_p4 = (n.leader_id == 4)
        print(f"Living Node P{n.node_id} -> Leader: P{n.leader_id} | State: {n.state} | OK: {is_p4}")
        if not is_p4:
            all_converged = False
            
    print(f"Dead Node P5 -> is_alive: {nodes[4].is_alive} | State: {nodes[4].state}")
    
    if all_converged:
        print("\n>>> TEST PASSED: All living nodes (P1..P4) successfully elected and converged on P4 as new Leader! <<<")
    else:
        print("\n>>> TEST FAILED: Nodes did not converge on P4. <<<")
        
    # 5. Dọn dẹp tài nguyên
    print("\nShutting down nodes...")
    for n in nodes:
        n.stop()
    print("Lab 4 Simulation completed.\n")

if __name__ == "__main__":
    run_lab4_simulation()
