/** Millimetres; +Y AC-output end, +Z SSR/front button face. */
export const spec={
 id:'acssr',name:'ACSSR',sku:'U139',size:[45,80,31],nominalMm:[45,80,31],vendorDimensionOrderMm:[80,45,31],
 controllerCadEnvelopeMm:[44.939388275146484,18.73927879333496,11.500001907348633],
 controller:{y:-30.63036060333252,frontZ:15.500001907348633,backZ:4},
 press:{center:[0,-28.65,15.5],travelMm:.22},
 grove:{position:[0,-39.7,9.3],color:0xc72920},
 terminal:{pitch:3.96,pinX:[-5.94,-1.98,1.98,5.94],names:['RS485_B','RS485_A','VIN','GND'],positions:[[-10.8,-30.6303606,9.3],[10.8,-30.6303606,9.3]]},
 ssr:{yMin:-21.26072120666504,yMax:40,screwX:[-12.75,12.75],screwY:[33.25,-14.51072120666504],mountY:[33.2,-14.7],mountRadius:2.6,indicator:[9.3,-1.2,13.55]},
 rgb:{position:[0,-28.65,15.12]},power:{position:[8.28,-35.223694,3.98]},
 source:{dimensions:'Official U139 kit 80 x 45 x 31 mm. Official controller drawing 45 x 18.7 x 11.5 mm; STL complete original shell is 44.94 x 18.74 x 11.5 mm.',hardware:'Official schematic confirms S1 momentary button, LED1 SK6812, D4 red 0603 power LED, ESP32-C3FH4, SP3485EN-L/TR, ME3116AM6G, HM8089, J2 I2C Grove, P1/P2 parallel RS485PWR. Exact U139 gallery shows DELIXI CDG1-1DA/10A SSR, four cross-head terminals, independent circular SSR red indicator and two removable HT3.96-4P plugs.',inferred:'SSR body/covers/metal flange/clamps, PCB and package layout, installed controller/SSR spacing, fork lugs, light-guide depth, terminal/socket dimensions, screw access and 0.22 mm tongue free-end travel are appearance reconstructions constrained by the exact-product photographs and official envelope. Not production-fit or electrical data.'}
};
