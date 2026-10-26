import {Device,Display,materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {physicalButton} from '../../modeling/actuators.js';
import {artwork} from '../../modeling/artwork.js';
import {DIM} from './dimensions.js';
import {addBody} from './body.js';
import {addPorts} from './ports.js';
import {KEY_CODES,keyLayout,addKeyboard} from './keyboard.js';
export class CardputerZero extends Device{
 static meta={id:'m5stack.cardputer-zero',name:'CardputerZero',sku:'C154',vendor:'M5Stack',size:DIM.body,keymap:Object.fromEntries([...KEY_CODES.flat(),'Escape','Tab'].map(k=>[k,`key-${k}`]))};
 build(){
  const keys=keyLayout();addBody(this,keys);addKeyboard(this,keys);addPorts(this);
  const d=DIM.display;this.add(new Display({id:'lcd',width:320,height:170,size:[d.w,d.h],position:[d.cx,d.cy,d.z],glass:{intensity:.1,roughness:.21},meta:{role:'external-framebuffer',activeAreaSource:'1.9-inch diagonal derived; panel drawing pending'}}));
  for(let r=0;r<4;r++)null;
  null;
  null;
  null;
  slab(this.body,5,4.8,.35,.9,[29.5,21.7,9.78],materials.plastic(0x30382e),[],.08).name='Power switch recess';
  const power=slab(this.body,3.6,3.7,1.0,.8,[28.8,21.7,10.0],materials.plastic(0xa53f1e,{roughness:.65}),[],.2);power.name='Orange power switch cap';
  physicalButton(this,{id:'power',label:'Power slider · visual detents only',mesh:power,axis:[1,0,0],travel:1.4,latching:true,meta:{surfaceCenter:[28.8,21.7,11],surfaceFace:'front',mechanism:'slide',electricalBehavior:false}});
 }
}
export default CardputerZero;
