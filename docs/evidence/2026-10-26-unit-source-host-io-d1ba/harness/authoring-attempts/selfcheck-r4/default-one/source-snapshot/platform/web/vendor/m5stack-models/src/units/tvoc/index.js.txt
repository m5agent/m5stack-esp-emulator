import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
textMark(host.body,'TVOC / eCO2',18,3,[0,-6,4.025],{size:1.65,color:'#188bbc'});
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
