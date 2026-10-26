/** Millimetres: +X right, +Y away from Grove, +Z vented front. Exact U090-B revision. */
export const spec={
 id:'mini-bps-v11',name:'Unit Mini BPS v1.1',sku:'U090-B',size:[24,24,8],nominalMm:[24,24,8],vendorDimensionOrderMm:[24,24,8],cadEnvelopeMm:[24,24,8],visualEnvelopeMm:[24,24,8.04],
 mountingHolesMm:[[-8,0],[8,0]],mountingHoleDiameterMm:5,
 grove:{position:[0,-11.8,1.4],color:0xb02218,pitchMm:2},
 airSlots:{centersMm:[[-1,8.5],[1,8.5]],sensorPositionMm:[0,8.5,1.65],packageMm:[2,2.5,.85],packageRotationZ:Math.PI/2,ventCenterPackageMm:[-.46,.71],ventDiameterMm:.2},
 source:{dimensions:'Exact U090-B own native assembled shell4162 triangles at scale1 and own dimension drawing agree24×24×8mm,16mm mounting pitch and nominalØ5mm holes. EOL U090 BMP28024×24×13mm excluded.',electronics:'Exact U090-B product/schematic:QMP6988,HT7533,two BSS138,four4.7k resistors,C1/C2/C4 and red HY2.0-4P. QST13-52-13 RevC p11 specifies2.00×2.50×0.85mm LGA9 package,1.82×2.32mm cap andØ0.20mm port at[-.46,.71]in package coordinates.',inferred:'PCB outline/installed plane,concealed population placement,QMP package orientation beneath two shell slots,internal die/cavity,HT7533 package rendering,Grove internals,fastener installation,adhesive thickness and print registration are appearance reconstruction. No production-fit claim.'}
};
