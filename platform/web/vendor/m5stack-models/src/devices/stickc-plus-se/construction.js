/** MIT. K016-P-SE original parametric visual reconstruction; not a native CAD conversion. */
import * as T from 'three';
import {materials,Button,Led,Port} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {slab,mesh,grove,FACE,portQuaternion} from '../../modeling/parts.js';
import {usbC} from '../../modeling/connectors.js';
import {DIM,HAT_PINS,GROVE_PINS} from './dimensions.js';
import {FlexButton} from './FlexButton.js';
const role=(object,name,kind='physical-structure')=>{object.name=name;object.userData.role=kind;return object;};
function solid(parent,shape,depth,position,material,name){return role(mesh(parent,new T.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:24}),material,position),name);}
function plate(parent,w,h,d,r,p,m,name,holes=[]){return role(slab(parent,w,h,d,r,p,m,holes,.04),name);}
function box(parent,size,position,material,name){return role(mesh(parent,new T.BoxGeometry(...size),material,position),name);}
function posed(parent,position,face,name){const g=new T.Group();g.position.fromArray(position);g.quaternion.copy(FACE[face]);g.name=name;parent.add(g);return g;}
function ring(parent,outer,inner,depth,position,material,name){const s=new T.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);const h=new T.Path();h.absarc(0,0,inner,0,Math.PI*2,true);s.holes.push(h);return solid(parent,s,depth,position,material,name);}
function cylinder(parent,r,d,position,material,name){return role(mesh(parent,new T.CylinderGeometry(r,r,d,40).rotateX(Math.PI/2),material,position),name);}

function enclosure(host,a,palette){
 const {shell}=palette,display=DIM.display;
 a.front=plate(host.body,24,48,1.1,3,[0,0,5.66],shell,'Plus SE orange front molding',[
  {w:display.window[0],h:display.window[1],r:.65,cy:8.1},
  {w:15,h:9.7,r:.9,cy:-13.8}
 ]);
 // A true aperture surrounds only the free edge/sides of the integral tab. Its
 // lower molded bridge remains in the fixed shell and never follows the key.
 a.hinge=plate(host.body,15,.35,1.1,.05,[0,-18.55,5.66],shell,'Plus SE fixed lower A-key hinge bridge');
 a.sides={};
 for(const face of ['left','right']){
  const g=posed(host.body,[face==='left'?-12:12,0,0],face,`Plus SE ${face} wall frame`);
  const c=face==='left'?DIM.power:DIM.b;
  const holes=[{w:c.w+.45,h:c.h+.4,r:.5,cx:face==='left'?-c.position[1]:c.position[1],cy:0}];
  // The small side apertures are real cavities with packages behind them.
  if(face==='left')holes.push({w:3.8,h:1.1,r:.15,cx:-17.0,cy:-.65},{w:2.7,h:1.2,r:.2,cx:3.4,cy:-.55});
  else holes.push({w:3.5,h:1.0,r:.1,cx:-4.1,cy:-.65},{w:3.4,h:1.0,r:.12,cx:16.3,cy:-.65});
  a.sides[face]=plate(g,42,11.32,1.1,.05,[0,0,-1.1],shell,`Plus SE thick ${face} enclosure wall`,holes);
 }
 for(const face of ['top','bottom']){
  const g=posed(host.body,[0,face==='top'?24:-24,0],face,`Plus SE ${face} wall frame`);
  // Both connector notches reach the rear split. An open perimeter is used
  // rather than passing an out-of-bounds hole to the triangulator.
  const profile=new T.Shape();
  const points=face==='top'?[[-9,-5.66],[9,-5.66],[9,3.35],[-9,3.35]]:[[-9,-5.66],[-5.3,-5.66],[-5.3,-.8],[5.3,-.8],[5.3,-5.66],[9,-5.66],[9,5.66],[-9,5.66]];
  points.forEach(([x,y],i)=>i?profile.lineTo(x,y):profile.moveTo(x,y));profile.closePath();
  const holes=face==='top'?[]:[{w:9.3,h:3.65,r:1.5,cy:3.25}];
  for(const h of holes)profile.holes.push(roundedRect(h.w,h.h,h.r,{cx:h.cx??0,cy:h.cy??0,path:new T.Path(),clockwise:true}));
  a.sides[face]=solid(g,profile,1.1,[0,0,-1.1],shell,`Plus SE thick ${face} notched enclosure wall`);
 }
 // Four analytic quarter-annular corners meet both straight sidewalls; they
 // are closed positive solids, not a cosmetic front-only rounded rectangle.
 a.corners=[];
 for(const sx of[-1,1])for(const sy of[-1,1]){
  const start=sx===1?(sy===1?0:-Math.PI/2):(sy===1?Math.PI/2:Math.PI),end=start+Math.PI/2;
  const s=new T.Shape();s.absarc(0,0,3,start,end,false);s.lineTo(1.9*Math.cos(end),1.9*Math.sin(end));s.absarc(0,0,1.9,end,start,true);s.closePath();
  a.corners.push(solid(host.body,s,11.32,[sx*9,sy*21,-5.66],shell,`Plus SE closed corner ${sx}/${sy}`));
 }
 const rear=new T.Shape();rear.moveTo(-9,-24);rear.lineTo(-5.5,-24);rear.lineTo(-5.5,-19);rear.lineTo(5.5,-19);rear.lineTo(5.5,-24);rear.lineTo(9,-24);rear.absarc(9,-21,3,-Math.PI/2,0,false);rear.lineTo(12,21);rear.absarc(9,21,3,0,Math.PI/2,false);rear.lineTo(-9,24);rear.absarc(-9,21,3,Math.PI/2,Math.PI,false);rear.lineTo(-12,-21);rear.absarc(-9,-21,3,Math.PI,Math.PI*1.5,false);rear.closePath();
 rear.holes.push(roundedRect(20.4,33.4,.65,{cx:0,cy:4,path:new T.Path(),clockwise:true}));
 for(const x of[-8,8])for(const y of[-14.6,-19.5])rear.holes.push(roundedRect(3.2,3.2,1.6,{cx:x,cy:y,path:new T.Path(),clockwise:true}));
 a.rear=solid(host.body,rear,1.1,[0,0,-6.76],shell,'Plus SE notched rear molding with real mounting bores');
 a.carrier=plate(host.body,21,37,.32,.65,[0,4.7,-6.86],materials.plastic(0xe6e5dc,{roughness:.85}),'Plus SE physical rear label substrate');a.carrier.userData.role='physical-label-substrate';
}

