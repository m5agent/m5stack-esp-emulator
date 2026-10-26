/** Millimetres; +X right, +Y top, +Z LCD/front side. */
export const spec={
 id:'lcd',name:'Unit LCD',sku:'U120',size:[24,48,8],nominalMm:[24,48,8],
 cadEnvelopeMm:[24.027999877929688,48.01752379536629,8],
 mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:4.85,
 lcd:{resolution:[135,240],activeMm:[14.8635,24.912],openingMm:[14.8,24.8],centreMm:[0,8.7],surfaceZ:3.68},
 grove:{position:[0,-23.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U120 drawing: 24 × 48 × 8; 14.8 × 24.8 aperture bottom 20.3 from base; two Ø4.85 mounting bores at 16 mm pitch, 12 from base.',display:'Official U120 product: 135 × 240 ST7789V2, pixel pitch 0.1101 × 0.1038 mm. Active area is pixel pitch multiplied by resolution.',inferred:'Installed screen Z, screen backing/glass border, PCB and component layout, magnet depth, FPC and Grove internal details are reconstructed appearance; no production PCB/assembly STEP.'},
};
