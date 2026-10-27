export const spec={
 id:'weight-i2c',name:'Weight-I2C',sku:'U180',
 size:[24,32,11.3],nominalMm:[24,32,11.3],cadEnvelopeMm:[24,32,8],mountY:-4,
 grove:{position:[0,-15.65,1.4],color:0xb52e3d,width:10,height:5.2},
 terminal:{width:15.8,pitch:3.96,position:[0,16.04,3.8],pinX:[-5.94,-1.98,1.98,5.94],names:['A+','A-','E-','E+'],signalNames:['S+','S-','E-','E+'],pinNumbers:[4,3,2,1]},
 source:{
  dimensions:'Official U180 mechanical drawing dimensions the 24 x 32 mm chassis, 8 mm shell and 11.3 mm assembled depth. Native CAD independently confirms 24 x 32 x 8 mm.',
  conflict:'The product prose table says 56.0 x 24.0 x 11.3 mm; it conflicts with the same-page drawing and official CAD. The visual model follows the drawing and CAD; the table value is retained as an unresolved documentation discrepancy.',
  terminal:'Official front photograph labels left-to-right A+, A-, E-, E+. Schematic P1 pin1=E+, pin2=E-, pin3=S-, pin4=S+; A labels reproduce the physical printing and S names retain the circuit terminology.',
  inferred:'PCB outline, package placement, connector internal walls, contact depths and removable plug details are photo-derived appearance estimates, not production tolerances.',
 },
};
