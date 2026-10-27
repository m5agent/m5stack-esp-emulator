import * as THREE from 'three';
import {Component,Port,Led,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion,FACE,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function bore(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
function board(host){
 // The two native mounting bosses and lower Grove are open outline reliefs.
 // No hole extends across the PCB's exterior contour.
 const s=new THREE.Shape(),cy=-12;
 s.moveTo(-6.4,22.7);s.lineTo(6.4,22.7);s.lineTo(10.4,18.7);s.lineTo(10.4,cy+4.35);s.lineTo(8,cy+4.35);
 s.absarc(8,cy,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,cy-4.35);s.lineTo(10.4,-18.7);s.lineTo(6.4,-22.7);
 s.lineTo(5.6,-22.7);s.lineTo(5.6,-16.5);s.lineTo(-5.6,-16.5);s.lineTo(-5.6,-22.7);s.lineTo(-6.4,-22.7);
 s.lineTo(-10.4,-18.7);s.lineTo(-10.4,cy-4.35);s.lineTo(-8,cy-4.35);s.absarc(-8,cy,4.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.4,cy+4.35);s.lineTo(-10.4,18.7);s.closePath();bore(s,0,cy,2.1);
 for(const x of [-3,-1,1,3])bore(s,x,-16.9,.32);
 return solid(host.body,s,.8,[0,0,-1.1],materials.plastic(0x274c3a,{roughness:.91}),'AudioPlayer physical PCB with native boss and Grove relief');
}
function audioJack(host){
 const g=new THREE.Group();g.name='AudioPlayer CN1 PJ-342 physical stereo jack';g.position.fromArray(spec.audio.position);g.quaternion.copy(FACE.top);host.body.add(g);
 const black=materials.plastic(0x151a18,{roughness:.73}),metal=materials.metal(0xbebfb4,{roughness:.37});
 // Local +Z points out of the audio end. Both annular parts have actual
 // inward-facing bore walls and a recessed end-stop, not a black disk at the lip.
 const face=roundedRect(6.6,5.5,.32);bore(face,0,0,1.75);
 const housing=solid(g,face,12.8,[0,0,-13.2],black,'PJ-342 body and true 3.5mm bore');
 const circle=new THREE.Shape();circle.absarc(0,0,2.55,0,Math.PI*2,false);bore(circle,0,0,1.75);
 const lip=solid(g,circle,.8,[0,0,-.8],black,'PJ-342 annular mouth lip');
 const stop=mesh(g,new THREE.BoxGeometry(3.5,3.5,.45),black,[0,0,-12.975],'PJ-342 recessed physical insertion stop');
 const contacts=[];for(const [n,z,a]of[['sleeve',-2.0,2.7],['ring',-6.7,-.45],['tip',-10.7,2.4]]){
  const contact=mesh(g,new THREE.BoxGeometry(.35,.9,2.4),metal,[1.67*Math.cos(a),1.67*Math.sin(a),z],'PJ-342 '+n+' recessed spring contact');contact.rotation.z=a;contacts.push(contact);
 }
 for(const [x,z]of[[-2.6,-3.5],[2.6,-7.0],[-2.6,-11.0]])mesh(g,new THREE.BoxGeometry(.5,.4,1.2),metal,[x,1.45,z],'PJ-342 PCB solder lead');
 const port=host.add(new Port({id:'audio',label:'PJ-342 · 3.5 mm stereo output',connector:'audio-3.5mm-trs',position:spec.audio.position,quaternion:portQuaternion('top'),hitSize:[5.2,1,5.2],pins:['Sleeve GND','Ring AUDIO_R','Tip AUDIO_L'].map(name=>({name})),meta:{role:'visual-connector',face:'top',scope:'Physical jack and mating frame only; no audio playback, electrical output, amplification or decoding'}}));return{group:g,housing,lip,stop,contacts,port};
}
function cardSocket(host){
 const g=new THREE.Group();g.name='AudioPlayer U2 5033981892 physical microSD socket';host.body.add(g);
 const steel=materials.metal(0xb6b9b3,{roughness:.51}),black=materials.plastic(0x202720,{roughness:.83}),gold=materials.metal(0xc3ab63,{roughness:.42});
 // Card insertion is from +X; the outer metal roof, side rails and insulating
 // carrier surround a true air channel. No pre-inserted card or filesystem state.
 const floor=mesh(g,new THREE.BoxGeometry(14.25,13.5,.2),black,[4.6,11.7,-2.6],'microSD insulating carrier');
 const roof=mesh(g,new THREE.BoxGeometry(14.25,13.5,.2),steel,[4.6,11.7,-3.9],'microSD folded metal roof');
 const walls=[];for(const y of[5.1,18.3])walls.push(mesh(g,new THREE.BoxGeometry(14.25,.3,1.5),steel,[4.6,y,-3.25],'microSD metal side rail'));
 const backstop=mesh(g,new THREE.BoxGeometry(.4,12.9,1.3),black,[-2.325,11.7,-3.25],'microSD recessed insertion stop');
 // End opening remains empty at X+11.85, between roof and floor.
 const contacts=[];for(let i=0;i<8;i++){
  const lead=mesh(g,new THREE.BoxGeometry(4.2,.42,.18),gold,[-.1,7.85+i*1.1,-2.9],'microSD recessed spring contact '+(i+1));lead.rotation.y=.10;contacts.push(lead);
 }
 for(const x of[-1.7,8.2])for(const y of[5.0,18.4])mesh(g,new THREE.BoxGeometry(1.5,.65,.25),steel,[x,y,-2.525],'microSD metal retention foot');
 const port=host.add(new Port({id:'sd',label:'microSD · 5033981892',connector:'microsd',position:spec.sd.position,quaternion:portQuaternion('right'),hitSize:[12,1,1.0],meta:{role:'visual-connector',face:'right',scope:'Physical storage-card socket and mating frame only; no card state, filesystem, hotplug, storage bus or playback behavior'}}));return{group:g,floor,roof,walls,backstop,contacts,port};
}
function electronics(host){
 const g=new THREE.Group();g.name='AudioPlayer concealed N9301 and passive packages';host.body.add(g);const dark=materials.plastic(0x202620,{roughness:.87}),metal=materials.metal(0xaaa997,{roughness:.57}),ceramic=materials.plastic(0xa69a77,{roughness:.9});
 const decoder=mesh(g,new THREE.BoxGeometry(4.0,5.0,1.0),dark,[0,2,.2],'AudioPlayer U1 N9301 decoder package');
 for(const x of[-2.5,2.5])for(let i=0;i<8;i++)mesh(g,new THREE.BoxGeometry(1,.32,.18),metal,[x,-.25+i*.65,-.15],'AudioPlayer N9301 lead');
 for(const[x,y]of[[-6.8,-1],[-6.8,-3.0],[6.8,-1.3],[6.8,-3.2],[-5.5,5],[-6.4,9],[6.0,1]]){
  mesh(g,new THREE.BoxGeometry(1.3,.75,.45),ceramic,[x,y,-.075],'AudioPlayer schematic passive package');for(const dx of[-.5,.5])mesh(g,new THREE.BoxGeometry(.3,.75,.47),metal,[x+dx,y,-.075],'AudioPlayer passive termination');
 }return{group:g,decoder};
}
class BlueBusyLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:spec.led.color});}
}
export function buildAudioPlayer(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe4e6e0,{roughness:.8}),lens:materials.plastic(0xcbd6d8,{roughness:.5,transparent:true,opacity:.72})});
 const pcb=board(host),audio=audioJack(host),sd=cardSocket(host),circuit=electronics(host);
 const socket=connector(host.body,48,true,{height:5.2});socket.name='AudioPlayer cyan open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical connector, attachment and four-wire cable appearance only; no serial command, supply or playback behavior'}}));
 const guide=native['AudioPlayer native BUSY light guide'];guide.removeFromParent();
 const led=host.add(new BlueBusyLed({id:'busy-led',label:'D1 · blue BUSY indicator',mesh:guide,color:spec.led.color,glowSize:2.8,radius:.5,meta:{role:'externally-driven-indicator',color:'fixed-blue',scope:'External on/brightness appearance only; no automatic BUSY, playback, UART or firmware behavior'}}));led.glow.position.fromArray(spec.led.position);
 // A true 0603 package sits below the native light guide. Its lens follows the
 // same external appearance command without inventing a second logical LED.
 const ledPackage=mesh(host.body,new THREE.BoxGeometry(1.6,.8,.55),materials.plastic(0xd3d7d0,{roughness:.63}),[7.9,-18.1,-.025],'AudioPlayer D1 BLUE 0603 physical package');
 screw(host.body,[0,-12,-3.97],'back',1.4);const shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.8,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-12,-2.7],'AudioPlayer concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'AudioPlayer appearance anchor',meta:{role:'visual-anchor',scope:'No audio, MP3/WAV, file, card, protocol, electrical or firmware commands'}}));
 addStickers(host);
 host.audioPlayerAssembly={pcb,audio,sd,circuit,socket,port,led,guide,ledPackage,shank};
}
