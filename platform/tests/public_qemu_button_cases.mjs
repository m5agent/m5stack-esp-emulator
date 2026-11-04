// Board and driver expectations for real browser MicroPython input validation.
// PMIC power keys report guest IRQ events; they are not GPIO level switches.
const gpio=(id,component,owner)=>({id,component,owner,mode:'driver-edges'});
const pmic=()=>({id:'power',component:'power',owner:'BtnPWR',mode:'pmic-event'});
const atom=()=>[gpio('button','button','BtnA')];
const stick=()=>[gpio('a','a','BtnA'),gpio('b','b','BtnB'),pmic()];
export const PUBLIC_QEMU_BUTTON_CASES=Object.freeze({
  stopwatch:[gpio('a','a','BtnA'),gpio('b','b','BtnB'),pmic()],
  sticks3:[gpio('a','btnA','BtnA'),gpio('b','btnB','BtnB'),{...pmic(),component:'btnPWR'}],
  atoms3:atom(), 'atoms3-lite':atom(), atoms3r:atom(),
  cores3:[pmic()],
  // The 56-key keyboard has its own FIFO/driver acceptance matrix. G0 is
  // admitted only by a runtime containing the dedicated GPIO0 input patch.
  'cardputer-adv':[gpio('boot','boot','BtnA')],
  stamplc:[gpio('key1','a','BtnA'),gpio('key2','b','BtnB'),gpio('key3','c','BtnC')],
  stackchan:[pmic()],
  papercolor:[gpio('key1','key1','BtnA'),gpio('key2','key2','BtnB'),gpio('key3','key3','BtnC'),pmic()],
  papermono:[gpio('key1','key1','BtnA'),gpio('key2','key2','BtnB'),pmic()],
  core2:[gpio('a','a','BtnA'),gpio('b','b','BtnB'),gpio('c','c','BtnC'),pmic()],
  'stickc-plus2':[gpio('a','a','BtnA'),gpio('b','b','BtnB'),gpio('power','power','BtnPWR')],
  stickc:stick(), 'stickc-plus':stick(), 'stickc-plus-se':stick(),
  dial:[gpio('wake','wake','BtnA')],
  'atom-lite':atom(), 'atom-matrix':atom(), 'atom-matrix-v11':atom(),
});

export const PUBLIC_QEMU_BUTTON_LIMITS=Object.freeze({
  'cardputer-adv':'G0 / Boot covers original BtnA on GPIO0; the 56-key keyboard FIFO has separate coverage.',
  stackchan:'The three Si12T capacitive body zones are separate from the PMIC button observer.',
  core2:'A/B/C route through the FT touch-controller raw bottom band, not GPIO switches.',
});
