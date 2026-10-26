import * as THREE from 'three';
import {Component,Port,Button,Led,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {NativeFlexureButton,NativeResetButton} from './buttons.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(s,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);s.holes.push(p);}
function extrude(parent,s,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}),material,position,name);}
function circle(r){const s=new THREE.Shape();s.absarc(0,0,r,0,tau,false);return s;}
function cylinder(parent,r,bottom,top,material,name,xy=[0,0]){return mesh(parent,new THREE.CylinderGeometry(r,r,top-bottom,96).rotateX(Math.PI/2),material,[...xy,(bottom+top)/2],name);}
function circuit(host){
 const s=new THREE.Shape();s.moveTo(-10.4,-20);s.lineTo(-8.5,-22.4);s.lineTo(-5.5,-22.4);s.lineTo(-5.5,-16.9);s.lineTo(5.5,-16.9);s.lineTo(5.5,-22.4);s.lineTo(8.5,-22.4);s.lineTo(10.4,-20);s.lineTo(10.4,-15.6);s.lineTo(8,-15.6);s.absarc(8,-12,3.6,-Math.PI/2,-Math.PI*1.5,true);s.lineTo(10.4,-8.4);s.lineTo(10.4,20.3);s.lineTo(8.4,22.4);s.lineTo(-8.4,22.4);s.lineTo(-10.4,20.3);s.lineTo(-10.4,-8.4);s.lineTo(-8,-8.4);s.absarc(-8,-12,3.6,Math.PI/2,-Math.PI/2,true);s.lineTo(-10.4,-15.6);s.closePath();hole(s,0,-12,2.8);
 const leadPitch=2.54/Math.sqrt(2),leadPositions=[[-leadPitch,16+leadPitch],[-leadPitch,16-leadPitch],[leadPitch,16-leadPitch],[leadPitch,16+leadPitch]];
 for(const[x,y]of leadPositions)hole(s,x,y,.35);for(let i=0;i<5;i++)hole(s,7.6,10-i*2.54,.4);
 const pcb=extrude(host.body,s,.8,[0,0,-.3],materials.plastic(0x236843,{roughness:.91}),'NCIR2 fixed PCB with true TO39 and hidden SWD holes and open mechanical reliefs');pcb.userData={role:'physical-pcb',inferred:true};
 const metal=materials.metal(0xb9bcaf,{roughness:.45}),dark=materials.plastic(0x202624,{roughness:.85}),ceramic=materials.plastic(0xb09b72,{roughness:.88}),parts=[];
 const part=(name,w,h,d,p,m=dark)=>{const q=slab(host.body,w,h,d,.07,p,m,[],.01);q.name='NCIR2 '+name;parts.push(q);return q;};
 const stm32=part('U2 STM32F030F4P6 TSSOP20 physical controller',4.4,6.5,1.1,[0,-3,-1.4]);for(const side of[-1,1])for(let i=0;i<10;i++)mesh(host.body,new THREE.BoxGeometry(.65,.3,.14),metal,[side*2.45,-3+(i-4.5)*.65,-.78],'NCIR2 STM32 fixed solder lead');
 const regulator=part('U1 SY8089 physical regulator',2,2,1,[-6,0,-1.3]);const inductor=part('L1 3015 fixed power inductor',3,3,1.5,[-6,4,-1.8],materials.plastic(0x737c70,{roughness:.8}));
 for(const[x,y]of[[-8,8],[-8,11],[-5,10],[-4,18],[4,18],[5,-5],[7,-5],[-5,-5],[-8,-5],[3.5,7],[5,10]]){part('fixed resistor or capacitor package',1.7,.9,.65,[x,y,-.95],ceramic);for(const side of[-1,1])mesh(host.body,new THREE.BoxGeometry(.3,.95,.65),metal,[x+side*.75,y,-.625],'NCIR2 passive solder termination');}
 const swd=[];for(let i=0;i<5;i++){const ring=circle(.65);hole(ring,0,0,.4);swd.push(extrude(host.body,ring,.04,[7.6,10-i*2.54,-.34],metal,'NCIR2 concealed unpopulated SWD pad'));}
 return{pcb,stm32,regulator,inductor,parts,swd,leadPositions};
}
function sensingPackage(host,positions){
 const metal=materials.metal(0xb6bab7,{roughness:.32}),xy=[0,16],profile=[[1.75,1],[4.1,1],[4.1,4.1],[2.8,4.1],[2.45,4.48],[2.3,4.6],[1.8,4.6],[1.75,4.55],[1.75,1]].map(p=>new THREE.Vector2(...p));
 const can=mesh(host.body,new THREE.LatheGeometry(profile,128).rotateX(Math.PI/2),metal,[...xy,0],'NCIR2 MLX90614 standard TO39 physical metal can and raised crown');can.userData={source:'Official linked Melexis MLX90614 datasheet standard xxA drawing:8.2mm body,9.12mm header,5.6mm crown,3.5mm window; U150 own sensor centre40mm from Grove end',inferred:'Installed height/crown slope/tab yaw; passive appearance only'};
 const window=cylinder(host.body,1.75,4.28,4.40,materials.glossy(0x182229,{roughness:.23}),'NCIR2 closed passive infrared optical window',xy);
 const flange=circle(4.56);for(const[x,y]of positions)hole(flange,x,y-16,.8);const header=extrude(host.body,flange,.5,[0,16,.5],metal,'NCIR2 drilled TO39 header');
 const tab=mesh(host.body,new THREE.BoxGeometry(.7,.7,.5),metal,[0,20.66,.75],'NCIR2 fixed TO39 orientation tab');
 const leads=[],feedthroughs=[],pads=[];for(const[i,[x,y]]of positions.entries()){const glass=circle(.8);hole(glass,0,0,.225);feedthroughs.push(extrude(host.body,glass,.5,[x,y,.5],materials.plastic(0x45524a),'NCIR2 TO39 nonconductive glass feedthrough'));leads.push(cylinder(host.body,.225,-.95,1,metal,`NCIR2 sensor installed clipped lead ${i+1}`,[x,y]));const pad=circle(.6);hole(pad,0,0,.35);pads.push(extrude(host.body,pad,.06,[x,y,-.36],metal,'NCIR2 sensor rear annular solder pad'));}
 return{can,window,header,tab,leads,feedthroughs,pads};
}
function actuators(host,front){
 const dark=materials.plastic(0x1b211f,{roughness:.82}),metal=materials.metal(0xb3b8ac,{roughness:.45}),cream=materials.plastic(0xe6e8df,{roughness:.78});
 const switchBody=slab(host.body,3.3,2.5,1.45,.13,[0,7.8,.5],dark,[],.02);switchBody.name='NCIR2 S2 PTS820 underlying functional tact switch';
 const switchHead=slab(host.body,1.4,1.4,.8,.08,[0,7.8,1.95],cream,[],.01);switchHead.name='NCIR2 moving front-switch follower under real flexure tongue';
 for(const side of[-1,1])for(const x of[-1.25,1.25])mesh(host.body,new THREE.BoxGeometry(.4,.6,.14),metal,[x,7.8+side*1.5,.57],'NCIR2 key1 fixed solder lead');
 const button=host.add(new NativeFlexureButton(front));button.cap.add(switchHead);switchHead.position.set(0,3.3,-2.05);
 const resetBody=slab(host.body,2.5,4,2.3,.12,[-9.1,16,-2.6],dark,[],.02);resetBody.name='NCIR2 S1 real side-accessible NRST tactile switch body';
 const reset=host.add(new NativeResetButton(front));
 const ledBase=slab(host.body,3.5,3.5,1.1,.12,[0,4.8,.5],cream,[],.01);ledBase.name='NCIR2 SK6812 RGB physical package beneath native slot';
 const pipe=slab(host.body,2.3,.75,1.85,.08,[0,4.8,1.6],materials.plastic(0xdadfd1,{roughness:.32,transparent:true,opacity:.55,depthWrite:false}),[],.01);pipe.name='NCIR2 actual narrow non-emissive RGB light pipe';
 const lens=new THREE.Mesh(new THREE.BoxGeometry(...spec.rgb.sizeMm),materials.plastic(0xe6e9d7,{roughness:.3}));lens.name='NCIR2 RGB lens behind the real native tongue slot';
 const rgb=host.add(new Led({id:'rgb',label:'LED1 SK6812 external RGB appearance',mesh:lens,position:spec.rgb.position,radius:.25,glowSize:1.3,meta:{role:'externally-driven-indicator',scope:'Visible RGB lens only;no temperature,alarm,button/reset coupling,MCU,protocol or firmware behavior'}}));
 return{switchBody,switchHead,button,resetBody,reset,ledBase,pipe,rgb};
}
function acousticPackage(host){
 const xy=[7.8,16],dark=materials.plastic(0x202824,{roughness:.86});
 const base=cylinder(host.body,2.55,.5,1,dark,'NCIR2 LS1 real buzzer lower base',xy);const wall=circle(2.55);hole(wall,0,0,1.55);const housing=extrude(host.body,wall,2.3,[...xy,1],dark,'NCIR2 real buzzer annular chamber wall');
 const top=circle(2.55);hole(top,-.9,0,.52);hole(top,.9,0,.52);const lid=extrude(host.body,top,.25,[...xy,3.3],dark,'NCIR2 buzzer real acoustic holes below native shell holes');const diaphragm=cylinder(host.body,1.55,1.15,1.25,materials.metal(0x55625a,{roughness:.8}),'NCIR2 passive buzzer diaphragm backing',xy);return{base,housing,lid,diaphragm};
}
function grove(host){
 const g=new THREE.Group();g.name='NCIR2 open red HY2.0-4P socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.71}),metal=materials.metal(0xbcb8a0,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,'NCIR2 Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.5],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],`contact ${i+1}`,metal));box([.42,1.4,.42],[(i-1.5)*2,-2.7,-5.8],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, four contacts, documented pin labels and cable pose only; no light, lux, optical, ADC, I2C, voltage, electrical or firmware simulation'}}));return{group:g,contacts,port};
}
export function buildNCIR2(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e3,{roughness:.78})}),circuitry=circuit(host),sensor=sensingPackage(host,circuitry.leadPositions),input=grove(host),controls=actuators(host,parts['NCIR2 complete native front shell and integral flexure tongue']),buzzer=acousticPackage(host);
 const fixing=screw(host.body,[0,-12,-3.8],'back',1.4);fixing.name='NCIR2 real recessed fixed rear fastening screw';
 const anchor=host.add(new Component({id:'sensor',label:'MLX90614 passive appearance anchor',position:[0,16,2.5],meta:{role:'visual-anchor',scope:'No temperature,threshold,alarm,IR beam,sound,audio,MCU reset,calibration,I2C,electrical or firmware commands'}}));
 host.ncir2Assembly={parts,circuitry,sensor,input,controls,buzzer,fixing,anchor};host.unitStickers=addStickers(host);
}
