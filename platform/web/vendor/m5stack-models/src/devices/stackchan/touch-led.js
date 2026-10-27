import * as THREE from 'three';
import {Led,materials} from '../../core/index.js';
import {hitButton} from '../../modeling/parts.js';

// Roof-slot datums fitted to the unchanged head-shell: the 5 mm corner is
// centred at X +/-22, Y30.25; both slots run along Z near -18.5..10.75.
// Six equal visual cells per side are inferred, not a PCB/electrical mapping.
const R=5.03,ANGLE=Math.PI/4,GUIDE_Z=-3.9,GUIDE_LENGTH=29;
function frame(side,z){
 const normal=new THREE.Vector3(side*Math.cos(ANGLE),Math.sin(ANGLE),0),along=new THREE.Vector3(0,0,side<0?1:-1),tangent=new THREE.Vector3(-side*Math.sin(ANGLE),Math.cos(ANGLE),0);
 return {position:[side*22+normal.x*R,30.25+normal.y*R,z],quaternion:new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(along,tangent,normal))};
}
/** A closed curved light-pipe section. X is along the guide, Y across its arc,
 * Z points out of the roof. Rounded end tapers stay inside the real slot. */
function guideGeometry(length,{roundLow=false,roundHigh=false,outer=5.025,inner=4.55,halfAngle=.19}={}){
 const uSteps=24,aSteps=16,positions=[],indices=[],row=aSteps+1,layer=(uSteps+1)*row;
 for(const radius of [outer,inner])for(let u=0;u<=uSteps;u++){
  const x=(u/uSteps-.5)*length,edge=Math.min(roundLow?x+length/2:Infinity,roundHigh?length/2-x:Infinity),t=Math.min(1,edge/.9),width=Math.sqrt(Math.max(0,1-(1-t)**2));
  for(let a=0;a<=aSteps;a++){const phi=(a/aSteps*2-1)*halfAngle*width;positions.push(x,radius*Math.sin(phi),radius*Math.cos(phi)-R);}
 }
 const quad=(a,b,c,d,flip=false)=>indices.push(...(flip?[a,c,b,b,c,d]:[a,b,c,b,d,c]));
 for(let u=0;u<uSteps;u++)for(let a=0;a<aSteps;a++){const i=u*row+a;quad(i,i+row,i+1,i+row+1);quad(layer+i,layer+i+row,layer+i+1,layer+i+row+1,true);}
 for(let u=0;u<uSteps;u++){const lo=u*row,hi=lo+aSteps;quad(lo,layer+lo,lo+row,layer+lo+row);quad(hi,hi+row,layer+hi,layer+hi+row);}
 for(let a=0;a<aSteps;a++){quad(a,a+1,layer+a,layer+a+1);const i=uSteps*row+a;quad(i,layer+i,i+1,layer+i+1);}
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.setIndex(indices);geometry.computeVertexNormals();geometry.computeBoundingBox();return geometry;
}

export function addTouchLed(host){
 const group=new THREE.Group();group.name='Head touch targets and RGB light guides';host.body.add(group);
 const touches=[],lights=[],guides=[];
 // Official BSP touch_sensor.h defines Front/Middle/Back. Exact electrode
 // boundaries are unavailable: these compact hit areas cover the plain top
 // surface and avoid Grove/IR openings. They add no visible cap or movement.
 for(const [i,region,z]of [[0,'front',2],[1,'middle',-10],[2,'back',-22]]){
  const touch=hitButton(host,{id:`touch-${i+1}`,label:`Top touch ${i+1} · ${region}`,position:[0,35.27,z],w:37,h:9,face:'top',meta:{capacitive:true,actuation:'capacitive',physicalZone:region,physicalIndex:i,source:'Official StackChan-BSP touch_sensor.h Front/Middle/Back; target boundaries inferred',electricalPad:null,scope:'input intent only; no capacitance values, gesture recognition or firmware'}});
  touch.travel=0;touch.longPressMs=0;group.add(touch.object3d);touches.push(touch);
 }
 for(const side of [-1,1]){
  const name=side<0?'left':'right',placement=frame(side,GUIDE_Z),guide=new THREE.Mesh(guideGeometry(GUIDE_LENGTH,{roundLow:true,roundHigh:true}),materials.glossy(0xa2b5b0,{roughness:.4,transparent:true,opacity:.88}));
  guide.name=`${name} continuous RGB light guide`;guide.position.fromArray(placement.position);guide.quaternion.copy(placement.quaternion);guide.userData={role:'rgb-light-guide',slotSource:'Official head-shell recess and A180 top/side photos; native curved approximation'};group.add(guide);guides.push(guide);
  const gap=.12,length=(28.5-gap*5)/6;
  for(let i=0;i<6;i++){
   const z=10.35-length/2-i*(length+gap),p=frame(side,z),front=i===0,back=i===5;
   const lens=new THREE.Mesh(guideGeometry(length,{roundLow:side<0?back:front,roundHigh:side<0?front:back,outer:5.04,inner:4.7,halfAngle:.15}),materials.glossy(0xa4b6b1,{roughness:.38}));lens.name=`${name} RGB guide segment ${i+1}`;
   const led=host.add(new Led({id:`rgb-${name}-${i+1}`,label:`${name} RGB ${i+1} · front-to-back physical cell`,mesh:lens,position:p.position,quaternion:p.quaternion,radius:0,glowSize:0,meta:{role:'externally-driven-visual',physicalSide:name,physicalIndex:i+1,physicalOrder:'front-to-back',electricalIndex:null,mapping:'Physical segmentation only; no assertion of U1-U12 chain order',source:'Official WS2812C x12 and BSP RGB_LED left6/right6; spacing and diffusion inferred',scope:'external color/brightness only; no touch-to-light or firmware response'}}),group);
   lights.push(led);
  }
 }
 group.userData={role:'head-touch-and-rgb',source:'Official Si12T three zones, WS2812C x12, BSP Front/Middle/Back and left6/right6; head-shell roof apertures',electricalBehavior:false};
 return {group,touches,lights,guides};
}
