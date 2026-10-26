/** Millimetres; +X front-label right, +Y terminal end, +Z front. */
export const spec={
 id:'adc-v11',name:'Unit ADC v1.1',sku:'U013-V11',size:[24,32,10.2],nominalMm:[24,32,10.2],vendorDimensionOrderMm:[32,24,10.2],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,10.2],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,mountingHoleFacetSpanMm:[4.8753,5],
 grove:{position:[0,-15.65,1.4],color:0xab3442},
 terminal:{position:[0,16.04,2.6],pitch:3.96,pinX:[-1.98,1.98],names:['VIN+','GND'],pinNumbers:[1,2]},
 source:{dimensions:'Official U013-V11 table32×24×10.2mm, runtime X/Y/Z24×32×10.2. Complete native shell24×32×8mm retained unchanged.',
 components:'Own Sch_UNIT_ADC_v1.1: U2 ADS1110, U1 LM358DR2G, U3/U4 HT7533, divider510K/100K. Exact own photos show burgundy Grove and orange fixed HT3.96-2P socket plus a supplied detachable2-screw plug. No external LED/button confirmed.',
 terminalOrder:'Front own print + / − maps left-to-right P1 pins1 / 2. Grove GND/5V/SDA/SCL physical order follows own schematic J1 pins4/3/2/1; bottom-facing local X is reversed.',
 inferred:'PCB outline/thickness/Z and concealed packages, fixed connector inner dimensions, plug mating clearance/contact clamp geometry, screw profile, redraw font/color/registration. Appearance only, no production fit or electrical behavior.'},
};
