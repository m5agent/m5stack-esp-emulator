import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Led,materials} from '../../core/index.js';
import {slab} from '../../modeling/parts.js';
import {makeUnit} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
 addStickers(host);
 slab(host.body,9,4,.1,1.8,[0,8,3.75],materials.plastic(0x252c30),[],.02).name='Color fixed optical package backing';
 slab(host.body,3.1,3.1,.1,.3,[0,8,3.87],materials.glossy(0x211e32,{roughness:.15}),[],.02).name='Color fixed sensor window';
 for(const [side,x] of [['left',-3.4],['right',3.4]]){
  const lens=slab(host.body,1.2,1.6,.3,.2,[0,0,0],materials.glossy(0xe4dfb4,{roughness:.35}),[],.02);lens.name=`Color ${side} white fill LED package`;
  const led=host.add(new Led({id:`fill-${side}`,label:`White fill LED · ${side}`,mesh:lens,position:[x,8,3.72],color:0xffffff,radius:0,glowSize:1.8,meta:{role:'externally-driven-visual',emitter:'white 0603',physicalSide:side,schematicReference:'D1/D2; exact side-to-designator correspondence unconfirmed',powerGroup:'VCC fill pair',independentElectricalControl:false,source:'Official U009 schematic: two white 0603 LEDs, each fed from VCC through 1K; source photos show both packages',placementEvidence:'Existing photo-fitted package XY retained; package depth and diffusion are appearance estimates',scope:'External visual color/brightness API only; common physical supply is for the calling framework to reflect, no I2C, illumination sensing or automatic power behavior'}}));
  led.glow.position.z=.17;
 }
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
