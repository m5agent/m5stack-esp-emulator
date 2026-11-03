# WASM32 TCI helper ABI control

Compile the **shipped patch postimage** against the browser build's real
libffi 3.4.7 with Emscripten 3.1.50. This is a standalone ABI test, not a guest
performance result or device validation. No firmware or ROM is required.

```sh
python3 tests/browser-qemu/typed_helpers/build.py \
  --emcc /path/to/emsdk/upstream/emscripten/emcc \
  --ffi-prefix .work/qemu-browser-runtime-build/target \
  --out-dir .work/typed-helper-abi-control
```

The output directory must be new. The tested header is extracted from
`0025-wasm-tci-typed-helper-calls.patch` and checked against the source lock.
The same functions run through the typed dispatcher and the original libffi:
zero through seven arguments, signed/unsigned high bits, pointer arguments and
results, void side effects, and guarded result buffers. Unsupported wide/floating
and struct types, variadic calls, excess arguments and a non-default ABI must
decline without executing the function or modifying the result. Both call paths
also cross a real `setjmp`/`longjmp` boundary.

An actual QEMU guest must separately validate CPU-loop exceptions, Asyncify
fiber switches, controller behavior and normal Worker cleanup. Native hosts
continue using the existing libffi path; this dispatcher is WASM32-specific.
