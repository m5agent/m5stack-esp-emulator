import {Button,Led,materials} from '../../core/index.js';
import {makeUnit,knob} from '../shared/CADUnit.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 const cap=knob(host.body,{y:0,z:0,r:5.3,h:13.38,cap:0xdbddd8});cap.name='Encoder moving knob';
 const press=host.add(new Button({id:'press',label:'Encoder press',mesh:cap,position:[0,7,6],travel:.35,meta:{role:'visual-control',travelSource:'Photo-derived visual travel; no switch or pulse emulation'}}));
 const rotation=host.add(new VisualJoint({id:'rotation',label:'Encoder knob rotation',position:[0,7,6],axis:[0,0,1],continuous:true,meta:{axisEvidence:'Official U135: rotary encoder with push input; cap axis normal to front shell',demoRpmMax:60}}));rotation.adopt(press.object3d);
 for(const [i,x]of [-7.5,7.5].entries())host.add(new Led({id:'led'+i,position:[x,7,5.9],radius:.7,glowSize:2,lensColor:0xc6d1c7,meta:{role:'externally-driven-visual'}}));
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
