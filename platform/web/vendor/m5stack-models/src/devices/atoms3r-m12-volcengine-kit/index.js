/** MIT. Exact D062-M12 controller + Atomic Voice Base visual assembly. */
import {Model as Host} from '../atoms3r-m12/index.js';
import data from './native-base-data.js';
import {buildVoiceBase} from '../atoms3r-ai-chatbot/voice-base.js';
export const defaults={};
export const configurations=[{id:'complete',name:'AtomS3R-M12 + Atomic Voice Base',options:{}}];
export const configurationSchema={};
export const spec={sku:'D062-M12',size:[26.4,24,32.5],nativeMm:[26.4,24,32],host:'atoms3r-m12',baseSku:'A149',documentedBaseMm:[24,24,14.14],matedBaseShellDepthMm:10};
export class AtomS3RM12VolcengineKit extends Host{
 static meta={...Host.meta,id:'m5stack.atoms3r-m12-volcengine-kit',name:'AtomS3R-M12 Volcengine Kit',sku:'D062-M12',size:spec.size};
 build(options={}){super.build(options);buildVoiceBase(this,{data,assembledInsertionMm:2.0,rearZ:-6,sourceMatingZ:-30,artwork:{'base-front':new URL('./artwork/base-front.png',import.meta.url).href,'base-mic':new URL('./artwork/base-mic.png',import.meta.url).href,'base-bottom':new URL('./artwork/base-bottom.png',import.meta.url).href}});}
}
export const Model=AtomS3RM12VolcengineKit;export default Model;
