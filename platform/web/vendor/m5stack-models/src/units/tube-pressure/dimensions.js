/** Millimetres: +X right, +Y away from Grove, +Z single tube nozzle. */
export const spec={
 id:'tube-pressure',name:'Unit Tube Pressure',sku:'U130',size:[24,32,12.5],nominalMm:[24,32,12.5],vendorDimensionOrderMm:[32,24,12.5],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,12.5],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-15.75,1.35],color:0x17191a,pitchMm:2},
 tube:{position:[-.013,7.95,8.5],connector:'tube-3mm',outerDiameterMm:3,boreDiameterMm:1.3,boreDepthMm:8.1,face:'front'},
 source:{dimensions:'Own U130 dimension drawing: 24×32×8 mm complete native shell, one Ø3 mm nozzle extending4.5 mm above the shell, total12.5 mm. Native assembled front/rear retained at scale1 with one common translation. Mounting pitch16 mm and narrow boreØ4.85 mm.',electronics:'Own U130 schematic confirms HT7533, MCP-H10-B200KPPN and five capacitors, with direct analog output through black HY2.0-4P. Same-model bare-board photos show a single nozzle, six-lead sensor package and no external lamp, button or rotary part.',inferred:'PCB profile/installed plane, packages/population placement, nozzle bore/depth, internal sensing diaphragm, tiny molded sensor recesses, Grove cavity internals and fastener installation are visual reconstruction; no production-fit claim.'}
};
