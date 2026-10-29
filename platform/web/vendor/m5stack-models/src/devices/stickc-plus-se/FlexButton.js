/** MIT. Own Plus SE normalized molded-tab motion; no stiffness or switch simulation. */
import {Button} from '../../core/components/Button.js';
export class FlexButton extends Button {
 constructor({mesh,hingeY,freeY,...rest}){
  super({mesh,...rest});this.hingeY=hingeY;this.freeY=freeY;this.lastDepth=0;this.bindings=[];
  mesh.traverse(o=>{if(!o.isMesh)return;const p=o.geometry.attributes.position,n=o.geometry.attributes.normal;
   const weights=[],slopes=[];for(let i=0;i<p.count;i++){const t=Math.max(0,Math.min(1,(p.getY(i)+o.position.y-hingeY)/(freeY-hingeY)));weights.push(t*t*(3-t)/2);slopes.push(t>0&&t<1?(3*t-1.5*t*t)/(freeY-hingeY):0);}
   this.bindings.push({o,p,n,rest:p.array.slice(),normal:n.array.slice(),weights,slopes});
  });
 }
 update(dt){const changed=super.update(dt),d=this.getActuationState().depthMm;if(d===this.lastDepth)return changed;
  for(const{o,p,n,rest,normal,weights,slopes}of this.bindings){for(let i=0;i<p.count;i++){
   p.setXYZ(i,rest[i*3],rest[i*3+1],rest[i*3+2]-d*(weights[i]-1));
   const x=normal[i*3],y=normal[i*3+1]+d*slopes[i]*normal[i*3+2],z=normal[i*3+2],l=Math.hypot(x,y,z);
   if(d===0)n.setXYZ(i,normal[i*3],normal[i*3+1],normal[i*3+2]);else n.setXYZ(i,x/l,y/l,z/l);
  }p.needsUpdate=true;n.needsUpdate=true;o.geometry.computeBoundingBox();o.geometry.computeBoundingSphere();}
  this.lastDepth=d;return true;
 }
 dispose(){super.dispose();this.bindings=[];}
}
