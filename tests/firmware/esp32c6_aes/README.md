# ESP32-C6 AES controller/GDMA regression

This ESP-IDF 5.5.4 firmware exercises the public mbedTLS hardware AES driver.
The independent oracle is [NIST SP 800-38A, F.2.1](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a.pdf).
It encrypts/decrypts the four-block vector three times, then processes 4096 bytes
(repeating that plaintext 64 times). The latter crosses IDF's 2000-byte interrupt
threshold and a GDMA descriptor boundary; its ciphertext SHA256 was computed
independently with OpenSSL AES-128-CBC, key `2b7e151628aed2a6abf7158809cf4f3c`,
IV `000102030405060708090a0b0c0d0e0f`, no padding:
`a34c13a49f3449b515b95dcb99679ba8097e370479ba2927fcc9cfff0ec4bdba`.

With an activated ESP-IDF 5.5.4 environment:

```sh
idf.py -C tests/firmware/esp32c6_aes -B .work/c6-aes-probe build
python -m esptool --chip esp32c6 merge-bin -o .work/c6-aes-probe/merged.bin \
  0x0 .work/c6-aes-probe/bootloader/bootloader.bin \
  0x8000 .work/c6-aes-probe/partition_table/partition-table.bin \
  0x10000 .work/c6-aes-probe/c6_aes_dma_probe.bin
```

Upload the merged image to a dedicated Device Service. Run `nesso-n1` and
`nanoc6` sessions with `runtime=qemu`, `ready_marker=C6_AES_READY` and retain
serial/evidence before stopping with `purge=0`. Require three
`C6_AES_CBC_PASS` lines plus `C6_AES_DMA_IRQ_PASS bytes=4096`, no FAIL/panic,
and the final marker. For controller tracing, launch the owned service with
`M5SW_C6_IRQ_TRACE=1` and require AES source 73. The backend and ROM paths must
refer to the C6 recipe, not the Xtensa Unit runtime.

Negative control: the runtime before `0008-c6-aes-gdma-wiring.patch` stops at
`C6_AES_START`, polling the absent AES state register at `0x6008804c`.

Scope: virtual-device data-plane validation. This does not establish physical
crypto timing/security, full firmware readiness, WiFi or filesystem support.

The dated results and exact identities are in
[evidence-2026-11-13.json](evidence-2026-11-13.json). The original Bruce image
now reaches its LittleFS error page; that is a narrower result than full
application readiness. Launcher and Meshtastic remain separate open failures.
