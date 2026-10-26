import * as THREE from 'three';
import {Device,Module,Component,Button,Display,Led,Port,VisualJoint,materials} from '../../core/index.js';
import {basisQuaternion} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {mesh,slab,grove,FACE,portQuaternion,screw} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

// Local display treatment: the native API remains an external framebuffer.
// The official configuration photo shows white monochrome emitters, not RGB.
class WhiteOLED extends Display{
 constructor(options){super(options);this.material.fragmentShader=this.material.fragmentShader.replace('vec3 c = texture2D(map, (cell + 0.5) / res).rgb;','vec3 c = texture2D(map, (cell + 0.5) / res).rgb;\n  c = vec3(dot(c, vec3(0.2126, 0.7152, 0.0722)));');}
}

// The U-shaped tongue is part of the original closed CAD shell. Flex its real
// vertices, with zero displacement at the hinge; never overlay a replacement cap
// or remove source triangles. The .25 mm free-end travel is a visual estimate.
class NativeFlexureButton extends Button{
 constructor(shell){
  const hit=new THREE.Mesh(new THREE.PlaneGeometry(7.7,6.5),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));
  hit.name='RollerCAN native tongue input surface';hit.position.z=.02;
  super({id:'press',label:'Bottom A flexure button',mesh:hit,position:spec.press.center,quaternion:basisQuaternion([0,0,1],[-1,0,0],[0,-1,0]),axis:[0,0,-1],travel:spec.press.travelMm,meta:{role:'visual-control',visualMotion:'native-flexure',surfaceCenter:spec.press.center,surfaceFace:'bottom',travelSource:'0.25 mm appearance estimate; original native tongue flexes from its outer hinge; rated switch travel unconfirmed',scope:'input intent only; no configuration menu or firmware behavior'}});
  // The target is input geometry, not the visible tongue. Keep it 0.02 mm
  // outside the neutral surface for the entire press, so the native CAD face
  // cannot win a coplanar pick or occlude the target while the tongue flexes.
  this.object3d.add(hit);this.meta.inputTargetOffsetMm=.02;
  this.shell=shell;this.restPositions=shell.geometry.attributes.position.array.slice();this.restNormals=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.restPositions.length/3);this.lastDepth=0;
  for(let i=0;i<this.weights.length;i++){const x=this.restPositions[i*3],y=this.restPositions[i*3+1],z=this.restPositions[i*3+2];if(Math.abs(x)<=4.051&&z>=-20.001&&z<=-10.949&&y<=-15.049)this.weights[i]=THREE.MathUtils.clamp((z+20)/8,0,1);}
  const index=shell.geometry.index.array,affected=new Set();
  for(let f=0;f<index.length;f+=3)if(this.weights[index[f]]||this.weights[index[f+1]]||this.weights[index[f+2]])for(let k=0;k<3;k++)affected.add(index[f+k]);
  this.normalVertices=Uint32Array.from(affected);this.normalMask=new Uint8Array(this.weights.length);for(const i of this.normalVertices)this.normalMask[i]=1;
  // Include unchanged incident faces when deriving the local rotation, while
  // retaining the original indexed crease groups. Never recalculate the rest
  // of the shell's CAD normals as an incidental effect of pressing A.
  this.normalTriangles=[];for(let f=0;f<index.length;f+=3)if(this.normalMask[index[f]]||this.normalMask[index[f+1]]||this.normalMask[index[f+2]])this.normalTriangles.push(f);
  this.restNormalSums=new Float64Array(this.restPositions.length);this.currentNormalSums=new Float64Array(this.restPositions.length);this.normalScratch={from:new THREE.Vector3(),to:new THREE.Vector3(),normal:new THREE.Vector3(),rotation:new THREE.Quaternion()};
  this.sumLocalFaceNormals(this.restPositions,this.restNormalSums);
  this.meta.deformedNativeVertices=this.weights.filter(w=>w>0).length;
  this.meta.localNormalVertices=this.normalVertices.length;
 }
 sumLocalFaceNormals(positions,target){
  target.fill(0);const index=this.shell.geometry.index.array;
  for(const f of this.normalTriangles){const a=index[f]*3,b=index[f+1]*3,c=index[f+2]*3,ux=positions[c]-positions[b],uy=positions[c+1]-positions[b+1],uz=positions[c+2]-positions[b+2],vx=positions[a]-positions[b],vy=positions[a+1]-positions[b+1],vz=positions[a+2]-positions[b+2],nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,length=Math.hypot(nx,ny,nz);if(!length)continue;for(let k=0;k<3;k++){const i=index[f+k];if(!this.normalMask[i])continue;target[i*3]+=nx/length;target[i*3+1]+=ny/length;target[i*3+2]+=nz/length;}}
 }
 syncLocalNormals(){
  this.sumLocalFaceNormals(this.shell.geometry.attributes.position.array,this.currentNormalSums);const attribute=this.shell.geometry.attributes.normal,{from,to,normal,rotation}=this.normalScratch;
  for(const i of this.normalVertices){const offset=i*3;from.fromArray(this.restNormalSums,offset);to.fromArray(this.currentNormalSums,offset);normal.fromArray(this.restNormals,offset);if(from.lengthSq()>1e-20&&to.lengthSq()>1e-20){from.normalize();to.normalize();if(from.distanceToSquared(to)>1e-24)normal.applyQuaternion(rotation.setFromUnitVectors(from,to));}attribute.setXYZ(i,normal.x,normal.y,normal.z);}attribute.needsUpdate=true;
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth!==this.lastDepth){const a=this.shell.geometry.attributes.position;for(let i=0;i<this.weights.length;i++)if(this.weights[i])a.setY(i,this.restPositions[i*3+1]+depth*this.weights[i]);a.needsUpdate=true;if(depth===0){this.shell.geometry.attributes.normal.array.set(this.restNormals);this.shell.geometry.attributes.normal.needsUpdate=true;}else this.syncLocalNormals();this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.lastDepth=depth;}return changed;}
 dispose(){this.shell=null;this.restPositions=null;this.restNormals=null;this.weights=null;this.normalVertices=null;this.normalMask=null;this.normalTriangles=null;this.restNormalSums=null;this.currentNormalSums=null;this.normalScratch=null;super.dispose();}
}

class FixedRedLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0xff2820});}
}

function lathe(parent,profile,name,material){return mesh(parent,new THREE.LatheGeometry(profile.map(p=>new THREE.Vector2(...p)),128),material,[0,0,0],name);}
function topRingBoard(parent){
 const s=new THREE.Shape(),edge=4.3,end=17,r=2,c=7.071,relief=3.3,offset=c-edge,dy=Math.sqrt(relief*relief-offset*offset),a=Math.atan2(dy,offset);
 s.moveTo(-edge+r,-end);s.lineTo(edge-r,-end);s.absarc(edge-r,-end+r,r,-Math.PI/2,0);
 for(const cy of [-c,c]){s.lineTo(edge,cy-dy);s.absarc(c,cy,relief,-Math.PI+a,Math.PI-a,true);}
 s.lineTo(edge,end-r);s.absarc(edge-r,end-r,r,0,Math.PI/2);s.lineTo(-edge+r,end);s.absarc(-edge+r,end-r,r,Math.PI/2,Math.PI);
 for(const cy of [c,-c]){s.lineTo(-edge,cy+dy);s.absarc(-c,cy,relief,a,-a,true);}
 s.lineTo(-edge,-end+r);s.absarc(-edge+r,-end+r,r,Math.PI,Math.PI*1.5);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,0,3.2,0,Math.PI*2,true);s.holes.push(bore);
 const pcb=mesh(parent,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x254134,{roughness:.91}),[0,11.25,0],'RollerCAN rotating top-ring PCB with real through-bore relief');pcb.rotation.x=-Math.PI/2;return pcb;
}
function mainBoard(host){
 const s=new THREE.Shape(),r=4.8,q=Math.sqrt(r*r-1),n=1.2;
 function corner(cx,cy,start,end){
  // The native corner pillar occupies more material than its LEGO bore.
  // Its full 4.8 mm relief meets the adjacent 2.6 mm mounting-hole relief;
  // follow the union's actual boundary as an open notch, not overlapping holes.
  const sx=Math.sign(cx)*12,sy=Math.sign(cy)*12,dx=sx-cx,dy=sy-cy,d=Math.hypot(dx,dy),small=1.7,a=(r*r-small*small+d*d)/(2*d),h=Math.sqrt(r*r-a*a),mx=cx+a*dx/d,my=cy+a*dy/d;
  const points=[[mx-h*dy/d,my+h*dx/d],[mx+h*dy/d,my-h*dx/d]],tau=Math.PI*2,angle=p=>Math.atan2(p[1]-cy,p[0]-cx),delta=p=>((start-angle(p))%tau+tau)%tau;
  points.sort((a,b)=>delta(a)-delta(b));const [first,last]=points;
  s.absarc(cx,cy,r,start,angle(first),true);s.absarc(sx,sy,small,Math.atan2(first[1]-sy,first[0]-sx),Math.atan2(last[1]-sy,last[0]-sx),true);s.absarc(cx,cy,r,angle(last),end,true);
 }
 // Four corner reliefs and the two edge slots are open outline arcs, not
 // invalid holes crossing the board perimeter. The smaller mounting clearances
 // join those edge reliefs and are therefore part of the outline as well.
 s.moveTo(-16+q,-17);s.lineTo(-n,-17);s.absarc(0,-17,n,Math.PI,0,true);s.lineTo(16-q,-17);
 corner(16,-16,Math.atan2(-1,-q),Math.atan2(q,1));
 // Inferred CAN connector edge clearance, open to the PCB perimeter.
 s.lineTo(17,-8.6);s.lineTo(12.35,-8.6);s.lineTo(12.35,8.6);s.lineTo(17,8.6);s.lineTo(17,16-q);
 corner(16,16,Math.atan2(-q,1),Math.atan2(1,-q));s.lineTo(n,17);s.absarc(0,17,n,0,-Math.PI,true);s.lineTo(-16+q,17);
 corner(-16,16,Math.atan2(1,q),Math.atan2(-q,-1));s.lineTo(-17,-16+q);
 corner(-16,-16,Math.atan2(q,-1),Math.atan2(-1,q));s.closePath();
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x254134,{roughness:.91}),[0,-12.3,0],'RollerCAN fixed PCB with mounting clearances');pcb.rotation.x=-Math.PI/2;
 for(const [x,z,w,h]of [[0,0,6,6],[6.2,-2,3,4],[-5,6,3,3]]){const part=slab(host.body,w,h,.9,.18,[x,-11.45,z],materials.plastic(0x1e2723),[],.03);part.rotation.x=-Math.PI/2;part.name='RollerCAN concealed fixed circuit package';}
 host.parts.pcb=pcb;
}
function display(host){
 const q=basisQuaternion([0,0,1],[-1,0,0],[0,-1,0]);
 const packageMesh=slab(host.body,16.4,12.4,.8,.35,[0,-17.1,0],materials.plastic(0x17231e,{roughness:.85}),[],.04);packageMesh.quaternion.copy(q);packageMesh.name='RollerCAN OLED physical module carrier';
 const glass=slab(host.body,14,10.4,1.05,.3,[0,-18.1,0],materials.glossy(0x121a18,{roughness:.2}),[],.025);glass.quaternion.copy(q);glass.name='RollerCAN OLED full-depth glass stack';
 host.add(new WhiteOLED({id:'lcd',label:'Bottom 0.66 inch white OLED',width:64,height:48,size:spec.lcd.activeMm,style:'oled',position:spec.lcd.position,quaternion:q,glass:false,blackLevel:0,offColor:0x080b0a,meta:{role:'externally-driven-framebuffer',monochrome:true,emissionColor:'white',source:'U188 specification and official U188 7.webp',orientation:'bottom (-Y); screen up points -X, screen right points +Z',activeAreaSource:'0.66 inch diagonal and 64:48 aspect; active dimensions inferred, not OLED manufacturing drawing',scope:'framebuffer appearance only; no controller, menu, registers or protocol'}}));
}
function openGrove(host,options,name){
 const socket=grove(host,options);socket.name=name;
 // Both actual red sockets are open above their contacts in the photos.
 const roof=socket.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);
 if(!roof)throw new Error('RollerCAN Grove roof not found');const red=roof.material;roof.removeFromParent();roof.geometry.dispose();
 for(const x of [-4.15,4.15])mesh(socket,new THREE.BoxGeometry(.65,.8,options.depth),red,[x,options.h/2-.4,-options.depth/2],name+' upper guide');
 mesh(socket,new THREE.BoxGeometry(3.4,.65,1.0),red,[0,1.0,-options.depth+.5],name+' short latch');
 const port=host.get(options.id??'grove','port');port.pins=['GND','5V','SDA','SCL'].map((name,i)=>({n:i+1,name}));port.meta={...port.meta,sku:'U188',part:'HY2.0-4P',scope:'visual connector only; no supply or I2C behavior'};
 return {socket,port};
}
function canSockets(host){
 const {faceX,rowsY,width:w,height:h,depth:d}=spec.can,black=materials.plastic(0x151a17,{roughness:.6}),gold=materials.metal(0xc8b66b,{roughness:.36});
 const q=basisQuaternion([0,0,-1],[0,1,0],[1,0,0]);
 function rectangle(x0,y0,x1,y1){const p=new THREE.Path;p.moveTo(x0,y0);p.lineTo(x0,y1);p.lineTo(x1,y1);p.lineTo(x1,y0);p.closePath();return p;}
 function splitPin(parent,x,y,r,thickness){
  // Actual male power contacts are split tubes, not solid screw heads.
  const s=new THREE.Shape(),a=.13;s.absarc(x,y,r,a,Math.PI*2-a,false);s.lineTo(x+(r-thickness)*Math.cos(a),y-(r-thickness)*Math.sin(a));s.absarc(x,y,r-thickness,-a,-Math.PI*2+a,true);s.closePath();
  mesh(parent,new THREE.ExtrudeGeometry(s,{depth:2.8,bevelEnabled:false,curveSegments:16}),gold,[0,0,-4.1],'RollerCAN XT30 split male power contact');
 }
 return rowsY.map((y,i)=>{
  const group=new THREE.Group;group.position.set(faceX,y,0);group.quaternion.copy(q);group.name='RollerCAN fixed PWRCAN '+(i+1)+' XT30(2+2) male socket';host.body.add(group);
  const s=new THREE.Shape(),c=.45;s.moveTo(-w/2+c,-h/2);s.lineTo(w/2-c,-h/2);s.lineTo(w/2,-h/2+c);s.lineTo(w/2,h/2-c);s.lineTo(w/2-c,h/2);s.lineTo(-w/2+c,h/2);s.lineTo(-w/2,h/2-c);s.lineTo(-w/2,-h/2+c);s.closePath();
  // Two open cells, with a real central separator and backstop, close the native
  // case aperture. Socket envelope is inferred from U188 photos and native cutout.
  s.holes.push(rectangle(-7.65,-1.5,-5.15,1.5),rectangle(-4.65,-1.5,7.65,1.5));
  mesh(group,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:12}),black,[0,0,-d],'RollerCAN XT30 real cavity walls and signal divider');
  mesh(group,new THREE.BoxGeometry(w-.7,h-.7,.65),black,[0,0,-d+.325],'RollerCAN XT30 rear insulator');
  splitPin(group,-2.4,0,.78,.18);splitPin(group,3.5,0,.78,.18);
  for(const v of [-.7,.7])mesh(group,new THREE.CylinderGeometry(.2,.2,3.2,16),gold,[-6.4,v,-3.2],'RollerCAN XT30 signal contact').rotation.x=Math.PI/2;
  const port=host.add(new Port({id:'can-'+(i+1),label:'PWRCAN '+(i+1)+' · XT30(2+2)',connector:'xt30-2+2',position:[faceX,y,0],quaternion:basisQuaternion([0,0,1],[1,0,0],[0,1,0]),hitSize:[w,1,h],pins:['PVIN','GND','CAN_H','CAN_L'].map(name=>({name})),meta:{role:'visual-connector',face:'right',sku:'U188',pinNumbering:'Signals identified by official product label and schematic; physical numbered order not claimed',scope:'visual connector only; no supply, bus, protocol, motor or electrical behavior'}}));return{socket:group,port};
 });
}

