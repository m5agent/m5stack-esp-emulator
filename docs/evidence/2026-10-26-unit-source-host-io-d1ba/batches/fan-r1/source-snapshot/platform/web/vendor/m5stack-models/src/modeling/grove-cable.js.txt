import * as THREE from 'three';
import {Component,materials} from '../core/index.js';
import {roundedRect} from '../core/geometry.js';

// Appearance envelopes inferred from the official HY2.0-4P photos and the
// existing model mouths. These are not connector manufacturing dimensions.
export const GROVE_CABLE_GEOMETRY=Object.freeze({
  pitchMm:2,wireRadiusMm:.4,plugInsertionMm:1.2,plugExitMm:4.2,
  wireColors:Object.freeze([0x202020,0xb8201c,0xe3bb14,0xe7e6e0]),
});
const Y=new THREE.Vector3(0,1,0),X=new THREE.Vector3(1,0,0);
const {pitchMm,wireRadiusMm,plugExitMm}=GROVE_CABLE_GEOMETRY;
const SAMPLE_COUNT=96;

function finiteArray(value,length,name){
  if(!Array.isArray(value)||value.length!==length||!value.every(Number.isFinite))throw new TypeError(`${name} must contain ${length} finite numbers`);
  return value;
}
function distance(value){
  if(!Number.isFinite(value)||value<12)throw new RangeError('cableLength must be >= 12 mm');
  return value;
}
function endpoint(value){
  const node=value?.object3d??value;
  if(!node?.isObject3D)throw new TypeError('A cable endpoint must be a Port or an Object3D mating frame');
  return node;
}
function addMesh(parent,geometry,material,name,position=[0,0,0]){
  const object=new THREE.Mesh(geometry,material);object.name=name;object.position.fromArray(position);parent.add(object);return object;
}
function makePlug(name){
  const group=new THREE.Group();group.name=name;group.userData.visualFamily='grove-cable-plug';
  const plastic=materials.plastic(0xe7e8e1,{roughness:.66});
  const profile=roundedRect(8.4,2.9,.24);
  for(let i=0;i<4;i++)profile.holes.push(roundedRect(.74,.9,.09,{cx:(i-1.5)*pitchMm,cy:-.2,path:new THREE.Path(),clockwise:true}));
  const nose=new THREE.ExtrudeGeometry(profile,{depth:3.8,bevelEnabled:false,curveSegments:10});
  nose.rotateX(Math.PI/2).translate(0,2.6,0);
  addMesh(group,nose,plastic,'Grove plug four-chamber housing');
  addMesh(group,new THREE.BoxGeometry(8.4,1.6,2.9),plastic,'Grove plug wire retainer',[0,3.4,0]);
  addMesh(group,new THREE.BoxGeometry(3.8,1.8,.46),plastic,'Grove plug latch',[0,1.4,1.6]);
  const metal=materials.metal(0xb9b18e,{roughness:.43});
  for(let i=0;i<4;i++){
    const contact=addMesh(group,new THREE.BoxGeometry(.6,1.4,.08),metal,'Grove plug crimp contact',[(i-1.5)*pitchMm,.1,-.59]);
    contact.userData.pin=i+1;
  }
  return group;
}
function readFrame(node,inverse){
  node.updateWorldMatrix(true,false);
  const matrix=new THREE.Matrix4().multiplyMatrices(inverse,node.matrixWorld);
  const position=new THREE.Vector3(),quaternion=new THREE.Quaternion(),scale=new THREE.Vector3();
  matrix.decompose(position,quaternion,scale);
  return {position,quaternion,scale,matrix};
}
function perpendicular(axis,tangent){
  const result=axis.clone().addScaledVector(tangent,-axis.dot(tangent));
  if(result.lengthSq()<1e-10)result.copy(Math.abs(tangent.x)<.8?X:new THREE.Vector3(0,0,1)).addScaledVector(tangent,-result.dot(tangent));
  return result.normalize();
}
function smoothTwist(t){
  const v=THREE.MathUtils.clamp((t-.08)/.84,0,1);return v*v*(3-2*v);
}

