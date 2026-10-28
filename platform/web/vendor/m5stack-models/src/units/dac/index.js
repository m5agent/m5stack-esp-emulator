/** MIT; Unit DAC U012 original MCP4725,appearance/attachment only. */
import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildDAC} from './assembly.js';
import {TerminalPlug} from './TerminalPlug.js';
import {spec} from './dimensions.js';
export const defaults={terminalPlug:true};
export const configurationSchema={terminalPlug:{type:'boolean',default:true,meaning:'Actual original orange2P plug installed or detached'},artwork:{type:'boolean',default:true,meaning:'Ink only;real rear/polarity film,relief andcontacts remain'}};
export const configurations=[{id:'complete',name:'完整原版 DAC',options:{terminalPlug:true}},{id:'without-terminal-plug',name:'原版 DAC 拔下2P端子',options:{terminalPlug:false}}];
function optionsFor(options){const n={...defaults,...options};if(typeof n.terminalPlug!=='boolean')throw new TypeError('terminalPlug must be boolean');return n;}
function install(host,options){if(options.terminalPlug)host.get('terminal').attach(new TerminalPlug({artwork:host.options.artwork}));}
export class Model extends Device{static meta={id:'m5stack.unit.dac',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:{}};build(options={}){const n=optionsFor(options);buildDAC(this);install(this,n);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.dac.grove',name:spec.name,sku:spec.sku,connector:'grove'};build(options={}){const n=optionsFor(options);buildGroveModuleAssembly(this,buildDAC,n);install(this,n);}}
export {TerminalPlug,spec};export default Model;
