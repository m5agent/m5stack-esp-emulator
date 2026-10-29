/** MIT. Exact K147 complete controller + Atomic Voice Base visual assembly. */
import {AtomS3R as Host} from '../atoms3r/index.js';
import data from './native-base-data.js';
import {buildVoiceBase} from './voice-base.js';
export const defaults={};
export const configurations=[{id:'complete',name:'AtomS3R + Atomic Voice Base',options:{}}];
export const configurationSchema={};
export const spec={sku:'K147',size:[24,24,22.9],host:'atoms3r',baseSku:'A149',documentedBaseMm:[24,24,14.14],matedBaseShellDepthMm:10};
export class AtomS3RAIChatbot extends Host{
 static meta={...Host.meta,id:'m5stack.atoms3r-ai-chatbot',name:'AtomS3R-AI Chatbot',sku:'K147',size:spec.size};
 build(options={}){super.build(options);buildVoiceBase(this,{data,assembledInsertionMm:1.65,rearZ:-6.45,sourceMatingZ:-9.50760555267334,sourceXY:[12.01745125465095,12],artwork:{'base-front':new URL('./artwork/base-front.png',import.meta.url).href,'base-mic':new URL('./artwork/base-mic.png',import.meta.url).href,'base-bottom':new URL('./artwork/base-bottom.png',import.meta.url).href}});}
}
export const Model=AtomS3RAIChatbot;export default Model;
