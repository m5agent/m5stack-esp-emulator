# Emscripten host poll timeout control

This opt-in C probe uses the actual WASM branch of QEMU patch `0015`, real
SDK `poll`, pipes and pthreads. It first preserves the SDK 3.1.50 negative
control: plain `poll` ignores its timeout. It then checks finite wait,
nonblocking and already-ready descriptors, and another pthread waking a finite
or infinite wait. This runs under Node, without a guest or virtual-device claim.

```sh
python3 tests/browser-qemu/poll_wait/build.py --emcc /path/to/emscripten/emcc \
  --node node --out-dir .work/poll-wait-control
```

The deterministic compiler test separately exercises sub-millisecond and very
large deadlines, zero descriptors and `EINTR`, without requiring an SDK cache:

```sh
python3 -m unittest discover -s platform/tests -p 'test_wasm_poll_wait_patch.py'
```

This host wait is outside the main-loop BQL and uses host monotonic time. It
does not slow a vCPU or change guest timers/watchdogs. The five-millisecond
slice bounds re-polling, not browser scheduling latency or a hard response SLA.
