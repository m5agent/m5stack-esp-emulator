import {addStickers} from './stickers.js';
import {makeUnit} from '../shared/CADUnit.js';
import {addOpticalAssembly} from './optical-assembly.js';
import {addHeartGrove} from './grove-assembly.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{addHeartGrove(host);addOpticalAssembly(host);addStickers(host);});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