function frontKey(host,a,palette){
 const g=new T.Group();g.name='Plus SE physical integral front A tab';
 // One closed solid includes its recessed letter floors and inner thickness.
 // Layered top/base meshes would bend with different face triangulations and
 // create tiny gaps; the tab therefore shares a single continuous boundary.
 const m=[[-5.1,-2.6],[-5.1,2.6],[-4.48,2.6],[-1.45,-.7],[1.25,2.6],[1.85,2.6],[1.85,-2.6],[1.25,-2.6],[1.25,1.63],[-1.44,-1.58],[-4.5,1.63],[-4.5,-2.6]];
 const five=[[2.65,2.6],[6.0,2.6],[6.0,1.95],[3.3,1.95],[3.3,.3],[5.2,.3],[6.0,-.4],[6.0,-1.9],[5.3,-2.6],[2.65,-2.6],[2.65,-1.95],[5.05,-1.95],[5.35,-1.65],[5.35,-.7],[5.0,-.35],[2.65,-.35]].map(([x,y])=>[x,y+.025]);
 let outer=roundedRect(14.4,9.2,.65).getPoints(24);outer=outer.filter((p,i)=>!i||p.distanceTo(outer[i-1])>1e-7);if(outer[0].distanceTo(outer.at(-1))<1e-7)outer.pop();if(T.ShapeUtils.area(outer)<0)outer.reverse();
 const holes=[m,five].map(poly=>poly.map(([x,y])=>new T.Vector2(x,y)));for(const h of holes)if(T.ShapeUtils.area(h)>0)h.reverse();
 const positions=[];
 const tri=(a,b,c)=>positions.push(...a,...b,...c);
 const face=(contour,voids,z,up)=>{const points=[...contour,...voids.flat()];for(const t of T.ShapeUtils.triangulateShape(contour,voids)){const q=t.map(i=>[points[i].x,points[i].y,z]);const cross=(q[1][0]-q[0][0])*(q[2][1]-q[0][1])-(q[1][1]-q[0][1])*(q[2][0]-q[0][0]);if((cross>0)!==up)[q[1],q[2]]=[q[2],q[1]];tri(...q);}};
 const sides=(loop,lo,hi)=>{for(let i=0;i<loop.length;i++){const p=loop[i],q=loop[(i+1)%loop.length],a=[p.x,p.y,lo],b=[q.x,q.y,lo],c=[q.x,q.y,hi],d=[p.x,p.y,hi];tri(a,b,c);tri(a,c,d);}};
 face(outer,holes,1.1,true);face(outer,[],0,false);sides(outer,0,1.1);
 for(const h of holes){sides(h,.76,1.1);face([...h].reverse(),[],.76,true);}
 const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(positions,3));geometry.computeVertexNormals();
 a.aBase=a.aSkin=role(mesh(g,geometry,palette.shell,[0,-13.8,5.66]),'Plus SE complete molded A tab with recessed M5 floors');
 const button=host.add(new FlexButton({id:'a',label:'Button A · molded front tab',mesh:g,hingeY:-18.4,freeY:-9.2,travel:.25,axis:[0,0,-1],longPressMs:0,meta:{gpio:'G37',role:'visual-control',visualMotion:'flex-pad',actuation:'momentary',hingeY:-18.4,freeY:-9.2,travelSource:'Visual estimate; no measured switch travel or plastic physics'}}));
 a.a=button;
}

