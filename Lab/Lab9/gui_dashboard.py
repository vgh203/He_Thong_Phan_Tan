"""
Native Desktop GUI Dashboard for Secure RPC & KDC Authentication Proxy Simulator
Lecture 09 (Slides 39-40)
Built with Python's built-in Tkinter & ttk (No external dependencies needed).
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time

from common import (
    KDC_HOST,
    KDC_PORT,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_NONCE_RA,
    DEFAULT_NONCE_RB,
)
from kdc import KDCDaemon
from server import SecureResourceServer
from rpc_proxy import SecureRPCProxy


class SecureRPCDashboardApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure RPC & KDC Authentication Proxy Simulator - Dashboard")
        self.root.geometry("1100x750")
        self.root.minsize(900, 650)
        self.root.configure(bg="#0f172a")

        # Global Instances
        self.kdc = None
        self.server = None
        self.proxy = None

        self._init_style()
        self._build_ui()
        self.start_backend_services()

    def _init_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#1e293b", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#0f172a", foreground="#f8fafc", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#38bdf8")
        style.configure("CardTitle.TLabel", background="#1e293b", font=("Segoe UI", 11, "bold"), foreground="#38bdf8")
        style.configure("CardText.TLabel", background="#1e293b", font=("Consolas", 9), foreground="#cbd5e1")
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), foreground="#fbbf24")

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        lbl_title = ttk.Label(header_frame, text="🔐 Secure RPC & KDC Authentication Proxy Simulator", style="Header.TLabel")
        lbl_title.pack(side=tk.LEFT)
        lbl_sub = ttk.Label(header_frame, text="Lecture 09 (Needham-Schroeder, AES-256-CBC, HMAC-SHA256, Anti-Replay)", font=("Segoe UI", 9), foreground="#94a3b8")
        lbl_sub.pack(side=tk.RIGHT, pady=4)

        # Status Cards Frame (Top)
        cards_frame = ttk.Frame(main_frame)
        cards_frame.pack(fill=tk.X, pady=(0, 15))

        # KDC Card
        card_kdc = ttk.Frame(cards_frame, style="Card.TFrame", padding=10)
        card_kdc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        ttk.Label(card_kdc, text="🔑 KDC Daemon (Port 9001)", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.lbl_kdc_status = ttk.Label(card_kdc, text="Status: Online\nMaster Keys: K_A, K_B Active\nSession Key: None", style="CardText.TLabel")
        self.lbl_kdc_status.pack(anchor=tk.W, pady=4)

        # Server Card
        card_srv = ttk.Frame(cards_frame, style="Card.TFrame", padding=10)
        card_srv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        ttk.Label(card_srv, text="🖥️ Server_Bob (Port 9002)", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.lbl_srv_status = ttk.Label(card_srv, text="Status: Online\nBalance: 0\nNonces Tracked: 0", style="CardText.TLabel")
        self.lbl_srv_status.pack(anchor=tk.W, pady=4)

        # Client Card
        card_cli = ttk.Frame(cards_frame, style="Card.TFrame", padding=10)
        card_cli.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        ttk.Label(card_cli, text="👤 Client (Alice)", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.lbl_cli_status = ttk.Label(card_cli, text="Status: Ready\nChannel: Disconnected\nLast Nonce: None", style="CardText.TLabel")
        self.lbl_cli_status.pack(anchor=tk.W, pady=4)

        # Middle Content Frame
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Left Column: Action Controls
        ctrl_frame = ttk.Frame(content_frame, width=380)
        ctrl_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))

        # 1-Click Runner
        btn_run_all = tk.Button(
            ctrl_frame, text="⚡ Run Full Slide 40 Flow & Attacks",
            bg="#0284c7", fg="white", font=("Segoe UI", 10, "bold"), relief="flat",
            command=self.run_full_sequence_async, height=2
        )
        btn_run_all.pack(fill=tk.X, pady=(0, 10))

        # Step 1 & 2: KDC
        ttk.Label(ctrl_frame, text="1. KDC Authentication (Needham-Schroeder)", style="Section.TLabel").pack(anchor=tk.W, pady=(5, 2))
        btn_kdc = tk.Button(ctrl_frame, text="🔑 Step 1-2: Request Ticket (R_A=84920)", bg="#7c3aed", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=self.step_kdc_auth)
        btn_kdc.pack(fill=tk.X, pady=2)

        # Step 3-5: Server Handshake
        btn_hs = tk.Button(ctrl_frame, text="🤝 Step 3-5: Handshake with Bob (R_B=10492)", bg="#059669", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=self.step_server_handshake)
        btn_hs.pack(fill=tk.X, pady=2)

        # Step 6: Secure RPC Calls
        ttk.Label(ctrl_frame, text="2. Secure RPC Invocation (AES-CBC + HMAC)", style="Section.TLabel").pack(anchor=tk.W, pady=(10, 2))
        btn_rpc_write = tk.Button(ctrl_frame, text="🚀 Execute Write('Balance', 500)", bg="#16a34a", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=lambda: self.execute_rpc("Write", "Balance", 500))
        btn_rpc_write.pack(fill=tk.X, pady=2)

        btn_rpc_read = tk.Button(ctrl_frame, text="📖 Execute Read('Balance')", bg="#0d9488", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=lambda: self.execute_rpc("Read", "Balance"))
        btn_rpc_read.pack(fill=tk.X, pady=2)

        # Step 7: Attacks & Security
        ttk.Label(ctrl_frame, text="3. Security & Anti-Replay Mitigation", style="Section.TLabel").pack(anchor=tk.W, pady=(10, 2))
        btn_replay = tk.Button(ctrl_frame, text="🚨 Attack: Replay Previous RPC Packet", bg="#d97706", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=self.attack_replay)
        btn_replay.pack(fill=tk.X, pady=2)

        btn_tamper = tk.Button(ctrl_frame, text="⚠️ Attack: Tamper Ciphertext (HMAC Test)", bg="#dc2626", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", command=self.attack_tamper)
        btn_tamper.pack(fill=tk.X, pady=2)

        # Reset button
        btn_reset = tk.Button(ctrl_frame, text="🔄 Reset All State", bg="#475569", fg="white", font=("Segoe UI", 9), relief="flat", command=self.reset_all)
        btn_reset.pack(fill=tk.X, pady=(15, 0))

        # Right Column: Console Log
        console_frame = ttk.Frame(content_frame)
        console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(console_frame, text="💻 Synchronized Console Trace Log (Matching Slide 40)", font=("Segoe UI", 10, "bold"), foreground="#38bdf8").pack(anchor=tk.W, pady=(0, 4))
        self.txt_console = scrolledtext.ScrolledText(
            console_frame, bg="#090d16", fg="#f1f5f9",
            font=("Consolas", 10), insertbackground="white", wrap=tk.WORD
        )
        self.txt_console.pack(fill=tk.BOTH, expand=True)

        # Console Color Tags
        self.txt_console.tag_config("CLIENT", foreground="#38bdf8")
        self.txt_console.tag_config("KDC", foreground="#c084fc")
        self.txt_console.tag_config("SERVER", foreground="#4ade80")
        self.txt_console.tag_config("REPLAY", foreground="#fb923c", background="#3b1b0b")
        self.txt_console.tag_config("VIOLATION", foreground="#f87171", background="#450a0a")
        self.txt_console.tag_config("SYSTEM", foreground="#94a3b8")

        # Bottom Frame: Packet Inspector
        inspector_frame = ttk.Frame(main_frame, style="Card.TFrame", padding=10)
        inspector_frame.pack(fill=tk.X)
        ttk.Label(inspector_frame, text="🔍 Cryptographic Packet Inspector (Last RPC Packet)", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.lbl_inspector = ttk.Label(
            inspector_frame,
            text="Payload: None | HMAC: None | Nonce: None | Mode: AES-256-CBC with PKCS7",
            style="CardText.TLabel"
        )
        self.lbl_inspector.pack(anchor=tk.W, pady=2)

    def log(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, msg):
        tag = "SYSTEM"
        if "[CLIENT]" in msg:
            tag = "CLIENT"
        elif "[KDC]" in msg:
            tag = "KDC"
        elif "[SERVER]" in msg:
            tag = "SERVER"
        elif "[REPLAY ATTACK DETECTED]" in msg:
            tag = "REPLAY"
        elif "[INTEGRITY VIOLATION]" in msg:
            tag = "VIOLATION"

        self.txt_console.insert(tk.END, msg + "\n", tag)
        self.txt_console.see(tk.END)
        self._update_status_display()

    def start_backend_services(self):
        self.kdc = KDCDaemon(host=KDC_HOST, port=KDC_PORT)
        threading.Thread(target=self.kdc.start, daemon=True).start()

        self.server = SecureResourceServer(host=SERVER_HOST, port=SERVER_PORT)
        threading.Thread(target=self.server.start, daemon=True).start()

        self.proxy = SecureRPCProxy(
            kdc_host=KDC_HOST, kdc_port=KDC_PORT,
            server_host=SERVER_HOST, server_port=SERVER_PORT
        )
        self.log("[SYSTEM] KDC Daemon and Secure Resource Server initialized on 9001 and 9002.")

    def _update_status_display(self):
        bal = self.server.resources.get("Balance", 0) if self.server else 0
        seen_count = len(self.server.seen_nonces) if self.server else 0
        k_ab = self.proxy.session_key.hex()[:16] + "..." if (self.proxy and self.proxy.session_key) else "None"
        channel_status = "AES-256-CBC Active" if (self.proxy and self.proxy.is_connected) else "Disconnected"

        self.lbl_srv_status.config(text=f"Status: Online\nBalance: {bal}\nNonces Tracked: {seen_count}")
        self.lbl_kdc_status.config(text=f"Status: Online\nMaster Keys: K_A, K_B Active\nSession Key: {k_ab}")
        self.lbl_cli_status.config(text=f"Status: Ready\nChannel: {channel_status}\nLast Nonce: {self.proxy.last_sent_packet.get('nonce', 'None') if self.proxy and self.proxy.last_sent_packet else 'None'}")

    def step_kdc_auth(self):
        def worker():
            try:
                self.proxy.authenticate_with_kdc(nonce_a=DEFAULT_NONCE_RA)
            except Exception as e:
                self.log(f"[CLIENT ERROR] KDC Auth Failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def step_server_handshake(self):
        def worker():
            try:
                self.proxy.establish_channel_with_server(challenge_hint=DEFAULT_NONCE_RB)
            except Exception as e:
                self.log(f"[CLIENT ERROR] Server Handshake Failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def execute_rpc(self, method, *args):
        def worker():
            try:
                res = self.proxy.call(method, *args)
                self.log(f"[CLIENT] RPC Result: {res.get('result')}")
                if self.proxy.last_sent_packet:
                    p = self.proxy.last_sent_packet
                    self.root.after(0, lambda: self.lbl_inspector.config(
                        text=f"Ciphertext: {p['payload'][:30]}... | HMAC: {p['hmac'][:24]}... | Status: Verified OK"
                    ))
            except Exception as e:
                self.log(f"[CLIENT ERROR] RPC Failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def attack_replay(self):
        def worker():
            try:
                res = self.proxy.replay_last_rpc()
                self.log(f"[CLIENT] Server Response to Replay: {res}")
            except Exception as e:
                self.log(f"[CLIENT ERROR] Replay test failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def attack_tamper(self):
        def worker():
            try:
                res = self.proxy.send_tampered_rpc("Write", "Balance", 999999)
                self.log(f"[CLIENT] Server Response to Tamper: {res}")
            except Exception as e:
                self.log(f"[CLIENT ERROR] Tamper test failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def run_full_sequence_async(self):
        def worker():
            try:
                self.log("\n>>> STARTING AUTOMATED SEQUENCE (SLIDE 40 TRACE) <<<")
                time.sleep(0.3)
                self.proxy.authenticate_with_kdc(nonce_a=DEFAULT_NONCE_RA)
                time.sleep(0.4)
                self.proxy.establish_channel_with_server(challenge_hint=DEFAULT_NONCE_RB)
                time.sleep(0.4)
                self.proxy.Write("Balance", 500)
                time.sleep(0.4)
                self.proxy.Read("Balance")
                time.sleep(0.5)

                self.log("\n--- ATTACK TEST 1: REPLAY OLD RPC PACKET ---")
                self.proxy.replay_last_rpc()
                time.sleep(0.5)

                self.log("\n--- ATTACK TEST 2: MITM CIPHERTEXT TAMPERING ---")
                self.proxy.send_tampered_rpc("Write", "Balance", 999999)
                self.log(">>> AUTOMATED SEQUENCE COMPLETE <<<\n")
            except Exception as e:
                self.log(f"[ERROR IN RUN-ALL] {e}")
        threading.Thread(target=worker, daemon=True).start()

    def reset_all(self):
        self.txt_console.delete("1.0", tk.END)
        if self.server:
            self.server.resources = {"Balance": 0}
            self.server.seen_nonces.clear()
        if self.proxy:
            self.proxy.close()
            self.proxy = SecureRPCProxy(
                kdc_host=KDC_HOST, kdc_port=KDC_PORT,
                server_host=SERVER_HOST, server_port=SERVER_PORT
            )
        self.lbl_inspector.config(text="Payload: None | HMAC: None | Nonce: None | Mode: AES-256-CBC with PKCS7")
        self.log("[SYSTEM] All states, nonces, and session keys reset.")
        self._update_status_display()


if __name__ == "__main__":
    root = tk.Tk()
    app = SecureRPCDashboardApp(root)
    root.mainloop()

