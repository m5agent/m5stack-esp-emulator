/** Engineering frame: +X right, +Y top, +Z front; millimetres. */
export const spec={
 id:'gps-v11',name:'GPS v1.1',sku:'U032-V11',
 size:[24,48,8],nominalMm:[24,48,8],cadEnvelopeMm:[24,48,8],visualEnvelopeMm:[24,48,8],
 mountY:-12,mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 grove:{position:[0,-23.65,1.4],color:0x00a5b9,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U032-V11 product table and module_size.jpg; normalized from 48×24×8 to X×Y×Z.',
  holes:'Official drawing: two 5 mm bores, 16 mm pitch, 12 mm from bottom.',
  connector:'Official drawing: 10×5.2 mm HY2.0-4P; cyan open-top socket in exact-version product photos.',
  inferred:'PCB thickness, hidden antenna/module envelope, connector internal wall dimensions and mounting screw detail are visual approximations, not a production-fit assembly.'},
};
