/** Millimetres: +X right, +Y away from Grove, +Z optical window. */
export const spec={
 id:'tmos-pir',name:'Unit TMOS PIR',sku:'U185',size:[24,32,8],nominalMm:[24,32,8],vendorDimensionOrderMm:[32,24,5.2],drawingDimensionOrderMm:[32,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,8],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 grove:{position:[0,-15.8,1.4],color:0xb02218,pitchMm:2},
 opticalWindow:{position:[0,8,4],sizeMm:[12,6],sensorPosition:[0,8,1.65],packageMm:[4.2,3.2,1.455],filterCenterMm:[-.7,-.28],filterSizeMm:[1.55,1.55]},
 dimensionConflict:{reportedTableMm:[32,24,5.2],nativeAndDrawingMm:[32,24,8],feedbackId:'052dc71fcd6b48e5a17651bb4f438896',decision:'Keep native complete shell at scale1;5.2mm in own drawing spans connector height,not overall8mm thickness. No production-fit claim.'},
 source:{dimensions:'Exact U185 native assembled shell3490 triangles at scale1 and own drawing agree24×32×8mm,16mm mounting pitch and nominalØ5mm holes. Product table instead lists32×24×5.2mm; discrepancy preserved explicitly.',electronics:'Own U185 schematic confirms STHS34PF80TR,XC6228D332VR-G,SRV05-4 and passive population. ST DS13916 Rev2 via official chip MCP specifies3.2×4.2×1.455mm maximum OLGA-10L package and integrated silicon infrared filter.',inferred:'PCB outline/plane and concealed population placement,package lid/rim/filter/internal support rendering,filter subdimensions,Grove internals,fastener installation and print registration are appearance reconstruction.'}
};
