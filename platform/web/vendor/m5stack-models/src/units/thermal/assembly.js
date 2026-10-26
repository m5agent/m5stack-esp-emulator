import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh} from '../../modeling/parts.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';

const pinPitchRadius=5.84/2;
// Melexis Fig2 is a bottom view with the reference tab pointing up. Mirror X
// to express that drawing in this library's front-view engineering XY frame.
const pins=[['SCL',4,112.5],['SDA',1,67.5],['GND',3,247.5],['VDD',2,292.5]].map(([name,pin,angle])=>{
 const a=angle*Math.PI/180,bottomView=[pinPitchRadius*Math.cos(a),pinPitchRadius*Math.sin(a)];
 return Object.freeze({name,pin,bottomView:Object.freeze(bottomView),position:Object.freeze([-bottomView[0],8+bottomView[1]])});
});

export const THERMAL_ASSEMBLY=Object.freeze({
 centre:Object.freeze([0,8]),bodyRadius:4.60,nominalBodyRadius:4.65,bodyRadiusTolerance:.075,
 bodyBottom:-.25,bodyTop:4.6,blackBodyHeight:4.85,topChamfer:.5,
 headerRadius:4.57,headerBottom:-1.1,headerTabSpan:10.03,headerTabWidth:.8,
 headerStepZ:-.85,headerNeckRadius:4.45,boardBottom:-1.9,boardTop:-1.1,
 windowRadius:1.3,windowBottom:3.36,windowTop:3.48,coneMouthRadius:3.55,
 coneSeatRadius:1.52,coneSeatZ:3.58,recessDepth:1.12,pinRadius:.225,pinPitchRadius,
 mountedLeadBottom:-2.30,pins:Object.freeze(pins),
 source:'M5 U016 dimension drawing; Melexis MLX90640 Rev12 p6 and p57 Fig29 (110 degree package).',
 radiusChoice:'Rendered radius 4.60 is within the specified nominal 4.65 +/-0.075 mm manufacturing range and clears the original polygonal shell aperture.',
 inferred:'Cone mouth/depth and small seat steps follow the manufacturer illustration and U016 photographs, not specified mechanical dimensions. Header step split, PCB outline/thickness/Z, zero package yaw, clipped leads and solder are assembled appearance inferences.',
});

const metal=()=>materials.metal(0xada78a,{roughness:.46});
const solder=()=>materials.metal(0xa9adad,{roughness:.4});
const extrusion=shape=>new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:32});
function circleHole(shape,x,y,r,clockwise=true){const hole=new THREE.Path();hole.absarc(x,y,r,0,Math.PI*2,clockwise);shape.holes.push(hole);}
function ring(outer,inner){const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);circleHole(shape,0,0,inner);return shape;}
function extrude(parent,shape,depth,z,material,name,xy=[0,0]){
 const geometry=new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32});
 return mesh(parent,geometry,material,[...xy,z],name);
}
function cylinder(parent,r,bottom,top,material,name,xy=[0,0]){
 return mesh(parent,new THREE.CylinderGeometry(r,r,top-bottom,96).rotateX(Math.PI/2),material,[...xy,(bottom+top)/2],name);
}

function replaceBoard(host){
 const old=host.body.getObjectByName('Unit PCB');
 if(!old?.isMesh)throw new Error('Thermal requires its original board before reconstruction');
 // Conservative outline inside the U016 cavity. Boss clearances open into
 // the outside contour; the centre boss and every lead have actual bores.
 const shape=new THREE.Shape();shape.moveTo(-5.4,13.4);shape.lineTo(5.4,13.4);shape.lineTo(9.4,9.4);shape.lineTo(9.4,.2);shape.lineTo(8,.2);
 shape.absarc(8,-4,4.2,Math.PI/2,Math.PI*1.5,false);shape.lineTo(9.4,-8.2);shape.lineTo(9.4,-9.4);shape.lineTo(5.4,-13.4);shape.lineTo(5.3,-13.4);shape.lineTo(5.3,-8.85);shape.lineTo(-5.3,-8.85);shape.lineTo(-5.3,-13.4);shape.lineTo(-5.4,-13.4);shape.lineTo(-9.4,-9.4);shape.lineTo(-9.4,-8.2);shape.lineTo(-8,-8.2);
 shape.absarc(-8,-4,4.2,Math.PI*1.5,Math.PI*2.5,false);shape.lineTo(-9.4,.2);shape.lineTo(-9.4,9.4);shape.lineTo(-5.4,13.4);shape.closePath();
 // The existing outer contour is clockwise; PCB bores must face inward.
 circleHole(shape,0,-4,3,false);
 for(const pin of pins)circleHole(shape,...pin.position,.35,false);
 for(const x of [-3,-1,1,3])circleHole(shape,x,-8.4,.30,false);
 const material=old.material;old.removeFromParent();old.geometry.dispose();
 const board=mesh(host.body,extrusion(shape),material,[0,0,THERMAL_ASSEMBLY.boardBottom],'Thermal PCB with open boss and Grove relief');
 board.userData={source:'Conservative U016 native-cavity reconstruction',zMm:[-1.9,-1.1],sideReliefRadiusMm:4.2,centreBoreRadiusMm:3,groveNotchHalfWidthMm:5.3,drillRadiusMm:{sensor:.35,grove:.30},inferred:'Board outline, thickness and placement are assembly inferences; header underside seats directly on board top.'};
 host.thermalBoard=board;host.parts.pcb=board;return board;
}

