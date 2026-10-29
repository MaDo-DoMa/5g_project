#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC "Edge vs Cloud in 5G" - UE Client (terminal device simulator + probe).

Traffic generator: for each traffic profile (URLLC Sensor, eMBB Video) it
performs REQUESTS queries to the UPF Router on 127.0.0.1:5000, embedding
the semantic flag in the Uplink payload (APP_TYPE=...). The UPF decides
where to steer the traffic - the client never connects to the servers
directly, exactly like a real 5G user plane.

Measured per query (time.perf_counter for high resolution):

    LATENCY [ms]     : t(send request) -> t(first received byte)
                       (RTT + server delay - URLLC-relevant metric)
    THROUGHPUT [Mbps]: (payload size in megabits) /
                       t(send request) -> t(last byte of the 1 MB buffer)

Every result is appended (append mode) to telemetry.csv with columns:
    timestamp, profile_type, latency_ms, throughput_mbps

Only the standard library is used.

Run:    python ue_client.py
"""

import argparse
import csv
import os
import socket
import time
from datetime import datetime

# ====================== CONFIGURATION ======================
UPF_PORT         = 5000    # UPF Router entry point (can be overridden via flags)
UPF_HOST         = "127.0.0.1"
REQUESTS         = 50      # queries per traffic profile
PAYLOAD_MB       = 1       # expected downlink size - only for verification
SOCKET_TIMEOUT_S = 10.0    # max time for connect/recv in a single query
RECV_BUF         = 65536   # receive chunk size on the UE side
RETRIES          = 3       # attempts per query (resistance to session glitches)
CSV_FILE         = "telemetry.csv"
# ===========================================================

# traffic profiles: (csv label, L7 flag embedded in the Uplink)
PROFILES = (
    ("URLLC_Sensor", b"APP_TYPE=URLLC_SENSOR"),   # -> UPF steers to EDGE
    ("eMBB_Video",   b"APP_TYPE=eMBB_VIDEO"),     # -> UPF steers to CLOUD
)


def measure_once(profile_name: str, request: bytes, expected_bytes: int, host: str, port: int):
    """One query through the UPF. Returns (latency_ms, throughput_mbps, total_bytes)."""
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_S) as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # disable Nagle - pure latency

        # --- request with the APP_TYPE flag (uplink trigger for DPI) ---
        t_send = time.perf_counter()
        sock.sendall(request)

        # --- FIRST received byte -> latency ---
        first = sock.recv(RECV_BUF)
        t_first = time.perf_counter()
        if not first:
            raise ConnectionError("session closed without any downlink data")
        latency_ms = (t_first - t_send) * 1000.0

        # --- LAST byte of the buffer (server FIN => EOF) -> throughput end point ---
        total = len(first)
        while True:
            chunk = sock.recv(RECV_BUF)
            if not chunk:
                break
            total += len(chunk)
        t_last = time.perf_counter()

    if total != expected_bytes:
        print(f"  [!] {profile_name}: received {total:,} B, expected {expected_bytes:,} B "
              f"(PAYLOAD_MB mismatch between UE / UPF / server?)", flush=True)

    session_s = max(t_last - t_send, 1e-9)  # protection against division by zero
    throughput_mbps = (total * 8.0) / session_s / 1e6  # bytes -> bits -> Mbps
    return latency_ms, throughput_mbps, total


def measure_with_retry(profile_name: str, request: bytes, expected_bytes: int, host: str, port: int):
    """Runs measure_once() with retries; returns None if the path keeps failing."""
    for attempt in range(1, RETRIES + 1):
        try:
            return measure_once(profile_name, request, expected_bytes, host, port)
        except OSError as exc:  # timeout, connection refused, reset...
            print(f"  [!] {profile_name} attempt {attempt}/{RETRIES} failed: {exc}", flush=True)
            if attempt < RETRIES:
                time.sleep(1.0)
    return None


def append_row(row) -> None:
    """Appends a single row to the CSV (creates the file with a header on first use)."""
    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "profile_type", "latency_ms", "throughput_mbps"])
        writer.writerow(row)


def run_loop(args) -> None:
    global CSV_FILE
    CSV_FILE = args.csv  # override the output path if changed via flags
    expected_bytes = args.size_mb * 1024 * 1024

    print(f"UPF Router: {args.host}:{args.port} | {args.requests} queries per profile "
          f"| results -> {CSV_FILE}\n", flush=True)

    # outer loop: traffic profiles (URLLC first, then eMBB)
    for profile_name, request in PROFILES:
        print(f"=== Profile: {profile_name} (flag: {request.decode()}) ===", flush=True)

        # inner loop: N measurement queries
        for i in range(1, args.requests + 1):
            result = measure_with_retry(profile_name, request, expected_bytes, args.host, args.port)
            ts = datetime.now().isoformat(timespec="seconds")

            if result is None:
                # path unreachable in this iteration -> still keep the sample structure
                append_row([ts, profile_name, "", ""])
                print(f"  [{i:3d}/{args.requests}] FAILED (written as an empty row)", flush=True)
                continue

            latency_ms, throughput_mbps, _ = result
            append_row([ts, profile_name, f"{latency_ms:.3f}", f"{throughput_mbps:.2f}"])
            print(f"  [{i:3d}/{args.requests}] "
                  f"latency = {latency_ms:8.2f} ms | throughput = {throughput_mbps:10.2f} Mbps", flush=True)

    print(f"\nDone. Results appended to: {CSV_FILE} | now run:  python data_viz.py", flush=True)


def parse_args():
    p = argparse.ArgumentParser(description="UE measurement client (queries go through the UPF Router).")
    p.add_argument("host", nargs="?", default=UPF_HOST,
                   help=f"UPF Router host (default: {UPF_HOST})")
    p.add_argument("--port", type=int, default=UPF_PORT, help=f"UPF Router port (default: {UPF_PORT})")
    p.add_argument("--requests", type=int, default=REQUESTS, help=f"queries per profile (default: {REQUESTS})")
    p.add_argument("--size-mb", type=int, default=PAYLOAD_MB,
                   help=f"expected payload size in MB for verification (default: {PAYLOAD_MB})")
    p.add_argument("--csv", default=CSV_FILE, help=f"output CSV file (default: {CSV_FILE})")
    return p.parse_args()


if __name__ == "__main__":
    run_loop(parse_args())
