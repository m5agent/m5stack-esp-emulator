import * as THREE from 'three';
import {Display,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function board(host){
 // Clockwise exterior with open reliefs around native mounting bosses and
 // Grove body. The central screw bore is a counter-clockwise inner contour.
 const s=new THREE.Shape();s.moveTo(-6.3,22);s.lineTo(6.3,22);s.lineTo(10.4,17.9);s.lineTo(10.4,-7.65);s.lineTo(8,-7.65);
 s.absarc(8,-12,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-16.35);s.lineTo(10.4,-18);s.lineTo(6.4,-22);
 s.lineTo(5.6,-22);s.lineTo(5.6,-16.5);s.lineTo(-5.6,-16.5);s.lineTo(-5.6,-22);s.lineTo(-6.4,-22);s.lineTo(-10.4,-18);s.lineTo(-10.4,-16.35);s.lineTo(-8,-16.35);
 s.absarc(-8,-12,4.35,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.4,-7.65);s.lineTo(-10.4,17.9);s.closePath();
 const hole=new THREE.Path();hole.absarc(0,-12,2.1,0,Math.PI*2,false);s.holes.push(hole);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:32}),materials.plastic(0x29483a,{roughness:.9}),[0,0,-1.5],'LCD physical PCB with clear native boss and Grove reliefs');
 pcb.userData={role:'physical-pcb',scope:'Appearance reconstruction, not production PCB geometry'};
 const components=[];const black=materials.plastic(0x232725,{roughness:.75}),silver=materials.metal(0xa7aea7,{roughness:.55});
 components.push(slab(host.body,7,7,.9,.15,[0,9,-.7],black,[],.025));components[0].name='LCD concealed ESP32-PICO-D4 package';
 components.push(slab(host.body,2.9,1.7,.85,.12,[-5.4,-4.7,-.7],black,[],.02));components[1].name='LCD concealed SPX3819 regulator package';
 for(const[x,y,w,h]of [[4.3,0,1.5,2],[5.4,-5,1.1,2.2],[-4.9,18,2,1],[-4.9,15.4,2,1],[-5.7,2.7,1.4,2]]){
  const c=slab(host.body,w,h,.55,.1,[x,y,-.7],materials.plastic(0x9c8f73,{roughness:.85}),[],.01);c.name='LCD concealed passive package';components.push(c);
  for(const sign of [-1,1]){const e=mesh(host.body,new THREE.BoxGeometry(w*.22,h,.57),silver,[x+sign*w*.39,y,-.41],'LCD passive metal end');components.push(e);}
 }
 // The official description identifies magnetic mounting. Two inferred bars sit behind
 // the native three-slot retainers so the back cannot look into an empty box.
 const magnets=[];for(const x of [-8.2,8.2])magnets.push(slab(host.body,2.9,7.4,1.1,.12,[x,3.3,-3.35],materials.metal(0x7d8581,{roughness:.5}),[],.02));
 for(const m of magnets)m.name='LCD rear magnetic mounting bar behind native retainer';
 return {pcb,components,magnets};
}

function screen(host,{pixelEffect=true}={}){
 const frame=slab(host.body,16.5,27.2,1.2,.32,[0,8.7,1.45],materials.metal(0x7d8582,{roughness:.63}),[],.04);frame.name='LCD solid module rear metal backplate';
 const backlight=slab(host.body,16.2,26.9,.67,.25,[0,8.7,2.65],materials.plastic(0xe3e4db,{roughness:.8}),[],.02);backlight.name='LCD solid backlight and diffuser stack';
 const glass=slab(host.body,16.1,26.7,.33,.23,[0,8.7,3.32],materials.plastic(0x111918,{roughness:.37}),[],.015);glass.name='LCD full-depth black glass substrate and inactive border';
 const fpc=slab(host.body,7.4,5.7,.15,.22,[0,-6.3,.7],materials.plastic(0x9d6730,{roughness:.7}),[],0);fpc.name='LCD folded amber FPC tail';
 const fpcSocket=slab(host.body,6.8,1.8,.8,.14,[0,-7.8,-.7],materials.plastic(0xe3e2d7,{roughness:.7}),[],.02);fpcSocket.name='LCD concealed FPC-0.5-8P connector';
 const latch=slab(host.body,5.9,.55,.25,.04,[0,-7.65,.1],materials.plastic(0x292d29),[],.01);latch.name='LCD FPC connector locking latch';
 for(let i=0;i<8;i++)mesh(host.body,new THREE.BoxGeometry(.2,.8,.05),materials.metal(0xc9ad70),[(i-3.5)*.5,-7.3,.18],'LCD FPC connector contact');
 const lcd=host.add(new Display({id:'lcd',label:'LCD 135×240 · ST7789V2',width:135,height:240,size:spec.lcd.activeMm,position:[0,8.7,spec.lcd.surfaceZ],touch:false,pixelEffect,glass:{size:[15.1,25.15],offset:.015,intensity:.13,roughness:.16},meta:{role:'external-framebuffer',driver:'ST7789V2',source:'U120 official resolution and pixel pitch; active area is pitch × resolution',scope:'External framebuffer and backlight only. No touch sensor, onboard ESP32 firmware, I2C register/command emulation or automatic content'}}));
 return {frame,backlight,glass,fpc,fpcSocket,latch,lcd};
}

export function buildLcd(host,options={}){
 addCadParts(host,data,{shell:materials.plastic(0xe6e8e2,{roughness:.78})});
 const electronics=board(host),display=screen(host,options);
 const socket=connector(host.body,48,false,{height:5.2});socket.name='LCD red open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector and attachment; no bus/electrical behavior'}}));
 screw(host.body,[0,-12,-3.98],'back',1.3);
 addStickers(host);
 host.lcdAssembly={...electronics,...display,socket,port};
}
