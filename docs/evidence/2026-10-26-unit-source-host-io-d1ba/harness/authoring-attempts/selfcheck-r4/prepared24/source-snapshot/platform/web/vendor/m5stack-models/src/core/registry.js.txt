// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
/**
 * Global plugin registry, so devices and modules can be created by id — handy
 * when commands arrive over a bridge (`{ type:'attach', module:'m5.hat.led-matrix' }`).
 */
const devices = new Map();
const modules = new Map();
const plugins = new Map();

/** A plugin is `{ name, devices: [DeviceClass], modules: [ModuleClass] }`. */
export function definePlugin(plugin) {
  if (!plugin?.name) throw new Error('definePlugin: "name" is required');
  return Object.freeze({ devices: [], modules: [], ...plugin });
}

export function registerPlugin(plugin) {
  if (plugins.has(plugin.name)) return plugin;
  plugins.set(plugin.name, plugin);
  for (const D of plugin.devices ?? []) registerDevice(D);
  for (const M of plugin.modules ?? []) registerModule(M);
  return plugin;
}

export function registerDevice(DeviceClass) {
  devices.set(DeviceClass.meta.id, DeviceClass);
}

export function registerModule(ModuleClass) {
  modules.set(ModuleClass.meta.id, ModuleClass);
}

export function createDevice(id, options) {
  const D = devices.get(id);
  if (!D) throw new Error(`Unknown device "${id}". Registered: ${[...devices.keys()].join(', ') || '(none)'}`);
  return new D(options);
}

export function createModule(id, options) {
  const M = modules.get(id);
  if (!M) throw new Error(`Unknown module "${id}". Registered: ${[...modules.keys()].join(', ') || '(none)'}`);
  return new M(options);
}

/** Metadata of registered devices. */
export function listDevices() {
  return [...devices.values()].map((D) => D.meta);
}

/** Metadata of registered modules, optionally only those fitting a connector. */
export function listModules({ connector } = {}) {
  return [...modules.values()].map((M) => M.meta).filter((m) =>
    !connector || (Array.isArray(m.connector) ? m.connector.includes(connector) : m.connector === connector));
}
