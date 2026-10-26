import * as THREE from 'three';
import {roundedSlab,capsule,decal,basisQuaternion} from '../core/geometry.js';
import {materials} from '../core/materials.js';
import {Port,Button} from '../core/index.js';
export const FACE={front:new THREE.Quaternion(),back:basisQuaternion([-1,0,0],[0,1,0],[0,0,-1]),bottom:basisQuaternion([1,0,0],[0,0,1],[0,-1,0]),top:basisQuaternion([1,0,0],[0,0,-1],[0,1,0]),left:basisQuaternion([0,-1,0],[0,0,1],[-1,0,0]),right:basisQuaternion([0,1,0],[0,0,1],[1,0,0])};
export function portQuaternion(face){const q=new THREE.Quaternion();if(face==='bottom')q.setFromAxisAngle(new THREE.Vector3(0,0,1),Math.PI);else if(face==='left'||face==='right')q.setFromAxisAngle(new THREE.Vector3(0,0,1),face==='left'?Math.PI/2:-Math.PI/2);else if(face==='front'||face==='back')q.setFromAxisAngle(new THREE.Vector3(1,0,0),face==='front'?Math.PI/2:-Math.PI/2);return q;}
export function mesh(parent,g,m,position=[0,0,0],name=''){const o=new THREE.Mesh(g,m);o.position.fromArray(position);o.name=name;parent.add(o);return o;}
export function slab(parent,w,h,depth,radius,position,material,holes=[],bevel=.25){return mesh(parent,roundedSlab({w,h,depth,radius,holes,bevel}),material,position);}
export function disc(parent,r,position,material){return mesh(parent,new THREE.CircleGeometry(r,96),material,position);}
export function mark(parent,w,h,position,draw,face='front'){const o=decal(w,h,draw,{pxPerMm:30});o.position.fromArray(position);o.quaternion.copy(FACE[face]);parent.add(o);return o;}
export function textMark(parent,text,w,h,position,{color='#34383b',size=2,face='front',weight=700}={}){return mark(parent,w,h,position,(ctx,W,H,s)=>{ctx.fillStyle=color;ctx.font=`${weight} ${size*s}px Arial`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,W/2,H/2);},face);}
export function socket(host,{id='usb',label='USB-C',position,face='bottom',w=8.7,h=3.1,color=0x9b9fa3,connector='usb-c',pins=4}){
 const group=new THREE.Group();group.position.fromArray(position);group.quaternion.copy(FACE[face]);host.body.add(group);group.name=label;
 const shape=capsule(w,h);shape.holes.push(capsule(w-.6,h-.6,{path:new THREE.Path(),clockwise:true}));mesh(group,new THREE.ExtrudeGeometry(shape,{depth:.45,bevelEnabled:false,curveSegments:16}),materials.metal(color,{roughness:.38}),[0,0,-.4]);
 mesh(group,new THREE.ShapeGeometry(capsule(w-.5,h-.5)),materials.cavity(),[0,0,-.42]);
 mesh(group,new THREE.BoxGeometry(w*.72,.55,.15),materials.plastic(0x22292d),[0,0,-.2]);
 for(let i=0;i<pins;i++)mesh(group,new THREE.BoxGeometry(.22,.18,.08),materials.metal(0xc7af72,{roughness:.4}),[(i-(pins-1)/2)*.55,.24,-.09]);
 if(id)host.add(new Port({id,label,connector,position,quaternion:portQuaternion(face),hitSize:[w,1,h],meta:{role:'visual-connector',face}}));
 return group;
}
export function grove(host,{position,face='bottom',id='grove',w=10,h=5,color=0xe8e9e4,depth=5.8}){
 const group=new THREE.Group();group.position.fromArray(position);group.quaternion.copy(FACE[face]);host.body.add(group);group.name='HY2.0-4P';
 const white=materials.plastic(color,{roughness:.58});
 for(const x of [-w/2+.45,w/2-.45])mesh(group,new THREE.BoxGeometry(.9,h,depth),white,[x,0,-depth/2]);
 for(const y of [-h/2+.4,h/2-.4])mesh(group,new THREE.BoxGeometry(w-1.4,.8,depth),white,[0,y,-depth/2]);
 mesh(group,new THREE.BoxGeometry(w-1.6,h-1.4,.6),white,[0,0,-depth+.3]);
 mesh(group,new THREE.PlaneGeometry(w-2,h-1.6),materials.cavity(0x202220),[0,0,-depth+.62]);
 for(let i=0;i<4;i++)mesh(group,new THREE.BoxGeometry(.42,.42,depth-1.3),materials.metal(0xbaad83,{roughness:.42}),[(i-1.5)*2,-.15,-depth/2]);
 for(const x of [-w/2+1,w/2-1])mesh(group,new THREE.BoxGeometry(.8,1.1,1.4),white,[x,h/2-.6,-.4]);
 host.add(new Port({id,label:'HY2.0-4P',connector:'grove',position,quaternion:portQuaternion(face),hitSize:[w,1,h],meta:{role:'visual-connector',face}}));return group;
}
export function header(parent,{position,face='back',cols=5,rows=2,pitch=2.54}){
 const group=new THREE.Group();group.position.fromArray(position);group.quaternion.copy(FACE[face]);parent.add(group);
 group.name='Female expansion header';group.userData.visualFamily='female-header';group.userData.layout={cols,rows,pitch};
 const black=materials.plastic(0x161819,{roughness:.76}),inside=materials.plastic(0x101312,{roughness:.85}),contact=materials.metal(0xb4ab8b,{roughness:.46});
 const opening=pitch*.66,throat=pitch*.4,holes=[];
 for(let c=0;c<cols;c++)for(let r=0;r<rows;r++)holes.push({w:opening,h:opening,r:.04,cx:(c-(cols-1)/2)*pitch,cy:(r-(rows-1)/2)*pitch});
 // Keep the existing outer face at +0.2 mm. The socket extends into the assembly;
 // each pin has a real entrance, tapered lead-in, bore and recessed spring contacts.
 const housing=slab(group,cols*pitch+.5,rows*pitch+.5,1.95,.5,[0,0,-1.75],black,holes,.045);housing.name='Header molded housing';
 const funnel=[];const a=opening/2,b=throat/2,outer=[[-a,-a],[a,-a],[a,a],[-a,a]],inner=[[-b,-b],[b,-b],[b,b],[-b,b]];
 for(let i=0;i<4;i++){const j=(i+1)%4,p=[...outer[i],.2],q=[...outer[j],.2],r=[...inner[j],-.35],s=[...inner[i],-.35];funnel.push(...p,...q,...r,...p,...r,...s);}
 const funnelGeometry=new THREE.BufferGeometry();funnelGeometry.setAttribute('position',new THREE.Float32BufferAttribute(funnel,3));funnelGeometry.computeVertexNormals();
 const boreShape=new THREE.Shape();boreShape.moveTo(-a,-a);boreShape.lineTo(a,-a);boreShape.lineTo(a,a);boreShape.lineTo(-a,a);boreShape.closePath();
 const boreHole=new THREE.Path();boreHole.moveTo(-b,-b);boreHole.lineTo(-b,b);boreHole.lineTo(b,b);boreHole.lineTo(b,-b);boreHole.closePath();boreShape.holes.push(boreHole);
 const boreGeometry=new THREE.ExtrudeGeometry(boreShape,{depth:1.25,bevelEnabled:false});
 for(const hole of holes){const {cx:x,cy:y}=hole;
  mesh(group,funnelGeometry,black,[x,y,0],'Header entrance chamfer');
  mesh(group,boreGeometry,inside,[x,y,-1.6],'Header socket bore');
  mesh(group,new THREE.BoxGeometry(throat,throat,.1),inside,[x,y,-1.65],'Header socket floor');
  for(const sign of [-1,1])mesh(group,new THREE.BoxGeometry(throat*.12,throat*.7,.64),contact,[x+sign*throat*.34,y,-1.08],'Header spring contact');
 }
 return group;
}
export function hitButton(host,{id,label,position,w,h,face='front',meta={}}){const target=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));target.name='hit-only';const b=new Button({id,label,mesh:target,position,quaternion:FACE[face],travel:.15,meta:{...meta,role:'visual-hit-target'}});host.add(b);return b;}
export function screw(parent,position,face='back',radius=1.2){const g=new THREE.Group();g.position.fromArray(position);g.quaternion.copy(FACE[face]);parent.add(g);disc(g,radius,[0,0,0],materials.metal(0xa3a8aa,{roughness:.4}));mesh(g,new THREE.CircleGeometry(radius*.4,6),materials.cavity(),[0,0,.02]);return g;}
