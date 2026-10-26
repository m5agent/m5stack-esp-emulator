import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
void 0;
const models=makeUnit(spec,data,host=>{
slab(host.body,7,6,.08,.2,[0,2.5,4.01],materials.plastic(0x158bc0),[],.02);mark(host.body,5,4,[0,2.5,4.11],(ctx,W,H,s)=>{ctx.fillStyle='#293c4c';ctx.font=`700 ${3*s}px Arial`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('*',W/2,H/2);});disc(host.body,2.4,[0,10.5,3.99],materials.plastic(0x9b8060));mark(host.body,4.1,4.1,[0,10.5,4.02],(ctx,W,H,s)=>{ctx.strokeStyle='#433f3c';ctx.lineWidth=.25*s;for(let i=0;i<5;i++){ctx.beginPath();ctx.moveTo(.6*s,(.6+i*.6)*s);ctx.lineTo(3.5*s,(.6+i*.6)*s);ctx.stroke();}});
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
