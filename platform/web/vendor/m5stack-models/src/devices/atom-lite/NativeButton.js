/** MIT. Own C008 continuous U-slot/side-tab flexure; all source faces stay present. */
import {Button} from '../../core/index.js';
import {THREE,FACE} from './geometry.js';
import {spec} from './dimensions.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
export class NativeButton extends Button{
 constructor(kind,shell,followers=[]){
  const main=kind==='button',target=new THREE.Mesh(new THREE.PlaneGeometry(main?10.8:3.5,main?9.7:2.7),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false}));target.name='C008 '+kind+' actual cap input target';
  super({id:kind,label:main?'C008 G39 native U-slot main key':'C008 independent side Reset input',mesh:target,position:spec[kind].position,quaternion:main?FACE.front:FACE.left,travel:spec[kind].travelMm,longPressMs:0,meta:{role:'visual-control',visualMotion:'native-flexure',scope:'Input intent and real cap deformation only;no reboot/boot/GPIO/electrical/firmware behavior',travelSource:'Own native/photo-derived display estimate,not rated stop'}});
  this.shell=shell;this.rest=shell.geometry.attributes.position.array.slice();this.norm=shell.geometry.attributes.normal.array.slice();this.weights=new Float32Array(this.rest.length/3);this.slopes=new Float32Array(this.weights.length);this.followers=followers.map(o=>({object:o,rest:o.position.clone()}));this.main=main;this.lastDepth=0;
  for(let i=0;i<this.weights.length;i++){const k=i*3,x=this.rest[k]+shell.position.x,y=this.rest[k+1],z=this.rest[k+2]+shell.position.z;let t=0,span;
   if(main){if(Math.abs(x)>6.03||y<-5.001||y>6.75||z<.449)continue;span=11.5;t=THREE.MathUtils.clamp((y+5)/span,0,1);}
   else{if(x>-9.9||y<1.6||y>7.4||z<.449)continue;span=3.85;t=THREE.MathUtils.clamp((z-.45)/span,0,1);}
   this.weights[i]=t*t*(3-2*t);this.slopes[i]=6*t*(1-t)/span;
  }
  this.meta.deformedNativeVertices=this.weights.filter(w=>w>0).length;
  this.hit(shell,intersection=>weightedInputHit(this,shell,intersection));
 }
 update(dt){const changed=super.update(dt),depth=this.getActuationState().depthMm;if(depth===this.lastDepth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;
  for(let i=0;i<this.weights.length;i++){if(!this.weights[i])continue;const k=i*3;let x=this.rest[k],y=this.rest[k+1],z=this.rest[k+2],nx=this.norm[k],ny=this.norm[k+1],nz=this.norm[k+2];if(depth){if(this.main){z-=depth*this.weights[i];ny+=depth*this.slopes[i]*nz;}else{x+=depth*this.weights[i];nz-=depth*this.slopes[i]*nx;}const length=Math.hypot(nx,ny,nz);nx/=length;ny/=length;nz/=length;}p.setXYZ(i,x,y,z);n.setXYZ(i,nx,ny,nz);}
  for(const f of this.followers){f.object.position.copy(f.rest);f.object.position[this.main?'z':'x']+=depth*(this.main?-.8:.8);}
  p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.lastDepth=depth;return true;
 }
 dispose(){super.dispose();this.shell=null;this.rest=null;this.norm=null;this.weights=null;this.slopes=null;this.followers=null;}
}
