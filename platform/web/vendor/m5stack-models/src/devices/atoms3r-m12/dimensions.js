// MIT. Own C126-M12 source and photographs; hidden dimensions/travel are appearance inferences.
export const spec=Object.freeze({id:'atoms3r-m12',name:'AtomS3R-M12',sku:'C126-M12',nominalMm:[26.4,24,22.5],nativeMm:[26.400001525878906,24,22],soc:'ESP32-S3-PICO-1-N8R8',camera:'OV3660 3MP',scope:'visual-only',grovePins:['GND','5V','G2','G1'],header5Pins:['3V3','G5','G6','G7','G8'],header4Pins:['G39','G38','5V','GND'],travelMm:{reset:.15},reset:{rootZ:-4.3,freeZ:2.506685256958008,seedSourceFace:10592},physicalBaseTranslationZ:.45});
export const defaults=Object.freeze({artwork:true});
export const configurations=Object.freeze([{id:'complete',name:'完整相机主机与贴纸',options:{}}]);
export const configurationSchema=Object.freeze({artwork:{type:'boolean',default:true,meaning:'Ink only;glass,optics,physical substrates,contacts and Reset motion retained'}});
// Component placements are local to the explicitly translated board assembly.
export const DIM=Object.freeze({usb:[0,-12.02,1.6],grove:[0,-12.02,-3.2],header5:[7.62,-2.7,-6.33],header4:[-7.62,-3.97,-6.33]});
