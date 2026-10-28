import {Component} from '../../core/index.js';
import {THREE} from './geometry.js';
function values(a,n){if(!Array.isArray(a)||a.length!==n||!a.every(Number.isFinite))throw new TypeError('finite pose array required');}
export class AssemblyPose extends Component{
 static kind='unit-frame';
 constructor(){super({id:'unitFrame',label:'A093 strip assembly pose',meta:{scope:'Actual strip3P/input and nominal100mm adapter,local pose only,no stretch/electrical behavior'}});this.inputLocal=new THREE.Vector3();}
 bindInput(port){this.input=port;this.object3d.updateWorldMatrix(true,true);this.inputLocal.copy(this.object3d.worldToLocal(port.object3d.getWorldPosition(new THREE.Vector3())));return this;}
 set(c={}){if(c.position)values(c.position,3);if(c.rotation)values(c.rotation,3);if(c.quaternion){values(c.quaternion,4);if(c.quaternion.every(v=>Math.abs(v)<1e-10))throw new RangeError('nonzero quaternion required');}if(c.distance!=null&&(!Number.isFinite(c.distance)||c.distance<45||c.distance>112))throw new RangeError('distance must be45..112mm');const p=this.object3d.position.clone(),q=this.object3d.quaternion.clone();try{if(c.quaternion)this.object3d.quaternion.fromArray(c.quaternion).normalize();else if(c.rotation)this.object3d.rotation.fromArray(c.rotation);if(c.position)this.object3d.position.fromArray(c.position);if(c.distance!=null)this.object3d.position.copy(new THREE.Vector3(0,c.distance,0).sub(this.inputLocal.clone().applyQuaternion(this.object3d.quaternion)));this.host?.find('input/cable')?.sync();}catch(e){this.object3d.position.copy(p);this.object3d.quaternion.copy(q);this.host?.find('input/cable')?.sync();throw e;}this.requestRender();return this.getState();}
 getState(){return{position:this.object3d.position.toArray(),quaternion:this.object3d.quaternion.toArray(),space:'module-host-Grove-frame',inputPort:'input',distanceRangeMm:[45,112],canonicalConnector:'m5.a093.3p-input'};}
 handle(c){if(c.type==='pose')return this.set(c);if(c.type==='state')return this.getState();return super.handle(c);}
}
