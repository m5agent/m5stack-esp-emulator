#!/usr/bin/env python3
"""Exercise SR9900A TX/RX through Linux AF_PACKET and r8152."""
import socket
import time

ETH_P_M5_PROBE = 0x88B5
IFACE = "eth0"
GUEST_MAC = bytes.fromhex("020000009900")
HOST_MAC = bytes.fromhex("020000009901")


def build_frame(destination, source, payload):
    frame = destination + source + ETH_P_M5_PROBE.to_bytes(2, "big") + payload
    if len(frame) < 60:
        frame += bytes(60 - len(frame))
    return frame


def main():
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW,
                         socket.htons(ETH_P_M5_PROBE))
    sock.bind((IFACE, 0))
    sock.settimeout(15)
    tx = build_frame(HOST_MAC, GUEST_MAC, b"M5-SR9900A-TX")
    print("USB_ETH_TX=" + tx.hex())
    for _ in range(10):
        sock.send(tx)
        time.sleep(1)

    deadline = time.time() + 15
    while time.time() < deadline:
        frame = sock.recv(65535)
        if frame[12:14] != ETH_P_M5_PROBE.to_bytes(2, "big"):
            continue
        if not frame[14:].startswith(b"M5-SR9900A-RX"):
            continue
        print("USB_ETH_RX=" + frame.hex())
        print("USB_ETH_ROUNDTRIP=PASS")
        return
    print("USB_ETH_ROUNDTRIP=FAIL")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
