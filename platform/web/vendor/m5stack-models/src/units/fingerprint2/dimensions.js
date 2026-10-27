/** Millimetres; +X right, +Y top, +Z sensor/front. */
export const spec={
 id:'fingerprint2',name:'Unit Fingerprint2',sku:'U203',size:[24,40,8],nominalMm:[24,40,8],vendorDimensionOrderMm:[40,24,8],
 cadEnvelopeMm:[23.99999237060547,40.00000047683716,8.000000238418579],
 mountY:-8,mountingHolesMm:[[-8,-8],[8,-8]],mountingHoleDiameterMm:4.85,
 sensor:{part:'A-K323CP',type:'capacitive semiconductor',center:[0,8],outerRadiusMm:9.65,faceRadiusMm:8.15,frontZ:3.93},
 grove:{position:[0,-19.65,1.4],color:0x0797ad,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U203 dimension drawing: 40×24×8 mm, sensor centre 28 mm from bottom, 4.85 mm mounting bores on 16 mm pitch. Native shell and power-guide triangles retained.',
  electronics:'Official U203 docs: STM32G031G8U6 and A-K323CP capacitive fingerprint module; seven-colour RGB ring. Official schematic LED1 BLUE. No independent mechanical button or touch-input API confirmed.',
  inferred:'Concealed PCB contour/thickness/Z, circular module envelope and interior construction, face radius/depth, ring cross-section, underside package positions, passives and connector internals reconstructed for appearance; no complete production assembly STEP or A-K323CP mechanical drawing.'}
};
