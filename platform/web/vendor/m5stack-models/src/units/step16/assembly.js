import * as THREE from 'three';
import {Component,Led,Port,VisualJoint,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import {addStickers} from './stickers.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
const tau=Math.PI*2;
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
function board(host){
 const s=new THREE.Shape();s.moveTo(-7.8,14.3);s.lineTo(7.8,14.3);s.lineTo(10.25,11.8);s.lineTo(10.25,.3);s.lineTo(8,.3);s.absarc(8,-4,4.3,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.25,-8.3);s.lineTo(10.25,-12.2);s.lineTo(8.3,-14.3);s.lineTo(5.5,-14.3);s.lineTo(5.5,-8.4);s.lineTo(-5.5,-8.4);s.lineTo(-5.5,-14.3);s.lineTo(-8.3,-14.3);s.lineTo(-10.25,-12.2);s.lineTo(-10.25,-8.3);s.lineTo(-8,-8.3);s.absarc(-8,-4,4.3,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.25,.3);s.lineTo(-10.25,11.8);s.closePath();
 bore(s,0,-4,1.9);for(const x of[-3,-1,1,3])bore(s,x,-8.7,.32);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x254c35,{roughness:.91}),[0,0,-1.8],'Step16 physical scalloped PCB with true mounting/Grove drillings');
 const metal=materials.metal(0xb5b7a5,{roughness:.47}),dark=materials.plastic(0x282d27,{roughness:.86}),packages=[];
 for(const[name,x,y,w,h,d]of[['STM32G031G8U6',0,6,4,4,.65],['ME6206A33XG',-5.8,.3,2.9,1.6,1.1],['RP1 BCD pullup network',4,1.4,2,1,.5],['RP2 segment resistor network',-7.2,2.8,2,1,.5],['RP3 segment resistor network',-7.2,11.8,2,1,.5]]){
  const part=slab(host.body,w,h,d,.08,[x,y,-1.8-d],dark,[],.02);part.name=`Step16 concealed ${name} package`;packages.push(part);
  for(const sign of[-1,1])for(let i=0;i<3;i++)mesh(host.body,new THREE.BoxGeometry(.28,.5,.12),metal,[x+(i-1)*w/3,y+sign*(h/2+.1),-1.86],`Step16 ${name} solder terminal`);
 }
 for(const[x,y]of[[-3,1.3],[3,1.3],[-3.7,12.5],[7.3,1.5],[-7.1,-10.9],[7.1,-10.9]])slab(host.body,1.2,.75,.45,.04,[x,y,-2.25],materials.plastic(0xb9aa80,{roughness:.9}),[],.015).name='Step16 concealed capacitor/resistor package';
 const swd=new THREE.Group();swd.name='Step16 internal J4 five-pad SWD service footprint';host.body.add(swd);for(let i=0;i<5;i++)mesh(swd,new THREE.CylinderGeometry(.35,.35,.06,24).rotateX(Math.PI/2),metal,[-2.54+i*1.27,12,-1.85],'Step16 J4 exposed PCB pad');
 return{pcb,packages,swd};
}
function rotary(host,cap){
 const dark=materials.plastic(0x343930,{roughness:.79}),metal=materials.metal(0xa0a58f,{roughness:.49}),[x,y]=spec.rotation.axis;
 const fixed=slab(host.body,7.8,7.8,3.4,.35,[x,y,-1],dark,[],.06);fixed.name='Step16 fixed GSMR-16 rotary DIP switch body';
 const plate=slab(host.body,7.5,7.5,.25,.18,[x,y,2.4],metal,[],.02);plate.name='Step16 fixed GSMR-16 retaining plate';
 for(const sign of[-1,1])for(const dy of[-2.4,0,2.4])mesh(host.body,new THREE.BoxGeometry(1.1,.65,.23),metal,[x+sign*4.05,y+dy,-.86],'Step16 GSMR-16 stationary solder tab');
 const shaft=mesh(host.body,new THREE.CylinderGeometry(1.5,1.5,2.0,48).rotateX(Math.PI/2),metal,[x,y,2.8],'Step16 moving rotary shaft seated beneath original cap');
 const rotation=host.add(new VisualJoint({id:'rotation',label:'Step16 16-position rotary cap',position:spec.rotation.axis,axis:[0,0,1],meta:{positions:16,detentDegrees:22.5,visualRangeDeg:[-180,180],axisEvidence:'Native cap circular base center, same assembly transform as shell',scope:'External visual angle only, including intermediate poses. Default at native CAD rest. No press, automatic rotation, detent snapping, BCD value, 0-F code, firmware zero/direction or segment/RGB linkage.'}}));rotation.adopt(cap,shaft);return{rotation,cap,shaft,fixed,plate};
}
/** Independent local emissive appearance behind the unchanged white front membrane. */
function frontDiffusion(front){
 const material=front.material.clone();front.material=material;const values=Array.from({length:8},()=>({value:0}));
 // 7-segment coordinates in host millimetres. Shapes are reconstructed from the lit photograph.
 const slots=[[-6,11.5,2.4,.72],[-3.55,9.35,.72,2.5],[-3.55,5.15,.72,2.5],[-6,3.0,2.4,.72],[-8.45,5.15,.72,2.5],[-8.45,9.35,.72,2.5],[-6,7.25,2.4,.72],[-2.9,2.9,.6,.6]];
 material.onBeforeCompile=shader=>{for(let i=0;i<8;i++)shader.uniforms[`step16Brightness${i}`]=values[i];shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nvarying vec3 vStep16Position;').replace('#include <begin_vertex>','#include <begin_vertex>\nvStep16Position = position;');shader.fragmentShader=shader.fragmentShader.replace('#include <common>','#include <common>\nvarying vec3 vStep16Position;\n'+values.map((_,i)=>`uniform float step16Brightness${i};`).join('\n'));const code=slots.map(([x,y,w,h],i)=>`vec2 step16Q${i} = max(abs(vStep16Position.xy - vec2(${x.toFixed(4)},${y.toFixed(4)})) - vec2(${(w/2).toFixed(4)},${(h/2).toFixed(4)}), vec2(0.0));\n float step16Mask${i} = exp(-dot(step16Q${i},step16Q${i})/0.28);\n totalEmissiveRadiance += vec3(1.0,0.51,0.075) * step16Brightness${i} * step16Mask${i} * smoothstep(3.65,3.96,vStep16Position.z) * 1.8;`).join('\n');shader.fragmentShader=shader.fragmentShader.replace('#include <emissivemap_fragment>','#include <emissivemap_fragment>\n'+code);};
 material.customProgramCacheKey=()=> 'step16-native-white-membrane-segments-v1';return{material,slots,values};
}
class SegmentLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:spec.display.fixedColor});this.glow.visible=false;this.onDiffusion?.(this.brightness);}
 dispose(){this.onDiffusion=null;super.dispose();}
}
function sevenSegment(host,front){
 const diffuse=frontDiffusion(front),backing=slab(host.body,7.6,12.6,1.8,.35,[-6,7.25,-1],materials.plastic(0xf0f0df,{roughness:.72}),[],.04);backing.name='Step16 physical FPC1 seven-segment display body under front membrane';
 const fpc=slab(host.body,4.2,3,.15,.12,[-5.7,.5,-.95],materials.plastic(0xb28e29,{roughness:.64}),[],.02);fpc.name='Step16 concealed 10-contact display flex tail';
 for(let i=0;i<10;i++)mesh(host.body,new THREE.BoxGeometry(.22,1.5,.04),materials.metal(0xbba55e),[-7.5+i*.4,.3,-.78],'Step16 display flex contact');
 const leds=diffuse.slots.map(([x,y,w,h],i)=>{
  const lens=new THREE.Mesh(new THREE.BoxGeometry(w,h,.25),materials.plastic(0xe6ddbe,{roughness:.45}));lens.name=`Step16 physical display segment ${i===7?'DP':'ABCDEFG'[i]}`;
  const id=i===7?'segment-dp':`segment-${'abcdefg'[i]}`;const led=host.add(new SegmentLed({id,label:`Warm yellow segment ${i===7?'DP':'ABCDEFG'[i]}`,position:[x,y,.925],mesh:lens,color:spec.display.fixedColor,radius:.1,glowSize:0,meta:{role:'externally-driven-visual',colorMode:'fixed-warm-yellow',part:'FPC1 A-G/DP',colorEvidence:spec.display.colorEvidence,scope:'Independent external on/brightness only; defaults off. No hexadecimal glyph encoder, automatic BCD read, angle/firmware association or framebuffer.'}}));led.onDiffusion=value=>{diffuse.values[i].value=value;};led.glow.visible=false;return led;
 });return{backing,fpc,leds,diffuse};
}
export function buildStep16(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77}),cap:materials.plastic(0xe9ebe5,{roughness:.69}),lens:materials.glossy(0xc3cec4,{roughness:.34})});
 const circuit=board(host),rotaryAssembly=rotary(host,native['Step16 complete native moving rotary cap']),display=sevenSegment(host,native['Step16 complete native front shell']);
 const socket=connector(host.body,32,false,{height:5.2});socket.name='Step16 red open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',scope:'Physical connector, four-wire cable attachment and pose only; no I2C, power or firmware behavior'}}));
 const guide=native['Step16 complete native RGB light guide'],rgbPosition=[7.9,-12.1,3.3];guide.geometry.translate(-rgbPosition[0],-rgbPosition[1],-rgbPosition[2]);
 const rgb=host.add(new Led({id:'rgb',label:'Independent WS2812C RGB indicator',mesh:guide,position:rgbPosition,radius:.2,glowSize:2.2,color:0x00bfff,meta:{role:'externally-driven-visual',colorMode:'rgb',part:'U3 WS2812C-2020',scope:'External color/on/brightness only, defaults off; original native light guide kept. No supply, angle, segment or firmware linkage.'}}));rgb.glow.position.set(0,-1.8,.7);
 const rgbPackage=slab(host.body,2,2,.8,.08,[7.9,-11.5,-1],materials.plastic(0xe7e5d6,{roughness:.64}),[],.03);rgbPackage.name='Step16 physical WS2812C-2020 package behind native guide';
 const fixing=screw(host.body,[0,-4,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.5,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-4,-2.7],'Step16 rear fixing screw shank');
 const sensor=host.add(new Component({id:'sensor',label:'Step16 physical assembly anchor',position:[4,7,2.2],meta:{role:'visual-anchor',scope:'No BCD data, input processing, electrical logic, I2C/registers, firmware or motor/stepper behavior'}}));
 const stickers=addStickers(host,native['Step16 complete native rear shell']);host.step16Assembly={native,circuit,rotary:rotaryAssembly,display,socket,port,rgb,rgbPackage,fixing,shank,sensor,stickers};
}
