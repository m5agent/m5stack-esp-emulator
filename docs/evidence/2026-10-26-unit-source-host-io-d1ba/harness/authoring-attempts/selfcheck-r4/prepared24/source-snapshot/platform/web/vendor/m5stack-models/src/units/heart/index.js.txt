import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
slab(host.body,2.7,4.8,.15,.2,[0,8,3.78],materials.glossy(0x181d24,{roughness:.2}),[],.03);for(const y of [7.1,8.9])slab(host.body,1.4,1.2,.04,.15,[0,y,3.95],materials.glossy(y<8?0x38242a:0x262a35),[],.01);
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
