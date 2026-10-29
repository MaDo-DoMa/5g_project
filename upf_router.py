#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC "Edge vs Cloud in 5G" - UPF Router (5G Core User Plane Function emulation).

Transparent TCP proxy on 127.0.0.1:5000 (entry point for the UE/Client).
It emulates an Uplink Classifier with Application-Aware Traffic Steering:

    1. accepts the client connection,
    2. intercepts the first part of the Uplink payload (DPI / L7 inspection)
       and parses the semantic flag, e.g.:
            APP_TYPE=URLLC_SENSOR   -> steer to EDGE  server (127.0.0.1:5002)
            APP_TYPE=eMBB_VIDEO     -> steer to CLOUD server (127.0.0.1:5001)
    3. opens a new TCP connection (socket.connect) to the selected target,
       forwards the request and relays the 1 MB downlink back to the client
       in 4096-byte chunks (stored, not buffered in memory),
    4. closes both descriptors (short-lived session, like HTTP/REST).

The payload bytes are never interpreted on the downlink - the router is
transparent for the data plane after the steering decision is made.

Only the standard library is used.

Run:    python upf_router.py
"""

import re
import socket
import threading

# ====================== CONFIGURATION ======================
BIND_ADDR     = ("127.0.0.1", 5000)   # entry point for the UE (gateway / UPF N3)
EDGE_ADDR     = ("127.0.0.1", 5002)   # MEC host    - low latency branch
CLOUD_ADDR    = ("127.0.0.1", 5001)   # data center - high bandwidth branch
DEFAULT_ROUTE = CLOUD_ADDR            # unknown traffic -> cloud (safe default)
# ===========================================================

SESSION_TIMEOUT_S  = 10.0   # max socket inactivity in a single session
CLIENT_HDR_BYTES   = 4096   # DPI window: first N bytes of the Uplink payload
RELAY_CHUNK        = 4096   # downlink chunk size (streaming to the client)

# DPI rule set - L7 signature -> destination data path
UPF_PATTERN = re.compile(rb"APP_TYPE\s*=\s*([A-Za-z0-9_]+)")
ROUTES = {
    b"URLLC_SENSOR": EDGE_ADDR,   # URLLC -> Edge
    b"eMBB_VIDEO":   CLOUD_ADDR,  # eMBB  -> Cloud
}


def classify(payload: bytes):
    """Deep Packet Inspection of the Uplink: returns (flag_name, target_addr)."""
    match = UPF_PATTERN.search(payload)
    if match is None:
        return None, DEFAULT_ROUTE
    flag = match.group(1).strip()
    return flag, ROUTES.get(flag, DEFAULT_ROUTE)


def handle_client(down: socket.socket, addr) -> None:
    """Single UE session: intercept uplink -> steer -> relay downlink -> close."""
    up = None
    try:
        down.settimeout(SESSION_TIMEOUT_S)

        # --- 1) intercept the Uplink (first kilkutes of bytes are enough for DPI) ---
        uplink = down.recv(CLIENT_HDR_BYTES)
        if not uplink:
            return

        # --- 2) Application-Aware Traffic Steering (Uplink Classifier) ---
        flag, target = classify(uplink)
        traffic_class = {b"URLLC_SENSOR": "URLLC", b"eMBB_VIDEO": "eMBB"}.get(flag, "unknown")
        print(f"[upf] UE {addr[0]}:{addr[1]} APP_TYPE={(flag.decode() if flag else '(none)')} "
              f"[{traffic_class:7s}] -> steering to {target[0]}:{target[1]}", flush=True)

        # --- 3) new TCP connection to the selected server + request forwarding ---
        up = socket.create_connection(target, timeout=SESSION_TIMEOUT_S)
        up.settimeout(SESSION_TIMEOUT_S)
        up.sendall(uplink)  # pass the original request through, unchanged

        # --- 4) relay the downlink: recv 4096 B -> sendall to the client, until EOF ---
        total = 0
        while True:
            chunk = up.recv(RELAY_CHUNK)
            if not chunk:
                break                      # target closed the session (clean EOF)
            down.sendall(chunk)
            total += len(chunk)
        print(f"[upf] session done: {total:,} B relayed from "
              f"{target[0]}:{target[1]}", flush=True)
    except OSError as exc:
        print(f"[upf] session aborted: {exc}", flush=True)
    finally:
        for sock in (up, down):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # fast rebind after restart
    srv.bind(BIND_ADDR)
    srv.listen(16)
    print(f"[upf] UPF Router listening on tcp://{BIND_ADDR[0]}:{BIND_ADDR[1]} | "
          f"DPI rules: URLLC_SENSOR -> {EDGE_ADDR[1]}, eMBB_VIDEO -> {CLOUD_ADDR[1]}",
          flush=True)

    try:
        while True:
            conn, addr = srv.accept()              # blocking accept - event loop
            # one thread per UE session (serial UE in this PoC, but robust anyway)
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[upf] stopped by user (Ctrl+C).", flush=True)
    finally:
        srv.close()


if __name__ == "__main__":
    main()
