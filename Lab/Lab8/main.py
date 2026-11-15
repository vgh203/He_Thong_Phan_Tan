import sys
import time
import multiprocessing as mp

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from gossip import run_replica, Cluster, N, BASE_PORT, call

class ConsoleCluster(Cluster):
    """Cluster subclass that outputs important event logs directly to console."""
    def log(self, kind, text):
        super().log(kind, text)
        if kind in ("client", "replica", "gossip", "system", "error"):
            print(text, flush=True)

def run_lab8_simulation():
    print("=" * 65)
    print("LAB 8: DISTRIBUTED GOSSIP PROTOCOL & QUORUM KV STORE SIMULATOR")
    print("Specification: Gifford Quorum (NR=3, NW=3) | Push-Pull Anti-Entropy | Tombstones")
    print("Reference: Lect08 Slide 36-38")
    print("=" * 65)

    logq = mp.Queue()
    procs = [mp.Process(target=run_replica, args=(i, logq), daemon=True) for i in range(1, N + 1)]
    for p in procs:
        p.start()
    time.sleep(1.0)

    cl = ConsoleCluster(logq)
    cl.start_threads()
    
    print(f"\n[SETUP] 5 replica server processes started (S1..S5, TCP ports {BASE_PORT}-{BASE_PORT + N - 1}).\n")
    
    # Cấu hình Quorum NW=3, NR=3, chọn replica tuần tự
    cl.cfg.update(nr=3, nw=3, select="sequential")
    cl.set_config({})
    time.sleep(0.5)

    print("=" * 65)
    print("[PHASE 1] QUORUM WRITE & ANTI-ENTROPY GOSSIP CONVERGENCE")
    print("=" * 65)
    cl.write("user1", "Bob")
    cl._wait("user1", secs=15)
    time.sleep(1.0)

    print("\n" + "=" * 65)
    print("[PHASE 2] DISTRIBUTED DELETION VIA TOMBSTONES")
    print("=" * 65)
    cl.write("user1", None, tombstone=True)
    cl._wait("user1", secs=15)
    time.sleep(1.0)

    print("\n" + "=" * 65)
    print("[FINAL STATE VERIFICATION ACROSS ALL REPLICAS]")
    print("=" * 65)
    all_converged = True
    for i in range(1, N + 1):
        dump = call(i, {"op": "DUMP"})
        if dump and dump.get("ok"):
            entry = dump["store"].get("user1")
            is_tomb = entry.get("is_tombstone") if entry else False
            ver = entry.get("version") if entry else 0
            print(f"Replica S{i} -> key='user1' | Version: {ver} | Is Tombstone: {is_tomb}")
            if not is_tomb or ver != 2:
                all_converged = False
        else:
            print(f"Replica S{i} -> Unreachable!")
            all_converged = False

    if all_converged:
        print("\n>>> TEST PASSED: All 5 replicas successfully converged via Quorum & Tombstone gossip! <<<")
    else:
        print("\n>>> TEST FAILED: Replicas did not converge properly. <<<")

    print("\nShutting down replica processes...")
    for p in procs:
        p.terminate()
    print("Lab 8 Simulation completed.\n")

if __name__ == "__main__":
    mp.freeze_support()
    run_lab8_simulation()