function sideKey(host,a,palette,id,d,label,gpio){
 const moving=new T.Group();moving.name=`Plus SE physical ${id} side key`;
 a[id+'Cap']=plate(moving,d.w,d.h,.85,.42,[0,0,-.76],palette.shell,`Plus SE ${id} complete key cap`);
 a[id+'Stem']=plate(moving,2.1,2.8,.75,.16,[0,0,-1.51],palette.shell,`Plus SE ${id} internal plunger`);
 const key=host.add(new Button({id,label,mesh:moving,position:d.position,quaternion:FACE[d.face],axis:[0,0,-1],travel:d.travel,longPressMs:0,meta:{role:'visual-control',gpio,actuation:'momentary',travelSource:'Photo-derived visual estimate; power intent does not change firmware'}}));
 const frame=posed(host.body,d.position,d.face,`Plus SE fixed ${id} switch support`);
 a[id+'Switch']=plate(frame,d.w+.8,d.h+.8,.9,.38,[0,0,-3.0],palette.black,`Plus SE recessed fixed ${id} tactile switch`);
 a[id+'SwitchLid']=plate(frame,d.w+.15,d.h+.15,.15,.28,[0,0,-2.1],palette.metal,`Plus SE fixed ${id} switch lid`);
 a[id]=key;
}

