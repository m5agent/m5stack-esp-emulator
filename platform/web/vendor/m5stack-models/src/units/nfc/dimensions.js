/** Millimetres; +X right, +Y top, +Z blue NFC front. */
export const spec={
 id:'nfc',name:'Unit NFC',sku:'U216',chip:'ST25R3916-AQWT',size:[24,48,8],nominalMm:[24,48,8],vendorDimensionOrderMm:[48,24,8],cadEnvelopeMm:[24,48,8],visualEnvelopeMm:[24,48,8],
 mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,mountingHoleFacetSpanMm:[4.8753,5],
 grove:{position:[0,-23.65,1.4],widthMm:10,heightMm:5.2,color:0xb91229,pitchMm:2},
 artwork:{front:{sizeMm:[17.7,27.7],positionMm:[0,6.5,3.8]},back:{sizeMm:[15.9,27.9],positionMm:[0,6.5,-3.8]}},
 source:{dimensions:'Exact U216 official model-size drawing: 24 × 48 × 8 mm, two nominal 5 mm bores on 16 mm pitch; common native CAD translation only.',
 electronics:'Own U216 schematic identifies U1 ST25R3916-AQWT, U3 TPAP7343D-33FS4, X1 27.12 MHz, ANT1 planar antenna and differential RF matching network. Own photos show red Grove and no external light, button or joint.',
 inferred:'Concealed PCB outline/Z/thickness, package registration, antenna winding trace dimensions/turn count and matching placement, screw dimensions and Grove contact depths are appearance reconstructions. No assembly STEP, exact antenna layout or production fit claimed.'}
};
