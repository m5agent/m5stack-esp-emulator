/** Millimetres; +X right, +Y long/top end, +Z switch/front side. */
export const CHANNELS=Array.from({length:8},(_,i)=>({number:i+1,physicalChannel:i,y:-23.8+i*6.8,switch:'switch-'+(i+1),led:'rgb-'+(i+1)}));
export const spec={
 id:'byteswitch',name:'Unit ByteSwitch',sku:'U191',size:[24,88,19.6],nominalMm:[24,88,19.6],vendorDimensionOrderMm:[88,24,19.6],
 cadEnvelopeMm:[24,88,12],visualEnvelopeMm:[24,88,19.6],
 mountingHolesMm:[[-8,-32],[8,-32],[-8,32],[8,32]],mountingHoleDiameterMm:4.85,
 grove:{input:[0,-43.65,-.6],output:[0,43.65,-.6],widthMm:10,heightMm:5.2,pitchMm:2},
 toggle:{pivotZ:6.6,rodLength:6.9,rodRadius:.62,anglesDeg:[-22.5,22.5],axis:[0,1,0],sweepEnvelopeMm:[24,88,20.12]},
 source:{dimensions:'Official U191 product dimension drawing: 88 × 24 × 19.6 mm, four Ø4.85 mounting bores at 16 × 64 mm pitch, 12 mm raised shell platform.',
  control:'Official product and schematic: eight independent DPDT 6-pin toggle switches, nine WS2812C-2020 RGB, two Grove I2C sockets.',
  inferred:'PCB outline/thickness/installed Z, toggle package/pivot/lever profile, ±22.5 degree detents, native lightpipe illumination mapping, concealed electronics and socket interior dimensions are visual reconstruction. The native shell/lightpipe geometry and assembled relative transforms remain unchanged. No production assembly STEP or switch mechanical drawing.'},
};
