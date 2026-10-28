export const defaults={};
export const configurations=[{id:'complete',name:'原版 ENV-II · SHT30 + BMP280 完整本体',options:{}}];
export const configurationSchema={};
export const spec={id:'env-ii',name:'Unit ENV-II',sku:'U001-B',parts:['SHT30-DIS-B','BMP280','HT7533'],lifecycle:'original/EOL',size:[24,32,8],nominalMm:[24,32,8],vendorTableOrderMm:[32,24,8],historicalNominalMm:[24.2,32.2,8.1],modelingRoute:'own-dimensional-parametric',defaults,configurations,configurationSchema,
 shell:{widthMm:24,heightMm:32,radiusMm:4,rearZ:-3.9,frontZ:4,skinMm:1,wallMm:1.1,splitZ:.05,source:'Current own32x24x8 nominal table with own01/02/05/06;all internal planes,skin/wall/radius and seating inferred. Rear M5 relief completes actual8mm depth.'},
 mounting:{centres:[[-8,-4],[8,-4]],boreRadiusMm:2.5,bossRadiusMm:3.2,source:'Own visible two holes/photo-scaled placement,not borrowed CAD or fit/tolerance datum.'},
 pcb:{bottomZ:-2.2,topZ:-1.4,thicknessMm:.8,groveTailY:-7.66,source:'Own PCB image/CAD unavailable;outline,levels,supports,package installation and clearances are own-photo reconstruction.'},
 vents:{columnCount:9,columnPitchMm:2,widthMm:.8,heightMm:1.65,verticalPitchMm:3.05,counts:[4,5,4,5,4,5,4,5,4],source:'Own06 visible40staggered capsule vents;opening size/registration inferred within current nominal shell.'},
 grove:{position:[0,-15.96,1.2],face:'bottom',depthMm:7.6,pins:['SCL','SDA','5V','GND']},
 sht30:{position:[-2,10.15,-1.4],bodyMm:[3,3,.85],portRadiusMm:.6,source:'Identity from own schematic. Hidden package/metal window/body and installation reconstructed,not exact layout/BOM.'},
 bmp280:{position:[5.4,7.1,-1.4],bodyMm:[2.5,2,.95],portLocal:[.6,0],portRadiusMm:.16,source:'Identity from own schematic. Hidden metal port/body and installation reconstructed;not manufacturing or sensing physics.'},
 rearFilm:{size:[16.2,12.2],position:[0,6.9,-3.98],thicknessMm:.08},
 limitations:['No own native geometry or source-face retention;not a stretched ENV/DHT12,ENVIII orENVIV shell.','Current nominal24x32x8 and old24.2x32.2x8.1 are distinct recorded source values;feedback420dc9d72c594a1e9b84ef68e45fd5ab retained,no new mechanical correction received.','All hidden PCB/package/support/port coordinates,wall/film thickness and clearances are appearance estimates,not fullBOM/manufacturing fit.','Static own physical housing/packages/Grove only;no readings,sampling,address,I2C,firmware,LED,button,joint or sensor anchor.']};
export const vents=[];for(let col=0;col<9;col++){const ys=col%2?[13.2,10.15,7.1,4.05,1]:[11.65,8.6,5.55,2.5];for(const[row,y]of ys.entries())vents.push({col,row,x:(col-4)*2,y});}
