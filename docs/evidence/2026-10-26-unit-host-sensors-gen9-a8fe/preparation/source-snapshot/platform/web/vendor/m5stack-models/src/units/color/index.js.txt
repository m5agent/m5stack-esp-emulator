import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
slab(host.body,9,4,.1,1.8,[0,8,3.75],materials.plastic(0x252c30),[],.02);slab(host.body,3.1,3.1,.1,.3,[0,8,3.87],materials.glossy(0x211e32,{roughness:.15}),[],.02);for(const x of [-3.4,3.4])slab(host.body,1.2,1.6,.1,.2,[x,8,3.87],materials.plastic(0xe4dfb4),[],.02);
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
