import {makeUnit} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {clearedBoard,terminal} from './assembly.js';
const models=makeUnit(spec,data,host=>{clearedBoard(host);terminal(host,spec);});
export const Model=models.Model;
export const GroveModule=models.GroveModule;
export default Model;
