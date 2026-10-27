/** Millimetres; +X right, +Y speaker end, +Z front grille. */
export const spec={
 id:'synth',name:'Synth',sku:'U178',size:[24,48,16],nominalMm:[24,48,16],vendorDimensionOrderMm:[48,24,16],
 cadEnvelopeMm:[24,48,16],visualEnvelopeMm:[24,48,16],mountingHolesMm:[[-8,-12],[8,-12]],mountingHoleDiameterMm:5,
 grove:{position:[0,-23.65,-3.8],color:0x029fb8,widthMm:10,heightMm:5.2,pitchMm:2},
 speaker:{centerMm:[0,8,3.8],frameMm:[20.2,28,1],impedanceOhm:8,powerW:1},
 source:{dimensions:'Official U178 dimension drawing and complete assembled native source shell: 48×24×16 mm, two 5 mm mounting holes at 16 mm pitch and 12 mm from Grove end.',
  electronics:'Official Sch_Unit_Synth_V1.1: SAM2695 U4, NS4150B U2, ME6211A33M3G-N U1, CN809R U3, external crystal X1, internal 1.25 mm 2P speaker socket J2, LED2/LED3. Grove J1: GND,5V_IN,SYS_MIDI,NC. No external DIN/3.5mm/USB, controls or LED windows in exact U178 photos/drawing.',
  inferred:'PCB outline/thickness/installed Z, concealed package locations/dimensions, speaker rectangular frame/cone/basket/magnet dimensions and installed datums, internal J2 placement/orientation/contact dimensions and fixed lead routing are visual reconstructions; no complete production PCB/assembled speaker STEP.'},
};
