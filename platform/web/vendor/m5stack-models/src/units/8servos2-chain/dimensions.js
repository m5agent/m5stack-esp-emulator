/** Own U223 outside dimensions. Millimetres: +X right, +Y Chain OUT, +Z header/front. */
export const spec={
 id:'8servos2-chain',name:'Unit 8Servos2-Chain',sku:'U223',size:[24,56,11.5],nominalMm:[24,56,11.5],visualEnvelopeMm:[24,56,11.5],sourceRoute:'own-dimensioned-parametric-no-CAD',cornerRadiusMm:3,
 mountingHolesMm:[[-8,-16],[8,-16]],mountingHoleDiameterMm:4.85,
 window:{center:[6,3.125],size:[8,30.25]},
 grove:{position:[0,-27.95,.1],face:'bottom',label:'Chain IN',pins:['GND','5V','RX1','TX1']},
 out:{position:[0,27.95,.1],face:'top',label:'Chain OUT',pins:['GND','5V','TX2','RX2']},
 dc:{position:[11.98,-7.19,-.45],outsideHoleDiameterMm:6,connector:'dc-5.5x2.1'},
 headers:{x:[3.46,6,8.54],y:[9.37,6.83,3.77,1.23,-1.83,-4.37,-7.43,-9.97],maleCount:24,pitchMm:2.54,connector:'servo-2.54-3',labels:['GND','5V','SIG']},
 pcb:{topZ:3.45,thicknessMm:.8},capacitor:{position:[6,14.3,3.45],radiusMm:3.4,heightMm:2.1},
 labels:{front:{size:[19.70006,35.9],position:[-.05,7.685,5.75]},back:{size:[18.4,35.9],position:[0,7.685,-5.75]}},
 defaults:{},source:{hardware:'Own U223 outside drawing:24x56x11.5/R3/two Ø4.85 bores,pitch16,y12frombottom,8x30.25 window,Ø6 DC at20.81frombottom. Exact own photos show24 male posts, fixed electrolytic capacitor,dual cyan HY2.0 Chain IN/OUT,side DC5.5x2.1 and stepped mounting area.',inferred:'Shell walls/step depth/snap fits,PCB outline and placement,hidden package envelopes/contact retention/pin exposure/film thickness and registration are own-photo inferences. The published shared dimension drawing shows an internal selector-like symbol; this detail is rejected in favour of the U223 fixed capacitor photo. No native CAD surfaces,external LED optical path,servo joints,UART/PWM/ADC/current/voltage/electrical/firmware behavior.'}
};
