import * as THREE from 'three';

// Appearance-only placement through the public Grove assembly API. Units keep
// their actual dimensions, component paths, mating frames and event ownership.
// This policy intentionally covers one direct HUB; deeper HUB trees and caller
// supplied poses require an explicit layout instead of being silently changed.
const HUB_ID = 'm5stack.unit.hub.grove';
const OUTPUTS = ['grove-1', 'grove-2', 'grove-3'];
const COMPACT_UNITS = new Set(['env-iii', 'tof', 'color', 'button']);
const GAP = 14;
const layouts = new WeakMap();

/** Bounds of a host's own rendered geometry, excluding attached assemblies. */
export function ownAssemblyBounds(host, space = host.find('unitFrame')?.object3d || host.body) {
  host.root.updateWorldMatrix(true, true);
  const inverse = space.matrixWorld.clone().invert();
  const excluded = new Set(host.list('port').filter(port => port.host === host && port.module).map(port => port.module.root));
  const bounds = new THREE.Box3();
  const visit = object => {
    if (excluded.has(object) || !object.visible) return;
    if (object.isMesh && ![object.material].flat().every(material => material.transparent && material.opacity === 0)) {
      object.geometry.computeBoundingBox();
      const local = object.geometry.boundingBox;
      if (local && !local.isEmpty()) {
        const transform = inverse.clone().multiply(object.matrixWorld);
        bounds.union(local.clone().applyMatrix4(transform));
      }
    }
    object.children.forEach(visit);
  };
  visit(space);
  return bounds;
}

function poseInSpace(module, position, space) {
  const frame = module.get('unitFrame');
  frame.object3d.parent.updateWorldMatrix(true, false);
  space.updateWorldMatrix(true, false);
  const desired = new THREE.Matrix4().copy(space.matrixWorld).multiply(new THREE.Matrix4().makeTranslation(...position));
  const local = frame.object3d.parent.matrixWorld.clone().invert().multiply(desired);
  const translation = new THREE.Vector3(), quaternion = new THREE.Quaternion(), scale = new THREE.Vector3();
  local.decompose(translation, quaternion, scale);
  frame.setPose({position: translation.toArray(), quaternion: quaternion.toArray()});
}

function bendInPort(module, direction, space) {
  const world = new THREE.Vector3(...direction).transformDirection(space.matrixWorld);
  module.body.updateWorldMatrix(true, false);
  return world.transformDirection(module.body.matrixWorld.clone().invert()).toArray();
}

function snapshot(module) {
  const cable = module.get('cable').getState();
  return {module, pose: module.get('unitFrame').getState(), cable: {slack: cable.slack, bend: cable.bend}};
}

function applyStates(states) {
  // Parent first, then children: the saved poses use each module's own Port
  // frame. No input is generated and no component is reparented or replaced.
  for (const state of states) if (state.module.find('unitFrame')) state.module.get('unitFrame').setPose(state.pose);
  for (const state of states) if (state.module.find('cable')) state.module.get('cable').setOptions(state.cable);
}

function restore(states) {
  const current = states.map(state => snapshot(state.module));
  try { applyStates(states); }
  catch (error) {
    // One bounded rollback; never retry a permanently failing optional painter.
    try { applyStates(current); }
    catch (rollback) { throw new AggregateError([error, rollback], `Unit layout restore failed: ${error.message}; rollback: ${rollback.message}`); }
    throw error;
  }
}

export function layoutHubAttachments(model) {
  if (model.meta.id !== 'm5stack.cores3' || model.options.dinBase) return [];
  const hubs = model.list('port').filter(port => port.host === model && port.module?.meta.id === HUB_ID);
  const results = [];
  for (const source of hubs) {
    const hub = source.module;
    const children = OUTPUTS.map(id => hub.find(id, 'port')?.module || null);
    const active = [hub, ...children.filter(Boolean)];
    const previous = layouts.get(hub);
    const eligible = source.id === 'grove' && children.some(Boolean) && !hub.options.unitPose
      && children.every(child => !child || (!child.options.unitPose && COMPACT_UNITS.has(child.meta.id.split('.').at(-2))));
    if (!eligible) {
      if (previous) {
        restore([...previous.values()].filter(state => active.includes(state.module)));
        layouts.delete(hub);
      }
      continue;
    }
    const original = new Map([...(previous || [])].filter(([module]) => active.includes(module)));
    for (const module of active) if (!original.has(module)) original.set(module, snapshot(module));
    const before = active.map(snapshot);
    try {
      const space = model.body;
      const hostBounds = ownAssemblyBounds(model, space);
      const hubBounds = ownAssemblyBounds(hub);
      const childBounds = children.map(child => child ? ownAssemblyBounds(child) : null);
      if (hostBounds.isEmpty() || hubBounds.isEmpty() || childBounds.some(bounds => bounds?.isEmpty())) continue;
      // A separate full-size HUB sits beside the controller; its three children
      // form a left-to-right row above both bodies, with sockets facing the
      // cable corridor. Empty slots reserve a nominal compact Unit width;
      // actual envelopes can produce a small recenter when a slot changes.
      const z = hostBounds.max.z - hubBounds.max.z;
      const hubOrigin = [hostBounds.min.x - GAP - hubBounds.max.x,
        hostBounds.getCenter(new THREE.Vector3()).y - hubBounds.getCenter(new THREE.Vector3()).y, z];
      poseInSpace(hub, hubOrigin, space);
      const widths = childBounds.map(bounds => bounds ? bounds.max.x - bounds.min.x : 24);
      const totalWidth = widths.reduce((sum, width) => sum + width, 0) + GAP * 2;
      const left = Math.min(hubOrigin[0] + hubBounds.min.x, hostBounds.min.x);
      const right = Math.max(hubOrigin[0] + hubBounds.max.x, hostBounds.max.x);
      const rowCenter = (left + right) / 2;
      const rowBottom = Math.max(hostBounds.max.y, hubOrigin[1] + hubBounds.max.y) + 28;
      let x = rowCenter - totalWidth / 2;
      children.forEach((child, index) => {
        if (child) {
          const bounds = childBounds[index];
          const position = [x - bounds.min.x, rowBottom - bounds.min.y, hostBounds.max.z - bounds.max.z];
          poseInSpace(child, position, space);
          child.get('cable').setOptions({slack: 24, bend: bendInPort(child, [0, 1, 0.4], space)});
        }
        x += widths[index] + GAP;
      });
      // Route the controller-to-HUB cable around the left side of the controller.
      hub.get('cable').setOptions({slack: 28, bend: bendInPort(hub, [-0.3, -1, 0.2], space)});
      layouts.set(hub, original);
      results.push({port: source.path, outputs: OUTPUTS.filter((id, index) => children[index]), policy: 'direct-hub-full-size-row'});
    } catch (error) {
      restore(before);
      results.push({port: source.path, policy: 'direct-hub-full-size-row', status: 'unavailable', reason: error.message});
    }
  }
  return results;
}