function electronics(host,a,palette){
 // The main board follows the real connector stack and clears the lower Grove
 // package. Chip/BOM positions concealed by the housing are visual inferences.
 // Avoid a cutout extending outside its parent contour: the board instead has
 // an open lower central notch in its perimeter.
 const pcbShape=new T.Shape();const points=[[-10.6,-21.15],[-5.55,-21.15],[-5.55,-17.5],[5.55,-17.5],[5.55,-21.15],[10.6,-21.15],[10.6,5.2],[8.8,5.2],[8.8,11],[10.6,11],[10.6,21.15],[-10.6,21.15],[-10.6,18],[-10.2,18],[-10.2,16],[-10.6,16],[-10.6,-2.6],[-10.2,-2.6],[-10.2,-4.2],[-10.6,-4.2],[-10.6,-12.5],[-8.8,-12.5],[-8.8,-18.5],[-10.6,-18.5]];points.forEach(([x,y],i)=>i?pcbShape.lineTo(x,y):pcbShape.moveTo(x,y));pcbShape.closePath();
 a.pcb=solid(host.body,pcbShape,.8,[0,0,.35],materials.plastic(0x205d46,{roughness:.91}),'Plus SE inferred main PCB with connector relief');
 a.battery=plate(host.body,17.0,27.4,3.65,1.1,[0,1.0,-4.6],materials.metal(0xa6aaa3,{roughness:.8}),'Plus SE internal 120mAh pouch envelope');
 box(host.body,[14,3,.3],[0,-11.32,-.75],palette.black,'Plus SE battery terminal insulation');
 plate(host.body,19.4,29.1,.7,.8,[0,8.1,3.55],palette.metal,'Plus SE LCD metal back');
 plate(host.body,18.3,28.2,1.1,.8,[0,8.1,4.25],palette.black,'Plus SE LCD optical module');
 a.lcdSupport=plate(host.body,16.3,26.3,.3,.6,[0,8.1,5.35],palette.black,'Plus SE front optical carrier');
 // A thick black glass perimeter surrounds the active display; the framebuffer
 // plane is independent. A sealed physical stack remains behind every pixel.
 a.glass=plate(host.body,15.4,25.8,.20,.58,[0,8.1,6.60],materials.glossy(0x080a0b,{roughness:.15,clearcoat:.6}),'Plus SE physical front glass');
 for(const [x,y,w,h]of[[-5,-3.5,7,7],[6,-4.5,3.2,5.2],[-6,15,3,3]])plate(host.body,w,h,.85,.25,[x,y,1.15],palette.black,'Plus SE inferred concealed package');
 const buzzer=cylinder(host.body,3.7,1.6,[0,-12,2.0],palette.black,'Plus SE passive buzzer housing');
 cylinder(host.body,3.2,.12,[0,-12,2.86],palette.metal,'Plus SE passive buzzer diaphragm');
 a.aSwitch=plate(host.body,5.5,5.5,.8,.3,[0,-12.8,4.0],palette.black,'Plus SE fixed front A tactile switch');
 plate(host.body,4.9,4.9,.18,.22,[0,-12.8,4.8],palette.metal,'Plus SE fixed A switch lid');
 cylinder(host.body,.8,.18,[0,-12.8,5.08],palette.black,'Plus SE fixed A switch plunger');
 // PCB-to-housing ribs and four real bosses close concealed empty edge strips.
 for(const x of[-9.2,9.2])for(const y of[-8,10])plate(host.body,1.5,3.8,4.8,.35,[x,y,-4.55],palette.shell,'Plus SE molded board support rib');
 for(const x of[-8,8])for(const y of[-14.6,-19.5]){
  ring(host.body,2.0,1.15,4.1,[x,y,-5.66],palette.shell,'Plus SE hollow mount boss');
  const f=posed(host.body,[x,y,-6.78],'back','Plus SE rear fastener assembly');
  ring(f,1.52,.66,.13,[0,0,0],y===-14.6?materials.metal(0xb3aa67,{roughness:.55}):palette.metal,y===-14.6?'Plus SE retained magnet ring':'Plus SE recessed rear screw head');
  cylinder(f,.64,.12,[0,0,-.9],palette.metal,'Plus SE blind screw stop');
 }
 a.buzzer=buzzer;
}

function interfaces(host,a,palette){
 a.usb=usbC(host,{...DIM.usb,face:'bottom'});
 a.usb.userData.role='physical-connector';a.usb.name='Plus SE USB-C shield tongue and 24 contacts';
 a.grove=grove(host,{...DIM.grove,face:'bottom',color:0xe8e8de});a.grove.name='Plus SE physical HY2.0-4P';
 const cavity=a.grove.children.find(o=>o.geometry?.type==='PlaneGeometry');if(cavity){cavity.removeFromParent();cavity.geometry.dispose();cavity.material.dispose();}
 host.port('grove').pins=GROVE_PINS.map(p=>({...p}));host.port('grove').meta={...host.port('grove').meta,pinSource:'Official Plus SE PinMap; visual-only'};
 const hat=posed(host.body,DIM.hat.position,'top','Plus SE physical eight-position HAT socket');a.hat=hat;
 const wells=Array.from({length:8},(_,i)=>({w:1.65,h:1.65,r:.045,cx:(i-3.5)*2.54,cy:0}));
 a.hatHousing=plate(hat,20.82,3.04,3.0,.22,[0,0,-2.8],palette.black,'Plus SE HAT thick molded eight-well housing',wells);
 a.hatStops=[];a.hatContacts=[];
 for(const hole of wells){
  const well=roundedRect(1.65,1.65,.045);well.holes.push(roundedRect(1.02,1.02,.025,{path:new T.Path(),clockwise:true}));
  solid(hat,well,2.3,[hole.cx,0,-2.6],palette.black,'Plus SE HAT four physical bore walls');
  a.hatStops.push(box(hat,[1.65,1.65,.16],[hole.cx,0,-2.68],palette.black,'Plus SE HAT deep socket stop'));
  for(const sign of[-1,1])a.hatContacts.push(box(hat,[.12,.72,.82],[hole.cx+sign*.37,0,-1.9],palette.metal,'Plus SE HAT recessed spring contact'));
 }
 host.add(new Port({id:'hat',label:'HAT · 1×8 2.54 mm',connector:'m5.hat',pins:HAT_PINS.map(p=>({...p})),position:[0,23.5,-5],quaternion:portQuaternion('top'),hitSize:[21,1,3],pinGrid:{cols:8,rows:1,pitch:2.54,center:[0,0],order:col=>8-col},meta:{role:'visual-connector',face:'top',pinSource:'Own Plus SE rear label; world +X to -X is printed rear-view left to right'}}));
 for(let i=0;i<8;i++){
  const x=(i-3.5)*2.54;
  box(host.body,[.46,3.5,.46],[x,20.8,-5],palette.metal,'Plus SE HAT board contact tail');
  box(host.body,[.46,.46,5.2],[x,19.3,-2.2],palette.metal,'Plus SE HAT inferred contact riser');
 }
 for(const x of[-3,-1,1,3]){
  box(host.body,[.42,1.5,.42],[x,-17.9,-3.7],palette.metal,'Plus SE Grove contact elbow');
  box(host.body,[.42,.42,4.6],[x,-17.3,-1.55],palette.metal,'Plus SE Grove PCB tail');
 }
 for(const x of[-4.5,4.5])box(host.body,[.7,2.2,1.4],[x,-21,1.7],palette.metal,'Plus SE USB-C board shield anchor');
}

