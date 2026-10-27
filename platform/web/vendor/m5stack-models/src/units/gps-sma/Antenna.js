import * as THREE from 'three';
import {Module,Component,materials} from '../../core/index.js';
import {mesh,slab} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import {addAntennaSticker} from './stickers.js';
const tau=Math.PI*2,Y=new THREE.Vector3(0,1,0);
function ring(parent,outer,inner,depth,y,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);const h=new THREE.Path();h.absarc(0,0,inner,0,tau,false);s.holes.push(h);return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2),material,[0,y,0],name);}
function validate(points){
 if(!Array.isArray(points)||points.length<3||points.length>32||points.some(p=>!Array.isArray(p)||p.length!==3||p.some(v=>!Number.isFinite(v)||Math.abs(v)>1500)))throw new TypeError('Antenna points require3–32 finite xyz millimetre coordinates within±1500');
 const next=points.map(p=>[...p]);if(next[0].some(v=>v!==0)||next[1][0]!==0||next[1][2]!==0||next[1][1]<18)throw new RangeError('First antenna point must be[0,0,0];first segment must follow+Y for at least18mm past fixed SMA strain relief');
 for(let i=1;i<next.length;i++)if(new THREE.Vector3(...next[i]).distanceTo(new THREE.Vector3(...next[i-1]))<2)throw new RangeError('Antenna consecutive points must be at least2mm apart');return next;
}
/** External visual curve and cable-entry-aligned puck, in the SMA port frame. */
export class AntennaShape extends Component{
 static kind='antenna-shape';
 constructor({points=spec.antenna.points}={}){
  super({id:'shape',label:'GPS SMA cable and active antenna pose',meta:{role:'visual-cable-shape',space:'module-port',scope:'External coax curve and terminal puck pose only;no RF,GNSS,NMEA,position,voltage,electrical or cable physics',dimensionsInferred:true}});
  this.cable=new THREE.Mesh(new THREE.BufferGeometry(),materials.plastic(0x171b19,{roughness:.78}));this.cable.name='GPS SMA supplied coax externally posed cable jacket';this.object3d.add(this.cable);
  this.puck=new THREE.Group();this.puck.name='GPS SMA supplied active38×36×13mm puck follows cable terminal';this.object3d.add(this.puck);
  const black=materials.plastic(0x272a26,{roughness:.83});
  const back=slab(this.puck,38,36,4,8,[0,18,-6.5],black,[],.35);back.name='GPS SMA active antenna puck closed molded lower case';
  const front=slab(this.puck,38,36,9,8,[0,18,-2.5],black,[],.35);front.name='GPS SMA active antenna puck closed rounded radome';
  const seam=slab(this.puck,38,36,.18,8,[0,18,-2.54],materials.plastic(0x3f423b,{roughness:.9}),[],.02);seam.name='GPS SMA antenna real case seam';
  const relief=mesh(this.puck,new THREE.CylinderGeometry(2.3,2.5,4,48),black,[0,-1.8,0],'GPS SMA antenna puck retained cable-entry strain relief');
  this.puckParts={back,front,seam,relief};this.setPoints(points);
 }
 setPoints(points){
  const next=validate(points),curve=new THREE.CatmullRomCurve3([new THREE.Vector3(...spec.antenna.cableStartMm),...next.slice(1).map(p=>new THREE.Vector3(...p))],false,'centripetal'),geometry=new THREE.TubeGeometry(curve,384,spec.antenna.cableOuterDiameterMm/2,12,false),end=curve.getPoint(1),tangent=curve.getTangent(1).normalize(),quaternion=new THREE.Quaternion().setFromUnitVectors(Y,tangent);
  this.cable.geometry.dispose();this.cable.geometry=geometry;this.points=next;this.curveLengthMm=curve.getLength();this.puck.position.copy(end);this.puck.quaternion.copy(quaternion);this.requestRender();return this;
 }
 getState(){return{points:this.points.map(p=>[...p]),space:'module-port',nominalCableLengthMm:1000,curveLengthMm:this.curveLengthMm,cableOuterDiameterMm:spec.antenna.cableOuterDiameterMm,cableStartMm:[...spec.antenna.cableStartMm],puckMm:[...spec.antenna.puckMm],puckCableEntryPositionMm:this.puck.position.toArray(),puckQuaternion:this.puck.quaternion.toArray(),dimensionsInferred:true};}
 handle(cmd){if(cmd.type==='shape'){this.setPoints(cmd.points);return this.getState();}return super.handle(cmd);}
}
/** Exact U190 supplied cabled SMA male active puck. No antenna hinge exists. */
export class Antenna extends Module{
 static meta={id:'m5stack.unit.gps-sma.antenna',name:'GPS SMA supplied active cabled puck antenna',sku:'U190 accessory',connector:'sma-female',physicalConnector:'sma-male',nominalCableLengthMm:1000};
 build(options={}){
  const fixed=new THREE.Group();fixed.name='GPS SMA antenna fixed true male coupling and straight strain relief';this.body.add(fixed);
  const gold=materials.metal(0xd0bc66,{roughness:.38}),ptfe=materials.plastic(0xe5e0c6,{roughness:.75}),dark=materials.plastic(0x191e1a,{roughness:.81});
  const nut=ring(fixed,4,3.19,7,-6.5,gold,'GPS SMA antenna male open coupling nut with true internally threaded bore');
  const hex=new THREE.Shape();for(let i=0;i<6;i++){const a=i*tau/6+Math.PI/6;i?hex.lineTo(Math.cos(a)*4.2,Math.sin(a)*4.2):hex.moveTo(Math.cos(a)*4.2,Math.sin(a)*4.2);}hex.closePath();const hole=new THREE.Path();hole.absarc(0,0,3.19,0,tau,false);hex.holes.push(hole);const hexBody=mesh(fixed,new THREE.ExtrudeGeometry(hex,{depth:5,bevelEnabled:false,curveSegments:64}).rotateX(-Math.PI/2),gold,[0,-4.5,0],'GPS SMA antenna male coupling retained hollow hex shoulder');
  class Thread extends THREE.Curve{getPoint(t,target=new THREE.Vector3()){const a=t*tau*7;return target.set(Math.cos(a)*3.23,-5.9+t*5.3,Math.sin(a)*3.23);}}
  const thread=mesh(fixed,new THREE.TubeGeometry(new Thread(),448,.06,6,false),gold,[0,0,0],'GPS SMA antenna male real internal helical thread');
  const dielectric=ring(fixed,3.18,.35,1.2,.15,ptfe,'GPS SMA antenna actual centre-pin dielectric');
  const pin=mesh(fixed,new THREE.CylinderGeometry(.22,.22,3.5,32),gold,[0,-1.45,0],'GPS SMA antenna actual male exposed centre pin');
  const pinTip=mesh(fixed,new THREE.ConeGeometry(.22,.35,32).rotateX(Math.PI),gold,[0,-3.375,0],'GPS SMA antenna tapered male contact tip');
  const crimp=mesh(fixed,new THREE.CylinderGeometry(2.2,2.2,4.5,48),gold,[0,2.75,0],'GPS SMA antenna retained coax crimp ferrule');
  const relief=mesh(fixed,new THREE.CylinderGeometry(1.7,2.25,5.2,48),dark,[0,7.4,0],'GPS SMA antenna fixed straight cable strain relief');
  const shape=this.add(new AntennaShape(options));const savedPosition=shape.puck.position.clone(),savedQuaternion=shape.puck.quaternion.clone();shape.puck.position.set(0,0,0);shape.puck.quaternion.identity();this.unitStickers=addAntennaSticker(this,shape.puckParts.front);shape.puck.position.copy(savedPosition);shape.puck.quaternion.copy(savedQuaternion);
  this.antennaAssembly={fixed,nut,hexBody,thread,dielectric,pin,pinTip,crimp,relief,shape};
 }
}
export default Antenna;