function sensorPackage(host){
 const d=THERMAL_ASSEMBLY,xy=d.centre;
 // One closed annular solid: outside wall, real 45 degree edge chamfer,
 // recessed cone, short aperture seat and the inside wall down to its base.
 const profile=[[d.windowRadius,d.bodyBottom],[d.bodyRadius,d.bodyBottom],[d.bodyRadius,d.bodyTop-d.topChamfer],[d.bodyRadius-d.topChamfer,d.bodyTop],[d.coneMouthRadius,d.bodyTop],[d.coneSeatRadius,d.coneSeatZ],[1.43,d.coneSeatZ],[1.43,d.windowTop],[d.windowRadius,d.windowTop],[d.windowRadius,d.bodyBottom]].map(p=>new THREE.Vector2(...p));
 const body=mesh(host.body,new THREE.LatheGeometry(profile,128).rotateX(Math.PI/2),materials.plastic(0x181c26,{roughness:.44}),[...xy,0],'Thermal MLX90640 black body with recessed cone');
 body.userData={variant:'MLX90640 110 x 75 degree TO39',source:d.source,nominalOuterDiameterMm:9.3,renderedOuterDiameterMm:9.2,radiusChoice:d.radiusChoice,blackBodyZMm:[d.bodyBottom,d.bodyTop],topOuterChamferMm:.5,centralApertureDiameterMm:2.6,recess:{mouthRadiusMm:d.coneMouthRadius,coneSeatZMm:d.coneSeatZ,windowTopZMm:d.windowTop,depthMm:d.recessDepth,source:'Visual inference from Fig29 illustration and official U016 gallery 1/4/6; not a dimensioned recess depth.'}};
 const window=cylinder(host.body,d.windowRadius,d.windowBottom,d.windowTop,materials.glossy(0x252936,{roughness:.26}),'Thermal closed recessed optical window',xy);
 window.userData={apertureDiameterMm:2.6,source:'Melexis Fig29 central diameter; thickness and axial recess are appearance inferences.',scope:'Passive opaque optical appearance; no emission, temperature values or generated image.'};

 const r=d.headerRadius,half=d.headerTabWidth/2,joinY=Math.sqrt(r*r-half*half),endY=d.headerTabSpan-r;
 const flange=new THREE.Shape();flange.moveTo(half,joinY);flange.lineTo(half,endY);flange.lineTo(-half,endY);flange.lineTo(-half,joinY);flange.absarc(0,0,r,Math.atan2(joinY,-half),Math.PI*2+Math.atan2(joinY,half),false);flange.closePath();
 const neck=new THREE.Shape();neck.absarc(0,0,d.headerNeckRadius,0,Math.PI*2,false);
 for(const pin of pins){const x=pin.position[0],y=pin.position[1]-8;circleHole(flange,x,y,.56);circleHole(neck,x,y,.56);}
 const header=extrude(host.body,flange,d.headerStepZ-d.headerBottom,d.headerBottom,metal(),'Thermal TO39 drilled metal header and reference tab',xy);
 header.userData={radiusMm:r,tabWidthMm:d.headerTabWidth,tabEnvelopeMm:d.headerTabSpan,bottomZMm:d.headerBottom,source:'Melexis Fig29 R4.57, 0.80 tab, 10.03 envelope; yaw and stepped thickness distribution inferred.'};
 const headerNeck=extrude(host.body,neck,d.bodyBottom-d.headerStepZ,d.headerStepZ,metal(),'Thermal TO39 drilled upper header seal',xy);
 headerNeck.userData={inferred:'Concealed upper seal radius and division of the dimensioned 0.85 mm package-base envelope.'};
 const leads=[],insulators=[],pads=[],fillets=[];
 for(const pin of pins){
  const [x,y]=pin.position;
  const seal=extrude(host.body,ring(.56,d.pinRadius),d.bodyBottom-d.headerBottom,d.headerBottom,materials.plastic(0x353a34,{roughness:.72}),`Thermal ${pin.name} insulating feedthrough`,[x,y]);insulators.push(seal);
  const lead=cylinder(host.body,d.pinRadius,d.mountedLeadBottom,d.bodyBottom,metal(),`Thermal ${pin.name} clipped TO39 lead`,[x,y]);
  lead.userData={pin:pin.pin,name:pin.name,bottomViewMm:[...pin.bottomView],modelFrontViewXYMm:[x,y],viewTransform:'Front X = -bottom-view X; front Y = 8 + bottom-view Y; reference tab chosen toward +Y.',source:'Fig29 pitch circle 5.84 and Fig2 pin names; package yaw and installed cut length are inferred.',rawUntrimmedLengthMm:6,mountedBottomZMm:d.mountedLeadBottom};leads.push(lead);
  const pad=extrude(host.body,ring(.62,.35),.06,d.boardBottom-.06,metal(),`Thermal ${pin.name} annular solder pad`,[x,y]);pads.push(pad);
  const filletProfile=[[d.pinRadius,-2.20],[.28,-2.20],[.56,-1.98],[.56,-1.94],[.35,-1.94],[.35,-2.05],[d.pinRadius,-2.15],[d.pinRadius,-2.20]].map(p=>new THREE.Vector2(...p));
  const fillet=mesh(host.body,new THREE.LatheGeometry(filletProfile,48).rotateX(Math.PI/2),solder(),[x,y,0],`Thermal ${pin.name} annular solder fillet`);fillet.userData={inferred:'Clipped through-hole solder appearance, not a measured production joint.'};fillets.push(fillet);
 }
 return {body,header,headerNeck,window,leads,insulators,pads,fillets};
}

