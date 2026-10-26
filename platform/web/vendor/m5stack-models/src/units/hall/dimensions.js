/** Millimetres; +X right, +Y top, +Z labeled front. */
export const spec={
 id:'hall',name:'Unit Hall',sku:'U084',sensor:'A3144E × 3',size:[24,32,8],nominalMm:[24,32,8],vendorDimensionOrderMm:[32,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,8],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 grove:{position:[0,-15.65,1.4],color:0x20262d,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U084 dimension drawing: 24 × 32 × 8 mm in model axes, two 5 mm bores on 16 mm pitch at 12 mm above bottom, 10 × 5.2 mm Grove face.',electronics:'Official U084 documentation and original schematic identify 3 × A3144E, 74HC08D, HT7533, D1 red 0603, 4 resistors and 7 capacitors. Exact official exterior photos show the black Grove and two printed faces, but no discrete LED lens/opening.',inferred:'PCB outline, thickness and installed plane, concealed component package envelopes/XYZ, solder detail, screw shank and connector interior depth/contact geometry are visual reconstructions. No populated assembly STEP, LED optical path, production PCB placement or manufacturing fit is claimed.'}
};
