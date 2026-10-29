// Observe the same guest's UART1 SCS controller; never infer output from inputs.
const SCS_PATH = '/machine/scs_servo';
const SCS_SOURCE = 'qemu-uart1-scs-controller';
const integer = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
function check(ok, message) { if (!ok) throw new Error(message); }

/** Calibration belongs to the admitted firmware/board mapping, not the bus. */
export function validateQemuServoOutputProfile(profile) {
  const output = profile?.outputs, calibration = output?.calibration;
  check(profile?.deviceId === 'stackchan' && profile.board === 'm5stackchan'
    && output?.kind === 'stackchan-scs-qom-v1' && output.path === SCS_PATH
    && output.property === 'state', 'Invalid QEMU StackChan servo output profile');
  check(calibration && Object.keys(calibration).length === 5
    && integer(calibration.yawZeroTicks, 0, 1000) && integer(calibration.pitchZeroTicks, 0, 1000)
    && calibration.tickDegrees === 5 / 16
    && [1, -1].includes(calibration.yawDirection) && [1, -1].includes(calibration.pitchDirection), 'QEMU StackChan servo calibration must be explicit');
  return output;
}

/** One QOM getter returns one controller snapshot, avoiding torn multi-reads. */
export function validateQemuServoState(profile, state) {
  validateQemuServoOutputProfile(profile);
  check(state?.schema_version === 1 && state.device_id === 'stackchan'
    && state.path === SCS_PATH && state.source === SCS_SOURCE
    && typeof state.powered === 'boolean'
    && integer(state.packets, 0, Number.MAX_SAFE_INTEGER)
    && integer(state.rejected_packets, 0, Number.MAX_SAFE_INTEGER)
    && state.motion_model === 'command-time-position-v1' && state.pwm_motion_modelled === false
    && Array.isArray(state.servos) && state.servos.length === 2, 'Invalid QEMU StackChan servo state');
  if(['uart_tx_connected','uart_rx_connected','disconnected_tx_bytes','disconnected_rx_packets'].some(key=>Object.hasOwn(state,key)))
    check(typeof state.uart_tx_connected==='boolean'&&typeof state.uart_rx_connected==='boolean'
      &&integer(state.disconnected_tx_bytes,0,Number.MAX_SAFE_INTEGER)&&integer(state.disconnected_rx_packets,0,Number.MAX_SAFE_INTEGER),'Invalid QEMU StackChan UART wiring state');
  for (const [index, servo] of state.servos.entries()) {
    check(servo?.id === index + 1 && integer(servo.present_position, 0, 1000)
      && integer(servo.goal_position, 0, 1000) && integer(servo.torque, 0, 2)
      && ['position', 'pwm'].includes(servo.mode) && typeof servo.moving === 'boolean'
      && integer(servo.goal_time_ms, 0, 65535) && integer(servo.goal_speed, 0, 65535)
      && integer(servo.pwm, -1023, 1023) && (servo.mode === 'pwm' || servo.pwm === 0),
    'Invalid QEMU StackChan servo registers');
    check(!servo.moving || state.powered && servo.torque === 1 && servo.mode === 'position'
      && servo.goal_time_ms > 0 && servo.present_position !== servo.goal_position,
    'Invalid QEMU StackChan movement state');
  }
  return state;
}

export async function readQemuServoOutputs(profile, qmp) {
  const output = validateQemuServoOutputProfile(profile);
  const observed = await qmp('qom-get', {path:output.path, property:output.property});
  // Preserve the controller source/units. The private bridge supplies only the
  // selected device identity and the fixed path it actually queried.
  return validateQemuServoState(profile, {...observed, device_id:profile.deviceId, path:output.path});
}

/** Present position is authoritative even after torque release or rail loss. */
export function qemuServoVisualCommands(profile, state) {
  validateQemuServoState(profile, state);
  const {yawZeroTicks, pitchZeroTicks, tickDegrees, yawDirection, pitchDirection} = profile.outputs.calibration;
  const yaw = (state.servos[0].present_position - yawZeroTicks) * tickDegrees * yawDirection;
  const pitch = (state.servos[1].present_position - pitchZeroTicks) * tickDegrees * pitchDirection;
  return [
    {type:'joint', target:'yaw', angleDeg:yaw, durationMs:0},
    // The CAD joint has a documented 0..90 degree visual limit. Raw controller
    // positions remain available in evidence when they exceed that envelope.
    {type:'joint', target:'pitch', angleDeg:Math.max(0, Math.min(90, pitch)), durationMs:0},
  ];
}

/** Explain observed motor inhibition without treating a command as motion. */
export function qemuServoDiagnostic(profile, state) {
  validateQemuServoState(profile,state);
  if(!state.powered)return {code:'power-off',message:'舵机电源尚未开启。请在固件中开启舵机供电。'};
  if(state.uart_tx_connected===false)return {code:'uart-tx-disconnected',message:'舵机串口未接通。请检查固件的 UART1 TX6 / RX7 配置。'};
  if(state.uart_rx_connected===false)return {code:'uart-rx-disconnected',message:'舵机返回通道未接通。请检查固件的 UART1 RX7 配置。'};
  if(state.servos.some(servo=>servo.mode==='pwm'))return {code:'pwm-unmodelled',message:'固件使用连续转动模式；此模式的机械运动尚未模拟。'};
  const disabled=state.servos.filter(servo=>servo.torque!==1);
  if(disabled.length)return {code:'torque-disabled',message:`${disabled.map(servo=>servo.id===1?'左右':'抬头').join('、')}舵机未使能。请在固件中开启舵机扭矩。`};
  const rawPitch=(state.servos[1].present_position-profile.outputs.calibration.pitchZeroTicks)
    *profile.outputs.calibration.tickDegrees*profile.outputs.calibration.pitchDirection;
  if(rawPitch<0||rawPitch>90)return {code:'visual-range',message:'实际舵机位置超出模型俯仰范围。请检查固件保存的零位。'};
  return {code:'ready',message:'舵机已使能，画面跟随实际位置。'};
}
