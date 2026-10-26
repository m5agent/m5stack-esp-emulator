/** Millimetres; +X right, +Y top, +Z ventilated sensor/front side. */
export const spec={
 id:'co2',name:'CO2',sku:'U103',sensor:'SCD40',size:[24,48,16],nominalMm:[24,48,16],
 cadEnvelopeMm:[24,48,16],visualEnvelopeMm:[24,48,16],
 mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 sensorCentreMm:[0,8],sensorPackageMm:[10.1,10.1,6.3],
 grove:{position:[0,-23.65,-2.6],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U103 drawing: 48 × 24 × 16; model axes 24 × 48 × 16. Native assembled shell retained without scaling; mount bores 5 mm with 16 mm pitch, 12 mm above bottom.',
  sensor:'Sensirion SCD4x datasheet v1.2, May 2022, section 4.1 page 20: 10.1 × 10.1 substrate, 0.8 mm base and 5.5 mm can rise; 8.5 to 7.8 mm can width.',
  inferred:'PCB outline/thickness/Z, sensor installed location, rounded can transition, membrane outline, minor power components and Grove internals reconstructed for appearance from same-SKU photos, schematic and cavity clearances. No production assembly STEP.'},
};
