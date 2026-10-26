import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {addBoard,addGrove,addChannels} from './assembly.js';
import {spec,CHANNELS} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
import {TerminalPlug} from './TerminalPlug.js';
function buildFourRelay(host){
 addCadParts(host,data,{shell:materials.plastic(0x424745,{roughness:.77})});addBoard(host);addGrove(host);addChannels(host);
 for(const y of[-44,52])screw(host.body,[0,y,-4.025],'back',1.32);
 addStickers(host);
 host.add(new Component({id:'sensor',label:'4Relay visual board anchor',meta:{role:'visual-anchor',scope:'Appearance anchor only; no relay state, sensor, protocol, load, electrical or firmware simulation'}}));
}
function addPlugs(host,options){if(options.terminalPlug===true)for(const{number}of CHANNELS)host.port(`terminal-${number}`).attach(new TerminalPlug());}
export class Model extends Device{
 static meta={id:'m5stack.unit.4relay',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};
 build(options={}){buildFourRelay(this);addPlugs(this,options);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.4relay.grove',name:spec.name,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildFourRelay,options);addPlugs(this,options);}
}
export {TerminalPlug,spec,CHANNELS};
export default Model;
