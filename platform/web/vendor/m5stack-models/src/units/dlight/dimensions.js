/** Millimetres: +X right, +Y away from Grove, +Z optical window. */
export const spec={
 id:'dlight',name:'Unit DLight',sku:'U136',size:[24,32,8],nominalMm:[24,32,8],vendorDimensionOrderMm:[32,24,8],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,8],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 grove:{position:[0,-15.8,1.4],color:0xb02218,pitchMm:2},
 opticalWindow:{position:[0,8,4],sizeMm:[2.9,5.7],sensorPosition:[0,8,2.15],packageMm:[1.6,3,.75]},
 source:{dimensions:'Exact U136 dimension drawing:32×24×8mm,16mm mounting pitch,nominalØ5mm mounting bores and2.9×5.7mm front optical opening. Complete3216-triangle native assembled shell at scale1 with one rigid transform.',electronics:'Own U136 schematic and bare-board photograph confirm BH1750FVI-TR optical sensing IC,HT7533 regulator,three resistors,four capacitors and two unpopulated4-pad P1/P2 rows. Official ROHM WSOF6I package drawing specifies1.6×3mm body and0.75mm maximum height.',inferred:'PCB outline and installed plane,hidden population placement,transparent package resin/internal die and lead rendering,Grove cavity/contact dimensions,fastener installation and print registration are visual reconstruction; no production-fit or optical-performance claim.'}
};
