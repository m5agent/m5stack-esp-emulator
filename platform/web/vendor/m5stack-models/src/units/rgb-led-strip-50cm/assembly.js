/** MIT; own A093 dimensional/photo construction. Hidden Z/terminal fit is inferred. */
import {Led,Port} from '../../core/index.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {THREE,materials,roundedRect,rectHole,solid,mesh,box,bakedBox,swept,tube,replaceGeometry} from './geometry.js';
import {StripFlex} from './Flex.js';
import {InputAdapter} from './Adapter.js';
import {AssemblyPose} from './AssemblyPose.js';
import {female3,male3,inputQuaternion,outputQuaternion} from './connectors.js';
import {INPUT_FAMILY,OUTPUT_FAMILY} from './dimensions.js';
const png=new URL('./artwork/plus5v.png',import.meta.url).href;

export function buildStrip(host,options={},groveMode=false){
 const pose=groveMode?host.add(new AssemblyPose()):null,frame=pose?.object3d??new THREE.Group();
 if(!pose)host.body.add(frame);frame.name='A093 own500mm30x5050 complete flexible assembly';
 const flex=host.add(new StripFlex(),frame),white=materials.plastic(0xe9e9df,{roughness:.78}),copper=materials.metal(0xb78445,{roughness:.48}),metal=materials.metal(0xb6b8a9,{roughness:.38});
 const fpc=flex.surface(mesh(frame,swept([[-5,0],[5,0],[5,.3],[-5,.3]]),white,[0,0,0],'A093 continuous solid500x10 FPC'));
 const adhesive=flex.surface(mesh(frame,swept([[-5,-.12],[5,-.12],[5,0],[-5,0]]),materials.plastic(0xd0bd89,{roughness:.85}),[0,0,0],'A093 continuous real rear adhesive carrier;unprinted'));
 const pads=[],packages=[],links=[],passives=[],inks=[];
 const solder=(p,site,q,n)=>{const o=mesh(frame,new THREE.CylinderGeometry(.2,.2,1,12),metal,[0,0,0],n);flex.link(o,p,site,q);links.push(o);return o;};
 for(let i=0;i<30;i++){
  const x=(i+.5)*500/30,g=new THREE.Group();g.name=`A093 rigid5050 LED package${i}`;frame.add(g);flex.site(g,x);
  const floor=box(g,[5,5,.22],[0,0,.46],white,'A093 actual5050 retained base'),shape=roundedRect(5,5,.12);rectHole(shape,0,0,3.8,3.8);
  const wall=mesh(g,solid(shape,1.18),white,[0,0,.57],'A093 actual5050 true resin window surround');
  const resin=new THREE.Mesh(new THREE.BoxGeometry(3.72,3.72,1.0),materials.plastic(0xd9dcd5,{roughness:.16,clearcoat:1}));resin.name=`A093 individual RGB resin emitter${i}`;
  const led=host.add(new Led({id:`pixel-${i}`,label:`A093 RGB pixel ${i+1}/30`,mesh:resin,position:[0,0,1.06],color:0xffffff,radius:1.86,glowSize:6,meta:{role:'externally-driven-RGB',scope:'External appearance only;no automatic rainbow,SK6812 protocol,power or propagation'}}),g);
  const terminals=[];
  for(const dx of[-1.7,1.7])for(const y of[-2.2,2.2]){
   terminals.push(box(g,[.72,.6,.2],[dx,y,.47],metal,'A093 retained5050 actual terminal'));
   pads.push(flex.surface(bakedBox(frame,[1.05,1.1,.035],[x+dx,y,.3175],copper,'A093 conforming actual LED copper land')));
   solder([x+dx,y,.335],g,[dx,y,.43],'A093 real curved FPC to rigid5050 solder bridge');
  }
  packages.push({frame:g,x,floor,wall,led,resin,terminals});
  const pg=new THREE.Group();frame.add(pg);flex.site(pg,x+4.7);
  const passive={frame:pg,x:x+4.7,body:box(pg,[1.55,.8,.4],[0,2.7,.53],materials.plastic(0xa3a294,{roughness:.8}),'A093 visible retained passive')};
  for(const dx of[-.64,.64]){box(pg,[.3,.8,.17],[dx,2.7,.415],metal,'A093 metallized passive foot');solder([x+4.7+dx,2.7,.335],pg,[dx,2.7,.415],'A093 passive real solder support');}passives.push(passive);
 }
 for(let row=0;row<=30;row++){
  const x=Math.max(.7,Math.min(499.3,row*500/30));
  for(const y of[-3.2,0,3.2])pads.push(flex.surface(bakedBox(frame,[1.3,1.9,.035],[x,y,.3175],copper,'A093 physical cut/termination copper pad')));
  if(row>0&&row<30&&options.artwork!==false){
   const panels=printedArtwork(host,{target:fpc,url:png,size:[3.1,1.55],position:[x+2.8,-3.45,.3],depth:.08,face:'front',name:'A093 +5V safe reference-redraw ink',artworkKind:'reference-redraw'});
   for(const p of panels){flex.surface(p);inks.push(p);}
  }
 }
 // A closed real transparent dropcoat,not a floating plane or a replacement for the board/packages.
 const coating=flex.surface(mesh(frame,swept([[-5,.3],[5,.3],[5,.65],[4.8,1.75],[4.1,2.35],[2.9,2.6],[-2.9,2.6],[-4.1,2.35],[-4.8,1.75],[-5,.65]]),new THREE.MeshPhysicalMaterial({color:0xf4f7ed,roughness:.14,metalness:0,transmission:.55,transparent:true,opacity:.23,clearcoat:1,depthWrite:false}),[0,0,0],'A093 continuous closed transparent protective dropcoat'));
 const ends=[];
 for(const input of[true,false]){
  const x=input?0:500,sign=input?-1:1,g=new THREE.Group();g.name=`A093 retained ${input?'input':'output'} end`;frame.add(g);flex.site(g,x);
  const sleeveShape=roundedRect(10.8,3.8,.65);rectHole(sleeveShape,0,0,10.1,3.12);
  const bg=solid(sleeveShape,10),bp=bg.attributes.position;for(let i=0;i<bp.count;i++){const a=bp.getX(i),b=bp.getY(i),c=bp.getZ(i);bp.setXYZ(i,c-5,a,b+1.25);}bg.computeVertexNormals();
  const boot=mesh(g,bg,materials.plastic(0xf0f0e8,{roughness:.55}),[0,0,0],'A093 real hollow white heat-shrink retained over FPC');
  const port=host.add(new Port({id:input?'input':'output',label:input?'Actual black3P receiving input':'Actual black3P male extension',connector:input?INPUT_FAMILY:OUTPUT_FAMILY,position:[sign*42,0,1.1],quaternion:input?inputQuaternion():outputQuaternion(),hitSize:[9.5,1,5.1],pins:[{n:1,name:'3P contact1'},{n:2,name:'3P contact2'},{n:3,name:'3P contact3'}],pinGrid:{cols:3,rows:1,pitch:2.5,center:[0,-.2],order:col=>col+1},meta:{physicalContacts:3,scope:'Own A093 mechanical family;not a Grove receptacle,not a generic JST/electrical mapping'}}),g);
  const connector=input?female3(port.object3d):male3(port.object3d,{name:'A093 actual output male3P'}),wires=[0xbe2821,0xe6e6db,0x19975a].map((c,i)=>mesh(frame,new THREE.BufferGeometry(),materials.plastic(c,{roughness:.62}),[0,0,0],`A093 ${input?'input':'output'} actual pigtail conductor${i}`));
  const end={input,frame:g,port,connector,boot,wires,wirePoints:[]};ends.push(end);
  flex.callbacks.push(()=>{end.wirePoints=wires.map((w,i)=>{
   const start=flex.point(input?1:499,(i-1)*3.2,.52),local=new THREE.Vector3((i-1)*2.5,input?-9.3:-10.5,-.2).applyQuaternion(port.object3d.quaternion).add(port.object3d.position),finish=local.applyQuaternion(g.quaternion).add(g.position),axis=new THREE.Vector3(sign,0,0).applyQuaternion(g.quaternion),curve=new THREE.CubicBezierCurve3(start,start.clone().addScaledVector(axis,12),finish.clone().addScaledVector(axis,-8),finish),ps=curve.getPoints(36);replaceGeometry(w,tube(ps,.43,10));return ps;
  });});
 }
 const a={frame,pose,flex,fpc,adhesive,coating,pads,packages,links,passives,inks,ends};host.rgbStrip50Assembly=a;host.unitStickers=inks;
 flex.set({bendDeg:options.bendDeg??0});
 if(pose){host.rgbstripSourceFrame=host.body;pose.bindInput(ends[0].port);pose.set({rotation:[0,0,Math.PI/2],distance:90});}
 if(options.adapter!==false)ends[0].port.attach(new InputAdapter());
 return a;
}
