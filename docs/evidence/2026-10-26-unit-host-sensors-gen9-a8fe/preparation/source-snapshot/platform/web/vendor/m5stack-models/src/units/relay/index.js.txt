import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
slab(host.body,16,11,3.9,.8,[0,2,0],materials.plastic(0xdd861b,{roughness:.75}),[],.25);slab(host.body,16,7.5,6,.5,[0,13.5,-2],materials.plastic(0xf06b1d,{roughness:.75}),[],.2);for(const x of [-5,0,5]){disc(host.body,1.8,[x,13.5,4.03],materials.metal(0xa8a9a2));slab(host.body,2.2,.3,.03,.1,[x,13.5,4.05],materials.cavity(),[],.008);}textMark(host.body,'Unit Relay',16,3,[0,21.1,4.03],{size:1.7,color:'#238cb4'});
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
