// Install hot guest blocks in Rust's exported function table. All steady-state
// execution stays in WASM; these imports only compile and retire cached code.
export function createJitHost(exports) {
  const free = [], live = new Map();
  const stats = { compiled: 0, failed: 0, released: 0, compileMs: 0, bytes: 0, liveBytes: 0, peakBytes: 0, peakModules: 0 };
  return {
    stats,
    imports: {
      host_jit_compile(ptr, len) {
        const start = performance.now();
        try {
          const w = exports();
          const bytes = new Uint8Array(w.memory.buffer, ptr, len).slice();
          const module = new WebAssembly.Module(bytes);
          const instance = new WebAssembly.Instance(module, { env: { memory: w.memory, table: w.__indirect_function_table } });
          const slot = free.length ? free.pop() : w.__indirect_function_table.grow(1);
          w.__indirect_function_table.set(slot, instance.exports.run);
          live.set(slot, len); stats.compiled++; stats.bytes += len;
          stats.liveBytes += len; stats.peakBytes = Math.max(stats.peakBytes, stats.liveBytes);
          stats.peakModules = Math.max(stats.peakModules, live.size);
          return slot;
        } catch (error) {
          stats.failed++;
          // Compilation failure is safe to interpret: no guest instruction has run.
          console.warn('[jit] compilation failed; interpreting block:', error);
          return 0;
        } finally { stats.compileMs += performance.now() - start; }
      },
      host_jit_release(slot) {
        const len = live.get(slot);
        if (len === undefined) return;
        live.delete(slot); stats.liveBytes -= len;
        exports().__indirect_function_table.set(slot, null);
        free.push(slot); stats.released++;
      },
    },
  };
}
