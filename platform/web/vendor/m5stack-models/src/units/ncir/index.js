import {makeUnit} from '../shared/CADUnit.js';
import {addNCIRAssembly} from './assembly.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
spec.artwork=void 0;
const models=makeUnit(spec,data,addNCIRAssembly);
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
