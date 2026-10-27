import {addStickers} from './stickers.js';
import {makeUnit} from '../shared/CADUnit.js';
import {addEncoderAssembly} from './assembly.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{addEncoderAssembly(host);addStickers(host);});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
