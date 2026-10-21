# UART peer proof

Minimal ESP-IDF C3 firmware plus a host-side Python peer. The firmware sends
`PING\n` on UART1, the host script receives it and returns `PONG\n`, and the
firmware prints `UART_PEER_OK` on UART0.

Build with ESP-IDF v5.5.5:

```sh
idf.py set-target esp32c3
idf.py build
idf.py merge-bin -o "$PWD/build/merged.bin"
```

Run:

```sh
esp-emu --chip esp32c3 --firmware build/merged.bin \
  --elf build/emu_uart_peer.elf \
  --uart1-tcp 127.0.0.1:15556 \
  --timeout 20s --exit-on UART_PEER_OK

python3 peer.py
```

This proves UART-as-external-device scripting works. It does not prove
baud-rate timing or UART timeout semantics; see upstream issue #20.
