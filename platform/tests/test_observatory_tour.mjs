import assert from 'node:assert/strict';
import {ObservatoryTour} from '../web/observatory-tour.js';

let now = 0;
const tour = new ObservatoryTour({clock: () => now});
const rows = [
  {session_id: 'core-a', device_id: 'cores3', created_at: '2026-11-06T00:00:00Z', units: [{id: 'relay'}]},
  {session_id: 'core-b', device_id: 'cores3', created_at: '2026-11-06T00:00:01Z'},
  {session_id: 'atom-a', device_id: 'atoms3r', created_at: '2026-11-06T00:00:02Z'},
];
assert.equal(tour.update([]).phase, 'idle');
assert.deepEqual(tour.update(rows), {phase: 'overview', selectedId: 'core-a', groupId: null, remaining: 12});
now = 6000;
assert.equal(tour.update(rows).selectedId, 'core-b', 'detail follows fair automatic rotation without camera changes');
now = 12000;
assert.equal(tour.update(rows).phase, 'group');
now = 17000;
assert.equal(tour.update(rows).phase, 'device');
now = 25000;
assert.equal(tour.update(rows).phase, 'overview');
const devices = new Set(), groups = new Set(), phases = new Set();
for (; now < 240000; now += 1000) {
  const state = tour.update(rows);
  devices.add(state.selectedId); groups.add(state.groupId); phases.add(state.phase);
}
assert.deepEqual([...devices].sort(), rows.map(x => x.session_id).sort(), 'black/headless devices are not starved');
assert.ok(groups.has('cores3') && groups.has('atoms3r'));
assert.ok(phases.has('overview') && phases.has('group') && phases.has('device'));
const afterRemoval = tour.update(rows.filter(x => x.session_id !== tour.selectedId));
assert.ok(rows.some(x => x.session_id === afterRemoval.selectedId));
assert.deepEqual(tour.update([]), {phase: 'idle', selectedId: null, groupId: null, remaining: 0});
const only = new ObservatoryTour({clock: () => now});
assert.equal(only.update([rows[0]]).phase, 'overview');
now += 12000;
assert.equal(only.update([rows[0]]).phase, 'device', 'single-group presentation skips a redundant group view');
const before = JSON.stringify(rows);
only.update(rows);
assert.equal(JSON.stringify(rows), before, 'presentation never edits lifecycle or guest data');
const busy = new ObservatoryTour({clock: () => now});
const activeRows = rows.map(row => ({...row, state: 'running'}));
busy.update(activeRows); now += 12000; busy.update(activeRows); now += 5000;
assert.equal(busy.update(activeRows).phase, 'device');
assert.equal(busy.update([...activeRows, {session_id: 'short', device_id: 'new-model', state: 'stopped', created_at: '2026-11-06T00:00:03Z'}]).phase, 'overview', 'a newly seen short task interrupts the close-up to become visible');
now += 12000; busy.update(activeRows); now += 5000; busy.update(activeRows);
assert.equal(busy.update(activeRows.map(row => row.session_id === 'atom-a' ? {...row, state: 'failed'} : row)).phase, 'overview', 'terminal transitions return to the whole laboratory');
console.log('Observatory unattended presentation timing, fairness and removal contracts PASS');
