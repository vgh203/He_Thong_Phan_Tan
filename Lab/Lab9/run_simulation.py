"""
Simulation Runner for Secure RPC & KDC Authentication Proxy Simulator
Orchestrates all 3 socket processes:
1. KDC Daemon (Process 1)
2. Secure Resource Server (Process 2)
3. Client App (Process 3)
"""

import subprocess
import sys
import time
import os
import threading

PYTHON_EXEC = sys.executable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def pipe_output(proc, stream_name):
    """Continuously reads from a process's stdout and prints to terminal immediately."""
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
    except Exception:
        pass


def main():
    print("=" * 75, flush=True)
    print("   SECURE RPC & KDC AUTHENTICATION PROXY SIMULATOR - DEMO RUNNER   ", flush=True)
    print("=" * 75, flush=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    kdc_proc = None
    server_proc = None

    try:
        # 1. Start KDC Daemon (Process 1)
        kdc_proc = subprocess.Popen(
            [PYTHON_EXEC, "-u", os.path.join(BASE_DIR, "kdc.py")],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        t_kdc = threading.Thread(target=pipe_output, args=(kdc_proc, "KDC"), daemon=True)
        t_kdc.start()
        time.sleep(0.5)

        # 2. Start Secure Resource Server (Process 2)
        server_proc = subprocess.Popen(
            [PYTHON_EXEC, "-u", os.path.join(BASE_DIR, "server.py")],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        t_srv = threading.Thread(target=pipe_output, args=(server_proc, "SERVER"), daemon=True)
        t_srv.start()
        time.sleep(0.5)

        # 3. Run Client App (Process 3)
        client_proc = subprocess.run(
            [PYTHON_EXEC, "-u", os.path.join(BASE_DIR, "client.py")],
            cwd=BASE_DIR,
            text=True,
            env=env,
        )

        time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[RUNNER] Interrupted by user.", flush=True)
    finally:
        # Terminate background daemon processes
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=1)
            except Exception:
                server_proc.kill()

        if kdc_proc:
            kdc_proc.terminate()
            try:
                kdc_proc.wait(timeout=1)
            except Exception:
                kdc_proc.kill()

        print("[RUNNER] All background processes stopped cleanly.", flush=True)


if __name__ == "__main__":
    main()
