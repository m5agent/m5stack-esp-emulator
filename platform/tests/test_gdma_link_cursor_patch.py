"""Actual shared GDMA register/cursor/descriptor code, independent guest RAM.

Only QOM/IRQ and RAM transports are shimmed. The real peripheral callbacks,
channel commands, register fields and memory-to-memory loop are replayed from
the committed source patches. This is C logic evidence, not guest validation.
"""
from pathlib import Path
import re
import hashlib
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0060-gdma-link-cursor-lifecycle.patch"
SOURCE = "hw/dma/esp_gdma.c"
HEADER = "include/hw/dma/esp_gdma.h"


def function(source, name):
    match = re.search(r"^(?:static\s+)?(?:inline\s+)?(?:void|bool|uint32_t|uint64_t)\s+" + name + r"\(", source, re.M)
    if match is None:
        raise AssertionError("actual GDMA function missing: " + name)
    start = source.index("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[match.start():index + 1]
    raise AssertionError("unterminated actual GDMA function")


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MIN(a,b) ((a)<(b)?(a):(b))
#define g_malloc0(n) calloc(1,(n))
#define g_malloc malloc
#define g_free free
#define error_report(...) fprintf(stderr,__VA_ARGS__)
#define GDMA_DEBUG 0
typedef int qemu_irq;
typedef int SysBusDevice;
typedef int SysBusDeviceClass;
typedef int MemoryRegion;
typedef int AddressSpace;
#define REG32(reg,addr) enum { A_##reg=(addr) };
#define FIELD(reg,name,shift,bits) enum { R_##reg##_##name##_SHIFT=(shift), R_##reg##_##name##_MASK=((1ULL<<(bits))-1)<<(shift) };
#define FIELD_EX32(value,reg,name) (((value)&R_##reg##_##name##_MASK)>>R_##reg##_##name##_SHIFT)
static void qemu_set_irq(qemu_irq irq,int level) {(void)irq;(void)level;}
'''
RAM = r'''
#undef ESP_GDMA_GET_CLASS
static ESPGdmaClass klass={.m_channel_count=1};
#define ESP_GDMA_GET_CLASS(s) (&klass)
static uint8_t ram[0x4000];
static unsigned callbacks;
static bool access_ram(uint32_t address,void *data,uint32_t len,bool write) {
    if(address<ESP_GDMA_RAM_ADDR || address-ESP_GDMA_RAM_ADDR>sizeof(ram) || len>sizeof(ram)-(address-ESP_GDMA_RAM_ADDR))return false;
    if(write)memcpy(ram+address-ESP_GDMA_RAM_ADDR,data,len);
    else memcpy(data,ram+address-ESP_GDMA_RAM_ADDR,len);
    return true;
}
static bool esp_gdma_read_descr(ESPGdmaState *s,uint32_t address,GdmaLinkedList *desc) {(void)s;return access_ram(address,desc,sizeof(*desc),false);}
static bool esp_gdma_write_descr(ESPGdmaState *s,uint32_t address,GdmaLinkedList *desc) {(void)s;return access_ram(address,desc,sizeof(*desc),true);}
static bool esp_gdma_read_guest(ESPGdmaState *s,uint32_t address,void *data,uint32_t len) {(void)s;return access_ram(address,data,len,false);}
static bool esp_gdma_write_guest(ESPGdmaState *s,uint32_t address,void *data,uint32_t len) {(void)s;return access_ram(address,data,len,true);}
static void started(void *opaque,GdmaPeripheral periph,int dir) {(void)opaque;assert(periph==GDMA_LCDCAM);assert(dir==0 || dir==1);callbacks++;}
'''
MAIN = r'''
#define ADDR(offset) (ESP_GDMA_RAM_ADDR+(offset))
static void descriptor(ESPGdmaState *s,unsigned offset,unsigned buffer,unsigned next,bool eof) {
    GdmaLinkedList d={.config={.size=4,.length=4,.owner=1,.suc_eof=eof},.buf_addr=ADDR(buffer),.next_addr=next?ADDR(next):0};
    assert(esp_gdma_write_descr(s,ADDR(offset),&d));
}
int main(int argc,char **argv) {
    assert(argc==2);unsigned test=atoi(argv[1]);
    DmaConfigState in[1]={0},out[1]={0};ESPGdmaState s={0};s.ch_conf[0]=in;s.ch_conf[1]=out;
    for(unsigned dir=0;dir<2;dir++) {
        s.ch_conf[dir][0].peripheral=GDMA_LCDCAM;
        s.start_cb[dir][GDMA_LCDCAM]=started;
    }
    memset(ram,0xcc,sizeof(ram));
    descriptor(&s,0x100,0x1000,0x110,false);descriptor(&s,0x110,0x1010,0x100,true);
    descriptor(&s,0x200,0x2000,0x210,false);descriptor(&s,0x210,0x2010,0x200,true);
    uint8_t payload[]={0x11,0x22,0x33,0x44},result[4]={0};uint32_t channel=99;
    unsigned dir=test==1 || test==3?1:0;
    uint32_t start=dir?R_GDMA_OUT_LINK_START_MASK:R_GDMA_IN_LINK_START_MASK;
    uint32_t restart=dir?R_GDMA_OUT_LINK_RESTART_MASK:R_GDMA_IN_LINK_RESTART_MASK;
    uint32_t stop=dir?R_GDMA_OUT_LINK_STOP_MASK:R_GDMA_IN_LINK_STOP_MASK;
    DmaConfigState *state=s.ch_conf[dir];
    state->link=(ADDR(0x100)&0xfffff)|start;
    esp_gdma_push_descriptor(&s,0,dir,ADDR(0x100));
    if(test<=1) {
        memcpy(ram+0x1000,"OLD!",4);memcpy(ram+0x2000,"NEW!",4);
        esp_gdma_write_chan_conf(&s,dir,0,GDMA_LINK_REG,(ADDR(0x200)&0xfffff)|start);
        if(dir) {assert(esp_gdma_complete_out_descriptor(&s,0,result,4)==4);assert(!memcmp(result,"NEW!",4));}
        else {assert(esp_gdma_complete_in_descriptor(&s,0,payload,4)==4);assert(!memcmp(ram+0x2000,payload,4));assert(!memcmp(ram+0x1000,"OLD!",4));}
    }else if(test<=3) {
        esp_gdma_write_chan_conf(&s,dir,0,GDMA_CONF0_REG,1);
        esp_gdma_write_chan_conf(&s,dir,0,GDMA_CONF0_REG,0);
        assert(!state->current_desc_addr && !state->state && !state->desc_addr && !state->bfr_desc_addr && !state->bfr_bfr_desc_addr);
        assert(!esp_gdma_get_channel_periph(&s,GDMA_LCDCAM,dir,&channel));
    }else if(test==4 || test==8) {
        assert(esp_gdma_complete_in_descriptor(&s,0,payload,4)==4);
        assert(state->current_desc_addr==ADDR(0x110));
        unsigned head=test==4?0x200:0x100;
        esp_gdma_write_chan_conf(&s,0,0,GDMA_LINK_REG,(ADDR(head)&0xfffff)|restart);
        assert(state->current_desc_addr==ADDR(0x110));
        assert(esp_gdma_complete_in_descriptor(&s,0,payload,4)==4);
        assert(!memcmp(ram+0x1010,payload,4) && ram[0x2000]==0xcc);
    }else if(test==5) {
        uint32_t readback=esp_gdma_read_chan_register(&s,dir,0,GDMA_LINK_REG);
        esp_gdma_write_chan_conf(&s,dir,0,GDMA_LINK_REG,readback|stop);
        assert(!esp_gdma_get_channel_periph(&s,GDMA_LCDCAM,dir,&channel));
        assert(callbacks==0 && state->current_desc_addr==ADDR(0x100));
        assert(!(esp_gdma_read_chan_register(&s,dir,0,GDMA_LINK_REG)&stop));
    }else if(test==6) {
        assert(!(esp_gdma_read_chan_register(&s,dir,0,GDMA_LINK_REG)&(start|restart|stop)));
        assert(esp_gdma_get_channel_periph(&s,GDMA_LCDCAM,dir,&channel) && channel==0);
    }else if(test==7) {
        esp_gdma_push_descriptor(&s,0,0,ADDR(0x110));
        esp_gdma_write_chan_conf(&s,0,0,GDMA_LINK_REG,ADDR(0x200)&0xfffff);
        assert(state->current_desc_addr==ADDR(0x110));
        assert(esp_gdma_get_channel_periph(&s,GDMA_LCDCAM,0,&channel));
        assert(esp_gdma_complete_in_descriptor(&s,0,payload,4)==4);
        assert(!memcmp(ram+0x1010,payload,4) && ram[0x2000]==0xcc);
    }else if(test==9 || test==10) {
        in[0].link=out[0].link=0;in[0].conf0=R_GDMA_IN_CONF0_MEM_TRANS_EN_MASK;
        descriptor(&s,0x100,0x1000,0x110,true);descriptor(&s,0x110,0x1010,0,true);
        descriptor(&s,0x200,0x2000,0x210,false);descriptor(&s,0x210,0x2010,0,false);
        memcpy(ram+0x1000,"AAAA",4);memcpy(ram+0x1010,"BBBB",4);
        esp_gdma_write_chan_conf(&s,0,0,GDMA_LINK_REG,(ADDR(0x200)&0xfffff)|R_GDMA_IN_LINK_START_MASK);
        esp_gdma_write_chan_conf(&s,1,0,GDMA_LINK_REG,(ADDR(0x100)&0xfffff)|R_GDMA_OUT_LINK_START_MASK);
        assert(!memcmp(ram+0x2000,"AAAA",4));
        if(test==10) {
            /* New ADDR heads must not replace the next-node restart cursor. */
            esp_gdma_write_chan_conf(&s,0,0,GDMA_LINK_REG,(ADDR(0x100)&0xfffff)|R_GDMA_IN_LINK_RESTART_MASK);
            esp_gdma_write_chan_conf(&s,1,0,GDMA_LINK_REG,(ADDR(0x200)&0xfffff)|R_GDMA_OUT_LINK_RESTART_MASK);
            assert(!memcmp(ram+0x2010,"BBBB",4));
        }
    }else return 2;
    puts("PASS actual GDMA fresh head/reset/stop/restart/RAM boundary");return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class GdmaLinkCursorPatchTests(unittest.TestCase):
    def test_actual_register_callbacks_and_independent_guest_ram(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for source, digest in ((SOURCE, "35b8b37e9d5e2cfb045c28de9c42f6cc5c1080c04cd4cff41c730deafa66bc5b"), (HEADER, "f4d82a9f8bb6301791c93b37f5df1ec4012c1546c9b1ccd62e1b807ef67a1300")):
                seed = ROOT / "platform/tests/fixtures/gdma_upstream" / Path(source).name
                self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(), digest)
                target = root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(seed.read_bytes())
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                for source in (SOURCE, HEADER):
                    subprocess.run(["git", "apply", "--include=" + source, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            header = "\n".join(line for line in (root / HEADER).read_text().splitlines() if not line.startswith(("#include", "#pragma")))
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            names = ("esp_gdma_check_interrupt_status", "esp_gdma_set_status", "esp_gdma_clear_status", "esp_gdma_reset_fifo",
                     "esp_gdma_push_descriptor", "esp_gdma_next_list_node", "esp_gdma_get_restart_buffer", "esp_gdma_get_channel_periph",
                     "esp_gdma_complete_out_descriptor", "esp_gdma_complete_in_descriptor", "esp_gdma_check_and_start_mem_transfer",
                     "esp_gdma_write_chan_conf", "esp_gdma_read_chan_register")
            for label, source in (("baseline", before), ("fixed", after)):
                descriptor = source[source.index("typedef struct GdmaLinkedList"):source.index("} GdmaLinkedList;") + len("} GdmaLinkedList;")]
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + header + descriptor + RAM + "\n".join(function(source, name) for name in names) + MAIN)
                result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-sign-compare", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                for case in range(11):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case in (4, 8, 9, 10):
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0, "preimage must fail the fresh-channel boundary")


if __name__ == "__main__":
    unittest.main()
