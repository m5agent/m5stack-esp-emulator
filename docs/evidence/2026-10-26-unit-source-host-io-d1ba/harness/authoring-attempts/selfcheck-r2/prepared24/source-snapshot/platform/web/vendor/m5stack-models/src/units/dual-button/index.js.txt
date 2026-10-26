import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {slab,mesh} from '../../modeling/parts.js';
import {physicalButton} from '../../modeling/actuators.js';
import {makeUnit,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 for(const [id,y,color]of [['blue',13,0x008ec4],['red',-1,0xc61722]]){
  const cap=new THREE.Group();cap.name=`Dual Button ${id} moving cap`;
  const outline=[[0,0],[5.35,0],[5.65,.1],[5.75,.3],[5.75,2.65],[5.65,2.92],[5.4,3],[0,3]].map(p=>new THREE.Vector2(...p));
  mesh(cap,new THREE.LatheGeometry(outline,96).rotateX(Math.PI/2),materials.plastic(color,{roughness:.58}),[0,0,0],`Dual Button ${id} full-depth cap`);
  cylinder(cap,3.4,1.6,[0,0,-.7],materials.plastic(0x252c2d)).name=`Dual Button ${id} moving stem`;
  physicalButton(host,{id,label:id,mesh:cap,position:[0,y,8],travel:.35,meta:{surfaceCenter:[0,y,11],surfaceFace:'front',dimensionsSource:'Official U025 mechanical drawing: diameter11.5, center spacing14, 12mm housing / 15mm including caps',travelSource:'Visual press estimate; no electrical switch behavior'}});
  cylinder(host.body,5.55,5.15,[0,y,3.625],materials.plastic(0x242a2b)).name=`Dual Button ${id} recessed switch body`;
  for(const x of [-4.2,4.2])for(const dy of [-3.6,3.6])slab(host.body,.7,1.4,.2,.1,[x,y+dy,1.03],materials.metal(0xada99a),[],.02).name=`Dual Button ${id} switch solder foot`;
 }
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
