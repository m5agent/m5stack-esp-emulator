import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(shape,x,y,r){const path=new THREE.Path();path.absarc(x,y,r,0,tau,false);shape.holes.push(path);}
function annulus(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32});}
function prototypeBoard(host){
 const f=spec.prototypeField,shape=new THREE.Shape(),edge=10.6,r=3.4,cy=-4,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2);
 shape.moveTo(-edge,14.2);shape.lineTo(edge,14.2);shape.lineTo(edge,cy+dy);shape.absarc(8,cy,r,a,tau-a,false);shape.lineTo(edge,-14.5);shape.lineTo(5.5,-14.5);shape.lineTo(5.5,-12.2);shape.lineTo(-5.5,-12.2);shape.lineTo(-5.5,-14.5);shape.lineTo(-edge,-14.5);shape.lineTo(-edge,cy-dy);shape.absarc(-8,cy,r,Math.PI+a,Math.PI-a,false);shape.lineTo(-edge,14.2);shape.closePath();hole(shape,0,-4,1.15);
 const holeCenters=[];
 for(let row=0;row<f.rows;row++)for(let col=0;col<f.columns;col++){
  const x=(col-(f.columns-1)/2)*f.pitchMm,y=f.center[1]+(row-(f.rows-1)/2)*f.pitchMm;
  holeCenters.push([x,y]);hole(shape,x,y,f.substrateBoreDiameterMm/2);
 }
 const bottom=f.pcbTopZ-f.pcbThicknessMm,boardMaterial=materials.plastic(0xc5a51d,{roughness:.85}),metal=materials.metal(0xbdb18a,{roughness:.48});
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:f.pcbThicknessMm,bevelEnabled:false,curveSegments:32}),boardMaterial,[0,0,bottom],'Mini Proto own yellow prototype substrate with48 actual bores,mount reliefs and true fixing bore');
 pcb.userData={role:'physical-perfboard',holes:48,pitchMm:2.54,inferredBoreAndInstallation:true};
 const ringGeometry=annulus(f.padDiameterMm/2,f.freeHoleDiameterMm/2,f.padThicknessMm),barrelGeometry=annulus(f.substrateBoreDiameterMm/2,f.freeHoleDiameterMm/2,f.pcbThicknessMm),topRings=[],bottomRings=[],barrels=[];
 for(const[i,[x,y]]of holeCenters.entries()){
  barrels.push(mesh(host.body,barrelGeometry,metal,[x,y,bottom],'Mini Proto plated through-hole barrel '+(i+1)));
  topRings.push(mesh(host.body,ringGeometry,metal,[x,y,f.pcbTopZ],'Mini Proto front metal annulus '+(i+1)));
  bottomRings.push(mesh(host.body,ringGeometry,metal,[x,y,bottom-f.padThicknessMm],'Mini Proto rear metal annulus '+(i+1)));
 }
 const grovePads=[];for(let i=0;i<4;i++)grovePads.push(mesh(host.body,new THREE.BoxGeometry(.85,.85,.025),metal,[(i-1.5)*2,-10.8,f.pcbTopZ+.0125],'Mini Proto actual Grove PCB solder pad '+(i+1)));
 return {pcb,holeCenters,barrels,topRings,bottomRings,grovePads};
}
function groveSocket(host){
 const frame=new THREE.Group();frame.name='Mini Proto actual black HY2.0-4P receiving board socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(portQuaternion('bottom'));host.body.add(frame);
 const plastic=materials.plastic(0x1b1f1a,{roughness:.7}),metal=materials.metal(0xbcb49a),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Mini Proto Grove '+n),rails=[];
 for(const sign of[-1,1]){
  rails.push(box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'actual full side rail'));
  rails.push(box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'actual top retaining rail'));
  box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');
 }
 const floor=box([8.7,5.9,.65],[0,-2.85,-1.475],'physical socket floor'),rear=box([8.7,.65,3.75],[0,-5.475,.075],'actual recessed dielectric rear'),bridge=box([4.8,1,.45],[0,-2.5,2.375],'actual retaining bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){
  contacts.push(box([.42,4.1,.42],[(i-1.5)*2,-2.85,.05],'real recessed male contact '+(i+1),metal));
  tails.push(box([.42,.42,1.45],[(i-1.5)*2,-5.1,-1.125],'retained PCB terminal '+(i+1),metal));
 }
 const port=host.add(new Port({id:'grove',label:'Mini Proto HY2.0-4P · documentary I/O/VCC/GND',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'bottom',scope:'Actual passive four-contact socket and cable pose only.Printed5V does not establish a new allowed VCC rating orsignal direction;no circuit routing,power orprotocol behavior.'}}));
 return {frame,rails,floor,rear,bridge,contacts,tails,port};
}
function fixing(host){
 const metal=materials.metal(0xaeb5af,{roughness:.4}),s=new THREE.Shape();s.absarc(0,0,1.55,0,tau,false);
 const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();s.holes.push(h);
 const head=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.5,bevelEnabled:false,curveSegments:32}),metal,[0,-4,-3.97],'Mini Proto real fixed rear hex-socket screw head');
 const floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),metal,[0,-4,-3.42],'Mini Proto recessed physical screw hex floor');
 const shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,6.3,32).rotateX(Math.PI/2),metal,[0,-4,-.27],'Mini Proto retained central fixing shaft');
 return {head,floor,shank};
}
export function buildMiniProto(host,{rearCover=true}={}){
 if(typeof rearCover!=='boolean')throw new TypeError('rearCover must be boolean');
 const parts=addCadParts(host,data.filter(p=>rearCover||p.role==='front'),{shell:materials.plastic(0xe6e9e2,{roughness:.81})}),board=prototypeBoard(host),socket=groveSocket(host),screw=rearCover?fixing(host):null;
 const label=spec.labels.back,film=rearCover?slab(host.body,...label.size,.04,.1,label.position,materials.plastic(0xd8dcd5,{roughness:.86}),[],0):null;
 if(film){film.name='Mini Proto real rear MINI PROTO adhesive substrate';film.userData={role:'physical-label-substrate',face:'back'};}
 host.miniProtoAssembly={parts,board,socket,screw,film,rearCover};host.unitStickers=addStickers(host);
}
