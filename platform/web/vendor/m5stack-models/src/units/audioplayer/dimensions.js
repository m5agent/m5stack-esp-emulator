/** Millimetres; +X right, +Y 3.5 mm audio end, +Z printed front. */
export const spec={
 id:'audioplayer',name:'AudioPlayer',sku:'U197',size:[24,48,8],nominalMm:[24,48,8],vendorDimensionOrderMm:[48,24,8],
 cadEnvelopeMm:[24,48,8],visualEnvelopeMm:[24,48.4,8],mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-23.65,1.4],color:0x0498b3,widthMm:10,heightMm:5.2,pitchMm:2},
 audio:{position:[0,24.4,1.15],mouthDiameterMm:3.5,insertionDepthMm:11.5},
 sd:{position:[11.85,11.7,-3.3],slotMm:[12.0,1.0],connector:'5033981892'},
 led:{id:'busy-led',color:0x148bff,position:[7.9,-21.0,3.9]},
 source:{dimensions:'Official U197 dimension drawing and complete native source assembly: 48×24×8 mm, 4.85 mm mounting bores on 16 mm pitch, 12 mm from Grove end.',
  electronics:'Official schematic: N9301 U1, Molex 5033981892 microSD U2, PJ-342 3.5 mm stereo CN1, Grove UART J1 and one blue 0603 BUSY LED D1. No physical buttons, USB, built-in speaker or knob documented or visible.',
  inferred:'PCB outline/thickness/Z, N9301 package/placement, passive locations, PJ-342 body and contact geometry, jack protrusion, microSD connector envelope and contacts, light-guide excitation and all concealed assembly datums reconstructed from exact U197 photographs/native apertures; no complete PCB/production assembly STEP.'},
};
