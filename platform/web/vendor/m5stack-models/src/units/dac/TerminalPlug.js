/** MIT; original U012 removable two-pole plug appearance. */
import * as THREE from 'three';
import {Module,materials} from '../../core/index.js';
import {mesh} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {solid,circleHole} from './geometry.js';
import {addPolarity} from './stickers.js';
import {spec} from './dimensions.js';
export class TerminalPlug extends Module{
 static meta={id:'m5stack.unit.dac.terminal-plug',name:'U012 original removable2P terminal',sku:'U012 accessory',connector:'m5.u012.2p-terminal'};
 build(){const frame=new THREE.Group();frame.name='DAC original orange removable2P terminal';this.body.add(frame);const plastic=materials.plastic(0xf28b3d,{roughness:.65}),metal=materials.metal(0xb1afa1,{roughness:.48});const box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'DAC2P plug '+n);
 const tongueShape=roundedRect(7.6,3.35,.12);for(const x of spec.terminal.pinX)tongueShape.holes.push(roundedRect(1.1,.9,.09,{cx:x,cy:-.55,path:new THREE.Path(),clockwise:true}));const tongue=solid(frame,tongueShape,.75,[0,0,0],plastic,'DAC2P bored insertion tongue');tongue.rotation.x=Math.PI/2;
 const floor=box([8,9.5,.55],[0,4.75,-1.825],'channel floor'),deck=box([8,9.5,.525],[0,4.75,1.8125],'front deck'),walls=[];for(const x of[-3.75,0,3.75])walls.push(box([.5,9.5,3.1],[x,4.75,0],'retained pole partition'));
 const entryShape=roundedRect(8,4.2,.13);for(const x of spec.terminal.pinX)circleHole(entryShape,x,-.2,1.18);const entry=solid(frame,entryShape,.65,[0,9.6,0],plastic,'DAC2P real open wire entries');entry.rotation.x=Math.PI/2;
 const springs=[],cages=[];for(const x of spec.terminal.pinX){for(const sign of[-1,1])springs.push(box([.13,1.6,.68],[x+sign*.39,.2,-.55],'recessed mating spring',metal));cages.push(box([2.65,.25,2.6],[x,1.9,-.15],'deep clamp rear web',metal));cages.push(box([2.65,6.7,.18],[x,5.3,-1.35],'lower conductor',metal));for(const sign of[-1,1])cages.push(box([.15,6.7,2.6],[x+sign*1.25,5.3,-.15],'clamp cage side',metal));}
 const film=box([7.65,4.1,.025],[0,2.35,2.0875],'physical polarity film');film.material=materials.plastic(0xf0ede5,{roughness:.85});film.userData.role='physical-label-substrate';this.dacTerminalAssembly={frame,tongue,floor,deck,walls,entry,springs,cages,film};this.unitStickers=addPolarity(this,film);}
}
