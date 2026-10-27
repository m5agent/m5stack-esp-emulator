/** Millimetres; +X right, +Y toward the stick end, +Z out of the thumb cap. */
export const spec={
 id:'joystick2',name:'Unit Joystick2',sku:'U024-V2',size:[24,40,23.9],nominalMm:[24,40,23.9],
 cadEnvelopeMm:[24.000001907348633,39.999999940395355,23.878649592399597],
 visualEnvelopeMm:[24.000001907348633,39.999999940395355,23.878649592399597],
 mountingHolesMm:[[-8,-8],[8,-8]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-19.65,1.4],color:0xb91b25},
 stick:{pivotMm:[-.013002395629882812,7.986999481916428,5.5],visualRangeDeg:[-18,18],pressTravelMm:.4,capDiameterMm:20},
 source:{dimensions:'Official U024-V2 product drawing: 40 × 24 × 23.9 mm, 20 mm thumb cap, 4.85 mm bores, 16 mm mounting pitch, hole row 12 mm above bottom.',
  motion:'Official product confirms Hall X/Y tilt and Z-axis button. Tilt limits, installed pivot and switch travel are not dimensioned; ±18 degrees and 0.4 mm travel are viewer-only approximations, not hardware limits or calibration.',
  inferred:'Concealed PCB outline/thickness/installed Z, JH16 fixed package, gimbal, shaft, hidden electronics, screw shank and Grove interiors reconstructed from the same-SKU photos. No production assembly STEP.'},
};
