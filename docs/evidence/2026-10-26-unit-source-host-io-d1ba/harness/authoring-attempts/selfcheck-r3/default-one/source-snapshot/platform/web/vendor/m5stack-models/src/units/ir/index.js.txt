import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh,disc} from '../../modeling/parts.js';
import {makeUnit,cylinder} from '../shared/CADUnit.js';
import {unitPcb} from '../shared/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';

const models=makeUnit(spec,data,host=>{
 // This taller Grove mouth needs board clearance around the connector, instead
 // of the full rectangular default board crossing the insertion cavity.
 const originalBoard=host.body.getObjectByName('Unit PCB');originalBoard.removeFromParent();originalBoard.geometry.dispose();originalBoard.material.dispose();
 unitPcb(host.body,{h:spec.size[1]});
 const silver=materials.metal(0xb9bebc,{roughness:.37});
 for(const optic of spec.optics){
  const receiver=optic.id==='receiver';
  const group=new THREE.Group();group.position.set(optic.x,optic.y,0);group.name=`IR ${optic.id} package`;host.body.add(group);
  cylinder(group,2.35,.65,[0,0,1.25],materials.plastic(receiver?0x1b2223:0x8b9695,{roughness:.7}));
  const dome=new THREE.SphereGeometry(optic.r,40,20,0,Math.PI*2,0,Math.PI/2).rotateX(Math.PI/2);
  mesh(group,dome,materials.glossy(receiver?0x151b1d:0xd7e2df,{roughness:receiver?.22:.14,transparent:!receiver,opacity:receiver?1:.66,depthWrite:receiver}),[0,0,1.5],`IR ${optic.id} optical dome`);
  if(receiver){disc(group,.75,[0,0,3.82],materials.glossy(0x4c5450,{roughness:.24}));}
  else{
   cylinder(group,1.55,.25,[0,0,2.2],silver);
   mesh(group,new THREE.BoxGeometry(.8,.65,.16),materials.plastic(0xe5e4dc,{roughness:.38}),[0,0,2.6],'IR LED die');
  }
  for(const x of [-.65,.65])mesh(group,new THREE.BoxGeometry(.32,.32,1.5),silver,[x,0,.6],'IR optical package lead');
 }
});
export const Model=models.Model;
export const GroveModule=models.GroveModule;
export default Model;
