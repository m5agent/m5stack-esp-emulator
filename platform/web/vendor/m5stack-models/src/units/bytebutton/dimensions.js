/** Millimetres; +X right, +Y top (CH7), +Z operating face. */
export const CHANNELS=Array.from({length:8},(_,i)=>({number:i+1,channel:i,y:-23.8+6.8*i,button:`press-${i+1}`,rgb:`rgb-${i+1}`}));
export const spec={
 id:'bytebutton',name:'Unit ByteButton',sku:'U192',size:[24,88,14],nominalMm:[24,88,12],cadEnvelopeMm:[24,88,12],visualEnvelopeMm:[24,88,14],
 mountingHolesMm:[[-8,-32],[8,-32],[-8,32],[8,32]],mountingHoleDiameterMm:4.85,
 button:{radiusMm:2.05,positionZ:6,topZ:8,travelMm:.2,axis:[0,0,-1]},
 grove:{position:[0,-43.8,-.6],outputPosition:[0,43.8,-.6],color:0xb52635,widthMm:10,heightMm:5.2,depthMm:6.5,pitchMm:2},
 source:{dimensions:'Official U192 product and dimension drawing: 88×24×12 mm housing, 64 mm mounting-row pitch, 16 mm transverse pitch, 4.85 mm mounting bores, eight 4.4 mm button apertures on 6.8 mm pitch; drawing separately shows 2 mm cap projection.',
 controls:'Eight momentary tactile keys, nine WS2812C-2020 RGB LEDs and two parallel I2C Grove connectors; S1–S8 packages 3×4×2.5 / 1.6 N from official schematic.',
 inferred:'Cap diameter, underside/stem, 0.2 mm visual travel, PCB outline/thickness, clearances, package installed Z, connector interiors and concealed electronics are visual reconstructions, not production assembly geometry or tolerances.'},
};
