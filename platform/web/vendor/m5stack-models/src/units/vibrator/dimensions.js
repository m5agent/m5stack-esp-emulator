/** Millimetres; +X right, +Y toward the exposed eccentric, +Z front. */
export const spec={
 id:'vibrator',name:'Vibrator',sku:'U059',size:[24,32,12.2],nominalMm:[24,32,8],
 cadEnvelopeMm:[24.000015258789062,32,12.199999809265137],visualEnvelopeMm:[24.000015258789062,37,12.199999809265137],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 grove:{position:[0,-15.65,1.4],color:0x202529,widthMm:10,heightMm:5.2,pitchMm:2},
 shaft:{axis:[0,1,0],centreMm:[0,15.65,2.2],diameterMm:1},
 eccentric:{diameterMm:7,lengthMm:5,axialStartMm:16,centreOffsetMm:[.8,0,0]},
 source:{dimensions:'Official U059 drawing: 32 × 24 mm base, 8 mm base depth, 5 mm exposed eccentric length and 7 mm diameter. Native motor cover gives 12.2 mm total CAD depth. Mounting bores 5 mm on 16 mm pitch, 12 mm above bottom.',
 inferred:'N20 installed can cross-section and length, PCB outline/thickness/plane, front bearing and shaft diameter/axis centre, eccentric shaft-bore offset and radial retaining screw, concealed passives, screw shank and Grove internals are reconstructed from exact U059 photos and native shell clearances; no complete manufacturing assembly.'},
};
