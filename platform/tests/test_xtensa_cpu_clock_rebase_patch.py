"""Execute actual CPU clock-switch, compare callback and reset C functions.

QEMU's Q32-nanosecond clock arithmetic is represented in the host shim. Oracles
use fixed tick counts and independent deadlines; these are host controls, not
original-firmware or physical-clock validation.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function
from test_xtensa_inactive_irq_yield_guard_patch import fragment, hunks
from test_xtensa_wallclock_noop_yield_patch import function

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0197-xtensa-clock-switch-cycle-continuity.patch'
IRQ_PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0194-xtensa-restored-irq-level.patch'

HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#define CLOCK_PERIOD_1SEC (UINT64_C(1000000000)<<32)
#define CLOCK_PERIOD_FROM_HZ(hz) ((hz)?CLOCK_PERIOD_1SEC/(hz):0u)
#define QEMU_CLOCK_VIRTUAL 1
#define ESP32_CPU_COUNT 2
#define ESP32_SOC_CLK_PLL 1
#define PS_EXCM 16
#define PS_UM 32
#define PS_RING_SHIFT 6
#define PS_WOE 128
#define MEMCTL_IL0EN 255
enum { PS,CCOUNT,CCOMPARE,CCOMPARE1,CCOMPARE2,INTSET,INTENABLE,LITBASE,
 CPENABLE,VECBASE,IBREAKENABLE,MEMCTL,ATOMCTL,CONFIGID0,CONFIGID1 };
enum { XTENSA_OPTION_TIMER_INTERRUPT,XTENSA_OPTION_DFP_COPROCESSOR,
 XTENSA_OPTION_INTERRUPT,XTENSA_OPTION_ATOMCTL };
#define EXC_RESET0 0
typedef struct { uint64_t period; unsigned updates; } Clock;
typedef struct { bool pending; int64_t due; unsigned modifications; } QEMUTimer;
typedef struct CPUXtensaState CPUXtensaState;
typedef struct { unsigned cpu_index,halted; CPUXtensaState *env; } CPUState;
typedef struct { CPUXtensaState *env; QEMUTimer *timer; } XtensaCcompareTimer;
typedef struct { bool timer_option; unsigned nccompare,timerint[3],exception_vector[16],
 vecbase,memctl_mask,configid[2]; } Config;
struct CPUXtensaState { CPUState cpu; Config *config; uint64_t time_base,ccount_time;
 uint32_t ccount_base,sregs[32],pc,static_vectors,exclusive_addr,runstall,fp_status;
 unsigned pending_irq_level; uint8_t high_priority_irq_levels;
 XtensaCcompareTimer ccompare[3]; unsigned *irq_inputs; };
typedef struct { CPUXtensaState env; Clock *clock; } XtensaCPU;
typedef CPUState Object;
typedef unsigned ResetType;
typedef struct { struct { void (*hold)(Object *,ResetType); } parent_phases; } XtensaCPUClass;
static XtensaCPUClass cpu_class;
#define CPU(obj) (obj)
#define XTENSA_CPU_GET_CLASS(obj) (&cpu_class)
static CPUXtensaState *cpu_env(CPUState *cs) { return cs->env; }
static bool xtensa_option_enabled(Config *config,unsigned option) {
 return option==XTENSA_OPTION_TIMER_INTERRUPT?config->timer_option:option==XTENSA_OPTION_INTERRUPT;
}
static void icount_note_high_priority_irq(unsigned cpu,bool active) { }
static void reset_mmu(CPUXtensaState *env) { }
static void set_no_signaling_nans(bool value,unsigned *status) { }
static void xtensa_use_first_nan(CPUXtensaState *env,bool value) { }
/* Q32 arithmetic follows include/hw/clock.h at canonical 40edccac. */
static uint64_t clock_get(Clock *clock) { return clock->period; }
static uint64_t clock_ns_to_ticks(Clock *clock,uint64_t ns) {
 return clock->period?(uint64_t)(((__uint128_t)ns<<32)/clock->period):0;
}
static uint64_t clock_ticks_to_ns(Clock *clock,uint64_t ticks) {
 __uint128_t ns=((__uint128_t)clock->period*ticks)>>32;
 return ns>INT64_MAX?INT64_MAX:(uint64_t)ns;
}
static void clock_update(Clock *clock,uint64_t period) { clock->period=period;clock->updates++; }
static void clock_update_hz(Clock *clock,unsigned hz) { clock_update(clock,CLOCK_PERIOD_FROM_HZ(hz)); }
static bool timer_pending(QEMUTimer *timer) { return timer->pending; }
static int64_t timer_expire_time_ns(QEMUTimer *timer) { return timer->due; }
static void timer_mod_ns(QEMUTimer *timer,int64_t due) {
 if(OMIT_RETIME)return;
 timer->pending=true;timer->due=due;timer->modifications++;
}
static unsigned irq_count,last_irq,last_level;
static void qemu_set_irq(unsigned irq,unsigned level) { irq_count++;last_irq=irq;last_level=level; }
/* ACTUAL_HELPER_CALLBACK_RESET */
typedef struct { unsigned apb_freq,writes; } ApbDevice;
typedef struct { XtensaCPU cpu[2]; struct { unsigned soc_clk,pll_apb_freq,xtal_apb_freq; } rtc_cntl;
 struct { unsigned cpuperiod_sel; } dport; ApbDevice frc_timer,timg[2]; } Esp32SocState;
#define ESP32_SOC(p) ((Esp32SocState*)(p))
#define DEVICE(p) (p)
static uint64_t now_ns;static unsigned now_reads;static bool mttcg;
static bool qemu_tcg_mttcg_enabled(void) { return mttcg; }
static uint64_t qemu_clock_get_ns(unsigned type) { assert(type==QEMU_CLOCK_VIRTUAL);now_reads++;return now_ns; }
static void qdev_prop_set_int32(ApbDevice *device,const char *name,unsigned value) {
 assert(!strcmp(name,"apb_freq"));device->apb_freq=value;device->writes++;
}
/* ACTUAL_BOARD */
static Config config={.timer_option=true,.nccompare=3,.timerint={6,15,16}};
static unsigned irq_inputs[32];
static void init(XtensaCPU *cpu,Clock *clock,QEMUTimer timers[3],unsigned hz) {
 memset(cpu,0,sizeof(*cpu));memset(timers,0,3*sizeof(*timers));*clock=(Clock){CLOCK_PERIOD_FROM_HZ(hz),0};
 cpu->clock=clock;cpu->env.config=&config;cpu->env.cpu.env=&cpu->env;cpu->env.irq_inputs=irq_inputs;
 cpu->env.sregs[PS]=0x60025;cpu->env.sregs[INTENABLE]=0x80000044;
 for(unsigned i=0;i<3;i++) {cpu->env.ccompare[i]=(XtensaCcompareTimer){&cpu->env,&timers[i]};timers[i].due=-1;}
}
static uint32_t count_at(XtensaCPU *cpu,uint64_t time) {
 return cpu->env.ccount_base+clock_ns_to_ticks(cpu->clock,time-cpu->env.time_base);
}
static void board_controls(void) {
 Esp32SocState soc={0};Clock clocks[2];QEMUTimer timers[2][3];
 for(unsigned i=0;i<2;i++) {
  init(&soc.cpu[i],&clocks[i],timers[i],i?80000000:160000000);soc.cpu[i].env.cpu.cpu_index=i;
  soc.cpu[i].env.time_base=1000000;soc.cpu[i].env.ccount_base=100+i;
 }
 soc.rtc_cntl.soc_clk=ESP32_SOC_CLK_PLL;soc.rtc_cntl.pll_apb_freq=80000000;soc.dport.cpuperiod_sel=2;
 now_ns=11000000;uint32_t before[2]={1600100,800101};assert(count_at(&soc.cpu[0],now_ns)==before[0]);assert(count_at(&soc.cpu[1],now_ns)==before[1]);
 for(unsigned i=0;i<2;i++){soc.cpu[i].env.sregs[CCOMPARE]=before[i]+240000;timers[i][0]=(QEMUTimer){true,(int64_t)(now_ns+3000000),0};}
 unsigned reads=now_reads;(OLD_BOARD?before_board:after_board)(&soc,0,1);
 for(unsigned i=0;i<2;i++) {
  assert(count_at(&soc.cpu[i],now_ns)==before[i]);
  assert(soc.cpu[i].env.time_base==now_ns&&soc.cpu[i].env.sregs[CCOUNT]==before[i]);
  /* 240000 cycles at 240MHz, rounded by QEMU's Q32 period: 999999ns. */
  assert(timers[i][0].due==(int64_t)(now_ns+999999));
 }
 assert(now_reads==reads+1);assert(soc.frc_timer.apb_freq==80000000&&soc.timg[0].apb_freq==80000000&&soc.timg[1].apb_freq==80000000);
 assert(soc.frc_timer.writes==1&&soc.timg[0].writes==1&&soc.timg[1].writes==1);
 Esp32SocState previous=soc;Clock previous_clocks[2]={clocks[0],clocks[1]};reads=now_reads;
 after_board(&soc,0,0);assert(!memcmp(&previous,&soc,sizeof(soc))&&!memcmp(previous_clocks,clocks,sizeof(clocks))&&reads==now_reads);
 /* XTAL path retains its original APB fanout. */
 soc.rtc_cntl.soc_clk=0;soc.rtc_cntl.xtal_apb_freq=40000000;after_board(&soc,0,1);
 assert(soc.frc_timer.apb_freq==40000000&&clocks[0].period==CLOCK_PERIOD_FROM_HZ(40000000));
 /* MTTCG retains its pre-existing clock-only behavior: no cross-thread env
  * mutation or virtual-time read is introduced by this serialized fix. */
 CPUXtensaState saved_env[2]={soc.cpu[0].env,soc.cpu[1].env};reads=now_reads;
 soc.rtc_cntl.soc_clk=ESP32_SOC_CLK_PLL;soc.dport.cpuperiod_sel=1;mttcg=true;
 after_board(&soc,0,1);mttcg=false;
 assert(now_reads==reads&&clocks[0].period==CLOCK_PERIOD_FROM_HZ(160000000));
 for(unsigned i=0;i<2;i++)assert(!memcmp(&saved_env[i],&soc.cpu[i].env,sizeof(saved_env[i])));

}
static unsigned rate_controls(void) {
 const unsigned rates[]={40000000,80000000,160000000,240000000};unsigned checks=0;
 for(unsigned a=0;a<4;a++)for(unsigned b=0;b<4;b++) {
  XtensaCPU cpu,peer;Clock clock,peer_clock;QEMUTimer timers[3],peer_timers[3];
  init(&cpu,&clock,timers,rates[a]);init(&peer,&peer_clock,peer_timers,80000000);peer.env.cpu.cpu_index=1;
  cpu.env.ccount_base=UINT32_MAX-99;cpu.env.time_base=1000000;
  uint64_t now=2000000;uint32_t count=(uint32_t)(UINT32_MAX-99+rates[a]/1000);
  assert(count_at(&cpu,now)==count);
  cpu.env.sregs[CCOUNT]=17;cpu.env.sregs[CCOMPARE]=count+160000;
  cpu.env.sregs[CCOMPARE1]=count+1;cpu.env.sregs[CCOMPARE2]=count+80000;
  timers[0]=(QEMUTimer){true,(int64_t)(now+4000000),0};timers[1]=(QEMUTimer){true,(int64_t)(now+100),0};
  uint32_t regs[32];memcpy(regs,cpu.env.sregs,sizeof(regs));CPUXtensaState peer_env=peer.env;
  xtensa_cpu_update_clock_hz(&cpu,rates[b],now);
  assert(count_at(&cpu,now)==count);
  if(a==b) {assert(cpu.env.time_base==1000000&&cpu.env.sregs[CCOUNT]==17&&clock.updates==0);assert(timers[0].due==(int64_t)(now+4000000));}
  else {
   assert(cpu.env.time_base==now&&cpu.env.ccount_time==now&&cpu.env.sregs[CCOUNT]==count&&clock.updates==1);
   uint64_t p=CLOCK_PERIOD_FROM_HZ(rates[b]);
   assert(timers[0].due==(int64_t)(now+(uint64_t)(((__uint128_t)p*160000)>>32)));
   assert(timers[1].due==(int64_t)(now+(p>>32)));
   assert(timers[0].modifications==1&&timers[1].modifications==1);
  }
  for(unsigned i=0;i<32;i++)if(i!=CCOUNT)assert(cpu.env.sregs[i]==regs[i]);
  assert(!timers[2].pending&&timers[2].due==-1);
  assert(!memcmp(&peer.env,&peer_env,sizeof(peer_env))&&peer_clock.updates==0);checks++;
 }
 return checks;
}
static void edge_controls(void) {
 XtensaCPU cpu;Clock clock;QEMUTimer timers[3];uint64_t now=2000000;
 init(&cpu,&clock,timers,0);cpu.env.ccount_base=123;xtensa_cpu_update_clock_hz(&cpu,80000000,now);
 assert(cpu.env.ccount_base==123&&cpu.env.time_base==now&&count_at(&cpu,now+1000)==203);
 /* No timer option leaves its accounting untouched, while changing clock. */
 init(&cpu,&clock,timers,160000000);config.timer_option=false;cpu.env.ccount_base=5;cpu.env.time_base=19;
 xtensa_cpu_update_clock_hz(&cpu,80000000,now);assert(cpu.env.ccount_base==5&&cpu.env.time_base==19&&clock.updates==1);config.timer_option=true;
 /* Pending deadline already due or overdue remains due, not another wrap. */
 for(unsigned overdue=0;overdue<2;overdue++) {
  init(&cpu,&clock,timers,160000000);cpu.env.time_base=now;cpu.env.ccount_base=100;
  cpu.env.sregs[CCOMPARE]=99;timers[0]=(QEMUTimer){true,(int64_t)now-overdue,0};
  xtensa_cpu_update_clock_hz(&cpu,80000000,now);assert(timers[0].due==(int64_t)now-overdue&&timers[0].modifications==0);
 }
 /* Latched IRQ is not cleared/rearmed; no timer is invented for NULL. */
 init(&cpu,&clock,timers,160000000);cpu.env.sregs[INTSET]=64;cpu.env.sregs[CCOMPARE]=19;
 cpu.env.ccompare[2].timer=NULL;xtensa_cpu_update_clock_hz(&cpu,80000000,now);
 assert(cpu.env.sregs[INTSET]==64&&!timers[0].pending&&!timers[1].pending&&cpu.env.ccompare[2].timer==NULL);
 /* Unsigned wrap: ten ticks remain, rather than clamping an expired value. */
 init(&cpu,&clock,timers,160000000);cpu.env.time_base=now;cpu.env.ccount_base=UINT32_MAX-4;cpu.env.sregs[CCOMPARE]=5;
 timers[0]=(QEMUTimer){true,(int64_t)now+1000,0};xtensa_cpu_update_clock_hz(&cpu,80000000,now);
 assert(timers[0].due==(int64_t)now+125);
 /* A genuinely wrapped future match must not be clamped to an immediate
  * interrupt merely because its signed delta is negative. */
 init(&cpu,&clock,timers,160000000);cpu.env.time_base=now;cpu.env.ccount_base=100;cpu.env.sregs[CCOMPARE]=99;
 timers[0]=(QEMUTimer){true,(int64_t)now+30000000000LL,0};xtensa_cpu_update_clock_hz(&cpu,80000000,now);
 assert(timers[0].due==(int64_t)now+53687091187LL);
 /* Equal-cycle armed match keeps the established one-tick policy. */
 init(&cpu,&clock,timers,160000000);cpu.env.time_base=now;cpu.env.ccount_base=100;cpu.env.sregs[CCOMPARE]=100;
 timers[0]=(QEMUTimer){true,(int64_t)now+1000,0};xtensa_cpu_update_clock_hz(&cpu,80000000,now);assert(timers[0].due==(int64_t)now+12);
 unsigned before=irq_count;xtensa_ccompare_cb(&cpu.env.ccompare[0]);assert(irq_count==before+1&&last_irq==6&&last_level==1);
 /* Reset remains the actual unchanged Xtensa reset, including timer state. */
 uint64_t base_time=cpu.env.time_base;uint32_t base_count=cpu.env.ccount_base,compare=cpu.env.sregs[CCOMPARE];QEMUTimer saved=timers[0];
 actual_reset(&cpu.env.cpu,0);assert(cpu.env.time_base==base_time&&cpu.env.ccount_base==base_count&&cpu.env.sregs[CCOMPARE]==compare&&!memcmp(&saved,&timers[0],sizeof(saved)));
 now+=1000;uint32_t expected=base_count+80;xtensa_cpu_update_clock_hz(&cpu,160000000,now);assert(count_at(&cpu,now)==expected);
}
int main(void) {
 for(unsigned i=0;i<32;i++)irq_inputs[i]=i;
 if(ZERO_INPUT) {XtensaCPU cpu;Clock clock;QEMUTimer timers[3];init(&cpu,&clock,timers,80000000);xtensa_cpu_update_clock_hz(&cpu,0,1);return 0;}
 board_controls();unsigned rates=rate_controls();edge_controls();
 printf("XTENSA_CLOCK_REBASE_HOST_PASS rate_pairs=%u\n",rates);return 0;
}
'''


def actual_code():
    pic = fragment(PATCH, 'hw/xtensa/pic_cpu.c')
    helper = extract_function(pic, 'void xtensa_cpu_update_clock_hz(')
    callback = function(pic, 'xtensa_ccompare_cb')
    reset = function(fragment(IRQ_PATCH, 'target/xtensa/cpu.c'), 'xtensa_cpu_reset_hold').replace(
        'xtensa_cpu_reset_hold', 'actual_reset', 1)
    board = '\n'.join(function(fragment(PATCH, 'hw/xtensa/esp32.c', kind),
                               'esp32_clk_update').replace('esp32_clk_update', kind + '_board', 1)
                      for kind in ('before', 'after'))
    return '\n'.join((helper, callback, reset)), board


@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'host C compiler and git required')
class XtensaCpuClockRebaseTests(unittest.TestCase):
    def compile_run(self, *, old_board=False, omit_retime=False, zero_input=False):
        actual, board = actual_code()
        source = HARNESS.replace('/* ACTUAL_HELPER_CALLBACK_RESET */', actual).replace('/* ACTUAL_BOARD */', board)
        source = (f'#define OLD_BOARD {int(old_board)}\n#define OMIT_RETIME {int(omit_retime)}\n'
                  f'#define ZERO_INPUT {int(zero_input)}\n' + source)
        with tempfile.TemporaryDirectory(prefix='m5-xtensa-clock-') as directory:
            c, exe = Path(directory) / 'clock.c', Path(directory) / 'clock'
            c.write_text(source)
            build = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
                                    str(c), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            return subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)

    def test_actual_clock_board_callback_reset_and_tick_deadlines(self):
        result = self.compile_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('XTENSA_CLOCK_REBASE_HOST_PASS rate_pairs=16', result.stdout)

    def test_original_board_frequency_only_update_is_a_required_failure(self):
        result = self.compile_run(old_board=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('count_at(&soc.cpu[i],now_ns)==before[i]', result.stderr)

    def test_rebase_without_pending_compare_retime_is_a_required_failure(self):
        result = self.compile_run(omit_retime=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timers[i][0].due==', result.stderr)

    def test_incoming_zero_is_rejected_instead_of_firing_a_fake_tick(self):
        result = self.compile_run(zero_input=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hz > 0', result.stderr)

    def test_patch_forward_reverse_and_no_watchdog_or_irq_state_write(self):
        pinned = {
            'board': function(fragment(PATCH, 'hw/xtensa/esp32.c', 'before'), 'esp32_clk_update'),
            'callback': function(fragment(PATCH, 'hw/xtensa/pic_cpu.c', 'before'), 'xtensa_ccompare_cb'),
            'reset': function(fragment(IRQ_PATCH, 'target/xtensa/cpu.c'), 'xtensa_cpu_reset_hold'),
        }
        self.assertEqual({key: hashlib.sha256(value.encode()).hexdigest() for key, value in pinned.items()}, {
            'board': '2acff13b898cc9b48d1e0e72cbd733342d9c7759d0212566a748dc1dc1d4f0e2',
            'callback': '8f73b1d2f619ffb9f369dbdac0857cae69a0a169617c3c27a4d8c9a43f258945',
            'reset': 'bcd1d57bc1e115655ee912a1fbc4a89088efe5c1ba3c993767c1b3227ed198fe',
        })
        with tempfile.TemporaryDirectory(prefix='m5-clock-patch-') as directory:
            tree, originals = Path(directory), {}
            subprocess.run(['git', 'init', '-q', directory], check=True)
            for name, changes in hunks(PATCH).items():
                rows = []
                for change in changes:
                    while len(rows) < change['start'] - 1:
                        rows.append('\n')
                    self.assertEqual(len(rows), change['start'] - 1)
                    rows.extend(change['before'])
                originals[name] = ''.join(rows)
                path = tree / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(originals[name])
            for args in (['--check'], [], ['--reverse', '--check'], ['--reverse']):
                subprocess.run(['git', 'apply', *args, str(PATCH)], cwd=tree, check=True, capture_output=True)
            self.assertTrue(all((tree / name).read_text() == value for name, value in originals.items()))
        helper = extract_function(fragment(PATCH, 'hw/xtensa/pic_cpu.c'), 'void xtensa_cpu_update_clock_hz(')
        for forbidden in ('INTSET]', 'INTENABLE]', 'pending_irq_level', 'watchdog', 'getenv(', 'qemu_clock_get_ns'):
            self.assertNotIn(forbidden, helper)
        self.assertNotIn('0197-', (ROOT / 'scripts/qemu-wasm-build/sources.lock.json').read_text())