/** A pose controller for the existing Unit assembly, in the host Port frame. */
export class UnitFrame extends Component{
  static kind='unit-frame';
  constructor({id='unitFrame'}={}){
    super({id,label:'Unit assembly pose',meta:{role:'visual-pose',space:'module-port',scope:'appearance-only'}});
    this.object3d.name='Unit assembly frame';this.inputLocal=new THREE.Vector3();
  }
  bindInput(port){
    this.inputPort=port;this.object3d.updateWorldMatrix(true,true);
    this.inputLocal.copy(this.object3d.worldToLocal(port.object3d.getWorldPosition(new THREE.Vector3())));
    return this;
  }
  setPose({position,rotation,quaternion}={}){
    if(position)finiteArray(position,3,'position');
    if(rotation)finiteArray(rotation,3,'rotation');
    if(quaternion){finiteArray(quaternion,4,'quaternion');if(quaternion.every(v=>Math.abs(v)<1e-10))throw new RangeError('quaternion must have a nonzero length');}
    const oldPosition=this.object3d.position.clone(),oldQuaternion=this.object3d.quaternion.clone();
    if(position)this.object3d.position.fromArray(position);
    if(quaternion)this.object3d.quaternion.fromArray(quaternion).normalize();
    else if(rotation)this.object3d.rotation.set(...rotation);
    try{this.host?.find('cable')?.sync();}catch(error){
      this.object3d.position.copy(oldPosition);this.object3d.quaternion.copy(oldQuaternion);throw error;
    }
    this.requestRender();return this;
  }
  /** Put the input mouth at [0,mm,0], preserving the current Unit rotation. */
  setDistance(mm){
    distance(mm);
    const inputOffset=this.inputLocal.clone().applyQuaternion(this.object3d.quaternion);
    return this.setPose({position:new THREE.Vector3(0,mm,0).sub(inputOffset).toArray()});
  }
  getState(){return {position:this.object3d.position.toArray(),quaternion:this.object3d.quaternion.toArray(),space:'module-port',inputPort:this.inputPort?.id??null};}
  handle(command){
    if(command.type==='pose'){if(command.distance!=null)this.setDistance(command.distance);else this.setPose(command);return this.getState();}
    return super.handle(command);
  }
}

