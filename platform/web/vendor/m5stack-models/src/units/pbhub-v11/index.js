import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {addBoard,addGroveSockets} from './assembly.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

function buildPbHub(host){
 addCadParts(host,data,{shell:materials.plastic(0xe1e4de,{roughness:.77})});
 host.pcb=addBoard(host);addGroveSockets(host);
 screw(host.body,[0,spec.mountY,-4.025],'back',1.4);
 addStickers(host);
 host.add(new Component({id:'sensor',label:'PbHUB visual board anchor',meta:{role:'visual-anchor',scope:'Appearance only; no GPIO, PWM, ADC, servo, RGB controller, I2C or power simulation'}}));
}

export class Model extends Device{
 static meta={id:'m5stack.unit.pbhub-v11',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{}};
 build(){buildPbHub(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.pbhub-v11.grove',name:spec.name,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildPbHub,options);}
}
export {spec};
export default Model;
