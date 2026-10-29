/** MIT. Own native-material flexure with exact rest-array restoration. */
import * as T from 'three';
import {Button} from '../../core/components/Button.js';
import {weightedInputHit} from '../../modeling/weighted-input.js';
export class NativePress extends Button {
 constructor({shell,body,field,...options}){super({...options,longPressMs:0});this.shell=shell;this.field=field;this.bodyFrame=body;this.depth=0;body.updateWorldMatrix(true,true);const matrix=body.matrixWorld.clone().invert().multiply(shell.matrixWorld),inverse=matrix.clone().invert();this.localAxis=this.axis.clone().transformDirection(inverse);const p=shell.geometry.attributes.position,n=shell.geometry.attributes.normal;this.rest=p.array.slice();this.norm=n.array.slice();this.weights=new Float32Array(p.count);this.gradients=[];
  for(let i=0;i<p.count;i++){const v=new T.Vector3().fromBufferAttribute(p,i).applyMatrix4(matrix),f=field(v);this.weights[i]=f?.w??0;this.gradients.push(new T.Vector3(...(f?.gradient??[0,0,0])).applyMatrix3(new T.Matrix3().setFromMatrix4(inverse)));}
  this.meta={...this.meta,actuation:'own-native-flexure',movingNativeVertices:this.weights.filter(w=>w>0).length,scope:'Normalized visual movement of own source;not rated switch/plastic physics'};this.hit(shell,h=>this.acceptHit(h));
 }
 acceptHit(h){if(!weightedInputHit(this,this.shell,h))return false;const p=this.bodyFrame.worldToLocal(h.point.clone());return(this.field(p)?.w??0)>1e-6;}
 update(dt){const changed=super.update(dt),d=this.getActuationState().depthMm;if(d===this.depth)return changed;const p=this.shell.geometry.attributes.position,n=this.shell.geometry.attributes.normal;
  for(let i=0;i<p.count;i++){const w=this.weights[i];if(!w)continue;const k=i*3;p.setXYZ(i,this.rest[k]+this.localAxis.x*d*w,this.rest[k+1]+this.localAxis.y*d*w,this.rest[k+2]+this.localAxis.z*d*w);if(d===0)n.setXYZ(i,this.norm[k],this.norm[k+1],this.norm[k+2]);else{const r=new T.Vector3(this.norm[k],this.norm[k+1],this.norm[k+2]),g=this.gradients[i],dot=r.dot(this.localAxis),den=1+d*g.dot(this.localAxis);r.addScaledVector(g,-d*dot/den).normalize();n.setXYZ(i,r.x,r.y,r.z);}}
  p.needsUpdate=true;n.needsUpdate=true;this.shell.geometry.computeBoundingBox();this.shell.geometry.computeBoundingSphere();this.depth=d;return true;
 }
 dispose(){super.dispose();this.shell=null;this.rest=null;this.norm=null;this.weights=null;this.gradients=[];this.bodyFrame=null;this.field=null;}
}