function groveAssembly(host){
 const grove=refineOpenTopGrove(host,'thermal'),tails=[],pads=[],fillets=[];
 // Contacts continue through the recessed support to a folded tail, then
 // through the drilled PCB. Only the short front contact is exposed in-mouth.
 for(const [i,x]of [-3,-1,1,3].entries()){
  tails.push(mesh(host.body,new THREE.BoxGeometry(.32,5.4,.32),metal(),[x,-11.1,1.25],`Thermal Grove concealed contact tail ${i+1}`));
  tails.push(mesh(host.body,new THREE.BoxGeometry(.32,.32,3.55),metal(),[x,-8.4,-.525],`Thermal Grove folded board leg ${i+1}`));
  pads.push(extrude(host.body,ring(.52,.30),.06,-1.96,metal(),`Thermal Grove annular solder pad ${i+1}`,[x,-8.4]));
  const filletShape=new THREE.Shape();filletShape.absarc(0,0,.48,0,Math.PI*2,false);
  const squareBore=new THREE.Path();squareBore.moveTo(-.16,-.16);squareBore.lineTo(-.16,.16);squareBore.lineTo(.16,.16);squareBore.lineTo(.16,-.16);squareBore.closePath();filletShape.holes.push(squareBore);
  const fillet=extrude(host.body,filletShape,.26,-2.20,solder(),`Thermal Grove annular solder fillet ${i+1}`,[x,-8.4]);
  fillet.userData={outerRadiusMm:.48,squareBoreMm:[.32,.32],zMm:[-2.20,-1.94],inferred:'Concealed solder appearance with a real square bore contacting the folded leg; upper face joins the existing solder pad.'};fillets.push(fillet);
 }
 const hit=grove.port.highlightMesh;hit.geometry.dispose();hit.geometry=new THREE.BoxGeometry(10,1,5.2);
 grove.group.userData={...grove.group.userData,source:'U016 own dimension drawing: 10 x 5.2 mm; front top z4, CAD bay floor z-1.2.',inferred:'Internal support, contact folds, drilled tail row and solder follow assembled appearance.'};
 return {grove:grove.group,grovePort:grove.port,groveTails:tails,grovePads:pads,groveFillets:fillets};
}

export function addThermalAssembly(host){
 const board=replaceBoard(host),sensor=sensorPackage(host),connector=groveAssembly(host);
 host.thermalAssembly={...sensor,board,...connector,dimensions:THERMAL_ASSEMBLY};
}
