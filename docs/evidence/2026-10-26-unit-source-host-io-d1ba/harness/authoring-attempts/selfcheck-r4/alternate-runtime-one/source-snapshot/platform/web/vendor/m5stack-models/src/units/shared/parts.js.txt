import * as THREE from 'three';
import { roundedSlab, roundedRect, decal } from '../../core/geometry.js';
import { materials } from '../../core/materials.js';

export const DIM = Object.freeze({ width:24, shellDepth:8, radius:4, holeDiameter:5, holePitch:16, holeFromBottom:12, connectorWidth:10 });
export function mesh(parent, geometry, material, position=[0,0,0], name='') {
  const m=new THREE.Mesh(geometry,material);m.position.fromArray(position);m.name=name;parent.add(m);return m;
}
export function slab(parent,w,h,depth,radius,position,material,holes=[],bevel=.35,name='') {
  return mesh(parent,roundedSlab({w,h,depth,radius,bevel,holes}),material,position,name);
}
// The middle shell cannot have a continuous lower rim across the Grove mouth.
// This single U-shaped contour follows the inner wall back around to the exterior.
export function shellSkirt(parent,spec,material){
  const b=.18,w=24-2*b,h=spec.h-2*b,r=4-b;
  const x=w/2,y=h/2,ix=10.6,iy=(spec.h-2.8)/2,ir=2.7,n=5.4;
  const s=new THREE.Shape();s.moveTo(-n,-y);s.lineTo(-n,-iy);s.lineTo(-ix+ir,-iy);
  s.absarc(-ix+ir,-iy+ir,ir,-Math.PI/2,-Math.PI,true);s.lineTo(-ix,iy-ir);
  s.absarc(-ix+ir,iy-ir,ir,Math.PI,Math.PI/2,true);s.lineTo(ix-ir,iy);
  s.absarc(ix-ir,iy-ir,ir,Math.PI/2,0,true);s.lineTo(ix,-iy+ir);
  s.absarc(ix-ir,-iy+ir,ir,0,-Math.PI/2,true);s.lineTo(n,-iy);s.lineTo(n,-y);
  s.lineTo(x-r,-y);s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);
  s.absarc(x-r,y-r,r,0,Math.PI/2);s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);
  s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
  const g=new THREE.ExtrudeGeometry(s,{depth:4-2*b,bevelEnabled:true,bevelThickness:b,bevelSize:b,bevelSegments:3,curveSegments:12});g.translate(0,0,b);g.computeVertexNormals();
  return mesh(parent,g,material,[0,0,-1.15],'shell-skirt');
}
export function unitPcb(parent,spec){
  const w=22.8,h=spec.h-1.6,r=3.7,x=w/2,y=h/2,n=5.3,top=-spec.h/2+7;
  const s=new THREE.Shape();s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,top);s.lineTo(n,top);s.lineTo(n,-y);s.lineTo(x-r,-y);
  s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);
  s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
  const hy=-spec.h/2+12;
  for(const cx of [-8,8])s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy:hy,path:new THREE.Path(),clockwise:true}));
  s.holes.push(roundedRect(3.8,3.8,1.9,{cx:0,cy:hy,path:new THREE.Path(),clockwise:true}));
  return mesh(parent,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:16}),materials.plastic(0x2c4639,{roughness:.91}),[0,0,.1],'Unit PCB');
}
// Open connector notch is part of the outside contour, not an invalid intersecting hole.
export function notchedSlab(parent,spec,holes,material){
  const b=.19,w=24-2*b,h=spec.h-2*b,r=4-b,x0=-w/2,x1=w/2,y0=-h/2,y1=h/2;
  const s=new THREE.Shape();s.moveTo(x0+r,y0);s.lineTo(-5.2,y0);s.lineTo(-5.2,-spec.h/2+7);s.lineTo(5.2,-spec.h/2+7);s.lineTo(5.2,y0);s.lineTo(x1-r,y0);
  s.absarc(x1-r,y0+r,r,-Math.PI/2,0);s.lineTo(x1,y1-r);s.absarc(x1-r,y1-r,r,0,Math.PI/2);s.lineTo(x0+r,y1);s.absarc(x0+r,y1-r,r,Math.PI/2,Math.PI);s.lineTo(x0,y0+r);s.absarc(x0+r,y0+r,r,Math.PI,Math.PI*1.5);
  for(const hole of holes)s.holes.push(roundedRect(hole.w,hole.h,hole.r,{cx:hole.cx,cy:hole.cy,path:new THREE.Path(),clockwise:true}));
  const g=new THREE.ExtrudeGeometry(s,{depth:1.25-2*b,bevelEnabled:true,bevelThickness:b,bevelSize:b,bevelSegments:3,curveSegments:12});g.translate(0,0,b);g.computeVertexNormals();
  return mesh(parent,g,material,[0,0,2.75],'front-shell');
}
export function cylinder(parent,radius,depth,position,material,name='') {
  return mesh(parent,new THREE.CylinderGeometry(radius,radius,depth,80).rotateX(Math.PI/2),material,position,name);
}
export function ring(parent,outer,inner,depth,position,material,name='') {
  const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);
  const h=new THREE.Path();h.absarc(0,0,inner,0,Math.PI*2,true);s.holes.push(h);
  const g=new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64});
  return mesh(parent,g,material,position,name);
}
export function connector(parent, h, digital=false,{height=5.2}={}) {
  const g=new THREE.Group();g.name='HY2.0-4P';parent.add(g);
  const c=materials.plastic(digital?0x20262d:0xb91229,{roughness:.57});
  // Official drawings show a 10 mm-wide connector face (5.2 mm ENV/PIR,
  // 4.8 mm Ultrasonic-I2C). Wall,
  // latch and insertion depths are photo-derived, not manufacturing dimensions.
  // The mouth is actual empty space: no painted four-hole plane or fake shadow cap.
  const y=-h/2;
  const floorBottom=4-height,floorTop=floorBottom+.65,wallHeight=4-floorTop;
  mesh(g,new THREE.BoxGeometry(10,6.6,.65),c,[0,y+3.3,floorBottom+.325],'Grove floor');
  for(const x of [-4.675,4.675])mesh(g,new THREE.BoxGeometry(.65,6.6,wallHeight),c,[x,y+3.3,(4+floorTop)/2],'Grove side wall');
  mesh(g,new THREE.BoxGeometry(8.7,.65,wallHeight),c,[0,y+6.275,(4+floorTop)/2],'Grove rear wall');
  for(const x of [-3.9,3.9])mesh(g,new THREE.BoxGeometry(.7,3.2,.6),c,[x,y+4.9,3.7],'Grove guide rail');
  mesh(g,new THREE.BoxGeometry(4.8,2.3,.45),c,[0,y+4.6,3.575],'Grove locking bridge');
  for(const x of [-3.65,3.65])mesh(g,new THREE.BoxGeometry(.6,1.2,.45),c,[x,y+1.8,3.775],'Grove latch shoulder');
  const pinMaterial=materials.metal(0xbdb18b,{roughness:.4});
  for(let i=0;i<4;i++){
    const pin=mesh(g,new THREE.BoxGeometry(.42,6.15,.42),pinMaterial,[(i-1.5)*2,y+4.075,1.1],'Grove contact pin');
    pin.userData.pin=i+1;
    mesh(g,new THREE.BoxGeometry(.42,.42,1.2),pinMaterial,[(i-1.5)*2,y+7.15,.5],'Grove solder tail');
  }
  return g;
}
export function mountingDetail(parent, x,y,z,back=false) {
  const mat=materials.plastic(0xd9dddb,{roughness:.72});
  ring(parent,3.18,2.52,.16,[x,y,z],mat,'mounting-counterbore');
  if(back) ring(parent,2.88,2.52,.22,[x,y,z+.01],materials.plastic(0xf0f1ef));
}
export function backLabel(parent,spec) {
  const long=spec.key==='sonic', labelH=long?37.5:12, cy=long?5.4:7;
  const print=decal(16.3,labelH,(ctx,W,H,s)=>{
    ctx.fillStyle='#d9dcda';ctx.fillRect(0,0,W,H);const p=.7*s;
    ctx.fillStyle='#292b2e';ctx.textBaseline='top';ctx.font=`900 ${1.9*s}px Arial`;
    if(long){
      ctx.fillText('ULTRASONIC',p,1*s);ctx.fillStyle='#ba142a';ctx.fillText('I2C',W-3.4*s,1*s);
      ctx.fillStyle='#343638';ctx.font=`${1.65*s}px Arial`;ctx.fillText('RANGE SENSOR',p,3.3*s);
      ctx.strokeStyle='#44484b';ctx.lineWidth=.16*s;ctx.beginPath();ctx.moveTo(2.3*s,10*s);ctx.lineTo(12*s,19*s);ctx.lineTo(2.3*s,28*s);ctx.stroke();
      ctx.beginPath();ctx.moveTo(13*s,8*s);ctx.lineTo(13*s,30*s);ctx.stroke();
      for(let y=8;y<30;y+=1){ctx.beginPath();ctx.moveTo(13*s,y*s);ctx.lineTo(14.1*s,(y+.55)*s);ctx.stroke();}
      ctx.font=`${1.1*s}px Arial`;ctx.fillStyle='#555';ctx.fillText('T',p,9*s);ctx.fillText('R',p,27*s);ctx.fillText('2–450 cm',4.7*s,31*s);
    } else {
      ctx.fillText(spec.key==='env'?'ENV. III':'MOTION',p,.6*s);
      ctx.fillText('SENSOR',p,2.8*s);ctx.font=`${1.25*s}px Arial`;
      ctx.fillText(spec.key==='env'?'SHT30 | QMP6988':'PIR  ·  HUMAN SENSOR',p,5.2*s);
    }
    const barY=H-4.8*s;ctx.fillStyle=spec.key==='pir'?'#34343c':'#cf3914';ctx.fillRect(p,barY,W-2*p,2.2*s);
    ctx.fillStyle='#fff';ctx.font=`700 ${1.65*s}px Arial`;ctx.fillText(spec.key==='pir'?'PORT. B · I/O':'PORT. A · I2C',p+.4*s,barY+.2*s);
    const names=spec.key==='pir'?['IN','OUT','5V','GND']:['SCL','SDA','5V','GND'];
    ['#f5f5ef','#ebc20c','#b52b25','#22272a'].forEach((c,i)=>{const x=p+i*(W-2*p)/4;ctx.fillStyle=c;ctx.fillRect(x,H-2.35*s,(W-2*p)/4,2*s);ctx.fillStyle=i<2?'#111':'#fff';ctx.font=`700 ${1.28*s}px Arial`;ctx.fillText(names[i],x+.17*s,H-2.12*s);});
  },{pxPerMm:40});
  print.position.set(0,cy,-4.025);print.rotation.y=Math.PI;parent.add(print);
  // Screw and subtle embossed maker text. Product wordmark is reproduced from the supplied official product photo.
  const hy=-spec.h/2+12;
  ring(parent,1.95,.9,.3,[0,hy,-3.98],materials.metal(0x969d9b), 'rear-screw');
  cylinder(parent,1.3,.15,[0,hy,-3.96],materials.metal(0xd2d7d6));
  const cross=decal(2.4,2.4,(ctx,W,H)=>{ctx.strokeStyle='#555d5c';ctx.lineWidth=W*.1;ctx.beginPath();ctx.moveTo(W*.2,H*.5);ctx.lineTo(W*.8,H*.5);ctx.moveTo(W*.5,H*.2);ctx.lineTo(W*.5,H*.8);ctx.stroke();});
  cross.rotation.y=Math.PI;cross.position.set(0,hy,-4.045);parent.add(cross);
  const mark=decal(9,5.8,(ctx,W,H)=>{ctx.strokeStyle='#bfc4c1';ctx.lineWidth=1.5;ctx.font=`500 ${H*.85}px Arial`;ctx.textBaseline='middle';ctx.strokeText('M5',2,H*.5);},{opacity:.6});
  mark.rotation.y=Math.PI;mark.position.set(0,-spec.h/2+5.4,-4.03);parent.add(mark);
}
export function transducer(parent,y){
  const alu=materials.metal(0xe1e4e6,{roughness:.3});
  cylinder(parent,8.25,.8,[0,y,4.2],materials.plastic(0xb8bdbe));
  ring(parent,8,7.35,6.2,[0,y,4.5],alu,'aluminium-transducer');
  ring(parent,7.98,7.05,.48,[0,y,10.7],materials.metal(0xe0e5e8,{roughness:.24}));
  cylinder(parent,7.34,.15,[0,y,9.15],materials.cavity(0x171b1e));
  // Fine woven grille, actual geometry. No moire-prone full-face bitmap.
  const wire=materials.metal(0x929b9e,{roughness:.6});
  const positions=[];for(let i=-12;i<=12;i++){const x=i*.52;const len=Math.sqrt(7.05**2-x*x);positions.push(x,-len,0,x,len,0,-len,x,.045,len,x,.045);}
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  const lattice=new THREE.LineSegments(geo,new THREE.LineBasicMaterial({color:0x889194,transparent:true,opacity:.8}));lattice.position.set(0,y,9.25);parent.add(lattice);
  ring(parent,7.45,7.15,.2,[0,y,9.4],wire);
}
