import * as THREE from 'three';
import {Device,Button,materials} from '../../core/index.js';
import {RoundDisplay} from '../../modeling/RoundDisplay.js';
import {addCadParts} from '../../modeling/cad.js';
import {socket,grove,header,mark,disc,screw,slab,mesh} from '../../modeling/parts.js';
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
  mark(this.body,27,29,[0,-.8,-7.55],(ctx,W,H,s)=>{ctx.fillStyle='#e7e9e6';ctx.fillRect(0,0,W,H);ctx.fillStyle='#283034';ctx.font=`800 ${2.8*s}px Arial`;ctx.textAlign='center';ctx.fillText('STOP WATCH',W/2,4*s);ctx.font=`${1.4*s}px Arial`;ctx.fillText('M5Stack · C152',W/2,6.4*s);ctx.font=`${1.15*s}px Arial`;['AMOLED 466 × 466','ESP32-S3R8','USB-C 5V · 450mAh'].forEach((t,i)=>ctx.fillText(t,W/2,(9+i*2)*s));for(let i=0;i<7;i++){ctx.fillStyle=['#dfc11c','#c84536','#444c53','#82b5c4'][i%4];ctx.fillRect(1*s,(17+i*1.25)*s,(25-i%2*3)*s,.75*s);}ctx.fillStyle='#434b4f';ctx.font=`700 ${1.3*s}px Arial`;ctx.fillText('STOPWATCH',W/2,28*s);},'back');
  for(const x of [-20,20])screw(this.body,[x,0,-7.52],'back',1.3);
 }
}
export default StopWatch;
