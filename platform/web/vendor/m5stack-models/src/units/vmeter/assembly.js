import *as THREE from 'three';
import{Component,Led,Port,materials}from'../../core/index.js';
import{addCadParts}from'../../modeling/cad.js';
import{mesh,slab,screw,FACE,portQuaternion}from'../../modeling/parts.js';
import{spec}from'./dimensions.js';import data from'./geometry-data.js';import{addStickers}from'./stickers.js';

function board(host){
 const x=10.4,y=-16,r=3.35,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r),s=new THREE.Shape();
 s.moveTo(-5.35,-26.8);s.lineTo(-7,-26.8);s.lineTo(-x,-23.4);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,17.7);s.lineTo(-8.25,17.7);s.lineTo(-8.25,26.8);s.lineTo(8.25,26.8);s.lineTo(8.25,17.7);s.lineTo(x,17.7);s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);s.lineTo(x,-23.4);s.lineTo(7,-26.8);s.lineTo(5.35,-26.8);s.lineTo(5.35,-20.8);s.lineTo(-5.35,-20.8);s.closePath();
 const hole=new THREE.Path();hole.absarc(0,-16,2.3,0,Math.PI*2,false);s.holes.push(hole);
 // Own U087 PCB photograph shows an isolation slit beside the converter.
 const slit=new THREE.Path();slit.moveTo(-7.6,2.2);slit.lineTo(-7.6,2.8);slit.lineTo(-2.2,2.8);slit.lineTo(-2.2,2.2);slit.closePath();s.holes.push(slit);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:36}),materials.plastic(0x286345,{roughness:.88}),[0,0,-.9],'VMeter physical PCB with open mounting scallops and isolation slit');pcb.userData={role:'physical-pcb',scope:'Own-photo envelope reconstruction; no copper routes or electrical behavior'};
 const dark=materials.plastic(0x232721,{roughness:.83}),metal=materials.metal(0xb9b7a6,{roughness:.46}),ceramic=materials.plastic(0xad8960,{roughness:.8}),parts=[];
 const part=(name,w,h,d,pos,mat=dark)=>{const p=slab(host.body,w,h,d,.1,pos,mat,[],.025);p.name='VMeter '+name;parts.push(p);return p;};
 const adc=part('ADS1115 ten-lead ADC physical package',3,4.9,.85,[-3.7,12,-.1]);for(const side of[-1,1])for(let i=0;i<5;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.75,.3,.18),metal,[-3.7+side*1.8,12+(i-2)*.9,.05],'VMeter ADS1115 lead'));
 const isolator=part('CA-IS3020S physical isolator package',4.1,5,.95,[3.8,4.3,-.1]);for(const side of[-1,1])for(let i=0;i<4;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.65,.45,.18),metal,[3.8+side*2.35,4.3+(i-1.5)*1.1,.05],'VMeter CA-IS3020S lead'));
 const transformer=new THREE.Group();transformer.name='VMeter own-photo wound DC-DC transformer';transformer.position.set(3.5,6.3,-1.2);host.body.add(transformer);mesh(transformer,new THREE.BoxGeometry(8.4,8.9,.6),dark,[0,0,-.3],'VMeter transformer lower bobbin');for(const y of[-3.2,3.2])mesh(transformer,new THREE.BoxGeometry(8.4,2.7,1.2),dark,[0,y,-1.2],'VMeter transformer ferrite bar');for(let j=0;j<10;j++){const torus=new THREE.TorusGeometry(1.38,.095,5,26);torus.rotateY(Math.PI/2);mesh(transformer,torus,materials.metal(0xa5682c),[-1.5+j*.32,0,-1.3],'VMeter visible copper winding');}for(const x of[-3,-1,1,3])for(const y of[-5,5])mesh(transformer,new THREE.BoxGeometry(.5,1.3,.35),metal,[x,y,-.8],'VMeter transformer lead');
 const eeprom=part('host calibration EEPROM fixed physical package',2.6,3,.65,[-4.9,-7,-.1]);part('host-side LDO physical package',1.5,2.9,.7,[5.6,-9,-.1]);
 for(const [x,y]of[[-6,8],[-1,9],[1,13],[6.5,13],[.5,-7],[-6.8,-3],[6.8,-2]])part('concealed resistor or decoupling package',1,.55,.45,[x,y,-.1],ceramic);
 return{pcb,parts,adc,isolator,transformer,eeprom};
}
function grove(host){
 const frame=new THREE.Group();frame.name='VMeter burgundy open-top HY2.0-4P';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.62}),metal=materials.metal(0xb9ad82,{roughness:.43}),box=(size,p,name,mat=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),mat,p,'VMeter Grove '+name);
 for(const x of[-4.65,4.65]){box([.7,5.2,6.5],[x,0,-3.25],'side wall');box([.85,.75,6.5],[Math.sign(x)*3.85,2.2,-3.25],'guide rail');box([.7,.9,.6],[x,2.05,0],'mouth ear');}
 box([8.6,.7,6.5],[0,-2.25,-3.25],'floor');box([8.6,5.2,.6],[0,0,-6.2],'recessed rear wall');box([8.6,2.65,3.6],[0,-1.25,-4.7],'recessed contact carrier');box([3.4,.65,2.7],[0,1.2,-5.1],'short locking tongue');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4],[(i-1.5)*2,-.15,-3.2],`contact ${i+1}`,metal));box([.42,1.2,.42],[(i-1.5)*2,-1.4,-5.7],`PCB tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.15],order:col=>4-col},meta:{role:'visual-connector',face:'bottom',protocol:'I2C',i2cAddress:'0x49',scope:'Connector and physical cable pose only; no bus, measurement, isolation, voltage, current or firmware behavior'}}));return{frame,contacts,port};
}
function terminal(host){
 const frame=new THREE.Group();frame.name='VMeter fixed orange HT3.96-4P socket';host.body.add(frame);
 const orange=materials.plastic(0xf29a47,{roughness:.65}),metal=materials.metal(0xb9b8a8,{roughness:.43}),parts=[];
 const solid=(name,w,h,d,p,holes=[])=>{const m=slab(frame,w,h,d,.18,p,orange,holes,.035);m.name='VMeter fixed terminal '+name;parts.push(m);return m;};
 const floor=solid('floor',15.8,9.8,.6,[0,23.1,-.7]);
 for(const x of[-7.55,7.55])solid('side cheek',.7,9.8,5.65,[x,23.1,-.1]);
 const rear=solid('recessed rear wall',14.4,.7,5.65,[0,18.35,-.1]);
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.1,r:.08,cx,cy:-3.65}));
 const roof=solid('roof with four real inspection windows',15.8,9.8,.65,[0,23.1,5.55],windows);
 for(const x of[-3.96,0,3.96])solid('lower channel rib',.4,8.2,.55,[x,23.8,-.1]);
 const contacts=[];for(const[i,x]of spec.terminal.pinX.entries()){
  const pin=mesh(frame,new THREE.BoxGeometry(.65,8.3,.65),metal,[x,22.9,1.2],`VMeter fixed terminal ${spec.terminal.names[i]} contact pin`);pin.userData={schematicPin:spec.terminal.pinNumbers[i],signal:spec.terminal.names[i]};contacts.push(pin);
  mesh(frame,new THREE.BoxGeometry(.65,1.7,.65),metal,[x,17.9,1.2],'VMeter fixed terminal bent lead');mesh(frame,new THREE.BoxGeometry(.65,.65,1.9),metal,[x,17.1,.25],'VMeter fixed terminal PCB tail');
 }
 const port=host.add(new Port({id:'terminal',label:'Voltage measurement · HT3.96-4P',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,6.9],pins:spec.terminal.names.map((name,i)=>({n:spec.terminal.pinNumbers[i],name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,-1.4],order:col=>4-col},meta:{role:'visual-connector',face:'top',signalRole:'voltage-measurement',scope:'Physical connector and detachable plug only; no continuity, voltage, current, measurement, protection or isolation behavior',pinNumbersAreViewerIndices:true,terminalOrderEvidence:'Own front + / − labels show positive left pair and negative right pair. Four individual pin numbers are not shown in own block diagram.'}}));return{frame,floor,rear,roof,contacts,parts,port};
}
class NeutralPreviewLed extends Led{set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:spec.powerLed.color});}}
function indicator(host){
 const carrier=mesh(host.body,new THREE.BoxGeometry(1.15,2.7,2.25),materials.plastic(0xc4c4af,{roughness:.7}),[-7.3,-22.5,1.8],'VMeter real indicator carrier behind native slot');
 const lens=slab(new THREE.Group(),.5,2.3,.55,.18,[0,0,0],materials.plastic(0xe0dfd0,{roughness:.5}),[],.02);lens.name='VMeter physical single power-LED lens';
 const led=host.add(new NeutralPreviewLed({id:'power-led',label:'Power indicator · emission color unconfirmed',mesh:lens,position:spec.powerLed.position,color:spec.powerLed.color,radius:.2,glowSize:1.7,meta:{role:'externally-driven-visual',singleEmitter:true,colorConfirmed:false,colorMode:'fixed-neutral-preview',colorEvidence:'Exact own front photo labels LED and native front shell has dedicated slot. Emission hue/circuit is not stated in available official block diagram.',renderColorScope:'Fixed neutral-white preview is an unconfirmed appearance estimate; no white specification or RGB hardware capability is claimed. External color requests do not change hue.',scope:'Defaults off; explicit external on/brightness only. No automatic response to voltage, Grove attachment, supply, measurement, isolation, firmware or terminal presence'}}));led.glow.position.z=.8;return{carrier,led};
}
export function buildVMeter(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e1,{roughness:.77})}),pcb=board(host),input=grove(host),output=terminal(host);
 screw(host.body,[0,-16,-3.98],'back',1.3);
 host.add(new Component({id:'sensor',label:'VMeter visual anchor',meta:{role:'visual-anchor',scope:'Appearance anchor only; no voltage/current, ADC samples, calibration, power, isolation, electrical or firmware behavior'}}));
 const powerLed=indicator(host),artwork=addStickers(host);host.vmeterAssembly={parts,pcb,input,terminal:output,powerLed,artwork};
}
