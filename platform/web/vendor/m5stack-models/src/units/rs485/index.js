import {makeUnit} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {clearedBoard,terminal} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';
const models=makeUnit(spec,data,host=>{clearedBoard(host);terminal(host,spec);refineOpenTopGrove(host,'rs485');});
export class Model extends models.Model{
 build(options={}){super.build(options);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export class GroveModule extends models.GroveModule{
 build(options={}){super.build(options);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export {TerminalPlug,spec};
export default Model;
