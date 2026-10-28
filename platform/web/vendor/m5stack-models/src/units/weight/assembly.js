import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
const circularHole=(s,x,y,r)=>{const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);};
function board(host){
 const e=9,r=3.8,y=-4,a=Math.acos((e-8)/r),dy=Math.sqrt(r*r-(e-8)**2),s=new THREE.Shape(),corner=3.2,halfLength=14;
 s.moveTo(-e+corner,halfLength);s.lineTo(e-corner,halfLength);s.absarc(e-corner,halfLength-corner,corner,Math.PI/2,0,true);s.lineTo(e,y+dy);s.absarc(8,y,r,a,tau-a,false);s.lineTo(e,-halfLength+corner);s.absarc(e-corner,-halfLength+corner,corner,0,-Math.PI/2,true);s.lineTo(-e+corner,-halfLength);s.absarc(-e+corner,-halfLength+corner,corner,-Math.PI/2,-Math.PI,true);s.lineTo(-e,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-e,halfLength-corner);s.absarc(-e+corner,halfLength-corner,corner,Math.PI,Math.PI/2,true);s.closePath();circularHole(s,0,-4,3);
 const top=spec.pcb.topZ,pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:32}),materials.plastic(0x315e46,{roughness:.9}),[0,0,top-.8],'Weight inferred own U030 PCB with actual mount reliefs and fixing bore'),black=materials.plastic(0x252a28,{roughness:.8}),metal=materials.metal(0xb9b7a2,{roughness:.49}),ceramic=materials.plastic(0xb1a581,{roughness:.8}),parts=[];
 const chip=slab(host.body,9.9,3.9,1.35,.2,[0,2,top],black,[],.045);chip.name='Weight U1 HX711 sole ADC physical SOIC16 package';parts.push(chip);
 const icLeads=[];for(let i=0;i<8;i++)for(const side of[-1,1]){const x=(i-3.5)*1.27;icLeads.push(mesh(host.body,new THREE.BoxGeometry(.43,.8,.14),metal,[x,2+side*2.5,top+.07],'Weight HX711 actual gull-wing foot'));icLeads.push(mesh(host.body,new THREE.BoxGeometry(.43,.14,.58),metal,[x,2+side*2.17,top+.36],'Weight HX711 actual gull-wing bend'));icLeads.push(mesh(host.body,new THREE.BoxGeometry(.43,.55,.14),metal,[x,2+side*1.95,top+.65],'Weight HX711 package lead'));}
 const transistor=slab(host.body,2.9,1.35,.8,.15,[-7.3,2.2,top],black,[],.025);transistor.name='Weight Q1 SS8550 Y2 SOT23 regulator transistor';parts.push(transistor);for(const[x,y]of[[-8.25,1.3],[-6.35,1.3],[-7.3,3.1]])parts.push(mesh(host.body,new THREE.BoxGeometry(.45,.7,.15),metal,[x,y,top+.075],'Weight SS8550 physical lead'));
 const passives=[];for(const[type,positions]of[['R',[[7.3,.3],[7.3,1.4],[7.3,2.5],[7.3,3.6],[7.3,4.7]]],['C',[[-7.3,.4],[-7.3,4.1],[-7.3,5.2],[0,5.6],[-4,5.6]]]])for(const[i,[x,y]]of positions.entries()){const part=slab(host.body,1.55,.85,.5,.07,[x,y,top],type==='R'?black:ceramic,[],.015);part.name=`Weight schematic ${type}${i+1} physical passive,position inferred`;passives.push(part);for(const side of[-1,1])passives.push(mesh(host.body,new THREE.BoxGeometry(.28,.89,.52),metal,[x+side*.64,y,top+.26],`Weight ${type}${i+1} metal termination`));}
 const pads=[];for(let i=0;i<4;i++)pads.push(mesh(host.body,new THREE.BoxGeometry(.95,.95,.04),metal,[(i-1.5)*2,-10.7,top+.02],'Weight Grove real solder pad '+(i+1)));for(const x of spec.terminal.pinX)pads.push(mesh(host.body,new THREE.BoxGeometry(1.05,1.05,.04),metal,[x,5.5,top+.02],'Weight terminal real PCB solder pad'));
 return{pcb,chip,icLeads,transistor,passives,parts,pads};
}
function grove(host){
 const frame=new THREE.Group();frame.name='Weight actual black HY2.0-4P open-top board socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(portQuaternion('bottom'));host.body.add(frame);const plastic=materials.plastic(0x20241f,{roughness:.7}),metal=materials.metal(0xbab49a,{roughness:.43}),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Weight Grove '+n),rails=[];
 for(const sign of[-1,1]){rails.push(box([.65,5.8,5.2],[sign*4.675,-2.8,0],'full side wall'));rails.push(box([1.1,5.8,.65],[sign*4.1,-2.8,2.275],'front retaining rail'));box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');}
 const floor=box([8.7,5.8,.65],[0,-2.8,-2.275],'actual socket floor'),rear=box([8.7,.65,4.55],[0,-5.375,-.325],'recessed dielectric rear'),bridge=box([3.6,1,.45],[0,-2.3,2.375],'short real locking bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){const x=(i-1.5)*2;contacts.push(box([.42,4.2,.42],[x,-2.8,.05],'recessed metal contact '+(i+1),metal));tails.push(box([.42,.42,2.56],[x,-5.2,-1.4],'actual board termination '+(i+1),metal));}
 const port=host.add(new Port({id:'grove',label:'HY2.0-4P · DAT/CLK/5V/GND',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,.05],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',protocol:'HX711 DOUT/PD_SCK documentary labels only',scope:'Four physical contacts and cable pose. No I2C,ADC data,voltage,current,firmware or load-cell behavior.'}}));
 return{frame,rails,floor,rear,bridge,contacts,tails,port};
}
function terminal(host){
 const frame=new THREE.Group();frame.name='Weight actual U030 fixed four-pole orange receiving terminal';host.body.add(frame);const orange=materials.plastic(0xf59045,{roughness:.7}),metal=materials.metal(0xb9b8a7,{roughness:.45});
 const floor=slab(frame,15.8,9.8,.55,.2,[0,11.1,-1.2],orange,[],.035);floor.name='Weight terminal real fixed floor';const walls=[];
 for(const x of[-7.55,7.55]){const o=slab(frame,.7,9.8,6.15,.12,[x,11.1,-.65],orange,[],.025);o.name='Weight terminal fixed side wall';walls.push(o);}
 const rear=slab(frame,14.4,.7,6.15,.12,[0,6.55,-.65],orange,[],.025);rear.name='Weight terminal recessed rear dielectric wall';
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.25,r:.12,cx,cy:7.6-11.1})),roof=slab(frame,15.8,9.8,.64,.2,[0,11.1,5.5],orange,windows,0);roof.name='Weight fixed terminal actual roof with four through inspection windows';
 const ribs=[];for(const x of[-3.96,0,3.96]){const o=slab(frame,.38,8.1,.4,.07,[x,11.7,-.65],orange,[],.025);o.name='Weight terminal low channel separator';ribs.push(o);}
 const contacts=[],tails=[];for(const x of spec.terminal.pinX){contacts.push(mesh(frame,new THREE.BoxGeometry(.64,8.4,.64),metal,[x,11.1,1.3],'Weight terminal actual 3.96mm pitch male pin'));mesh(frame,new THREE.BoxGeometry(.64,1.75,.64),metal,[x,6.025,1.3],'Weight terminal contact bent return');tails.push(mesh(frame,new THREE.BoxGeometry(.64,.64,2.6),metal,[x,5.5,0],'Weight terminal actual board termination'));}
 for(const x of[-7,7]){const ear=slab(frame,.7,1,.12,.08,[x,15.4,6.02],orange,[],.015);ear.name='Weight fixed terminal real retention ear';}
 const port=host.add(new Port({id:'terminal',label:'HT3.96-4P · A+/A−/E−/E+',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,6.8],pins:spec.terminal.names.map((name,i)=>({n:spec.terminal.pinNumbers[i],name})),pinGrid:{cols:4,rows:1,pitch:3.96,center:[0,0],order:col=>col+1},meta:{role:'visual-connector',face:'top',scope:'Passive physical socket and removable plug only. No load cell,excitation,ADC,calibration,electrical or firmware behavior.'}}));return{frame,floor,walls,rear,roof,ribs,contacts,tails,port};
}
function fixing(host){
 const metal=materials.metal(0xb6b9b2,{roughness:.4}),s=new THREE.Shape();s.absarc(0,0,1.55,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=i*tau/6;i?h.lineTo(Math.cos(a)*.67,Math.sin(a)*.67):h.moveTo(Math.cos(a)*.67,Math.sin(a)*.67);}h.closePath();s.holes.push(h);
 const head=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.48,bevelEnabled:false,curveSegments:32}),metal,[0,-4,-3.98],'Weight real single rear hex-socket fixing screw'),floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),metal,[0,-4,-3.45],'Weight fixing screw recessed hex floor'),shank=mesh(host.body,new THREE.CylinderGeometry(.72,.72,6.9,32).rotateX(Math.PI/2),metal,[0,-4,-.03],'Weight retained actual centre fixing shaft');return{head,floor,shank};
}
export function buildWeight(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe6e8df,{roughness:.8})}),pcb=board(host),socket=grove(host),fixedTerminal=terminal(host),screw=fixing(host),silver=materials.metal(0xc4c7bd,{roughness:.61});
 const front=slab(host.body,...spec.labels.front.size,spec.labels.front.filmThicknessMm,.05,spec.labels.front.position,silver,[],0);front.name='Weight actual independent four-colour front terminal label silver film';front.userData={role:'physical-label-substrate',face:'front'};
 const back=slab(host.body,...spec.labels.back.size,spec.labels.back.filmThicknessMm,.07,spec.labels.back.position,silver,[],0);back.name='Weight actual independent rear silver WEIGHT adhesive film';back.userData={role:'physical-label-substrate',face:'back'};
 host.weightAssembly={parts,board:pcb,socket,terminal:fixedTerminal,screw,films:{front,back}};host.unitStickers=addStickers(host);
}
