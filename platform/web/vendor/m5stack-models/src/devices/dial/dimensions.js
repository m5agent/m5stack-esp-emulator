/** K130 initial Dial; local coordinates front +Z, top +Y. mm. */
export const defaults={artwork:true};
export const configurationSchema={artwork:{type:'boolean',default:true}};
export const configurations=[{id:'complete',label:'Dial K130 · complete body and mounting nut',options:{}}];
export const spec={id:'dial',sku:'K130',name:'Dial',size:[51,51,32.3],nativeSize:[50.817,50.817,30.32],lcd:{resolution:[240,240],diameter:32.512,position:[0,0,17.16]},grove:[{id:'port-a',position:[-17.65,.55,-11.72],pins:['G15 SCL','G13 SDA','5V','GND'],color:0x932e35},{id:'port-b',position:[17.65,.55,-11.72],pins:['G1 IN','G2 OUT','5V','GND'],color:0x181e20}],usb:{position:[0,-21.1,-7.1]},notes:['Initial K130 StampS3, separate from v1.1 StampS3A.','Nominal official dimensions retained; own STL 9 parts are preserved without scaling.','Internal hardware envelopes, fit and actuation travel are supported visual reconstructions, not manufacturing dimensions.']};
