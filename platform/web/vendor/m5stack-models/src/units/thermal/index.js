import {makeUnit} from '../shared/CADUnit.js';
import {addThermalAssembly} from './assembly.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
import {addStickers} from './stickers.js';
spec.artwork=void 0;
const models=makeUnit(spec,data,host=>{addThermalAssembly(host);addStickers(host);});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
