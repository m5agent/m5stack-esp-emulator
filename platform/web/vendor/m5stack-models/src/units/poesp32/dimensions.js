/** Millimetres; +X right, +Y RJ45 end, +Z printed front. */
export const spec={
 id:'poesp32',name:'PoESP32',sku:'U138',size:[26,72,19.2],nominalMm:[26,72,19.2],vendorDimensionOrderMm:[72,26,19.2],cadEnvelopeMm:[26,72,19.2],visualEnvelopeMm:[26,72.15,19.2],
 mountingHolesMm:[[-8,-24],[8,-24]],mountingHoleDiameterMm:3.2,mountingCounterboreDiameterMm:4.85,
 grove:{position:[0,-35.65,-5.3],color:0x0498b3,heightMm:5.2,pitchMm:2},
 ethernet:{position:[0,36.15,-1.35],connector:'rj45-8p8c',widthMm:15.8,heightMm:12.9,depthMm:21.4},
 leds:[{id:'link-led',color:0xffd400,localPosition:[6.0,4.95,-.35]},{id:'activity-led',color:0x42d51b,localPosition:[-6.0,4.95,-.35]}],
 source:{dimensions:'Official Unit PoESP32 U138 product specifications: 72×26×19.2 mm. Complete original STL shell pair agrees with this envelope.',
 hardware:'Official schematic: ESP-WROOM-32U/D U3, IP101G U2, HBJ-6308ANLF magnetic RJ45 U1 with yellow/green LEDs, WC-PD06H050A PoE M2, AMS1117-3.3 VR1, UART Grove J1, internal download J2, P1/P2 5×2 interboard pair. Official assembled pictures show no exposed button or USB.',
 inferred:'PCB contours, scalloped boss clearances, layer spacing, installed component transforms, hidden packages, power transformer/capacitor envelopes, RJ45 internal stepped cavity/contact bends/shield spring details and connector protrusion are reconstructed from original apertures and official photos. No complete populated production assembly STEP.'}
};
