export const defaults={};
export const configurations=[{id:'complete',name:'原版 RFID · MFRC522 完整本体',options:{}}];
export const configurationSchema={};
export const spec={id:'rfid',name:'Unit RFID',sku:'U031',part:'MFRC522',lifecycle:'original/EOL',size:[24,48,8],nominalMm:[24,48,8],vendorTableOrderMm:[48,24,8],modelingRoute:'own-dimensional-parametric',defaults,configurations,configurationSchema,
 shell:{widthMm:24,heightMm:48,cornerRadiusMm:4,rearZ:-3.9,frontZ:3.9,skinMm:1,wallMm:1.1,source:'Own nominal product table24x48x8 and own multiview;all internal planes,skin/wall/corner details inferred. Front film and rear M5 relief complete8mm actual visual depth.'},
 mounting:{centres:[[-8,-12],[8,-12]],boreRadiusMm:2.4,bossRadiusMm:3.2,source:'Own visible two bores and scale;nominal layout/hole dimensions photo-derived,not manufacturing datum or borrowed RFID2.'},
 pcb:{bottomZ:-2.2,topZ:-1.4,thicknessMm:.8,groveTailY:-15.66,source:'Own original has no PCB photo/CAD;shape,levels,supports,component and antenna placement reconstructed.'},
 grove:{position:[0,-23.96,1.2],face:'bottom',depthMm:7.6,pins:['SCL','SDA','5V','GND'],source:'Literal original J1/rear legend numbering only;no automatic electrical cable routing.'},
 frontFilm:{size:[18.2,28.2],position:[0,7.4,3.9],thicknessMm:.1},rearFilm:{size:[16.2,28.2],position:[0,7.4,-3.98],thicknessMm:.08},
 topSlot:{centerX:-6.8,centerZ:-.55,widthMm:1.6,heightMm:1.25,frontY:24,backingY:22.25,source:'Own05 visible small top side slot;position/depth inferred. Unknown function;no button,LED or sensor anchor.'},
 limitations:['No own native CAD,retained source faces,complete BOM or measured hidden placement.','Do not borrow U031-B/WS1850S shell,photos,labels,PCB or package topology.','MFRC522 package and RF antenna outline/trace coordinates are hidden appearance reconstruction,not verified circuitry/antenna implementation.','Static geometry and mechanical Grove/cable/pose only;no UID,NFC,data read/write,sensing animation,address,I2C,firmware,LED,button,joint or sensor output.','Slot and fastening detail,film registration,PCB support/clearances are estimated,not manufacturing acceptance.']};
