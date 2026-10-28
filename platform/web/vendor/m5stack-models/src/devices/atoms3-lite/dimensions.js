// MIT. C124 own official native and exact-SKU photographs; concealed assembly dimensions are visual estimates.
export const spec=Object.freeze({id:'atoms3-lite',name:'AtomS3 Lite',sku:'C124',nominalMm:[24,24,9.5],nativeMm:[24,24,9.50714111328125],soc:'ESP32-S3FN8',scope:'visual-only',grovePins:['GND','5V','G2','G1'],userGpio:'G41',rgbGpio:'G35',irGpio:'G4',header5Pins:['3V3','G5','G6','G7','G8'],header4Pins:['G39','G38','5V','GND'],travelMm:{button:.18,reset:.15},printRevision:'C124 own supplied bottom and conformity flat artwork'});
export const defaults=Object.freeze({artwork:true});
export const configurations=Object.freeze([{id:'complete',name:'完整本体与贴纸',options:{}}]);
export const configurationSchema=Object.freeze({artwork:{type:'boolean',default:true,meaning:'Only the two ink panels toggle;physical carriers,all native faces,contacts,optics and actuation remain.'}});
export const DIM=Object.freeze({usb:[0,-12.02,1.7],grove:[0,-12.02,-2.95],header5:[7.62,-2.7,-4.52],header4:[-7.62,-3.97,-4.52],pcb:{centre:[0,.1,-.65],size:[20,19.4,.8]},ir:[-7.05,11.25,1.85]});
