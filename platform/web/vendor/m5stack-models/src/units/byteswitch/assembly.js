import * as THREE from 'three';
import {Component,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {ToggleButton} from './ToggleButton.js';
import {spec,CHANNELS} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

function hole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,position,name);}
function annulus(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,-Math.PI*2,true);hole(s,0,0,inner);return solid(parent,s,depth,position,material,name);}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,40).rotateX(Math.PI/2),material,position,name);}

function board(host){
 const s=new THREE.Shape(),x=10.5,r=4.3,dx=x-8,dy=Math.sqrt(r*r-dx*dx),theta=Math.acos(dx/r);
 // Clockwise exterior with open relief around all four native bosses and both
 // connectors. Closed holes are confined to the interior central screw seats.
 s.moveTo(-5.6,-42);s.lineTo(-6.5,-42);s.lineTo(-x,-38);
 for(const y of [-32,32]){s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+theta,Math.PI-theta,false);}
 s.lineTo(-x,38);s.lineTo(-6.5,42);s.lineTo(-5.6,42);s.lineTo(-5.6,36.5);s.lineTo(5.6,36.5);s.lineTo(5.6,42);s.lineTo(6.5,42);s.lineTo(x,38);
 for(const y of [32,-32]){s.lineTo(x,y+dy);s.absarc(8,y,r,theta,Math.PI*2-theta,false);}
 s.lineTo(x,-38);s.lineTo(6.5,-42);s.lineTo(5.6,-42);s.lineTo(5.6,-36.5);s.lineTo(-5.6,-36.5);s.closePath();
 for(const y of [-32,32])hole(s,0,y,2.15);
 const pcb=solid(host.body,s,.8,[0,0,-3.2],materials.plastic(0x254234,{roughness:.91}),'ByteSwitch physical PCB with four open boss and two Grove reliefs');
 pcb.userData={role:'physical-pcb',scope:'Appearance reconstruction; no traces, bus or electronics simulation'};
 slab(host.body,5,5,.8,.2,[-5,0,-4],materials.plastic(0x202822,{roughness:.86}),[],.03).name='ByteSwitch concealed STM32 package';
 return pcb;
}
function toggle(host,item){
 const {number,y,physicalChannel}=item,dark=materials.plastic(0x203127,{roughness:.8}),steel=materials.metal(0xaeb8b4,{roughness:.36});
 const packageMesh=slab(host.body,4.7,5.4,4.9,.35,[0,y,-2.4],dark,[],.04);packageMesh.name=`CH${physicalChannel} fixed DPDT six-pin switch package`;
 const cover=slab(host.body,4.7,5.4,.45,.25,[0,y,2.5],steel,[],.025);cover.name=`CH${physicalChannel} fixed switch retaining cover`;
 const bushing=annulus(host.body,1.63,.97,3.5,[0,y,2.8],steel,`CH${physicalChannel} fixed hollow threaded bushing`);
 const nut=annulus(host.body,2.12,1.68,.55,[0,y,6.0],steel,`CH${physicalChannel} fixed annular panel nut`);
 const seat=annulus(host.body,1.55,1.03,.55,[0,y,6.3],steel,`CH${physicalChannel} fixed spherical pivot seat`);
 for(const sx of [-1,1])for(let i=0;i<3;i++)mesh(host.body,new THREE.BoxGeometry(.35,.55,1.15),steel,[sx*1.7,y+(i-1)*1.8,-2.7],`CH${physicalChannel} DPDT terminal ${sx>0?i+4:i+1}`);
 const lever=new THREE.Group();lever.name=`CH${physicalChannel} true hinged metal toggle lever`;
 const ball=mesh(lever,new THREE.SphereGeometry(.94,32,20),steel,[0,0,0],`CH${physicalChannel} moving pivot ball`);
 const rod=cylinder(lever,spec.toggle.rodRadius,spec.toggle.rodLength-.4,[0,0,(spec.toggle.rodLength+.4)/2],steel,`CH${physicalChannel} moving metal rod`);
 const tip=mesh(lever,new THREE.SphereGeometry(spec.toggle.rodRadius,32,16),steel,[0,0,spec.toggle.rodLength],`CH${physicalChannel} rounded toggle tip`);
 const control=host.add(new ToggleButton({id:item.switch,label:`CH${physicalChannel} stable toggle`,mesh:lever,position:[0,y,spec.toggle.pivotZ],anglesDeg:spec.toggle.anglesDeg,meta:{role:'visual-control',mechanism:'hinged-toggle',physicalChannel,detents:[0,1],axis:spec.toggle.axis,pivotMm:[0,y,spec.toggle.pivotZ],anglesDeg:spec.toggle.anglesDeg,evidence:'Official U191 drawing/photo shows tilting toggle; pivot and ±22.5 degree stops are visual estimates, not mechanical ratings',scope:'Two retained visual positions and input intent only; no DPDT truth table, sensor values, register or electrical model'}}));
 return {control,package:packageMesh,cover,bushing,nut,seat,lever,ball,rod,tip};
}
function socket(host,id,face,position){
 const g=new THREE.Group();g.name=`ByteSwitch ${id} red open-top HY2.0-4P`;g.position.fromArray(position);g.quaternion.copy(FACE[face]);host.body.add(g);
 const plastic=materials.plastic(0xb92329,{roughness:.62}),metal=materials.metal(0xb9ad86,{roughness:.4}),depth=6.6;
 const box=(size,p,name,material=plastic)=>mesh(g,new THREE.BoxGeometry(...size),material,p,`${id} ${name}`);
 for(const sign of [-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.9],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');
 box([4.8,.45,2.3],[0,2.375,-4.6],'locking bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.7],[(i-1.5)*2,.2,-3.7],`contact ${i+1}`,metal);box([.42,1.4,.42],[(i-1.5)*2,-2.7,-6.0],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id,label:id==='grove'?'PORT.A · I2C input':'PORT.A · I2C cascade',connector:'grove',position,quaternion:portQuaternion(face),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face,connectionRole:id==='grove'?'input':'cascade-output',protocol:'I2C',scope:'Physical attachment and cable pose only; no bus routing, electrical behavior or firmware'}}));
 return {object3d:g,port};
}
function lights(host,parts){
 const comb=parts['ByteSwitch native connected eight-way RGB lightpipe comb'],end=parts['ByteSwitch native end RGB lightpipe'];
 const g=comb.geometry.toNonIndexed(),p=g.attributes.position,n=g.attributes.normal,bodyPos=[],bodyNormal=[],selected=CHANNELS.map(()=>({position:[],normal:[]}));
 for(let i=0;i<p.count;i+=3){
  const channel=CHANNELS.findIndex(c=>[0,1,2].every(k=>Math.abs(p.getY(i+k)-c.y)<=1.21&&p.getZ(i+k)>5.99));
  const out=channel<0?{position:bodyPos,normal:bodyNormal}:selected[channel];
  for(let k=0;k<3;k++){out.position.push(p.getX(i+k),p.getY(i+k),p.getZ(i+k));out.normal.push(n.getX(i+k),n.getY(i+k),n.getZ(i+k));}
 }
 const geometry=out=>new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(out.position,3)).setAttribute('normal',new THREE.Float32BufferAttribute(out.normal,3));
 comb.geometry.dispose();comb.geometry=geometry({position:bodyPos,normal:bodyNormal});g.dispose();
 const rgb=selected.map((out,i)=>{
  const lens=new THREE.Mesh(geometry(out),materials.plastic(0xc6cebd,{roughness:.63}));lens.name=`CH${i} native RGB lightpipe emission face`;
  const led=host.add(new Led({id:CHANNELS[i].led,label:`CH${i} external RGB`,mesh:lens,radius:.4,glowSize:2.7,meta:{role:'externally-driven-visual',physicalChannel:i,nativeTopFaceTriangles:out.position.length/9,mapping:'Physical channel location only; not schematic LED chain index',scope:'No automatic response to toggle, input, power or communication'}}));
  led.glow.position.set(11.3,CHANNELS[i].y,6.08);return led;
 });
 end.removeFromParent();end.material=end.material.clone();
 const led=host.add(new Led({id:'rgb-9',label:'End external RGB',mesh:end,radius:.4,glowSize:2.7,meta:{role:'externally-driven-visual',location:'top end near CH7',mapping:'Physical location only; not schematic chain order',scope:'No power, switch or bus coupling'}}));led.glow.position.set(-8,43.85,.9);rgb.push(led);
 return rgb;
}
export function buildByteSwitch(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0x5f635f,{roughness:.8}),diffuser:materials.plastic(0xc6cebd,{roughness:.63})});
 const pcb=board(host),mechanisms=CHANNELS.map(item=>toggle(host,item)),rgb=lights(host,parts);
 const input=socket(host,'grove','bottom',spec.grove.input),output=socket(host,'grove-out','top',spec.grove.output);
 for(const y of [-32,32])screw(host.body,[0,y,-5.97],'back',1.4);
 host.add(new Component({id:'sensor',label:'ByteSwitch geometry anchor',meta:{role:'visual-anchor',scope:'No state-byte, I2C address, registers, DPDT electrical truth table or firmware simulation'}}));
 host.byteSwitchAssembly={pcb,mechanisms,rgb,input,output,parts};
 host.byteStickers=addStickers(host);
}
