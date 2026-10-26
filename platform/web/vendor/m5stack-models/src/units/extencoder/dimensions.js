/** Millimetres: +X front-label right, +Y five-pole end, +Z labeled front. */
export const spec={
 id:'extencoder',name:'Unit ExtEncoder',sku:'U161',size:[24,32,10.7],nominalMm:[24,32,10.7],vendorDimensionOrderMm:[32,24,10.7],cadEnvelopeMm:[24,32,8],visualEnvelopeMm:[24,32,10.7],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,mountingHoleFacetSpanMm:[4.8753,5],
 grove:{position:[0,-15.65,1.4],color:0xab3442},
 encoder:{position:[0,16,2.4],connector:'vh2.54-5p',pitchMm:2.54,pinX:[-5.08,-2.54,0,2.54,5.08],names:['GND','5V','Z1','B1','A1'],pinNumbers:[5,4,3,2,1],bodyMm:[14.5,10.2,7.3]},
 source:{dimensions:'Own official dimension drawing and table: vendor order 32 × 24 × 10.7 mm, shell 8 mm, fixed connector width14.5 and plan length10.2. Model axis order X/Y/Z =24/32/10.7. Whole native shell kept at scale1.',
 components:'Own schematic: U1 STM32F030F4P6, U2 HX6306, D1 TVS5V, RC input network, fixed J2 SWD pads and J1 Grove. No external crystal, visible LED, switch, motor or integral rotary encoder.',
 pinOrder:'Front connector print G/5V/Z/B/A left-to-right is P6 pins5/4/3/2/1. Own schematic P6 pins1/2/3/4/5 =A1/B1/Z1/VCC_5V/GND. Grove print GND/5V/SDA/SCL and conventional colored wires are metadata only.',
 inferred:'PCB outline/Z/thickness, hidden component placement and leads, connector cavity depths, contact bends, removable screw-terminal plug dimensions and insertion clearance, screw recess and angle, artwork registration. These are visual reconstruction estimates, not manufacturing or fit tolerances.'}
};
