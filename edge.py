#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC "Edge vs Cloud in 5G" - EDGE server (MEC host emulation).

Stateless TCP responder bound to 127.0.0.1:5002. For every accepted
connection it waits for a trigger (the request forwarded by the UPF
router), emulates the short processing overhead of an edge node
(time.sleep(0.005) = 5 ms), then pushes a fixed 1 MB downlink buffer
(sendall) and closes the connection (short-lived HTTP/REST session).

Network Delay Emulation:
    edge  ->   5 ms  (processing node close to the gNB)
    cloud ->  50 ms  (RTT to a remote data center, see cloud.py)

Only the standard library is used.

Run:    python edge.py
"""

import socket
import threading
import time

# ====================== CONFIGURATION ======================
SERVER_IP           = "127.0.0.1"   # loopback - logical node separation via port only
SERVER_PORT         = 5002          # EDGE endpoint (UPF steers URLLC here)
PROCESSING_DELAY_S  = 0.005         # 5 ms - edge processing/uplink delay emulation
PAYLOAD_MB          = 1             # downlink payload size (1 MB = 1024*1024 B)
# ===========================================================

RECV_TIMEOUT_S  = 5.0     # max waiting for the trigger from the UPF
DRAIN_TIMEOUT_S = 0.2     # grace period while closing (protection against RST)


def handle_client(conn: socket.socket, payload: bytes) -> None:
    """Single connection lifecycle: trigger -> delay -> payload -> FIN -> close."""
    addr = None
    try:
        addr = conn.getpeername()

        # 1) wait for the request (trigger) from the UPF router
        conn.settimeout(RECV_TIMEOUT_S)
        if not conn.recv(4096):
            return  # peer closed the connection - nothing to send

        # 2) KEY ELEMENT: distance/propagation emulation
        time.sleep(PROCESSING_DELAY_S)

        # 3) downlink payload: sendall guarantees the whole buffer is queued
        conn.sendall(payload)

        # 4) graceful close: FIN first, then drain leftovers,
        #    so the sender always receives all data and a clean EOF
        conn.shutdown(socket.SHUT_WR)
        try:
            conn.settimeout(DRAIN_TIMEOUT_S)
            while conn.recv(4096):
                pass
        except socket.timeout:
            pass
    except OSError:
        pass  # any network error - this one connection is just dropped
    finally:
        if addr is not None:
            print(f"[edge] served {addr[0]}:{addr[1]} -> {len(payload):,} B "
                  f"(delay {PROCESSING_DELAY_S * 1000:.0f} ms)", flush=True)
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
    print(f"[edge] EDGE server listening on tcp://{SERVER_IP}:{SERVER_PORT} | "
          f"delay = {PROCESSING_DELAY_S * 1000:.0f} ms | "
          f"payload = {PAYLOAD_MB} MB ({len(payload):,} B)", flush=True)

    try:
        while True:
            conn, addr = srv.accept()              # blocking accept - event loop
            # one short-lived thread per connection
            threading.Thread(target=handle_client, args=(conn, payload), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[edge] stopped by user (Ctrl+C).", flush=True)
    finally:
        srv.close()


if __name__ == "__main__":
    main()
