import * as THREE from 'three';
import {Button,Component,Led,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function annulus(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,-tau,true);hole(s,0,0,inner);return solid(parent,s,depth,position,material,name);}
class WhiteLed extends Led{set(s){if(typeof s==='boolean')s={on:s};else if(typeof s==='string'||typeof s==='number')s={on:true};super.set({...s,color:0xfffaf0});}}
class RedLed extends Led{set(s){if(typeof s==='boolean')s={on:s};else if(typeof s==='string'||typeof s==='number')s={on:true};super.set({...s,color:0xff2420});}}
function board(host){
 const s=new THREE.Shape();s.moveTo(-5.5,-22.3);s.lineTo(-10.3,-22.3);s.lineTo(-10.3,-15.5);s.lineTo(-8,-15.5);s.absarc(-8,-12,3.5,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.3,-8.5);s.lineTo(-10.3,21.8);s.lineTo(10.3,21.8);s.lineTo(10.3,-8.5);s.lineTo(8,-8.5);s.absarc(8,-12,3.5,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.3,-15.5);s.lineTo(10.3,-22.3);s.lineTo(5.5,-22.3);s.lineTo(5.5,-16.6);s.lineTo(-5.5,-16.6);s.closePath();hole(s,0,-12,1.85);
 const pcb=solid(host.body,s,.8,[0,0,-4.95],materials.plastic(0x25533e,{roughness:.92}),'QRCode physical carrier PCB with native boss and Grove relief');pcb.userData={role:'physical-pcb',inferred:true};
 const dark=materials.plastic(0x1d2522,{roughness:.83}),metal=materials.metal(0xb2b3a2,{roughness:.5}),ceramic=materials.plastic(0xb1a789,{roughness:.9});
 const chip=slab(host.body,4.4,6.5,1.1,.2,[3,-5,-4.15],dark,[],.035);chip.name='QRCode U1 STM32F030F4P6 physical TSSOP20 package';for(const x of[.6,5.4])for(let i=0;i<10;i++)mesh(host.body,new THREE.BoxGeometry(.7,.3,.18),metal,[x,-5+(i-4.5)*.6,-3.98],'QRCode U1 gull wing lead');
 slab(host.body,2.9,1.7,1.1,.15,[-4.8,-5,-4.15],dark,[],.02).name='QRCode U2 HX6306P332MR regulator';
 for(const[x,y]of[[-5,3.7],[4.5,3.7],[6,0],[-7,-3],[-3,-7],[7,-7]]){mesh(host.body,new THREE.BoxGeometry(1.35,.8,.55),ceramic,[x,y,-3.88],'QRCode physical passive package');for(const dx of[-.57,.57])mesh(host.body,new THREE.BoxGeometry(.25,.8,.57),metal,[x+dx,y,-3.88],'QRCode passive solder termination');}
 const buzzer=mesh(host.body,new THREE.CylinderGeometry(4.2,4.2,3.4,64).rotateX(Math.PI/2),dark,[-5.4,2,-2.45],'QRCode fixed internal P1 buzzer can');const cap=annulus(host.body,4.2,.65,.35,[-5.4,2,-.75],dark,'QRCode buzzer top acoustic bore');const diaphragm=mesh(host.body,new THREE.CylinderGeometry(.63,.63,.1,32).rotateX(Math.PI/2),materials.plastic(0x111714,{roughness:1}),[-5.4,2,-1.2],'QRCode fixed recessed buzzer diaphragm');
 const fpcSocket=slab(host.body,8,2.6,1.6,.2,[1.7,6,-4.15],materials.plastic(0xdbd7c3,{roughness:.7}),[],.03);fpcSocket.name='QRCode FPC1 physical 12P socket';for(let i=0;i<12;i++)mesh(host.body,new THREE.BoxGeometry(.25,1.8,.15),metal,[1.7+(i-5.5)*.5,6,-3.3],'QRCode FPC1 contact');
 const ribbon=mesh(host.body,new THREE.BoxGeometry(6.5,9,.18),materials.plastic(0xc58a39,{roughness:.7}),[1.7,10.5,-3.1],'QRCode fixed internal 12P flexible ribbon');for(let i=0;i<12;i++)mesh(host.body,new THREE.BoxGeometry(.12,8.7,.02),materials.metal(0xaa7934,{roughness:.5}),[1.7+(i-5.5)*.5,10.5,-2.999],'QRCode FPC fixed copper trace');
 return{pcb,chip,buzzer,cap,diaphragm,fpcSocket,ribbon};
}
function grove(host){
 const g=new THREE.Group();g.name='QRCode pink open HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);const plastic=materials.plastic(spec.grove.color,{roughness:.68}),metal=materials.metal(0xb8b38b,{roughness:.45}),depth=6.6;
 const box=(size,p,name,m=plastic)=>mesh(g,new THREE.BoxGeometry(...size),m,p,'QRCode Grove '+name);
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.9],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.6],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.7],[(i-1.5)*2,.2,-3.7],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-6],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'UART / I2C · four physical pins',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX / SDA',color:'yellow'},{n:4,name:'UART_TX / SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocols:['UART','I2C'],scope:'Physical attachment/cable pose and pin labels only; side-slide position does not change electrical or protocol state'}}));return{group:g,contacts,port};
}
function controls(host,parts){
 const cap=parts['QRCode native independent TRIG button'];const button=host.add(new Button({id:'button',label:'TRIG scan trigger',mesh:cap,travel:spec.trigger.travelMm,axis:[0,0,-1],meta:{role:'visual-control',mechanism:'native-independent-cap',travelSource:'0.3 mm visual estimate, not a measured switch specification',scope:'Press/release/cancel shape and input intent only; no scanning, decoding, LED, beep or firmware behavior'}}));
 const dark=materials.plastic(0x151d19,{roughness:.85}),white=materials.plastic(0xd8ded3,{roughness:.65}),metal=materials.metal(0xaab2a6,{roughness:.45});
 const body=mesh(host.body,new THREE.BoxGeometry(3.3,6.1,2.1),dark,[-9.4,-.95,-3.45],'QRCode S1 fixed DPDT UART I2C slide package');for(const x of[-10.2,-8.6])for(const y of[-2.6,-1,.6])mesh(host.body,new THREE.BoxGeometry(.4,.5,.5),metal,[x,y,-4.55],'QRCode S1 solder terminal');
 const slider=mesh(new THREE.Group(),new THREE.BoxGeometry(1.2,1.4,1.25),white,[0,0,0],'QRCode real retained white mode slide cap');const mode=host.add(new Button({id:'mode',label:'UART / I2C physical mode slide',mesh:slider,position:spec.mode.position,latching:true,axis:spec.mode.axis,travel:spec.mode.travelMm,meta:{role:'visual-control',mechanism:'retained-slide',positions:['UART','I2C'],detentsMm:[0,2],evidence:'Native side opening and exact U173 side label/photo; visual travel and installed package envelope inferred',scope:'Retained visual position/input intent only; no bus switch, register, power, decoder or firmware state'}}));
 const tact=slab(host.body,6,6,2.6,.3,[0,-1.8,-4.15],dark,[],.04);tact.name='QRCode S2 fixed 6×6×5 trigger switch base';mesh(host.body,new THREE.CylinderGeometry(1.6,1.6,2.4,32).rotateX(Math.PI/2),dark,[0,-1.8,-.35],'QRCode concealed fixed trigger plunger visual envelope');return{button,mode,switchBody:body,tact};
}
function scanner(host){
 const g=new THREE.Group();g.name='QRCode fixed M14 640×480 CMOS optical engine';g.position.set(0,23.5,2.2);g.quaternion.copy(FACE.top);host.body.add(g);
 const black=materials.plastic(0x141a18,{roughness:.86}),metal=materials.metal(0x9ea8a4,{roughness:.38}),pcbmat=materials.plastic(0x1e4b37,{roughness:.89});
 const housing=slab(g,21.5,10.4,14.8,.5,[0,0,-15.1],black,[],.08);housing.name='QRCode M14 physical opaque engine enclosure';
 const frontShape=roundedRect(21.4,9.8,.4);hole(frontShape,0,0,2.85);for(const x of[-7.4,7.4])frontShape.holes.push(roundedRect(3.5,3.4,.15,{cx:x,cy:0,path:new THREE.Path(),clockwise:true}));
 const face=solid(g,frontShape,.45,[0,0,-.3],black,'QRCode M14 optical face with three true openings');
 const lensBarrel=annulus(g,2.8,1.45,2.6,[0,0,-2.35],black,'QRCode central camera real hollow lens barrel');const bezel=annulus(g,2.85,1.45,.4,[0,0,-.02],black,'QRCode lens retaining ring');
 const glass=mesh(g,new THREE.SphereGeometry(1.43,48,24,0,tau,0,Math.PI/2).rotateX(Math.PI/2).scale(1,1,.25),new THREE.MeshPhysicalMaterial({color:0x2d4744,roughness:.13,metalness:.2,clearcoat:1}),[0,0,-.08],'QRCode fixed convex dark optical lens glass');
 const sensor=mesh(g,new THREE.BoxGeometry(4.2,4.2,.7),black,[0,0,-4.0],'QRCode fixed CMOS 640×480 package');const sensorWindow=mesh(g,new THREE.BoxGeometry(2.3,2.3,.1),materials.plastic(0x283b3d,{roughness:.18}),[0,0,-3.6],'QRCode fixed CMOS optical window');
 const daughter=mesh(g,new THREE.BoxGeometry(20,9,.8),pcbmat,[0,0,-11.3],'QRCode M14 internal physical board');
 const leds=[];for(const[id,x,Cls,color,baseColor,label]of[['illumination',-7.4,WhiteLed,0xfffaf0,0xe7d96c,'M14 white illumination LED'],['aiming',7.4,RedLed,0xff2420,0xc5bcb3,'M14 red aiming LED']]){
  const packageBody=slab(g,3.45,3.35,.65,.12,[x,0,-.72],materials.plastic(0xc5ccbd,{roughness:.7}),[],.02);packageBody.name='QRCode '+label+' fixed package';
  const lens=slab(new THREE.Group(),2.95,2.85,.3,.18,[0,0,0],new THREE.MeshPhysicalMaterial({color:baseColor,roughness:.28,clearcoat:1}),[],.02);lens.name='QRCode '+label+' real lens';
  const led=host.add(new Cls({id,label,mesh:lens,color,position:[x,23.6,2.2],quaternion:FACE.top,radius:.1,glowSize:5,meta:{role:'externally-driven-visual',colorMode:id==='illumination'?'fixed-white':'fixed-red',scope:'Default off; independent external on/brightness only. No scan, trigger, mode, aiming beam, illumination field or decoder coupling'}}));led.glow.position.z=.22;leds.push(led);
  for(const dx of[-1.65,1.65])mesh(g,new THREE.BoxGeometry(.16,2.3,.3),metal,[x+dx,0,-.32],'QRCode '+label+' metallic termination');
 }
 g.userData={role:'fixed-optical-engine',inferred:true,scope:'Physical enclosure/lens/CMOS and two distinct light packages only; no image capture, recognition, optical ray, beam or decoded values'};return{group:g,housing,face,lensBarrel,bezel,glass,sensor,sensorWindow,daughter,leds};
}
function refractor(host,parts,options){
 const frame=parts['QRCode native removable fixed refractor frame'];if(options.refractor===false)return null;
 // Original supplied frame defines a fixed 45 degree reflector carrier, not a hinge.
 const mirror=mesh(host.body,new THREE.BoxGeometry(21.9,15.8,.22),new THREE.MeshPhysicalMaterial({color:0xc4d2d0,roughness:.12,metalness:.88,clearcoat:.8}),[0,34.3,4.0],'QRCode fixed removable refractor reflective sheet');mirror.rotation.x=Math.PI/4;mirror.userData={role:'fixed-optical-reflector',inferred:true,scope:'Fixed physical metal-coated reflector appearance only; no environment capture, scan rays, movable hinge or optical simulation'};return{frame,mirror};
}
export function buildQrCode(host,options={}){
 const parts=addCadParts(host,options.refractor===false?data.filter(p=>p.component!==5):data,{shell:materials.plastic(0x666b65,{roughness:.83})});
 const nativeRefractor=refractor(host,parts,options),electronics=board(host),input=grove(host),control=controls(host,parts),engine=scanner(host);const fixing=screw(host.body,[0,-12,-7.97],'back',1.4);
 host.add(new Component({id:'sensor',label:'M14 optical engine visual anchor',position:[0,21,2.2],meta:{role:'visual-anchor',part:'M14 640×480 CMOS',scope:'Passive fixed visual anchor only; no capture, scan, decoding, serial/I2C/register, audio, beam or sensor-value commands'}}));
 host.qrcodeAssembly={parts,refractor:nativeRefractor,electronics,input,controls:control,engine,fixing};host.qrcodeStickers=addStickers(host);
}
