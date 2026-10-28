import * as THREE from 'three';
import {Device,Module} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {buildChainBus} from './assembly.js';
import {spec} from './dimensions.js';
export class Model extends Device{
 static meta={id:'m5stack.unit.chainbus',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm};
 build(){buildChainBus(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.chainbus.grove',name:spec.name+' · ChainBus IN cable',sku:spec.sku,connector:'grove',inputPort:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildChainBus,options);}
}
/** The existing fixed white EXT plug inserted directly into a host socket. */
export class DirectModule extends Module{
 static meta={id:'m5stack.unit.chainbus.direct',name:spec.name+' · direct EXT plug',sku:spec.sku,connector:'grove',inputPort:'ext',scope:'Fixed direct mechanical assembly;no cable or added source plug'};
 build(){
  const owner=this.body,frame=new THREE.Group();frame.name='ChainBus fixed direct EXT assembly';frame.position.fromArray(spec.direct.position);frame.rotation.set(...spec.direct.rotation);owner.add(frame);
  this.body=frame;try{buildChainBus(this);}finally{this.body=owner;}
  this.directAssemblyFrame=frame;
 }
}
export {spec};export default Model;
