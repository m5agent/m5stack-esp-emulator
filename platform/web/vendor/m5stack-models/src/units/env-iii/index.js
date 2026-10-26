import {UnitDevice,createGroveModule} from '../shared/ClassicUnit.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
export class Model extends UnitDevice {static spec=spec;static meta={...spec,vendor:'M5Stack'};build(){super.build();addStickers(this);}}
const BaseGroveModule=createGroveModule(spec);
export class GroveModule extends BaseGroveModule {build(options={}){super.build(options);addStickers(this);}}
export default Model;
