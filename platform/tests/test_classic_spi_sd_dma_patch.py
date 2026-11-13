"""Replay full native SPI prefix and exercise real CS/DMA C under ASan/UBSan.

Only QEMU memory/IRQ/GPIO plumbing and observable slave endpoints are shimmed.
No firmware, runtime checkout or guest result is required or implied.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = 'patches/qemu-m5stack-peripherals/0192-classic-spi-sd-dma.patch'
SPI = 'hw/ssi/esp32_spi.c'


def function(source, name):
    match = re.search(r'(?m)^(?:static\s+)?(?:inline\s+)?(?:void|uint32_t|uint64_t|int)\s+' + name + r'\s*\([^;{}]*\)\s*\{', source)
    if not match:
        raise AssertionError(name)
    opening = source.index('{', match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if not depth:
            return source[match.start():index + 1]
    raise AssertionError(name)


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define ESP32_SPI_BUF_WORDS 16
#define ESP32_SPI_CS_COUNT 3
#define ESP32_SPI(x) ((Esp32SpiState *)(x))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define g_malloc(n) malloc(n)
#define g_malloc0(n) calloc(1,n)
#define g_free(p) free(p)
#define bswap32(v) __builtin_bswap32(v)
#define FIELD_EX32(v,r,f) (((v)>>SHIFT_##r##_##f)&MASK_##r##_##f)
#define SHIFT_SPI_USER_COMMAND 31
#define MASK_SPI_USER_COMMAND 1
#define SHIFT_SPI_USER_ADDR 30
#define MASK_SPI_USER_ADDR 1
#define SHIFT_SPI_USER_MOSI 27
#define MASK_SPI_USER_MOSI 1
#define SHIFT_SPI_USER_MISO 28
#define MASK_SPI_USER_MISO 1
#define SHIFT_SPI_USER_MOSI_HIGHPART 25
#define MASK_SPI_USER_MOSI_HIGHPART 1
#define SHIFT_SPI_USER_MISO_HIGHPART 24
#define MASK_SPI_USER_MISO_HIGHPART 1
#define SHIFT_SPI_USER1_ADDR_BITLEN 26
#define MASK_SPI_USER1_ADDR_BITLEN 63
#define SHIFT_SPI_USER2_COMMAND_BITLEN 28
#define MASK_SPI_USER2_COMMAND_BITLEN 15
#define SHIFT_SPI_USER2_COMMAND_VALUE 0
#define MASK_SPI_USER2_COMMAND_VALUE 65535
#define SHIFT_SPI_SLAVE_TRANS_DONE 4
#define MASK_SPI_SLAVE_TRANS_DONE 1
#define SHIFT_SPI_SLAVE_TRANS_INTEN 9
#define MASK_SPI_SLAVE_TRANS_INTEN 1
#define BASE 0x3ff00000u
typedef uint64_t hwaddr;
typedef struct { int unused; } M5SpiPanelState;
typedef struct { uint8_t (*transfer)(void *,uint8_t); void (*set_cs)(void *,bool); } M5SpiSlaveOps;
typedef struct {
 uint32_t addr_reg,ctrl_reg,status_reg,ctrl1_reg,ctrl2_reg,user_reg,user1_reg,user2_reg;
 uint32_t mosi_dlen_reg,miso_dlen_reg,pin_reg,trans_done,trans_inten,m5_dma_out_link,m5_dma_in_link;
 uint32_t data_reg[16]; M5SpiPanelState *m5_panel; int m5_dc_pin,m5_cs_pin,spi,irq,cs_gpio[3];
 int gpio_cs0_signal,gpio_cs0_level,spi_slave_cs_pin,spi_slave_cs_level;
 const M5SpiSlaveOps *spi_slave_ops; void *spi_slave_opaque; uint32_t flash_qio_header_bytes;
} Esp32SpiState;
typedef struct {
 int cmd_bytes; uint32_t cmd; int addr_bytes; uint32_t addr; int extra_dummy_bytes;
 int data_tx_bytes,data_rx_bytes; uint32_t *data;
} Esp32SpiTransaction;
static uint8_t ram[1<<20],wire[1<<22],panel[1<<22];
static unsigned wire_count,panel_count,ssi_count,desc_reads,mem_reads,mem_writes,cs_calls;
static int last_cs,levels[40],routes[40];
static unsigned protocol_cursor;
static unsigned write_lengths[9000],write_addresses[9000];
static Esp32SpiState *current;
static void *checked_memcpy(void *dst,const void *src,size_t n) {
 if(current && n) {
  uintptr_t first=(uintptr_t)current->data_reg,last=first+sizeof(current->data_reg),from=(uintptr_t)src,to=(uintptr_t)dst;
  if(from>=first && from<last)assert(n<=last-from);
  if(to>=first && to<last)assert(n<=last-to);
 }
 return memcpy(dst,src,n);
}
#define memcpy checked_memcpy
static int esp32_gpio_get_line(int pin) {assert(pin>=0 && pin<40);return levels[pin];}
static int esp32_gpio_matrix_out_signal(int pin,bool inv) {assert(pin>=0&&pin<40&&!inv);return routes[pin];}
static void qemu_set_irq(int pin,int value) {}
static void esp32_spi_update_irq(Esp32SpiState *s) {}
static void maybe_encrypt_data(Esp32SpiState *s) {}
static uint8_t slave_transfer(void *opaque,uint8_t tx) {
 assert(wire_count<sizeof(wire));wire[wire_count++]=tx;protocol_cursor++;return tx^0xa5;
}
static void slave_cs(void *opaque,bool level) {last_cs=level;cs_calls++;if(!level)protocol_cursor=0;}
static int ssi_transfer(int bus,int tx) {ssi_count++;return 0xee;}
static void cpu_physical_memory_read(uint32_t address,void *dst,size_t n) {
 assert(address>=BASE && (uint64_t)address+n<=BASE+sizeof(ram));
 mem_reads++;if(n==12)desc_reads++;memcpy(dst,ram+(address-BASE),n);
}
static void cpu_physical_memory_write(uint32_t address,const void *src,size_t n) {
 assert(address>=BASE && (uint64_t)address+n<=BASE+sizeof(ram));assert(mem_writes<9000);
 write_addresses[mem_writes]=address;write_lengths[mem_writes++]=n;memcpy(ram+(address-BASE),src,n);
}
static void m5_spi_panel_write(M5SpiPanelState *p,const uint8_t *data,uint32_t n,bool command) {
 assert(panel_count+n<=sizeof(panel));memcpy(panel+panel_count,data,n);panel_count+=n;
}
static void m5_spi_panel_read(M5SpiPanelState *p,uint8_t *data,uint32_t n) {memset(data,0x5c,n);}
static void esp32_spi_txrx_buffer(Esp32SpiState *,void *,int,int);
static void esp32_spi_do_command(Esp32SpiState *,uint32_t);
'''

MAIN = r'''
static void descriptor(unsigned at,unsigned capacity,unsigned length,bool owner,bool eof,unsigned buf,unsigned next) {
 uint32_t d[]={capacity|(length<<12)|(owner?1u<<31:0)|(eof?1u<<30:0),BASE+buf,next?BASE+next:0};
 memcpy(ram+at,d,sizeof(d));
}
static uint32_t descriptor_word(unsigned at) {uint32_t word;memcpy(&word,ram+at,4);return word;}
static void reset_output(void) {wire_count=panel_count=ssi_count=desc_reads=mem_reads=mem_writes=cs_calls=0;}
int main(int argc,char **argv) {
 assert(argc==2);int test=atoi(argv[1]);
 for(int i=0;i<40;i++){levels[i]=1;routes[i]=256;}
 M5SpiPanelState p={0};M5SpiSlaveOps ops={slave_transfer,slave_cs};
 Esp32SpiState s={.m5_panel=&p,.m5_dc_pin=15,.m5_cs_pin=5,.pin_reg=6,
 .gpio_cs0_signal=68,.gpio_cs0_level=1,.spi_slave_cs_pin=4,.spi_slave_cs_level=1,.spi_slave_ops=&ops};
 current=&s;for(int i=0;i<64;i++)((uint8_t*)s.data_reg)[i]=i+1;
 Esp32SpiTransaction t={.data=s.data_reg,.data_tx_bytes=4};
 if(test==0){routes[4]=68;esp32_spi_transaction(&s,&t);assert(wire_count==4&&ssi_count==0&&panel_count==0&&cs_calls==2&&last_cs==1);}
 if(test==1){levels[4]=0;levels[4]=0;esp32_spi_slave_cs(&s,4,0);reset_output();esp32_spi_transaction(&s,&t);assert(wire_count==4&&panel_count==0&&last_cs==0);}
 if(test==2){routes[4]=11;esp32_spi_transaction(&s,&t);assert(wire_count==0&&panel_count==0&&ssi_count==4);}
 if(test==3){routes[4]=68;s.pin_reg=7;esp32_spi_transaction(&s,&t);assert(wire_count==0&&panel_count==0&&ssi_count==4);}
 if(test==4){ops.set_cs=NULL;levels[4]=0;esp32_spi_slave_cs(&s,4,0);routes[4]=68;esp32_spi_transaction(&s,&t);assert(wire_count==4&&last_cs==0);}
 if(test==5){levels[4]=0;esp32_spi_slave_cs(&s,4,0);s.user_reg=1u<<27;s.user2_reg=(7u<<28)|0x9f;s.mosi_dlen_reg=31;esp32_spi_do_command(&s,R_SPI_CMD_USR_MASK);assert(wire_count==4&&wire[0]==1);}
 if(test==6){levels[4]=0;esp32_spi_slave_cs(&s,4,0);s.user_reg=(1u<<31)|(1u<<27);s.user2_reg=(7u<<28)|0x9f;s.mosi_dlen_reg=31;esp32_spi_do_command(&s,R_SPI_CMD_USR_MASK);assert(wire_count==5&&wire[0]==0x9f&&wire[1]==1);}
 if(test==7){routes[5]=68;levels[5]=1;esp32_spi_transaction(&s,&t);assert(panel_count==4&&wire_count==0);s.pin_reg=7;reset_output();esp32_spi_transaction(&s,&t);assert(panel_count==0);}
 if(test>=8){
  levels[4]=0;esp32_spi_slave_cs(&s,4,0);reset_output();
  for(unsigned i=0;i<300;i++)ram[0x2000+i]=(uint8_t)(i^0x83);
  for(unsigned i=0;i<300;i++)ram[0x3000+i]=(uint8_t)(i^0x5a);
  memset(ram+0x4000,0xcc,1000);memset(ram+0x5000,0xcc,1000);
 }
 if(test==8){
  descriptor(0x100,128,128,true,false,0x2000,0x120);descriptor(0x120,192,192,true,true,0x3000,0);
  esp32_spi_write(&s,0x104,0x100,4);esp32_spi_write(&s,0x104,1u<<29,4);assert(wire_count==0);
  t.data_tx_bytes=300;esp32_spi_transaction(&s,&t);assert(wire_count==300&&desc_reads==2&&!s.m5_dma_out_link);
  assert(!memcmp(wire,ram+0x2000,128)&&!memcmp(wire+128,ram+0x3000,172));
  reset_output();t.data_tx_bytes=4;esp32_spi_transaction(&s,&t);assert(wire_count==4&&desc_reads==0&&wire[0]==1);
 }
 if(test==9){descriptor(0x100,20,20,true,true,0x2000,0);s.m5_dma_out_link=0x100;t.data_tx_bytes=100;esp32_spi_transaction(&s,&t);assert(wire_count==20&&desc_reads==1);}
 if(test==10){descriptor(0x100,20,20,false,true,0x2000,0);s.m5_dma_out_link=0x100;t.data_tx_bytes=20;esp32_spi_transaction(&s,&t);assert(wire_count==0&&desc_reads==1);}
 if(test==11){
  descriptor(0x100,128,0,true,false,0x4000,0x120);descriptor(0x120,192,0,true,false,0x5000,0);
  esp32_spi_write(&s,0x108,0x100,4);esp32_spi_write(&s,0x108,1u<<29,4);t.data_tx_bytes=0;t.data_rx_bytes=300;
  esp32_spi_transaction(&s,&t);assert(wire_count==300&&!s.m5_dma_in_link&&desc_reads==2);
  for(int i=0;i<128;i++)assert(ram[0x4000+i]==0xa5);for(int i=0;i<172;i++)assert(ram[0x5000+i]==0xa5);
  assert(ram[0x4000+128]==0xcc&&ram[0x5000+172]==0xcc);
  assert(!(descriptor_word(0x100)&(1u<<31))&&!(descriptor_word(0x100)&(1u<<30))&&((descriptor_word(0x100)>>12)&0xfff)==128);
  assert(!(descriptor_word(0x120)&(1u<<31))&&(descriptor_word(0x120)&(1u<<30))&&((descriptor_word(0x120)>>12)&0xfff)==172);
  assert(mem_writes==4&&write_addresses[0]==BASE+0x4000&&write_addresses[1]==BASE+0x100&&write_lengths[1]==4);
 }
 if(test==12){
  descriptor(0x100,60,60,true,true,0x2000,0);descriptor(0x120,60,0,true,false,0x4000,0);
  s.m5_dma_out_link=0x100;s.m5_dma_in_link=0x120;t.data_tx_bytes=t.data_rx_bytes=60;levels[5]=0;
  esp32_spi_transaction(&s,&t);assert(wire_count==60&&panel_count==60&&!memcmp(panel,ram+0x2000,60));
  for(int i=0;i<60;i++)assert(ram[0x4000+i]==0x5c);assert(ram[0x403c]==0xcc);
 }
 if(test==13){descriptor(0x100,0,0,true,false,0x4000,0x100);s.m5_dma_in_link=0x100;t.data_tx_bytes=0;t.data_rx_bytes=200;esp32_spi_transaction(&s,&t);assert(desc_reads==1&&mem_writes==0);}
 if(test==14){descriptor(0x100,64,0,false,false,0x4000,0);s.m5_dma_in_link=0x100;t.data_tx_bytes=0;t.data_rx_bytes=64;esp32_spi_transaction(&s,&t);assert(desc_reads==1&&mem_writes==0&&ram[0x4000]==0xcc);}
 if(test==15){descriptor(0x100,1,1,true,false,0x2000,0x100);s.m5_dma_out_link=0x100;t.data_tx_bytes=5000;esp32_spi_transaction(&s,&t);assert(desc_reads==4096&&wire_count==4096);}
 if(test==16){s.m5_dma_out_link=s.m5_dma_in_link=0x100;esp32_spi_write(&s,0x100,12,4);assert(!s.m5_dma_out_link&&!s.m5_dma_in_link);esp32_spi_write(&s,0x104,0x100,4);esp32_spi_write(&s,0x108,0x120,4);esp32_spi_write(&s,0x104,1u<<28,4);esp32_spi_write(&s,0x108,1u<<28,4);assert(!s.m5_dma_out_link&&!s.m5_dma_in_link);}
 if(test==17){esp32_spi_write(&s,A_SPI_MOSI_DLEN,0xffffffff,4);esp32_spi_write(&s,A_SPI_MISO_DLEN,0xffffffff,4);assert(s.mosi_dlen_reg==0xffffff&&s.miso_dlen_reg==0xffffff);}
 if(test==18){levels[5]=0;t.data=s.data_reg+8;t.data_tx_bytes=48;t.data_rx_bytes=16;s.miso_dlen_reg=127;esp32_spi_transaction(&s,&t);assert(wire_count==48&&panel_count==48);for(int i=0;i<48;i++){assert(wire[i]==33+i%32);assert(panel[i]==33+i%32);}}
 if(test==19){levels[5]=0;t.data_tx_bytes=128;t.data_rx_bytes=64;s.miso_dlen_reg=511;esp32_spi_transaction(&s,&t);assert(wire_count==128&&panel_count==128);for(int i=0;i<128;i++){assert(wire[i]==1+i%64);assert(panel[i]==1+i%64);}}
 if(test==20){levels[4]=0;esp32_spi_slave_cs(&s,4,0);routes[4]=11;reset_output();esp32_spi_transaction(&s,&t);assert(wire_count==0&&ssi_count==4);}
 if(test==21){descriptor(0x100,20,20,true,true,0x2000,0);descriptor(0x120,100,0,true,false,0x4000,0);s.m5_dma_out_link=0x100;s.m5_dma_in_link=0x120;t.data_tx_bytes=t.data_rx_bytes=100;esp32_spi_transaction(&s,&t);assert(wire_count==20&&ram[0x4014]==0xcc&&((descriptor_word(0x120)>>12)&0xfff)==20);}
 if(test==22){descriptor(0x100,10,0,true,false,0x4000,0x100);s.m5_dma_in_link=0x100;t.data_tx_bytes=0;t.data_rx_bytes=100;esp32_spi_transaction(&s,&t);assert(desc_reads==2&&mem_writes==2&&ram[0x400a]==0xcc);}
 if(test==23){descriptor(0x100,0,0,true,false,0x2000,0x100);s.m5_dma_out_link=0x100;t.data_tx_bytes=100;esp32_spi_transaction(&s,&t);assert(desc_reads==1&&wire_count==0);}
 if(test==24){levels[5]=0;routes[5]=11;esp32_spi_transaction(&s,&t);assert(panel_count==0);}
 if(test>=25&&test<=28){
  int hspi=test<27,index=(test==25||test==27)?1:2;s.gpio_cs0_signal=hspi?11:68;routes[4]=hspi?60+index:68+index;s.pin_reg=7;
  esp32_spi_transaction(&s,&t);assert(wire_count==0);reset_output();s.pin_reg&=~(1u<<index);
  esp32_spi_transaction(&s,&t);assert(wire_count==4&&last_cs==1&&ssi_count==0);
 }
 if(test==29){
  reset_output();s.spi_slave_cs_level=1;levels[4]=0;esp32_spi_slave_cs(&s,4,0);assert(cs_calls==1);
  for(int i=0;i<3;i++)esp32_spi_transaction(&s,&t);
  assert(wire_count==12&&protocol_cursor==12&&cs_calls==1&&last_cs==0);
  levels[4]=1;esp32_spi_slave_cs(&s,4,1);assert(cs_calls==2&&last_cs==1);
 }
 puts("PASS classic SPI SD DMA");return 0;
}
'''


CASES = (
    'hardware_cs0', 'software_gpio_cs', 'other_controller_cs0', 'disabled_cs0',
    'null_cs_callback', 'disabled_command_with_stale_bitlen', 'enabled_command',
    'hardware_panel_cs0', 'chained_tx_and_no_replay', 'short_tx_eof', 'cpu_owned_tx',
    'chained_rx_capacity_and_owner_order', 'duplex_panel_original_mosi',
    'zero_capacity_rx_cycle', 'cpu_owned_rx', 'bounded_tx_cycle', 'dma_reset_stop',
    'length_register_mask', 'highpart_fifo_boundary', 'duplex_fifo_repeat',
    'gpio_to_other_controller_remap', 'short_duplex_dma', 'rx_cycle_owner_return',
    'zero_length_tx_cycle', 'wrong_controller_panel_cs', 'hspi_cs1', 'hspi_cs2',
    'vspi_cs1', 'vspi_cs2', 'held_gpio_cs_preserves_protocol',
)


def translation_unit(source):
    registers={'CMD':0,'ADDR':4,'CTRL':8,'STATUS':0x10,'CTRL1':0xc,'CTRL2':0x14,'USER':0x1c,'USER1':0x20,'USER2':0x24,'MOSI_DLEN':0x28,'MISO_DLEN':0x2c,'PIN':0x34,'SLAVE':0x38,'W0':0x80}
    defines='\n'.join(f'#define A_SPI_{name} {value}' for name,value in registers.items())+'\n'
    names=['READ','WREN','WRDI','RDID','RDSR','WRSR','PP','SE','BE','CE','DP','RES','USR']
    defines+='\n'.join(f'#define R_SPI_CMD_{name}_MASK (1u<<{index})' for index,name in enumerate(names))+'\n'
    enum=re.search(r'enum\s*\{.*?\};',source,re.S).group(0)
    functions=['esp32_spi_txrx_buffer']
    if 'static int esp32_spi_pin_cs_level' in source:functions+=['esp32_spi_pin_cs_level']
    functions+=['esp32_spi_cs_set']
    functions+=['esp32_spi_dma_copy','esp32_spi_dma_transfer'] if 'static uint32_t esp32_spi_dma_copy' in source else ['esp32_spi_m5_dma_panel']
    functions+=['esp32_spi_transaction','esp32_spi_slave_cs','bitlen_to_bytes','esp32_spi_do_command','esp32_spi_write']
    return STUBS+defines+enum+'\n'+'\n'.join(function(source,name) for name in functions)+MAIN


@unittest.skipUnless(shutil.which('git') and shutil.which('cc'), 'git and C compiler required')
class ClassicSpiSdDmaTests(unittest.TestCase):
    def test_actual_classic_spi_full_prefix_before_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            seed=ROOT/'platform/tests/fixtures/classic_spi_upstream/esp32_spi.c'
            self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(),'c563518d0829bd656389629ea0cbd951ad5e89def13f4777e49dc6526386b797')
            (root/SPI).parent.mkdir(parents=True);(root/SPI).write_bytes(seed.read_bytes())
            for prior in bootstrap_stack(full=True):
                if prior==PATCH:break
                subprocess.run(['git','apply','--include='+SPI,str(ROOT/prior)],cwd=root,check=True,capture_output=True)
            before=(root/SPI).read_text()
            subprocess.run(['git','apply','--include='+SPI,str(ROOT/PATCH)],cwd=root,check=True,capture_output=True)
            after=(root/SPI).read_text()
            subprocess.run(['git','apply','--reverse','--check','--include='+SPI,str(ROOT/PATCH)],cwd=root,check=True,capture_output=True)
            for label,source in [('before',before),('after',after)]:
                c=root/(label+'.c');exe=root/label;c.write_text(translation_unit(source))
                result=subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined',str(c),'-o',str(exe)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                for case, description in enumerate(CASES):
                    with self.subTest(source=label,case=description):
                        result=subprocess.run([str(exe),str(case)],capture_output=True,text=True)
                        if label=='before' and case in (0,4,5,7,10,11,12,13,14,16,17,18,19,20,21,22,23,24,25,26,27,28):
                            self.assertNotEqual(result.returncode,0,'negative control unexpectedly passed')
                        else:
                            self.assertEqual(result.returncode,0,result.stderr)
