# Grove cable and Unit pose API

The same connection interface works with every implemented Grove Unit in `catalog/products.json`. It adds appearance geometry and pose controls: two fitted HY2.0-4P cable plugs and four black/red/yellow/white wires. It does not add voltage, bus traffic, sensor readings or firmware behavior.

Roller485 U182 uses its fixed front-facing `grove` mouth as the Module input. Its separate `grove-top` belongs to the rotating output assembly; nested paths such as `grove/grove-top/sensor` remain valid as `grove/rotor` moves. Attached poses are relative to that moving port, and cable endpoints follow its actual transform. PWR485 and debug connectors are separate visual connector families and are excluded from the Grove menu. This geometry does not transmit power, I2C or RS485 signals through a slip ring.

## Connect a Unit

```js
import {loadModel, loadGroveModule} from './src/loaders.js';

const host = await loadModel('atoms3r');
const unit = await loadGroveModule('env-iii', {
  cableLength: 70,
  cable: {slack: 16, bend: [0, 0, -1]},
});
host.port('grove').attach(unit);

// These components are also available through the host's nested paths.
const frame = host.get('grove/unitFrame');
const cable = host.get('grove/cable');
frame.setDistance(90);
frame.setPose({position: [20, 110, 0], rotation: [0.1, -0.2, 0.3]});
cable.setOptions({slack: 20, bend: [0, 0, -1]});
```

`cableLength` preserves the previous option's placement meaning: the initial mouth-to-mouth distance in millimetres, minimum 12. The default is 35. The default pose is solved from the Unit's actual `grove` Port, including its offset in Z, so both ends meet their sockets. It does not infer the endpoint from nominal shell length.

Coordinates are in the host Port's local frame: +Y points out of the host, +Z points towards its front. `unitPose.position` is the Unit assembly origin in this frame; it is not the input socket position. `rotation` is an XYZ Euler rotation in radians; `quaternion` is `[x,y,z,w]` and takes precedence. Construction also accepts these fields in `unitPose`.

## Components and commands

| Component | Method | Meaning |
| --- | --- | --- |
| `unitFrame` | `setPose({position, rotation, quaternion})` | Set any supplied assembly transform fields; missing fields keep their value. |
| `unitFrame` | `setDistance(mm)` | Move the actual input mouth to `[0,mm,0]`, preserving the Unit's current rotation. |
| `unitFrame` | `getState()` | Return the assembly position/quaternion and its input Port ID. |
| `cable` | `setOptions({slack, bend})` | Set midpoint bow in mm and a nonzero bend direction in the module Port frame. |
| `cable` | `sync()` | Refresh plugs and wire geometry from current endpoint transforms; returns whether geometry changed. |
| `cable` | `getState()` | Return both mating frames, their outward normals, face distance and exposed bundle centerline length. |

```js
host.handle({type: 'pose', target: 'grove/unitFrame', distance: 85});
host.handle({type: 'pose', target: 'grove/unitFrame', rotation: [0, 0.2, 0.3]});
host.handle({type: 'cable', target: 'grove/cable', slack: 12, bend: [0, 0, -1]});
```

Setters synchronize immediately and request a render. External frameworks can instead write `unit.get('unitFrame').object3d.position/quaternion` and call their usual `host.update(dt,time)`; the cable detects endpoint changes. Its source inherits the attached host Port, so nested modules and rotated hosts retain correct mating frames. The original `sensor`, control, display and output-Port IDs are unchanged, including input-event bubbling, for example `grove/grove-1/sensor` through a HUB.

The cable follows endpoint poses and uses `slack` as an appearance control. It does not enforce a fixed material length or solve collisions with arbitrary scene objects. The initial arrangement and checked motion poses keep wires outside both enclosures; frameworks should choose outward-facing, separated poses and adjust `bend` to route around other objects. Mouths closer than 12 mm are rejected. Pose changes through `setPose` roll back on invalid separation.

For the Roller485 moved test pose (`position:[18,75,-2]`, `rotation:[0.13,-0.28,0.32]`, slack 18), choose `bend:[0,0,1]` in the module Port frame. The flat-Unit `-Z` bow crosses this product's bottom shell; the `+Z` route passes the same shell-clearance checks before and after host rotation. This is a checked routing example, not an automatic collision solver.

## Reusable helper and lifecycle

`src/modeling/grove-cable.js` exports `VisualCable`, `UnitFrame` and `buildGroveModuleAssembly`. The latter builds a Unit in its addressable pose frame and retains the existing component IDs. `VisualCable` accepts `source` and `target` as Ports or Object3D mating frames (+Y outward); it can also be reused through `bind(source,target)`.

`port.detach({dispose:false})` preserves the module for later attachment. Default detachment and host disposal release its cable buffers, components and nested modules. Geometry is rebuilt only when endpoint transforms or cable options change; replaced wire buffers are disposed immediately.

The white plug has a controlled 1.2 mm mating nose, four open contact chambers, recessed metal contacts, a latch and a molded wire retainer. All four wire endpoints exactly meet their respective retainer exits. Parallel transport and gradual ribbon twist preserve wire separation while the Unit rotates. Connector envelopes/hidden contact shapes are inferred from official product photos and the modeled socket clearances, not manufacturing drawings. The official MCP query on 2026-10-25 (`Grove Cable HY2.0 4P 四根线 两端插头 黑 红 黄 白`, product filter) confirmed the Black/Red/Yellow/White HY2.0-4P ordering in official Grove tables; product-specific pin semantics remain the existing Port metadata.

## Check

```sh
node scripts/check-grove-cable.mjs
node scripts/check-host-grove-assembly.mjs
```

The first script enumerates every implemented Grove Unit and checks rendered-wire endpoint rings, both plug frames, four-wire bend clearance, Unit pose/host rotation, insertion bounds, real AtomS3R and Cardputer-ADV enclosures, nested rotated HUB attachment, preserved IDs/events, detach/reuse and cable-buffer disposal. Counts and results are saved in `artifacts/grove-cable-check.json`; its shell rays sample wire centerline segments.

The second checks all actual source Grove interfaces on the requested hosts and CoreS3+DinBase, including StackChan at neutral, combined35-degree and pitch90-degree poses. Each case uses a real compact ENV III assembly. It samples eight rails on each rendered tube surface every two rings, prunes unrelated meshes with world-space boxes, then casts against actual mesh triangles in both directions. Its mating frames and sampled surface results are in `artifacts/host-grove-assembly-check.json`. This broadens real-enclosure coverage; it does not prove every target or arbitrary scene pose collision-free. Browser appearance and hardware fit remain separate checks.
