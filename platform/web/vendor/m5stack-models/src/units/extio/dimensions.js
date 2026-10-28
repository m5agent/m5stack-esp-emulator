/** Own original U011/PCA9554PW dimensional/photo reconstruction. No native CAD. */
export const defaults={};
export const configurations=[{id:'complete',name:'原版 EXT.IO · 完整本体',options:{}}];
export const configurationSchema={};
export const spec={id:'extio',name:'Unit EXT.IO',sku:'U011',part:'PCA9554PW',lifecycle:'original/EOL',size:[24,32,11.1],nominalMm:[24,32,11],modelingRoute:'own-dimensional-parametric',defaults,configurations,configurationSchema,
 shell:{widthMm:24,heightMm:32,cornerRadiusMm:4,baseRearZ:-4.3,baseFrontZ:4.3,raisedFrontZ:6.7,skinMm:1,wallMm:1.1,source:'11mm is the own table nominal external envelope.8.6mm base/2.4mm hood and every internal datum are own-photo appearance estimates,not U011-B8+2.2 drawing or exact manufacturing coordinates.'},
 mounting:{centres:[[-8,-4],[8,-4]],boreRadiusMm:2.55,bossRadiusMm:3.25,source:'Own visible holes and standard LEGO-like layout appearance estimate;not the ambiguous B-version drawing or a fit certification.'},
 pcb:{bottomZ:-2.4,topZ:-1.6,thicknessMm:.8},
 grove:{position:[0,-15.94,1],face:'bottom',depthMm:7.6,tailBodyY:-8.54,pins:['SCL','SDA','VCC','GND'],source:'Own red open-top4contact HY2.0 receiver;numbering follows original J1 schematic,not automatic wire/electrical routing.'},
 io:{position:[0,15.82,2.67],face:'top',connector:'header-2x5-2.54mm-male',pitchMm:2.54,columns:5,rows:2,pinTipY:15.7,rowZ:[1.4,3.94],bendY:[8.66,11.2],columnX:[-5.08,-2.54,0,2.54,5.08],source:'Own01 explicitly2x5@2.54mm,own05 exposed solid contacts and exact P1 Header5X2 schematic. Right-angle male pin presentation;body/bend/installation inferred from own photos.'},
 label:{size:[16.1,11.8],position:[0,6.85,-4.34],thicknessMm:.04},
 limitations:['No own native source or face-retention claim;each shell/PCB/contact is newly constructed from original U011 evidence.','Original table11mm conflicts with linked U011_B10.2mm drawing;B image excluded as an exact original datum. Hidden dimensions/positions are inferred.','Physical rear M5 relief extends0.1mm beyond the chosen nominal rear face;actual model depth11.1mm is separately recorded.','No GPIO/ADC/PWM,logic,I2C,address,voltage,readings or firmware simulation.','No external controls,LEDs,joints,attachments or invented sensor anchor.','Film/embossing and contact retention/PCB/package shape/fit are reconstruction,not fabrication or manufacturing acceptance.']};
