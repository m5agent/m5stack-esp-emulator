// U123 Unit Fader, not a generic linear slider. Millimetres; +X right,
// +Y away from the Grove socket, +Z the cap/front side.
export const spec={
 id:'fader',name:'Unit Fader',sku:'U123',size:[24,64,22.8],
 nominalMm:[24,64,22.8],cadEnvelopeMm:[24,64,10.4],visualEnvelopeMm:[24,64,22.8],
 mountY:-20,mountingHoles:[[-8,-20],[8,-20]],mountingBoreMm:4.85,
 grove:{position:[0,-31.7,.2],face:'bottom',w:10,h:5.2,depth:6.5,color:0x272a29},
 slider:{origin:[-.006,6.837,0],axis:[0,1,0],rangeMm:[-17.5,17.5],capWidth:7.2,capLength:11.2,capTop:17.6},
};
// Numbering follows the exact U123 rear product photograph, viewed through
// the assembled coordinate frame. It is a visual label, not a data-chain model.
export const LEDS=Array.from({length:14},(_,i)=>({id:'rgb-'+(i+1),number:i+1,x:i<7?-7.65:7.65,y:i<7?-12.5+i*6.25:25-(i-7)*6.25}));
