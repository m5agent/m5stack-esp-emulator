import {Device,Display,materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {physicalButton} from '../../modeling/actuators.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {DIM} from './dimensions.js';
import {addBody} from './body.js';
import {addPorts} from './ports.js';
import {addPerimeterStickers} from './stickers.js';
import {KEY_CODES,keyLayout,addKeyboard} from './keyboard.js';
export class CardputerZero extends Device{
 static meta={id:'m5stack.cardputer-zero',name:'CardputerZero',sku:'C154',vendor:'M5Stack',size:DIM.body,keymap:Object.fromEntries([...KEY_CODES.flat(),'Escape','Tab'].map(k=>[k,`key-${k}`]))};
 build(){
  const keys=keyLayout();addBody(this,keys);addKeyboard(this,keys);addPorts(this);
  addPerimeterStickers(this);
  const d=DIM.display;this.add(new Display({id:'lcd',width:320,height:170,size:[d.w,d.h],position:[d.cx,d.cy,d.z],glass:{intensity:.1,roughness:.21},meta:{role:'external-framebuffer',activeAreaSource:'1.9-inch diagonal derived; panel drawing pending'}}));
  const lid=this.body.getObjectByName('Drilled 46-key front lid');
  // The official four strip labels sit between the moving black keys.
  for(let r=0;r<4;r++)printedArtwork(this,{target:lid,url:new URL(`./artwork/keyboard-row-${r+1}.png`,import.meta.url).href,size:[82,[2.72,2.89,2.97,2.72][r]],position:[0,-1.1-r*6.55,9.8],name:`CardputerZero official fixed keyboard row ${r+1}`});
  printedArtwork(this,{target:lid,url:new URL('./artwork/front-zero.png',import.meta.url).href,size:[14.57,11.2],position:[-33.5,10.5,9.8],name:'CardputerZero official front name sticker'});
  printedArtwork(this,{target:lid,url:new URL('./artwork/front-power.png',import.meta.url).href,size:[14.17,20.96],position:[33.6,13.6,9.8],name:'CardputerZero official fixed power and USB sticker'});
  printedArtwork(this,{target:this.body.getObjectByName('Rear battery enclosure cover'),url:new URL('./artwork/rear.png',import.meta.url).href,size:[75.6,41.38],position:[0,0,-11.55],face:'back',name:'CardputerZero official rear circuit sticker'});
  slab(this.body,5,4.8,.35,.9,[29.5,21.7,9.78],materials.plastic(0x30382e),[],.08).name='Power switch recess';
  const power=slab(this.body,3.6,3.7,1.0,.8,[28.8,21.7,10.0],materials.plastic(0xa53f1e,{roughness:.65}),[],.2);power.name='Orange power switch cap';
  physicalButton(this,{id:'power',label:'Power slider · visual detents only',mesh:power,axis:[1,0,0],travel:1.4,latching:true,meta:{surfaceCenter:[28.8,21.7,11],surfaceFace:'front',mechanism:'slide',electricalBehavior:false}});
  printedArtwork(this,{target:power,url:new URL('./artwork/power-cap.png',import.meta.url).href,size:[3.3,2.2],position:[28.8,21.7,11],name:'CardputerZero official moving power cap print'});
 }
}
export default CardputerZero;
