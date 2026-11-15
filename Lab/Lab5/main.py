import time
import os
import shutil
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from wal import WriteAheadLog
from participant import Participant
from coordinator import Coordinator

def run_lab5_tests():
    print("=" * 65)
    print("LAB 5: TWO-PHASE COMMIT (2PC) SIMULATOR WITH WAL & RECOVERY")
    print("Specification: 1 Coordinator (6000) | 3 Participants (6001..6003) | WAL fsync")
    print("=" * 65)
    
    data_dir = 'Lab5/data'
    # Dọn dẹp dữ liệu cũ trước khi test
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    
    # 1. Khởi động 3 Participant và 1 Coordinator
    print("\n[SETUP] Starting Coordinator and Participants P1, P2, P3...")
    participants = {
        1: Participant(pid=1, data_dir=data_dir),
        2: Participant(pid=2, data_dir=data_dir),
        3: Participant(pid=3, data_dir=data_dir)
    }
    coord = Coordinator(data_dir=data_dir)
    time.sleep(1.0)
    
    # ========================================================
    # KỊCH BẢN 1: GIAO DỊCH COMMIT BÌNH THƯỜNG (TX 101)
    # ========================================================
    print("\n" + "=" * 65)
    print("[SCENARIO 1] NORMAL COMMIT: Tx 101 (Account Balance = 500)")
    print("=" * 65)
    res1 = coord.execute_transaction(tx_id=101, data={'account': 'Alice', 'balance': 500})
    time.sleep(0.5)
    
    print("\n[VERIFY SCENARIO 1]")
    print(f"Coordinator Decision: {res1}")
    for pid, p in participants.items():
        print(f"P{pid} Data Store: {p.data_store} | Tx 101 State: {p.tx_states.get(101)}")
        assert p.tx_states.get(101) == 'COMMITTED', f"P{pid} did not commit Tx 101"
        assert p.data_store.get('balance') == 500
    print(">>> SCENARIO 1 PASSED: All participants committed Tx 101 successfully! <<<")
    
    # ========================================================
    # KỊCH BẢN 2: GIAO DỊCH BỊ ABORT DO P3 TỪ CHỐI (TX 102)
    # ========================================================
    print("\n" + "=" * 65)
    print("[SCENARIO 2] TRANSACTION ABORT: Tx 102 (P3 fails validation / rejects)")
    print("=" * 65)
    participants[3].reject_next = True
    res2 = coord.execute_transaction(tx_id=102, data={'account': 'Bob', 'balance': 999})
    time.sleep(0.5)
    
    print("\n[VERIFY SCENARIO 2]")
    print(f"Coordinator Decision: {res2}")
    for pid, p in participants.items():
        print(f"P{pid} Data Store: {p.data_store} | Tx 102 State: {p.tx_states.get(102)}")
        assert p.tx_states.get(102) == 'ABORTED', f"P{pid} did not abort Tx 102"
        assert 'Bob' not in str(p.data_store)
    print(">>> SCENARIO 2 PASSED: All participants aborted Tx 102; no data leaked! <<<")
    
    # ========================================================
    # KỊCH BẢN 3: PARTICIPANT CRASH & WAL RECOVERY (TX 103)
    # ========================================================
    print("\n" + "=" * 65)
    print("[SCENARIO 3] FAULT TOLERANCE: P2 crashes after logging PREPARED")
    print("=" * 65)
    # Cấu hình P2 tự crash ngay sau khi ghi PREPARED và gửi VOTE_COMMIT
    participants[2].fail_on_prepared = True
    
    res3 = coord.execute_transaction(tx_id=103, data={'account': 'Charlie', 'balance': 1200})
    time.sleep(0.5)
    
    print("\n[STATUS CHECK RIGHT AFTER CRASH]")
    print(f"Coordinator Decision for Tx 103: {res3}")
    print(f"P2 is alive: {participants[2].is_alive} | (P2 is currently DEAD)")
    
    print("\n--> RESTARTING PARTICIPANT P2 (Simulating Node Reboot & Recovery)...")
    # Khởi động lại P2 bằng một instance mới với cùng thư mục WAL
    recovered_p2 = Participant(pid=2, data_dir=data_dir)
    time.sleep(1.0)
    
    print("\n[VERIFY SCENARIO 3 AFTER RECOVERY]")
    print(f"Recovered P2 Data Store: {recovered_p2.data_store}")
    print(f"Recovered P2 Tx 103 State: {recovered_p2.tx_states.get(103)}")
    
    assert recovered_p2.tx_states.get(103) == 'COMMITTED', "Recovered P2 failed to commit Tx 103"
    assert recovered_p2.data_store.get('account') == 'Charlie'
    print(">>> SCENARIO 3 PASSED: P2 recovered from PREPARED via WAL & Coordinator DECISION_QUERY! <<<")
    
    # Dọn dẹp tài nguyên
    print("\nShutting down servers...")
    coord.stop()
    for p in participants.values():
        p.stop()
    recovered_p2.stop()
    print("Lab 5 Tests completed successfully!\n")

if __name__ == "__main__":
    run_lab5_tests()
