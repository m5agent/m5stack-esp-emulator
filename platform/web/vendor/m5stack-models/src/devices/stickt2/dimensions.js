/** K016-T2 own source/drawing; hidden installation and visual travel inferred. */
export const spec={id:'stickt2',sku:'K016-T2',name:'M5StickT2',nominalMm:[24,48,24],nativeEnvelopeMm:[30.4,48,23.9],pixels:[135,240],driver:'ST7789',batteryMah:300,thermalCamera:'Lepton3.0;passive visual optical module only'};
export const DIM={display:{active:[14.8,24.86],window:[15.6,26.2],position:[0,8.0,11.36]},a:{position:[0,-16,11.95],travel:.22},b:{position:[11.96,9,0],travel:.16},power:{position:[-11.95,-13.5,0],travel:.15},wheel:{position:[12.12,-8,-4.65],radius:3.45,travel:.18},usb:{position:[0,-24,1.8],depth:5.0},grove:{position:[0,-24,-2.9],depth:5.8}};
export const GROVE_PINS=['GND','5V','G32','G33'];
export const defaults={artwork:true,pixelEffect:true};export const configurations=[{id:'complete',label:'Complete M5StickT2',options:{}}];export const configurationSchema={artwork:{type:'boolean',default:true},pixelEffect:{type:'boolean',default:true}};
