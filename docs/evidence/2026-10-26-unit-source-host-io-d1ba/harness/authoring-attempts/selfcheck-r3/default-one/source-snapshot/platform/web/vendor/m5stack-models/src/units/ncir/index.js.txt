import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
can(host.body,{y:8,z:4,r:4.5,h:.58,lens:0x17232e});
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
