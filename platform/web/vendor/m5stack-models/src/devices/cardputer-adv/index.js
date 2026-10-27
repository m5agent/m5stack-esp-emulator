import * as THREE from 'three';
import {Device,Display,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,screw,header} from '../../modeling/parts.js';
import {cadButton,physicalButton} from '../../modeling/actuators.js';
import {addStickers} from './stickers.js';
import {addStampAssembly,addInternalAssembly} from './assembly.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
const rows=[['Escape','Digit1','Digit2','Digit3','Digit4','Digit5','Digit6','Digit7','Digit8','Digit9','Digit0','Minus','Equal','Backspace'],['Tab','KeyQ','KeyW','KeyE','KeyR','KeyT','KeyY','KeyU','KeyI','KeyO','KeyP','BracketLeft','BracketRight','Backslash'],['Fn','CapsLock','KeyA','KeyS','KeyD','KeyF','KeyG','KeyH','KeyJ','KeyK','KeyL','Semicolon','Quote','Enter'],['ControlLeft','AltLeft','AltRight','KeyZ','KeyX','KeyC','KeyV','KeyB','KeyN','KeyM','Comma','Period','Slash','Space']];
export class CardputerADV extends Device{
 static meta={id:'m5stack.cardputer-adv',name:'Cardputer-ADV',sku:'K132-Adv',vendor:'M5Stack',size:DIM.body,keymap:Object.fromEntries(rows.flat().map(code=>[code,`key-${code}`]))};
 build(){
  const parts=addCadParts(this,data,{shell:materials.plastic(0xd4d6d2,{roughness:.76}),black:materials.plastic(0x25292a,{roughness:.78}),key:materials.plastic(0x16191a,{roughness:.91})});
  addStampAssembly(this);addInternalAssembly(this);
  const d=DIM.display;slab(this.body,d.w+1,d.h+1,.06,.25,[d.cx,d.cy,d.z-.09],materials.glossy(0x080a0a,{roughness:.2}),[],.01);
  this.add(new Display({id:'lcd',width:240,height:135,size:[d.w,d.h],position:[d.cx,d.cy,d.z],glass:{intensity:.12,roughness:.2},meta:{role:'external-framebuffer',physicalAreaSource:'official A183 active area; same ST7789V2 panel, verify revision'}}));
  const k=DIM.keyboard;
  rows.forEach((row,r)=>row.forEach((code,c)=>cadButton(this,{source:parts['keyboard-membrane'],id:`key-${code}`,label:code,position:[k.x0+c*k.dx,k.y0-r*k.dy,7.2],w:5.25,h:3.35,r:.65,depth:2,travel:.25,meta:{matrix:[r,c],role:'keyboard-key'}})));
  for(const x of [-29,12.4])screw(this.body,[x,9.4,9.63],'front',1.5);
  const groveBody=grove(this,{position:[-42.02,19,1.7],face:'left',w:9.9,h:5,color:0xc8c9c3});
  groveBody.children[5].name='Grove deep insulating backstop';
  for(let i=0;i<4;i++)groveBody.children[6+i].name=`Grove spring contact ${i+1}`;
  // The 2×7 female EXT socket occupies the centered opening in the black battery base,
  // below the upper-shell seam. Official gallery-08/09; CAD aperture X ±9.4, Z −6.9…−0.8.
  header(this.body,{position:[0,26.8,-4],face:'top',cols:7,rows:2});
  // Official gallery-08 locates OFF/ON, G0 and RST on the +Y edge.
  physicalButton(this,{id:'power',label:'Power slider · visual detents only',mesh:parts['side-switch'],axis:[1,0,0],travel:1.3,latching:true,isolateMaterials:true,meta:{surfaceCenter:[10.1,26.8,2.6],surfaceFace:'top',mechanism:'slide',electricalBehavior:false}});
  cadButton(this,{source:parts['upper-housing'],id:'boot',label:'G0 / Boot button',position:[20.8,27,2.8],face:'top',w:5.6,h:7.5,r:.7,depth:1.4,travel:.2});
  cadButton(this,{source:parts['upper-housing'],id:'reset',label:'Reset button',position:[-26.5,27,2.8],face:'top',w:5.6,h:7.5,r:.7,depth:1.4,travel:.2});
  addStickers(this);
 }
}
export default CardputerADV;
