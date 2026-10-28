import*as THREE from'three';import{Module,VisualJoint,materials}from'../../core/index.js';import{mesh}from'../../modeling/parts.js';import{spec}from'./dimensions.js';
const tau=Math.PI*2;
function ring(parent,outer,inner,depth,y,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);const h=new THREE.Path();h.absarc(0,0,inner,0,tau,false);s.holes.push(h);const g=new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:48}).rotateX(-Math.PI/2);return mesh(parent,g,material,[0,y,0],name);}
/** Supplied U110 hinged rubber antenna; estimated100mm envelope,not a measured length. */
export class Antenna extends Module{
 // connector names the accepting Port family, as required by Port.accepts.
 static meta={id:'m5stack.unit.zigbee.antenna',name:'U110 supplied hinged SMA antenna',sku:'U110 accessory',connector:'sma-female',physicalConnector:'sma-male',estimatedLengthMm:100,dimensionsInferred:true};
 build({angleDeg=0}={}){
  const fixed=new THREE.Group();fixed.name='ZigBee antenna fixed SMA male coupling and hinge fork';this.body.add(fixed);
  const black=materials.plastic(0x171b18,{roughness:.85}),rib=materials.plastic(0x252a25,{roughness:.84}),metal=materials.metal(0xb9b6a4,{roughness:.4}),gold=materials.metal(0xc3ac55,{roughness:.39}),ptfe=materials.plastic(0xe3e1ce,{roughness:.76});
  const nut=ring(fixed,4.8,3.19,9.45,-6.45,black,'ZigBee antenna real open coupling nut');
  const lip=ring(fixed,4.25,3.16,.55,-6.5,metal,'ZigBee antenna SMA male open metal mouth');
  for(let i=0;i<44;i++){const a=i*tau/44;const o=mesh(fixed,new THREE.BoxGeometry(.15,8.2,.12),rib,[Math.cos(a)*4.76,-1.6,Math.sin(a)*4.76],'ZigBee antenna molded coupling knurl');o.rotation.y=-a;}
  class InnerThread extends THREE.Curve{getPoint(t,target=new THREE.Vector3()){const a=t*tau*7;return target.set(Math.cos(a)*3.235,-5.9+t*5.2,Math.sin(a)*3.235);}}
  const thread=mesh(fixed,new THREE.TubeGeometry(new InnerThread(),448,.06,6,false),metal,[0,0,0],'ZigBee antenna SMA male internal helical thread');
  const carrier=ring(fixed,3.18,.35,1.3,.2,ptfe,'ZigBee antenna male centre dielectric');
  const pin=mesh(fixed,new THREE.CylinderGeometry(.22,.22,3.5,32),gold,[0,-1.45,0],'ZigBee antenna actual exposed SMA centre pin');
  const pinTip=mesh(fixed,new THREE.ConeGeometry(.22,.35,32).rotateX(Math.PI),gold,[0,-3.375,0],'ZigBee antenna tapered male contact tip');
  const collar=mesh(fixed,new THREE.CylinderGeometry(3.8,4.0,9.5,48),black,[0,7.75,0],'ZigBee antenna fixed rubber neck');
  const cheeks=[];for(const sign of[-1,1])cheeks.push(mesh(fixed,new THREE.CylinderGeometry(3.8,3.8,1.2,48).rotateZ(Math.PI/2),black,[sign*2.9,13,0],'ZigBee antenna fixed hinge cheek'));
  const axle=mesh(fixed,new THREE.CylinderGeometry(1.05,1.05,7.15,32).rotateZ(Math.PI/2),rib,[0,13,0],'ZigBee antenna retained hinge axle');
  const moving=new THREE.Group();moving.name='ZigBee antenna hinged rubber radome';
  const knuckle=mesh(moving,new THREE.CylinderGeometry(3.25,3.25,4.4,48).rotateZ(Math.PI/2),black,[0,0,0],'ZigBee antenna moving hinge knuckle');
  const lower=mesh(moving,new THREE.CylinderGeometry(3.7,3.5,15.5,48),black,[0,7.75,0],'ZigBee antenna lower radome shoulder');
  const rod=mesh(moving,new THREE.CylinderGeometry(2.9,3.7,62.1,48),black,[0,46.55,0],'ZigBee antenna tapered solid rubber rod');
  const tip=mesh(moving,new THREE.SphereGeometry(2.9,40,20,0,tau,0,Math.PI/2),black,[0,77.6,0],'ZigBee antenna rounded closed rubber tip');
  // Estimated100mm straight envelope: pivotY13 + moving tipY80.5 - mouthY(-6.5).
  for(const y of[15.6,73.3])mesh(moving,new THREE.TorusGeometry(y<20?3.68:2.95,.07,6,48).rotateX(Math.PI/2),rib,[0,y,0],'ZigBee antenna molded radome seam');
  const tilt=this.add(new VisualJoint({id:'tilt',label:'Antenna physical hinge angle',position:spec.antenna.pivot,axis:spec.antenna.axis,limitsDeg:spec.antenna.limitsDeg,meta:{visualRangeDeg:[0,90],rangeEvidence:spec.antenna.rangeEvidence,scope:'One real radome hinge only; no automatic sweep, SMA unscrewing, continuous spin, RF field, gain, frequency or electrical behavior'}}));tilt.object3d.add(moving);tilt.set({angleDeg});
  this.antennaAssembly={fixed,nut,lip,thread,carrier,pin,pinTip,collar,cheeks,axle,moving,knuckle,lower,rod,tip,tilt};
 }
}
