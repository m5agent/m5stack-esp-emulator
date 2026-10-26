import {UnitDevice,createGroveModule} from '../shared/ClassicUnit.js';
import {spec} from './dimensions.js';
export class Model extends UnitDevice {static spec=spec;static meta={...spec,vendor:'M5Stack'};}
export const GroveModule=createGroveModule(spec);
export default Model;
