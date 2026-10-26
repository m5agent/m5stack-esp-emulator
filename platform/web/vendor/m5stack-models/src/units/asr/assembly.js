import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function board(host){
 // The Grove and two native mounting bosses have open outline reliefs.
 const s=new THREE.Shape();s.moveTo(-6.4,22.4);s.lineTo(6.4,22.4);s.lineTo(10.4,18.4);s.lineTo(10.4,-8.6);s.lineTo(8,-8.6);
 s.absarc(8,-12,3.4,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-15.4);s.lineTo(10.4,-18.4);s.lineTo(6.4,-22.4);
 s.lineTo(5.6,-22.4);s.lineTo(5.6,-16.5);s.lineTo(-5.6,-16.5);s.lineTo(-5.6,-22.4);s.lineTo(-6.4,-22.4);s.lineTo(-10.4,-18.4);s.lineTo(-10.4,-15.4);s.lineTo(-8,-15.4);
 s.absarc(-8,-12,3.4,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-8.6);s.lineTo(-10.4,18.4);s.closePath();bore(s,0,-12,1.9);
 for(const x of[-3,-1,1,3])bore(s,x,-16.1,.32);
 return solid(host.body,s,.8,[0,0,-6.1],materials.plastic(0x253f31,{roughness:.91}),'ASR physical PCB with native boss and Grove relief');
}
function circuit(host){
 const group=new THREE.Group();group.name='ASR concealed CI-03T physical daughterboard and carrier circuit';host.body.add(group);
 const boardMat=materials.plastic(0x164b39,{roughness:.9}),dark=materials.plastic(0x1d2521,{roughness:.87}),metal=materials.metal(0xb5b7ae,{roughness:.56}),ceramic=materials.plastic(0xada380,{roughness:.91});
 const moduleBoard=mesh(group,new THREE.BoxGeometry(16,18,.8),boardMat,[0,10,-4.85],'ASR M1 CI-03T physical module PCB');
 const moduleChip=mesh(group,new THREE.BoxGeometry(7.2,7.2,.95),dark,[0,10.2,-3.975],'ASR CI-03T concealed processing package visual envelope');
 const leads=[];for(let i=0;i<11;i++)for(const side of[-1,1])leads.push(mesh(group,new THREE.BoxGeometry(1.25,.65,.13),metal,[side*7.8,10+(i-5)*1.5,-5.18],'ASR CI-03T module castellated solder pad'));
 const diode=mesh(group,new THREE.BoxGeometry(3,1.75,.9),dark,[6,-3.4,-4.85],'ASR D1 1N5819 series diode body');
 for(const x of[4.35,7.65])mesh(group,new THREE.BoxGeometry(.5,1.4,.13),metal,[x,-3.4,-5.2],'ASR D1 solder termination');
 for(const[x,y]of[[-6.7,-1],[-3.5,-2],[3.5,-1.5],[6.6,0],[-6.8,20],[-3.7,21],[0,21],[3.7,21],[6.8,20]]){
  mesh(group,new THREE.BoxGeometry(1.3,.8,.55),ceramic,[x,y,-5.025],'ASR concealed decoupling capacitor or resistor package');
  for(const dx of[-.53,.53])mesh(group,new THREE.BoxGeometry(.26,.8,.57),metal,[x+dx,y,-5.025],'ASR passive metal termination');
 }
 const ledPackage=mesh(group,new THREE.BoxGeometry(1.6,.8,.55),materials.plastic(0x852b25,{roughness:.75}),[-5.5,-4.1,-5.025],'ASR concealed D4 red power LED physical package');
 for(const dx of[-.65,.65])mesh(group,new THREE.BoxGeometry(.3,.8,.57),metal,[-5.5+dx,-4.1,-5.025],'ASR D4 solder termination');
 // Exact exterior references do not prove an exposed D4 lens or optical path.
 // A printed blue bulb in the rear diagram does not define a visible blue LED.
 return{group,moduleBoard,moduleChip,leads,diode,ledPackages:[ledPackage]};
}
function loudspeaker(host){
 const group=new THREE.Group();group.name='ASR fixed internal 8 ohm cavity loudspeaker';group.position.set(0,8,0);host.body.add(group);
 const frameMat=materials.plastic(0x262b29,{roughness:.9}),paper=materials.plastic(0x353c37,{roughness:.98}),rubber=materials.plastic(0x1c2421,{roughness:.91}),steel=materials.metal(0x7f8981,{roughness:.53});
 // Rectangular speaker chassis and oval diaphragm back every native grille
 // opening. These are a physical speaker reconstruction, never a shadow decal.
 const frameShape=roundedRect(20.2,28,2.3),mouth=new THREE.Path();mouth.absellipse(0,0,8.65,12.35,0,Math.PI*2,false);frameShape.holes.push(mouth);
 const frame=solid(group,frameShape,.7,[0,0,5.65],frameMat,'ASR speaker rectangular chassis with true oval opening');
 const surroundShape=new THREE.Shape();surroundShape.absellipse(0,0,8.65,12.35,0,Math.PI*2,false);const surroundHole=new THREE.Path();surroundHole.absellipse(0,0,7.7,11.3,0,Math.PI*2,false);surroundShape.holes.push(surroundHole);
 const surround=solid(group,surroundShape,.24,[0,0,5.67],rubber,'ASR loudspeaker fixed oval suspension surround');
 // Closed cone surface: ring profile descends toward the voice-coil neck.
 const coneGeometry=new THREE.LatheGeometry([new THREE.Vector2(7.7,5.68),new THREE.Vector2(2.7,3.85),new THREE.Vector2(2.2,3.55),new THREE.Vector2(0,3.55)],80);coneGeometry.rotateX(Math.PI/2);coneGeometry.scale(1,11.3/7.7,1);
 const cone=mesh(group,coneGeometry,paper,[0,0,0],'ASR fixed recessed paper speaker cone');
 const capGeometry=new THREE.SphereGeometry(2.5,40,20,0,Math.PI*2,0,Math.PI/2);capGeometry.rotateX(Math.PI/2);capGeometry.scale(1,1.25,.33);
 const cap=mesh(group,capGeometry,paper,[0,0,3.65],'ASR fixed convex speaker dust cap');
 const basket=[];for(const x of[-7.5,7.5])for(const y of[-8.5,8.5]){
  const strut=mesh(group,new THREE.BoxGeometry(1.5,2.1,3.4),steel,[x,y,3.95],'ASR speaker rear basket rib');strut.rotation.y=x>0?.25:-.25;basket.push(strut);
 }
 const magnet=mesh(group,new THREE.CylinderGeometry(5,5,2.2,64).rotateX(Math.PI/2),materials.metal(0x747e76,{roughness:.65}),[0,0,2],'ASR speaker permanent magnet can');
 const back=mesh(group,new THREE.CylinderGeometry(5.15,5.15,.35,64).rotateX(Math.PI/2),steel,[0,0,.725],'ASR speaker fixed magnet rear plate');
 const terminals=[];for(const x of[-7.5,7.5])terminals.push(mesh(group,new THREE.BoxGeometry(1.25,2.0,.25),materials.metal(0xb9a86c,{roughness:.53}),[x,-8.5,2.25],'ASR speaker fixed solder terminal'));
 group.userData={role:'fixed-speaker-assembly',scope:'Physical frame, diaphragm, dust cap, basket and magnet only; no displacement, sound, playback, recognition or acoustic simulation',inferred:true};
 return{group,frame,surround,cone,cap,basket,magnet,back,terminals};
}
function speakerConnection(host){
 const group=new THREE.Group();group.name='ASR concealed P1 1.25 mm 2P fixed speaker connector';group.position.set(-6.5,-4.3,-5.3);host.body.add(group);
 const white=materials.plastic(0xd9ded3,{roughness:.7}),contact=materials.metal(0xbbaa70,{roughness:.47});
 const floor=mesh(group,new THREE.BoxGeometry(4.8,3.4,.45),white,[0,0,.225],'ASR P1 insulating floor');
 const walls=[];for(const x of[-2.175,2.175])walls.push(mesh(group,new THREE.BoxGeometry(.45,3.4,2.1),white,[x,0,1.5],'ASR P1 socket side wall'));
 const rear=mesh(group,new THREE.BoxGeometry(3.9,.45,2.1),white,[0,-1.475,1.5],'ASR P1 recessed contact support');
 const roof=mesh(group,new THREE.BoxGeometry(3.9,3.4,.4),white,[0,0,2.35],'ASR P1 socket roof');
 const contacts=[];for(const x of[-.625,.625])contacts.push(mesh(group,new THREE.BoxGeometry(.3,2.4,.3),contact,[x,-.35,1.15],'ASR P1 recessed 1.25 mm speaker contact'));
 // Fixed two-wire internal loom, from the concealed socket to speaker terminals.
 const wires=[];for(const[x,color,dx]of[[-7.5,0x252a27,-.625],[7.5,0xb83225,.625]]){
  const points=[new THREE.Vector3(-6.5+dx,-2.6,-4.15),new THREE.Vector3(-6.0+dx,-1.1,-2.5),new THREE.Vector3(x,-2.0,.8),new THREE.Vector3(x,-.5,2.25)];
  wires.push(mesh(host.body,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),24,.24,10,false),materials.plastic(color,{roughness:.72}),[0,0,0],'ASR fixed internal speaker lead'));
 }
 group.userData={role:'concealed-fixed-connector',pitchMm:1.25,pins:2,scope:'P1 internal physical socket/contact estimate only; not an exposed mating Port or electrical model'};return{group,floor,walls,rear,roof,contacts,wires};
}
function microphone(host){
 const group=new THREE.Group();group.name='ASR fixed analog microphone and acoustic inlet';host.body.add(group);
 const metal=materials.metal(0x9caaa3,{roughness:.68}),black=materials.plastic(0x141b17,{roughness:.98}),rubber=materials.plastic(0x27302a,{roughness:.95});
 // Exact images identify the small opening at the front shoulder as MIC. The
 // native shell is retained; the package, gasket and installation are inferred.
 const canShape=new THREE.Shape();canShape.absarc(0,0,2.7,0,Math.PI*2,false);bore(canShape,0,0,.25);
 const can=solid(group,canShape,2.7,[0,0,0],metal,'ASR fixed GM16027P-2C320DB microphone metal can with actual acoustic bore');can.rotation.x=Math.PI/2;can.position.set(0,-4.35,-.55);
 const ductShape=new THREE.Shape();ductShape.absarc(0,0,.55,0,Math.PI*2,false);bore(ductShape,0,0,.25);
 const duct=solid(group,ductShape,.65,[0,0,0],rubber,'ASR fixed acoustic duct with real bore');duct.rotation.x=Math.PI/2;duct.position.set(0,-7,-.55);
 const back=mesh(group,new THREE.CylinderGeometry(2.5,2.5,.22,64),materials.plastic(0x34644d,{roughness:.9}),[0,-4.25,-.55],'ASR microphone rear insulating disc');
 const gasketShape=roundedRect(1.05,1.38,.48);bore(gasketShape,0,0,.25);
 const gasket=solid(group,gasketShape,.4,[0,0,0],rubber,'ASR small physical microphone acoustic gasket with open bore');gasket.rotation.x=Math.PI/2;gasket.position.set(0,-7.64,-.55);
 // A true recessed acoustic mesh is visible through the open gasket. It is
 // fixed and has no capture command, animation or simulated signal.
 const diaphragm=mesh(group,new THREE.CylinderGeometry(.23,.23,.08,48),black,[0,-6.95,-.55],'ASR microphone recessed fixed diaphragm');
 const grille=[];for(const d of[-.12,0,.12]){
  grille.push(mesh(group,new THREE.BoxGeometry(.025,.035,.44),metal,[d,-7.51,-.55],'ASR microphone fixed fine vertical protection wire'));
  grille.push(mesh(group,new THREE.BoxGeometry(.44,.035,.025),metal,[0,-7.51,-.55+d],'ASR microphone fixed fine horizontal protection wire'));
 }
 const leads=[];for(const x of[-.85,.85]){const pts=[new THREE.Vector3(x,-4.28,-.55),new THREE.Vector3(x,-3.7,-2),new THREE.Vector3(x,-3.6,-5.1)];leads.push(mesh(group,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts),16,.12,8,false),materials.metal(0xada78b),[0,0,0],'ASR fixed microphone PCB lead'));}
 group.userData={role:'fixed-analog-microphone',inferred:true,scope:'Physical can, acoustic gasket/bore, fixed protective wire mesh, diaphragm and leads only; no microphone capture, sensor values, signal, voice recognition or simulation'};
 return{group,can,back,duct,gasket,diaphragm,grille,leads};
}
export function buildAsr(host){
 addCadParts(host,data,{shell:materials.plastic(0xe7e9e3,{roughness:.78})});
 const pcb=board(host),electronics=circuit(host),speaker=loudspeaker(host),internalConnector=speakerConnection(host),mic=microphone(host);
 const socket=connector(host.body,48,true,{height:5.2});socket.name='ASR cyan open-top HY2.0-4P';socket.position.z=-5.2;socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'RXD',color:'yellow'},{n:4,name:'TXD',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical connector, attachment and four-wire cable pose only; no UART protocol, recognition, wake words, microphone capture, sound, playback, firmware or electrical behavior'}}));
 const fixing=screw(host.body,[0,-12,-7.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.0,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-12,-6.7],'ASR concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'CI-03T physical visual package anchor',position:[0,10.2,-3.5],meta:{role:'visual-anchor',part:'CI-03T',scope:'Passive visual anchor only; no microphone capture, speech recognition, wake words, playback, sound, firmware, sensor values or electrical commands'}}));
 host.asrAssembly={pcb,electronics,speaker,internalConnector,microphone:mic,socket,port,fixing,shank};
 host.asrStickers=addStickers(host);
}
