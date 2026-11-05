"""Compile actual tracked model postimages against independent register/RAM oracles.

These host-only C controls exercise protocol boundaries, not guest or hardware.
Native guest execution remains a separate validation gate.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_route_patch import function

ROOT = Path(__file__).resolve().parents[2]
EPD = "hw/m5stopwatch/m5_epd_panel.c"
PMIC = "hw/m5stopwatch/m5sw_i2c_devs.c"
BASE = ROOT / "patches/qemu-unit-runtime/0001-reconstructed-xtensa-source.patch"

EPD_SHIM = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
 uint8_t *packed, *lsb, *msb;
 uint32_t native_w, native_h, packed_size, plane_size;
 uint8_t cmd, window_params[9];
 uint32_t data_index, window_param_count;
 uint32_t window_x0, window_x1, window_y0, window_y1;
 bool color, dirty, window_valid;
} M5EpdPanelState;
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
'''
EPD_CASES = r'''
static void command(M5EpdPanelState *s, uint8_t b) {
 m5_epd_panel_write(s, &b, 1, true);
}
int main(void) {
 uint8_t ram[32], lsb[8], msb[8];
 memset(ram, 0x11, sizeof(ram));
 M5EpdPanelState s = {.packed=ram, .lsb=lsb, .msb=msb,
  .native_w=16, .native_h=4, .packed_size=32, .plane_size=8,
  .color=true, .window_x1=15, .window_y1=3, .window_valid=true};
 uint8_t window[] = {0,8, 0,15, 0,1, 0,2, 1};
 command(&s, 0x83);
 m5_epd_panel_write(&s, window, 3, false);
 m5_epd_panel_write(&s, window+3, 2, false);
 m5_epd_panel_write(&s, window+5, 4, false);
 command(&s, 0x10);
 uint8_t pixels[] = {0x00,0x22,0x33,0x55,0x66,0x00,0x22,0x33};
 m5_epd_panel_write(&s, pixels, 3, false);
 m5_epd_panel_write(&s, pixels+3, 5, false);
 for (unsigned i=0;i<32;i++) {
  unsigned expected = i>=12 && i<16 ? pixels[i-12]
   : i>=20 && i<24 ? pixels[4+i-20] : 0x11;
  CHECK(ram[i]==expected);
 }
 uint8_t before[32]; memcpy(before,ram,32);
 uint8_t extra=0xff; m5_epd_panel_write(&s,&extra,1,false);
 CHECK(!memcmp(before,ram,32));
 CHECK(!s.dirty);
 command(&s,0x17); uint8_t automatic=0xa1;
 m5_epd_panel_write(&s,&automatic,1,false); CHECK(!s.dirty);
 automatic=0xa5; m5_epd_panel_write(&s,&automatic,1,false); CHECK(s.dirty);
 s.dirty=false; automatic=0xa7;
 m5_epd_panel_write(&s,&automatic,1,false); CHECK(s.dirty);
 for(unsigned variant=0;variant<3;variant++) {
  window[3]=variant==0 ? 7 : (variant==1 ? 16 : 15);
  window[8]=variant==2 ? 0xff : 1;
  command(&s,0x83); m5_epd_panel_write(&s,window,9,false);
  command(&s,0x10); m5_epd_panel_write(&s,pixels,8,false);
  CHECK(!memcmp(before,ram,32));
 }
 // Legacy full-frame data remains linear with no window command.
 memset(ram,0x11,32); s.window_valid=true;
 s.window_x0=s.window_y0=0; s.window_x1=15; s.window_y1=3;
 command(&s,0x10); m5_epd_panel_write(&s,pixels,8,false);
 CHECK(!memcmp(ram,pixels,8)); CHECK(ram[8]==0x11);
 s.dirty=false; command(&s,0x12); CHECK(s.dirty);
 // The monochrome path still writes independent planes.
 memset(lsb,0,8); memset(msb,0,8); s.color=false;
 command(&s,0x24); m5_epd_panel_write(&s,pixels,8,false);
 command(&s,0x26); m5_epd_panel_write(&s,pixels+4,4,false);
 CHECK(!memcmp(lsb,pixels,8)); CHECK(!memcmp(msb,pixels+4,4));
 puts("EPD_WINDOW_AUTO_LEGACY_OK"); return 0;
}
'''

@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and Git required")
class LatestControllerPatchTests(unittest.TestCase):
 def test_native_variant_agrees_across_profile_peripherals_and_matrix(self):
  profiles=json.loads((ROOT/"platform/qemu/profiles.json").read_text())["devices"]
  matrix=json.loads((ROOT/"tests/uiflow2/device_matrix.json").read_text())["devices"]
  peripheral=json.loads((ROOT/"platform/peripherals/catalog.json").read_text())["devices"]["atoms3"]
  model=next(row for row in profiles if row["id"]=="atoms3")["board_model"]
  self.assertTrue(model)
  self.assertEqual(model,peripheral["board_model"])
  self.assertEqual(model,next(row for row in matrix if row["id"]=="atoms3")["machine"])

 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(); cls.root=Path(cls.temp.name)
  cls.sources={}
  for current in (False,True):
   root=cls.root/str(current); root.mkdir()
   subprocess.run(["git","init","-q"],cwd=root,check=True,capture_output=True)
   patches=[BASE]
   if current:
    patches += [ROOT/"patches/qemu-m5stack-peripherals/0162-axp2101-charger-state.patch",
                ROOT/"patches/qemu-m5stack-peripherals/0163-ed2208-partial-window.patch"]
   for patch in patches:
    subprocess.run(["git","apply","--include="+EPD,"--include="+PMIC,str(patch)],
                   cwd=root,check=True,capture_output=True)
   cls.sources[current]=((root/EPD).read_text(),(root/PMIC).read_text())

 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()

 def compiled(self,name,source):
  c=self.root/(name+".c"); exe=self.root/name; c.write_text(source)
  subprocess.run([shutil.which("cc"),"-std=c11","-Werror",str(c),"-o",str(exe)],check=True,capture_output=True)
  return subprocess.run([str(exe)],capture_output=True,text=True)

 def epd(self,current):
  source=self.sources[current][0]
  refresh=function(source,"m5_epd_refresh") if "static void m5_epd_refresh(" in source else ""
  return self.compiled("epd"+str(current),EPD_SHIM+refresh+function(source,"m5_epd_panel_write")+EPD_CASES)

 def test_partial_window_fragment_bounds_auto_and_legacy(self):
  result=self.epd(True)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn("EPD_WINDOW_AUTO_LEGACY_OK",result.stdout)

 def test_original_model_fails_the_same_nonzero_window_oracle(self):
  self.assertNotEqual(self.epd(False).returncode,0)

 def pmic(self,current):
  source=self.sources[current][1]
  section=source[source.index("case M_AXP2101:"):]
  block=re.search(r"if \(r == 0x01\) \{(.*?)\n        \}",section,re.S).group(1)
  program='''#include <stdbool.h>
#include <stdint.h>
struct State {bool charging;int vin_mv;};
static uint8_t status(bool charge,int vin) {
 struct State value={charge,vin};struct State *s=&value;
'''+block+'''}
int main(void) {
 if(status(true,5000)!=0x22) return 1;
 if(status(false,5000)!=0x05) return 2;
 if(status(false,0)!=0x45) return 3;
 // Both old direction-only and new state-first charging readers agree.
 for(int charging=0;charging<2;charging++) {
  uint8_t v=status(charging,charging?5000:0);
  if(((v&0x60)==0x20)!=charging) return 4;
  if(((v&7)<=3)!=charging) return 5;
 }
 return 0;
}'''
  return self.compiled("pmic"+str(current),program)

 def test_pmic_status_fields_and_old_new_readers(self):
  self.assertEqual(self.pmic(True).returncode,0)

 def test_original_status_fails_the_same_register_oracle(self):
  self.assertNotEqual(self.pmic(False).returncode,0)
