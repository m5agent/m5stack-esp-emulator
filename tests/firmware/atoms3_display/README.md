# AtomS3 original display autodetection

Use an owned Device Service with canonical native layers through 0186. Supply
unaltered public images: [ATOMS3 UserDemo](https://burner.m5stack.com/api/v1/firmwares/1897200000000000938)
and [Snake Game](https://github.com/Forairaaaaa/Stupinake/blob/f6df0ad424fbbd57d5c22eb0a52263a374dacccb/Arduino/AtomS3/Stupinake_0x0.bin).
The runner pins their SHA-256, uploads the source bytes, selects the original
GC9107 variant, verifies nonblank frames for 120 seconds and, for Snake, supplies
four MPU6886 acceleration inputs through QOM and observes changed guest frames.
Pillow must be installed in the Python environment.

```sh
python3 tests/firmware/atoms3_display/run_test.py \
  --api "$OWNED_SERVICE_API" --token-file "$OWNED_TOKEN_FILE" \
  --case snake --bin "$ORIGINAL_SNAKE_BIN" --out "$IGNORED_EVIDENCE_DIR"
```

Repeat with `--case userdemo` and its original BIN. The runner downloads the
same-session evidence ZIP before stopping with retained history. A process
running or an upload succeeding does not satisfy this test.

The two controller fixes are separate: 0185 connects AtomS3's on-chip LCD_CAM
and completes command-only parallel-bus probes, even with no parallel panel;
0186 clocks panel RDDID bytes through SPI transactions and latches RX FIFO
words. The previous model repeated the complete ID for each 8-bit read.
These are native virtual-device results. Browser-WASM and physical hardware,
LCD_CAM 16-bit pixel output and physical LCD/IMU behavior are not covered.
