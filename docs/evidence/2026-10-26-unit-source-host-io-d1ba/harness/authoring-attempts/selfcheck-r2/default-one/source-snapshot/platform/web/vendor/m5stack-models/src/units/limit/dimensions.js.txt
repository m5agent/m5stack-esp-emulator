// Official U145 dimensions and drawing: source-manifest.json (limit.referenceSources).
// +X right, +Y switch end, +Z front; millimetres. Lever travel is a visual estimate.
const restAngleDeg=8, pressedAngleDeg=0, length=16, thickness=.25;
const restAngle=restAngleDeg*Math.PI/180;
export const spec={
 id:'limit',name:'Unit Limit',sku:'U145',size:[24,32,9.5],nominalMm:[24,32,9.5],
 cadEnvelopeMm:[24,31.947620391845703,9.5],visualEnvelopeMm:[24,35,9.5],mountY:-4,
 grove:{position:[0,-15.65,.75],color:0x171d20},
 switch:{size:[20.4,10.6,6.2],position:[0,10.55,0]},
 lever:{length,thickness,width:5.2,restAngleDeg,pressedAngleDeg,
  pivot:[-7,19-length*Math.sin(restAngle)-thickness*Math.cos(restAngle),0],
  contactX:4,contactTravelMm:4*Math.sin(restAngle),
  axis:[0,0,1],
  evidence:'Official U145 drawing: 16 mm handle and 35 mm total at rest; axis and package shape from official front/top photos. Rest 8 degrees, pressed 0 degrees and contact travel are visual estimates, not rated switch travel.'},
};