/** Four physical wires and two fitted plugs; it has no bus/electrical behavior. */
export class VisualCable extends Component{
  static kind='cable';
  constructor({id='cable',source,target,slack=10,bend=[0,0,-1]}={}){
    super({id,label:'Grove cable',meta:{role:'visual-cable',connector:'grove',scope:'appearance-only'}});
    this.source=endpoint(source);this.target=endpoint(target);this._signature='';
    this.sourcePlug=makePlug('Grove source plug');this.targetPlug=makePlug('Grove Unit plug');
    this.object3d.add(this.sourcePlug,this.targetPlug);
    this.wires=GROVE_CABLE_GEOMETRY.wireColors.map((color,i)=>{
      const object=this.hit(addMesh(this.object3d,new THREE.BufferGeometry(),materials.plastic(color,{roughness:.58}),`Grove wire ${i+1}`));
      object.userData={...object.userData,visualFamily:'grove-wire',wireIndex:i};return object;
    });
    this.setOptions({slack,bend});
  }
  setOptions({slack=this.slack??10,bend=this.bend?.toArray()??[0,0,-1]}={}){
    if(!Number.isFinite(slack)||slack<0||slack>500)throw new RangeError('slack must be between 0 and 500 mm');
    finiteArray(bend,3,'bend');const vector=new THREE.Vector3(...bend);
    if(vector.lengthSq()<1e-10)throw new RangeError('bend must be a nonzero direction in the module Port frame');
    this.slack=slack;this.bend=vector.normalize();this._signature='';
    if(this.host)this.sync();this.requestRender();return this;
  }
  bind(source,target){this.source=endpoint(source);this.target=endpoint(target);this._signature='';if(this.host)this.sync();return this;}
  onMount(){this.sync();}
  sync(){
    this.object3d.updateWorldMatrix(true,false);
    const inverse=this.object3d.matrixWorld.clone().invert(),a=readFrame(this.source,inverse),b=readFrame(this.target,inverse);
    const signature=[...a.matrix.elements,...b.matrix.elements,this.slack,...this.bend.toArray()].map(v=>Math.round(v*1e8)).join(',');
    if(signature===this._signature)return false;
    const faceDistance=a.position.distanceTo(b.position);
    if(faceDistance<12-1e-6)throw new RangeError('Grove mouths must remain at least 12 mm apart');
    this.sourcePlug.position.copy(a.position);this.sourcePlug.quaternion.copy(a.quaternion);
    this.targetPlug.position.copy(b.position);this.targetPlug.quaternion.copy(b.quaternion);
    const startNormal=Y.clone().applyQuaternion(a.quaternion),endNormal=Y.clone().applyQuaternion(b.quaternion);
    const start=a.position.clone().addScaledVector(startNormal,plugExitMm),end=b.position.clone().addScaledVector(endNormal,plugExitMm);
    const chord=end.clone().sub(start),length=chord.length(),forward=chord.clone().normalize();
    const lead=THREE.MathUtils.clamp(length*.18,.5,18),middle=start.clone().lerp(end,.5).addScaledVector(this.bend,this.slack);
    const first=new THREE.CubicBezierCurve3(start,start.clone().addScaledVector(startNormal,lead),middle.clone().addScaledVector(forward,-length*.17),middle);
    const second=new THREE.CubicBezierCurve3(middle,middle.clone().addScaledVector(forward,length*.17),end.clone().addScaledVector(endNormal,lead),end);
    const point=t=>t<=.5?first.getPoint(t*2):second.getPoint((t-.5)*2);
    // Curve's finite-difference tangent nudges an endpoint off its plug row;
    // the mating normals give exact analytic end tangents.
    const tangent=t=>t<=0?startNormal.clone():t>=1?endNormal.clone().negate():t<=.5?first.getTangent(t*2).normalize():second.getTangent((t-.5)*2).normalize();
    const centers=[],tangents=[],axes=[];
    let row=perpendicular(X.clone().applyQuaternion(a.quaternion),tangent(0));
    for(let i=0;i<=SAMPLE_COUNT;i++){
      const t=i/SAMPLE_COUNT,next=tangent(t);
      if(i)row.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(tangents[i-1],next));
      row=perpendicular(row,next);centers.push(point(t));tangents.push(next);axes.push(row.clone());
    }
    const lastTangent=tangents.at(-1),desired=perpendicular(X.clone().applyQuaternion(b.quaternion),lastTangent),transported=axes.at(-1);
    const twist=Math.atan2(lastTangent.dot(transported.clone().cross(desired)),THREE.MathUtils.clamp(transported.dot(desired),-1,1));
    for(let i=0;i<=SAMPLE_COUNT;i++)axes[i].applyAxisAngle(tangents[i],twist*smoothTwist(i/SAMPLE_COUNT));
    this.wirePoints=this.wires.map((wire,index)=>{
      const points=centers.map((p,i)=>p.clone().addScaledVector(axes[i],(index-1.5)*pitchMm));
      const curve=new THREE.CatmullRomCurve3(points,false,'centripetal');
      const geometry=new THREE.TubeGeometry(curve,SAMPLE_COUNT,wireRadiusMm,8,false);
      wire.geometry.dispose();wire.geometry=geometry;return points;
    });
    this.centerPoints=centers;
    this._state={slack:this.slack,bend:this.bend.toArray(),faceDistanceMm:faceDistance,
      curveLengthMm:centers.slice(1).reduce((sum,p,i)=>sum+p.distanceTo(centers[i]),0),
      source:{position:a.position.toArray(),quaternion:a.quaternion.toArray(),outward:startNormal.toArray()},
      target:{position:b.position.toArray(),quaternion:b.quaternion.toArray(),outward:endNormal.toArray()},
      wireCount:4,plugCount:2,space:'module-port'};
    this._signature=signature;return true;
  }
  update(){return this.sync();}
  getState(){this.sync();return structuredClone(this._state);}
  handle(command){if(command.type==='cable'){this.setOptions(command);return this.getState();}return super.handle(command);}
  dispose(){super.dispose();this.source=null;this.target=null;this.wirePoints=[];this.centerPoints=[];}
}

/** Shared by all Unit wrappers without moving the existing component IDs. */
export function buildGroveModuleAssembly(host,buildUnit,{cableLength=35,unitPose,cable={}}={}){
  distance(cableLength);
  const owner=host.body,frame=new UnitFrame();owner.add(frame.object3d);
  host.body=frame.object3d;try{buildUnit(host);}finally{host.body=owner;}
  const input=host.get('grove','port');frame.bindInput(input);
  // Register the assembly frame after its child components: host disposal then
  // releases child components first, leaving only the static assembly to it.
  host.add(frame,owner);frame.setDistance(cableLength);if(unitPose)frame.setPose(unitPose);
  const visualCable=host.add(new VisualCable({...cable,id:'cable',source:owner,target:input}),owner);
  host.unitFrame=frame;host.cable=visualCable;
  return {unitFrame:frame,cable:visualCable};
}
