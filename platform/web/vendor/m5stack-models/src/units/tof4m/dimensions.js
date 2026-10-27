/** Millimetres; +X right, +Y top, +Z optical/front side. */
export const spec={
 id:'tof4m',name:'ToF4M',sku:'U172',size:[24,32,8],nominalMm:[24,32,8],
 cadEnvelopeMm:[24.00001049041748,32.000006675720215,7.999999761581421],visualEnvelopeMm:[24.00001049041748,32.000006675720215,8],
 mountY:-4,mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 opticalCentreMm:[0,8],sensorPackageMm:[4.9,2.5,1.56],
 grove:{position:[0,-15.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U172 product drawing: 24 × 32 × 8; 5 mm mounting bores with 16 mm pitch; shell retained from exact-SKU STL.',
  sensor:'ST VL53L1X DocID031281 Rev 2, February 2018, pages 1/4/25: optical LGA12 package 4.9 × 2.5 × 1.56 mm, 0.85 mm receiver lens and 0.70 mm emitter aperture beneath filter glass.',
  inferred:'Concealed PCB outline/thickness/position, package installed Z, filter well dimensions/color, lens/emitter depth, passives placement and Grove interiors are visual reconstructions from same-SKU photographs and schematic; no production assembly STEP.'},
};
