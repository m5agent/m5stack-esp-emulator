// Board and driver expectations for real browser MicroPython input validation.
// PMIC power keys report guest IRQ events; they are not GPIO level switches.
const gpio=(id,component,owner)=>({id,component,owner,mode:'driver-edges'});
const pmic=()=>({id:'power',component:'power',owner:'BtnPWR',mode:'pmic-event'});
const atom=()=>[gpio('button','button','BtnA')];
const stick=()=>[gpio('a','a','BtnA'),gpio('b','b','BtnB'),pmic()];
// Explicit user-application setup, not a default Flash/runtime change. PM1's
// factory single-click reset mode is not a BtnPWR click-IRQ mode.
export const PM1_BUTTON_OBSERVER_SETUP=Object.freeze({
  stopwatch:Object.freeze({board:'M5StopWatch',i2c:1,scl:48,sda:47,addr:0x6e,click_window_ms:500,configuration_api:'m5pm1-python-driver'}),
  sticks3:Object.freeze({board:'M5StickS3',i2c:1,scl:48,sda:47,addr:0x6e,click_window_ms:500,configuration_api:'m5pm1-python-driver'}),
  papercolor:Object.freeze({board:'M5PaperColor',i2c:1,scl:2,sda:3,addr:0x6e,click_window_ms:500,configuration_api:'machine-i2c-register-rmw'}),
  papermono:Object.freeze({board:'M5PaperMono',i2c:1,scl:48,sda:47,addr:0x6e,click_window_ms:500,configuration_api:'machine-i2c-register-rmw'}),
});
export const PUBLIC_QEMU_BUTTON_CASES=Object.freeze({
  stopwatch:[gpio('a','a','BtnA'),gpio('b','b','BtnB'),pmic()],
  sticks3:[gpio('a','btnA','BtnA'),gpio('b','btnB','BtnB'),{...pmic(),component:'btnPWR'}],
  atoms3:atom(), 'atoms3-lite':atom(), atoms3r:atom(),
  cores3:[pmic()],
  // The 56-key keyboard has its own FIFO/driver acceptance matrix. G0 is
  // admitted only by a runtime containing the dedicated GPIO0 input patch.
  'cardputer-adv':[gpio('boot','boot','BtnA')],
  cardputer:[gpio('f12','boot','BtnA')],
  corematrix:[gpio('a','btnA','BtnA'),gpio('b','btnB','BtnB'),gpio('c','btnC','BtnC')],
  stamplc:[gpio('key1','a','BtnA'),gpio('key2','b','BtnB'),gpio('key3','c','BtnC')],
  stackchan:[pmic()],
  papercolor:[gpio('key1','key1','BtnA'),gpio('key2','key2','BtnB'),gpio('key3','key3','BtnC'),pmic()],
  papermono:[gpio('key1','key1','BtnA'),gpio('key2','key2','BtnB'),pmic()],
  paperdiy:[gpio('a','key1','BtnA'),gpio('b','key2','BtnB')],
  papers3:[{id:'screen',owner:'Touch',mode:'touch-edges',point:{x:270,y:400}}],
  core2:[gpio('a','a','BtnA'),gpio('b','b','BtnB'),gpio('c','c','BtnC'),pmic()],
  'stickc-plus2':[gpio('a','a','BtnA'),gpio('b','b','BtnB'),gpio('power','power','BtnPWR')],
  stickc:stick(), 'stickc-plus':stick(), 'stickc-plus-se':stick(),
  dial:[gpio('wake','wake','BtnA')],
  'atom-lite':atom(), 'atom-matrix':atom(), 'atom-matrix-v11':atom(),
});

export const PUBLIC_QEMU_BUTTON_LIMITS=Object.freeze({
  'cardputer-adv':'G0 / Boot covers original BtnA on GPIO0; the 56-key keyboard FIFO has separate coverage.',
  cardputer:'G0 / Boot uses GPIO0. The K132 GPIO matrix has a separate stock launcher and Fn indicator case.',
  corematrix:'A/B/C are read by the M5 button API from the virtual M5PM1 over HP I2C.',
  stackchan:'The three Si12T capacitive body zones are separate from the PMIC button observer.',
  core2:'A/B/C route through the FT touch-controller raw bottom band, not GPIO switches.',
  papers3:'The GT911 touchscreen is the browser input path. PMS150G power behavior is unmodeled.',
  paperdiy:'A/B use independent GPIO inputs. PM1 power-button behavior remains outside this case.',
});
