"""Execute the actual C6 USB endpoint functions with chardev/clock stubs."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from test_c6_wifi_tsf_patch import function

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "c6_usb_serial_jtag"
PATCH = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0020-c6-usb-serial-jtag-endpoints.patch"
STUB = r"""
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
typedef int SysBusDevice; typedef int MemoryRegion; typedef int CharBackend;
typedef int qemu_irq; typedef int QEMUTimer; typedef int ResetType; typedef void Object;
typedef void DeviceState;
typedef uint64_t hwaddr;
#define OBJECT_CHECK(t,p,n) ((t *)(p))
#define BIT(n) (1u << (n))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define QEMU_CLOCK_VIRTUAL 0
static bool bound=true, opened=true;static int irq_level, write_limit=64;
static bool handlers_removed, timer_freed;
static uint8_t received[1024];static unsigned received_len;static int64_t now;
#define qemu_chr_fe_backend_connected(p) (bound)
#define qemu_chr_fe_backend_open(p) (bound && opened)
#define qemu_set_irq(p,v) (irq_level=(v))
#define qemu_clock_get_ms(c) (now)
#define timer_mod(t,d) ((void)0)
#define qemu_chr_fe_accept_input(c) ((void)0)
#define qemu_chr_fe_set_handlers(...) (handlers_removed=true)
#define timer_free(t) (timer_freed=true)
static int qemu_chr_fe_write(CharBackend *chr,const uint8_t *bytes,int len){
 if (write_limit < 0) {
  return -1;
 }
 int count = MIN(len, write_limit);
 assert(received_len + count <= sizeof(received));
 memcpy(received+received_len,bytes,count);received_len+=count;return count;
}
"""
MAIN = r"""
static ESP32C6UsbJtagState s;
static uint32_t rd(unsigned r){return esp32c6_jtag_read(&s,r,4);}
static void wr(unsigned r,uint32_t v){esp32c6_jtag_write(&s,r,v,4);}
int main(int argc,char **argv){
 assert(argc==2);unsigned test=atoi(argv[1]);setup(&s);esp32c6_jtag_reset_hold(&s,0);
 switch(test){
 case 0:wr(0x14,~0u);wr(0x10,8);wr(0,65);wr(0,66);wr(0,67);assert(!received_len);
  wr(4,1);assert(!(rd(4)&2)&&!irq_level);tick(&s);assert(received_len==3&&!memcmp(received,"ABC",3)&&irq_level&&(rd(4)&2));break;
 case 1:for(int i=0;i<65;i++)wr(0,i);assert(!(rd(4)&2));tick(&s);assert(received_len==64);
  for (int i = 0; i < 64; i++) {
   assert(received[i] == i);
  }
  break;
 case 2:for(int i=0;i<5;i++)wr(0,i+7);wr(4,1);write_limit=2;tick(&s);assert(received_len==2&&!(rd(4)&2));
  tick(&s);assert(received_len==4&&!(rd(4)&2));tick(&s);assert(received_len==5&&(rd(4)&2));
  for (int i = 0; i < 5; i++) {
   assert(received[i] == i + 7);
  }
  break;
 case 3:wr(0,42);wr(4,1);write_limit=0;tick(&s);assert(!received_len&&!(rd(8)&8)&&!(rd(4)&2));
  write_limit=-1;tick(&s);assert(!received_len&&!(rd(8)&8));write_limit=1;tick(&s);assert(received_len==1&&received[0]==42);break;
 case 4:{uint8_t data[]={9,8,7};wr(0x14,~0u);wr(0x10,4);receive(&s,data,3);assert(irq_level&&(rd(4)&4));
  wr(0x14,4);assert(!irq_level&&(rd(4)&4));for(int i=0;i<3;i++)assert(rd(0)==data[i]);assert(!(rd(4)&4));break;}
 case 5:{uint8_t data[64];memset(data,90,64);receive(&s,data,64);assert(can_receive(&s)==0);
  receive(&s,data,1);for(int i=0;i<64;i++)assert(rd(0)==90);assert(can_receive(&s)==64);receive(&s,data,1);assert(rd(0)==90);break;}
 case 6:wr(0x18,0);wr(0,42);wr(4,1);tick(&s);assert(!received_len&&rd(0x24)==0&&can_receive(&s)==0);
  wr(0x18,(1u<<14)|(1u<<9));tick(&s);assert(received_len==1&&rd(0x24)==1);break;
 case 7:opened=false;wr(0,42);wr(4,1);tick(&s);assert(!received_len&&rd(0x24)==0&&can_receive(&s)==0);
  opened=true;tick(&s);assert(received_len==1);break;
 case 8:{uint8_t data=3;receive(&s,&data,1);wr(0,7);wr(4,1);wr(0x10,~0u);esp32c6_jtag_reset_hold(&s,0);
  assert(rd(0x10)==0&&!irq_level&&!(rd(4)&4)&&(rd(4)&2));tick(&s);assert(!received_len);break;}
 case 9:wr(0x10,~0u);assert(rd(0x10)==14);wr(0x14,~0u);assert(!irq_level&&rd(0xc)==0);break;
 case 10:tick(&s);wr(0x10,10);assert((rd(8)&10)==10&&irq_level);wr(0x14,2);assert(rd(0xc)==8&&irq_level);wr(0x14,8);assert(!irq_level);break;
 case 11:for(int i=0;i<2048;i++)tick(&s);assert(rd(0x24)==0);tick(&s);assert(rd(0x24)==1);break;
 case 12:bound=false;for(int i=0;i<64;i++)wr(0,i);assert(!(rd(4)&2));tick(&s);assert(!received_len&&!(rd(8)&8));break;
 case 13:wr(0,0xabcdef42);wr(4,1);tick(&s);assert(received_len==1&&received[0]==0x42);break;
 case 14:unrealize(&s);assert(handlers_removed&&timer_freed);break;
 default:abort();
 }
 printf("PASS endpoint %u\n",test);return 0;
}
"""


def build(source, target, after):
    text = (source / "hw/misc/esp32c6_jtag.c").read_text()
    header = (source / "include/hw/misc/esp32c6_jtag.h").read_text()
    code = STUB + re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.M)
    if after:
        code += re.search(r"enum \{.*?\n\};", text, re.S).group()
        for name in ("update_irq", "host_attached", "can_receive", "receive", "host_frame"):
            code += function(text, "esp32c6_jtag_" + name)
    for name in ("read", "write", "reset_hold"):
        code += function(text, "esp32c6_jtag_" + name)
    if after:
        code += function(text, "esp32c6_jtag_unrealize")
        code += """
