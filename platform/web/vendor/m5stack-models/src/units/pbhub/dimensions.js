export const defaults={};
export const configurations=[{id:'complete',name:'原版 PbHub · 六路 GPIO 扩展外观',options:{}}];
export const configurationSchema={};
export const spec={
 id:'pbhub',name:'Unit PbHub',sku:'U041',lifecycle:'original/EOL',size:[24,48,10.8],nominalMm:[24,48,10.8],vendorTableOrderMm:[48,24,10.8],historicalNominalMm:[24,48,12],modelingRoute:'own-photo-parametric',defaults,configurations,configurationSchema,
 shell:{rearZ:-3.92,frontZ:4,skinMm:1,wallMm:1.2,radiusMm:4,source:'Own current U041 photos and nominal envelope;8mm approximate casing,wall/radius/split and all installation levels inferred. No U041-B native or dimensions imported.'},
 mounting:{centres:[[-8,-12],[8,-12]],radiusMm:2.5,bossRadiusMm:3.3,source:'Own two visible holes,photo-scaled position/diameter;not manufacturing fit.'},
 pcb:{size:[20.2,30.2],centre:[0,7.6],rearZ:0,frontZ:.8,thicknessMm:.8,source:'Own black exposed board photo;outline,depth,drills,all support/retention and package installation inferred.'},
 input:{id:'grove',position:[0,-24,1.2],face:'bottom',pins:['SCL','SDA','5V','GND'],depthMm:7.8},
 outputs:[
  {id:'grove-0',channel:0,position:[7.5,-1.7,6.8],turn:-Math.PI/2},
  {id:'grove-1',channel:1,position:[7.5,8.7,6.8],turn:-Math.PI/2},
  {id:'grove-2',channel:2,position:[5,18.2,6.8],turn:0},
  {id:'grove-3',channel:3,position:[-5,18.2,6.8],turn:0},
  {id:'grove-4',channel:4,position:[-7.5,8.7,6.8],turn:Math.PI/2},
  {id:'grove-5',channel:5,position:[-7.5,-1.7,6.8],turn:Math.PI/2}
 ],
 rearFilm:{size:[16.2,28.4],position:[0,7.3,-4],thicknessMm:.08},
 pcbPrint:{size:[20.2,30.2],position:[0,7.6,.8]},
 sourceConflict:{descriptionAndRearFilm:'MEGA328',linkedOriginalSchematic:'ATMEGA328',currentSpecificationTable:'STM32F030F4P6',feedbackId:'d1563a5d43244eb4ba20aebb7ef67fbc',treatment:'Visible QFP32 envelope only;no asserted production BOM.'},
 limitations:['No original U041 CAD;all casing internals,board/package/socket/contact installation and tolerances are photo-based appearance estimates.','Current24x48x10.8 and old24x48x12 nominal dimensions remain distinct.','Current own02 rear film0x61~0x68 only;old0x40~0x47/QC omitted.','Seven physical four-contact Grove frames/cables only;no GPIO/ADC/PWM/RGB/I2C/MCU/power/firmware behavior or invented control/LED/sensor.']
};
