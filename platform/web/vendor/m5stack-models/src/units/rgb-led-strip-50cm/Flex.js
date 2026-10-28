import {Component} from '../../core/index.js';
import {THREE} from './geometry.js';
export class StripFlex extends Component{
 static kind='visual-flex';
 constructor(){super({id:'flex',label:'A093 continuous strip display bend',meta:{role:'externally-driven-flex',neutralAxisLengthMm:500,rangeDeg:[-120,120],scope:'Viewer bound only;no elastic/material/minimum-radius/force/electrical behavior'}});this.bendDeg=0;this.transition=null;this.surfaces=[];this.sites=[];this.links=[];this.callbacks=[];}
 point(x,y,z=0){const k=THREE.MathUtils.degToRad(this.bendDeg)/500;if(!k)return new THREE.Vector3(x,y,z);const a=k*x;return new THREE.Vector3(Math.sin(a)/k-z*Math.sin(a),y,(1-Math.cos(a))/k+z*Math.cos(a));}
 basis(x){return new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),-THREE.MathUtils.degToRad(this.bendDeg)*x/500);}
 surface(o){this.surfaces.push({mesh:o,base:new Float32Array(o.geometry.attributes.position.array)});return o;}
 site(o,x){this.sites.push({object:o,x});return o;}
 link(o,p,site,q){this.links.push({mesh:o,stripPoint:p,site,sitePoint:new THREE.Vector3(...q)});return o;}
 apply(){for(const s of this.surfaces){const p=s.mesh.geometry.attributes.position;if(!this.bendDeg)p.array.set(s.base);else for(let i=0;i<p.count;i++){const v=this.point(...s.base.subarray(i*3,i*3+3));p.setXYZ(i,...v.toArray());}p.needsUpdate=true;s.mesh.geometry.computeVertexNormals();s.mesh.geometry.computeBoundingBox();s.mesh.geometry.computeBoundingSphere();}
  for(const s of this.sites){s.object.position.copy(this.point(s.x,0));s.object.quaternion.copy(this.basis(s.x));}
  for(const l of this.links){const a=this.point(...l.stripPoint),b=l.sitePoint.clone().applyQuaternion(l.site.quaternion).add(l.site.position),d=b.clone().sub(a);l.mesh.position.copy(a).add(b).multiplyScalar(.5);l.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.clone().normalize());l.mesh.scale.set(1,d.length(),1);}
  for(const f of this.callbacks)f();this.requestRender();
 }
 set({bendDeg,durationMs=0}={}){if(!Number.isFinite(bendDeg)||bendDeg< -120||bendDeg>120)throw new RangeError('bendDeg must be in[-120,120] display range');if(!Number.isFinite(durationMs)||durationMs<0)throw new RangeError('durationMs must be finite >=0');this.transition=durationMs>0&&bendDeg!==this.bendDeg?{from:this.bendDeg,to:bendDeg,t:0,duration:durationMs/1000}:null;if(!this.transition){this.bendDeg=bendDeg;this.apply();}this.requestRender();return this.getState();}
 update(dt=0){if(!Number.isFinite(dt)||dt<0)throw new RangeError('dt must be finite >=0');if(!this.transition)return false;const a=this.transition;a.t=Math.min(a.duration,a.t+dt);this.bendDeg=a.from+(a.to-a.from)*a.t/a.duration;this.apply();if(a.t===a.duration)this.transition=null;return true;}
 handle(c){if(c.type==='flex')return this.set(c);if(c.type==='state')return this.getState();return super.handle(c);}
 getState(){return{bendDeg:this.bendDeg,targetBendDeg:this.transition?.to??this.bendDeg,transitioning:!!this.transition,neutralAxisLengthMm:500,rangeDeg:[-120,120],inputAnchored:true};}
}