function debug(host){
 const {position,width:w,height:h,depth:d,pitch}=spec.debug,g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE.back);g.name='RollerCAN fixed MX1.25-5P debug socket';host.body.add(g);const white=materials.plastic(0xdddcd4,{roughness:.65});
 for(const x of [-w/2+.3,w/2-.3])mesh(g,new THREE.BoxGeometry(.6,h,d),white,[x,0,-d/2],'RollerCAN debug side guide');for(const y of [-h/2+.25,h/2-.25])mesh(g,new THREE.BoxGeometry(w-.9,.5,d),white,[0,y,-d/2],'RollerCAN debug edge');mesh(g,new THREE.BoxGeometry(w-.8,h-.8,.5),white,[0,0,-d+.25],'RollerCAN debug back');
 for(let i=0;i<5;i++)mesh(g,new THREE.BoxGeometry(.3,.3,2.5),materials.metal(0xbeb69a),[(i-2)*pitch,0,-2.3],'RollerCAN debug contact '+(i+1));
 host.add(new Port({id:'debug',label:'MX1.25-5P debug',connector:'mx1.25-5p',position,quaternion:portQuaternion('back'),hitSize:[w,1,h],meta:{role:'visual-connector',face:'back',scope:'no programming, debug or electrical behavior'}}));
}
function fixedRgb(host){
 return [-4.9,4.9].map((z,i)=>{
  const chip=new THREE.Mesh(new THREE.BoxGeometry(2,2,.5),materials.plastic(0xe0e3d9,{roughness:.55}));chip.position.z=-2.1;chip.name='RollerCAN fixed RGB'+(i+1)+' physical package';
  const led=host.add(new Led({id:'rgb-'+(i+1),label:'Fixed RGB '+(i+1),mesh:chip,position:[-19.3,-15.3,z],quaternion:FACE.left,glowSize:7,radius:.4,meta:{role:'externally-driven-visual',part:'WS2812C-2020',physicalOrder:'spatial left/right only; U4/U5 chain identity not inferred',scope:'no automatic mode, fault or power response'}}));led.glow.position.z=.75;return led;
 });
}
function rotor(host,parts){
 const can=lathe(host.body,[[6.3,-4.8],[19.9,-4.8],[20.5,-4.2],[20.5,-1.2],[20.2,-1.05],[20.2,-.85],[20.5,-.7],[20.5,5.1],[20.2,5.25],[20.2,5.45],[20.5,5.6],[20.5,9.4],[19.9,10],[6.3,10],[6.3,-4.8]],'RollerCAN rotating D3504 outer bell',materials.metal(0x161a18,{roughness:.47}));
 // The 16 mm fixed boss and 12.6 mm bore come from the official motor drawing.
 lathe(host.body,[[3,-7.3],[8,-7.3],[8,-4.8],[6.15,-4.8],[6.15,9.8],[3,9.8],[3,-7.3]],'RollerCAN fixed central bearing and shaft sleeve',materials.metal(0x3b403c,{roughness:.58}));
 const topBoard=topRingBoard(host.body);
 const output=openGrove(host,spec.groveTop,'RollerCAN rotating red Grove socket');output.port.meta={...output.port.meta,role:'visual-connector',mechanicalParent:'rotor',connectionEvidence:'Official U188 slip-ring description and top-ring schematic; no electrical propagation'};
 const guide=parts['RollerCAN native rotating power light guide'];
 // addCadParts shares palette entries. This independently driven indicator
 // must own a material, so changing LED1 cannot tint the fixed RGB diffuser.
 guide.material=guide.material.clone();guide.material.name='RollerCAN dedicated top red indicator diffuser';
 guide.geometry.computeBoundingBox();const center=guide.geometry.boundingBox.getCenter(new THREE.Vector3());guide.geometry.translate(-center.x,-center.y,-center.z);
 const topLed=host.add(new FixedRedLed({id:'top-led',label:'Top-ring red indicator',mesh:guide,position:center.toArray(),color:0xff2820,radius:.3,glowSize:2.2,meta:{role:'externally-driven-visual',colorMode:'fixed-red',part:'Top-ring LED1 RED',scope:'no automatic supply indicator or electrical behavior'}}));topLed.glow.position.set(0,3.5,-5.75);
 const joint=host.add(new VisualJoint({id:'rotor',label:'U188 slip-ring output rotor',axis:[0,1,0],continuous:true,meta:{axisEvidence:'Official U188 40 mm assembly drawing, D3504 motor drawing and coaxial native assembled STL; physical rotating top is +Y',demoRpmMax:60,mechanicalChildren:['expansion plate','D3504 outer bell','top-ring PCB','grove-top','top-led'],neutralPhase:'Native STL assembled position; arbitrary relative to independent product photos',scope:'externally requested visual angle/rpm only; no motor dynamics, encoder value or physical capability claim'}}));
 joint.adopt(parts['RollerCAN native rotating expansion plate'],can,topBoard,output.socket,output.port.object3d,topLed.object3d);
 host.rollerMechanism={joint,can,topBoard,output,topLed};
}
function fasteners(host){
 // Heads occupy the native countersinks. The holes and cap fit are preserved.
 for(const x of [-7.071,7.071])for(const z of [-7.071,7.071]){const group=screw(host.parts['RollerCAN native rotating expansion plate'],[x,19.9,z],'top',1.6);group.name='RollerCAN rotating M3 fastener';group.children[0].name='RollerCAN rotating M3 head';}
 for(const x of [-8,8])for(const z of [-10.5,10.5]){const group=screw(host.body,[x,-19.96,z],'bottom',1.3);group.name='RollerCAN fixed face fastener';group.children[0].name='RollerCAN fixed face screw head';}
}
function build(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0x686e67,{roughness:.8}),lens:materials.plastic(0xdce3d7,{roughness:.52,transparent:true,opacity:.82})});
 mainBoard(host);display(host);openGrove(host,spec.grove,'RollerCAN fixed red Grove socket');host.canSockets=canSockets(host);debug(host);fixedRgb(host);host.add(new NativeFlexureButton(parts['RollerCAN native fixed OLED face shell']));rotor(host,parts);fasteners(host);
 addStickers(host);
 host.add(new Component({id:'sensor',label:'RollerCAN visual anchor',meta:{role:'visual-anchor',sku:'U188',scope:'no encoder counts, current, torque, bus, firmware or electrical model'}}));

}
export class Model extends Device{static meta={id:'m5stack.unit.rollercan',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:spec.keymap};build(){build(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.rollercan.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:spec.keymap};build(options={}){buildGroveModuleAssembly(this,build,options);}}
export {spec};
export default Model;
