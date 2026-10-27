import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh} from '../../modeling/parts.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';

const pinRadius=.225,pitchRadius=5.08/2,a=pitchRadius/Math.sqrt(2);
// The manufacturer pinout is a bottom view. Mirror X for this library's
// front-view XY frame; choosing the reference tab toward +Y is inferred.
const pins=[['SCL',1,-a,a],['SDA',2,-a,-a],['VDD',3,a,-a],['VSS',4,a,a]].map(([name,pin,x,y])=>Object.freeze({name,pin,position:Object.freeze([x,8+y]),bottomView:Object.freeze([-x,y])}));

export const NCIR_ASSEMBLY=Object.freeze({
 centre:Object.freeze([0,8]),bodyRadius:4.1,headerRadius:4.56,
 packageBottom:.5,shoulderZ:4.1,topZ:4.6,headerTop:1,
 crownRadius:2.8,windowRadius:1.75,windowBottom:4.28,windowTop:4.40,
 boardBottom:-.3,boardTop:.5,pinRadius,pinPitchRadius:pitchRadius,
 mountedLeadBottom:-.95,pins:Object.freeze(pins),
 source:'M5Stack U028 own mechanical drawing; Melexis MLX90614 Rev21 p6/p47, standard MLX90614xxA package.',
 inferred:'Package yaw, flange thickness/tab, crown slope/window recess, PCB outline/thickness/placement, clipped lead length and solder are assembled appearance inferences; no production PCB or assembly STEP is available.',
});

const metal=()=>materials.metal(0xb3b6b5,{roughness:.35});
const solder=()=>materials.metal(0xa9adad,{roughness:.42});
// ExtrudeGeometry only repairs hole winding while reversing a CCW outer
// contour. Our PCB is already clockwise, so holes must start CCW themselves.
function circleHole(shape,x,y,r){const hole=new THREE.Path();hole.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(hole);}
function ring(outer,inner){const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);circleHole(shape,0,0,inner);return shape;}
function extrude(parent,shape,depth,z,material,name,xy=[0,0]){
 return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32}),material,[...xy,z],name);
}
function cylinder(parent,r,bottom,top,material,name,xy=[0,0]){
 return mesh(parent,new THREE.CylinderGeometry(r,r,top-bottom,96).rotateX(Math.PI/2),material,[...xy,(bottom+top)/2],name);
}

function replaceBoard(host){
 const old=host.body.getObjectByName('Unit PCB');
 if(!old?.isMesh)throw new Error('NCIR requires its original board before reconstruction');
 // Hidden board reconstructed conservatively inside this product's native
 // cavity. LEGO boss reliefs are open contours; leads have real drilled holes.
 const shape=new THREE.Shape();
 shape.moveTo(-6.4,13.8);shape.lineTo(6.4,13.8);shape.lineTo(10.4,9.8);shape.lineTo(10.4,.35);shape.lineTo(8,.35);
 shape.absarc(8,-4,4.35,Math.PI/2,Math.PI*1.5,false);shape.lineTo(10.4,-8.35);shape.lineTo(10.4,-9.8);shape.lineTo(6.4,-13.8);shape.lineTo(5.6,-13.8);shape.lineTo(5.6,-8.5);shape.lineTo(-5.6,-8.5);shape.lineTo(-5.6,-13.8);shape.lineTo(-6.4,-13.8);shape.lineTo(-10.4,-9.8);shape.lineTo(-10.4,-8.35);shape.lineTo(-8,-8.35);
 shape.absarc(-8,-4,4.35,Math.PI*1.5,Math.PI*2.5,false);shape.lineTo(-10.4,.35);shape.lineTo(-10.4,9.8);shape.closePath();
 circleHole(shape,0,-4,3);
 for(const pin of pins)circleHole(shape,...pin.position,.35);
 for(const x of [-3,-1,1,3])circleHole(shape,x,-8.1,.30);
 const material=old.material;old.removeFromParent();old.geometry.dispose();
 const board=extrude(host.body,shape,.8,NCIR_ASSEMBLY.boardBottom,material,'NCIR PCB with open boss and Grove relief');
 board.userData={source:'U028 native-cavity reconstruction; concealed engineering fit, not a production PCB drawing',zMm:[-.3,.5],drillRadiusMm:{sensor:.35,grove:.30},inferred:NCIR_ASSEMBLY.inferred};
 host.parts.pcb=board;return board;
}

