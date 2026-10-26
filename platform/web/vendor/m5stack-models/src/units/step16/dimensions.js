/** Millimetres; +X right, +Y top, +Z rotary/front face. */
export const spec={
 id:'step16',name:'Unit Step16',sku:'U198',size:[24,32,16.9],nominalMm:[24,32,16.9],vendorDimensionOrderMm:[32,24,16.9],cadEnvelopeMm:[24,32,16.9],visualEnvelopeMm:[24,32,16.908],
 shellZ:[-4,4],mountingHolesMm:[[-8,-4],[8,-4]],mountingHoleDiameterMm:4.8,nativeBoreNote:'Source rear straight bore X span 4.85 mm; front X span 4.8 mm. Faceted cardinal wall radii 2.34–2.43 mm. Original source retained; not an independently verified drill specification.',
 grove:{position:[0,-15.65,1.4],color:0xb91229},rotation:{axis:[4,7,2.2],positions:16,detentDegrees:22.5},
 display:{center:[-6,7.3,2.75],fixedColor:0xffbb45,colorEvidence:'Warm yellow/amber appearance in exact U198 official lit photograph, not a measured spectrum or confirmed display part number.'},
 source:{dimensions:'Official U198 32 × 24 × 16.9 mm; normalized model +X/+Y/+Z envelope 24 × 32 × 16.9. Native shell depth 8 mm, complete native cap reaches Z12.9, rear reaches Z−4.',hardware:'Official schematic: SW1 GSMR-16, U1 STM32G031G8U6, FPC1 A-G/DP seven-segment, U2 ME6206A33XG, U3 WS2812C-2020, J1 I2C Grove, internal J4 SWD_5P.',inferred:'PCB layout/depth and package sizes, switch fixed body/shaft depth, display segment outlines/spacing and front-shell light diffusion are appearance reconstructions. Native shell, cap, RGB light-guide and their original assembled coordinates are retained; no production fit or optical model is claimed.'}
};
