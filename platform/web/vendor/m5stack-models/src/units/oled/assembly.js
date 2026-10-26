import * as THREE from 'three';
import {Display,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function cylinder(parent,r,depth,p,mat,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),mat,p,name);}
function pcb(host){
 // Clockwise outside with open scallops around both native mounting bosses;
 // retaining-post and screw bores have counter-clockwise interior contours.
 const s=new THREE.Shape();s.moveTo(-6.4,26.5);s.lineTo(6.4,26.5);s.lineTo(10.35,22.55);s.lineTo(10.35,-12.65);s.lineTo(8,-12.65);
 s.absarc(8,-16,3.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.35,-19.35);s.lineTo(10.35,-22.55);s.lineTo(6.4,-26.5);
 s.lineTo(5.6,-26.5);s.lineTo(5.6,-20.5);s.lineTo(-5.6,-20.5);s.lineTo(-5.6,-26.5);s.lineTo(-6.4,-26.5);
 s.lineTo(-10.35,-22.55);s.lineTo(-10.35,-19.35);s.lineTo(-8,-19.35);s.absarc(-8,-16,3.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.35,-12.65);s.lineTo(-10.35,22.55);s.closePath();
 bore(s,0,-16,2.05);for(const x of [-8,8])for(const y of [-2,22])bore(s,x,y,1.45);
 for(const x of [-3,-1,1,3])bore(s,x,-20.1,.32);
 const b=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x244936,{roughness:.9}),[0,0,.05],'OLED PCB with open mounting and Grove relief');b.userData={role:'physical-pcb',scope:'Concealed visual reconstruction; no electrical traces or production geometry'};return b;
}
export function buildOled(host){
 addCadParts(host,data,{shell:materials.plastic(0xe4e6df,{roughness:.8})});
 const board=pcb(host),d=spec.display;
 const backing=mesh(host.body,new THREE.BoxGeometry(17.6,33.3,.85),materials.plastic(0x1b2021,{roughness:.8}),[0,d.centre[1],1.97],'OLED solid display module carrier');
 // The black glass is a volume, wider than the actual front aperture, so the
 // whole window is closed by the display assembly including its inactive edge.
 const glass=mesh(host.body,new THREE.BoxGeometry(16.8,32.3,.65),materials.glossy(0x050708,{roughness:.3}),[0,d.centre[1],2.7],'OLED physical black glass and inactive border');
 const display=host.add(new Display({id:'lcd',label:'1.3-inch SH1107 B/W OLED · portrait 64×128',width:d.width,height:d.height,size:d.size,position:[0,d.centre[1],d.z],style:'oled',touch:false,blackLevel:0,offColor:0x050708,glass:{size:[16.8,32.3],offset:.008,intensity:.09,roughness:.25},meta:{role:'external-framebuffer',monochrome:true,sourceResolution:d.nativeResolution,rasterRotationDeg:90,orientation:'portrait',monochromeMapping:'Luminance threshold 0.5 at render time; source buffer preserved',scope:'Externally written pixels only; no SH1107 registers, firmware, I2C or automatic content'}}));
 display.material.fragmentShader=display.material.fragmentShader.replace('vec3 c = texture2D(map, (cell + 0.5) / res).rgb;','vec3 c = vec3(step(0.5, dot(texture2D(map, (cell + 0.5) / res).rgb, vec3(0.2126, 0.7152, 0.0722))));');
 const flex=mesh(host.body,new THREE.BoxGeometry(8.2,3.3,.15),materials.plastic(0x9a6522,{roughness:.7}),[0,-9.8,1.14],'OLED concealed display flexible tail');
 const chips=[];for(const [x,y,w,h,z]of[[-4.8,-10.8,2.9,1.6,1.2],[3.1,-10.2,2.1,2.1,1.24],[-2.5,-12.1,1.55,1,1.15],[4.6,-12,1.4,.85,1.15]])chips.push(mesh(host.body,new THREE.BoxGeometry(w,h,.5),materials.plastic(0x222628,{roughness:.85}),[x,y,z],'OLED concealed driver/power package'));
 const magnets=[];for(const x of[-7.8,7.8])magnets.push(cylinder(host.body,1.35,.65,[x,22,-1.95],materials.metal(0xa2a6a5,{roughness:.45}),'OLED concealed rear magnetic fixing'));
 const socket=connector(host.body,56,false,{height:5.2});socket.name='OLED red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical attachment and cable pose only; no bus or electrical behavior'}}));
 screw(host.body,[0,-16,-3.97],'back',1.4);const shank=cylinder(host.body,.65,1.6,[0,-16,-2.65],materials.metal(0x919997,{roughness:.5}),'OLED concealed mounting screw shank');
 addStickers(host);
 host.oledAssembly={board,backing,glass,display,flex,chips,magnets,socket,port,shank};
}
