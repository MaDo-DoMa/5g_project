#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Edge vs Cloud PoC - stateless TCP payload server.

Behavior:
    accept connection -> receive any string (trigger)
    -> send back exactly one fixed-size packet (default: 1 MB of zero bytes)
    -> close connection.

The client is fully responsible for the measurement - the server only
"serves" the payload, so the Edge and Cloud instances are identical.
Only the standard library is used (no external packages required).

Run:    python server.py
"""

import socket
import threading

# ====================== CONFIGURATION ======================
SERVER_IP   = "0.0.0.0"   # bind address ("0.0.0.0" = all interfaces)
SERVER_PORT = 5001        # TCP port for clients
PAYLOAD_MB  = 1           # size of the sent payload in MB (1 MB = 1024*1024 B)
# ===========================================================

RECV_TIMEOUT_S  = 5.0     # max waiting for the trigger from the client
DRAIN_TIMEOUT_S = 0.2     # grace period while closing (protection against RST)


def handle_client(conn: socket.socket, payload: bytes) -> None:
    """Single connection lifecycle: trigger -> payload -> FIN -> close."""
    try:
        # 1) wait for any string from the client (trigger)
        conn.settimeout(RECV_TIMEOUT_S)
        if not conn.recv(4096):
            return  # client closed the connection - nothing to send

        # 2) send back the full payload (sendall ensures all bytes are queued)
        conn.sendall(payload)

        # 3) graceful close: send FIN first, then drain leftovers,
        #    so the client always receives all data and a clean EOF
        conn.shutdown(socket.SHUT_WR)
        try:
            conn.settimeout(DRAIN_TIMEOUT_S)
            while conn.recv(4096):
                pass
        except socket.timeout:
            pass  # client simply did not close within the grace period
    except OSError:
        pass  # any network error - this one connection is just dropped
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main() -> None:
    payload = b"\x00" * (PAYLOAD_MB * 1024 * 1024)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # fast rebind after restart
    srv.bind((SERVER_IP, SERVER_PORT))
    srv.listen(16)
    print(f"[server] listening on {SERVER_IP}:{SERVER_PORT} | payload = {PAYLOAD_MB} MB ({len(payload):,} B)",
          flush=True)

    try:
        while True:
            conn, addr = srv.accept()
            # one short-lived thread per connection - simple and robust
            threading.Thread(target=handle_client, args=(conn, payload), daemon=True).start()
            print(f"[server] accepted request from {addr[0]}:{addr[1]} -> will send {len(payload):,} B", flush=True)
    except KeyboardInterrupt:
        print("\n[server] stopped by user (Ctrl+C).", flush=True)
    finally:
        srv.close()


if __name__ == "__main__":
    main()
