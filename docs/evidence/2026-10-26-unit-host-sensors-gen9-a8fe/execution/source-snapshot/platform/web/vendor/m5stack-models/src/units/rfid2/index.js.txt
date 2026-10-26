import {materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {makeUnit} from '../shared/CADUnit.js';
import {unitPcb} from '../shared/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';

const models=makeUnit(spec,data,host=>{
 const originalBoard=host.body.getObjectByName('Unit PCB');originalBoard.removeFromParent();originalBoard.geometry.dispose();originalBoard.material.dispose();
 unitPcb(host.body,{h:spec.size[1]});
 // The selected official face shell has an open antenna window. The actual
 // product has a laminated dielectric face here; keep its thickness independent
 // of any printed artwork, which awaits the user's original file.
 const c=spec.frontCover;
 const face=slab(host.body,...c.size,c.depth,.7,c.position,materials.plastic(0xdcded9,{roughness:.91,clearcoat:0}),[],.035);face.name='RFID dielectric front cover';
 // Public references do not show the hidden antenna trace or IC placement.
 // Keep those unspecified rather than inventing an internal circuit layout.
});
export const Model=models.Model;
export const GroveModule=models.GroveModule;
export default Model;
