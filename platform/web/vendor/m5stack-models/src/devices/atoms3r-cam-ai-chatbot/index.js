/** MIT. Exact K147-CAM controller + Atomic Voice Base visual assembly. */
import {Model as Host} from '../atoms3r-cam/index.js';
import data from './native-base-data.js';
import {buildVoiceBase} from '../atoms3r-ai-chatbot/voice-base.js';
export const defaults={};
export const configurations=[{id:'complete',name:'AtomS3R-CAM + Atomic Voice Base',options:{}}];
export const configurationSchema={};
export const spec={sku:'K147-CAM',size:[24,24,23.5],host:'atoms3r-cam',baseSku:'A149',documentedBaseMm:[24,24,14.14],matedBaseShellDepthMm:10};
export class AtomS3RCAMAIChatbot extends Host{
 static meta={...Host.meta,id:'m5stack.atoms3r-cam-ai-chatbot',name:'AtomS3R-CAM AI Chatbot',sku:'K147-CAM',size:spec.size};
 build(options={}){super.build(options);buildVoiceBase(this,{data,assembledInsertionMm:2.0,rearZ:-6,sourceMatingZ:-30,artwork:{'base-front':new URL('./artwork/base-front.png',import.meta.url).href,'base-mic':new URL('./artwork/base-mic.png',import.meta.url).href,'base-bottom':new URL('./artwork/base-bottom.png',import.meta.url).href}});}
}
export const Model=AtomS3RCAMAIChatbot;export default Model;
