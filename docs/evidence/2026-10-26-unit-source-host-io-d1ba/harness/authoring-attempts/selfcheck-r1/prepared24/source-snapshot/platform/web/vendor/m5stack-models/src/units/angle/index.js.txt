import {materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {makeUnit,knob} from '../shared/CADUnit.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 slab(host.body,9,9,.5,.5,[0,7,4],materials.metal(0x8d9496),[],.1);
 const cap=knob(host.body,{y:7,z:4.5,r:5.2,h:13.45,cap:0x008ec0});cap.name='Angle moving knob';
 const rotation=host.add(new VisualJoint({id:'rotation',label:'Angle knob position',position:[0,7,4.5],axis:[0,0,1],meta:{axisEvidence:'Official U005: rotary potentiometer; cap axis normal to front shell',visualRangeDeg:[-150,150],rangeEvidence:'Viewer range only; official mechanical travel and zero offset are unconfirmed'}}));rotation.adopt(cap);
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
