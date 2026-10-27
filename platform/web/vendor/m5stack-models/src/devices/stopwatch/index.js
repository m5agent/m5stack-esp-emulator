import * as THREE from 'three';
import {Device,Button,materials} from '../../core/index.js';
import {RoundDisplay} from '../../modeling/RoundDisplay.js';
import {addCadParts} from '../../modeling/cad.js';
import {socket,grove,header,disc,screw,slab,mesh} from '../../modeling/parts.js';
import {printedFilm} from '../../modeling/artwork.js';
import {DIM} from './dimensions.js';
import data from './geometry-data.js';
export class StopWatch extends Device {
 static meta={id:'m5stack.stopwatch',name:'StopWatch',sku:'C152',revision:'visual-reference-2026-10-25',size:[52,52,15.5],vendor:'M5Stack',keymap:{KeyA:'a',KeyB:'b',KeyP:'power'}};
 build(){
  const parts=addCadParts(this,data,{black:materials.plastic(0x202326,{roughness:.8,clearcoat:.02})});
  for(const [part,id,gpio] of [['key-a','a','G2'],['key-b','b','G1'],['power-key','power',null]]){const m=parts[part];this.add(new Button({id,label:id==='power'?'Power key':`Key ${id.toUpperCase()}`,mesh:m,travel:.22,axis:id==='a'?[.7,-.7,0]:id==='b'?[-.7,-.7,0]:[.7,.7,0],meta:{...(gpio?{gpio}:{}),role:'visual-control'}}));}
  disc(this.body,25.25,[0,0,7.52],materials.glossy(0x050607,{roughness:.19}));
  this.add(new RoundDisplay({id:'lcd',label:'1.75-inch round AMOLED 466×466',width:466,height:466,diameter:DIM.displayDiameter,position:[0,0,DIM.displayZ],style:'oled',pixelEffect:true,touch:true,blackLevel:0,glass:{size:[DIM.glassDiameter,DIM.glassDiameter],offset:.18,intensity:.2,roughness:.11},meta:{shape:'circle',role:'external-framebuffer'}}));
  socket(this,{...DIM.usb});
  const portHousing=grove(this,{...DIM.grove,face:'bottom',w:9,h:4.1,color:0xd9dcd5});
  const radial=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),DIM.grove.radialRotation);
  portHousing.quaternion.premultiply(radial);
  const port=this.get('grove');port.object3d.quaternion.premultiply(radial);port.meta.face='rim';port.meta.outward=[Math.SQRT1_2,-Math.SQRT1_2,0];
  const sockets=[[-16.5,0,7],[16.5,1.27,6]];
  const clearances=sockets.flatMap(([x,y,count])=>Array.from({length:count},(_,i)=>({w:1.85,h:1.85,r:.12,cx:x,cy:y+(i-(count-1)/2)*2.54})));
  const pcb=slab(this.body,44,44,.8,22,[0,0,-6.2],materials.plastic(0x29372e,{roughness:.9}),clearances,.06);pcb.name='Rear main PCB';
  mesh(this.body,new THREE.CylinderGeometry(6.5,6.5,.8,64).rotateX(Math.PI/2),materials.plastic(0x101413,{roughness:1}),[0,17.5,-5.85],'Speaker acoustic backing');
  for(const [x,y,count]of sockets)header(this.body,{position:[x,y,-7.52],cols:1,rows:count});
  // The official uncut label bridges the four round CAD recesses. Its source
  // alpha retains the speaker's U-shaped opening and side header notches.
  printedFilm(this,{parent:parts['body-shell'],url:new URL('./artwork/rear.png',import.meta.url).href,size:[36.6,35.3],position:[0,0,-7.52],face:'back',holes:clearances.map(({w,h,r,cx,cy})=>({w,h,r,cx:-cx,cy})),name:'StopWatch official rear circuit sticker'});
  for(const x of [-20,20])screw(this.body,[x,0,-7.52],'back',1.3);
 }
}
export default StopWatch;
