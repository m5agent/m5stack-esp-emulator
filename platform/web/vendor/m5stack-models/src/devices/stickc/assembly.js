/** MIT. Own source halves, independent supported interfaces and movement. */
import * as T from 'three';
import {materials,Port,Led} from '../../core/index.js';
import {mesh,slab,grove,FACE,portQuaternion} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {usbC} from '../../modeling/connectors.js';
import {nativeParts,source} from './native-data.js';
import {NativePress} from './NativePress.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
import {DIM,spec,HAT_PINS,GROVE_PINS} from './dimensions.js';
const add=(p,size,pos,mat,name)=>mesh(p,new T.BoxGeometry(...size),mat,pos,name);
const block=(p,w,h,d,r,pos,mat,name,holes=[])=>{const o=slab(p,w,h,d,r,pos,mat,holes,.04);o.name=name;return o;};
function field(id,p){
 if(id==='a'){if(Math.abs(p.x)>6.85||p.y< -17.5002||p.y> -9.8998)return null;const t=T.MathUtils.clamp((p.y+17.5)/7.6,0,1);return{w:t,gradient:[0,t>0&&t<1?1/7.6:0,0]};}
 if(id==='b'){if((p.x<9.0||p.x>11.75)||p.y<5.2||p.y>11.0||p.z< -3.1||p.z>1.5)return null;const t=T.MathUtils.clamp((1.5-p.z)/4.6,0,1);return{w:t,gradient:[0,0,t>0&&t<1?-1/4.6:0]};}
 if(p.x> -10.3||p.y< -16.3999||p.y> -12.6001||p.z< -1.901||p.z>4.5)return null;const t=T.MathUtils.clamp((4.5-p.z)/6.4,0,1);return{w:t,gradient:[0,0,t>0&&t<1?-1/6.4:0]};
}
export function buildAssembly(host){
 const shellMat=materials.plastic(0xff6c19,{roughness:.71}),black=materials.plastic(0x1d2421,{roughness:.9}),metal=materials.metal(0xb1b7ac,{roughness:.45}),boardMat=materials.plastic(0x215941,{roughness:.9});
 const nativeRoot=new T.Group();nativeRoot.rotation.y=Math.PI;host.body.add(nativeRoot);const parts={};for(const p of nativeParts){const g=new T.BufferGeometry();for(const[k,values]of Object.entries(p.attributes)){if(k==='index')g.setIndex(new T.Uint16BufferAttribute(values,1));else g.setAttribute(k,k==='sourceFaceIndex'?new T.Uint32BufferAttribute(values,1):k==='sourceAttributeWord'?new T.Uint16BufferAttribute(values,1):new T.Float32BufferAttribute(values,3));}const o=new T.Mesh(g,shellMat);o.name=spec.name+' own native '+p.id;o.position.fromArray(p.position);o.userData={source:'official-structure',sourceFaceCount:p.triangles};nativeRoot.add(o);parts[p.id]=o;}
 const a={nativeRoot,parts,source,geometry:'own-native-halves-plus-supported-inferred-internals'};
 for(const[id,part,label,axis,gpio]of[['a','front-shell','Button A',[0,0,-1],'G37'],['b','rear-shell','Button B',[-1,0,0],'G39'],['power','front-shell','AXP192 power/reset intention',[1,0,0],'AXP192 PWR_KEY']]){
  a[id]=host.add(new NativePress({id,label,body:host.body,shell:parts[part],field:p=>field(id,p),travel:DIM[id].travel,axis,position:DIM[id].position,meta:{gpio,role:'visual-control',surfaceCenter:DIM[id].position,surfaceFace:id==='a'?'front':id==='b'?'right':'left',travelSource:'Inferred normalized visual travel;no power or firmware action'}}));
 }
 a.a.hit(parts['front-shell'],h=>a.a.acceptHit(h));a.power.hit(nativeRoot,h=>a.power.acceptHit(h));
 // Native walls remain intact. Supported solid board/package envelopes close
 // hidden recesses but clear each real socket and moving molded cap.
 const pcb=new T.Shape();const outline=[[-10.3,-20.8],[-5.7,-20.8],[-5.7,-17.7],[5.7,-17.7],[5.7,-20.8],[10.3,-20.8],[10.3,5],[8.7,5],[8.7,11.2],[10.3,11.2],[10.3,21],[-10.3,21],[-10.3,-12.4],[-8.7,-12.4],[-8.7,-18.8],[-10.3,-18.8]];outline.forEach(([x,y],i)=>i?pcb.lineTo(x,y):pcb.moveTo(x,y));pcb.closePath();a.pcb=mesh(host.body,new T.ExtrudeGeometry(pcb,{depth:.8,bevelEnabled:false}),boardMat,[0,0,.3],spec.name+' inferred main PCB with connector/key reliefs');
 a.battery=block(host.body,16.9,27.0,3.3,.8,[0,1.3,-4.6],materials.metal(0xb4b8ac,{roughness:.82}),spec.name+' 95mAh battery envelope');
 const d=DIM.display;
 a.lcdBack=block(host.body,d.window[0]+2,d.window[1]+1.8,.8,.65,[0,d.position[1],4.1],metal,spec.name+' LCD module supported back');
 a.glass=block(host.body,d.window[0],d.window[1],.18,.3,[0,d.position[1],d.position[2]-.21],materials.glossy(0x070b0c,{roughness:.2}),spec.name+' physical display glass');
 for(const[x,y]of[[-8.7,-5],[8.7,-5],[-8.7,14],[8.7,14]])block(host.body,1.3,3.1,3.9,.2,[x,y,-4.5],shellMat,spec.name+' supported PCB rib');
 a.switches={};for(const[id,pos,size]of[['a',[0,-13.4,3.9],[5,5,.9]],['b',[8.8,8,0],[1.1,5.3,4.6]],['power',[-8.8,-15,2],[1.1,4.4,4.0]]])a.switches[id]=add(host.body,size,pos,black,spec.name+' fixed '+id+' switch backing');
 for(const[x,y]of[[-5,2],[5,-5],[4,14]])block(host.body,4.2,4.2,.7,.2,[x,y,1.1],black,spec.name+' inferred package envelope');
 a.usb=usbC(host,{...DIM.usb,face:'bottom',depth:5.2});a.grove=grove(host,{...DIM.grove,face:'bottom',w:10.4,h:5.4,depth:5.8});const plane=a.grove.children.find(o=>o.geometry?.type==='PlaneGeometry');if(plane){plane.removeFromParent();plane.geometry.dispose();plane.material.dispose();}host.port('grove').pins=GROVE_PINS.map((name,i)=>({n:i+1,name}));
 // Top row is a real eight-well housing, with closed walls/16 spring contacts.
 const hat=new T.Group();hat.position.set(0,23.3,-5.2);hat.quaternion.copy(FACE.top);host.body.add(hat);a.hat=hat;const holes=Array.from({length:8},(_,i)=>({w:1.65,h:1.65,r:.05,cx:(i-3.5)*2.54}));a.hatHousing=block(hat,20.82,3.04,3,.2,[0,0,-2.8],black,spec.name+' eight real HAT wells',holes);a.hatStops=[];a.hatContacts=[];
 for(const h of holes){const shape=roundedRect(1.65,1.65,.05);shape.holes.push(roundedRect(1.02,1.02,.025,{path:new T.Path(),clockwise:true}));mesh(hat,new T.ExtrudeGeometry(shape,{depth:2.3,bevelEnabled:false}),black,[h.cx,0,-2.6],spec.name+' HAT four socket bore walls');a.hatStops.push(add(hat,[1.65,1.65,.16],[h.cx,0,-2.68],black,spec.name+' HAT deep stop'));for(const s of[-1,1])a.hatContacts.push(add(hat,[.12,.72,.82],[h.cx+s*.37,0,-1.9],metal,spec.name+' HAT recessed spring contact'));add(host.body,[.36,3.4,.36],[h.cx,20.6,-5.2],metal,spec.name+' HAT contact solder tail');}
 host.add(new Port({id:'hat',label:'HAT 1×8 · 2.54 mm',connector:'m5.hat',position:[0,23.5,-5.2],quaternion:portQuaternion('top'),pins:HAT_PINS.map((name,i)=>({n:i+1,name})),hitSize:[21,.5,3],pinGrid:{cols:8,rows:1,pitch:2.54,center:[0,0],order:i=>8-i},meta:{role:'visual-connector',face:'top'}}));
 a.label=block(host.body,21,37,.08,.6,[0,4.5,-7.065],materials.plastic(0xedece2,{roughness:.88}),spec.name+' permanent rear label carrier');a.label.userData.role='physical-label-substrate';
 a.mounts=[];for(const x of[-8,8]){const ring=roundedRect(3.0,3.0,1.5);ring.holes.push(roundedRect(1.0,1.0,.5,{path:new T.Path(),clockwise:true}));const head=mesh(host.body,new T.ExtrudeGeometry(ring,{depth:.15,bevelEnabled:false,curveSegments:32}),metal,[x,-19.5,-7.08],spec.name+' retained rear screw');a.mounts.push(head);add(host.body,[1,1,.15],[x,-19.5,-6.6],metal,spec.name+' mount blind stop');}
 const ir=block(host.body,1.6,1.5,1.1,.2,[-11.35,17.0,-.8],black,spec.name+' passive IR package');a.ir=ir;
 const lens=new T.Mesh(new T.BoxGeometry(1.7,.65,.28),materials.plastic(0xcb2116,{roughness:.24}));lens.name=spec.name+' physical red LED lens';a.red=host.add(new Led({id:'red',label:'Red LED · G10 visual output',mesh:lens,position:[-11.9,17,-.3],quaternion:FACE.left,color:0xff2010,glowSize:2.4,radius:.3,meta:{gpio:'G10',role:'externally-driven-visual'}}));
 block(host.body,3.0,1.8,1,.2,[-10.5,-4,0],black,spec.name+' microphone package/backstop');

 host.stickAssembly=a;return a;
}
