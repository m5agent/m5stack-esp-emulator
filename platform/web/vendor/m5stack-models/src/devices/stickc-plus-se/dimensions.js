/** MIT. K016-P-SE photo/drawing reconstruction; concealed dimensions are estimates. */
export const DIM=Object.freeze({
 body:Object.freeze([24,48,13.52]),cornerRadius:3,shellWall:1.1,
 display:Object.freeze({width:135,height:240,active:[14.8,24.86],position:[0,8.1,6.81],window:[15.5,26.0]}),
 a:Object.freeze({position:[0,-13.8,0],w:14.4,h:9.2,hingeY:-18.4,freeY:-9.2,travel:.25}),
 b:Object.freeze({position:[12,8.1,0],face:'right',w:4.4,h:5.6,travel:.18}),
 power:Object.freeze({position:[-12,-15.5,0],face:'left',w:4.2,h:5.5,travel:.18}),
 usb:Object.freeze({position:[0,-24,3.25],w:8.7,h:3.1,depth:5}),
 grove:Object.freeze({position:[0,-24,-3.55],w:10,h:5.15,depth:5.8}),
 hat:Object.freeze({position:[0,23.3,-5.0],cols:8,rows:1,pitch:2.54}),
 label:Object.freeze({size:[21,37],position:[0,4.7,-6.86]}),
 mounts:Object.freeze({x:8,magnetY:-14.6,screwY:-19.5})
});
export const HAT_PINS=Object.freeze([
 {n:1,name:'GND'},{n:2,name:'5V OUT'},{n:3,name:'G26'},{n:4,name:'G36 / G25'},
 {n:5,name:'G0'},{n:6,name:'BAT'},{n:7,name:'3V3'},{n:8,name:'5V IN'}
]);
export const GROVE_PINS=Object.freeze([{n:1,name:'GND'},{n:2,name:'5V'},{n:3,name:'G32'},{n:4,name:'G33'}]);
export const spec=Object.freeze({id:'stickc-plus-se',sku:'K016-P-SE',name:'M5StickC Plus SE',nominalMm:DIM.body,scope:'visual-only',geometry:'original-parametric-reconstruction',display:{width:135,height:240,driver:'ST7789V2',touch:false},buttons:['a','b','power'],ports:['grove','usb','hat']});
export const defaults=Object.freeze({artwork:true,pixelEffect:true});
export const configurations=Object.freeze([{id:'complete',label:'Complete StickC Plus SE',options:{}}]);
export const configurationSchema=Object.freeze({artwork:{type:'boolean',default:true},pixelEffect:{type:'boolean',default:true}});
