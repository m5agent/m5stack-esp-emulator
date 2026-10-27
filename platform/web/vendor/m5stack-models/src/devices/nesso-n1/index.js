import {Device,Display,Button,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {slab} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
import {addStickers} from './stickers.js';
import {nessoAssembly} from './assembly.js';
export class NessoN1 extends Device{
 static meta={id:'m5stack.nesso-n1',name:'Arduino Nesso N1',sku:'DK001',vendor:'M5Stack / Arduino',size:DIM.body,keymap:{KeyA:'a',KeyP:'power'}};
 build(){
  const parts=addCadParts(this,data,{black:materials.plastic(0x171c1f,{roughness:.78,clearcoat:.02}),key:materials.plastic(0xa8cd43,{roughness:.62})});
  slab(this.body,22.6,46.4,.08,2.4,[0,0,10.11],materials.glossy(0x101619,{roughness:.32,clearcoat:.12}),[],.02);
  const d=DIM.display;this.add(new Display({id:'lcd',width:135,height:240,size:[d.w,d.h],position:[d.cx,d.cy,d.z],touch:true,glass:{intensity:.1,roughness:.25},meta:{role:'external-framebuffer',activeAreaSource:'same nominal 1.14-inch panel; pending panel drawing'}}));
  this.add(new Button({id:'a',label:'Front button',mesh:parts['front-key'],travel:.18,axis:[0,0,-1],meta:{role:'visual-control'}}));
  // Button aperture in the cover; avoid painting over the real raised key.
  parts['front-key'].renderOrder=1;
  null;
  // The stored antenna is a single CAD assembly; independent connectors carry real recesses and contacts.
  slab(this.body,19.1,32.8,3.6,.7,[0,6.2,6.45],materials.plastic(0x192124,{roughness:.82}),[],.1);
  nessoAssembly(this);
  cadButton(this,{source:parts['upper-housing'],id:'power',label:'Side reset / power key',position:[-12,-16,3.3],face:'left',w:4.4,h:6.6,r:.65,depth:1.3,travel:.18});
  addStickers(this);
 }
}
export default NessoN1;
