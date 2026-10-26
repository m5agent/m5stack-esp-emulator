import * as THREE from 'three';
import {Device,Display,Led,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {socket,grove,slab} from '../../modeling/parts.js';
import {cadButton,physicalButton} from '../../modeling/actuators.js';
import {artwork} from '../../modeling/artwork.js';
import {stampS3A} from '../../modeling/subassemblies.js';
import {stamplcTerminals,stamplcDC} from './terminals.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
export class StamPLC extends Device{
 static meta={id:'m5stack.stamplc',name:'StamPLC',sku:'K141',vendor:'M5Stack',size:DIM.body,keymap:{KeyA:'a',KeyB:'b',KeyC:'c',KeyR:'reset'}};
 build(){
  const parts=addCadParts(this,data,{light:materials.plastic(0xdde0db,{roughness:.79}),black:materials.plastic(0x22272a,{roughness:.76}),key:materials.plastic(0x272c2d,{roughness:.83})});
  stampS3A(this.body,{x:21.8,y:12.5,front:13.85});
  // The one Stamp-S3A RGB sits in the original USB-side cover slot. The
  // download-mode red indication is an externally supplied color of this
  // emitter, not evidence of a second monochrome lamp or a local boot model.
  const rgbPackage=slab(this.body,1.5,1.5,.55,.18,[0,0,0],materials.glossy(0xd4d7c8,{roughness:.35}),[],.03);rgbPackage.name='StamPLC StampS3A RGB package';
  const rgb=this.add(new Led({id:'stamp-rgb',label:'Stamp-S3A RGB',mesh:rgbPackage,position:[29.25,6.48,12.9],radius:0,glowSize:2.4,meta:{role:'externally-driven-visual',emitter:'WS2812B-2020',count:1,source:'Official StamPLC download/RGB instructions and Stamp-S3A specification: one programmable RGB',placementEvidence:'Original Stamp cover slot beside USB; XY is registered against the source aperture, package dimensions and height above the existing board are appearance estimates',electricalBehavior:false,scope:'external color/brightness only; no GPIO38 gate, boot response or firmware'}}));rgb.glow.position.z=.56;
  const d=DIM.display;
  this.add(new Display({id:'lcd',width:135,height:240,size:[d.w,d.h],position:[d.cx,d.cy,d.z],rotation:[0,0,Math.PI/2],glass:false,meta:{role:'external-framebuffer',nativeRasterRotation:90,activeAreaSource:'nominal 1.14-inch ST7789V2 panel; verify panel revision'}}));
  ['a','b','c'].forEach((id,i)=>cadButton(this,{source:parts.keys,id,label:id.toUpperCase(),position:[-19.6+i*10,1.4,15],w:8.7,h:4.4,r:.7,depth:2,travel:.2}));
  grove(this,{id:'port-a',position:[13,1,16.74],face:'front',w:10,h:5,color:0xb32235});
  grove(this,{id:'port-c',position:[25,1,16.74],face:'front',w:10,h:5,color:0x1c85ac});
  null;
  null;
  null;
  null;
  slab(this.body,67,69,1.2,1.2,[0,0,.5],materials.plastic(0x2c4938,{roughness:.9}),[],.1);
  stamplcTerminals(this.body);
  stamplcDC(this);
  socket(this,{position:[36.02,11,3],face:'right',w:8.7,h:3.1});
  physicalButton(this,{id:'reset',label:'Reset/boot key',mesh:parts['reset-key'],axis:[0,-1,0],travel:.2,isolateMaterials:true,meta:{surfaceCenter:[-24,37.5,8.5],surfaceFace:'top'}});
 }
}
export default StamPLC;
