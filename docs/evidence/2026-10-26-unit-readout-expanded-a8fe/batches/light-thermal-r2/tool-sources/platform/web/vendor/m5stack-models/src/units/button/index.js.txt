import {materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {extractCadCap} from '../../modeling/actuators.js';
import {makeUnit,cylinder} from '../shared/CADUnit.js';
import {FlexPadButton} from './FlexPadButton.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 const position=[0,7.4,4],hingeY=3,freeY=11.1001;
 const {cap}=extractCadCap(host.parts.housing,{name:'Button native molded flex pad',position,face:'front',w:10.6,h:8.8,r:1.4,depth:1.5,outward:.05});
 host.add(new FlexPadButton({id:'press',label:'Press here',mesh:cap,position,hingeY:hingeY-position[1],freeY:freeY-position[1],travel:.35,meta:{role:'visual-control',visualMotion:'flex-pad',hingeY,freeY,footprintSource:'Official U027 mechanical drawing: 10.2 mm inner pad; native U-shaped cut and grooves retained',travelSource:'Visual free-edge travel estimate; no plastic stiffness or switch behavior'}}));
 const pack=slab(host.body,6,6,.8,.4,[0,7,1.1],materials.plastic(0x202727),[],.04);pack.name='Button recessed tactile switch';
 const cover=slab(host.body,5.6,5.6,.18,.3,[0,7,1.91],materials.metal(0xa1a6a4),[],.025);cover.name='Button tactile switch cover';
 cylinder(host.body,1.1,.2,[0,7,2.15],materials.plastic(0x2b3031)).name='Button recessed switch plunger';
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
