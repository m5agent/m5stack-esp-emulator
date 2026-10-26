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
 return solid(host.body,s,.8,[0,0,-6.1],materials.plastic(0x253f31,{roughness:.91}),'Synth physical PCB with native boss and Grove relief');
}
function circuit(host){
 const group=new THREE.Group();group.name='Synth concealed SAM2695 and NS4150B physical circuit';host.body.add(group);
 const dark=materials.plastic(0x202620,{roughness:.85}),metal=materials.metal(0xb5b7ae,{roughness:.56}),ceramic=materials.plastic(0xafa17d,{roughness:.91});
 const synth=mesh(group,new THREE.BoxGeometry(7,7,1.0),dark,[0,7,-4.7],'Synth U4 SAM2695 physical QFN48 package');
 const leads=[];for(let i=0;i<12;i++)for(const side of[-1,1]){
  leads.push(mesh(group,new THREE.BoxGeometry(.25,.65,.12),metal,[(i-5.5)*.5,7+side*3.55,-5.24],'SAM2695 QFN48 exposed edge pad'));
  leads.push(mesh(group,new THREE.BoxGeometry(.65,.25,.12),metal,[side*3.55,7+(i-5.5)*.5,-5.24],'SAM2695 QFN48 exposed edge pad'));
 }
 const amp=mesh(group,new THREE.BoxGeometry(4.9,3.9,1.15),dark,[0,-.2,-4.725],'Synth U2 NS4150B 8-lead amplifier body');
 for(const x of[-1.905,-.635,.635,1.905])for(const side of[-1,1])leads.push(mesh(group,new THREE.BoxGeometry(.4,1.0,.14),metal,[x,-.2+side*2.35,-5.2],'NS4150B physical gull-wing foot'));
 const crystal=mesh(group,new THREE.BoxGeometry(3.2,2.5,.8),metal,[-6.5,9,-4.9],'Synth X1 metal crystal package');
 for(const[x,y,name]of[[-6.5,3,'U1 ME6211A33M3G-N'],[6.5,3,'U3 CN809R']]){
  mesh(group,new THREE.BoxGeometry(2.8,1.6,.9),dark,[x,y,-4.85],'Synth '+name+' physical package');
  for(const dx of[-.9,0,.9])leads.push(mesh(group,new THREE.BoxGeometry(.38,.65,.13),metal,[x+dx,y-1.05,-5.235],name+' solder lead'));
 }
 const capacitor=mesh(group,new THREE.CylinderGeometry(2.5,2.5,4.1,40).rotateX(Math.PI/2),dark,[6.5,15.5,-3.25],'Synth C10 cylindrical bulk capacitor');
 mesh(group,new THREE.CylinderGeometry(2.32,2.32,.15,40).rotateX(Math.PI/2),metal,[6.5,15.5,-1.13],'Synth C10 metal vent cap');
 for(const[x,y]of[[-6.5,15],[-6.5,17],[-3.2,16],[0,16],[-6,0],[6,0],[-3,-4],[0,-4],[3,-4],[6.8,6.5],[6.8,9.0],[-4.5,20],[0,20],[4.5,20]]){
  mesh(group,new THREE.BoxGeometry(1.3,.8,.55),ceramic,[x,y,-5.025],'Synth concealed resistor or capacitor package');
  for(const dx of[-.53,.53])mesh(group,new THREE.BoxGeometry(.26,.8,.57),metal,[x+dx,y,-5.025],'Synth passive metal termination');
 }
 // LED2 and LED3 are present in the schematic, but exact exterior photos show
 // no lens/window. Keep their unlit physical packages concealed; no invented
 // visible indicator, autonomous status or colour assignment is exposed.
 const ledPackages=[];for(const[x,y,label]of[[-4.7,-5.9,'LED2 MIDI activity'],[4.7,-5.9,'LED3 supply']]){
  ledPackages.push(mesh(group,new THREE.BoxGeometry(1.6,.8,.55),materials.plastic(0xd4d7cb,{roughness:.7}),[x,y,-5.025],'Synth concealed '+label+' physical package'));
  for(const dx of[-.65,.65])mesh(group,new THREE.BoxGeometry(.3,.8,.57),metal,[x+dx,y,-5.025],label+' solder termination');
 }
 return{group,synth,amp,leads,crystal,capacitor,ledPackages};
}
function loudspeaker(host){
 const group=new THREE.Group();group.name='Synth fixed internal 8 ohm 1 W loudspeaker';group.position.set(0,8,0);host.body.add(group);
 const frameMat=materials.plastic(0x262b29,{roughness:.9}),paper=materials.plastic(0x353c37,{roughness:.98}),rubber=materials.plastic(0x1c2421,{roughness:.91}),steel=materials.metal(0x7f8981,{roughness:.53});
 // Rectangular speaker chassis and oval diaphragm back every native grille
 // opening. These are a physical speaker reconstruction, never a shadow decal.
 const frameShape=roundedRect(20.2,28,2.3),mouth=new THREE.Path();mouth.absellipse(0,0,8.65,12.35,0,Math.PI*2,false);frameShape.holes.push(mouth);
 const frame=solid(group,frameShape,.7,[0,0,5.65],frameMat,'Synth speaker rectangular chassis with true oval opening');
 const surroundShape=new THREE.Shape();surroundShape.absellipse(0,0,8.65,12.35,0,Math.PI*2,false);const surroundHole=new THREE.Path();surroundHole.absellipse(0,0,7.7,11.3,0,Math.PI*2,false);surroundShape.holes.push(surroundHole);
 const surround=solid(group,surroundShape,.24,[0,0,5.67],rubber,'Synth loudspeaker fixed oval suspension surround');
 // Closed cone surface: ring profile descends toward the voice-coil neck.
 const coneGeometry=new THREE.LatheGeometry([new THREE.Vector2(7.7,5.68),new THREE.Vector2(2.7,3.85),new THREE.Vector2(2.2,3.55),new THREE.Vector2(0,3.55)],80);coneGeometry.rotateX(Math.PI/2);coneGeometry.scale(1,11.3/7.7,1);
 const cone=mesh(group,coneGeometry,paper,[0,0,0],'Synth fixed recessed paper speaker cone');
 const capGeometry=new THREE.SphereGeometry(2.5,40,20,0,Math.PI*2,0,Math.PI/2);capGeometry.rotateX(Math.PI/2);capGeometry.scale(1,1.25,.33);
 const cap=mesh(group,capGeometry,paper,[0,0,3.65],'Synth fixed convex speaker dust cap');
 const basket=[];for(const x of[-7.5,7.5])for(const y of[-8.5,8.5]){
  const strut=mesh(group,new THREE.BoxGeometry(1.5,2.1,3.4),steel,[x,y,3.95],'Synth speaker rear basket rib');strut.rotation.y=x>0?.25:-.25;basket.push(strut);
 }
 const magnet=mesh(group,new THREE.CylinderGeometry(5,5,2.2,64).rotateX(Math.PI/2),materials.metal(0x747e76,{roughness:.65}),[0,0,2],'Synth speaker permanent magnet can');
 const back=mesh(group,new THREE.CylinderGeometry(5.15,5.15,.35,64).rotateX(Math.PI/2),steel,[0,0,.725],'Synth speaker fixed magnet rear plate');
 const terminals=[];for(const x of[-7.5,7.5])terminals.push(mesh(group,new THREE.BoxGeometry(1.25,2.0,.25),materials.metal(0xb9a86c,{roughness:.53}),[x,-8.5,2.25],'Synth speaker fixed solder terminal'));
 group.userData={role:'fixed-speaker-assembly',scope:'Physical frame, diaphragm, dust cap, basket and magnet only; no displacement, sound, playback, MIDI or acoustic simulation',inferred:true};
 return{group,frame,surround,cone,cap,basket,magnet,back,terminals};
}
function speakerConnection(host){
 const group=new THREE.Group();group.name='Synth concealed J2 1.25 mm 2P fixed speaker connector';group.position.set(-6.5,-4.3,-5.3);host.body.add(group);
 const white=materials.plastic(0xd9ded3,{roughness:.7}),contact=materials.metal(0xbbaa70,{roughness:.47});
 const floor=mesh(group,new THREE.BoxGeometry(4.8,3.4,.45),white,[0,0,.225],'Synth J2 insulating floor');
 const walls=[];for(const x of[-2.175,2.175])walls.push(mesh(group,new THREE.BoxGeometry(.45,3.4,2.1),white,[x,0,1.5],'Synth J2 socket side wall'));
 const rear=mesh(group,new THREE.BoxGeometry(3.9,.45,2.1),white,[0,-1.475,1.5],'Synth J2 recessed contact support');
 const roof=mesh(group,new THREE.BoxGeometry(3.9,3.4,.4),white,[0,0,2.35],'Synth J2 socket roof');
 const contacts=[];for(const x of[-.625,.625])contacts.push(mesh(group,new THREE.BoxGeometry(.3,2.4,.3),contact,[x,-.35,1.15],'Synth J2 recessed 1.25 mm speaker contact'));
 // Fixed two-wire internal loom, from the concealed socket to speaker terminals.
 const wires=[];for(const[x,color,dx]of[[-7.5,0x252a27,-.625],[7.5,0xb83225,.625]]){
  const points=[new THREE.Vector3(-6.5+dx,-2.6,-4.15),new THREE.Vector3(-6.0+dx,-1.1,-2.5),new THREE.Vector3(x,-2.0,.8),new THREE.Vector3(x,-.5,2.25)];
  wires.push(mesh(host.body,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),24,.24,10,false),materials.plastic(color,{roughness:.72}),[0,0,0],'Synth fixed internal speaker lead'));
 }
 group.userData={role:'concealed-fixed-connector',pitchMm:1.25,pins:2,scope:'J2 internal physical socket/contact estimate only; not an exposed mating Port or electrical model'};return{group,floor,walls,rear,roof,contacts,wires};
}
export function buildSynth(host){
 addCadParts(host,data,{shell:materials.plastic(0xe7e9e3,{roughness:.78})});
 const pcb=board(host),electronics=circuit(host),speaker=loudspeaker(host),internalConnector=speakerConnection(host);
 const socket=connector(host.body,48,true,{height:5.2});socket.name='Synth cyan open-top HY2.0-4P';socket.position.z=-5.2;socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · MIDI input',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V_IN',color:'red'},{n:3,name:'SYS_MIDI',color:'yellow'},{n:4,name:'NC',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'MIDI input over UART',scope:'Physical connector, attachment and four-wire cable pose only; no MIDI parsing, sound, synthesis, amplifier, audio, firmware or electrical behavior'}}));
 const fixing=screw(host.body,[0,-12,-7.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,2.0,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-12,-6.7],'Synth concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'SAM2695 visual package anchor',position:[0,7,-4.2],meta:{role:'visual-anchor',part:'SAM2695',scope:'Passive visual anchor only; no MIDI, notes, synthesis, sound, audio, firmware, sensor values or electrical commands'}}));
 host.synthAssembly={pcb,electronics,speaker,internalConnector,socket,port,fixing,shank};
 host.synthStickers=addStickers(host);
}
