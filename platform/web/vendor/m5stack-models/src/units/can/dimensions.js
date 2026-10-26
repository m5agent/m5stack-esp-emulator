/** Millimetres; +X right, +Y terminal-facing end, +Z front. */
export const spec={
 id:'can',name:'Unit CAN',sku:'U085',size:[24,56,10.2],nominalMm:[24,56,10.2],vendorDimensionOrderMm:[56,24,10.2],cadEnvelopeMm:[24.0000629425,56.0000316922,8],
 mountingHolesMm:[[-8,-16],[8,-16]],mountingHoleDiameterMm:4.85,
 grove:{position:[0,-27.6,.3],color:0xe4e6df},
 terminal:{position:[0,27.8,2.7],pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['CAN_H','CAN_L','NC','SHIELD']},
 led:{position:[-7.35,-22.5,-.7],color:0xffffff},
 source:{dimensions:'Official U085 drawing/product: 56 × 24 × 10.2 mm; native shell depth 8 mm, Grove 10 × 5.2 mm, Ø4.85 LEGO bores at 16 mm pitch and 12 mm from Grove end.',
  components:'Official schematic SCH_UNIT_ISOCAN_v1.1: CA-IS3050G isolated CAN transceiver, B0505ST16-W5 DC-DC module, MST5333 regulator, white LED1; JP1 pin4 H, pin3 L, pin2 NC, pin1 SHIELD. Product package and exact-SKU photographs confirm a separate HT/VH3.96-4P screw plug.',
  inferred:'PCB shape/Z/thickness, component population and concealed locations; terminal/contact/plug details and installed fit; Grove internals; LED light-guide depth; screw recess geometry. Actual terminal visible front order H/L/NC/G is retained. No production-fit claim, termination resistor, electronics or firmware simulation.'},
};
