/** MIT. Own T2 native shell and original supported optical/electronic assembly. */
import * as T from 'three';
import {materials,Button} from '../../core/index.js';
import {slab,mesh,grove,FACE} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {usbC} from '../../modeling/connectors.js';
import {nativeParts,source} from './native-data.js';
import {NativePress} from './NativePress.js';import {WheelRotation} from './WheelRotation.js';import{DIM,GROVE_PINS}from './dimensions.js';
const box=(p,s,v,m,n)=>mesh(p,new T.BoxGeometry(...s),m,v,n);
const plate=(p,w,h,d,r,v,m,n)=>{const o=slab(p,w,h,d,r,v,m,[],.04);o.name=n;return o;};
const cyl=(p,r,d,v,m,n)=>mesh(p,new T.CylinderGeometry(r,r,d,48).rotateX(Math.PI/2),m,v,n);
function ring(p,r,bore,d,v,m,n){const s=new T.Shape().absarc(0,0,r,0,Math.PI*2,false),h=new T.Path().absarc(0,0,bore,0,Math.PI*2,true);s.holes.push(h);return mesh(p,new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:40}),m,v,n);}
function field(id,p){
 if(id==='a'){if(Math.abs(p.x)>5.7||p.y< -20.2||p.y> -12.1||p.z<8.4)return null;const t=T.MathUtils.clamp((p.y+20.2)/8.1,0,1);return{w:t,gradient:[0,t>0&&t<1?1/8.1:0,0]};}
 if(id==='b'){if(p.x<10.0||p.y<6.7||p.y>11.3||p.z< -2.95||p.z>3.15)return null;const t=T.MathUtils.clamp((3.15-p.z)/6.1,0,1);return{w:t,gradient:[0,0,t>0&&t<1?-1/6.1:0]};}
 if(p.x> -10.4||p.x< -12.1||p.y< -16.0||p.y> -11.0||p.z< -2.95||p.z>3.15)return null;const t=T.MathUtils.clamp((3.15-p.z)/6.1,0,1);return{w:t,gradient:[0,0,t>0&&t<1?-1/6.1:0]};
}
export function buildAssembly(host){
 const black=materials.plastic(0x171c1e,{roughness:.96}),nylon=materials.plastic(0x252725,{roughness:.97}),metal=materials.metal(0xa0a39d,{roughness:.5});const a={source};
 const nativeRoot=new T.Group();nativeRoot.rotation.y=Math.PI;nativeRoot.position.fromArray(source.rootRigidTransform.translationMm);host.body.add(nativeRoot);a.nativeRoot=nativeRoot;const frontFrame=new T.Group();nativeRoot.add(frontFrame);a.parts={};
 for(const p of nativeParts){const g=new T.BufferGeometry();for(const[k,v]of Object.entries(p.attributes)){if(k==='index')g.setIndex(new T.Uint16BufferAttribute(v,1));else g.setAttribute(k,k==='sourceFaceIndex'?new T.Uint32BufferAttribute(v,1):k==='sourceAttributeWord'?new T.Uint16BufferAttribute(v,1):new T.Float32BufferAttribute(v,3));}const o=new T.Mesh(g,nylon);o.position.fromArray(p.position);o.name='StickT2 own native '+p.id;o.userData={source:'official-structure',sourceFaceCount:p.triangles};(p.id==='front-shell'?frontFrame:nativeRoot).add(o);a.parts[p.id]=o;}
 for(const[id,axis,gpio]of[['a',[0,0,-1],'G37'],['b',[-1,0,0],'G39'],['power',[1,0,0],'AXP192 PWR_KEY']])a[id]=host.add(new NativePress({id,label:id==='power'?'AXP192 power/reset intention':'Button '+id.toUpperCase(),body:host.body,shell:a.parts[id==='b'?'rear-shell':'front-shell'],field:p=>field(id,p),travel:DIM[id].travel,axis,position:DIM[id].position,meta:{gpio,role:'visual-control',surfaceCenter:DIM[id].position,surfaceFace:id==='a'?'front':id==='b'?'right':'left',travelSource:'Normalized visual own-source material field;not rated mechanism or power operation'}}));
 // A and power share one source shell;B uses the actual rear cap. Distinct ancestors keep
 // each actual intersection routed without partitioning or duplicating faces.
 a.a.hit(a.parts['front-shell'],h=>a.a.acceptHit(h));a.b.hit(a.parts['rear-shell'],h=>a.b.acceptHit(h));a.power.hit(nativeRoot,h=>a.power.acceptHit(h));
 const boardShape=new T.Shape();const outline=[[-10,-21],[-5.6,-21],[-5.6,-17.7],[5.6,-17.7],[5.6,-21],[10,-21],[10,-12.2],[7.8,-12.2],[7.8,-3.5],[10,-3.5],[10,6.3],[8.5,6.3],[8.5,11.7],[10,11.7],[10,21],[-10,21],[-10,-10.5],[-8.5,-10.5],[-8.5,-16.4],[-10,-16.4]];outline.forEach(([x,y],i)=>i?boardShape.lineTo(x,y):boardShape.moveTo(x,y));boardShape.closePath();a.pcb=mesh(host.body,new T.ExtrudeGeometry(boardShape,{depth:.8,bevelEnabled:false}),materials.plastic(0x245641,{roughness:.9}),[0,0,.2],'StickT2 inferred own PCB with port/key/encoder reliefs');
 a.battery=plate(host.body,16.5,21.5,4.2,.7,[0,-9,-8.5],materials.metal(0xb1b4aa,{roughness:.8}),'StickT2 300mAh supported battery envelope');
 a.lcdBack=plate(host.body,17.0,28.1,1.0,.6,[0,8.0,7.9],metal,'StickT2 LCD supported metal back');a.optical=plate(host.body,16.4,27.1,1.1,.6,[0,8.0,8.9],black,'StickT2 LCD optical carrier');a.glass=plate(host.body,15.7,26.4,.2,.5,[0,8.0,11.08],materials.glossy(0x070c0e,{roughness:.18}),'StickT2 thick front cover glass');
 a.switches={};for(const[id,size,pos]of[['a',[4.8,5,.9],[0,-16,9]],['b',[1.1,5,5.2],[9.0,9,0]],['power',[1.1,5,5.2],[-9,-13.5,0]]])a.switches[id]=box(host.body,size,pos,black,'StickT2 fixed '+id+' switch backing');
 for(const[x,y]of[[-8,-4],[8,-2],[-8,16],[8,16]])plate(host.body,1.6,3.2,5.5,.25,[x,y,1.1],nylon,'StickT2 inferred molded board support');
 for(const[x,y]of[[-5,1],[5,16],[-5,-6]])plate(host.body,3.5,4.5,.9,.2,[x,y,1.1],black,'StickT2 passive concealed package');
 plate(host.body,2.8,2,1.0,.2,[-8,-7,1.2],black,'StickT2 passive SPM1423 microphone envelope');
 a.cameraBoard=plate(host.body,12.5,13,.8,.25,[0,8,-4.9],materials.plastic(0x35513d,{roughness:.9}),'StickT2 passive Lepton carrier board');a.cameraModule=plate(host.body,10.5,11.7,5.0,.5,[0,8,-10.0],metal,'StickT2 supported passive Lepton3.0 module envelope');
 const lens=new T.Group();lens.position.set(0,8,-11.5);lens.quaternion.copy(FACE.back);host.body.add(lens);a.cameraLens=lens;ring(lens,2.3,1.65,2.4,[0,0,-2.0],black,'StickT2 actual optical collar wall');cyl(lens,1.62,.18,[0,0,.30],materials.glossy(0x3e274b,{roughness:.12,metalness:.25}),'StickT2 passive backed LWIR front lens');cyl(lens,1.64,.35,[0,0,.08],black,'StickT2 solid optical backstop');
 a.usb=usbC(host,{...DIM.usb,face:'bottom'});a.grove=grove(host,{...DIM.grove,w:10.3,h:5.1,face:'bottom'});const plane=a.grove.children.find(o=>o.geometry?.type==='PlaneGeometry');if(plane){plane.removeFromParent();plane.geometry.dispose();plane.material.dispose();}host.port('grove').pins=GROVE_PINS.map((name,i)=>({n:i+1,name}));
 for(const x of[-3,-1,1,3]){box(host.body,[.38,1.2,.38],[x,-17.9,-2.9],metal,'StickT2 Grove folded contact tail');box(host.body,[.38,.38,3.3],[x,-17.3,-1.5],metal,'StickT2 Grove retained PCB leg');}
 a.mounts=[];for(const[z,outer,bore]of[[-4.2,3.5,2.9],[4.5,1.65,1.3]]){const f=new T.Group();f.position.set(-18.35,8,z);f.quaternion.copy(FACE.left);host.body.add(f);a.mounts.push(ring(f,outer,bore,4.8,[0,0,-4.8],metal,'StickT2 recessed '+(outer>2?'1/4-inch':'M3')+' mounting insert with actual bore'));cyl(f,bore,.3,[0,0,-5.05],black,'StickT2 physical mounting bore deep stop');}
 a.screws=[];for(const[x,y,z,face]of[[-14,14.7,11.9,'front'],[-14,1.4,11.9,'front'],[-8,-19.3,-11.95,'back'],[8,-19.3,-11.95,'back']]){const f=new T.Group();f.position.set(x,y,z);f.quaternion.copy(FACE[face]);host.body.add(f);a.screws.push(ring(f,1.6,.65,.15,[0,0,0],metal,'StickT2 retained recessed screw head'));cyl(f,.63,.12,[0,0,-.65],metal,'StickT2 screw head blind stop');}
 // Small 2021 wheel silhouette: dimension is fitted to own native side opening,
 // not a declared detent count or measured production encoder travel.
 const cap=new T.Group(),r=DIM.wheel.radius;a.wheelCap=cyl(cap,r,.85,[0,0,-.25],black,'StickT2 complete encoder push cap');a.wheelRim=ring(cap,r+.06,r-.65,.75,[0,0,-.38],black,'StickT2 visible encoder turning rim');a.wheelRibs=[];for(let i=0;i<20;i++){const t=i*Math.PI/10,o=box(cap,[.36,.52,.72],[r*Math.cos(t),r*Math.sin(t),-.17],black,'StickT2 closed encoder grip ridge');o.rotation.z=t;a.wheelRibs.push(o);}cyl(cap,1.15,2.0,[0,0,-1.6],metal,'StickT2 moving encoder shaft');
 a.press=host.add(new Button({id:'press',label:'Encoder wheel push · center',mesh:cap,position:DIM.wheel.position,quaternion:FACE.right,axis:[0,0,-1],travel:DIM.wheel.travel,longPressMs:0,meta:{gpio:'PA2 SW (as named in official PinMap)',role:'visual-control',travelSource:'Inferred visual shaft press;not rated switch mechanism'}}));
 const shaft=new T.Group();shaft.position.fromArray(DIM.wheel.position);shaft.quaternion.copy(FACE.right);host.body.add(shaft);
 // Own native side window extends beyond the reduced wheel. A supported fixed
 // receiver has real thickness and a shaft bore, so the battery and opposite
 // power-key opening do not become the visible background around the rotor.
 // Hidden receiver dimensions remain inferred from this own window/photo.
 const receiverShape=roundedRect(14.4,9.5,.65),shaftBore=new T.Path();shaftBore.absarc(0,0,1.32,0,Math.PI*2,true);receiverShape.holes.push(shaftBore);
 a.encoderStator=mesh(shaft,new T.ExtrudeGeometry(receiverShape,{depth:1.3,bevelEnabled:false,curveSegments:40}),black,[0,0,-3.62],'StickT2 fixed closed encoder receiver with actual shaft bore');
 a.encoderShaftStop=cyl(shaft,1.5,.16,[0,0,-3.70],black,'StickT2 encoder shaft bore deep stop');
 a.encoderReceiver={frame:shaft,housing:a.encoderStator,stop:a.encoderShaftStop,scope:'Own-window supported visual receiver;concealed package/BOM and dimensions inferred,not production mounting certification'};
 a.rotation=host.add(new WheelRotation({id:'rotation',label:'Encoder rim · drag to rotate',position:DIM.wheel.position,quaternion:FACE.right,meshes:[a.wheelRim,...a.wheelRibs],meta:{gpio:'PA3 EN_B / PA4 EN_A (official PinMap names)',demoRpmMax:40,scope:'Continuous signed angle intent;no detent or pulse count inferred'}}));a.rotation.adopt(a.press.object3d);
 host.stickT2Assembly=a;return a;
}
