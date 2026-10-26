import {addStickers} from './stickers.js';
import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {addBoard,addGrove,addTerminal} from './assembly.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {TerminalPlug} from './TerminalPlug.js';

function buildWeight(host){
 addCadParts(host,data,{shell:materials.plastic(0xe4e6df,{roughness:.76})});
 addBoard(host);addGrove(host,spec);addTerminal(host,spec);
 screw(host.body,[0,-4,-4.02],'back',1.35);
 host.add(new Component({id:'sensor',label:'Weight-I2C visual anchor',meta:{role:'visual-anchor',scope:'No sensor data, calibration, electrical or protocol behavior'}}));
 host.unitStickers=addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.weight-i2c',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};
 build(options={}){buildWeight(this);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.weight-i2c.grove',name:spec.name,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildWeight,options);if(options.terminalPlug===true)this.port('terminal').attach(new TerminalPlug());}
}
export {TerminalPlug,spec};
export default Model;