function optics(host,a,palette){
 // Own SE uses red LED G10 and IR G9. Both packages remain independent;
 // commands are visible output only, without electrical or firmware emulation.
 const left=posed(host.body,[-12,0,0],'left','Plus SE passive optical and acoustic stack');
 plate(left,3.5,.85,1.5,.16,[-17,-.65,-1.55],materials.plastic(0xd7dcd3,{roughness:.26}),'Plus SE side status light guide');
 plate(left,2.7,1.1,1.3,.2,[3.4,-.55,-1.5],palette.black,'Plus SE microphone acoustic package');
 const lens=new T.Mesh(new T.BoxGeometry(2.35,.63,.26),materials.plastic(0xcc2018,{roughness:.25}));lens.name='Plus SE actual red status lens';lens.userData.role='physical-optic';
 a.red=host.add(new Led({id:'red',label:'Red LED · external visual output',mesh:lens,position:[-12.01,17,-.65],quaternion:FACE.left,glowSize:2.7,radius:.3,color:0xff3020,meta:{gpio:'G10',role:'externally-driven-visual',scope:'Separate G10 red LED and G9 passive IR; no automatic output coupling'}}));
 const right=posed(host.body,[12,0,0],'right','Plus SE opposite acoustic and sleep indicator stack');
 plate(right,3.15,.8,1.1,.12,[-4.1,-.65,-1.3],palette.black,'Plus SE opposite recessed acoustic cavity');
 a.green=plate(right,3.1,.75,1.2,.14,[16.3,-.65,-1.2],materials.plastic(0xd5edc6,{roughness:.28}),'Plus SE photo-derived small passive side light guide');

 a.ir=plate(left,3.1,.65,1.2,.14,[-17,-.65,-1.3],palette.black,'Plus SE passive infrared package');
}

export function buildConstruction(host){
 const palette={shell:materials.plastic(0xff6215,{roughness:.38,clearcoat:.22,transparent:true,opacity:.58,depthWrite:false}),black:materials.plastic(0x1c2522,{roughness:.86}),metal:materials.metal(0xa4aaa4,{roughness:.48})};
 const a={noImu:true,bodyThicknessSource:'Own SE mechanical drawing13.52mm;page table8.4mm conflicts',geometryKind:'original-parametric-reconstruction'};enclosure(host,a,palette);frontKey(host,a,palette);sideKey(host,a,palette,'b',DIM.b,'Button B · right side','G39');sideKey(host,a,palette,'power',DIM.power,'AXP192 power/reset intention','AXP192 PWR_KEY');electronics(host,a,palette);interfaces(host,a,palette);optics(host,a,palette);host.stickcPlusSeAssembly=a;return a;
}
