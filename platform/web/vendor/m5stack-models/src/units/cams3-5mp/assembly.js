import * as THREE from 'three';
import {Component,Port,Led,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,header} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function tube(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);const h=new THREE.Path();h.absarc(0,0,inner,0,Math.PI*2,false);s.holes.push(h);return solid(parent,s,depth,position,material,name);}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,72).rotateX(Math.PI/2),material,position,name);}
function pcb(host){
 const s=roundedRect(21.5,36.9,2.1),board=solid(host.body,s,.8,[0,0,-1.65],materials.plastic(0x294f37,{roughness:.92}),'CamS3-5MP complete physical main PCB');
 return board;
}
function camera(host){
 const g=new THREE.Group();g.name='PY260 fixed-focus optical and FPC assembly';g.position.set(spec.camera.center[0],spec.camera.center[1],0);host.body.add(g);
 const black=materials.plastic(0x101518,{roughness:.65}),flexMat=materials.plastic(0xb47824,{roughness:.83}),gold=materials.metal(0xc2a654,{roughness:.46});
 const sensorCarrier=mesh(g,new THREE.BoxGeometry(8.2,8.2,.7),materials.plastic(0x30402c,{roughness:.82}),[0,0,.05],'PY260 ceramic sensor carrier');
 const sensor=mesh(g,new THREE.BoxGeometry(3.5,2.8,.22),materials.plastic(0x22232e,{roughness:.15,clearcoat:1}),[0,0,.51],'PY260 physical image-sensor die');
 const barrel=tube(g,spec.camera.barrelRadiusMm,1.22,4.55,[0,0,.8],black,'PY260 fixed-focus annular lens barrel');
 const frontRing=tube(g,3.48,.92,.45,[0,0,4.8],materials.plastic(0x171a1c,{roughness:.54}),'PY260 stepped optical retaining rim');
 const glass=cylinder(g,.91,.22,[0,0,5.04],materials.plastic(0x244c42,{roughness:.08,clearcoat:1,metalness:.24}),'PY260 recessed physical front optical glass');
 const rearGlass=cylinder(g,1.08,.18,[0,0,1.15],materials.plastic(0x23352e,{roughness:.14,clearcoat:1}),'PY260 inner optical element');
 // Optical elements are fixed. There is no invented focus, shutter, tilt or pan joint.
 const flex=mesh(g,new THREE.BoxGeometry(7.0,6.2,.12),flexMat,[0,-6.1,-.04],'PY260 amber camera FPC tongue');
 const fold=mesh(g,new THREE.BoxGeometry(7,1.0,.85),flexMat,[0,-9.3,-.45],'PY260 physical FPC folded tail');
 const connectorBody=mesh(g,new THREE.BoxGeometry(13.3,3.0,.85),materials.plastic(0xdfdfcb,{roughness:.74}),[0,-10.8,-.425],'PY260 24-pin 0.5mm-pitch FPC connector');
 const latch=mesh(g,new THREE.BoxGeometry(13.1,.7,.45),black,[0,-11.9,.06],'PY260 FPC retaining latch');
 const contacts=[];for(let i=0;i<24;i++)contacts.push(mesh(g,new THREE.BoxGeometry(.19,1.0,.14),gold,[(i-11.5)*.5,-10.4,.06],'PY260 recessed FPC contact '+(i+1)));
 return{group:g,sensorCarrier,sensor,barrel,frontRing,glass,rearGlass,flex,fold,connectorBody,latch,contacts};
}
function radioModule(host){
 const g=new THREE.Group();g.name='ESP32-S3-WROOM-1 physical module and shield';host.body.add(g);
 const substrate=mesh(g,new THREE.BoxGeometry(18,25.5,.7),materials.plastic(0x252b23,{roughness:.86}),[0,5.0,-2.0],'ESP32-S3-WROOM module substrate');
 const shield=solid(g,roundedRect(16.1,17.4,.36),3.0,[0,2.6,-5.23],materials.metal(0xb4b9b5,{roughness:.57}),'ESP32-S3-WROOM physical RF shield in native rear window');
 const antenna=mesh(g,new THREE.BoxGeometry(17.8,6.6,.16),materials.plastic(0x1d2a1f,{roughness:.88}),[0,14.45,-2.44],'ESP32-S3-WROOM actual PCB antenna region');
 const contacts=[];for(const x of[-8.85,8.85])for(let i=0;i<14;i++)contacts.push(mesh(g,new THREE.BoxGeometry(.52,.68,.24),materials.metal(0xc2ab66,{roughness:.47}),[x,-6.6+i*1.27,-2.37],'ESP32-S3-WROOM castellated solder pad'));
 return{group:g,substrate,shield,antenna,contacts};
}
function cardSocket(host){
 const g=new THREE.Group();g.name='CamS3-5MP true microSD socket';host.body.add(g);
 const steel=materials.metal(0xb9bdb8,{roughness:.47}),black=materials.plastic(0x1c231e,{roughness:.82}),gold=materials.metal(0xc2ab62,{roughness:.44});
 const floor=mesh(g,new THREE.BoxGeometry(13.6,14.5,.24),black,[0,-12.55,-2.95],'microSD physical insulating carrier');
 const roof=mesh(g,new THREE.BoxGeometry(13.6,14.5,.2),steel,[0,-12.55,-4.7],'microSD folded metal roof behind native window');
 const walls=[];for(const x of[-6.65,6.65])walls.push(mesh(g,new THREE.BoxGeometry(.3,14.5,1.75),steel,[x,-12.55,-3.825],'microSD folded side rail'));
 const stop=mesh(g,new THREE.BoxGeometry(13,.35,1.5),black,[0,-5.475,-3.825],'microSD recessed insertion stop');
 const contacts=[];for(let i=0;i<8;i++)contacts.push(mesh(g,new THREE.BoxGeometry(.45,4.1,.2),gold,[(i-3.5)*1.1,-8.7,-3.21],'microSD recessed spring contact '+(i+1)));
 for(const x of[-6.85,6.85])for(const y of[-7,-17.5])mesh(g,new THREE.BoxGeometry(.8,1.8,.3),steel,[x,y,-2.9],'microSD soldered metal retention tab');
 const port=host.add(new Port({id:'sd',label:'microSD socket',connector:'microsd',position:spec.sd.position,quaternion:portQuaternion('bottom'),hitSize:[12,1,1.1],meta:{role:'visual-connector',face:'bottom',scope:'Physical socket only; no image storage, card state, filesystem or firmware behavior'}}));return{group:g,floor,roof,walls,stop,contacts,port};
}
function headers(host){
 const groups=spec.headers.x.map((x,i)=>{const h=header(host.body,{position:[x,spec.headers.y,-5.18],face:'back',cols:1,rows:3,pitch:spec.headers.pitchMm});h.name='CamS3-5MP physical 1x3 '+(i===0?'download':'expansion')+' female socket';return h;});
 const ports=spec.headers.x.map((x,i)=>host.add(new Port({id:i===0?'download':'expansion',label:i===0?'EN / G0 / GND':'G44 / G43 / 5V',connector:'female-1x3-2.54mm',position:[x,spec.headers.y,-5.38],quaternion:portQuaternion('back'),hitSize:[2.6,1,7.62],pins:spec.headers.pins[i].map(name=>({name})),meta:{role:'visual-connector',face:'back',pitchMm:2.54,scope:'Real three-contact header appearance only; no boot, reset, flashing or GPIO execution'}})));
 return{groups,ports};
}
function microphone(host){
 const g=new THREE.Group();g.name='CamS3-5MP PDM physical microphone';g.position.set(6.1,-2.15,.35);host.body.add(g);
 const body=tube(g,1.35,.25,.8,[0,0,0],materials.metal(0xa6afa8,{roughness:.6}),'PDM microphone metal can with true acoustic bore');
 const diaphragm=cylinder(g,.26,.08,[0,0,.05],materials.plastic(0x151a17,{roughness:.87}),'PDM microphone recessed diaphragm');
 return{group:g,body,diaphragm};
}
class BlueStatusLed extends Led{set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:spec.led.color});}}
export function buildCamS3FiveMP(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe7e9e4,{roughness:.78})}),board=pcb(host),optics=camera(host),radio=radioModule(host),sd=cardSocket(host),debug=headers(host),mic=microphone(host);
 const socket=connector(host.body,40,true,{height:5.2});socket.position.z=-1;socket.name='CamS3-5MP white open-top Grove USB-UART connector';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'Grove · USB/UART physical connector',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name,color:['black','red','yellow','white'][i]})),meta:{role:'visual-connector',face:'bottom',protocol:'USB/UART appearance only',scope:'Physical four-wire attachment only; no USB enumeration, UART, camera data, firmware or power behavior'}}));
 const ledLens=new THREE.Mesh(new THREE.BoxGeometry(1.0,.65,.35),materials.plastic(0xa9bbcd,{roughness:.36}));ledLens.name='CamS3-5MP D1 blue 0603 physical LED lens';
 const led=host.add(new BlueStatusLed({id:'status-led',label:'G14 · programmable blue indicator',mesh:ledLens,position:spec.led.position,color:spec.led.color,radius:.3,glowSize:2.6,meta:{role:'externally-driven-indicator',color:'fixed-blue',scope:'Independent external on/brightness appearance only; no capture, network, power or firmware status'}}));
 led.glow.position.set(.5,-2.6,-1.7);
 const ledCarrier=mesh(host.body,new THREE.BoxGeometry(1.6,.8,.35),materials.plastic(0xddd9c6,{roughness:.8}),[-6,-17.2,.35],'CamS3-5MP LED physical 0603 carrier');
 host.add(new Component({id:'sensor',label:'PY260 fixed-camera visual anchor',meta:{role:'visual-anchor',sensor:'PY260',focus:'fixed',scope:'No camera capture, image frames, recognition, network, microphone data, card/filesystem, firmware or electrical behavior'}}));
 const stickers=addStickers(host,{native,radio});
 host.camS3Assembly={native,board,optics,radio,sd,debug,mic,socket,port,led,ledCarrier,stickers};
}
