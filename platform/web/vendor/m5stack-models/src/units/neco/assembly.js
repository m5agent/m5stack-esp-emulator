import{Button,Led,Port}from'../../core/index.js';
import{THREE,materials,roundedRect,solid,ring,box,boardShape,socketQuaternion}from'./geometry.js';
import{spec,mountingCenters,pixels,capacitorPositions}from'./dimensions.js';
import{addStickers}from'./stickers.js';
class PackageLed extends Led{set(state){super.set(state);this.glow.visible=false;}}
function circuit(host){
 const black=materials.plastic(0x222321,{roughness:.88}),tin=materials.metal(0xb6b9ad,{roughness:.48}),gold=materials.metal(0xb48b24,{roughness:.4});
 const pcb=solid(host.body,boardShape(),1,[0,0,-.5],black,'Neco own dimensioned 1mm curved cat-ear PCB with four true bores');
 pcb.userData={role:'physical-pcb',source:'Own U163 orthographic outline/photo reconstruction; no borrowed model or STEP faces'};
 const pads=[],barrels=[],eyelets=[],capacitors=[],terminals=[];
 for(const[i,[x,y]]of mountingCenters.entries()){
  if(i<2){barrels.push(ring(host.body,1.1,1.05,1,[x,y,-.5],tin,'Neco outer true plated mounting bore'));for(const z of[-.525,.5])pads.push(ring(host.body,1.58,1.05,.025,[x,y,z],tin,'Neco outer mounting annular metal land'));}
  else{
   eyelets.push(ring(host.body,1.28,.85,1,[x,y,-.5],gold,'Neco actual through-board metal fixing eye barrel'));
   eyelets.push(ring(host.body,1.6,.85,.13,[x,y,.5],tin,'Neco actual front fixing-eye flange'));
   eyelets.push(ring(host.body,2,.85,1.5,[x,y,-2],gold,'Neco actual rear gold fixing collar with open bore'));
  }
 }
 for(const[i,p]of capacitorPositions.entries()){
  const frame=new THREE.Group();frame.name='Neco C'+(i+1)+' fixed front decoupling package frame';frame.position.set(p.x,p.y,.5);frame.rotation.z=p.angle;host.body.add(frame);
  capacitors.push(box(frame,[.68,1.15,.45],[0,0,.225],materials.plastic(0xaba581,{roughness:.75}),'Neco actual C'+(i+1)+' decoupling body; photo inferred position'));
  for(const sy of[-1,1]){terminals.push(box(frame,[.75,.27,.18],[0,sy*.5,.15],tin,'Neco actual fixed capacitor metal termination'));pads.push(box(frame,[.87,.44,.035],[0,sy*.53,.0175],tin,'Neco actual capacitor solder land'));}
 }
 return{pcb,pads,barrels,eyelets,capacitors,terminals,mountingCenters};
}
function socket(host,id){
 const p=spec.ports[id],frame=new THREE.Group();frame.name='Neco actual '+id+' rear upright Grove receiving socket';frame.position.fromArray(p.position);frame.quaternion.copy(socketQuaternion(id));host.body.add(frame);
 const white=materials.plastic(0xe1e2d6,{roughness:.68}),tin=materials.metal(0xbabcb1,{roughness:.4}),depth=8.25,parts=[],contacts=[],returns=[],tails=[],pads=[],anchors=[];
 const b=(size,pos,name,mat=white)=>{const o=box(frame,size,pos,mat,'Neco '+id+' '+name);parts.push(o);return o;};
 for(const sign of[-1,1]){
  b([.65,depth,5.1],[sign*4.675,-depth/2,0],'actual end wall');
  b([.65,2.6,.5],[sign*3.85,-depth+1.6,2.3],'actual guide rail');
  b([.6,1.15,.4],[sign*3.65,-1.9,2.35],'actual latch shoulder');
  b([1.3,1.35,1.2],[sign*5.15,-depth+.675,-1.95],'actual PCB foot');
  anchors.push(b([1.05,.22,1.8],[sign*5.15,-depth+.11,.5],'actual SMD anchor tab',tin));
 }
 const floor=b([8.7,depth,.65],[0,-depth/2,-2.225],'closed actual socket floor'),back=b([8.7,.65,4.45],[0,-depth+.325,.325],'closed actual dielectric backing'),bridge=b([4.8,2.3,.45],[0,-depth+1.5,2.325],'actual locking bridge');
 for(let i=0;i<4;i++){
  const x=(i-1.5)*2;
  contacts.push(b([.42,depth-1.7,.42],[x,-depth/2-.45,.15],'actual receiving contact '+(i+1),tin));
  returns.push(b([.42,.42,2.95],[x,-depth+.4,1.55],'actual fixed bent SMD contact '+(i+1),tin));
  tails.push(b([.42,.2,1.3],[x,-depth+.1,3.1],'actual fixed SMD solder tail '+(i+1),tin));
  pads.push(b([.72,.035,1.55],[x,-depth+.0175,3.1],'actual fixed PCB solder pad '+(i+1),tin));
 }
 const names=id==='grove'?['BTN','RGB-IN','5V','GND']:['NC (PCB print BTN)','RGB-OUT','5V','GND'];
 const port=host.add(new Port({id,label:id==='grove'?'J1 · rear IN':'J2 · rear OUT',connector:'grove',position:p.position,quaternion:socketQuaternion(id),pins:names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,.15],order:col=>col+1},hitSize:[11.6,1,5.1],meta:{role:'visual-connector',face:'back',physicalRole:p.role,source:'Own U163 photograph and HY-2.0-4P_SMD J1/J2 schematic',scope:'Physical four-contact connector and attachment only. Documentary labels do not forward signals or serial LED state; J2 pin1 is NC in schematic although PCB says BTN.'}}));
 return{frame,parts,floor,back,bridge,contacts,returns,tails,pads,anchors,port};
}
function leds(host){
 const packages=[],lenses=[],terminals=[],components=[],frames=[];
 const white=materials.plastic(0xdfdfd2,{roughness:.6}),tin=materials.metal(0xb9baaa,{roughness:.5});
 for(const p of pixels){
  const frame=new THREE.Group();frame.name='Neco actual RGB package '+p.number+' fixed frame';frame.position.set(p.x,p.y,.5);frame.rotation.z=p.angle;host.body.add(frame);frames.push(frame);
  packages.push(box(frame,[2,2,.55],[0,0,.275],white,'Neco actual RGB '+p.number+' 2020 package base'));
  const shape=roundedRect(2,2,.06),opening=new THREE.Path();opening.absarc(0,0,.62,0,Math.PI*2,false);shape.holes.push(opening);
  packages.push(solid(frame,shape,.3,[0,0,.55],white,'Neco actual RGB '+p.number+' molded lip around real encapsulant'));
  for(const dx of[-.74,.74])for(const dy of[-.74,.74])terminals.push(box(frame,[.52,.52,.07],[dx,dy,.035],tin,'Neco actual RGB package corner termination'));
  const lens=new THREE.Mesh(new THREE.CylinderGeometry(.6,.6,.35,32).rotateX(Math.PI/2),materials.plastic(0xdad7bd,{roughness:.32}));lens.name='Neco actual RGB '+p.number+' independent encapsulant';
  const led=host.add(new PackageLed({id:'led-'+p.number,label:'RGB '+p.number+' · visible edge package',position:[p.x,p.y,1.175],mesh:lens,radius:.6,glowSize:0,color:0xffffff,meta:{role:'externally-driven-visual',part:'WS2812C-2020',packageIndex:p.number,physicalOrder:'Front lower-left to tip to lower-right; visual indexing only, not claimed schematic U number or serial address',scope:'Independent external on/color/brightness only; no matrix, automatic effects, WS2812 bus, signal cascade, firmware or power emulation'}}));
  lenses.push(lens);components.push(led);
 }
 return{frames,packages,lenses,terminals,components};
}
function tactile(host){
 const p=spec.button,frame=new THREE.Group();frame.name='Neco actual rear S1 fixed switch package';frame.position.set(p.position[0],p.position[1],-.5);frame.rotation.z=p.rotationZ;host.body.add(frame);
 const black=materials.plastic(0x242522,{roughness:.8}),tin=materials.metal(0xb5b8ac,{roughness:.4}),fixed=[],terminals=[];
 const base=box(frame,[3.8,5.5,.25],[0,0,-.125],black,'Neco S1 closed fixed dielectric base');fixed.push(base);
 const rim=roundedRect(3.8,5.5,.2);rim.holes.push(roundedRect(2.48,3.26,.13,{path:new THREE.Path(),clockwise:true}));
 fixed.push(solid(frame,rim,.55,[0,0,-.8],black,'Neco S1 actual fixed molded plunger well'));
 const lid=roundedRect(3.8,5.5,.18);lid.holes.push(roundedRect(2.48,3.26,.12,{path:new THREE.Path(),clockwise:true}));
 fixed.push(solid(frame,lid,.15,[0,0,-.95],tin,'Neco S1 fixed metal cover with actual cap opening'));
 for(const x of[-2,2])for(const y of[-1.9,1.9])terminals.push(box(frame,[.8,.85,.17],[x,y,-.085],tin,'Neco S1 actual fixed solder terminal'));
 const cap=new THREE.Group();cap.name='Neco actual moving yellow S1 plunger';
 solid(cap,roundedRect(2.16,2.9,.15),.5,[0,0,-.25],materials.plastic(0xd5bc12,{roughness:.6}),'Neco S1 actual yellow moving cap');
 box(cap,[.7,.9,.075],[0,0,-.2875],black,'Neco S1 actual dark moving plunger centre');
 const button=host.add(new Button({id:p.id,label:'Rear S1 tactile input intent',position:p.position,rotation:[0,0,p.rotationZ],mesh:cap,axis:[0,0,1],travel:p.travelMm,longPressMs:800,meta:{role:'visual-control',surfaceFace:'back',part:'S1 SW-PB',travelSource:'Undimensioned 0.15mm appearance estimate into actual fixed switch well; not measured or rated travel',scope:'Momentary press/release/multi-source cancel and input intent only; no automatic LED effect, firmware, reset or electrical state.'}}));
 return{frame,fixed,base,terminals,button,moving:cap};
}
export function buildNeco(host){
 const board=circuit(host),input=socket(host,'grove'),output=socket(host,'out'),control=tactile(host),display=leds(host);
 host.necoAssembly={board,input,output,control,display};host.unitStickers=addStickers(host);
}
