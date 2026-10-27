import {makeUnit} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {motorBoard,motor,propeller} from './assembly.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {addStickers} from './stickers.js';
const models=makeUnit(spec,data,host=>{
 motorBoard(host);motor(host,spec);if(host.options.propeller===true)propeller(host,spec);
 const rotor=host.add(new VisualJoint({id:'rotor',label:'Fan shaft / propeller',position:[0,15.2,spec.shaft.centerZ],axis:[0,1,0],continuous:true,meta:{axisEvidence:'Official U063 drawing: shaft points along +Y; 1 mm diameter',demoRpmMax:240}}));
 rotor.adopt(host.body.getObjectByName('Fan motor shaft'));
 const blade=host.body.getObjectByName('Optional static 60 mm propeller');if(blade)rotor.adopt(blade);
 addStickers(host);
});
export const Model=models.Model;
export const GroveModule=models.GroveModule;
export default Model;
