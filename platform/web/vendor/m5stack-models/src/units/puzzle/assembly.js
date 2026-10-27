import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion,FACE} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {PixelLed,Matrix} from './Matrix.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
function circuit(host){
 const s=roundedRect(23.8,23.8,.55);const h=new THREE.Path();h.absarc(0,0,1.05,0,Math.PI*2,false);s.holes.push(h);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:48}),materials.plastic(0x252a25,{roughness:.9}),[0,0,4.55],'Puzzle real PCB,with central M2 drilling');
 const metal=materials.metal(0xb5afa0,{roughness:.48}),passives=[];
 for(const[x,y,w,h]of[[-3.6,7.8,1,.6],[3.6,7.8,1,.6],[-3.6,-7.8,1,.6],[3.6,-7.8,1.6,.9]]){const c=slab(host.body,w,h,.5,.04,[x,y,4.05],materials.plastic(0xbbae8c,{roughness:.88}),[],.015);c.name='Puzzle concealed populated LED supply decoupling capacitor';passives.push(c);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.2,h+.06,.12),metal,[x+sign*w/2,y,4.12],'Puzzle capacitor solder end');}
 const fixing=mesh(host.body,new THREE.CylinderGeometry(.78,.78,3,32).rotateX(Math.PI/2),metal,[0,0,3.15],'Puzzle M2 central fastening shank');return{pcb,passives,fixing};
}
function matingQuaternion(face){return portQuaternion(face).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),Math.PI));}
function socket(host,id,position,face){
 const g=new THREE.Group();g.name=`Puzzle ${id==='grove'?'J2 input':'J1 output'} real HY2.0-4P socket`;g.position.fromArray(position);g.quaternion.copy(matingQuaternion(face));host.body.add(g);
 const plastic=materials.plastic(0xe3e5de,{roughness:.72}),metal=materials.metal(0xbdb8a0,{roughness:.44}),box=(s,p,n,m=plastic)=>mesh(g,new THREE.BoxGeometry(...s),m,p,`Puzzle ${id} ${n}`),depth=6.3;
 for(const sign of[-1,1]){box([.65,depth,4.9],[sign*4.675,-depth/2,0],'side wall');box([.7,3.2,.6],[sign*3.85,-4.7,2.15],'guide rail');box([.6,1.2,.45],[sign*3.65,-1.8,2.225],'latch shoulder');}
 box([8.7,depth,.65],[0,-depth/2,-2.125],'floor');box([8.7,.65,4.25],[0,-depth+.325,.325],'rear wall');box([4.8,2.3,.45],[0,-4.5,2.225],'locking bridge');
 const contacts=[];for(let i=0;i<4;i++){const c=box([.42,4.5,.42],[(i-1.5)*2,-3.6,-.2],`real contact ${i+1}`,metal);c.userData.pin=i+1;contacts.push(c);box([.42,.42,7.1],[(i-1.5)*2,-5.8,-3.85],`installed solder lead ${i+1}`,metal);}
 const pins=[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:id==='grove'?'SIG_IN':'SIG_OUT',color:'yellow'},{n:4,name:'IO2',color:'white'}];
 const port=host.add(new Port({id,label:id==='grove'?'J2 · Grove input':'J1 · Grove output',connector:'grove',position,quaternion:matingQuaternion(face),hitSize:[10,1,4.9],pins,pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.2],order:col=>col+1},meta:{role:'visual-connector',face,physicalRole:id==='grove'?'input':'output',matingFrame:'+Y outward,+Z toward Unit rear;actual rear-open socket and printed pin-row handedness',scope:'Physical four-contact attachment/ownership/cable geometry only;no voltage,IO signal propagation,WS2812 data,address mapping,pixel copying or electrical behavior'}}));return{group:g,contacts,port};
}
function pixels(host){
 const pixels=[],packages=[],contacts=[];const metal=materials.metal(0xb6ae8c,{roughness:.48});
 for(let row=0;row<8;row++)for(let col=0;col<8;col++){
  const i=row*8+col,x=(col-3.5)*2.8,y=(3.5-row)*2.8;
  const base=mesh(host.body,new THREE.BoxGeometry(1.3,1.3,.55),materials.plastic(0xebe8d8,{roughness:.6}),[x,y,5.625]);base.name=`Puzzle pixel-${i} physical WS2812E-1313 package`;packages.push(base);
  for(const dx of[-.48,.48])for(const dy of[-.48,.48])contacts.push(mesh(host.body,new THREE.BoxGeometry(.25,.25,.08),metal,[x+dx,y+dy,5.34],`Puzzle pixel-${i} package terminal`));
  const lens=new THREE.Mesh(new THREE.BoxGeometry(.98,.98,.24),materials.plastic(0xe3dfce,{roughness:.45}));lens.name=`Puzzle pixel-${i} real encapsulated RGB emissive surface`;
  const led=host.add(new PixelLed({id:`pixel-${i}`,label:`Pixel row ${row+1},column ${col+1}`,position:[x,y,6.02],mesh:lens,radius:.1,glowSize:0,color:0xffffff,meta:{role:'externally-driven-visual',row,column:col,layoutIndex:i,package:'WS2812E-1313',order:'row-major-top-left',scope:'Physical position only,not schematic D number or automatic WS2812 address. External color/on/brightness only,default off;no animation,power,current or downstream propagation'}}));pixels.push(led);
 }
 const diffuser=slab(host.body,23.92,23.92,.16,.35,[0,0,7.32],materials.plastic(0xf6f6ee,{roughness:.4,transparent:true,opacity:.35,depthWrite:false}),[],.01);diffuser.name='Puzzle physical translucent front diffuser covering original 64-cell grid';
 const matrix=host.add(new Matrix(pixels));return{pixels,packages,contacts,diffuser,matrix};
}
export function buildPuzzle(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e4,{roughness:.78}),grid:materials.plastic(0xe8e9e2,{roughness:.73})});
 const board=circuit(host),input=socket(host,'grove',spec.grove.position,'bottom'),output=socket(host,'out',spec.out.position,'top'),display=pixels(host);
 host.puzzleAssembly={parts,board,input,output,display};host.unitStickers=addStickers(host);
}
