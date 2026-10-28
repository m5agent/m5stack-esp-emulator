// During interaction, choose slices from observed cost independently of guest time.
// Keep the original slice size otherwise. A slice cannot be preempted; slow/JIT-cold
// work may still exceed the interaction target.
export function createPacing() {
  let interactiveUntil = -Infinity;
  let cyclesPerMs = 16_000;
  return {
    input(now) { interactiveUntil = now + 250; },
    turnMs(now) { return now < interactiveUntil ? 8 : 25; },
    sliceCycles(remaining, wallBudgetMs, now) {
      if (now >= interactiveUntil) return Math.max(1, Math.floor(Math.min(remaining, 2_000_000)));
      return Math.max(1, Math.floor(Math.min(remaining, 2_000_000,
        cyclesPerMs * Math.max(0.1, Math.min(4, wallBudgetMs)))));
    },
    observe(cycles, elapsedMs) {
      if (cycles <= 0 || elapsedMs <= 0) return;
      const measured = cycles / elapsedMs;
      // Respond immediately to expensive work; grow gradually when work becomes cheaper.
      cyclesPerMs = Math.min(measured, cyclesPerMs * 1.25);
    },
  };
}
