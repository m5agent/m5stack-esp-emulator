/** MIT. Original C008 Atom Lite: complete visual assembly and external input/output. */
import {Device,Led,Port} from '../../core/index.js';
import {buildAssembly} from './assembly.js';
import {NativeButton} from './NativeButton.js';
import {spec} from './dimensions.js';
import {box,THREE,materials,portQuaternion} from './geometry.js';
import {addStickers} from './stickers.js';
class AtomLite extends Device{
 static meta={id:'m5stack.atom-lite',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'button'}};
 build(){const a=buildAssembly(this);this.atomLiteAssembly=a;this.add(new NativeButton('button',a.shell.front,[a.mainStem]));this.add(new NativeButton('reset',a.shell.rear,[a.resetStem]));
  const lens=new THREE.Mesh(new THREE.BoxGeometry(1.6,.18,.5),materials.plastic(0xdde5d5,{roughness:.3}));lens.name='C008 actual supported RGB lightpipe through own native slit';this.add(new Led({id:'rgb',label:'Single C008 SK6812 RGB · external output',mesh:lens,position:spec.rgb.position,color:0xffffff,glowSize:2,radius:.3,meta:{role:'external-output',pin:'G27',scope:'Human-visible RGB only;defaultoff,no button/reset/firmware linkage'}}));
  const add=(id,connector,position,pins=[],face='bottom',grid=null)=>this.add(new Port({id,label:'C008 actual '+id,connector,position,quaternion:portQuaternion(face),hitSize:id==='grove'?[10.2,1,5.2]:id==='usb'?[8.1,1,3.1]:[2.6,1,id==='ext-5p'?12.7:10.16],pins:pins.map((name,i)=>({n:i+1,name})),pinGrid:grid,meta:{role:'visual-connector',face,scope:'Pure mechanical appearance;GPIO/USB/UART/I2C/power/protocol and firmware external'}}));
  a.grove.port=add('grove','grove',spec.grove.position,spec.grove.pins,'bottom',{cols:4,rows:1,pitch:2,center:[0,-.2],order:i=>i+1});a.usb.port=add('usb','usb-c',spec.usb.position);
  for(const h of spec.headers)a.headers[h.id].port=add(h.id,h.connector,h.position,h.pins,'back',{cols:1,rows:h.count,pitch:2.54,center:[0,0],order:(c,r)=>h.count-r});this.unitStickers=addStickers(this);
 }
}
export {AtomLite as Model};export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default AtomLite;
