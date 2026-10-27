import {addStickers} from './stickers.js';
import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {addElectronics,addGrove,addControls} from './assembly.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';

function build(host){
 addCadParts(host,data,{shell:materials.plastic(0x626661,{roughness:.78}),metal:materials.metal(0xb4b8b2,{roughness:.46}),strain:materials.plastic(0x65726a,{roughness:.9})});
 addElectronics(host);addGrove(host);addControls(host);
 host.add(new Component({id:'sensor',label:'Mini Scales load-cell visual anchor',meta:{role:'visual-anchor',scope:'No weight, calibration, strain, mechanics, firmware or protocol simulation'}}));
 host.unitStickers=addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.mini-scales',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'button'}};
 build(){build(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.mini-scales.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,build,options);}
}
export {spec};
export default Model;
