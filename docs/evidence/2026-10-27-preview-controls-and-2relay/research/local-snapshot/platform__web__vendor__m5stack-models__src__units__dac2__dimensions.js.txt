/** Millimetres; +X physical front-label right, +Y terminal end, +Z front. */
export const spec={
 id:'dac2',name:'Unit DAC2',sku:'U012-B',size:[24,32,10.2],nominalMm:[24,32,10.2],vendorDimensionOrderMm:[32,24,10.2],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,10.2],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,mountingHoleFacetSpanMm:[4.8753,5],
 grove:{position:[0,-15.65,1.4],color:0xab3442},
 terminal:{position:[0,16.04,2.6],pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['VOUT0','GND','VOUT1','GND'],pinNumbers:[4,3,2,1]},
 source:{dimensions:'Official product table: 32 × 24 × 10.2 mm. Runtime uses X/Y/Z order 24 × 32 × 10.2; unchanged native shell is 24 × 32 × 8 mm.',
  components:'Own SCH_UNIT_DAC2_V1.0: GP8413, TPS61040DBVR, HX6306P332MR, L1 10uH2520, D3 1N5819WS, D1/D2 TVS12V, physical A0/A1/A2 jumpers JP1/2/3 (0R/NC/NC). Exact product/package photos show burgundy Grove and orange fixed four-pole HT3.96 socket plus separate four-screw plug. No LEDs or external switches confirmed.',
  terminalOrder:'Own front print V0/G/V1/G maps left-to-right schematic P1 pins4/3/2/1. Grove front print G/V/D/C maps left-to-right GND/5V/SDA/SCL; Port pinGrid reverses because its bottom-facing local X axis points left.',
  inferred:'PCB envelope/Z/holes and concealed component placement, connector inner depths/contact lengths, removable plug profile and insertion clearance, screw head angles/recesses. These are appearance reconstructions; no production mating/fit tolerances or electrical conversion.'},
};
