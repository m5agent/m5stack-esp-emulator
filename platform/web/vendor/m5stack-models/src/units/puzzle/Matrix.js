import * as THREE from 'three';
import {Component,Led} from '../../core/index.js';
/** Keep emission local to each real package: no billboard glow over adjacent cells. */
export class PixelLed extends Led{
 set(state){super.set(state);this.glow.visible=false;}
}
function color(value){
 if(value?.isColor){if(![value.r,value.g,value.b].every(v=>Number.isFinite(v)&&v>=0&&v<=1))throw new RangeError('Matrix Color channels must be finite values in [0,1]');return value.clone();}
 if(typeof value==='number'){if(!Number.isInteger(value)||value<0||value>0xffffff)throw new RangeError('Matrix numeric colors must be RGB integers in [0,0xffffff]');return new THREE.Color(value);}
 if(typeof value==='string'&&(/^#[0-9a-f]{3}$/i.test(value)||/^#[0-9a-f]{6}$/i.test(value)||Object.hasOwn(THREE.Color.NAMES,value.toLowerCase())))return new THREE.Color(value);
 throw new TypeError('Matrix colors must be RGB integers,hex RGB strings,named colors or finite THREE.Color objects');
}
function list(value,length,name){if(!(Array.isArray(value)||ArrayBuffer.isView(value))||value instanceof DataView||value.length!==length)throw new TypeError(`${name} must contain ${length} entries`);return Array.from(value);}
/** Atomic external appearance frame. No framebuffer protocol or automatic animation. */
export class Matrix extends Component{
 static kind='matrix';
 constructor(pixels){super({id:'matrix',label:'8 × 8 physical RGB matrix',meta:{role:'externally-driven-visual',width:8,height:8,order:'row-major-top-left',scope:'External colors/normalized visual brightness only. Pixels are actual physical LED packages;no WS2812 protocol,address mapping,automatic animation,electrical power/current/limiting or forwarding to output.'}});this.pixels=pixels;}
 handle(command){
  if(command.type!=='matrix')return super.handle(command);
  const brightness=command.brightness??1;if(!Number.isFinite(brightness)||brightness<0||brightness>1)throw new RangeError('Matrix brightness must be in [0,1]');
  if((command.colors!=null)===(command.rgba!=null))throw new TypeError('Matrix command requires exactly one colors or rgba frame');
  let frame;
  if(command.colors!=null)frame=list(command.colors,64,'colors').map(v=>({color:color(v),brightness}));
  else{const values=list(command.rgba,256,'rgba');if(!values.every(v=>Number.isInteger(v)&&v>=0&&v<=255))throw new RangeError('Matrix RGBA values must be integer bytes in [0,255]');frame=Array.from({length:64},(_,i)=>({color:new THREE.Color((values[i*4]<<16)|(values[i*4+1]<<8)|values[i*4+2]),brightness:brightness*values[i*4+3]/255}));}
  // Every entry is checked before the first physical package is changed.
  frame.forEach((state,i)=>this.pixels[i].set(state));return this.getState();
 }
 getState(){return{width:8,height:8,order:'row-major-top-left',pixels:this.pixels.map(pixel=>pixel.getState())};}
 dispose(){this.pixels=[];super.dispose();}
}
