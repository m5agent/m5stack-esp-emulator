/** Millimetres; +X right, +Y top (display end), +Z screen/front. */
export const spec={
 id:'oled',name:'OLED',sku:'U119',size:[24,56,8],nominalMm:[24,56,8],
 cadEnvelopeMm:[24.007047653198242,56.007047563791275,8],visualEnvelopeMm:[24.007047653198242,56.007047563791275,8],
 mountingHolesMm:[[-8,-16],[8,-16]],mountingHoleDiameterMm:4.85,
 display:{width:64,height:128,size:[14.7,29.42],centre:[0,8.15],z:3.04,windowMm:[16.4,31.9],nativeResolution:[128,64],orientation:'portrait; factory landscape raster rotated 90 degrees'},
 grove:{position:[0,-27.65,1.4],color:0xb91b25,widthMm:10,heightMm:5.2,pitchMm:2},
 source:{dimensions:'Official U119 drawing: 24×56×8mm, 16.4×31.9mm display window, 4.85mm mounting bores on 16mm pitch, 12mm above connector end; official product specification active area 14.7×29.42mm.',
  display:'Official U119 SH1107 black/white 128×64 OLED. The local portrait framebuffer exposes 64 columns×128 rows; monochrome luminance threshold is visual mapping only.',
  inferred:'PCB outline, retaining reliefs, thickness and placement; display stack/glass thickness and installed Z; active-area centring; FPC routing, electronics and magnets are concealed visual reconstruction, not production assembly STEP.'},
};
