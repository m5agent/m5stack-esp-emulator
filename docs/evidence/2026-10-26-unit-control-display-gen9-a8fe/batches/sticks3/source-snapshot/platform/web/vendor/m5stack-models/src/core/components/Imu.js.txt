// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import * as THREE from 'three';
import { Component } from '../Component.js';

const AXES = { '+x': [1, 0, 0], '-x': [-1, 0, 0], '+y': [0, 1, 0], '-y': [0, -1, 0], '+z': [0, 0, 1], '-z': [0, 0, -1] };
const UP = new THREE.Vector3(0, 1, 0);

/**
 * Inertial sensor derived from the on-screen orientation of the device: drag
 * the device around and the accelerometer sees gravity move, the gyroscope sees
 * the angular rate. Vibration adds a little high-frequency noise.
 *
 * `axes` maps each sensor axis to a model axis, e.g. for a chip whose X points
 * to the device bottom: `{ x: '-y', y: '+x', z: '+z' }`.
 *
 * `read()` → { accel: {x,y,z} in g, gyro: {x,y,z} in °/s }
 */
export class Imu extends Component {
  static kind = 'imu';

  constructor({ axes = { x: '+x', y: '+y', z: '+z' }, ...rest }) {
    super(rest);
    const cols = ['x', 'y', 'z'].map((k) => {
      const a = AXES[axes[k]];
      if (!a) throw new Error(`Imu: bad axis mapping ${k} → ${axes[k]}`);
      return new THREE.Vector3(...a);
    });
    /** model-frame vector → sensor-frame vector */
    this.toSensor = new THREE.Matrix3().set(...cols[0].toArray(), ...cols[1].toArray(), ...cols[2].toArray());
    this.#prevQ = null;
    this.#gyro = new THREE.Vector3();
  }

  #prevQ;
  #gyro;
  #q = new THREE.Quaternion();
  #dq = new THREE.Quaternion();
  #v = new THREE.Vector3();

  /** Orientation of the IMU in world space. */
  #worldQuat() {
    return this.object3d.getWorldQuaternion(this.#q);
  }

  update(dt) {
    if (!this.host || dt <= 0) return false;
    const q = this.#worldQuat();
    if (this.#prevQ) {
      // body-frame angular velocity: dq = q_prev⁻¹ · q
      this.#dq.copy(this.#prevQ).invert().multiply(q);
      if (this.#dq.w < 0) { this.#dq.x *= -1; this.#dq.y *= -1; this.#dq.z *= -1; this.#dq.w *= -1; }
      const angle = 2 * Math.acos(Math.min(1, this.#dq.w));
      const s = Math.sqrt(1 - this.#dq.w * this.#dq.w);
      const w = this.#v.set(0, 0, 0);
      if (s > 1e-6) w.set(this.#dq.x / s, this.#dq.y / s, this.#dq.z / s).multiplyScalar(angle / dt);
      this.#gyro.lerp(w, 1 - Math.exp(-dt * 25));
    } else {
      this.#prevQ = new THREE.Quaternion();
    }
    this.#prevQ.copy(q);
    return this.#gyro.lengthSq() > 1e-6;
  }

  read() {
    const q = this.#worldQuat();
    const inv = q.clone().invert();
    // At rest an accelerometer reads the reaction to gravity: +1 g "up".
    const a = UP.clone().applyQuaternion(inv).applyMatrix3(this.toSensor);
    const shake = this.host?.vibrating ? 0.15 : 0;
    if (shake) a.addScalar((Math.random() - 0.5) * shake);
    const g = this.#gyro.clone().applyMatrix3(this.toSensor).multiplyScalar(180 / Math.PI);
    const r = (n) => Math.round(n * 1000) / 1000;
    return { accel: { x: r(a.x), y: r(a.y), z: r(a.z) }, gyro: { x: r(g.x), y: r(g.y), z: r(g.z) } };
  }

  handle(cmd) {
    if (cmd.type === 'imu' || cmd.type === 'read') return this.read();
    return super.handle(cmd);
  }

  getState() {
    return this.read();
  }
}
