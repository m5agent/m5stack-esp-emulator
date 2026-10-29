// Controller-to-model contract checks only; this file does not execute a guest.
import assert from 'node:assert/strict';
import {validateQemuServoOutputProfile, validateQemuServoState, readQemuServoOutputs,
  qemuServoVisualCommands} from '../web/public-qemu-servo.js';

const profile = {deviceId:'stackchan', board:'m5stackchan', outputs:{kind:'stackchan-scs-qom-v1',
  path:'/machine/scs_servo', property:'state', calibration:{yawZeroTicks:460, pitchZeroTicks:620, tickDegrees:5 / 16, yawDirection:1, pitchDirection:1}}};
const raw = {schema_version:1, source:'qemu-uart1-scs-controller', powered:true,
  packets:24, rejected_packets:2, motion_model:'command-time-position-v1', pwm_motion_modelled:false,
  servos:[
    {id:1, present_position:556, goal_position:652, torque:1, mode:'position', moving:true, goal_time_ms:100, goal_speed:0, pwm:0},
    {id:2, present_position:684, goal_position:876, torque:1, mode:'position', moving:true, goal_time_ms:100, goal_speed:0, pwm:0},
  ]};
const reads = [];
const observed = await readQemuServoOutputs(profile, async (execute, args) => {
  reads.push({execute, ...args}); return structuredClone(raw);
});
assert.deepEqual(reads, [{execute:'qom-get', path:'/machine/scs_servo', property:'state'}]);
assert.equal(observed.device_id, 'stackchan');
assert.deepEqual(qemuServoVisualCommands(profile, observed), [
  {type:'joint', target:'yaw', angleDeg:30, durationMs:0},
  {type:'joint', target:'pitch', angleDeg:20, durationMs:0},
]);
// Targets do not drive geometry: partial movement must show present, not goal.
const otherTargets = structuredClone(observed);
otherTargets.servos[0].goal_position = 1000;
otherTargets.servos[1].goal_position = 999;
assert.deepEqual(qemuServoVisualCommands(profile, otherTargets), qemuServoVisualCommands(profile, observed));
// Power and torque off hold the last observed shaft pose; neither snaps home.
const released = structuredClone(observed); released.powered = false;
released.servos.forEach(servo => { servo.torque = 0; servo.moving = false; });
assert.deepEqual(qemuServoVisualCommands(profile, released), qemuServoVisualCommands(profile, observed));
// Firmware calibration is explicit: a UIFlow mapping has different zero ticks.
const uiflow = structuredClone(profile);
uiflow.outputs.calibration.yawZeroTicks = 450; uiflow.outputs.calibration.pitchZeroTicks = 125;
const uiflowObserved = structuredClone(observed);
uiflowObserved.servos[0].present_position = 450; uiflowObserved.servos[1].present_position = 125;
assert.deepEqual(qemuServoVisualCommands(uiflow, uiflowObserved).map(command => command.angleDeg), [0, 0]);
const reversed = structuredClone(profile);
reversed.outputs.calibration.yawDirection = -1; reversed.outputs.calibration.pitchDirection = -1;
const reverseObserved = structuredClone(observed);
reverseObserved.servos[1].present_position = 556;
assert.deepEqual(qemuServoVisualCommands(reversed, reverseObserved).map(command => command.angleDeg), [-30, 20]);
const limits = structuredClone(observed);
limits.servos[0].present_position = 0; limits.servos[1].present_position = 1000;
assert.deepEqual(qemuServoVisualCommands(profile, limits).map(command => command.angleDeg), [-143.75, 90]);
limits.servos[1].present_position = 0;
assert.equal(qemuServoVisualCommands(profile, limits)[1].angleDeg, 0);
const pwm = structuredClone(observed);
pwm.servos[0] = {...pwm.servos[0], mode:'pwm', pwm:-512, moving:false};
assert.equal(validateQemuServoState(profile, pwm), pwm);
assert.deepEqual(qemuServoVisualCommands(profile, pwm), qemuServoVisualCommands(profile, observed), 'unmodelled PWM never fabricates rotation');
for (const modify of [
  value => { delete value.outputs.calibration; },
  value => { value.outputs.calibration.tickDegrees = 0.3; },
  value => { value.outputs.calibration.pitchDirection = 0; },
  value => { delete value.outputs.calibration.yawDirection; },
  value => { value.outputs.calibration.yawZeroTicks = '460'; },
  value => { value.outputs.path = '/machine/other'; },
  value => { value.outputs.property = 'present'; },
  value => { value.deviceId = 'cores3'; },
]) {
  const invalid = structuredClone(profile); modify(invalid);
  assert.throws(() => validateQemuServoOutputProfile(invalid), /QEMU StackChan/);
}
for (const modify of [
  value => { value.source = 'input'; },
  value => { value.path = '/machine/other'; },
  value => { value.device_id = 'cores3'; },
  value => { value.powered = 1; },
  value => { value.servos.reverse(); },
  value => { value.servos[0].present_position = NaN; },
  value => { value.servos[0].present_position = 1001; },
  value => { value.servos[0].present_position = '556'; },
  value => { value.servos[0].goal_time_ms = -1; },
  value => { value.servos[0].torque = 0; },
  value => { value.servos[0].pwm = 512; },
  value => { value.servos[0].moving = 'true'; },
  value => { value.servos[0].mode = 'pwm'; },
  value => { value.servos[0].present_position = value.servos[0].goal_position; },
  value => { value.pwm_motion_modelled = true; },
]) {
  const invalid = structuredClone(observed); modify(invalid);
  assert.throws(() => validateQemuServoState(profile, invalid), /QEMU StackChan/);
}
await assert.rejects(readQemuServoOutputs(profile, async () => { throw new Error('QOM unavailable'); }), /QOM unavailable/);
await assert.rejects(readQemuServoOutputs(profile, async () => ({...raw, source:'serial-text'})), /QEMU StackChan/);
console.log('StackChan fixed QOM snapshot, calibration, present-position geometry and fail-closed contracts passed; no guest executed');
