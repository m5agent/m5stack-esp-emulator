"""Replay actual native accepted-IRQ, return, reset and yield C/TCG functions.

Host controls bind preimages and retain old-implementation failures. Original
firmware execution and timing evidence are separate from these source controls.
"""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function, file_hunks
from test_xtensa_inactive_irq_yield_guard_patch import fragment, hunks
from test_xtensa_wallclock_noop_yield_patch import function

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-m5stack-peripherals/0194-xtensa-restored-irq-level.patch'

HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define HELPER(name) helper_##name
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define PS_EXCM 16
#define PS_UM 32
#define PS_INTLEVEL 15
#define PS_RING_SHIFT 6
#define PS_WOE 128
#define MEMCTL_IL0EN 0xff
#define INTTYPE_NMI 0
#define LEVEL1_INTERRUPT_CAUSE 4
#define CPU_LOG_INT 1
#define qemu_log_mask(...) ((void)0)
#define qemu_log(...) ((void)0)
enum { PS=0, EPS2=2, EPC1=16, DEPC=24, EXCCAUSE, INTSET, INTENABLE,
 CCOUNT, LITBASE, CPENABLE, VECBASE, IBREAKENABLE, MEMCTL, ATOMCTL, CONFIGID0,CONFIGID1 };
enum { EXC_RESET0, EXC_IRQ,EXC_DOUBLE,EXC_USER,EXC_KERNEL,EXC_DEBUG,
 EXC_WINDOW_OVERFLOW4,EXC_WINDOW_UNDERFLOW4,EXC_WINDOW_OVERFLOW8,
 EXC_WINDOW_UNDERFLOW8,EXC_WINDOW_OVERFLOW12,EXC_WINDOW_UNDERFLOW12 };
enum { XTENSA_OPTION_DFP_COPROCESSOR, XTENSA_OPTION_INTERRUPT,
 XTENSA_OPTION_ATOMCTL };
static int use_icount;
#define icount_enabled() use_icount
static unsigned icount_high_priority_irq_cpus;
static unsigned exits[2], mmu_resets;
typedef struct CPUXtensaState CPUXtensaState;
typedef struct { unsigned cpu_index; int exception_index,halted; CPUXtensaState *env; } CPUState;
typedef struct { int nlevel,nmi_level,ndepc; uint32_t level_mask[8],
 interrupt_vector[8],inttype_mask[1],exception_vector[16],vecbase,memctl_mask,configid[2]; } Config;
struct CPUXtensaState { CPUState cpu; Config *config; uint32_t sregs[64],regs[16],pc;
 int pending_irq_level; uint8_t high_priority_irq_levels; unsigned static_vectors,
 exclusive_addr,runstall,fp_status; };
