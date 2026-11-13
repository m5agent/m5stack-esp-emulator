"""Actual C6 endpoint plus upstream CDC consumer interleavings (not guest runs)."""
from pathlib import Path
import os
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from test_c6_wifi_tsf_patch import function
from test_c6_usb_serial_jtag_patch import STUB as ENDPOINT_STUB

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).with_name('fixtures') / 'c6_usb_serial_jtag'
FIXTURE = Path(__file__).with_name('fixtures') / 'c6_usb_host_timing'
PATCHES = ROOT / 'patches/qemu-esp32c6-uiflow2-adapters'
PATCH = PATCHES / '0022-c6-usb-serial-jtag-host-timing.patch'
STUB = ENDPOINT_STUB.replace('#define qemu_clock_get_ms(c) (now)',
 'static int64_t qemu_clock_get_ms(int c){return now / 1000000;}\nstatic int64_t qemu_clock_get_ns(int c){return now;}').replace(
 '#define timer_mod(t,d) ((void)0)', 'static int64_t deadline;\n#define timer_mod(t,d) (deadline=(d)*1000000)\n#define timer_mod_ns(t,d) (deadline=(d))')
DRIVER_STUB = r'''
#define IRAM_ATTR
#define CONFIG_USJ_NO_AUTO_LS_ON_CONNECTION 0
#define ALLOWED_NO_SOF_TICKS 3
#define USB_SERIAL_JTAG_INTR_SOF 2
#define USB_SERIAL_JTAG_INTR_SERIAL_IN_EMPTY 8
#define USB_SERIAL_JTAG_INTR_SERIAL_OUT_RECV_PKT 4
#define USB_SERIAL_JTAG_INTR_BUS_RESET 16
static ESP32C6UsbJtagState s;
static uint32_t rd(unsigned r){return esp32c6_jtag_read(&s,r,4);}
static void wr(unsigned r,uint32_t v){esp32c6_jtag_write(&s,r,v,4);}
static uint32_t usb_serial_jtag_ll_get_intraw_mask(void){return rd(8);}
static void usb_serial_jtag_ll_clr_intsts_mask(uint32_t mask){wr(0x14,mask);}
static unsigned removed, added;
static void rtc_clk_bbpll_remove_consumer(void){removed++;}
static void rtc_clk_bbpll_add_consumer(void){added++;}
static volatile bool s_usb_serial_jtag_conn_status;
static uint32_t remaining_allowed_no_sof_ticks;
static bool bridge_is_plugged(void){return s_usb_serial_jtag_conn_status;}
typedef int portBASE_TYPE; typedef int BaseType_t;
#define pdTRUE 1
#define portYIELD_FROM_ISR() ((void)0)
#define ARDUINO_HW_CDC_EVENTS 0
#define ARDUINO_HW_CDC_TX_EVENT 1
#define ARDUINO_HW_CDC_RX_EVENT 2
#define ARDUINO_HW_CDC_BUS_RESET_EVENT 3
typedef struct {struct{unsigned len;}tx,rx;} arduino_hw_cdc_event_data_t;
static uint8_t tx_ring[153],rx_data_buf[64];static unsigned ring_pos;
static void *tx_ring_buf=(void*)1, *rx_queue;
static volatile bool connected;
static uint32_t usb_serial_jtag_ll_get_intsts_mask(void){return rd(0xc);}
static unsigned usb_serial_jtag_ll_txfifo_writable(void){return !!(rd(4)&2);}
static void usb_serial_jtag_ll_disable_intr_mask(unsigned m){wr(0x10,rd(0x10)&~m);}
static void usb_serial_jtag_ll_ena_intr_mask(unsigned m){wr(0x10,rd(0x10)|m);}
static uint8_t *xRingbufferReceiveUpToFromISR(void *r,size_t *n,unsigned limit){
 *n=MIN(sizeof(tx_ring)-ring_pos,limit);return *n?tx_ring+ring_pos:NULL;}
static void vRingbufferReturnItemFromISR(void*r,void*b,portBASE_TYPE*w){
 assert(b==tx_ring+ring_pos);ring_pos+=MIN(sizeof(tx_ring)-ring_pos,64u);}
static void usb_serial_jtag_ll_write_txfifo(uint8_t*b,size_t n){for(size_t i=0;i<n;i++)wr(0,b[i]);}
static void usb_serial_jtag_ll_txfifo_flush(void){wr(4,1);}
static unsigned usb_serial_jtag_ll_read_rxfifo(uint8_t*b,unsigned n){unsigned i=0;while(i<n&&(rd(4)&4))b[i++]=rd(0);return i;}
static bool xQueueSendFromISR(void*q,uint8_t*b,portBASE_TYPE*w){return true;}
static void arduino_hw_cdc_event_post(int b,int e,void*d,size_t n,portBASE_TYPE*w){}
'''
MAIN = r'''
static void run_due(void){if(deadline<=now)callback(&s);}
static void init(void){setup(&s);esp32c6_jtag_reset_hold(&s,0);s_usb_serial_jtag_conn_status=true;
 remaining_allowed_no_sof_ticks=3;for(unsigned i=0;i<sizeof(tx_ring);i++)tx_ring[i]=(i*7+3)&255;}
static void at(int64_t ns){now=ns;}
static void fifo(unsigned n){for(unsigned i=0;i<n;i++)wr(0,(i*7+3)&255);}
static void monitor_at(int64_t ns){at(ns);usb_serial_jtag_sof_tick_hook();}
int main(int argc,char**argv){
 assert(argc==2);unsigned test=atoi(argv[1]);init();
 switch(test){
 case 0: /* SOF is visible at MMIO before a delayed timer dispatch. */
  for (int i = 1; i <= 8; i++) {
   monitor_at(i * 1000000);
  }
  assert(s_usb_serial_jtag_conn_status && removed == 0);
  break;
 case 1:wr(0x14,~0u);wr(0x10,8);wr(4,1);at(7999);assert(!(rd(8)&8));
  at(8000);run_due();assert((rd(8)&8)&&irq_level&&s.tx_packets==1&&received_len==0);break;
 case 2:fifo(64);at(63999);assert(!received_len&&!(rd(4)&2));
  at(64000);run_due();assert(received_len==64&&(rd(4)&2));assert(!(rd(8)&2));break;
 case 3:fifo(3);wr(4,1);at(32000);wr(4,1);at(64000);run_due();
  assert(received_len==3&&s.tx_packets==1&&(rd(8)&8));break;
 case 4: /* Catch-up preserves SOF phase and frame count. */
  at(3500000);run_due();assert(rd(0x24)==3);wr(0x14,2);at(3999999);assert(!(rd(8)&2));
  at(4000000);assert((rd(8)&2)&&rd(0x24)==4);break;
 case 5:wr(0x10,2);at(1000000);assert(rd(8)&2);wr(0x14,2);assert(!(rd(8)&2)&&!irq_level);
  at(1999999);assert(!(rd(8)&2));at(2000000);assert((rd(8)&2)&&irq_level);break;
 case 6:fifo(5);wr(4,1);write_limit=2;at(64000);run_due();assert(received_len==2&&!(rd(4)&2));
  at(128000);run_due();assert(received_len==4&&!(rd(4)&2));at(192000);run_due();assert(received_len==5&&(rd(4)&2));break;
 case 7:fifo(2);wr(4,1);write_limit=0;at(64000);run_due();assert(!received_len&&!(rd(4)&2));
  write_limit=-1;at(128000);run_due();assert(!received_len&&!(rd(8)&8));
  write_limit=64;at(192000);run_due();assert(received_len==2);break;
 case 8:fifo(3);wr(4,1);wr(0x18,0);at(2000000);run_due();assert(!received_len&&!(rd(8)&2));
  wr(0x18,(1u<<14)|(1u<<9));at(2063999);assert(!received_len&&!(rd(4)&2));
  at(2064000);run_due();assert(received_len==3);break;
 case 9:fifo(3);wr(4,1);opened=false;at(64000);run_due();assert(!received_len&&!(rd(8)&8));
  opened=true;at(1000000);run_due();assert(!received_len);at(1064000);run_due();assert(received_len==3);break;
 case 10:fifo(3);wr(4,1);at(32000);esp32c6_jtag_reset_hold(&s,0);
  at(64000);run_due();assert(!received_len&&rd(0x10)==0&&(rd(4)&2));
  at(1031999);assert(!(rd(8)&2));at(1032000);assert(rd(8)&2);break;
 case 11:bound=false;fifo(64);at(5000000);run_due();assert(!received_len&&!(rd(8)&8)&&rd(0x24)==0);break;
 case 12:{uint8_t b[]={8,9};esp32c6_jtag_receive(&s,b,2);wr(0x10,4);assert(irq_level);
  at(1000000);run_due();assert((rd(8)&6)==6);wr(0x14,4);assert(!irq_level&&(rd(4)&4));assert(rd(0)==8&&rd(0)==9);break;}
 case 13:at(2049000000LL);run_due();assert(rd(0x24)==1);break;
 case 14:wr(0x10,8);wr(0x14,~0u);fifo(2);assert(!(rd(8)&8));at(10000000);run_due();
  assert(received_len==0&&(rd(4)&2));break;
 case 15: /* A real host detachment must still disconnect. */
  opened=false;for(int i=1;i<=4;i++){at(i*1000000);run_due();usb_serial_jtag_sof_tick_hook();}
  assert(!s_usb_serial_jtag_conn_status&&removed==1);opened=true;at(5000000);run_due();usb_serial_jtag_sof_tick_hook();
  assert(s_usb_serial_jtag_conn_status&&added==1);break;
 case 16:case 17:case 18:{
  /* Unmodified upstream ISR/monitor, controlled delayed host callbacks.
     Distinct controls let 0/64/128 bytes reach the host before the gap. */
  unsigned prefix=(test-16)*64;wr(0x10,8);
  while(received_len<prefix){hw_cdc_isr_handler(NULL);at(now+1000000);run_due();}
  for(int i=1;i<=5;i++)monitor_at(now+1000000);
  hw_cdc_isr_handler(NULL);
  for(int i=0;i<8;i++){at(now+1000000);run_due();hw_cdc_isr_handler(NULL);}
  fprintf(stderr,"cdc-prefix=%u total=%u ring-consumed=%u connected=%u\n",prefix,received_len,ring_pos,s_usb_serial_jtag_conn_status);
  assert(received_len==sizeof(tx_ring)&&ring_pos==sizeof(tx_ring));
  assert(!memcmp(received,tx_ring,sizeof(tx_ring)));break;}
 case 19:{uint8_t b=42;esp32c6_jtag_receive(&s,&b,1);wr(0x10,14);wr(4,1);at(1000000);run_due();
   assert((rd(8)&14)==14);wr(0x14,8);assert((rd(8)&14)==6&&irq_level);assert(rd(0)==42);}break;
 case 20:esp32c6_jtag_unrealize(&s);assert(handlers_removed&&timer_freed);break;
 case 21: /* A latched final SOF is consumed once, never refreshed offline. */
  at(1000000);run_due();assert(rd(8)&2);opened=false;usb_serial_jtag_sof_tick_hook();
  assert(!(rd(8)&2));for(int i=2;i<=5;i++){at(i*1000000);run_due();usb_serial_jtag_sof_tick_hook();}
  assert(!s_usb_serial_jtag_conn_status&&removed==1&&rd(0x24)==1&&!(rd(8)&2));break;
 case 22: /* External PHY and override without pull-up both gate traffic. */
  for(unsigned gate=0;gate<2;gate++){
   wr(0x18,gate?((1u<<14)|(1u<<8)):((1u<<14)|1));fifo(3);wr(4,1);
   at(now+2000000);run_due();assert(received_len==3*gate&&esp32c6_jtag_can_receive(&s)==0);
   wr(0x18,(1u<<14)|(1u<<9));at(now+64000);run_due();assert(received_len==3*(gate+1));}break;
 case 23:{uint8_t b[64];memset(b,90,sizeof(b));esp32c6_jtag_receive(&s,b,64);
  assert(!esp32c6_jtag_can_receive(&s));b[0]=8;esp32c6_jtag_receive(&s,b,1);
  for (int i = 0; i < 64; i++) {
   assert(rd(0) == 90);
  }
  assert(esp32c6_jtag_can_receive(&s) == 64);
  esp32c6_jtag_receive(&s,b,1);assert(rd(0)==8);break;}
 case 24:drop_timer(&s);bound=false;esp32c6_jtag_reset_hold(&s,0);fifo(64);wr(4,1);at(10000000);
  assert(!(rd(4)&2)&&!(rd(8)&8)&&received_len==0&&rd(0x24)==0);break;
 case 25:fifo(64);wr(4,1);at(32000);wr(4,1);at(64000);run_due();assert(received_len==64);
  for (unsigned i = 0; i < 64; i++) {
   assert(received[i] == ((i * 7 + 3) & 255));
  }
  break;
 case 26:{ESP32C6UsbJtagState other={0};setup(&other);at(500000);esp32c6_jtag_reset_hold(&other,0);
  at(1000000);assert(rd(0x24)==1&&esp32c6_jtag_read(&other,0x24,4)==0);
  at(1500000);assert(esp32c6_jtag_read(&other,0x24,4)==1&&rd(0x24)==1);break;}
 case 27:fifo(3);wr(4,1);at(32000);esp32c6_jtag_reset_hold(&s,0);wr(0,42);wr(4,1);
  at(64000);run_due();assert(!received_len);at(96000);run_due();assert(received_len==1&&received[0]==42);break;
 case 28:wr(0x10,~0u);assert(rd(0x10)==14);wr(0x14,~0u);assert(!irq_level&&rd(0xc)==0);break;
 case 29:fifo(3);wr(4,1);opened=false;at(64000);assert(!(rd(8)&8)&&!received_len);
  opened=true;at(2000000);assert(!(rd(8)&8)&&!received_len);at(2064000);run_due();assert(received_len==3);break;
 default:abort();
 }
 printf("PASS actual endpoint timing %u\n",test);return 0;
}
'''


