/** MIT. Complete K001-V27 Basic v2.7 visual host; external firmware/IO boundary. */
import {Device} from '../../core/index.js';
import {spec,defaults} from './dimensions.js';
import {buildAssembly} from './assembly.js';
import {addStickers} from './stickers.js';
class BasicV27 extends Device{
 static meta={id:'m5stack.basic-v27',name:spec.name,sku:spec.sku,revision:spec.revision,vendor:'M5Stack',size:spec.size,keymap:{KeyA:'a',KeyB:'b',KeyC:'c',KeyP:'power'}};
 constructor(options={}){super({...defaults,...options});if(!['installed','removed'].includes(this.options.base))throw new RangeError('K001-V27 base must be installed or removed');}
 build(){buildAssembly(this);this.unitStickers=addStickers(this);
  // Core disposal owns each attached material. Native button materials are already
  // independent;deduplicate only repeated fixed-assembly instances for exact release.
  const seen=new Set();this.body.traverse(o=>{if(!o.material)return;const take=m=>{if(seen.has(m))return m.clone();seen.add(m);return m;};o.material=Array.isArray(o.material)?o.material.map(take):take(o.material);});
 }
}
export {BasicV27 as Model};export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default BasicV27;
