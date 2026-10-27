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
 // The real board has open mounting-boss scallops and a C-shaped air gap
 // around the BME688 island. These are not painted cutouts or a filled shell.
 const s=new THREE.Shape();s.moveTo(-6.4,13.8);s.lineTo(6.4,13.8);s.lineTo(10.4,9.8);s.lineTo(10.4,.35);s.lineTo(8,.35);
 s.absarc(8,-4,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-8.35);s.lineTo(10.4,-9.8);s.lineTo(6.4,-13.8);
 s.lineTo(5.6,-13.8);s.lineTo(5.6,-8.5);s.lineTo(-5.6,-8.5);s.lineTo(-5.6,-13.8);s.lineTo(-6.4,-13.8);
 s.lineTo(-10.4,-9.8);s.lineTo(-10.4,-8.35);s.lineTo(-8,-8.35);s.absarc(-8,-4,4.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.4,.35);s.lineTo(-10.4,9.8);s.closePath();bore(s,0,-4,2.1);
 for(const x of [-3,-1,1,3])bore(s,x,-8.1,.32);
 const thermal=new THREE.Path(),a=-70*Math.PI/180,b=250*Math.PI/180;
 thermal.absarc(0,8,4,a,b,false);thermal.lineTo(2.05*Math.cos(b),8+2.05*Math.sin(b));thermal.absarc(0,8,2.05,b,a,true);thermal.closePath();s.holes.push(thermal);
 const pcb=solid(host.body,s,.8,[0,0,-.3],materials.plastic(0x202723,{roughness:.92}),'ENV Pro black PCB with thermal isolation and open mounting relief');
 pcb.userData={role:'physical-pcb',scope:'Photo-reconstructed shape and thermal-isolation gap, no trace-level electrical or production assembly model'};return pcb;
}
function sensor(host){
 const group=new THREE.Group();group.name='ENV Pro BME688 physical sensor package';group.position.set(0,8,.5);host.body.add(group);
 const substrate=mesh(group,new THREE.BoxGeometry(3,3,.13),materials.plastic(0x373b31,{roughness:.78}),[0,0,.065],'BME688 LGA substrate');
 const metal=materials.metal(0xbabbb3,{roughness:.55});
 const flange=solid(group,roundedRect(2.95,2.95,.13),.12,[0,0,.13],metal,'BME688 metal flange');
 const profile=roundedRect(2.8,2.8,.28);bore(profile,.6,-.6,.175);
 const lid=solid(group,profile,.68,[0,0,.25],metal,'BME688 physical metal lid with real gas vent');
 // The bore remains an air passage through the lid and ends at an interior
 // support below the opening; no decal or opaque plane seals the vent mouth.
 const interior=mesh(group,new THREE.CylinderGeometry(.175,.175,.08,32).rotateX(Math.PI/2),materials.plastic(0x292d26,{roughness:1}),[.6,-.6,.21],'BME688 recessed internal vent floor');
 const pads=[];for(const y of[-1.2,1.2])for(const x of[-1.2,-.4,.4,1.2])pads.push(mesh(group,new THREE.BoxGeometry(.4,.4,.10),materials.metal(0xb8ae85,{roughness:.48}),[x,y,.05],'BME688 LGA contact pad'));
 group.userData={role:'physical-sensor-package',part:'BME688',packageMm:[3,3,.93],scope:'Passive metal-lid appearance only; no gas, humidity, pressure, temperature, IAQ, I2C or firmware behavior',inferred:spec.source.inferred};
 return {group,substrate,flange,lid,interior,pads};
}
function supportElectronics(host){
 const dark=materials.plastic(0x252724,{roughness:.83}),metal=materials.metal(0xb1b3aa,{roughness:.57}),ceramic=materials.plastic(0xa89d79,{roughness:.91}),parts=[];
 const regulator=mesh(host.body,new THREE.BoxGeometry(1.6,1.6,.55),dark,[-6.2,3.2,.775],'ENV Pro VRH3301 regulator package');parts.push(regulator);
 for(const[x,y]of[[-6.2,1.3],[-6.2,-.3],[-4.3,1.3],[-4.3,-.3],[-1.9,3.2],[.1,3.2]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.3,.75,.5),ceramic,[x,y,.75],'ENV Pro ceramic capacitor'));for(const dx of[-.51,.51])parts.push(mesh(host.body,new THREE.BoxGeometry(.28,.75,.52),metal,[x+dx,y,.75],'ENV Pro capacitor termination'));
 }
 for(const[x,y]of[[3.2,1.8],[5.2,1.8],[6.5,-10.8],[6.5,-12.3],[-6.5,-12.3]])parts.push(mesh(host.body,new THREE.BoxGeometry(.9,.6,.35),dark,[x,y,.675],'ENV Pro resistor or ESD package'));
 parts.push(mesh(host.body,new THREE.BoxGeometry(2.0,1.0,.55),dark,[-6.5,-10.7,.775],'ENV Pro input protection fuse'));
 return parts;
}
export function buildENVPro(host){
 addCadParts(host,data,{shell:materials.plastic(0x5f615e,{roughness:.85})});
 const pcb=board(host),bme688=sensor(host),electronics=supportElectronics(host);
 const socket=connector(host.body,32,false,{height:5.2});socket.name='ENV Pro red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no bus or electrical behavior'}}));
 screw(host.body,[0,-4,-3.97],'back',1.4);
 const shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.6,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.65],'ENV Pro concealed fastening screw shank');
 host.add(new Component({id:'sensor',label:'BME688 visual package anchor',position:[0,8,1.43],meta:{role:'visual-anchor',part:'BME688',scope:'No commands, sensor values, gas/IAQ algorithms, I2C, electrical or autonomous light behavior'}}));
 addStickers(host);
 host.envProAssembly={pcb,bme688,electronics,socket,port,shank};
}
