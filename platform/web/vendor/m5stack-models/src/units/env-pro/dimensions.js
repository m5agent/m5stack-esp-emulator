/** Millimetres; +X right, +Y top, +Z ventilated front. */
export const spec={
 id:'env-pro',name:'ENV Pro',sku:'U169',sensor:'BME688',size:[24,32,8],nominalMm:[24,32,8],
 cadEnvelopeMm:[24,32,7.9999998807907104],visualEnvelopeMm:[24,32,7.9999998807907104],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 sensorCentreMm:[0,8],sensorPackageMm:[3,3,.93],sensorVent:{centreMm:[.6,-.6],diameterMm:.35},
 grove:{position:[0,-15.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U169 drawing: 32 × 24 × 8 mm, 5 mm mounting bores on 16 mm pitch, 12 mm above bottom; model axes 24 × 32 × 8.',
  sensor:'Bosch BME688 datasheet BST-BME688-DS000-01 revision 1.1 July 2022, page 53 picture 16: 3 × 3 × 0.93 mm metal-lid LGA; 2.8 mm lid width, 0.35 mm gas vent 0.9 mm from lower/right package edge.',
  inferred:'PCB outline/thickness/installed plane, sensor XYZ and orientation, C-shaped thermal-isolation cutout, cap cross-section, concealed passives, regulator, protection packages and Grove interior are reconstructed from exact U169 photos, schematic and shell clearances. No production PCB or complete assembly STEP.'},
};
