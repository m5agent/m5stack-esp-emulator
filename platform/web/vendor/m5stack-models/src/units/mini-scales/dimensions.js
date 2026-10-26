// U177 Mini Scales. Millimetres; +Z weighing surface, +Y button, -Y Grove.
export const spec={
 id:'mini-scales',name:'Unit Mini Scales',sku:'U177',size:[24,40,18],
 nominalMm:[24,40,18],cadEnvelopeMm:[23.976123809814453,39.97612380981445,18],
 mountingHoles:[[-8,-16],[8,-16],[-8,16],[8,16]],mountingBoreMm:4.85,
 grove:{position:[0,-19.65,-4.65],face:'bottom',color:0xa62f3d},
 button:{position:[0,16,3],travel:.18,axis:[0,0,-1]},
 source:{dimensions:'Official U177 assembly drawing: 24 x 40 x 18 mm. Native STL filleted envelope is 23.976 x 39.976 x 18 mm; preserve it without rescaling.',motion:'Button travel is a small visual estimate. No load-cell deformation or weight-driven platform motion is asserted.'},
};
