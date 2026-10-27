import * as THREE from 'three';
import {Button,Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {FACE,mesh,slab,screw,portQuaternion} from '../../modeling/parts.js';
import {unitPcb} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function socket(host,item){
 const isInput=item.id==='grove',d=spec.connector,depth=isInput?6.5:d.outputDepthMm;
 const group=new THREE.Group();group.name=`PaHUB ${isInput?'input':`CH${item.channel}`} open-top HY2.0-4P`;
 group.position.fromArray(item.position);group.quaternion.copy(isInput?FACE.bottom:new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),item.rotation));host.body.add(group);
 const red=materials.plastic(0x9f263c,{roughness:.64}),metal=materials.metal(0xbeb59b,{roughness:.4}),parts={};
 const box=(name,size,position,material=red)=>parts[name]=mesh(group,new THREE.BoxGeometry(...size),material,position,`PaHUB ${item.id} ${name}`);
 // Real walls, a recessed support and four contacts. The upper channel and
 // mating entrance remain empty; there is no shadow/photo plane across them.
 for(const sign of [-1,1]){
  box(`side rail ${sign}`,[.7,5.2,depth],[sign*4.65,0,-depth/2]);
  box(`upper lip ${sign}`,[.9,.8,depth],[sign*3.85,2.2,-depth/2]);
  box(`mouth ear ${sign}`,[.7,1.1,.6],[sign*4.65,2.05,0]);
 }
 box('floor',[8.6,.7,depth],[0,-2.25,-depth/2]);
 box('rear wall',[8.6,5.2,.6],[0,0,-depth+.3]);
 const contactEnd=1.85,supportDepth=depth-contactEnd;
 box('recessed support',[8.6,2.7,supportDepth],[0,-1.25,-contactEnd-supportDepth/2]);
 box('locking tongue',[3.4,.65,Math.min(3,depth-2)],[0,1.2,-depth+1.55]);
 for(let i=0;i<4;i++){
  const n=isInput?4-i:i+1;
  const contact=box(`contact ${n}`,[.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],metal);
  contact.userData.pin=n;
 }
 const turn=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),item.rotation),quaternion=portQuaternion(isInput?'bottom':'front');
 if(!isInput)quaternion.premultiply(turn);
 const pins=[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:isInput?'SDA':`SD${item.channel}`,color:'yellow'},{n:4,name:isInput?'SCL':`SC${item.channel}`,color:'white'}];
 const port=host.add(new Port({id:item.id,label:isInput?'PORT.A input':`CH${item.channel} output`,connector:'grove',position:item.position,quaternion,hitSize:[10,1,5.2],pins,pinGrid:{cols:4,rows:1,pitch:2,center:[0,isInput?-.15:.15],order:col=>col+1},meta:{role:'visual-connector',face:isInput?'bottom':'front',channel:item.channel??null,pinReference:'n is library cable-colour order (black/red/yellow/white), not schematic J pin numbering',scope:'Physical connection and cable pose only; no I2C channels, address, electrical or power behavior'}}));
 group.userData={visualFamily:'open-top-grove',channel:item.channel??null,scope:'Appearance only; internal connector dimensions inferred'};
 return {group,port,parts};
}
function board(host){
 const pcb=unitPcb(host.body,{h:48});pcb.name='PaHUB solid red PCB with mounting and Grove clearances';pcb.material.color.setHex(0x922637);
 const black=materials.plastic(0x202c2d,{roughness:.77}),metal=materials.metal(0xb3b4a7,{roughness:.46});
 const ic=slab(host.body,4.5,9.8,1.25,.16,[0,4.3,.9],black,[],.035);ic.name='PaHUB PCA9548AP physical package';
 for(const sign of [-1,1])for(let i=0;i<12;i++)mesh(host.body,new THREE.BoxGeometry(.85,.29,.18),metal,[sign*2.65,4.3+(i-5.5)*.65,1.03],'PaHUB IC gull-wing lead');
 for(const x of [-2.3,0,2.3]){
  slab(host.body,1.7,1.3,.6,.06,[x,11.4,.9],black,[],.015).name='PaHUB resistor array package';
  for(const sign of [-1,1])mesh(host.body,new THREE.BoxGeometry(.22,1.25,.18),metal,[x+sign*.76,11.4,1.04],'PaHUB resistor array termination');
 }
 for(const [x,y] of [[-3.7,13.4],[-3.7,-.2],[3.1,-7.9],[-3,-7.9]]){
  mesh(host.body,new THREE.BoxGeometry(.9,1.5,.5),materials.plastic(0xb6a57d,{roughness:.8}),[x,y,1.15],'PaHUB ceramic component');
  for(const sign of [-1,1])mesh(host.body,new THREE.BoxGeometry(.95,.25,.55),metal,[x,y+sign*.7,1.15],'PaHUB component termination');
 }
 return pcb;
}
function dipSwitch(host){
 const dark=materials.plastic(0x203a3c,{roughness:.74}),light=materials.plastic(0xd4dbc6,{roughness:.68});
 slab(host.body,5.6,5.2,1.7,.18,[0,-4.97,.9],dark,[],.04).name='PaHUB fixed three-pole DIP package';
 const holes=spec.dip.rowsY.map(y=>({cx:0,cy:y+4.97,w:3.4,h:.88,r:.06}));
 slab(host.body,5.6,5.2,.4,.18,[0,-4.97,2.6],dark,holes,.025).name='PaHUB slotted DIP upper carrier';
 return spec.dip.ids.map((id,index)=>{
  const cap=new THREE.Group();cap.name=`PaHUB DIP ${index+1} stable thumb`;
  slab(cap,1.2,.72,.55,.08,[0,0,0],light,[],.02);
  mesh(cap,new THREE.BoxGeometry(.18,.7,.07),light,[0,0,.57],'PaHUB DIP grip ridge');
  return host.add(new Button({id,label:`DIP ${index+1} visual position`,mesh:cap,position:[-.45,spec.dip.rowsY[index],2.8],axis:[1,0,0],travel:spec.dip.travelMm,latching:true,longPressMs:0,meta:{role:'visual-control',mechanism:'DIP slider',detents:[0,1],positionEvidence:'Three real sliders and side-to-side travel from official U040-B-V21 photos; 0.9 mm travel is an appearance estimate',scope:'Visual stable position only; no address calculation, I2C switching, power or electrical behavior'}}));
 });
}
export function buildPahub(host){
 addCadParts(host,data,{shell:materials.plastic(0xe5e8e0,{roughness:.8})});
 const pcb=board(host),input=socket(host,spec.input),outputs=spec.outputs.map(item=>socket(host,item)),dips=dipSwitch(host);
 screw(host.body,[0,spec.mountY,-3.97],'back',1.4);
 addStickers(host);
 host.add(new Component({id:'sensor',label:'PaHUB v2.1 appearance anchor',meta:{role:'visual-anchor',scope:'No I2C channel, address, data, electrical or power behavior'}}));
 host.pahubAssembly={pcb,input,outputs,dips};
}
