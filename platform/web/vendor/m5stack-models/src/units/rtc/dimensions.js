/** Millimetres; +X right, +Y top, +Z labeled front. */
export const spec={
 id:'rtc',name:'Unit RTC',sku:'U126',sensor:'HYM8563',size:[24,48,8],nominalMm:[24,48,8],
 cadEnvelopeMm:[24,48,7.999999761581421],visualEnvelopeMm:[24,48,7.999999761581421],
 mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 grove:{position:[0,-23.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 battery:{diameterMm:12.5,thicknessMm:2,centreMm:[0,12,1.6],model:null,removable:false,scope:'Concealed unmarked button-cell reconstruction; dimensions, tabs and installed position are estimates, not battery BOM or a replaceability claim'},
 source:{dimensions:'Official U126 drawing: 48 × 24 × 8 mm; 5 mm mounting bores on 16 mm pitch, 12 mm above bottom; model axes 24 × 48 × 8.',
  electronics:'Official U126 product page specifies HYM8563 and 32.768 kHz crystal; schematic shows RTC8563 alternative U1/U2 footprints, HT7533, BAV74 and BT1 Battery. One HYM8563 package is populated visually; simultaneous RTC population is not asserted.',
  inferred:'PCB outline/thickness/installed plane, HYM8563 installed XYZ/package choice, crystal/regulator/passive placement, concealed generic button-cell diameter/thickness/position and fixed metallic support tabs, Grove interior and screw shank. Official external photographs and native shell constrain fit, but no populated PCB, battery BOM or assembly STEP was supplied.'},
};
