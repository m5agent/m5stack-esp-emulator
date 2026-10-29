// MIT. Own C126-Ext source and photographs; hidden dimensions/travel are appearance inferences.
export const spec=Object.freeze({id:'atoms3r-ext',name:'AtomS3R-Ext',sku:'C126-Ext',nominalMm:[24,24,12],nativeMm:[24,24,12],soc:'ESP32-S3-PICO-1-N8R8',prototype:{cols:5,rows:6,pitchMm:2.54,isolated:true},scope:'visual-only',grovePins:['GND','5V','G2','G1'],header5Pins:['3V3','G5','G6','G7','G8'],header4Pins:['G39','G38','5V','GND'],travelMm:{reset:.15},reset:{rootZ:-4.3,freeZ:2.506685256958008,seedSourceFace:3272},physicalBaseTranslationZ:.45});
export const defaults=Object.freeze({artwork:true});
export const configurations=Object.freeze([{id:'complete',name:'完整原型扩展主机与贴纸',options:{}}]);
export const configurationSchema=Object.freeze({artwork:{type:'boolean',default:true,meaning:'Ink only;prototype board,FPC,physical substrates,contacts and Reset motion retained'}});
// Component placements are local to the explicitly translated board assembly.
export const DIM=Object.freeze({usb:[0,-12.02,1.6],grove:[0,-12.02,-3.2],header5:[7.62,-2.7,-6.33],header4:[-7.62,-3.97,-6.33]});
