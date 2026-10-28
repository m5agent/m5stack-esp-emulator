import {Port} from '../../core/index.js';
import {THREE,mesh,slab,FACE,portQuaternion,materials,roundedRect,solid,hole,annulus,outline,corner} from './geometry.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function enclosure(host){
 const plastic=materials.plastic(0xe9ece6,{roughness:.79}),parts=[],bores=[];
 const layer=(name,z,d,{notch=false,relief=0,rear=false}={})=>{const s=outline({notch,relief});if(!relief)for(const[x,y]of spec.mountingHolesMm)hole(s,x,y,2.5);if(rear)hole(s,0,0,1.75);const o=solid(host.body,s,d,[0,0,z],plastic,'Mini IMU-Pro own '+name);parts.push(o);return o;};
 const frontShelf=layer('front depressed mounting shelves',2.8,.5,{notch:true}),front=layer('front closed skin and real Grove cutout',3.3,.7,{notch:true,relief:3.2}),rearShelf=layer('rear depressed mounting shelves',-3.3,.5,{rear:true}),rear=layer('rear closed skin and real screw bore',-4,.7,{relief:3.2,rear:true});
 for(const[x,y]of spec.mountingHolesMm)bores.push(mesh(host.body,annulus(3.4,2.5,5.6),plastic,[x,y,-2.8],'Mini IMU-Pro actual full through-bore cylindrical wall'));
 const walls=[],box=(w,h,d,x,y,z,name)=>{const o=mesh(host.body,new THREE.BoxGeometry(w,h,d),plastic,[x,y,z],name);walls.push(o);return o;};
 for(const[z,d,back]of[[-1.2,4,false],[-2.8,1.6,true]]){
  for(const sign of[-1,1])box(1.2,16,d,sign*11.4,0,z+d/2,'Mini IMU-Pro actual side enclosure wall');
  for(const[cx,cy,a,b]of[[8,-8,-Math.PI/2,0],[8,8,0,Math.PI/2],[-8,8,Math.PI/2,Math.PI],[-8,-8,Math.PI,Math.PI*1.5]])walls.push(corner(host.body,cx,cy,a,b,z,d,plastic,'Mini IMU-Pro own R4 curved enclosure wall'));
  if(back){box(16,1.2,d,0,11.4,z+d/2,'Mini IMU-Pro rear upper wall below service opening');box(16,1.2,d,0,-11.4,z+d/2,'Mini IMU-Pro rear lower wall behind Grove floor');}
  else{for(const sign of[-1,1]){box(4.3,1.2,d,sign*5.85,11.4,z+d/2,'Mini IMU-Pro actual service opening side wall');box(2.9,1.2,d,sign*6.55,-11.4,z+d/2,'Mini IMU-Pro real Grove opening side wall');}box(7.4,1.2,1.15,0,11.4,2.225,'Mini IMU-Pro actual service opening upper bridge');}
 }
 const boss=mesh(host.body,annulus(1.75,.82,6.1),plastic,[0,0,-2.8],'Mini IMU-Pro inferred blind front fixing boss with actual screw passage');
 const snapSeats=[];for(const sign of[-1,1])snapSeats.push(mesh(host.body,new THREE.BoxGeometry(.45,2.3,.65),plastic,[sign*10.58,-4.7,-.85],'Mini IMU-Pro inferred retained side snap seat'));
 const relief=[],logo=materials.plastic(0xe1e5dd,{roughness:.86}),stroke=(points)=>{for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i],dx=b[0]-a[0],dy=b[1]-a[1],o=mesh(host.body,new THREE.BoxGeometry(Math.hypot(dx,dy)+.1,.32,.025),logo,[-(a[0]+b[0])/2,(a[1]+b[1])/2,-4.0125],'Mini IMU-Pro own shallow fixed M5 molded relief');o.rotation.z=Math.atan2(dy,-dx);relief.push(o);}};
 stroke([[-4.2,-9.8],[-4.2,-4.7],[-1.9,-7],[.4,-4.7],[.4,-9.8]]);stroke([[4.6,-4.7],[1.3,-4.7],[1.3,-7],[3.5,-7],[4.4,-7.5],[4.6,-8.5],[4.1,-9.4],[3.2,-9.8],[1.3,-9.8]]);
 return{front,frontShelf,rear,rearShelf,bores,walls,boss,snapSeats,parts,relief};
}
function board(host){
 const s=outline({edge:10.35,radius:2.35,notch:true,notchTop:-6.3,relief:3.65});hole(s,0,0,1.9);for(const[x,y]of spec.pcb.groveBoresMm)hole(s,x,y,.46);
 const green=materials.plastic(0x236c42,{roughness:.9}),metal=materials.metal(0xb7ae8d,{roughness:.43}),dark=materials.plastic(0x202723),ceramic=materials.plastic(0xb8a27a),pcb=solid(host.body,s,.8,[0,0,-2],green,'Mini IMU-Pro own inferred green PCB with real mount reliefs,fixing/Grove bores'),barrels=[],lands=[];
 for(const[x,y]of spec.pcb.groveBoresMm){barrels.push(mesh(host.body,annulus(.46,.33,.8),metal,[x,y,-2],'Mini IMU-Pro actual Grove plated PCB barrel'));for(const z of[-2.04,-1.2])lands.push(mesh(host.body,annulus(.68,.33,.04),metal,[x,y,z],'Mini IMU-Pro actual Grove annular solder land'));}
 const sensors={},terminals=[];
 for(const[name,cfg]of Object.entries(spec.packages)){
  const[w,h,d]=cfg.sizeMm,[x,y,z]=cfg.position;
  if(name==='bmm150'){
   sensors[name]=slab(host.body,w,h,.46,.035,[x,y,z+.14],dark,[],.005);sensors[name].name='Mini IMU-Pro actual BMM150 WLCSP12 body;inferred installed position';
   for(const[bx,by]of[[-.4,-.4],[.4,-.4],[-.2,-.2],[.2,-.2],[-.4,0],[.4,0],[-.2,.2],[.2,.2],[-.4,.4],[.4,.4],[0,-.4],[0,.4]])terminals.push(mesh(host.body,new THREE.SphereGeometry(.105,16,12).scale(1,1,.07/.105),metal,[x+bx,y+by,z+.07],'Mini IMU-Pro actual BMM150 retained solder ball'));
  }else{
   sensors[name]=slab(host.body,w,h,d-.08,.045,[x,y,z+.08],name==='bmp280'?materials.metal(0xa6afa8,{roughness:.42}):dark,[],.005);sensors[name].name='Mini IMU-Pro actual '+name.toUpperCase()+' package;inferred installed position';
   const per=name==='bmi270'?4:2;for(const sign of[-1,1]){for(let i=0;i<per;i++)terminals.push(mesh(host.body,new THREE.BoxGeometry(.36,.3,.08),metal,[x+sign*(w/2-.12),y+(i-(per-1)/2)*.5,z+.04],'Mini IMU-Pro actual '+name+' fixed LGA land'));const horiz=name==='bmi270'?3:2;for(let i=0;i<horiz;i++)terminals.push(mesh(host.body,new THREE.BoxGeometry(.3,.36,.08),metal,[x+(i-(horiz-1)/2)*.5,y+sign*(h/2-.12),z+.04],'Mini IMU-Pro actual '+name+' fixed LGA end land'));}
  }
 }
 const ldo=slab(host.body,1.3,2.8,.75,.05,[3.7,-3.9,-1.15],dark,[],.005);ldo.name='Mini IMU-Pro own schematic HX6306P332MR inferred fixed envelope';for(const[dx,dy]of[[-.68,-.8],[-.68,.8],[.68,0]])terminals.push(mesh(host.body,new THREE.BoxGeometry(.45,.35,.1),metal,[3.7+dx,-3.9+dy,-1.15],'Mini IMU-Pro retained regulator termination'));
 const passives=[],passiveEnds=[];for(const[n,x,y]of[['R1',-4.8,3.2],['R2',4.9,3.2],['R3',0,8.8],['C1',-7,-6.8],['C2',7,-6.8],['C3',7,-8.5],['C4',-5.4,-3.3],['C5',3.6,8.7],['C6',5.4,5.9],['C7',-1.8,-3.9],['C8',-5.4,5.9]]){const q=slab(host.body,.9,.55,.4,.03,[x,y,-1.15],n[0]==='R'?dark:ceramic,[],.005);q.name='Mini IMU-Pro own schematic '+n+' inferred fixed envelope';passives.push(q);for(const sign of[-1,1])passiveEnds.push(mesh(host.body,new THREE.BoxGeometry(.15,.55,.08),metal,[x+sign*.39,y,-1.16],'Mini IMU-Pro actual passive fixed termination'));}
 const serviceLands=[];for(const x of[-2.6,2.6])serviceLands.push(mesh(host.body,new THREE.BoxGeometry(.5,.85,.12),metal,[x,9.3,-1.14],'Mini IMU-Pro own visible fixed top-opening metal land;not a located switch'));
 return{pcb,barrels,lands,sensors,terminals,ldo,passives,passiveEnds,serviceLands};
}
function grove(host){
 const frame=new THREE.Group();frame.name='Mini IMU-Pro own red HY2.0 four-contact receiving socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);
 const red=materials.plastic(spec.grove.color,{roughness:.64}),metal=materials.metal(0xb8b69a,{roughness:.42}),box=(s,p,n,m=red)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Mini IMU-Pro Grove '+n),walls=[],guides=[],contacts=[],returns=[],tails=[];
 for(const sign of[-1,1]){walls.push(box([.65,5.2,6.3],[sign*4.675,0,-3.15],'actual full receiving side wall'));guides.push(box([1.1,.65,5.8],[sign*4.1,2.275,-3.4],'actual top retaining rail'));guides.push(box([.65,.5,1.2],[sign*3.8,2.35,-1.7],'actual locking shoulder'));}
 const floor=box([8.7,.65,6.3],[0,-2.275,-3.15],'actual receiving floor'),back=box([8.7,4.55,.65],[0,.325,-5.975],'actual deep dielectric backing'),bridge=box([4.8,.45,2.1],[0,2.375,-4.45],'actual rear retaining bridge');
 for(let i=0;i<4;i++){const x=(i-1.5)*2;contacts.push(box([.42,.42,4.9],[x,-.15,-3.4],'actual recessed contact '+(i+1),metal));returns.push(box([.42,2.65,.42],[x,-1.265,-6.2],'actual retained vertical return '+(i+1),metal));tails.push(box([.42,.9,.42],[x,-3.05,-6.2],'actual through-PCB solder tail '+(i+1),metal));}
 const port=host.add(new Port({id:'grove',label:'PORT.A · documentary GND/5V/SDA/SCL',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'bottom',physicalFamily:'HY2.0-4P receiving socket',scope:'Four physical contacts and cable pose only;no I2C,power,address,sensor,electrical or firmware behavior.'}}));return{frame,walls,guides,floor,back,bridge,contacts,returns,tails,port};
}
function fixing(host){const s=new THREE.Shape();s.absarc(0,0,1.65,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3;i?h.lineTo(Math.cos(a)*.68,Math.sin(a)*.68):h.moveTo(Math.cos(a)*.68,Math.sin(a)*.68);}h.closePath();s.holes.push(h);const metal=materials.metal(0xb6bcb6,{roughness:.36}),head=solid(host.body,s,.5,[0,0,-4.01],metal,'Mini IMU-Pro actual rear hex-socket fixing head'),floor=mesh(host.body,new THREE.CylinderGeometry(.69,.69,.1,6).rotateX(Math.PI/2),metal,[0,0,-3.46],'Mini IMU-Pro recessed real hex-socket floor'),shaft=mesh(host.body,new THREE.CylinderGeometry(.72,.72,6.2,32).rotateX(Math.PI/2),metal,[0,0,-.45],'Mini IMU-Pro actual retained fixing shaft');return{head,floor,shaft};}
function films(host){const white=materials.plastic(0xf2f3ed,{roughness:.8}),f=spec.labels,front=slab(host.body,...f.front.size,.04,.9,[0,7.2,4],white,[],0),back=slab(host.body,...f.back.size,.04,.025,[0,7.1,-4.04],white,[],0),s=new THREE.Shape();s.absarc(0,0,3,0,tau,false);const axis=solid(host.body,s,.04,[0,.8,4],white,'Mini IMU-Pro actual circular XYZ adhesive film');for(const[face,o]of Object.entries({front,axis,back})){o.name='Mini IMU-Pro own independent physical '+face+' adhesive film';o.userData={role:'physical-label-substrate',face,inferredThicknessMm:.04};}return{front,axis,back};}
export function buildMiniIMUPro(host){const shell=enclosure(host),electronics=board(host),input=grove(host),screw=fixing(host),labels=films(host);host.miniIMUProAssembly={shell,board:electronics,input,fixing:screw,films:labels};host.unitStickers=addStickers(host);}
