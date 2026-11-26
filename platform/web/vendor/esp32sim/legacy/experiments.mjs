// Only pre-boot timing setters belong on the experiment dispatch surface.
const u32 = n => Number.isInteger(n) && n >= 0 && n <= 0xffffffff;
const price = n => u32(n) && n <= 1000000;
const positive = n => u32(n) && n > 0;
const mode = max => n => u32(n) && n <= max;
const quantum = n => Number.isInteger(n) && n >= 64 && n <= 4096 && n % 64 === 0;
const setters = new Map([
  ['esp32sim_set_approximate_jit_timing', [n => positive(n) && n <= 256, n => positive(n) && n <= 4096]],
  ['esp32sim_set_approximate_jit_frontiers', [mode(2)]],
  ['esp32sim_set_approximate_jit_cache', [price, price, mode(3)]],
  ['esp32sim_set_approximate_cache_contention', [mode(1)]],
  ['esp32sim_set_approximate_cache_fill_service', [price]],
  ['esp32sim_set_approximate_flash_timing', [price, price]],
  ['esp32sim_set_approximate_pie_timing', [mode(2)]],
  ['esp32sim_set_spi2_timing', [mode(1)]],
  ['esp32sim_set_measured_te', [mode(1)]],
  ['esp32sim_set_control_prices', [mode(1)]],
  ['esp32sim_set_icache_fill', [price]],
  ['esp32sim_set_quantum', [quantum]],
  // Not timing: the fluidbox benchmark's scripted IMU handling (guest-time driven, exact).
  ['esp32sim_set_imu_motion', [mode(1)]],
]);

export const HW = [
  ['esp32sim_set_approximate_jit_timing', 1, 512],
  ['esp32sim_set_approximate_jit_frontiers', 1],
  ['esp32sim_set_approximate_jit_cache', 96, 160, 2],
  ['esp32sim_set_approximate_cache_contention', 1],
  ['esp32sim_set_approximate_cache_fill_service', 160],
  ['esp32sim_set_spi2_timing', 1],
  ['esp32sim_set_measured_te', 1],
  ['esp32sim_set_control_prices', 1],
  ['esp32sim_set_icache_fill', 404],
];

export function validateExperiments(experiments) {
  if (!Array.isArray(experiments)) throw new Error('experiments must be an array');
  for (const entry of experiments) {
    const validators = Array.isArray(entry) && setters.get(entry[0]);
    if (!validators || entry.length !== validators.length + 1 || !validators.every((valid, i) => valid(entry[i + 1]))) {
      throw new Error('invalid timing experiment: ' + JSON.stringify(entry));
    }
  }
  const names = experiments.map(entry => entry[0]);
  if (names.includes('esp32sim_set_quantum') && names.includes('esp32sim_set_approximate_jit_timing')) {
    throw new Error('quantum does not apply to approximate JIT timing');
  }
}

export function applyExperiments(wasm, emu, experiments) {
  validateExperiments(experiments);
  // Check the entire dispatch list before any setter can mutate the emulator.
  for (const [name] of experiments) {
    if (typeof wasm[name] !== 'function') throw new Error('missing timing export: ' + name);
  }
  const applied = [];
  for (const [name, ...args] of experiments) {
    if (wasm[name](emu, ...args) !== 0) throw new Error('timing export rejected: ' + name);
    applied.push([name, ...args]);
  }
  return applied;
}

export function experimentsFromParams(params, board) {
  const timing = params.get('timing');
  if (timing !== null && !/^hw(?:-[0-8])*$/.test(timing)) throw new Error('invalid timing bisect: ' + timing);
  const dropped = timing === null ? [] : timing.split('-').slice(1).map(Number);
  // A bisect that drops a prerequisite also drops its dependent prices.
  if (dropped.includes(0)) dropped.push(1, 2, 3, 4, 7, 8);
  if (dropped.includes(2)) dropped.push(3, 4);
  if (timing !== null && board && /^(esp32c[36]|c[36]|waveshare-c6-lcd147|c6-lcd147|lcd147)$/.test(board)) {
    throw new Error('timing=hw requires an ESP32-S3 board');
  }
  const experiments = timing === null ? [] : HW.filter((_, n) => !dropped.includes(n)
    && (n !== 6 || !board || ['waveshare-amoled18-v2', 'amoled18-v2'].includes(board))).map(entry => [...entry]);
  if (params.has('quantum')) {
    const value = params.get('quantum');
    if (!/^[0-9]+$/.test(value) || !quantum(Number(value))) throw new Error('quantum must be a multiple of 64 from 64 to 4096');
    if (timing !== null) throw new Error('quantum cannot be combined with timing');
    experiments.push(['esp32sim_set_quantum', Number(value)]);
  }
  validateExperiments(experiments);
  return experiments;
}
