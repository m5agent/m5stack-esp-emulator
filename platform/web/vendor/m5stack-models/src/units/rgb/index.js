import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {slab,mesh,disc,mark,textMark,hitButton,grove} from '../../modeling/parts.js';
import {makeUnit,knob,can,cylinder} from '../shared/CADUnit.js';
import {spec} from './dimensions.js';import data from './geometry-data.js';
import {addStickers} from './stickers.js';
void 0;
const models=makeUnit(spec,data,host=>{
for(const [i,x]of [-6.5,0,6.5].entries())host.add(new Led({id:'led'+i,label:'RGB LED '+i,position:[x,2.7,4.03],mesh:new THREE.Mesh(new THREE.CircleGeometry(2.05,48),materials.plastic(0xbfc6bd,{roughness:.45})),radius:2.05,glowSize:4,lensColor:0xbfc6bd,meta:{role:'externally-driven-visual'}}));grove(host,{id:'out',position:[0,15.65,0],face:'top',color:0x20272a,w:10,h:5});
addStickers(host);
});
export const Model=models.Model;export const GroveModule=models.GroveModule;export default Model;
