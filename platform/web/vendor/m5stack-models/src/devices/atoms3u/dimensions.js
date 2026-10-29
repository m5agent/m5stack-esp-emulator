// MIT. K125 own native rigid pose; body source excludes USB-A male plug.
export const spec=Object.freeze({id:'atoms3u',name:'AtomS3U',sku:'K125',nominalMm:[20,53,10.3],officialDimensionsMm:[53,20,10.3],nativeMm:[20.706867218017578,40.32127244770527,10.300000429153442],soc:'ESP32-S3FN8',scope:'visual-only',grovePins:['GND','5V','G2','G1'],headerPins:['GND','5V','G14','G17','G42','G40'],userGpio:'G41',rgbGpio:'G35',irGpio:'G12',travelMm:{button:.16,reset:.12},nativePose:{rotationX:-Math.PI/2,translation:[-8.6,26.5,2.95]},dimensionConflict:'hero52x20x10;current table53x20x10.3;native body excludes reconstructed male USB plug'});
export const defaults=Object.freeze({artwork:true});
export const configurations=Object.freeze([{id:'complete',name:'完整USB主机与贴纸',options:{}}]);
export const configurationSchema=Object.freeze({artwork:{type:'boolean',default:true,meaning:'Only printed ink;native shells,adhesive carrier,physical RGB/microphone/IR,connectors and both inputs retained'}});
export const DIM=Object.freeze({usb:[0,-26.5,.4],grove:[0,26.52,1.95],header:[0,26.52,-2.4]});
