import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {RgbAppearance} from './RgbAppearance.js';
import {addStickers} from './stickers.js';

function board(host){
 const outline=new THREE.Shape();
 outline.moveTo(-10.5,-10.5);outline.lineTo(10.5,-10.5);outline.lineTo(10.5,4.4);outline.lineTo(5.1,4.4);outline.lineTo(4.5,5.2);outline.lineTo(4.5,10.8);outline.lineTo(-4.5,10.8);outline.lineTo(-4.5,5.2);outline.lineTo(-5.1,4.4);outline.lineTo(-10.5,4.4);outline.closePath();
 const bore=new THREE.Path();bore.absarc(0,4,1.2,0,-Math.PI*2,true);outline.holes.push(bore);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(outline,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x23714d,{roughness:.9}),[0,0,-1.2],'ChainBus shaped PCB with actual retaining bore and mounting reliefs');
 pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x222722),metal=materials.metal(0xb6baaa),ceramic=materials.plastic(0xb4a07a);
 const mcu=slab(host.body,4,4,.8,.12,[0,-3.5,0],dark,[],.015);mcu.name='ChainBus STM32G031G8U6 28-pad package envelope';
 const pads=[];
 for(const side of[-1,1])for(let i=0;i<7;i++){
  pads.push(mesh(host.body,new THREE.BoxGeometry(.42,.24,.13),metal,[side*2.03,-3.5+(i-3)*.5,-.365],'ChainBus MCU physical perimeter pad'));
  pads.push(mesh(host.body,new THREE.BoxGeometry(.24,.42,.13),metal,[(i-3)*.5,-3.5+side*2.03,-.365],'ChainBus MCU physical perimeter pad'));
 }
 const ldo=slab(host.body,1.3,2.9,.9,.12,[3,6,.05],dark,[],.01);ldo.name='ChainBus ME6211A33M3G fixed LDO package';
 for(const y of[5.05,6.95])mesh(host.body,new THREE.BoxGeometry(.65,.35,.14),metal,[2.25,y,-.33],'ChainBus LDO physical terminal');
 mesh(host.body,new THREE.BoxGeometry(.65,.35,.14),metal,[3.75,6,-.33],'ChainBus LDO physical terminal');
 const passives=[];
 for(const [name,x,y] of [['R2',-2.5,4.8],['C1',-3.3,3],['C3',2.5,-.5],['C5',3.2,8.8],['C6',-3,0],['C7',1.8,7.5],['C8',3,4],['C12',2,-7]]){
  const q=slab(host.body,1.2,.7,.5,.03,[x,y,-.15],name[0]==='R'?dark:ceramic,[],.005);q.name='ChainBus populated '+name+' fixed schematic envelope';passives.push(q);
  for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.18,.7,.12),metal,[x+sign*.52,y,-.35],'ChainBus passive physical termination');
 }
 const led=slab(host.body,2,2,.7,.08,[0,-7,-.05],materials.plastic(0xe0e4da),[],.01);led.name='ChainBus actual WS2812C-2020 package below native guide';
 for(const x of[-.8,.8])for(const y of[-7.7,-6.3])mesh(host.body,new THREE.BoxGeometry(.35,.45,.12),metal,[x,y,-.35],'ChainBus RGB package solder pad');
 const debugPads=[];for(let i=0;i<5;i++)debugPads.push(mesh(host.body,new THREE.CylinderGeometry(.4,.4,.04,24).rotateX(Math.PI/2),materials.metal(0xbda151),[-4+i*2,-7.5,-1.22],'ChainBus fixed SWD solder pad'));
 return {pcb,mcu,pads,ldo,passives,led,debugPads};
}

function chainSocket(host,id){
 const cfg=spec[id],frame=new THREE.Group();frame.name='ChainBus '+id+' actual cyan HY2.0-4P board socket';frame.position.fromArray(cfg.position);frame.quaternion.copy(portQuaternion(cfg.face));host.body.add(frame);
 const plastic=materials.plastic(cfg.color,{roughness:.65}),metal=materials.metal(0xbcb59b),box=(size,position,name,material=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),material,position,'ChainBus '+id+' '+name);
 for(const sign of[-1,1]){
  box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'full side rail');
  box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'top retaining rail');
  box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');
 }
 box([8.7,5.9,.65],[0,-2.85,-1.475],'socket floor');
 const rear=box([8.7,.65,3.75],[0,-5.475,.075],'recessed dielectric rear carrier');
 box([4.8,1,.45],[0,-2.5,2.375],'retaining bridge');
 const contacts=[];
 for(let i=0;i<4;i++){
  contacts.push(box([.42,4.1,.42],[(i-1.5)*2,-2.85,.05],'real recessed contact '+(i+1),metal));
  box([.42,.42,1.45],[(i-1.5)*2,-5.1,-1.125],'retained solder leg '+(i+1),metal);
 }
 const names=id==='grove'?['GND','5V','RX1','TX1']:['GND','5V','TX2','RX2'];
 const port=host.add(new Port({id,label:id==='grove'?'ChainBus IN':'ChainBus OUT',connector:'grove',position:cfg.position,quaternion:portQuaternion(cfg.face),hitSize:[10,1,4.4],pins:names.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:cfg.face,physicalFamily:'HY2.0-4P socket',printedTopToBottom:cfg.printedTopToBottom,pinScope:'Literal documentary labels only;not color-to-terminal routing or resolved MCU UART numbering',scope:'Mechanical family and four physical contacts/cable pose only;no protocol,electrical or firmware interoperability'}}));
 return {frame,rear,contacts,port};
}

