/** Millimetres: +X right, +Y top/IO, +Z raised blank front. */
export const spec={
 id:'extio2',name:'Unit EXT.IO2',sku:'U011-B',sensor:'STM32F030F4P6',size:[24,32,10.2],nominalMm:[24,32,10.2],vendorDimensionOrderMm:[32,24,10.2],
 cadEnvelopeMm:[24,32,10.200000047683716],visualEnvelopeMm:[24,32,10.200000047683716],
 mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:5,
 grove:{position:[0,-15.65,.3],color:0xb52223,widthMm:10,heightMm:5.2,pitchMm:2},
 io:{position:[0,15.7,2.31],connector:'header-2x5-2.54mm-male',pitchMm:2.54,columns:5,rows:2,tipY:15.7,rowZ:[3.58,1.04],columnX:[-5.08,-2.54,0,2.54,5.08]},
 source:{dimensions:'Official U011-B drawing labels 32 × 24 mm, 8 mm base depth and 2.2 mm raised front, 5 mm mounting bores at 16 mm pitch and 12 mm above bottom; model axes 24 × 32 × 10.2.',
  electronics:'U011-B schematic: U1 STM32F030F4P6, U2 HT7533, P2 2×5 / 2.54 mm IO0–7/VCC/GND, J1 I2C Grove; P1 is five-node SWD connection. Exact-product photos show top male right-angle P2, visible PCB/MCU and red open-top Grove; no exterior buttons or LEDs.',
  inferred:'PCB outline/plane/thickness, package installed locations/envelopes, bent P2 pin bends/carrier and recessed solder ends, concealed SWD test-pad placement/population, passives, connector interior, screw shank, label print registration are visual reconstructions, not production assembly or electrical tolerances.'},
};
