import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {slab,mesh} from '../../modeling/parts.js';
import {makeUnit} from '../shared/CADUnit.js';
import {unitPcb} from '../shared/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';

const models=makeUnit(spec,data,host=>{
 const old=host.body.getObjectByName('Unit PCB');old.removeFromParent();old.geometry.dispose();old.material.dispose();
 unitPcb(host.body,{h:24});
 // A physical passive acoustic package backs the five original shell vents.
 // Exact concealed package dimensions are photo-derived visual approximations.
 const acoustic=slab(host.body,12,6.7,1.7,1.0,[0,8.0,1.05],materials.plastic(0x17201d,{roughness:.91}),[],.08);acoustic.name='Buzzer acoustic package';
 const diaphragm=mesh(host.body,new THREE.CircleGeometry(3.4,48),materials.plastic(0x2f3932,{roughness:.86}),[0,7.8,2.76],'Buzzer recessed diaphragm');
 for(const x of [-3.2,3.2])mesh(host.body,new THREE.BoxGeometry(.32,.65,.45),materials.metal(0xabb3a8,{roughness:.5}),[x,7.8,.95],'Buzzer package lead');
 addStickers(host);
});
export const Model=models.Model;
export const GroveModule=models.GroveModule;
export default Model;
