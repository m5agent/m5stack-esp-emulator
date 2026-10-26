// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import {Device,Display,Button,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,mark,FACE} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import {usbC} from '../../modeling/connectors.js';
import {addAssembly} from './assembly.js';
import {paintBackLabel,paintSidePrint} from './labels.js';
import {DIM} from './dimensions.js';
import data from './geometry-data.js';
export {DIM};
export const HAT2_PINS=[{n:1,name:'GND'},{n:2,name:'G5'},{n:3,name:'EXT_5V'},{n:4,name:'G4'},{n:5,name:'BOOT (G0)'},{n:6,name:'G6'},{n:7,name:'G1'},{n:8,name:'G7'},{n:9,name:'G8'},{n:10,name:'G43'},{n:11,name:'BAT'},{n:12,name:'G44'},{n:13,name:'3V3_L2'},{n:14,name:'G2'},{n:15,name:'5V_IN'},{n:16,name:'G3'}];
export const GROVE_PINS=[{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'G9'},{n:4,name:'G10'}];
export const USB_PINS=[{n:1,name:'VBUS'},{n:2,name:'D−'},{n:3,name:'D+'},{n:4,name:'CC'},{n:5,name:'GND'}];
export class StickS3 extends Device {
 static meta={id:'m5stack.sticks3',name:'StickS3',vendor:'M5Stack',sku:'K150',size:[24,48,15],keymap:{Space:'btnA',Enter:'btnA',KeyA:'btnA',KeyB:'btnB',KeyP:'btnPWR'}};
 build({touch=false,pixelEffect=true,caseColor=0x292c30,keyColor=0x148bd5}={}){
  const parts=addCadParts(this,data,{black:materials.plastic(caseColor,{roughness:.79,clearcoat:0}),blue:materials.glossy(keyColor,{roughness:.42,clearcoat:.15})});
  this.add(new Button({id:'btnA',label:'KEY1 · BtnA',mesh:parts['front-key'],axis:[0,0,-1],travel:.35,meta:{gpio:'G11',role:'visual-control'}}));
  slab(this.body,DIM.window.w,DIM.window.h,.015,DIM.window.r,[0,DIM.window.cy,6.505],materials.cavity(),[],.01);
  this.add(new Display({id:'lcd',label:'LCD 135×240 · A183 active area',width:135,height:240,size:[DIM.lcd.w,DIM.lcd.h],position:[0,DIM.lcd.cy,DIM.lcd.z],touch,pixelEffect,glass:{size:[16.5,26.5],offset:.015,intensity:.18,roughness:.13},meta:{role:'external-framebuffer',activeAreaSource:'M5Stack A183: 14.864 × 24.912 mm'}}));
  cadButton(this,{source:parts['rear-shell'],id:'btnB',label:'KEY2 · BtnB',position:[12,0,.15],face:'right',w:8.8,h:5.6,r:.65,depth:1.4,travel:.18,meta:{gpio:'G12'}});
  cadButton(this,{source:parts['rear-shell'],id:'btnPWR',label:'Power / Reset',position:[-12,-15.5,.15],face:'left',w:4.4,h:5.6,r:.65,depth:1.4,travel:.18});
  usbC(this,{position:[0,-24,DIM.usb.z],face:'bottom',w:DIM.usb.w,h:DIM.usb.h});
  grove(this,{position:[0,-23.95,DIM.grove.z],w:9.7,h:5.1});
  addAssembly(this);
  this.add(new Port({id:'hat',label:'Hat2-Bus 2×8',connector:'m5.hat2',pins:HAT2_PINS,position:[0,24,0],hitSize:[21,1,5.8],hitOffset:[0,0,DIM.header.z],meta:{role:'visual-connector',face:'top'}}));
  this.add(new Led({id:'irTx',label:'IR emitter aperture',radius:.55,glowSize:3,position:[6.5,23.1,-1.2],quaternion:FACE.top,lensColor:0xd5dcdd,meta:{gpio:'G46',role:'externally-driven-visual'}}));
  mark(this.body,21,33.5,[0,6.6,-7.52],paintBackLabel,'back');mark(this.body,26,3.6,[-12.02,1,2.8],paintSidePrint,'left');
 }
}
