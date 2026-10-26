import * as THREE from 'three';
import {Module,Component,materials} from '../../core/index.js';
import {spec} from './dimensions.js';
const SEGMENTS=72,RADIAL=24;
function validated(points){
 if(!Array.isArray(points)||points.length<3||points.length>16||points.some(p=>!Array.isArray(p)||p.length!==3||p.some(v=>!Number.isFinite(v)||Math.abs(v)>500)))throw new TypeError('Hose points must contain3–16 finite xyz millimetre coordinates within±500');
 const p=points.map(v=>[...v]);if(p[0].some(v=>v!==0)||p[1][0]!==0||p[1][2]!==0||p[1][1]<6)throw new RangeError('Hose first point must be[0,0,0] and first segment must follow+Y for at least6mm');
 for(let i=1;i<p.length;i++)if(new THREE.Vector3(...p[i]).distanceTo(new THREE.Vector3(...p[i-1]))<1)throw new RangeError('Hose consecutive points must be at least1mm apart');return p;
}
function tube(points){
 const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)),false,'centripetal'),frames=curve.computeFrenetFrames(SEGMENTS,false),vertices=[],normals=[],index=[],centers=[];
 for(let i=0;i<=SEGMENTS;i++){
  const center=curve.getPointAt(i/SEGMENTS);centers.push(center.toArray());
  for(const radius of[spec.hose.outerDiameterMm/2,spec.hose.innerDiameterMm/2])for(let j=0;j<=RADIAL;j++){
   const a=j/RADIAL*Math.PI*2,n=frames.normals[i].clone().multiplyScalar(Math.cos(a)).addScaledVector(frames.binormals[i],Math.sin(a)),v=center.clone().addScaledVector(n,radius);vertices.push(...v.toArray());normals.push(...n.multiplyScalar(radius===spec.hose.outerDiameterMm/2?1:-1).toArray());
  }
 }
 const row=(RADIAL+1)*2;for(let i=0;i<SEGMENTS;i++)for(let j=0;j<RADIAL;j++)for(let side=0;side<2;side++){
  const a=i*row+side*(RADIAL+1)+j,b=a+1,c=a+row,d=c+1;if(side===0)index.push(a,b,c,b,d,c);else index.push(a,c,b,b,c,d);
 }
 // Annular end faces close the wall while preserving the continuous open lumen.
 for(const i of[0,SEGMENTS])for(let j=0;j<RADIAL;j++){
  const a=i*row+j,b=a+1,c=a+RADIAL+1,d=c+1;if(i===0)index.push(a,c,b,b,c,d);else index.push(a,b,c,b,d,c);
 }
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));geometry.setIndex(index);geometry.computeBoundingBox();geometry.computeBoundingSphere();return{geometry,centers,length:curve.getLength()};
}
export class HoseShape extends Component{
 static kind='hose-shape';
 constructor({points=spec.hose.points}={}){
  super({id:'shape',label:'Externally posed flexible hose',meta:{role:'visual-hose-shape',space:'module-port',scope:'External hollow-tube geometry only; no fluid, pumping, pressure, moisture, motor, sensor, power or electrical state',dimensionsInferred:true}});
  this.tube=new THREE.Mesh(new THREE.BufferGeometry(),materials.plastic(0xdfe2dd,{roughness:.51,transparent:true,opacity:.56,depthWrite:true}));const annulus=new THREE.Shape();annulus.absarc(0,0,3,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,2.25,0,Math.PI*2,false);annulus.holes.push(bore);this.sleeve=new THREE.Mesh(new THREE.ExtrudeGeometry(annulus,{depth:5.4,bevelEnabled:false,curveSegments:48}).rotateX(-Math.PI/2),this.tube.material);this.sleeve.position.y=-5.4;this.sleeve.name='Watering fixed soft-tube stretched seating sleeve over real pump nipple';this.object3d.add(this.sleeve);this.tube.name='Watering supplied soft tube with genuine inner and outer walls and two open ends';this.object3d.add(this.tube);this.setPoints(points);
 }
 setPoints(points){const next=validated(points),built=tube(next);this.tube.geometry.dispose();this.tube.geometry=built.geometry;this.points=next;this.centerPoints=built.centers;this.lengthMm=built.length;this.requestRender();return this;}
 getState(){return{points:this.points.map(p=>[...p]),outerDiameterMm:spec.hose.outerDiameterMm,innerDiameterMm:spec.hose.innerDiameterMm,wallMm:spec.hose.wallMm,insertionMm:5.4,seatingInnerDiameterMm:4.5,curveLengthMm:this.lengthMm,space:'module-port',dimensionsInferred:true};}
 handle(cmd){if(cmd.type==='shape'){this.setPoints(cmd.points);return this.getState();}return super.handle(cmd);}
}
/** One of the two supplied tubes, attached independently to inlet or outlet. */
export class Hose extends Module{
 static meta={id:'m5stack.unit.watering.hose',name:'Watering supplied flexible tube',connector:'silicone-tube-4mm',dimensionsInferred:true};
 build(options={}){this.shape=this.add(new HoseShape(options));}
}
export default Hose;
