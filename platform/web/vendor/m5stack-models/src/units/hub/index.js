import * as THREE from 'three';
import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,mesh,screw} from '../../modeling/parts.js';
import {unitPcb} from '../shared/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {addStickers} from './stickers.js';

function buildHub(host){
 addCadParts(host,data,{shell:materials.plastic(0xe0e3dc,{roughness:.8})});
 const pcb=unitPcb(host.body,{h:32});pcb.name='HUB parallel connector PCB';
 grove(host,{id:'grove',position:spec.input.position,face:'bottom',w:10,h:5.2,color:0xe4e5df});
 const quarterTurn=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),Math.PI/2);
 for(const output of spec.outputs){
  const group=grove(host,{id:output.id,position:output.position,face:'front',w:10,h:5,color:0xe4e5df,depth:5.8});
  group.quaternion.premultiply(quarterTurn);
  // The front-facing mating frame uses the same pin-row rotation as its housing.
  host.get(output.id).object3d.quaternion.premultiply(quarterTurn);
  group.name=`HUB ${output.id} upright socket`;
 }
 screw(host.body,[0,-4,-4.025],'back',1.4);
 host.add(new Component({id:'sensor',label:'Passive 1-to-3 connector board',meta:{role:'visual-anchor',scope:'no-bus-behavior'}}));
 addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.hub',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};
 build(){buildHub(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.hub.grove',name:spec.name,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildHub,options);
 }
}
export default Model;