function sensorPackage(host){
 const d=NCIR_ASSEMBLY,xy=d.centre;
 // Full closed annular can. The nominal 3.60 shoulder and 4.10 crown are
 // measured from the SAME flange underside; their difference is the crown.
 const profile=[[d.windowRadius,d.headerTop],[d.bodyRadius,d.headerTop],[d.bodyRadius,d.shoulderZ],[d.crownRadius,d.shoulderZ],[2.45,4.48],[2.3,d.topZ],[1.8,d.topZ],[d.windowRadius,4.55],[d.windowRadius,d.headerTop]].map(p=>new THREE.Vector2(...p));
 const body=mesh(host.body,new THREE.LatheGeometry(profile,128).rotateX(Math.PI/2),metal(),[...xy,0],'NCIR MLX90614 standard TO39 can with raised crown');
 body.userData={variant:'MLX90614ESF-BAA / standard xxA',source:d.source,outerDiameterMm:8.2,crownDiameterMm:5.6,windowDiameterMm:3.5,shoulderFromBaseMm:3.6,totalFromBaseMm:4.1,inferred:'Crown slope and window lip/recess follow U028 photographs; flange thickness and assembled Z are engineering reconstructions.'};
 const window=cylinder(host.body,d.windowRadius,d.windowBottom,d.windowTop,materials.glossy(0x25313b,{roughness:.25}),'NCIR closed recessed infrared window',xy);
 window.userData={diameterMm:3.5,source:'Melexis xxA mechanical drawing; axial recess and thickness are appearance inferences.',scope:'Passive opaque optical appearance only; no visible IR emission or temperature simulation.'};
 const r=d.headerRadius,half=.35,join=Math.sqrt(r*r-half*half),end=r+.5;
 const shape=new THREE.Shape();shape.moveTo(half,join);shape.lineTo(half,end);shape.lineTo(-half,end);shape.lineTo(-half,join);shape.absarc(0,0,r,Math.atan2(join,-half),Math.PI*2+Math.atan2(join,half),false);shape.closePath();
 for(const pin of pins)circleHole(shape,pin.position[0],pin.position[1]-8,.8);
 const header=extrude(host.body,shape,d.headerTop-d.packageBottom,d.packageBottom,metal(),'NCIR drilled TO39 flange and reference tab',xy);
 header.userData={diameterMm:9.12,baseZMm:d.packageBottom,inferred:'Flange thickness .50, tab .70 wide/.50 extension and tab toward +Y are unmeasured appearance choices; 3.60 in the datasheet is NOT flange thickness.'};
 const leads=[],insulators=[],pads=[],fillets=[];
 for(const pin of pins){
  const [x,y]=pin.position;
  insulators.push(extrude(host.body,ring(.8,d.pinRadius),d.headerTop-d.packageBottom,d.packageBottom,materials.plastic(0x41453e,{roughness:.72}),`NCIR ${pin.name} glass feedthrough`,[x,y]));
  const lead=cylinder(host.body,d.pinRadius,d.mountedLeadBottom,d.headerTop,metal(),`NCIR ${pin.name} clipped TO39 lead`,[x,y]);
  lead.userData={pin:pin.pin,name:pin.name,bottomViewMm:[...pin.bottomView],modelFrontViewXYMm:[x,y],source:'Melexis bottom-view pinout; 5.08 pitch circle and .45 conductor diameter.',inferred:'Reference tab yaw and installed clipped length; raw nominal leads are 13 mm, not this installed length.'};leads.push(lead);
  pads.push(extrude(host.body,ring(.62,.35),.06,-.36,metal(),`NCIR ${pin.name} annular solder pad`,[x,y]));
  const filletProfile=[[d.pinRadius,-.78],[.28,-.78],[.56,-.40],[.56,-.36],[.35,-.36],[.35,-.63],[d.pinRadius,-.73],[d.pinRadius,-.78]].map(p=>new THREE.Vector2(...p));
  const fillet=mesh(host.body,new THREE.LatheGeometry(filletProfile,48).rotateX(Math.PI/2),solder(),[x,y,0],`NCIR ${pin.name} annular solder fillet`);fillet.userData={inferred:'Concealed solder and cropped leads, not a measured production joint.'};fillets.push(fillet);
 }
 return {body,window,header,leads,insulators,pads,fillets};
}

function groveAssembly(host){
 const socket=refineOpenTopGrove(host,'ncir'),tails=[],pads=[],fillets=[];
 for(const [i,x]of [-3,-1,1,3].entries()){
  tails.push(mesh(host.body,new THREE.BoxGeometry(.32,5.7,.32),metal(),[x,-10.95,1.25],`NCIR Grove concealed contact tail ${i+1}`));
  tails.push(mesh(host.body,new THREE.BoxGeometry(.32,.32,2.26),metal(),[x,-8.1,.28],`NCIR Grove folded board leg ${i+1}`));
  pads.push(extrude(host.body,ring(.52,.30),.06,-.36,metal(),`NCIR Grove annular solder pad ${i+1}`,[x,-8.1]));
  const shape=new THREE.Shape();shape.absarc(0,0,.48,0,Math.PI*2,false);
  const hole=new THREE.Path();hole.moveTo(-.16,-.16);hole.lineTo(-.16,.16);hole.lineTo(.16,.16);hole.lineTo(.16,-.16);hole.closePath();shape.holes.push(hole);
  fillets.push(extrude(host.body,shape,.28,-.64,solder(),`NCIR Grove solder with square leg bore ${i+1}`,[x,-8.1]));
 }
 const hit=socket.port.highlightMesh;hit.geometry.dispose();hit.geometry=new THREE.BoxGeometry(10,1,5.2);
 socket.group.userData={...socket.group.userData,source:'U028 own mechanical drawing: connector mouth 10 x 5.2, top aligns with shell Z4; centre Z1.4.',inferred:'Internal support/contact folds, footprint, solder and hidden PCB are reconstructed appearance.'};
 return {grove:socket.group,grovePort:socket.port,groveTails:tails,grovePads:pads,groveFillets:fillets};
}

export function addNCIRAssembly(host){
 const board=replaceBoard(host),sensor=sensorPackage(host),connector=groveAssembly(host);
 host.ncirAssembly={...sensor,board,...connector,dimensions:NCIR_ASSEMBLY};
}
