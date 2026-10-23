#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Edge vs Cloud PoC - measurement client.

For each of the two target servers (EDGE and CLOUD) the client performs
REQUESTS measurements. In every iteration it:
    1. opens a NEW TCP connection (like a typical HHTP request),
    2. sends a trigger (any string),
    3. measures LATENCY    = time from sending the trigger
                             to the first received bytes            [ms]
    4. measures THROUGHPUT = effective download speed of the payload
                             (first byte -> end of transmission)    [Mbps]
    5. appends (append!) one row to results.csv.

Edge and Cloud queries are interleaved (iteration i = Edge + Cloud),
which eliminates the effect of changing network conditions over time.

Each query is retried on failure, so single network glitches do not
break the experiment.

Usage:
    python client.py <EDGE_IP> <CLOUD_IP>
    python client.py 192.168.0.20 140.82.121.4 --requests 50

Output CSV columns:
    timestamp, server_type, latency_ms, throughput_mbps
"""

import argparse
import csv
import os
import socket
import time
from datetime import datetime

# ====================== CONFIGURATION ======================
PORT             = 5001    # default server port (can be overridden via flags)
REQUESTS         = 50      # queries per environment (Edge AND Cloud)
PAYLOAD_MB       = 1       # expected payload size - only for verification
SOCKET_TIMEOUT_S = 10.0    # max time for connect/recv in a single query
RECV_BUF         = 65536   # receive chunk size
RETRIES          = 3       # attempts per query (resistance to network errors)
CSV_FILE         = "results.csv"
# ===========================================================


def measure_once(ip: str, port: int):
    """One query. Returns (latency_ms, throughput_mbps, total_bytes); raises OSError on failure."""
    with socket.create_connection((ip, port), timeout=SOCKET_TIMEOUT_S) as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # disable Nagle - pure latency

        # --- trigger: any string starts the response on the server ---
        t_send = time.perf_counter()
        sock.sendall(b"PING\n")

        # --- FIRST received bytes -> latency ---
        first = sock.recv(RECV_BUF)
        t_first = time.perf_counter()
        if not first:
            raise ConnectionError("server closed the connection without sending data")
        latency_ms = (t_first - t_send) * 1000.0

        # --- download until EOF (server sends FIN) -> throughput ---
        total = len(first)
        while True:
            chunk = sock.recv(RECV_BUF)
            if not chunk:
                break
            total += len(chunk)
        t_end = time.perf_counter()

    download_s = max(t_end - t_first, 1e-9)  # protection against division by zero
    throughput_mbps = (total * 8.0) / download_s / 1e6  # bytes -> bits -> Mbps
    return latency_ms, throughput_mbps, total


def measure_with_retry(label: str, ip: str, port: int):
    """Calls measure_once() with retries; returns None if the environment is constantly unreachable."""
    for attempt in range(1, RETRIES + 1):
        try:
            return measure_once(ip, port)
        except OSError as exc:  # timeout, connection refused, reset, DNS problem...
            print(f"  [!] {label} attempt {attempt}/{RETRIES} failed: {exc}", flush=True)
            if attempt < RETRIES:
                time.sleep(1.0)
    return None


def append_row(row) -> None:
    """Appends a single row to the CSV file (creates the file with a header on first use)."""
    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "server_type", "latency_ms", "throughput_mbps"])
        writer.writerow(row)


def run_loop(args) -> None:
    targets = (("Edge",  args.edge_ip,  args.edge_port),
               ("Cloud", args.cloud_ip, args.cloud_port))
    expected_bytes = args.size_mb * 1024 * 1024

    print(f"Targets: Edge = {args.edge_ip}:{args.edge_port} | Cloud = {args.cloud_ip}:{args.cloud_port}")
    print(f"Queries: {args.requests} per environment (interleaved), results -> {CSV_FILE}\n", flush=True)

    for i in range(1, args.requests + 1):
        for server_type, ip, port in targets:
            result = measure_with_retry(server_type, ip, port)
            ts = datetime.now().isoformat(timespec="seconds")

            if result is None:
                # environment constantly unreachable in this iteration
                append_row([ts, server_type, "", ""])
                print(f"[{i:2d}/{args.requests}] {server_type:5s} FAILED (written as an empty row)", flush=True)
                continue

            latency_ms, throughput_mbps, total = result
            if total != expected_bytes:
                print(f"  [!] {server_type}: received {total:,} B, expected {expected_bytes:,} B "
                      f"(SERVER PAYLOAD_MB / CLIENT --size-mb mismatch?)", flush=True)
            append_row([ts, server_type, f"{latency_ms:.3f}", f"{throughput_mbps:.2f}"])
            print(f"[{i:2d}/{args.requests}] {server_type:5s} "
                  f"latency = {latency_ms:8.2f} ms | throughput = {throughput_mbps:10.2f} Mbps", flush=True)

    print(f"\nDone. Results appended to: {CSV_FILE} | now run:  python plot.py", flush=True)


def parse_args():
    p = argparse.ArgumentParser(description="Latency/throughput PoC client (Edge vs Cloud).")
    p.add_argument("edge_ip", help="IP address (or hostname) of the Edge server")
    p.add_argument("cloud_ip", help="IP address (or hostname) of the Cloud server")
    p.add_argument("--edge-port", type=int, default=PORT, help=f"Edge server port (default: {PORT})")
    p.add_argument("--cloud-port", type=int, default=PORT, help=f"Cloud server port (default: {PORT})")
    p.add_argument("--requests", type=int, default=REQUESTS, help=f"queries per environment (default: {REQUESTS})")
    p.add_argument("--size-mb", type=int, default=PAYLOAD_MB,
                   help=f"expected payload size in MB for verification (default: {PAYLOAD_MB})")
    return p.parse_args()


if __name__ == "__main__":
    run_loop(parse_args())
