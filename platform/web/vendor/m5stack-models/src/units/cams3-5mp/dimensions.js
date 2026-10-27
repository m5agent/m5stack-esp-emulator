/** Millimetres; +X right, +Y antenna end, +Z fixed camera front. */
export const spec={
 id:'cams3-5mp',name:'CamS3-5MP',sku:'U174-B',size:[24,40,11],nominalMm:[24,40,11],vendorDimensionOrderMm:[40,24,11],
 cadEnvelopeMm:[24.055862,40.055861,11],visualEnvelopeMm:[24.055862,40.055861,11],mountingHolesMm:[],
 grove:{position:[0,-19.65,.1],pins:['GND','5V','G20 TX/D+','G19 RX/D-'],color:0xe3e6e2},
 sd:{position:[0,-19.85,-3.8],slotMm:[12,1.1]},
 headers:{x:[-8.89,8.89],y:-13.8,pitchMm:2.54,pins:[['EN','G0','GND'],['G44','G43','5V']]},
 camera:{center:[-.00524,6.50524,0],sensor:'PY260',focus:'fixed',focalDistanceM:.6,barrelRadiusMm:3.52,frontZ:5.35},
 led:{id:'status-led',color:0x148bff,position:[-6,-17.2,.7]},
 source:{dimensions:'Exact U174-B official dimension drawing: 40×24×11 mm; source CAD retains small tessellated XY tolerance beyond nominal. No native mounting bores; four side clip reliefs retained.',
  electronics:'Official U174-B page: PY260 fixed-focus camera, ESP32-S3-WROOM-1-N16R8, microSD, PDM microphone, one programmable blue G14 LED, Grove G20/G19 USB/UART. Exact photos/drawing show two 1×3 female headers; no onboard physical button or USB-C socket.',
  inferred:'PCB outline/Z/thickness, RF module shield/antenna, fixed optical barrel/glass/sensor/FPC, microSD carrier and contacts, microphone package and LED coupling reconstructed from exact photographs and native apertures; concealed datums are not production fit evidence.'},
};
