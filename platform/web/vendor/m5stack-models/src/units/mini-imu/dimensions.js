/** Millimetres; +X right, +Y top, +Z labeled front. */
export const spec={
 id:'mini-imu',name:'Unit Mini IMU',sku:'U095',sensor:'MPU6886',size:[24,24,8],nominalMm:[24,24,8],cadEnvelopeMm:[24,24,8],visualEnvelopeMm:[24,24,8.008],
 mountingHolesMm:[[-8,0],[8,0]],mountingHoleDiameterMm:5,
 grove:{position:[0,-11.65,1.4],color:0xb91229,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U095 dimension drawing: 24 × 24 × 8 mm, two 5 mm bores on 16 mm pitch at 12 mm above bottom, 10 × 5.2 mm Grove face.',
 electronics:'Official U095 documentation and schematic identify MPU6886, HT7533 and Q1/Q2 BSS138. Official PCB rear photo constrains scalloped board silhouette and fastening/solder holes.',
 inferred:'PCB outline depth and installed plane, concealed component package envelopes and installed XYZ, solder-pad details, screw shank and Grove interior depth/contact geometry are visual reconstructions; no populated assembly STEP or manufacturing datum is claimed.'}
};
