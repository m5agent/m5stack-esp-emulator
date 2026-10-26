import {Device,Display,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {slab,hitButton,mark,screw,disc,FACE} from '../../modeling/parts.js';
import {artwork} from '../../modeling/artwork.js';
import {core2Assembly} from './assembly.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
export class Core2 extends Device{
 static meta={id:'m5stack.core2',name:'Core2 v1.1',sku:'K010-V11',revision:'v1.1',vendor:'M5Stack',size:DIM.body,keymap:{KeyA:'a',KeyB:'b',KeyC:'c',KeyP:'power',KeyR:'reset'}};
 build(){
  addCadParts(this,data,{black:materials.plastic(0xcfd3d1,{roughness:.74}),light:materials.plastic(0x393e40,{roughness:.83}),key:materials.plastic(0xdddeda)});
  const g=DIM.glass;slab(this.body,g.w,g.h,.12,3.5,[0,0,g.z-.12],materials.glossy(0x080b0d,{roughness:.19,clearcoat:.32}),[],.025);
  const d=DIM.display;this.add(new Display({id:'lcd',width:320,height:240,size:[d.w,d.h],position:[d.cx,d.cy,d.z],touch:true,glass:{intensity:.12,roughness:.18},meta:{role:'external-framebuffer',activeAreaSource:'2-inch diagonal derived; pending panel drawing'}}));
  for(const [i,x] of [-15,0,15].entries()){
   mark(this.body,5,3,[x,-20.7,8.34],(ctx,W,H,s)=>{ctx.strokeStyle='#6e1620';ctx.lineWidth=.3*s;ctx.beginPath();ctx.arc(W/2,H/2,1*s,0,Math.PI*2);ctx.stroke();});
   const touch=hitButton(this,{id:['a','b','c'][i],label:`Capacitive area ${['A','B','C'][i]}`,position:[x,-20.7,8.36],w:10,h:8,meta:{actuation:'capacitive',role:'visual-touch-target'}});touch.travel=0;
  }
  core2Assembly(this);
  // The removable EXT board and its lid occupy the rear shell's long assembly opening.
  slab(this.body,11.8,38.8,.7,1,[16.7,0,-7.65],materials.plastic(0x2b4939,{roughness:.9}),[],.08);
  slab(this.body,12.1,39.2,1.35,1,[16.7,0,-8.26],materials.plastic(0xd3d7d0,{roughness:.82}),[{w:1.2,h:1.2,r:.6,cy:13.5},{w:1.2,h:1.2,r:.6,cy:-13.5}],.12);
  null;
  null;
  for(const x of [-22,22])for(const y of [-22,22])screw(this.body,[x,y,-8.3],'back',2.7);
  for(const x of [-15.2,15.2])for(const y of [-22,22]){const m=disc(this.body,2.5,[x,y,-8.3],materials.plastic(0x151a1c));m.quaternion.copy(FACE.back);}
 }
}
export default Core2;
