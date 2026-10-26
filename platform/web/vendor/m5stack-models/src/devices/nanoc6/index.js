import * as THREE from 'three';
import {Device,Led,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {slab,mesh,FACE} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import data from './geometry-data.js';
import {DIM} from './dimensions.js';
import {nanoAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
export class NanoC6 extends Device {
 static meta={id:'m5stack.nanoc6',name:'NanoC6',sku:'C125',size:[12,23.5,9.5],vendor:'M5Stack',keymap:{Space:'button'}};
 build(){
  const parts=addCadParts(this,data,{cyan:materials.plastic(0x05a9c5,{roughness:.64,clearcoat:.04})});
  nanoAssembly(this);cadButton(this,{source:parts['front-shell'],id:'button',label:'NanoC6 programmable key',position:[0,-1.7,4.75],w:7.3,h:7.3,r:.75,depth:1.1,travel:.16,meta:{gpio:'G9'}});
  // Official right-side IR window: retain the opening around the physical emitter.
  // The seat/lens dimensions are photo-derived; the position follows the CAD aperture.
  const ir=new THREE.Group();ir.name='IR emitter assembly';ir.position.set(5.6,2.45,.5);ir.quaternion.copy(FACE.right);this.body.add(ir);
  slab(ir,2.5,1.55,.7,.15,[0,0,-.25],materials.plastic(0x242a26,{roughness:.86}),[],.04);
  mesh(ir,new THREE.CylinderGeometry(.64,.72,.35,24).rotateX(Math.PI/2),materials.plastic(0x454b43,{roughness:.64}),[0,0,.22],'IR emitter package');
  const irLens=mesh(ir,new THREE.SphereGeometry(.64,24,16),materials.glossy(0x333c30,{roughness:.2,clearcoat:.25}),[0,0,.37],'IR optical lens');irLens.scale.z=.55;
  this.add(new Led({id:'rgb',label:'RGB light aperture',radius:.45,glowSize:1.8,position:[-5.57,4.85,-1.55],quaternion:FACE.left,lensColor:0xdce2da,meta:{role:'externally-driven-visual'}}));
  addStickers(this);
 }
}
export default NanoC6;
