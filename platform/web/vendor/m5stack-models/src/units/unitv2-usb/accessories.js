import * as THREE from 'three';
import {Module,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
/** Whole exact native supplied clip, statically retained; no inferred articulation. */
export class Clip extends Module{
 static meta={id:'m5stack.unit.unitv2-usb.clip',name:'UnitV2-USB supplied static clip',sku:'U078-USB accessory',connector:spec.mount.connector};
 build(){const owner=this.body,g=new THREE.Group();g.name='U078-USB static native clip mating frame';g.rotation.x=Math.PI/2;g.position.set(0,-9.2,-6);owner.add(g);this.body=g;let parts;try{parts=addCadParts(this,data.slice(2),{clip:materials.plastic(0x5b5e5a,{roughness:.78})});}finally{this.body=owner;}this.clipAssembly={frame:g,native:parts[data[2].name],parts};}
}