def build(source, output, after):
    text = (source / 'hw/misc/esp32c6_jtag.c').read_text()
    header = (source / 'include/hw/misc/esp32c6_jtag.h').read_text()
    code = STUB + re.sub(r'^#(?:include|pragma).*\n', '', header, flags=re.M)
    code += re.search(r'enum \{.*?\n\};', text, re.S).group()
    names = ['update_irq', 'host_attached', 'can_receive', 'receive']
    names += ['schedule', 'start_in', 'sync_host', 'host_timer', 'commit'] if after else ['host_frame']
    names += ['read', 'write', 'reset_hold', 'unrealize']
    for name in names:
        code += function(text, 'esp32c6_jtag_' + name)
    timer = 'host_timer' if after else 'host_frame'
    code += f'\nstatic void setup(ESP32C6UsbJtagState*s){{s->{timer}=(void*)1;}}\n'
    code += f'static void callback(ESP32C6UsbJtagState*s){{esp32c6_jtag_{timer}(s);}}\n'
    code += f'static void drop_timer(ESP32C6UsbJtagState*s){{s->{timer}=NULL;}}\n'
    code += DRIVER_STUB
    code += function((FIXTURE / 'usb_serial_jtag_connection_monitor.c').read_text(), 'usb_serial_jtag_sof_tick_hook')
    consumer = function((FIXTURE / 'HWCDC.cpp').read_text().replace('static void hw_cdc_isr_handler(void *arg) {', 'static void hw_cdc_isr_handler(void *arg)\n{'), 'hw_cdc_isr_handler')
    # Only bind the C++ inline API name to the C state reader. The ISR flow
    # and ring operations are extracted from the unchanged upstream source.
    code += consumer.replace('HWCDC::isPlugged()', 'bridge_is_plugged()') + MAIN
    output.with_suffix('.c').write_text(code)
    subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                    '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-function',
                    '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                    str(output.with_suffix('.c')),'-o',str(output)],check=True,capture_output=True,text=True)


