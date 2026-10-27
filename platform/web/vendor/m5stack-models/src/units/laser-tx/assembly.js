import*as THREE from'three';
import{Component,Port,Led,materials}from'../../core/index.js';
import{addCadParts}from'../../modeling/cad.js';
import{mesh,portQuaternion,screw}from'../../modeling/parts.js';
import{connector}from'../shared/parts.js';
import data from'./geometry-data.js';import{spec}from'./dimensions.js';import{addStickers}from'./stickers.js';
const tau=Math.PI*2;
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
function extrude(parent,s,depth,z,material,name){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:48}),material,[0,0,z],name);}
function board(host){
 // Board perimeter clears the untouched native bosses and the open Grove socket.
 const s=new THREE.Shape();s.moveTo(-7,14.4);s.lineTo(7,14.4);s.lineTo(10.4,11);s.lineTo(10.4,-.6);s.lineTo(8,-.6);s.absarc(8,-4,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-7.4);s.lineTo(10.4,-11);s.lineTo(7,-14.4);s.lineTo(5.3,-14.4);s.lineTo(5.3,-8.5);s.lineTo(-5.3,-8.5);s.lineTo(-5.3,-14.4);s.lineTo(-7,-14.4);s.lineTo(-10.4,-11);s.lineTo(-10.4,-7.4);s.lineTo(-8,-7.4);s.absarc(-8,-4,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-.6);s.lineTo(-10.4,11);s.closePath();bore(s,0,-4,1.9);for(const x of[-3,-1,1,3])bore(s,x,-8.15,.32);
 const pcb=extrude(host.body,s,.8,-2.9,materials.plastic(0x176743,{roughness:.93}),'Laser TX physical notched PCB with real fastening and solder bores');pcb.userData={role:'physical-pcb',scope:'Concealed reconstructed visual board; no production placement or manufacturing-fit claim'};
 const metal=materials.metal(0xb2b6ad,{roughness:.5}),pads=[];for(const x of[-3,-1,1,3]){const ann=new THREE.Shape();ann.absarc(x,-8.15,.56,0,tau,false);bore(ann,x,-8.15,.32);for(const z of[-2.95,-2.1])pads.push(extrude(host.body,ann,.05,z,metal,'Laser TX Grove physical solder annulus'));}
 return{pcb,pads};
}
function electronics(host){
 const dark=materials.plastic(0x292d28,{roughness:.8}),metal=materials.metal(0xb0b5aa,{roughness:.5}),ceramic=materials.plastic(0xb7a477,{roughness:.9}),parts=[];
 const q1=mesh(host.body,new THREE.BoxGeometry(2.9,1.65,1.05),dark,[-4.5,1.1,-1.56],'Laser TX Q1 AO3400A physical SOT23 MOSFET package');for(const[x,y]of[[-5.45,-.05],[-3.55,-.05],[-4.5,2.25]])parts.push(mesh(host.body,new THREE.BoxGeometry(.45,.85,.17),metal,[x,y,-2.015],'Laser TX Q1 stationary solder terminal'));
 for(const[id,x,y,kind]of[['R1',-4.7,-1.5,'resistor'],['R2',-6.8,1.2,'resistor'],['C1',4.5,4.0,'capacitor'],['C2',5.8,-1.5,'capacitor']]){parts.push(mesh(host.body,new THREE.BoxGeometry(1.6,.8,.55),kind==='resistor'?dark:ceramic,[x,y,-1.825],`Laser TX ${id} physical ${kind} package`));for(const dx of[-.65,.65])parts.push(mesh(host.body,new THREE.BoxGeometry(.3,.83,.58),metal,[x+dx,y,-1.81],`Laser TX ${id} metal termination`));}
 return{q1,parts};
}
class RedEmitter extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:spec.optic.color});this.glow.visible=false;}
}
function optics(host){
 const group=new THREE.Group();group.name='Laser TX fixed metal laser head and physical collimator';host.body.add(group);
 const brass=materials.metal(0xb89a54,{roughness:.42}),metal=materials.metal(0xa6ada8,{roughness:.4}),dark=materials.plastic(0x161b1e,{roughness:.61});
 // True hollow brass barrel and nose. The native shell's top aperture is retained.
 const barrelShape=new THREE.Shape();barrelShape.absarc(0,0,2.15,0,tau,false);bore(barrelShape,0,0,1.4);
 const barrelGeometry=new THREE.ExtrudeGeometry(barrelShape,{depth:8.4,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2);
 const barrel=mesh(group,barrelGeometry,brass,[0,5.1,0],'Laser TX hollow brass cylindrical laser module barrel');
 const rear=mesh(group,new THREE.CylinderGeometry(2.15,2.15,.4,64),brass,[0,5.1,0],'Laser TX brass rear end cap');
 const diodeCan=mesh(group,new THREE.CylinderGeometry(1.32,1.32,3.8,48),metal,[0,7.25,0],'Laser TX D1 physical laser diode can inside barrel');
 const dielectric=mesh(group,new THREE.CylinderGeometry(1.2,1.2,.3,48),dark,[0,9.3,0],'Laser TX diode front isolator');
 const die=mesh(group,new THREE.BoxGeometry(.35,.09,.35),materials.metal(0xb2944c,{roughness:.3}),[0,9.49,0],'Laser TX fixed internal diode die carrier');
 const shoulder=mesh(group,new THREE.CylinderGeometry(1.4,2.15,.8,64),brass,[0,13.9,0],'Laser TX brass collimator shoulder');
 const noseShape=new THREE.Shape();noseShape.absarc(0,0,1.4,0,tau,false);bore(noseShape,0,0,1.03);
 const nose=mesh(group,new THREE.ExtrudeGeometry(noseShape,{depth:1.35,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2),brass,[0,14.3,0],'Laser TX hollow recessed brass optical nose');
 // A solid lens backs the emission opening; its material alone gets external brightness.
 const lensGeometry=new THREE.SphereGeometry(1.01,48,20,0,tau,0,Math.PI/2).rotateX(Math.PI/2).scale(1,1,.18/1.01);
 const lens=new THREE.Mesh(lensGeometry,materials.glossy(0x392225,{roughness:.15}));lens.name='Laser TX fixed collimator front optical lens';
 const emitter=host.add(new RedEmitter({id:'emitter',label:'650 nm red emitter appearance',position:spec.optic.center,rotation:[-Math.PI/2,0,0],mesh:lens,color:spec.optic.color,radius:0,glowSize:0,meta:{role:'externally-driven-visual',colorMode:'fixed-red',printedWavelengthNm:650,colorEvidence:'Exact U066 official hero and rear-label photographs print WL:650NM; red visible wavelength. Material/brightness is visual reconstruction, not a measured spectrum.',scope:'External lens brightness only; defaults off. No projected beam, spot, optical propagation, waveform, frequency, modulation, communication, DIN/electrical state, RX coupling or sensor reading.'}}));emitter.glow.visible=false;
 const leads=[];for(const[x,color]of[[-.75,0x97392e],[.75,0x282b2c]]){const points=[[x,4.9,0],[x,3.6,-.2],[x*1.5,2.9,-1.4],[x*1.8,3.1,-2.06]].map(p=>new THREE.Vector3(...p));const lead=mesh(group,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),20,.18,8,false),materials.plastic(color,{roughness:.8}),[0,0,0],'Laser TX internal insulated diode lead');leads.push(lead);leads.push(mesh(group,new THREE.CylinderGeometry(.27,.27,.18,24).rotateX(Math.PI/2),metal,[x*1.8,3.1,-2.04],'Laser TX diode lead solder connection'));}
 return{group,barrel,rear,diodeCan,dielectric,die,shoulder,nose,lens,emitter,leads};
}
export function buildLaserTx(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})}),circuit=board(host),physicalElectronics=electronics(host),optic=optics(host);
 const socket=connector(host.body,32,true,{height:5.2});socket.name='Laser TX black open-top HY2.0-4P';
 const groveTails=[];for(const x of[-3,-1,1,3]){const points=[[x,-8.85,-.1],[x,-8.85,-1.1],[x,-8.15,-1.8],[x,-8.15,-2.45]].map(p=>new THREE.Vector3(...p));groveTails.push(mesh(host.body,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),16,.18,8,false),materials.metal(0xb7b09a,{roughness:.47}),[0,0,0],'Laser TX continuous Grove tail to physical PCB'));}
 const port=host.add(new Port({id:'grove',label:'PORT.B · Digital Input',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'DIN',color:'yellow'},{n:4,name:'NC',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'GPIO',scope:'Physical attachment and four-wire cable pose only. Yellow is DIN in the official interface table; the exact rear print says OUT and is reproduced as printed. No GPIO, power, electrical, optical communication or automatic emitter linkage.'}}));
 const fixing=screw(host.body,[0,-4,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.3,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.8],'Laser TX rear fixing screw shank');
 const sensor=host.add(new Component({id:'sensor',label:'Fixed laser module physical anchor',position:[0,10,0],meta:{role:'visual-anchor',part:'D1 Laser',scope:'Passive visual anchor only; no readings, communication, laser modulation, receiver linkage, light transport, GPIO or firmware'}}));
 const stickers=addStickers(host);host.laserTxAssembly={native,circuit,electronics:physicalElectronics,optic,socket,groveTails,port,fixing,shank,sensor,stickers};
}
