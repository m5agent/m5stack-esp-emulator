import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 addStickers(host);
slab(host.body,4.4,2.6,.25,.4,[0,8,3.7],materials.plastic(0x171a23),[],.04);for(const x of [-1,1])disc(host.body,.65,[x,8,3.97],materials.glossy(0x292039,{roughness:.13}));
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
