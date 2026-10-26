// Official specification supplies 84×54×23.1. No official assembled CAD was available.
// Local contour, cover split, keys and port offsets are calibrated from official orthographic photos.
export const DIM={
 body:[84,54,23.1],
 display:{w:42.62,h:22.64,cx:.8,cy:13.1,z:10.16},
 keyboard:{x0:-37.8,dx:7.56,y0:-4,dy:6.55,z:9.95,depth:1.45},
 shell:{back:-11.55,front:9.8,split:4.8,deckBase:8.4},
 ports:{
  usbC:[42.04,13.1,6.65],usbC2:[-42.04,13.1,6.65],
  usbA:[42.04,13.1,-.7],hdmi:[-42.04,-13.6,.5],
  grove:[-42.04,13.1,.85],audio:[-42.04,.1,1.1],
  ethernet:[42.04,-13.8,-3.1],ext:[0,27.03,1.2],sd:[18.1,27.03,6.0]
 }
};
