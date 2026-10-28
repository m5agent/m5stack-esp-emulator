/** Millimetres: +X OUT side,+Y fixed EXT plug,+Z front pin strips. */
export const spec={
 id:'chainbus',name:'Unit ChainBus',sku:'U212',size:[24,29.8,8],nominalMm:[24,29.8,8],vendorDimensionOrderMm:[29.8,24,8],shellMm:[24,24,8],cadEnvelopeMm:[24,26.679523468017578,8],visualEnvelopeMm:[24,29.8,8],
 mountingHolesMm:[[-8,8],[8,8]],mountingHoleDiameterMm:4.85,
 grove:{position:[-11.9,-3,1.4],face:'left',color:0x1398b0,printedTopToBottom:['G','5V','RX1','TX1']},
 out:{position:[11.9,-3,1.4],face:'right',color:0x1398b0,printedTopToBottom:['RX2','TX2','5V','G']},
 ext:{position:[0,17.8,.8],face:'top',connector:'hy2.0-4p-plug',bodyMm:[8.4,5.8,3.3],chamberMm:[.8,1],pitchMm:2,printedBackOrder:['SCL','SDA','5V','G'],scope:'Fixed four-chamber plug;not a socket or a generic cable-source connector'},
 rgb:{position:[0,-10,3.9],defaultOff:true},
 direct:{inputPort:'ext',plugTipInHostMm:[0,-1.2,0],insertionMm:1.2,position:[0,16.6,-.8],rotation:[0,0,Math.PI],inferred:true,scope:'Fixed direct assembly transform;no extra cable/source plug or free joint'},
 labels:{front:{size:[7.232255469690606,10.054343416975996],position:[0,-3,3.86]},back:{size:[20.858883153436935,14.331849168935081],position:[0,-3.45,-3.86]}},
 source:{dimensions:'Own U212 table/drawing:24mm square housing,8mm depth,twoØ4.85mm bores16mm apart20mm from bottom;29.8mm overall includes5.8mm fixed EXT plug.Complete native4156 triangles atscale1 separately measure24×26.679523×8 including existing EXT latch.',hardware:'Three actual HY2.0-4P interfaces:cyan IN left,cyan OUT right,fixed white four-chamber EXT plug top.STM32G031G8U6,ME6211A33M3G,WS2812C-2020 and existing native guide.No external button,USB,sensor or joint.',conflict:'Own print/product text label leftIN UART1 and rightOUT UART2;formal schematic reverses MCU UART/net numbering.Preserve literal appearance only;official review edca641cfca844a2a21fe0aa326d25de pending.',inferred:'Concealed PCB/package layout and installation,connector cavity/contact details,mating fit,1.2mm direct insertion and adhesive thickness.No UART,I2C,GPIO/ADC/NVIC,UID,enumeration,heartbeat,power,electrical or firmware behavior.'}
};