static void setup(ESP32C6UsbJtagState*s){s->host_frame=(void*)1;}
static void tick(ESP32C6UsbJtagState*s){now++;esp32c6_jtag_host_frame(s);}
static void receive(ESP32C6UsbJtagState*s,uint8_t*b,int n){esp32c6_jtag_receive(s,b,n);}
static int can_receive(ESP32C6UsbJtagState*s){return esp32c6_jtag_can_receive(s);}
static void unrealize(ESP32C6UsbJtagState*s){esp32c6_jtag_unrealize(s);assert(!s->host_frame);}
"""
    else:
        code += """
static void setup(ESP32C6UsbJtagState*s){}
static void tick(ESP32C6UsbJtagState*s){}
static void receive(ESP32C6UsbJtagState*s,uint8_t*b,int n){}
static int can_receive(ESP32C6UsbJtagState*s){return 0;}
static void unrealize(ESP32C6UsbJtagState*s){}
"""
    target.with_suffix(".c").write_text(code + MAIN)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                    "-Wno-unused-variable", "-fsanitize=address,undefined", "-g",
                    str(target.with_suffix(".c")), "-o", str(target)], check=True, capture_output=True)


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6UsbSerialJtagTests(unittest.TestCase):
    def test_actual_endpoints_before_after(self):
        with tempfile.TemporaryDirectory(prefix="m5-c6-usj-") as temp:
            root = Path(temp)
            for after in (False, True):
                source = root / str(after)
                shutil.copytree(FIXTURE, source)
                if after:
                    included = ["--include=hw/misc/esp32c6_jtag.c", "--include=include/hw/misc/esp32c6_jtag.h"]
                    for args in (["--check"], [], ["--reverse", "--check"]):
                        subprocess.run(["git", "apply", *included, *args, str(PATCH)], cwd=source,
                                       check=True, capture_output=True)
                binary = root / ("after" if after else "before")
                try:
                    build(source, binary, after)
                except subprocess.CalledProcessError as error:
                    self.fail(error.stderr.decode())
                for case in range(15):
                    with self.subTest(after=after, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True,
                                                timeout=10, env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0",
                                                                     UBSAN_OPTIONS="halt_on_error=1"))
                        if after or case == 13:
                            self.assertEqual(result.returncode, 0, result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn("assert", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