def apply(source, patch):
    includes = ['--include=hw/misc/esp32c6_jtag.c','--include=include/hw/misc/esp32c6_jtag.h']
    for options in (['--check'], [], ['--reverse','--check']):
        subprocess.run(['git','apply',*includes,*options,str(patch)],cwd=source,check=True,capture_output=True)


@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'C compiler and git required')
class C6UsbHostTimingTests(unittest.TestCase):
    def test_pinned_upstream_consumers(self):
        for name, digest in {
            'HWCDC.cpp': '29b6f2da994afc86b9c8b88c286f5ae039a756bc7316f20da0a8af1ee4df6cd9',
            'usb_serial_jtag_connection_monitor.c': '6d5ee3b3d7824155ba956a973b7767e4b0e473fc4d0776c738a63c782f27a49f',
        }.items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), digest)

    def test_actual_controller_driver_interleavings(self):
        unchanged = {11, 12, 13, 14, 15, 19, 20, 21, 23, 24, 28, 29}
        with tempfile.TemporaryDirectory(prefix='m5-c6-usb-timing-') as temp:
            temp = Path(temp)
            for after in (False, True):
                source = temp / ('after-source' if after else 'before-source')
                shutil.copytree(BASE, source)
                # Never let git apply resolve paths in an enclosing worktree.
                subprocess.run(['git','init','-q'],cwd=source,check=True,capture_output=True)
                apply(source, PATCHES / '0020-c6-usb-serial-jtag-endpoints.patch')
                for path, digest in {
                    'hw/misc/esp32c6_jtag.c': '42a44e2d592e81824740657031d646bf19689a4c160217a2f90b87ce975e8bb1',
                    'include/hw/misc/esp32c6_jtag.h': '000c4de19ca0120c2bed591fdd812b1aeb6ebfc97d1f99b52eee46a0abc4fc03',
                }.items():
                    self.assertEqual(hashlib.sha256((source / path).read_bytes()).hexdigest(), digest)
                if after:
                    apply(source, PATCH)
                binary = temp / ('after' if after else 'before')
                try:
                    build(source, binary, after)
                except subprocess.CalledProcessError as error:
                    self.fail(error.stderr)
                for case in range(30):
                    with self.subTest(after=after, case=case):
                        result = subprocess.run([str(binary),str(case)],capture_output=True,text=True,timeout=10,
                                                env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
                        if after or case in unchanged:
                            self.assertEqual(result.returncode,0,result.stderr)
                        else:
                            self.assertNotEqual(result.returncode,0)
                            self.assertIn('assert',result.stderr.lower())
                            if case in (16, 17, 18):
                                prefix = (case - 16) * 64
                                self.assertIn(f'cdc-prefix={prefix} total={prefix} ring-consumed={prefix} connected=0', result.stderr)


if __name__ == '__main__':
    unittest.main()
