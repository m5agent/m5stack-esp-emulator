/** MIT. Original K027 reconstruction from its own official photographs. K210, not ESP32. */
import * as T from 'three';
import {Device,Display,Button,Led,materials} from '../../core/index.js';
import {slab,mesh,grove,FACE} from '../../modeling/parts.js';
import {FlexButton} from './FlexButton.js';
import {usbC,microSD} from '../../modeling/connectors.js';
const plastic=c=>materials.plastic(c,{roughness:.76});
function plate(p,w,h,d,r,pos,m,name,holes=[]){const o=slab(p,w,h,d,r,pos,m,holes,.025);o.name=name;o.userData.role='physical-assembly';return o;}
function frame(p,pos,face,name){const g=new T.Group();g.position.fromArray(pos);g.quaternion.copy(FACE[face]);g.name=name;p.add(g);return g;}
function key(host,id,label,pos,face,w,h,color){const g=new T.Group();g.name=id+' physical key assembly';plate(g,w,h,.9,.3,[0,0,-.75],color,id+' whole cap');plate(g,w*.45,h*.65,.8,.1,[0,0,-1.55],color,id+' plunger');const b=host.add(new Button({id,label,mesh:g,position:pos,quaternion:FACE[face],travel:.2,longPressMs:0,meta:{role:'visual-control',surfaceCenter:pos,surfaceFace:face,travelSource:'Own-product photo reconstruction, visual estimate'}}));const f=frame(host.body,pos,face,id+' fixed switch');plate(f,w+.6,h+.6,1,.2,[0,0,-2.9],plastic(0x252929),id+' fixed switch body');plate(f,w*.8,h*.8,.2,.1,[0,0,-1.9],materials.metal(0xb3b9b4),id+' fixed switch lid');return b;}
function corners(p,w,h,d,r,c){for(const sx of[-1,1])for(const sy of[-1,1]){const t=sx>0?(sy>0?0:-Math.PI/2):(sy>0?Math.PI/2:Math.PI),e=t+Math.PI/2,s=new T.Shape();s.absarc(0,0,r,t,e,false);s.lineTo((r-1.05)*Math.cos(e),(r-1.05)*Math.sin(e));s.absarc(0,0,r-1.05,e,t,true);s.closePath();mesh(p,new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:20}),c,[sx*(w/2-r),sy*(h/2-r),-d/2],'closed molded corner');}}
function ring(p,ro,ri,d,pos,m,name){const s=new T.Shape();s.absarc(0,0,ro,0,2*Math.PI,false);const h=new T.Path();h.absarc(0,0,ri,0,2*Math.PI,true);s.holes.push(h);return mesh(p,new T.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:36}),m,pos,name);}
export const defaults={pcb:'blue'};
export const configurations=[{id:'blue-pcb',name:'Blue PCB · I2C IMU',options:{pcb:'blue'}},{id:'black-pcb',name:'Black PCB · revised microphone board',options:{pcb:'black'}}];
export const configurationSchema={pcb:{type:'string',enum:['blue','black'],default:'blue'}};
export const spec={sku:'K027',size:[24,48,22],geometry:'original-own-product-photo-reconstruction',display:{width:135,height:240,driver:'ST7789',touch:false}};
export class StickV extends Device{
 static meta={id:'m5stack.stickv',name:'M5StickV',sku:'K027',size:spec.size,vendor:'M5Stack',keymap:{Space:'a',KeyA:'a',KeyB:'b',KeyP:'power'}};
 build({pcb='blue',pixelEffect=true}={}){
  if(!['blue','black'].includes(pcb))throw new RangeError('StickV pcb must be blue or black');
  const a=this.stickVAssembly={pcb},c=plastic(0x008fc3),black=plastic(0x171e21),metal=materials.metal(0xaeb6ad);
  a.front=plate(this.body,24,48,1.15,2.4,[0,0,9.85],c,'StickV own blue front molding',[{w:16,h:26.2,r:.7,cy:7.1},{w:12.1,h:12.1,r:.8,cy:-13.5}]);
  // Rear optics and acoustic openings are through the real thick wall. Each
  // has its own lens, microphone or speaker body and deep support behind it.
  const holes=[{w:5.4,h:5.4,r:2.7,cy:7.4},{w:8.5,h:3.7,r:.5,cy:17.4}];
  for(let x=-4;x<=4;x+=2)for(let y=-8;y<=-2;y+=2)holes.push({w:.85,h:.85,r:.425,cx:x,cy:y});
  for(const x of[-7.5,7.5])holes.push({w:3.1,h:3.1,r:1.55,cx:x,cy:-19});
  a.rear=plate(this.body,24,48,1.15,2.4,[0,0,-11],c,'StickV own rear camera and speaker cover',holes);
  for(const face of['left','right']){const f=frame(this.body,[face==='left'?-12:12,0,0],face,'StickV '+face+' wall');plate(f,43.2,19.7,1.05,.025,[0,0,-1.05],c,'StickV thick '+face+' wall',face==='left'?[{w:17.9,h:1.8,r:.1,cx:-5.5,cy:3.3},{w:3.5,h:4.8,r:.3,cx:17,cy:0}]:[{w:5.3,h:5.3,r:.5,cx:7,cy:0}]);}
  for(const face of['top','bottom']){const f=frame(this.body,[0,face==='top'?24:-24,0],face,'StickV '+face+' wall');plate(f,19.2,19.7,1.05,.025,[0,0,-1.05],c,'StickV thick '+face+' wall',face==='bottom'?[{w:9.3,h:3.5,r:1.6,cy:1.9},{w:10.6,h:5.6,r:.4,cy:-4.7},{w:3.7,h:3.7,r:1.85,cy:7.2}]:[]);}
  corners(this.body,24,48,19.7,2.4,c);
  a.pcb=plate(this.body,21.5,44.8,.85,1.2,[0,0,-1],plastic(pcb==='blue'?0x194f8f:0x212524),'StickV '+pcb+' PCB visual envelope');
  plate(this.body,17.2,27,3.9,1,[0,4,-6.1],materials.metal(0xb0b4a9),'StickV 200mAh battery visual envelope');
  plate(this.body,18,29,2,.8,[0,7.1,6.6],black,'StickV ST7789 physical LCD package');a.glass=plate(this.body,15.7,25.9,.35,.6,[0,7.1,10.45],materials.glossy(0x080c0d),'StickV actual LCD window');
  this.add(new Display({id:'lcd',label:'1.14-inch 135×240 LCD · ST7789',width:135,height:240,size:[14.2,25.25],position:[0,7.1,10.86],pixelEffect,touch:false,glass:false,meta:{role:'external-framebuffer',activeAreaSource:'Nominal 1.14 inch 135:240; own-photo registration'}}));
  a.hinge=plate(this.body,12.1,.25,1.15,.02,[0,-19.425,9.85],c,'StickV fixed lower U-tab hinge bridge');
  const tab=new T.Group();tab.name='StickV own three-sided U-slot continuous A tongue';
  a.aTab=plate(tab,11.6,11.6,1.15,.65,[0,-13.5,9.85],c,'StickV whole molded U-tab with inner wall');
  a.aPlunger=plate(tab,4.6,4.6,.7,.2,[0,-13.5,9.15],c,'StickV A tongue inner force boss');
  a.keyGrips=[-2,0,2].map(y=>plate(tab,8,.4,.16,.1,[0,-13.5+y,11],c,'StickV physical molded key grip'));
  a.a= this.add(new FlexButton({id:'a',label:'Front button A · molded U tongue',mesh:tab,hingeY:-19.3,freeY:-7.7,travel:.2,longPressMs:0,meta:{role:'visual-control',surfaceCenter:[0,-13.5,11],surfaceFace:'front',visualMotion:'flex-pad',hingeY:-19.3,freeY:-7.7,travelSource:'Own U-tab photo;normalized visual bending,not material stiffness'}}));
  plate(this.body,5,5,1,.3,[0,-13.5,7.5],black,'StickV A fixed tactile switch body');plate(this.body,4.5,4.5,.2,.2,[0,-13.5,8.5],metal,'StickV A fixed tactile switch lid');
  a.b=key(this,'b','Side button B',[12,7,0],'right',4.8,4.8,c);a.power=key(this,'power','Power key intent',[-12,-17,0],'left',3,4.3,c);
  a.usb=usbC(this,{position:[0,-24,1.9],face:'bottom',depth:3.7});a.grove=grove(this,{position:[0,-24,-4.7],face:'bottom',h:5.2});a.sd=microSD(this,{position:[-12,5.5,3.3],face:'left',w:17.5,h:1.5,depth:4});
  this.port('grove').pins=[{n:1,name:'GND'},{n:2,name:'VOUT'},{n:3,name:'G35'},{n:4,name:'G34'}];
  const mount=frame(this.body,[0,-24,7.2],'bottom','StickV own bottom M3 blind mounting bore');a.m3=mount;
  ring(mount,2.5,1.35,4,[0,0,-4],c,'StickV thick M3 boss bore wall');ring(mount,1.83,1.35,3.35,[0,0,-3.3],materials.metal(0xb9a35e),'StickV recessed M3 brass insert');
  a.m3Floor=mesh(mount,new T.CylinderGeometry(1.35,1.35,.18,40).rotateX(Math.PI/2),metal,[0,0,-4.05],'StickV M3 inferred deep blind stop');
  const optic=frame(this.body,[0,7.4,-11.02],'back','StickV physical OV7740 camera assembly');a.camera=optic;
  plate(optic,9,9,.8,.5,[0,0,-4],plastic(0x1c6247),'StickV rear camera daughterboard');plate(optic,6.4,6.4,2.4,.5,[0,0,-3.2],black,'StickV fixed camera sensor package');ring(optic,2.65,1.8,1.4,[0,0,-1.45],black,'StickV camera lens barrel');
  mesh(optic,new T.CylinderGeometry(1.76,1.76,.25,40).rotateX(Math.PI/2),materials.glossy(0x181b33,{roughness:.1}),[0,0,-.2],'StickV actual passive camera glass');
  const lamp=new T.Mesh(new T.BoxGeometry(8.25,3.4,.3),materials.glossy(0x829398,{roughness:.24}));lamp.name='StickV RGBW physical light lens';
  this.add(new Led({id:'rgbw',label:'RGBW lamp · external visual output',mesh:lamp,position:[0,17.4,-10.98],quaternion:FACE.back,color:0xffffff,glowSize:5,radius:1,meta:{role:'externally-driven-visual',hardwareChannels:'RGBW; displayed output is supplied color/brightness only'}}));
  plate(this.body,12,12,3,.8,[0,-5,-8.8],black,'StickV physical rear speaker chamber');plate(this.body,10.8,10.8,.2,.6,[0,-5,-9.3],materials.metal(0x7d8685),'StickV actual recessed speaker grille support');
  if(pcb==='black')plate(this.body,3,2.5,.8,.2,[6,-3,-2],metal,'Revised black PCB concealed microphone envelope');
  for(const x of[-7.5,7.5]){ring(this.body,2.1,1.1,6.2,[x,-19,-9.85],c,'StickV hollow rear screw boss');const f=frame(this.body,[x,-19,-11.02],'back','StickV rear fastener');ring(f,1.45,.55,.12,[0,0,0],metal,'StickV actual screw head');plate(f,1,1,.15,.45,[0,0,-1],metal,'StickV deep blind screw stop');}
  // Its blue case has no paper rear pinout sticker in the own-product photos.
  // A small ink mark on the free front key follows its actual cap motion.

 }
}
export const Model=StickV;export default Model;
