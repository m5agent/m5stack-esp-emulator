// Output-only model updates shared by the workbench and local observatory.
// A surface owns one model/display, disposal identity and driveActivities Map.
// These functions never install input handlers, start audio or call a service.

// These two upstream Component-based indicators reject color changes instead
// of exposing Led.fixedColor. Their pinned source permits on/brightness only.
const FIXED_BLUE_STATUS_HOSTS = new Set(['m5stack.unit.timercamera-f', 'm5stack.unit.timercamera-f.grove',
  'm5stack.unit.timercamera-x', 'm5stack.unit.timercamera-x.grove']);
const fixedColorIndicator = led => led.fixedColor !== undefined || led.meta.fixedColor !== undefined
  || [led.meta.colorMode, led.meta.color].some(value => String(value || '').startsWith('fixed-'))
  || (led.id === 'status' && FIXED_BLUE_STATUS_HOSTS.has(led.host?.meta?.id));

export async function setModelImage(surface, image, sequence = surface.frameSeq + 1, commitGuard = () => true) {
    if (!surface.display || surface.disposed || !commitGuard()) return false;
    const bitmap = await createImageBitmap(image);
    try {
      if (surface.disposed || !commitGuard()) return false;
      const rotated = surface.display.meta.nativeRasterRotation === 90 && bitmap.width === surface.display.height && bitmap.height === surface.display.width;
      if (!rotated && (bitmap.width !== surface.display.width || bitmap.height !== surface.display.height)) {
        surface.showOverlay('Framebuffer mismatch', `收到 ${bitmap.width}×${bitmap.height}，面板为 ${surface.display.width}×${surface.display.height}`);
        return false;
      }
      const context = surface.display.getContext2D();
      context.clearRect(0, 0, surface.display.width, surface.display.height);
      context.save();
      if (rotated) { context.translate(surface.display.width, 0); context.rotate(Math.PI / 2); }
      context.drawImage(bitmap, 0, 0);
      context.restore();
      surface.display.present();
      surface.frameSeq = sequence;
      surface.hideOverlay();
      return true;
    } finally { bitmap.close(); }
  }

export function applyModelVisualState(surface, commands) {
    if (surface.disposed) return [];
    surface.feedbackDepth++;
    try {
      return (Array.isArray(commands) ? commands : [commands]).map(command => {
        if (!command || !['led', 'joint', 'display', 'vibrate', 'position', 'button-state', 'drive-activity'].includes(command.type)) {
          throw new TypeError('Expected an output-only visual command');
        }
        if (command.type === 'drive-activity') {
          if (typeof command.active !== 'boolean' || !String(command.target).endsWith('/rotor')) throw new TypeError('Expected a fan drive activity command');
          const joint = surface.model.find(command.target, 'joint');
          if (!joint?.continuous) throw new TypeError('Fan rotor joint is unavailable');
          let activity = surface.driveActivities.get(command.target);
          if (!activity) {
            activity = {joint, update: joint.update, active: false, angle: joint.getState().angleDeg};
            surface.driveActivities.set(command.target, activity);
            joint.update = (dt = 0) => {
              if (!activity.active) return activity.update.call(joint, dt);
              if (!Number.isFinite(dt) || dt < 0) return activity.update.call(joint, dt);
              // A fixed graphical cadence communicates electrical activity.
              // It is deliberately independent of duty/frequency and is never
              // written to the joint's RPM state or claimed as shaft speed.
              activity.angle = (activity.angle + Math.max(0, Math.min(dt, 0.25)) * 180) % 360;
              joint.setAngle(activity.angle);
              return true;
            };
          }
          activity.active = command.active;
          joint.requestRender();
          return {active: activity.active, semantics: 'drive-activity-only; shaft-speed-unmodeled'};
        }
        if (command.type === 'position') {
          return surface.model.button(command.target).setPosition(command.position);
        }
        if (command.type === 'button-state') {
          const button = surface.model.button(command.target);
          if (button.latching) throw new TypeError('Latching switches use position output');
          if (typeof command.pressed !== 'boolean') throw new TypeError('pressed must be boolean');
          if (command.pressed) button.press('runtime-readback');
          else button.cancel('runtime-readback');
          return button.getState();
        }
        if (command.type === 'joint') {
          if (command.known !== undefined && typeof command.known !== 'boolean') throw new TypeError('Joint known must be boolean');
          const joint=surface.model.find(command.target,'joint');
          if (!joint) throw new TypeError('Joint component is unavailable');
          // Unknown output preserves the last observed pose; it is not a home command.
          const result=command.known===false?joint.getState():surface.model.handle(command);
          joint.runtimeKnown=joint.object3d.userData.runtimeKnown=command.known!==false;
          return result;
        }
        if (command.type === 'led') {
          if (command.known !== undefined && typeof command.known !== 'boolean') throw new TypeError('LED known must be boolean');
          const led = surface.model.find(command.target, 'led');
          if (!led) throw new TypeError('LED component is unavailable');
          if (command.known !== false) {
            if (command.brightness !== undefined && !Number.isFinite(command.brightness)) throw new TypeError('LED brightness must be finite');
            if (command.on !== undefined && typeof command.on !== 'boolean') throw new TypeError('LED on must be boolean');
            if (command.color !== undefined) {
              if (typeof command.color === 'number' && (!Number.isInteger(command.color) || command.color < 0 || command.color > 0xFFFFFF)) throw new TypeError('LED color must be packed RGB');
              // Three.js may warn and retain the old color for invalid input.
              // Parse on a detached value so that cannot promote unknown output.
              const color = led.color.clone();
              color.r = color.g = color.b = NaN;
              color.set(command.color);
              if (![color.r, color.g, color.b].every(Number.isFinite)) throw new TypeError('LED color is invalid');
            }
          }
          // Zero emission is the neutral appearance of unknown output, not an
          // electrical off observation. Keep that distinction on the component.
          if (command.known === false) {
            led.set(fixedColorIndicator(led) ? {brightness: 0} : {color: 0, brightness: 0});
            led.runtimeKnown = led.object3d.userData.runtimeKnown = false;
            return {known: false};
          }
          const result = surface.model.handle(command);
          led.runtimeKnown = led.object3d.userData.runtimeKnown = true;
          return result;
        }
        return surface.model.handle(command);
      });
    } finally { surface.feedbackDepth--; }
  }

export function clearModelDriveActivities(surface, port = null) {
    for (const [target, activity] of surface.driveActivities) {
      if (port !== null && !target.startsWith(`${port}/`)) continue;
      activity.active = false;
      activity.joint.update = activity.update;
      surface.driveActivities.delete(target);
    }
  }
