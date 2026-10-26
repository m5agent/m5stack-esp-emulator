/** Millimetres; +X right, +Y receiver end, +Z labeled front. */
export const spec={
 id:'laser-rx',name:'Unit Laser RX',sku:'U065',sensor:'ISO103',size:[24,32,8],nominalMm:[24,32,8],vendorDimensionOrderMm:[32,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,8],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 receiver:{position:[0,15.6,0],outward:[0,1,0],nativeApertureDiameterMm:3},
 grove:{position:[0,-15.65,1.4],color:0x20262d,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Exact U065 drawing: 24 × 32 × 8 mm in model axes, 5 mm mounting bores at 16 mm pitch, 3 mm receiver aperture on the opposite end from the Grove, and 10 × 5.2 mm Grove face.',electronics:'Exact U065 product documentation identifies ISO103. The original schematic has P1 Header3, R1 10K, R2 20K, C2 100nF and J1 GROVE_IO; there is no separate visible indicator LED.',inferred:'PCB outline/thickness/plane, concealed ISO103 package envelope and installed depth, receiver surface tint, lead bends, passive XYZ, screw shank and connector interior depth/contact geometry are visual reconstructions. Exact production populated assembly/BOM not supplied; no optical/electrical or manufacturing-fit claim.'}
};