typedef CPUState Object;
typedef int ResetType;
typedef struct { struct { void (*hold)(Object*,ResetType); } parent_phases; } XtensaCPUClass;
static XtensaCPUClass cpu_class;
#define CPU(obj) (obj)
#define XTENSA_CPU_GET_CLASS(obj) (&cpu_class)
static CPUState *env_cpu(CPUXtensaState *env) { return &env->cpu; }
static CPUXtensaState *cpu_env(CPUState *cpu) { return cpu->env; }
static unsigned xtensa_get_cintlevel(CPUXtensaState *env) {
 unsigned level=env->sregs[PS]&15;
 return (env->sregs[PS]&PS_EXCM)&&level<1?1:level;
}
static void cpu_exit(CPUState *cpu) { exits[cpu->cpu_index]++; }
static uint32_t relocated_vector(CPUXtensaState *env,uint32_t vector) { return vector; }
static void intclear(CPUXtensaState *env,uint32_t bits) { env->sregs[INTSET]&=~bits; }
static void check_interrupts(CPUXtensaState *env) { }
static bool xtensa_option_enabled(Config *config,int option) { return option==XTENSA_OPTION_INTERRUPT; }
static void reset_mmu(CPUXtensaState *env) { mmu_resets++; }
static void set_no_signaling_nans(bool value,unsigned *status) { }
static void xtensa_use_first_nan(CPUXtensaState *env,bool value) { }
/* ACTUAL_COMMON */
/* ACTUAL_FUNCTIONS */
typedef struct { Config *config; } DisasContext;
typedef struct { unsigned imm; } OpcodeArg;
static int cpu_SR[64],tcg_env=99;
enum { CALL,OLD_CALL,AND,MOV,JUMP };
typedef struct { unsigned op; int a,b; uint32_t c; } Event;
static Event ir[8];static unsigned ir_count;
static void emit(unsigned op,int a,int b,uint32_t c) { assert(ir_count<8);ir[ir_count++]=(Event){op,a,b,c}; }
static int tcg_constant_i32(uint32_t value) { return value; }
static void gen_helper_high_priority_irq_return(int env,int level) { assert(env==tcg_env);emit(CALL,level,0,0); }
static void gen_helper_old_return(int env) { assert(env==tcg_env);emit(OLD_CALL,0,0,0); }
static void tcg_gen_andi_i32(int out,int in,uint32_t mask) { emit(AND,out,in,mask); }
static void tcg_gen_mov_i32(int out,int in) { emit(MOV,out,in,0); }
static void gen_jump(DisasContext *dc,int target) { emit(JUMP,target,0,0); }
/* ACTUAL_TRANSLATORS */
static Config config;
static void init(CPUXtensaState *env,unsigned cpu) {
 memset(env,0,sizeof(*env));env->cpu=(CPUState){.cpu_index=cpu,.env=env};
 env->config=&config;env->pc=0x40080000;
}
static void enter(CPUXtensaState *env,unsigned level) {
 env->pending_irq_level=level;env->cpu.exception_index=EXC_IRQ;
 (OLD_ENTRY?before_do_interrupt:after_do_interrupt)(&env->cpu);
}
static void returned(CPUXtensaState *env,unsigned level) {
 DisasContext dc={.config=&config};OpcodeArg args[]={{level}};uint32_t params[]={0};ir_count=0;
 if(level==0)after_rfde(&dc,args,params);
 else if(level==1)(OLD_RETURN?before_rfe:after_rfe)(&dc,args,params);
 else (OLD_RETURN?before_rfi:after_rfi)(&dc,args,params);
 unsigned jumps=0,calls=0;
 for(unsigned i=0;i<ir_count;i++) {
  Event e=ir[i];
  if(e.op==AND)env->sregs[e.a]=env->sregs[e.b]&e.c;
  else if(e.op==MOV)env->sregs[e.a]=env->sregs[e.b];
  else if(e.op==CALL){helper_return_after(env,e.a);calls++;}
  else if(e.op==OLD_CALL){helper_return_before(env);calls++;}
  else if(e.op==JUMP){env->pc=env->sregs[e.a];jumps++;}
 }
 assert(jumps==1);
 if(!OLD_RETURN)assert(calls==(level>1));
}
static unsigned entry_controls(void) {
 /* A stale pending notification with no enabled interrupt must be inert. */
 CPUXtensaState rejected;init(&rejected,0);use_icount=1;icount_high_priority_irq_cpus=2;
 enter(&rejected,4);assert(icount_high_priority_irq_cpus==2&&rejected.high_priority_irq_levels==0);
 unsigned count=0;
 for(use_icount=0;use_icount<3;use_icount++)for(unsigned cpu=0;cpu<2;cpu++)
 for(unsigned level=0;level<=7;level++)for(unsigned ps=0;ps<=31;ps++)
 for(unsigned nlevel=5;nlevel<=7;nlevel+=2)for(unsigned pending=0;pending<2;pending++)
 for(unsigned enabled=0;enabled<2;enabled++) {
  CPUXtensaState env;init(&env,cpu);config.nlevel=nlevel;env.sregs[PS]=ps;
  env.sregs[INTSET]=pending?(1U<<level):0;env.sregs[INTENABLE]=enabled?(1U<<level):0;
  unsigned before=1U<<(1-cpu);icount_high_priority_irq_cpus=before;
  bool accepted=(level>xtensa_get_cintlevel(&env)&&level<=nlevel&&pending&&enabled)||level==7;
  enter(&env,level);
  unsigned expected=accepted&&level>=4?(1U<<level):0;
  assert(env.high_priority_irq_levels==expected);
  assert(icount_high_priority_irq_cpus==(before|((use_icount&&expected)?(1U<<cpu):0)));
  if(accepted&&level>1) {
   assert(env.sregs[EPS2+level-2]==ps&&env.sregs[EPC1+level-1]==0x40080000);
   assert(env.pc==config.interrupt_vector[level]);
  } else if(!accepted)assert(env.sregs[PS]==ps&&env.pc==0x40080000);
  count++;
 }
 return count;
}
static unsigned return_controls(void) {
 unsigned count=0;config.nlevel=7;
 for(use_icount=0;use_icount<3;use_icount++)for(unsigned cpu=0;cpu<2;cpu++)
 for(unsigned slots=0;slots<256;slots+=16)for(unsigned level=0;level<=7;level++)
 for(unsigned pre=0;pre<32;pre++)for(unsigned saved=0;saved<32;saved++) {
  CPUXtensaState env;init(&env,cpu);env.sregs[PS]=pre;env.high_priority_irq_levels=slots;
  for(unsigned i=2;i<=7;i++)env.sregs[EPS2+i-2]=saved;
  for(unsigned i=1;i<=7;i++)env.sregs[EPC1+i-1]=0x40090000+4*i;
  unsigned before=(1U<<(1-cpu))|(slots?(1U<<cpu):0);icount_high_priority_irq_cpus=before;
  returned(&env,level);
  unsigned expected=level>=4?slots&~(1U<<level):slots;
  assert(env.high_priority_irq_levels==expected);
  unsigned mask=use_icount&&level>=4?(before&~(1U<<cpu))|(expected?(1U<<cpu):0):before;
  assert(icount_high_priority_irq_cpus==mask);
  assert(env.sregs[PS]==(level>1?saved:level==1?pre&~PS_EXCM:pre));count++;
 }
 return count;
}
static void nested_and_reset_controls(void) {
 use_icount=1;config.nlevel=7;CPUXtensaState env;init(&env,0);
 env.sregs[INTSET]=env.sregs[INTENABLE]=0xff;icount_high_priority_irq_cpus=2;
 enter(&env,4);assert(env.high_priority_irq_levels==16);env.sregs[PS]=5|PS_EXCM; /* RSIL */
 enter(&env,7);assert(env.high_priority_irq_levels==144);returned(&env,7);
 assert(env.high_priority_irq_levels==16&&icount_high_priority_irq_cpus==3);
 returned(&env,4);assert(env.high_priority_irq_levels==0&&icount_high_priority_irq_cpus==2);
 /* Return to a software PS5 critical section still retires the actual IRQ. */
 env.sregs[PS]=5;env.sregs[INTSET]=0xff;enter(&env,7);returned(&env,7);
 assert(env.sregs[PS]==5&&env.high_priority_irq_levels==0&&icount_high_priority_irq_cpus==2);
 /* Deliberate software lowering permits a repeated level: one hardware slot. */
 env.sregs[PS]=0;env.sregs[INTSET]=0xff;enter(&env,5);env.sregs[PS]=0;enter(&env,5);
 assert(env.high_priority_irq_levels==32);returned(&env,5);assert(env.high_priority_irq_levels==0);
 env.sregs[PS]=0;enter(&env,4);env.sregs[PS]=0;enter(&env,5);
 returned(&env,1);returned(&env,0);assert(env.high_priority_irq_levels==48);
 returned(&env,5);assert(env.high_priority_irq_levels==16);returned(&env,4);assert(!env.high_priority_irq_levels);
 env.sregs[PS]=0;enter(&env,4);enter(&env,5);assert(icount_high_priority_irq_cpus==3);
 unsigned before_resets=mmu_resets;after_reset(&env.cpu,0);
 assert(!env.high_priority_irq_levels&&!env.pending_irq_level&&icount_high_priority_irq_cpus==2);
 assert(mmu_resets==before_resets+1);
}
static void yield_controls(void) {
 for(use_icount=0;use_icount<3;use_icount++)for(unsigned cpu=0;cpu<2;cpu++)
 for(unsigned mask=0;mask<4;mask++)for(unsigned slots=0;slots<256;slots+=16)
 for(unsigned ps=0;ps<32;ps++)for(unsigned only=0;only<2;only++) {
  CPUXtensaState env;init(&env,cpu);env.high_priority_irq_levels=slots;env.sregs[PS]=ps;
  icount_high_priority_irq_cpus=mask;unsigned before=exits[cpu];
  (OLD_YIELD?helper_yield_before:helper_yield_after)(&env,only);
  assert(exits[cpu]==before+(unsigned)(use_icount&&mask&&(!only||slots)));
 }
}
int main(void) {
 for(unsigned i=0;i<64;i++)cpu_SR[i]=i;
 config.nmi_level=7;config.inttype_mask[0]=128;
 for(unsigned i=0;i<8;i++){config.level_mask[i]=1U<<i;config.interrupt_vector[i]=0x40081000+16*i;}
 unsigned entries=entry_controls(),returns=return_controls();
 nested_and_reset_controls();yield_controls();
 printf("IRQ_SLOT_HOST_PASS entry=%u return=%u\n",entries,returns);return 0;
}
'''


def actual_code():
    bodies, translators = [], []
    for kind in ('before', 'after'):
        exc = fragment(PATCH, 'target/xtensa/exc_helper.c', kind)
        for signature, old, new in (
            ('static void handle_interrupt(', 'handle_interrupt', kind + '_handle_interrupt'),
            ('void xtensa_cpu_do_interrupt(', 'xtensa_cpu_do_interrupt', kind + '_do_interrupt'),
        ):
            body = extract_function(exc, signature).replace(old, new, 1)
            if old == 'xtensa_cpu_do_interrupt':
                body = body.replace('handle_interrupt(env)', kind + '_handle_interrupt(env)')
            bodies.append(body)
        op = fragment(PATCH, 'target/xtensa/op_helper.c', kind)
        for name in ('return', 'yield'):
            signature = 'void HELPER(high_priority_irq_' + name + ')('
            bodies.append(extract_function(op, signature).replace(
                'HELPER(high_priority_irq_' + name + ')', 'helper_' + name + '_' + kind, 1))
        source = fragment(PATCH, 'target/xtensa/translate.c', kind)
        for instruction in ('rfe', 'rfi') + (('rfde',) if kind == 'after' else ()):
            body = function(source, 'translate_' + instruction).replace(
                'translate_' + instruction, kind + '_' + instruction, 1)
            if kind == 'before':
                body = body.replace('gen_helper_high_priority_irq_return', 'gen_helper_old_return')
            translators.append(body)
    bodies.append(function(fragment(PATCH, 'target/xtensa/cpu.c'), 'xtensa_cpu_reset_hold').replace(
        'xtensa_cpu_reset_hold', 'after_reset', 1))
    common_source = file_hunks('--- a/accel/tcg/tcg-accel-ops-icount.c')
    common = '\n'.join(extract_function(common_source, signature) for signature in (
        'void icount_note_high_priority_irq(', 'void icount_yield_for_high_priority_irq(',
        'bool icount_high_priority_irq_active('))
    return common, '\n'.join(bodies), '\n'.join(translators)


@unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'host compiler and git required')
class XtensaRestoredIrqLevelTests(unittest.TestCase):
    def test_pinned_before_functions_and_patch_forward_reverse(self):
        before = {
            'helper': extract_function(fragment(PATCH, 'target/xtensa/op_helper.c', 'before'),
                                       'void HELPER(high_priority_irq_return)('),
            'rfe': function(fragment(PATCH, 'target/xtensa/translate.c', 'before'), 'translate_rfe'),
            'rfi': function(fragment(PATCH, 'target/xtensa/translate.c', 'before'), 'translate_rfi'),
        }
        self.assertEqual({key: hashlib.sha256(value.encode()).hexdigest() for key, value in before.items()}, {
            'helper': 'ecc995ee8e7068e7c2700eea2487789c6f67c0d190bea4edf237fcb98bdf90b5',
            'rfe': 'a343bf62295c1e58c01409be792d1c10fd6d037282f3f3e40d7eb8bf778a720c',
            'rfi': '47f3a3d504b6832fd018d154bfee2484a14583d2e0e21220cf571cead25010d6',
        })
        with tempfile.TemporaryDirectory(prefix='m5-irq-slot-patch-') as directory:
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

    def compile_and_run(self, *, old_entry=False, old_return=False, old_yield=False):
        common, bodies, translators = actual_code()
        source = (HARNESS.replace('/* ACTUAL_COMMON */', common).replace(
            '/* ACTUAL_FUNCTIONS */', bodies).replace('/* ACTUAL_TRANSLATORS */', translators))
        source = (f'#define OLD_ENTRY {int(old_entry)}\n#define OLD_RETURN {int(old_return)}\n'
                  f'#define OLD_YIELD {int(old_yield)}\n' + source)
        with tempfile.TemporaryDirectory(prefix='m5-irq-slots-') as directory:
            c, exe = Path(directory) / 'irq.c', Path(directory) / 'irq'
            c.write_text(source)
            built = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined', str(c), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            return subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)

    def test_actual_entry_return_reset_yield_and_translators(self):
        result = self.compile_and_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('IRQ_SLOT_HOST_PASS', result.stdout)

    def test_original_unaccepted_pending_irq_entry_is_a_required_failure(self):
        result = self.compile_and_run(old_entry=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('icount_high_priority_irq_cpus==', result.stderr)

    def test_original_pre_restore_level_four_return_is_a_required_failure(self):
        result = self.compile_and_run(old_return=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, 'high_priority_irq_levels==expected|icount_high_priority_irq_cpus==mask')

    def test_original_ps_proxy_memw_gate_is_a_required_failure(self):
        result = self.compile_and_run(old_yield=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exits[cpu]==', result.stderr)

    def test_native_registration_field_and_helper_contract(self):
        from test_unit_flashlight_cold_pad_patch import bootstrap_stack
        self.assertIn(str(PATCH.relative_to(ROOT)), bootstrap_stack(full=True))
        self.assertNotIn('0194-', (ROOT / 'scripts/qemu-wasm-build/sources.lock.json').read_text())
        self.assertIn('uint8_t high_priority_irq_levels;', fragment(PATCH, 'target/xtensa/cpu.h'))
        self.assertIn('DEF_HELPER_2(high_priority_irq_return, void, env, i32)', fragment(PATCH, 'target/xtensa/helper.h'))
        changed = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                            if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))
        for forbidden in ('CCOMPARE', 'M5_LITE_DIAG', 'getenv(', 'timer_mod', 'DISABLE_WDT', 'qemu_clock_get'):
            self.assertNotIn(forbidden, changed)
