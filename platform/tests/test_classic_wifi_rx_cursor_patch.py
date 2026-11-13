"""Replay native classic MAC registers; guest acceptance is a separate fixture."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack
from test_spi_panel_read_cursor_patch import function

PATCH = 'patches/qemu-m5stack-peripherals/0188-classic-wifi-rx-cursors.patch'
SOURCE = 'hw/misc/esp32_wifi.c'
STUBS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef uint64_t hwaddr;
#define DEBUG 0
#define MEMTXATTRS_UNSPECIFIED 0
#define MEMTX_OK 0
#define ESP32_WIFI(p) ((Esp32WifiState *)(p))
typedef struct dma_list_item {
    unsigned size:12, length:12, reserved:6, eof:1, owner:1;
    uint32_t address,next;
} dma_list_item;
typedef struct {unsigned frame_length;void *next_frame;} mac80211_frame;
typedef struct {uint32_t mem[1024];int raw_interrupt,irq;uint32_t dma_inlink_address;} Esp32WifiState;
static int address_space_memory;
static uint8_t ram[4096];
static int address_space_read(void *unused,uint32_t address,int attrs,void *data,size_t n) {
    assert(address>=0x3ff00000 && (address-0x3ff00000)+n<=sizeof(ram));
    memcpy(data,ram+address-0x3ff00000,n);return MEMTX_OK;
}
static void Esp32_WLAN_handle_frame(Esp32WifiState *s,mac80211_frame *f) {abort();}
static void esp32_wifi_loopback_espnow(Esp32WifiState *s,mac80211_frame *f) {abort();}
static void set_interrupt(Esp32WifiState *s,int n) {s->raw_interrupt|=n;}
static void qemu_set_irq(int irq,int n) {}
'''
MAIN = r'''
int main(int argc,char **argv) {
    assert(argc==2);int test=atoi(argv[1]);Esp32WifiState s={0};
    if(test==0) assert(esp32_wifi_read(&s,A_WIFI_NEXT_RX_DSCR,4)==0x3ff00000);
    if(test==1) {
        esp32_wifi_write(&s,A_WIFI_DMA_INLINK,0x3ff00200,4);
        assert(esp32_wifi_read(&s,A_WIFI_NEXT_RX_DSCR,4)==0x3ff00200);
    }
    if(test==2) {
        s.mem[A_WIFI_LAST_RX_DSCR/4]=0x3ff00100;
        esp32_wifi_write(&s,A_WIFI_DMA_INLINK,0x3ff00200,4);
        assert(esp32_wifi_read(&s,A_WIFI_LAST_RX_DSCR,4)==0x3ff00100);
    }
    if(test==3 || test==4) {
        dma_list_item tail={.next=0x3ff00300};memcpy(ram+0x100,&tail,sizeof(tail));
        s.mem[A_WIFI_LAST_RX_DSCR/4]=0x3ff00100;
        if(test==4)s.dma_inlink_address=0x3ff00200;
        esp32_wifi_write(&s,A_WIFI_DMA_IN_STATUS,1,4);
        assert(s.dma_inlink_address==(test==3?0x3ff00300:0x3ff00200));
        assert(esp32_wifi_read(&s,A_WIFI_DMA_IN_STATUS,4)==0);
    }
    puts("PASS classic RX descriptor cursor");return 0;
}
'''

@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'C compiler and git required')
class ClassicWifiRxCursorTests(unittest.TestCase):
    def test_real_register_paths_before_and_after(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            subprocess.run(['git','init','-q',str(root)],check=True)
            for patch in bootstrap_stack(full=True):
                if patch == PATCH: break
                subprocess.run(['git','apply','--include='+SOURCE,str(ROOT/patch)],cwd=root,check=True,capture_output=True)
            before=(root/SOURCE).read_text()
            subprocess.run(['git','apply','--include='+SOURCE,str(ROOT/PATCH)],cwd=root,check=True,capture_output=True)
            after=(root/SOURCE).read_text()
            registers={'DMA_IN_STATUS':0x84,'DMA_INLINK':0x88,'NEXT_RX_DSCR':0x8c,'LAST_RX_DSCR':0x90,
                       'DMA_INT_STATUS':0xc48,'DMA_INT_CLR':0xc4c,'STATUS':0xcc8,'DMA_OUTLINK':0xd20,'DMA_OUT_STATUS':0xd24}
            defines=''.join(f'#define A_WIFI_{name} {value}\n' for name,value in registers.items())
            for label,source in [('before',before),('after',after)]:
                text=STUBS+defines+function(source,'esp32_wifi_read')+function(source,'esp32_wifi_write')+MAIN
                c=root/(label+'.c');binary=root/label;c.write_text(text)
                result=subprocess.run(['cc','-std=c11','-fsanitize=address',str(c),'-o',str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                for case in range(5):
                    with self.subTest(version=label,case=case):
                        result=subprocess.run([str(binary),str(case)],capture_output=True,text=True)
                        if label=='before' and case in (0,1,3): self.assertNotEqual(result.returncode,0)
                        else: self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('s->mem[A_WIFI_LAST_RX_DSCR / 4] = s->dma_inlink_address;',after)
            self.assertLess(after.index('Esp32_WLAN_prepare_rx(s, frame)'),after.index('memcpy(header+28, frame, length)'))
