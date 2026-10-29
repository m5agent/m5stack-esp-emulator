/** Exact SKU facts; all concealment dimensions and travel remain visual inferences. */
export const spec={"id": "stickc-plus", "sku": "K016-P", "name": "M5StickC Plus", "nominalMm": [24, 48, 13.5], "nativeEnvelopeMm": [24, 48, 13.5], "pixels": [135, 240], "driver": "ST7789V2", "batteryMah": 120};
export const DIM={display:{active:[14.75, 24.95],window:[15.4, 26.0],position:[0,8.1,6.55]},a:{position:[0,-13.6,6.35],travel:.22},b:{position:[11.6,8,0],travel:.16},power:{position:[-11.5,-15,2],travel:.15},usb:{position:[0,-24,3.1]},grove:{position:[0,-24,-3.6]}};
export const defaults={artwork:true,pixelEffect:true};
export const configurations=[{id:'complete',label:'Complete M5StickC Plus',options:{}}];
export const configurationSchema={artwork:{type:'boolean',default:true},pixelEffect:{type:'boolean',default:true}};
export const HAT_PINS=['GND','5V OUT','G26','G36/G25','G0','BAT','3V3','5V IN'];
export const GROVE_PINS=['GND','5V','G32','G33'];
