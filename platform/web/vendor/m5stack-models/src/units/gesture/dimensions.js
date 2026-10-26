/** Millimetres; +X right, +Y top, +Z optical/front side. */
export const spec={
 id:'gesture',name:'Gesture',sku:'U127',size:[24,32,8],nominalMm:[24,32,8],
 cadEnvelopeMm:[24.0006103515625,32,8],visualEnvelopeMm:[24.0006103515625,32,8],
 mountY:-4,mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 opticalCentreMm:[0,8],opticalOpeningMm:[12,6],
 grove:{position:[0,-15.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U127 product drawing: 24 × 32 × 8; 12 × 6 capsule opening centred 8 mm below top; 5 mm mounting bores with 16 mm pitch.',
  sensor:'PixArt PAJ7620U2 datasheet v1.2, 29 Feb 2016, figure 3: 5.2 × 3 mm package footprint, 1.88 mm body and 0.32 mm substrate in side view.',
  inferred:'PCB outline/thickness/position, package installed Z, shallow optical recesses, lens/emitter detailing, Grove internal walls and tails are appearance reconstructions; no production assembly STEP.'},
};
