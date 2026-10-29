/** MIT. Original K016 reconstruction from its own official photos, not later StickC CAD. */
import * as T from 'three';
import {Device,Display,Button,Led,materials} from '../../core/index.js';
import {slab,mesh,grove,FACE} from '../../modeling/parts.js';
import {usbC,microSD} from '../../modeling/connectors.js';
import {printedArtwork} from '../../modeling/artwork.js';
const plastic=c=>materials.plastic(c,{roughness:.76});
function plate(p,w,h,d,r,pos,m,name,holes=[]){const o=slab(p,w,h,d,r,pos,m,holes,.025);o.name=name;o.userData.role='physical-assembly';return o;}
function frame(p,pos,face,name){const g=new T.Group();g.position.fromArray(pos);g.quaternion.copy(FACE[face]);g.name=name;p.add(g);return g;}
function key(host,id,label,pos,face,w,h,color){const g=new T.Group();g.name=id+' physical key assembly';plate(g,w,h,.9,.3,[0,0,-.75],color,id+' whole cap');plate(g,w*.45,h*.65,.8,.1,[0,0,-1.55],color,id+' plunger');const b=host.add(new Button({id,label,mesh:g,position:pos,quaternion:FACE[face],travel:.2,longPressMs:0,meta:{role:'visual-control',surfaceCenter:pos,surfaceFace:face,travelSource:'Own-product photo reconstruction, visual estimate'}}));const f=frame(host.body,pos,face,id+' fixed switch');plate(f,w+.6,h+.6,1,.2,[0,0,-2.9],plastic(0x252929),id+' fixed switch body');plate(f,w*.8,h*.8,.2,.1,[0,0,-1.9],materials.metal(0xb3b9b4),id+' fixed switch lid');return b;}
function corners(p,w,h,d,r,c){for(const sx of[-1,1])for(const sy of[-1,1]){const t=sx>0?(sy>0?0:-Math.PI/2):(sy>0?Math.PI/2:Math.PI),e=t+Math.PI/2,s=new T.Shape();s.absarc(0,0,r,t,e,false);s.lineTo((r-1.05)*Math.cos(e),(r-1.05)*Math.sin(e));s.absarc(0,0,r-1.05,e,t,true);s.closePath();mesh(p,new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:20}),c,[sx*(w/2-r),sy*(h/2-r),-d/2],'closed molded corner');}}
function ring(p,ro,ri,d,pos,m,name){const s=new T.Shape();s.absarc(0,0,ro,0,2*Math.PI,false);const h=new T.Path();h.absarc(0,0,ri,0,2*Math.PI,true);s.holes.push(h);return mesh(p,new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:36}),m,pos,name);}
const ART={
 'rear-gray':new URL('./artwork/rear-gray.png',import.meta.url).href,
 'rear-white':new URL('./artwork/rear-white.png',import.meta.url).href,
};
function mark(host,target,name,size,pos,face='back'){printedArtwork(host,{target,url:ART[name],size,position:pos,face,depth:.22,artworkKind:'reference-redraw',name:host.meta.name+' '+name+' · own official photograph reference redraw'});}
export const defaults={version:'gray'};
export const configurations=[{id:'gray',name:'Gray · MPU9250 hardware revision',options:{version:'gray'}},{id:'white',name:'White · no IMU hardware revision',options:{version:'white'}}];
export const configurationSchema={version:{type:'string',enum:['gray','white'],default:'gray'}};
export const spec={sku:'K016',size:[25.5,48.2,13.7],geometry:'original-own-product-photo-reconstruction',display:{width:64,height:128,driver:'SH1107',touch:false}};
export class M5Stick extends Device{
 static meta={id:'m5stack.m5stick',name:'M5Stick',sku:'K016',size:spec.size,vendor:'M5Stack',keymap:{Space:'a',KeyA:'a',KeyP:'power'}};
 build({version='gray',pixelEffect=true}={}){
  if(!['gray','white'].includes(version))throw new RangeError('M5Stick version must be gray or white');
  const a=this.m5stickAssembly={version},c=plastic(version==='gray'?0x777f80:0xe5e5d9),black=plastic(0x171d1d),metal=materials.metal(0xb0b5ae);
  a.front=plate(this.body,25.5,48.2,1.05,2.7,[0,0,5.8],c,'M5Stick front molded cover',[{w:17.5,h:32,r:.8,cy:5.1}]);
  a.rear=plate(this.body,25.5,48.2,1.05,2.7,[0,0,-6.85],c,'M5Stick rear cover',[{w:3.2,h:3.2,r:1.6,cx:-8,cy:-20.4},{w:3.2,h:3.2,r:1.6,cx:8,cy:-20.4}]);
  for(const face of['left','right']){const f=frame(this.body,[face==='left'?-12.75:12.75,0,0],face,'M5Stick '+face+' wall');const isA=face==='right',y=isA?9:-17;plate(f,42.8,11.6,1.05,.02,[0,0,-1.05],c,'M5Stick thick '+face+' wall',[{w:isA?5.5:3.5,h:isA?5.5:3.6,r:.35,cx:face==='left'?-y:y},{w:4,h:.9,r:.1,cx:face==='left'?-6:16},{w:4,h:.9,r:.1,cx:face==='left'?10:-17}]);}
  for(const face of['top','bottom']){const f=frame(this.body,[0,face==='top'?24.1:-24.1,0],face,'M5Stick '+face+' wall');plate(f,20.1,11.6,1.05,.02,[0,0,-1.05],c,'M5Stick thick '+face+' wall',face==='bottom'?[{w:9.3,h:3.5,r:1.6,cy:2.8},{w:10.5,h:5.4,r:.3,cy:-2.7}]:[]);}
  corners(this.body,25.5,48.2,11.6,2.7,c);
  a.pcb=plate(this.body,22.8,44.4,.8,1.4,[0,0,-.35],plastic(0x315c46),'M5Stick own-board visual support');
  a.battery=plate(this.body,17.5,25,3.5,1,[0,3,-4.7],materials.metal(0xaeb2a7),'M5Stick 80mAh pouch visual envelope');
  plate(this.body,19,33,1.15,.7,[0,5.1,3.9],black,'M5Stick SH1107 physical module');
  a.glass=plate(this.body,17.2,31.7,.3,.6,[0,5.1,6.35],materials.glossy(0x070b0c),'M5Stick physical OLED window');
  this.add(new Display({id:'lcd',label:'1.3-inch 64×128 OLED · SH1107',width:64,height:128,size:[14.77,29.53],position:[0,5.1,6.72],style:'oled',touch:false,pixelEffect,glass:false,blackLevel:0,meta:{role:'external-framebuffer',activeAreaSource:'Nominal 1.3 inch diagonal and 1:2 pixel aspect; photo position inferred'}}));
  a.a=key(this,'a','Button A',[12.75,9,0],'right',5,5,c);a.power=key(this,'power','Power / reset intent',[-12.75,-17,0],'left',3,3.1,c);
  a.usb=usbC(this,{position:[0,-24.1,2.8],face:'bottom',depth:3.6});a.grove=grove(this,{position:[0,-24.1,-2.7],face:'bottom',h:5});
  this.port('grove').pins=[{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'G32'},{n:4,name:'G33'}];
  // An actual emitter and package occupy the photo-visible side slot. IR and
  // buzzer are physical parts only; no invented audio or infrared simulation.
  const optics=frame(this.body,[-12.74,0,0],'left','M5Stick optical inserts');plate(optics,3.8,.8,1.2,.1,[-6,0,-1.4],black,'M5Stick passive IR package');
  const lens=new T.Mesh(new T.BoxGeometry(2.4,.65,.4),plastic(0x3063a8));lens.name='M5Stick physical blue status lens';
  this.add(new Led({id:'blue',label:'Blue LED · external visual output',mesh:lens,position:[-12.77,-10,0],quaternion:FACE.left,color:0x0088ff,radius:.3,glowSize:2,meta:{role:'externally-driven-visual',gpio:'G19'}}));
  for(const face of['left','right']){const g=frame(this.body,[face==='left'?-11.9:11.9,0,0],face,'M5Stick recessed accessory clip support');for(const y of[-17,10])plate(g,5,2,1,.2,[y,0,-.2],black,'M5Stick recessed clip stop');}
  plate(this.body,13,9,2,.7,[0,-12,1.2],black,'M5Stick buzzer housing');plate(this.body,13,9,.15,.6,[0,-12,3.2],metal,'M5Stick buzzer lid');
  if(version==='gray')plate(this.body,3.5,3.5,.8,.2,[6,10,.45],black,'Gray-version concealed MPU9250 envelope');
  for(const x of[-8,8]){ring(this.body,2,1.1,3.8,[x,-20.4,-5.8],c,'M5Stick screw boss');const f=frame(this.body,[x,-20.4,-6.87],'back','M5Stick real screw well');ring(f,1.5,.6,.15,[0,0,0],metal,'M5Stick recessed screw head');plate(f,1.1,1.1,.18,.5,[0,0,-.9],metal,'M5Stick blind screw well stop');}
  a.label=plate(this.body,20.2,34,.16,.5,[0,1.5,-7.01],plastic(0xf2efe2),'M5Stick physical rear label substrate');mark(this,a.label,'rear-'+version,[20.2,34],[0,1.5,-7.01]);
  // Embossed M5 is molded physical geometry, independent of the ink switch.
  const emblem=[[[ -5.1,-2.6],[-5.1,2.6],[-4.48,2.6],[-1.45,-.7],[1.25,2.6],[1.85,2.6],[1.85,-2.6],[1.25,-2.6],[1.25,1.63],[-1.44,-1.58],[-4.5,1.63],[-4.5,-2.6]],[[2.65,2.6],[6,2.6],[6,1.95],[3.3,1.95],[3.3,.3],[5.2,.3],[6,-.4],[6,-1.9],[5.3,-2.6],[2.65,-2.6],[2.65,-1.95],[5.05,-1.95],[5.35,-1.65],[5.35,-.7],[5,-.35],[2.65,-.35]]];
  for(const points of emblem){const shape=new T.Shape();points.forEach(([x,y],i)=>i?shape.lineTo(x,y):shape.moveTo(x,y));shape.closePath();mesh(this.body,new T.ExtrudeGeometry(shape,{depth:.15,bevelEnabled:false}),c,[0,-14,6.86],'M5Stick physical molded M5 emblem');}
 }
}
export const Model=M5Stick;export default Model;
