"""Replay classic SPI chip select, bus readback and retained FIFO semantics."""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack
from test_spi_panel_read_cursor_patch import function

PATCH = 'patches/qemu-m5stack-peripherals/0190-classic-spi-panel-cs-fifo.patch'
SPI = 'hw/ssi/esp32_spi.c'
PANEL = 'hw/m5stopwatch/m5_spi_panel.c'
HEADER = 'include/hw/ssi/esp32_spi.h'
STUBS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define ESP32_SPI_BUF_WORDS 16
#define ESP32_SPI(x) ((Esp32SpiState *)(x))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FIELD_DP32(a,b,c,d) (a)
typedef uint64_t hwaddr;
typedef struct { uint32_t read_id, read_offset; uint8_t cmd; } M5SpiPanelState;
typedef struct {
 uint32_t addr_reg,ctrl_reg,status_reg,ctrl1_reg,ctrl2_reg,user_reg,user1_reg,user2_reg;
 uint32_t mosi_dlen_reg,miso_dlen_reg,pin_reg,trans_done,trans_inten,m5_dma_out_link;
 uint32_t data_reg[16]; M5SpiPanelState *m5_panel; int m5_dc_pin,m5_cs_pin,spi;
} Esp32SpiState;
typedef struct {
 int cmd_bytes; uint32_t cmd; int addr_bytes; uint32_t addr; int extra_dummy_bytes;
 int data_tx_bytes,data_rx_bytes; uint32_t *data;
} Esp32SpiTransaction;
static int cs=0,dc=1; static unsigned writes;
static uint8_t last[64];
static int esp32_gpio_get_line(int pin) { assert(pin==5 || pin==15);return pin==5?cs:dc; }
static void esp32_spi_cs_set(Esp32SpiState *s,int v) {}
static void esp32_spi_update_irq(Esp32SpiState *s) {}
static int ssi_transfer(int spi,int data) { return 0; }
static void esp32_spi_txrx_buffer(Esp32SpiState *s,void *data,int tx,int rx) {
 if (data==s->data_reg || data==s->data_reg+8) {
   size_t cap=data==s->data_reg?64:32; assert(tx<=cap && rx<=cap);
 }
 if(rx)memset(data,0,rx);
}
static void m5_spi_panel_write(M5SpiPanelState *p,const uint8_t *data,uint32_t n,bool command) {
 writes+=n;memcpy(last,data,MIN(n,64)); if(command && n){p->cmd=data[n-1];p->read_offset=0;}
}
static void esp32_spi_m5_dma_panel(Esp32SpiState *s,uint32_t a,uint32_t n,bool command,...) {abort();}
'''
MAIN = r'''
static uint32_t read_bits(Esp32SpiState *s,unsigned bits,bool high) {
 s->miso_dlen_reg=bits-1;
 Esp32SpiTransaction t={.data=s->data_reg+(high?8:0),.data_rx_bytes=(bits+7)/8};
 esp32_spi_transaction(s,&t);
 return esp32_spi_read(s,A_SPI_W0+(high?32:0),4);
}
int main(int argc,char **argv) {
 assert(argc==2);int test=atoi(argv[1]);
 M5SpiPanelState p={.read_id=0xe3,.cmd=4};
 Esp32SpiState s={.m5_panel=&p,.m5_dc_pin=15,.m5_cs_pin=5};
 if(test==0){cs=1;assert(read_bits(&s,32,false)!=0xe3);assert(p.read_offset==0);}
 if(test==1){for(int i=0;i<4;i++)assert((read_bits(&s,8,false)&255)==(i==0?0xe3:0));}
 if(test==2){read_bits(&s,1,false);assert(p.read_offset==0);assert(read_bits(&s,32,false)==0xe3);}
 if(test==3){assert(read_bits(&s,32,false)==0xe3);cs=1;for(int i=0;i<3;i++)assert(esp32_spi_read(&s,A_SPI_W0,4)==0xe3);s.data_reg[0]=0x1234;assert(esp32_spi_read(&s,A_SPI_W0,4)==0x1234);}
 if(test==4){cs=1;s.data_reg[0]=0x29;dc=0;Esp32SpiTransaction t={.data=s.data_reg,.data_tx_bytes=256};esp32_spi_transaction(&s,&t);assert(writes==0 && p.cmd==4);}
 if(test==5){cs=0;dc=0;s.data_reg[0]=0x29;Esp32SpiTransaction t={.data=s.data_reg,.data_tx_bytes=1};esp32_spi_transaction(&s,&t);assert(p.cmd==0x29 && writes==1);assert(read_bits(&s,8,false)==0);}
 if(test==6){assert(read_bits(&s,32,true)==0xe3);assert(p.read_offset==4);}
 if(test==7){s.data_reg[0]=0xaabbccdd;Esp32SpiTransaction t={.data=s.data_reg,.data_tx_bytes=4,.data_rx_bytes=4};s.miso_dlen_reg=31;esp32_spi_transaction(&s,&t);assert(writes==4 && last[0]==0xdd && last[3]==0xaa);assert(s.data_reg[0]==0xe3);}
 puts("PASS classic panel chip-select and FIFO");return 0;
}
'''

@unittest.skipUnless(shutil.which('git') and shutil.which('cc'), 'git and C compiler required')
class ClassicPanelCsFifoTests(unittest.TestCase):
    def test_actual_classic_bus_before_and_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            seed=ROOT/'platform/tests/fixtures/classic_spi_upstream/esp32_spi.c'
            self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(),'c563518d0829bd656389629ea0cbd951ad5e89def13f4777e49dc6526386b797')
            (root/SPI).parent.mkdir(parents=True,exist_ok=True)
            (root/SPI).write_bytes(seed.read_bytes())
            for patch in bootstrap_stack(full=True):
                if patch==PATCH:break
                subprocess.run(['git','apply','--include='+SPI,'--include='+PANEL,str(ROOT/patch)],cwd=root,check=True,capture_output=True)
            before=(root/SPI).read_text()
            applied=subprocess.run(['git','apply','--include='+SPI,str(ROOT/PATCH)],cwd=root,capture_output=True,text=True)
            self.assertEqual(applied.returncode,0,applied.stderr)
            after=(root/SPI).read_text()
            registers={'ADDR':0x04,'CTRL':0x08,'STATUS':0x10,'CTRL1':0x0c,'CTRL2':0x14,'USER':0x1c,'USER1':0x20,'USER2':0x24,'MOSI_DLEN':0x28,'MISO_DLEN':0x2c,'PIN':0x34,'SLAVE':0x38,'W0':0x80,'EXT2':0xf8}
            defines='\n'.join(f'#define A_SPI_{name} {value}' for name,value in registers.items())
            panel=(root/PANEL).read_text()
            for label,source in [('before',before),('after',after)]:
                c=root/(label+'.c');exe=root/label
                c.write_text(STUBS+defines+'\n'+function(panel,'m5_spi_panel_read')+'\n'+function(panel,'m5_spi_panel_read_id')+'\n'+function(source,'esp32_spi_read')+'\n'+function(source,'esp32_spi_transaction')+MAIN)
                r=subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined',str(c),'-o',str(exe)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                for case in range(8):
                    with self.subTest(source=label,case=case):
                        r=subprocess.run([str(exe),str(case)],capture_output=True,text=True)
                        if label=='before' and case in (0,1,3,4,5,6,7):self.assertNotEqual(r.returncode,0)
                        else:self.assertEqual(r.returncode,0,r.stderr)
