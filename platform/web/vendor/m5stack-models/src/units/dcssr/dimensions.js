/** Millimetres; +Y DC-output end, +Z SSR/front button face. */
export const spec={
 id:'dcssr',name:'DCSSR',sku:'U140',size:[45,80,31],nominalMm:[45,80,31],vendorDimensionOrderMm:[45,30.7,11.5],
 dimensionStatus:'Full-kit appearance estimate; official 45 x 30.7 x 11.5 mm drawing covers controller including fork lugs only',
 controllerCadEnvelopeMm:[44.939388275146484,18.73927879333496,11.500001907348633],
 controller:{y:-30.63036060333252,frontZ:15.500001907348633,backZ:4},
 press:{center:[0,-28.65,15.5],travelMm:.22},
 grove:{position:[0,-39.7,9.3],color:0xc72920},
 terminal:{pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['RS485_B','RS485_A','VIN','GND'],positions:[[-10.8,-30.6303606,9.3],[10.8,-30.6303606,9.3]]},
 ssr:{yMin:-21.26072120666504,yMax:40,screwX:[-12.75,12.75],screwY:[33.25,-14.51072120666504],mountY:[33.2,-14.7],mountRadius:2.6,indicator:[9.3,-1.2,13.55]},
 rgb:{position:[0,-28.65,15.12]},power:{position:[8.28,-35.223694,3.98]},
 source:{dimensions:'Exact U140 drawing specifies controller with fork lugs 45 x 30.7 x 11.5 mm; native shell alone 44.94 x 18.74 x 11.5 mm. Approximately 45 x 80 x 31 mm assembled kit is reconstructed from same-model front/side photographs and the known 45 mm controller width; no production datum is published.',hardware:'Official U140 product specifies ESP32-C3, central button, SK6812 RGB, two supplied HT3.96-4P plugs and red SSR indicator. Exact U140 photographs show DELIXI CDG1-1DD/10A DC SSR, four cross-head terminal screws, two metal fork lugs, rear PWR icon/indicator and red Grove. Concealed packages are visual envelopes only, not an asserted U140 BOM.',inferred:'Full SSR package dimensions, thermal flange/clamps/guards, PCB/hidden component envelopes, installation datum, light-guide depth, terminal/socket envelopes, screw access and 0.22 mm tongue free-end travel are appearance reconstructions constrained by exact U140 photographs. No production-fit, electrical or certification data.'}
};
