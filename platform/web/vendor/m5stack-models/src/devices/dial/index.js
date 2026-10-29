import {Device,Button,Port} from '../../core/index.js';
import {RoundDisplay} from '../../modeling/RoundDisplay.js';
import {THREE,FACE,portQuaternion} from './geometry.js';
import {spec} from './dimensions.js';
import {buildAssembly} from './assembly.js';
import {DialRotation} from './DialRotation.js';
import {NativeReset} from './NativeReset.js';
import {printedFilm} from '../../modeling/artwork.js';
class Dial extends Device{
 static meta={id:'m5stack.dial',name:'Dial',sku:'K130',vendor:'M5Stack',size:spec.size,keymap:{Space:'wake',KeyR:'reset',KeyB:'boot'}};
 build(){const a=buildAssembly(this);this.dialAssembly=a;const rotor=this.add(new DialRotation({id:'rotation',label:'Dial outer ring · drag to rotate',meshes:[a.native.parts['outer-rotor']],meta:{demoRpmMax:30}}));rotor.adopt(a.native.parts['outer-rotor'],a.board.encoderRotor);
 const wake=this.add(new Button({id:'wake',label:'WAKE · press orange front frame',travel:.2,longPressMs:0,meta:{role:'visual-control',actuation:'linear-carrier',surfaceFace:'front',surfaceCenter:[0,20,17.3],scope:'Shared screen/front carrier visual press intention;travel inferred,no electrical wake or HOLD'}}));
 this.body.updateMatrixWorld(true);for(const object of[a.native.parts['front-bezel'],a.board.lcdPCB,a.board.lcdSupport,a.board.glass,a.keys.wakeStem]){wake.cap.attach(object);if(object.isMesh&&object!==a.board.glass)wake.hit(object);}a.board.glass.raycast=()=>{};
 const lcd=this.add(new RoundDisplay({id:'lcd',label:'K130 round GC9A01 · touch FT3267',diameter:spec.lcd.diameter,width:240,height:240,position:spec.lcd.position,glass:false,touch:true,meta:{shape:'circle',scope:'Framebuffer and touch pixel intent only;SPI/I2C/firmware external'}}));wake.cap.attach(lcd.object3d);a.display=lcd;a.wake=wake;
 const boot=this.add(new Button({id:'boot',label:'StampS3 GPIO0',mesh:a.keys.bootCap,travel:.12,axis:[0,0,1],longPressMs:0,meta:{role:'visual-control',surfaceFace:'back',surfaceCenter:[0,-2.5,-11.85],scope:'Input only,no bootloader/USB mode'}}));a.boot=boot;a.reset=this.add(new NativeReset(a.native.parts['threaded-rear-body']));
 for(const p of spec.grove){const q=portQuaternion('back').multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),-Math.PI/2));a.grove[p.id].port=this.add(new Port({id:p.id,label:p.id==='port-a'?'PORT.A · HY2.0 I2C':'PORT.B · HY2.0 GPIO',connector:'grove',position:p.position,quaternion:q,hitSize:[10.1,.6,5],pins:p.pins.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:2,center:[0,-.2],order:i=>i+1},meta:{role:'visual-connector',face:'back',scope:'Visual mechanical connection;GPIO/I2C/power external'}}));}
 a.usb.port=this.add(new Port({id:'usb',label:'StampS3 USB-C',connector:'usb-c',position:spec.usb.position,quaternion:portQuaternion('bottom'),hitSize:[8.4,.6,3.2],meta:{role:'visual-connector',face:'bottom'}}));a.power.port=this.add(new Port({id:'power',label:'6–36V 2P DC input',connector:'terminal-2p-2.54',position:[0,17.6,-11.72],quaternion:portQuaternion('back'),hitSize:[6.9,.5,8.1],pins:[{n:1,name:'VIN+'},{n:2,name:'GND'}],meta:{role:'visual-connector',face:'back',scope:'Appearance only;do not simulate electrical supply'}}));
 this.unitStickers=[printedFilm(this,{url:new URL('./artwork/stamp-label.png',import.meta.url).href,size:[16.6,22.2],position:[0,-4.5,-11.6],face:'back',holes:[{w:3.8,h:2.8,r:.1,cx:0,cy:2}],name:'K130 original StampS3 clear-photo reference redraw;unreadable microtext omitted',artworkKind:'reference-redraw'})].filter(Boolean);
 }
}
export{Dial as Model};export{spec,defaults,configurationSchema,configurations}from'./dimensions.js';export default Dial;
