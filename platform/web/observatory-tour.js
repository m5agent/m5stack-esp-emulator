// A deterministic, input-free presentation clock. It never affects a guest.
const ordered = rows => [...rows].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)) || a.session_id.localeCompare(b.session_id));
const ACTIVE = new Set(['provisioning', 'flashing', 'booting', 'running', 'stopping']);
export class ObservatoryTour {
  constructor({clock = Date.now} = {}) {
    this.clock = clock; this.phase = 'idle'; this.deadline = 0; this.detailDeadline = 0;
    this.selectedId = null; this.groupId = null; this.groupCursor = 0; this.deviceCursors = new Map();
    this.previous = new Map();
  }
  pick(rows, groupId = null) {
    const candidates = ordered(rows.filter(row => !groupId || row.device_id === groupId));
    if (!candidates.length) return null;
    const key = groupId || '*';
    const index = this.deviceCursors.get(key) || 0;
    // The first detail favours a connected assembly; following selections are
    // fair round-robin, including headless and black-screen devices.
    const start = !this.deviceCursors.has(key) ? Math.max(0, candidates.findIndex(row => row.units?.length)) : index % candidates.length;
    this.deviceCursors.set(key, start + 1);
    return candidates[start].session_id;
  }
  update(input) {
    const rows = ordered(input), now = this.clock(), groups = [...new Set(rows.map(row => row.device_id))].sort();
    const activity = rows.some(row => !this.previous.has(row.session_id)
      || ACTIVE.has(this.previous.get(row.session_id)) && !ACTIVE.has(row.state));
    this.previous = new Map(rows.map(row => [row.session_id, row.state]));
    if (!rows.length) {
      this.phase = 'idle'; this.selectedId = this.groupId = null; this.deadline = 0;
      return this.snapshot(now);
    }
    const hasSelected = rows.some(row => row.session_id === this.selectedId);
    const hasGroup = !this.groupId || groups.includes(this.groupId);
    if (this.phase === 'idle' || !hasGroup || this.phase === 'device' && !hasSelected) {
      this.phase = 'overview'; this.groupId = null; this.deadline = now + 12000;
      this.selectedId = this.pick(rows); this.detailDeadline = now + 6000;
    } else if (!hasSelected) {
      this.selectedId = this.pick(rows, this.phase === 'group' ? this.groupId : null); this.detailDeadline = now + 6000;
    }
    if (activity && this.phase !== 'overview') {
      // New arrivals and terminal transitions must appear in the shared space
      // before an 8-second terminal model leaves. Busy centres stay panoramic;
      // the passive tour resumes once the activity settles.
      this.phase = 'overview'; this.groupId = null; this.deadline = now + 12000;
      this.detailDeadline = now + 6000;
    } else if (activity) this.deadline = Math.max(this.deadline, now + 8000);
    if (now >= this.deadline) {
      if (this.phase === 'overview') {
        this.groupId = groups[this.groupCursor++ % groups.length];
        this.selectedId = this.pick(rows, this.groupId);
        this.phase = groups.length > 1 ? 'group' : 'device';
        this.deadline = now + (this.phase === 'group' ? 5000 : 8000);
      } else if (this.phase === 'group') {
        this.phase = 'device'; this.deadline = now + 8000;
      } else {
        this.phase = 'overview'; this.groupId = null; this.deadline = now + 12000;
        this.selectedId = this.pick(rows); this.detailDeadline = now + 6000;
      }
    } else if (this.phase === 'overview' && now >= this.detailDeadline) {
      this.selectedId = this.pick(rows); this.detailDeadline = now + 6000;
    }
    return this.snapshot(now);
  }
  snapshot(now = this.clock()) {
    return {phase: this.phase, selectedId: this.selectedId, groupId: this.groupId,
      remaining: Math.max(0, Math.ceil((this.deadline - now) / 1000))};
  }
}
