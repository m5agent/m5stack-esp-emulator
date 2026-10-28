/** MIT; GPIO2 LED1 is documentary fixed blue,externally driven only. */
import{Led}from'../../core/index.js';
export class FixedBlue extends Led{set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0x247cff});}}
