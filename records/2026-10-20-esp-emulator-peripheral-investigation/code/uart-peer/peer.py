import socket, time
for _ in range(80):
    try:
        s = socket.create_connection(("127.0.0.1", 15556), timeout=0.5)
        break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("peer: emulator UART1 listener did not appear")
s.settimeout(10)
data = b""
while b"PING\n" not in data:
    chunk = s.recv(128)
    if not chunk:
        raise SystemExit("peer: socket closed before PING")
    data += chunk
print("peer_rx=" + repr(data), flush=True)
s.sendall(b"PONG\n")
time.sleep(0.5)
s.close()