function extensionPlug(host){
 const plastic=materials.plastic(0xe9ebe5,{roughness:.68}),metal=materials.metal(0xbcb59d),s=roundedRect(...[spec.ext.bodyMm[0],spec.ext.bodyMm[2],.18]);
 for(let i=0;i<4;i++)s.holes.push(roundedRect(...spec.ext.chamberMm,.08,{cx:(i-1.5)*spec.ext.pitchMm,path:new THREE.Path(),clockwise:true}));
 const nose=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:spec.ext.bodyMm[1],bevelEnabled:false,curveSegments:24}).rotateX(Math.PI/2),plastic,spec.ext.position,'ChainBus actual fixed white EXT four-chamber plug housing');
 nose.userData={role:'physical-ext-plug',matingFamily:'HY2.0-4P plug',installationInferred:true};
 const contacts=[],tails=[];
 for(let i=0;i<4;i++){
  const x=(i-1.5)*2;
  const contact=new THREE.Group();contact.name='ChainBus EXT recessed socket contact '+(i+1);host.body.add(contact);contacts.push(contact);
  for(const sign of[-1,1])mesh(contact,new THREE.BoxGeometry(.09,2.2,.75),metal,[x+sign*.265,16,.8],'ChainBus EXT contact spring wall');
  mesh(contact,new THREE.BoxGeometry(.62,2.2,.09),metal,[x,16,.43],'ChainBus EXT retained contact floor');
  mesh(contact,new THREE.BoxGeometry(.62,.15,.85),metal,[x,14.95,.8],'ChainBus EXT retained contact rear');
  tails.push(mesh(host.body,new THREE.BoxGeometry(.36,2.6,.25),metal,[x,11.9,.8],'ChainBus EXT fixed terminal tail'));
  tails.push(mesh(host.body,new THREE.BoxGeometry(.36,.35,1.25),metal,[x,10.75,.3],'ChainBus EXT fixed board termination'));
 }
 const port=host.add(new Port({id:'ext',label:'Unit EXT · fixed HY2.0-4P plug',connector:spec.ext.connector,position:spec.ext.position,quaternion:portQuaternion('top'),hitSize:[8.4,1,3.3],pins:['GND','5V','SDA/IO/ADC','SCL/IO/ADC'].map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'top',physicalFamily:'Fixed HY2.0-4P four-chamber plug',scope:'Plug mating frame only;ordinary GroveModule cable plugs do not fit this plug.Use DirectModule to place this actual plug in a host socket.No protocol,gender inference,electrical or firmware behavior'}}));
 return {nose,contacts,tails,port};
}

function adhesive(host){
 const plastic=materials.plastic(0xe1e3df,{roughness:.9}),[fw,fh]=spec.labels.front.size,fr=.25,front=new THREE.Shape();
 front.moveTo(-fw/2,-fh/2);front.lineTo(-fr,-fh/2);front.absarc(0,-fh/2,fr,Math.PI,0,true);front.lineTo(fw/2,-fh/2);front.lineTo(fw/2,fh/2);front.lineTo(-fw/2,fh/2);front.closePath();
 const frontFilm=mesh(host.body,new THREE.ExtrudeGeometry(front,{depth:.04,bevelEnabled:false,curveSegments:32}),plastic,[0,-3,3.82],'ChainBus independent physical front pin-strip adhesive film');frontFilm.userData={role:'physical-label-substrate',face:'front'};
 const [w,h]=spec.labels.back.size,r=1.3,n=3.1,back=new THREE.Shape();back.moveTo(-w/2+r,-h/2);back.lineTo(w/2-r,-h/2);back.quadraticCurveTo(w/2,-h/2,w/2,-h/2+r);back.lineTo(w/2,h/2-r);back.quadraticCurveTo(w/2,h/2,w/2-r,h/2);back.lineTo(n,h/2);back.absarc(0,h/2,n,0,-Math.PI,true);back.lineTo(-w/2+r,h/2);back.quadraticCurveTo(-w/2,h/2,-w/2,h/2-r);back.lineTo(-w/2,-h/2+r);back.quadraticCurveTo(-w/2,-h/2,-w/2+r,-h/2);back.closePath();
 const backFilm=mesh(host.body,new THREE.ExtrudeGeometry(back,{depth:.04,bevelEnabled:false,curveSegments:48}),plastic,[0,-3.45,-3.86],'ChainBus independent physical rear die-cut adhesive film');backFilm.userData={role:'physical-label-substrate',face:'back'};
 return {front:frontFilm,back:backFilm};
}

function fixing(host){
 const metal=materials.metal(0xaeb5b3,{roughness:.38}),s=new THREE.Shape();s.absarc(0,0,1.55,0,Math.PI*2,false);const hole=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;if(i)hole.lineTo(x,y);else hole.moveTo(x,y);}hole.closePath();s.holes.push(hole);
 const head=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.5,bevelEnabled:false,curveSegments:48}),metal,[0,4,-3.97],'ChainBus actual fixed rear hex-socket retaining head');
 const floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.12,6).rotateX(Math.PI/2),metal,[0,4,-3.44],'ChainBus real recessed hex-socket floor');
 const shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,5.9,32).rotateX(Math.PI/2),metal,[0,4,-.52],'ChainBus fixed retaining screw shank');return {head,floor,shank};
}

export function buildChainBus(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe4e7e2,{roughness:.8}),guide:materials.plastic(0xaeb9b4,{roughness:.42})}),electronics=board(host),input=chainSocket(host,'grove'),output=chainSocket(host,'out'),extension=extensionPlug(host),films=adhesive(host),screw=fixing(host),lens=parts['ChainBus complete native RGB light guide'],rgb=host.add(new RgbAppearance(lens,spec.rgb.position));
 host.chainbusAssembly={parts,electronics,input,output,extension,films,screw,lens,rgb};host.unitStickers=addStickers(host);
}
