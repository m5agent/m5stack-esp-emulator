/** Millimetres; +X right, +Y XLR-facing end, +Z front/component side. */
export const spec={
 id:'dmx',name:'Unit DMX',sku:'U183',size:[24,51.6,32],nominalMm:[24,51.6,32],vendorDimensionOrderMm:[51.6,24,32],
 cadEnvelopeMm:[23.98604,47.98604,19],visualEnvelopeMm:[23.98604,51.59302,32],
 mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-23.65,.6],widthMm:10,heightMm:5.2,color:0x06b4c9},
 xlr:{position:[0,24,11.7],outerRadiusMm:10.7,innerRadiusMm:9.9,insertRadiusMm:7.65,contactCentersMm:[[-3.8,.7],[3.8,.7],[0,-3.3]],contactHoleRadiusMm:1.35},
 termination:{position:[-8,-3.3,3.1],axis:[0,1,0],travelMm:1.8},
 release:{position:[0,0,0],axis:[0,-1,0],travelMm:1},
 source:{dimensions:'Official U183 drawing: shell 48 × 24 × 19 mm, total length 51.6 mm and depth 32 mm, XLR axis 15.7 mm from rear, mounting Ø4.85 bores at 16 mm pitch and 12 mm from Grove end.',
  components:'Official schematic: CA-IS3092W, SS-1260 switch with 120R, XLR-328P female 3-contact receptacle, D4 RED LED. Product photographs show fixed PCB-mounted receptacle, metal PUSH release, cyan Grove and front indicator.',
  inferred:'PCB profile/thickness/installed Z; connector barrel, female-contact dimensions, insert/ear geometry and concealed electronic packages; SS-1260 cap dimensions and 1.8 mm detents; release shape and 1 mm axial travel; indicator lens dimensions. Native complete shell pair retained with one rigid translation. No complete PCB/XLR assembly STEP or switch/latch mechanical travel drawing.'},
};
