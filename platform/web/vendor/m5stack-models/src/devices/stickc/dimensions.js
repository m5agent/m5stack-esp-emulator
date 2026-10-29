/** Exact SKU facts; all concealment dimensions and travel remain visual inferences. */
export const spec={"id": "stickc", "sku": "K016-C", "name": "M5StickC", "nominalMm": [25.5, 48.2, 13.7], "nativeEnvelopeMm": [24, 48, 13.5], "pixels": [80, 160], "driver": "ST7735SV / ST7735S", "batteryMah": 95};
export const DIM={display:{active:[10.9, 21.8],window:[11.7, 22.5],position:[0,8.0,6.07]},a:{position:[0,-13.6,6.35],travel:.22},b:{position:[11.6,8,0],travel:.16},power:{position:[-11.5,-15,2],travel:.15},usb:{position:[0,-24,3.1]},grove:{position:[0,-24,-3.6]}};
export const defaults={artwork:true,pixelEffect:true};
export const configurations=[{id:'complete',label:'Complete M5StickC',options:{}}];
export const configurationSchema={artwork:{type:'boolean',default:true},pixelEffect:{type:'boolean',default:true}};
export const HAT_PINS=['GND','5V OUT','G26','G36','G0','BAT','3V3','5V IN'];
export const GROVE_PINS=['GND','5V','G32','G33'];
