import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,tau,false);shape.holes.push(p);}
function annulus(outer,inner,depth){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);hole(s,0,0,inner);return new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:32});}
function prototypeBoard(host){
 const f=spec.prototypeField,shape=new THREE.Shape(),edge=10.6,r=3.4,cy=-12,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2);
 shape.moveTo(-edge,22.2);shape.lineTo(edge,22.2);shape.lineTo(edge,cy+dy);shape.absarc(8,cy,r,a,tau-a,false);shape.lineTo(edge,-22.5);shape.lineTo(5.5,-22.5);shape.lineTo(5.5,-20.2);shape.lineTo(-5.5,-20.2);shape.lineTo(-5.5,-22.5);shape.lineTo(-edge,-22.5);shape.lineTo(-edge,cy-dy);shape.absarc(-8,cy,r,Math.PI+a,Math.PI-a,false);shape.lineTo(-edge,22.2);shape.closePath();hole(shape,0,-12,1.15);
 const holeCenters=[];for(let row=0;row<f.rows;row++)for(let col=0;col<f.columns;col++){const x=(col-(f.columns-1)/2)*f.pitchMm,y=f.center[1]+(row-(f.rows-1)/2)*f.pitchMm;holeCenters.push([x,y]);hole(shape,x,y,f.substrateBoreDiameterMm/2);}
 const bottom=f.pcbTopZ-f.pcbThicknessMm,boardMaterial=materials.plastic(0xc5a51d,{roughness:.85}),metal=materials.metal(0xbdb18a,{roughness:.48}),pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:f.pcbThicknessMm,bevelEnabled:false,curveSegments:32}),boardMaterial,[0,0,bottom],'Proto true1mm thick yellow prototype substrate with77 actual bores,real mount reliefs and fixing bore');pcb.userData={role:'physical-perfboard',holes:77,pitchMm:2.54,inferredThickness:true};
 const ringGeometry=annulus(f.padDiameterMm/2,f.freeHoleDiameterMm/2,f.padThicknessMm),barrelGeometry=annulus(f.substrateBoreDiameterMm/2,f.freeHoleDiameterMm/2,f.pcbThicknessMm),topRings=[],bottomRings=[],barrels=[];
 for(const[i,[x,y]]of holeCenters.entries()){barrels.push(mesh(host.body,barrelGeometry,metal,[x,y,bottom],'Proto plated through-hole barrel '+(i+1)));topRings.push(mesh(host.body,ringGeometry,metal,[x,y,f.pcbTopZ],'Proto front metal annulus '+(i+1)));bottomRings.push(mesh(host.body,ringGeometry,metal,[x,y,bottom-f.padThicknessMm],'Proto rear metal annulus '+(i+1)));}
 const grovePads=[];for(let i=0;i<4;i++)grovePads.push(mesh(host.body,new THREE.BoxGeometry(.85,.85,.025),metal,[(i-1.5)*2,-18.8,f.pcbTopZ+.0125],'Proto actual Grove fixed PCB solder pad '+(i+1)));
 return {pcb,holeCenters,barrels,topRings,bottomRings,grovePads};
}
function groveSocket(host){
 const frame=new THREE.Group();frame.name='Proto actual black HY2.0-4P receiving board socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(portQuaternion('bottom'));host.body.add(frame);const plastic=materials.plastic(0x1b1f1a,{roughness:.7}),metal=materials.metal(0xbcb49a),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Proto Grove '+n),rails=[];
 for(const sign of[-1,1]){rails.push(box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'actual full side rail'));rails.push(box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'actual top retaining rail'));box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');}
 const floor=box([8.7,5.9,.65],[0,-2.85,-1.475],'physical socket floor'),rear=box([8.7,.65,3.75],[0,-5.475,.075],'actual recessed dielectric rear'),bridge=box([4.8,1,.45],[0,-2.5,2.375],'actual retaining bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){contacts.push(box([.42,4.1,.42],[(i-1.5)*2,-2.85,.05],'real recessed male contact '+(i+1),metal));tails.push(box([.42,.42,1.45],[(i-1.5)*2,-5.1,-1.125],'retained PCB terminal '+(i+1),metal));}
 const port=host.add(new Port({id:'grove',label:'Proto HY2.0-4P · documentary I/O/VCC/GND',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'bottom',scope:'Actual receiving board socket and four metal pins/cable pose only.Documentary labels do not assign VCC rating,signal direction orprotocol;no electrical routing oruser-added circuit behavior'}}));return{frame,rails,floor,rear,bridge,contacts,tails,port};
}
function fixing(host){
 const metal=materials.metal(0xaeb5af,{roughness:.4}),s=new THREE.Shape();s.absarc(0,0,1.55,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();s.holes.push(h);const head=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.5,bevelEnabled:false,curveSegments:32}),metal,[0,-12,-3.97],'Proto real single fixed rear hex-socket screw head'),floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),metal,[0,-12,-3.42],'Proto recessed physical screw hex floor'),shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,6.6,32).rotateX(Math.PI/2),metal,[0,-12,-.12],'Proto retained central fixing shaft');return{head,floor,shank};
}
export function buildProto(host){const rearCover=host.options.rearCover!==false,parts=addCadParts(host,data.filter(p=>rearCover||p.role==='front'),{shell:materials.plastic(0xe6e9e2,{roughness:.81})}),board=prototypeBoard(host),socket=groveSocket(host),screw=rearCover?fixing(host):null,film=rearCover?slab(host.body,...spec.labels.back.size,.04,.1,[0,7,-3.84],materials.metal(0xc5c8bf,{roughness:.62}),[],0):null;if(film){film.name='Proto independent real silver rear PROTO adhesive film';film.userData={role:'physical-label-substrate',face:'back'};}host.protoAssembly={parts,board,socket,screw,film,rearCover};host.unitStickers=addStickers(host);}
