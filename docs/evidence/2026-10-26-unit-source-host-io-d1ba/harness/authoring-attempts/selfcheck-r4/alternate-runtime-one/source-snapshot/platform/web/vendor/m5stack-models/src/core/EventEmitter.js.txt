// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
/**
 * Minimal typed-ish event emitter. `on()` returns an unsubscribe function so
 * callers never need to keep a reference to the handler.
 */
export class EventEmitter {
  #handlers = new Map();

  on(type, fn) {
    let set = this.#handlers.get(type);
    if (!set) this.#handlers.set(type, (set = new Set()));
    set.add(fn);
    return () => this.off(type, fn);
  }

  once(type, fn) {
    const off = this.on(type, (...args) => {
      off();
      fn(...args);
    });
    return off;
  }

  off(type, fn) {
    const set = this.#handlers.get(type);
    if (!set) return;
    if (fn) set.delete(fn);
    else set.clear();
  }

  emit(type, ...args) {
    const set = this.#handlers.get(type);
    if (set) for (const fn of [...set]) fn(...args);
    const any = this.#handlers.get('*');
    if (any && type !== '*') for (const fn of [...any]) fn(type, ...args);
  }

  removeAllListeners() {
    this.#handlers.clear();
  }
}
