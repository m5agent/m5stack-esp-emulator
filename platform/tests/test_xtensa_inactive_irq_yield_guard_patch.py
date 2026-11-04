"""Execute actual helper functions and emitted guard IR from committed patches.

Host C/TCG-IR controls only; no QEMU/TCI, guest or performance PASS. The full
pre/post source is bound by the build lock and checked by the fresh builder;
ordinary checkout tests replay the U3 changed hunks without local source caches.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function
from test_xtensa_wallclock_noop_yield_patch import patch_image, function

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-wasm-probe/0030-xtensa-inactive-irq-yield-guard.patch"
ORIGINAL = ROOT / "patches/qemu-wasm-probe/0011-wasm-main805-native-context-compat.patch"
POST_SHA = {
    "accel/tcg/tcg-accel-ops-icount.c": "62f65add2fa1f3962da8ca7693f370922d71c24a97b256b3ec8eb054f17fd1b9",
    "include/sysemu/cpu-timers.h": "6631e9985af402e0658af8e15773a37c5d6365aa5ade8e7831ba423f13414faa",
    "stubs/icount.c": "296574516eebbab1f8d364388d7ea01afcf727220d3718a3ecc3c34a3f024792",
    "target/xtensa/translate.c": "15335266110a8c3dd93e779b47c2465d26b7666ecbb1829717fb0c2dc543cc71",
}


def hunks(path):
    result, name, hunk = {}, None, None
    for line in path.read_text().splitlines(keepends=True):
        if line.startswith("--- a/"):
            name = line[6:].strip()
            result[name] = []
            hunk = None
        elif line.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            hunk = {"start": int(match[1]), "before": [], "after": []}
            result[name].append(hunk)
        elif hunk is not None:
            if line.startswith((" ", "-")):
                hunk["before"].append(line[1:])
            if line.startswith((" ", "+")):
                hunk["after"].append(line[1:])
    return result


def fragment(path, name, kind="after"):
    return "".join("".join(hunk[kind]) for hunk in hunks(path)[name])


def actual_functions():
    icount = fragment(ORIGINAL, "accel/tcg/tcg-accel-ops-icount.c")
    op = fragment(ORIGINAL, "target/xtensa/op_helper.c")
    common = "\n".join(extract_function(icount, signature) for signature in (
        "void icount_note_high_priority_irq(", "void icount_yield_for_high_priority_irq(",
        "bool icount_high_priority_irq_active("))
    common += "\n" + "\n".join(extract_function(op, signature) for signature in (
        "void HELPER(high_priority_irq_yield)(", "void HELPER(high_priority_irq_return)("))
    common += "\n" + extract_function(fragment(PATCH, "accel/tcg/tcg-accel-ops-icount.c"),
                                        "const unsigned *icount_high_priority_irq_state(")
    common += "\n" + extract_function(fragment(PATCH, "stubs/icount.c"),
                                        "const unsigned *icount_high_priority_irq_state(").replace(
                                            "icount_high_priority_irq_state", "stub_irq_state", 1)
    old = patch_image(postimage=True)
    before = [function(old, "translate_" + instruction) for instruction in ("memw", "retw")]
    new_fragment = fragment(PATCH, "target/xtensa/translate.c")
    guard = extract_function(new_fragment, "static void gen_high_priority_irq_yield(")
    after_memw = function(new_fragment, "translate_memw")
    retw_hunk = hunks(PATCH)["target/xtensa/translate.c"][-1]
    old_tail, new_tail = ("".join(retw_hunk[kind]).rstrip() for kind in ("before", "after"))
    if before[1].count(old_tail) != 1:
        raise AssertionError("Retw delta does not match the complete shipped translator")
    after = [after_memw, before[1].replace(old_tail, new_tail)]
    translators = "\n".join(body.replace("translate_" + instruction, prefix + "_" + instruction, 1)
                            for prefix, bodies in (("before", before), ("after", after))
                            for instruction, body in zip(("memw", "retw"), bodies))
    return common, guard, translators


HARNESS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
enum { ICOUNT_DISABLED, ICOUNT_PRECISE, ICOUNT_ADAPTATIVE };
static int use_icount;
#define icount_enabled() use_icount
static unsigned icount_high_priority_irq_cpus;
typedef struct { int cpu_index; } CPUState;
typedef struct { unsigned ps,excm_level; CPUState cpu; } CPUXtensaState;
static unsigned exits[2];
static CPUState *env_cpu(CPUXtensaState *env) { return &env->cpu; }
static int xtensa_get_cintlevel(CPUXtensaState *env) {
    unsigned level=env->ps & 15;
    return (env->ps & 16)&&env->excm_level>level?env->excm_level:level;
}
static void cpu_exit(CPUState *cpu) { exits[cpu->cpu_index]++; }
#define HELPER(name) helper_##name
/* ACTUAL_HELPERS */
typedef int TCGv_i32;
typedef const void *TCGv_ptr;
typedef struct { int id; } TCGLabel;
typedef struct { uint32_t pc; int tb_cf_use_icount; } DisasContext;
typedef struct { int unused; } OpcodeArg;
enum { WINDOW_BASE, WINDOW_START };
static int cpu_SR[]={101,102},cpu_R[]={201},tcg_env=301;
enum { TCG_BAR_SC=16,TCG_MO_ALL=15,TCG_COND_EQ,TCG_COND_NE };
enum { CALL,BARRIER,SHL,ANDC,MOVI,DEPOSIT,RETW,JUMP,LOAD,BRANCH,LABEL };
typedef struct { int kind; intptr_t a[5]; } Event;
typedef struct { Event events[32]; unsigned count; } Program;
static Program ir;
static TCGLabel labels[8];
static int next_temp,label_count;
static void emit(int kind,intptr_t a,intptr_t b,intptr_t c,intptr_t d,intptr_t e) {
    assert(ir.count<32);ir.events[ir.count++]=(Event){kind,{a,b,c,d,e}};
}
static int tcg_temp_new(void) { return ++next_temp; }
static int tcg_temp_new_i32(void) { return tcg_temp_new(); }
static int tcg_constant_i32(uint32_t value) { return (int)value; }
static TCGv_ptr tcg_constant_ptr(const void *value) { return value; }
static TCGLabel *gen_new_label(void) { labels[label_count]=(TCGLabel){label_count};return &labels[label_count++]; }
static void gen_set_label(TCGLabel *label) { emit(LABEL,label->id,0,0,0,0); }
static void tcg_gen_ld_i32(int out,TCGv_ptr pointer,int offset) { emit(LOAD,out,(intptr_t)pointer,offset,0,0); }
static void tcg_gen_brcondi_i32(int condition,int value,int immediate,TCGLabel *label) { emit(BRANCH,condition,value,immediate,label->id,0); }
static void gen_helper_high_priority_irq_yield(int env,int flag) { emit(CALL,env,flag,0,0,0); }
static void tcg_gen_mb(int flags) { emit(BARRIER,flags,0,0,0,0); }
static void tcg_gen_shl_i32(int out,int a,int b) { emit(SHL,out,a,b,0,0); }
static void tcg_gen_andc_i32(int out,int a,int b) { emit(ANDC,out,a,b,0,0); }
static void tcg_gen_movi_i32(int out,int value) { emit(MOVI,out,value,0,0,0); }
static void tcg_gen_deposit_i32(int out,int a,int b,int first,int count) { emit(DEPOSIT,out,a,b,first,count); }
static void gen_helper_retw(int env,int value) { emit(RETW,env,value,0,0,0); }
static void gen_jump(DisasContext *dc,int target) { emit(JUMP,dc->pc,target,0,0,0); }
/* ACTUAL_TRANSLATORS */
typedef void (*Translator)(DisasContext *,const OpcodeArg [],const uint32_t []);
static Program translate(Translator translate,int replay_flag) {
    DisasContext dc={.pc=0x12345678,.tb_cf_use_icount=replay_flag};
    OpcodeArg args[1]={{0}};uint32_t params[1]={0};
    memset(&ir,0,sizeof(ir));next_temp=1000;label_count=0;translate(&dc,args,params);return ir;
}
typedef struct { Program visible;unsigned helpers,exits[2],mask; } Observation;
static Observation execute(Program program,unsigned mask,unsigned ps,unsigned excm_level,unsigned cpu_index) {
    CPUXtensaState env={.ps=ps,.excm_level=excm_level,.cpu={.cpu_index=cpu_index}};
    Observation observation={0};unsigned values[1100]={0};
    icount_high_priority_irq_cpus=mask;exits[0]=exits[1]=0;
    for(unsigned i=0;i<program.count;i++) {
        Event e=program.events[i];
        if(e.kind==LOAD) {
            assert(e.a[2]==0&&e.a[0]<1100);values[e.a[0]]=*(const unsigned *)e.a[1];
        } else if(e.kind==BRANCH) {
            bool equal=values[e.a[1]]==(unsigned)e.a[2];
            if((e.a[0]==TCG_COND_EQ&&equal)||(e.a[0]==TCG_COND_NE&&!equal)) {
                while(++i<program.count&&!(program.events[i].kind==LABEL&&program.events[i].a[0]==e.a[3])){}
                assert(i<program.count);
            }
        } else if(e.kind==CALL) {
            assert(e.a[0]==tcg_env);observation.helpers++;HELPER(high_priority_irq_yield)(&env,e.a[1]);
        } else if(e.kind!=LABEL) {
            observation.visible.events[observation.visible.count++]=e;
        }
    }
    observation.exits[0]=exits[0];observation.exits[1]=exits[1];observation.mask=icount_high_priority_irq_cpus;
    return observation;
}
int main(void) {
    unsigned controls=0,saved_calls=0;
    for(use_icount=0;use_icount<=2;use_icount++) for(int replay=0;replay<2;replay++) {
        Translator old[]={before_memw,before_retw},candidate[]={after_memw,after_retw};
        for(unsigned instruction=0;instruction<2;instruction++) {
            Program before=translate(old[instruction],replay),after=translate(candidate[instruction],replay);
            for(unsigned mask=0;mask<4;mask++) for(unsigned ps=0;ps<32;ps++) for(unsigned excm=0;excm<8;excm++) for(unsigned cpu=0;cpu<2;cpu++) {
                // The SAME emitted program is run with changing masks. A guard
                // constant-folded at translation time fails these cases.
                Observation a=execute(before,mask,ps,excm,cpu),b=execute(after,mask,ps,excm,cpu);
                assert(!memcmp(&a.visible,&b.visible,sizeof(a.visible)));
                assert(!memcmp(a.exits,b.exits,sizeof(a.exits))&&a.mask==b.mask&&b.mask==mask);
                unsigned level=(ps&16)&&excm>(ps&15)?excm:(ps&15);
                unsigned expected=use_icount&&(mask!=0)&&(!instruction?level>=4:true);
                assert(b.exits[cpu]==expected&&b.exits[1-cpu]==0);
                assert(a.helpers==(use_icount?1u:0u));
                assert(b.helpers==(use_icount&&mask?1u:0u));saved_calls+=a.helpers-b.helpers;controls++;
            }
        }
    }
    use_icount=1;icount_high_priority_irq_cpus=0;
    const unsigned *address=icount_high_priority_irq_state();assert(address==&icount_high_priority_irq_cpus);
    icount_note_high_priority_irq(0,true);assert(*address==1);
    icount_note_high_priority_irq(1,true);assert(*address==3);
    CPUXtensaState zero={.ps=4,.cpu={.cpu_index=0}},one={.ps=5,.cpu={.cpu_index=1}};
    HELPER(high_priority_irq_return)(&zero);assert(*address==2);
    HELPER(high_priority_irq_return)(&one);assert(*address==2);
    one.ps=4;HELPER(high_priority_irq_return)(&one);assert(*address==0);
    icount_note_high_priority_irq(1,true);assert(*address==2);
    const unsigned *inactive=stub_irq_state();assert(inactive&&*inactive==0&&stub_irq_state()==inactive);
    icount_note_high_priority_irq(1,false);assert(*address==0); // reset's exact call
    printf("INACTIVE_IRQ_GUARD_HOST_PASS controls=%u skipped_helpers=%u\n",controls,saved_calls);return 0;
}
"""


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "Host compiler and git required")
class XtensaInactiveIrqGuardTests(unittest.TestCase):
    def test_patch_is_exactly_locked_and_original_helpers_are_unchanged(self):
        lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
        row = next(row for row in lock["patches"] if row["path"] == str(PATCH.relative_to(ROOT)))
        self.assertEqual(row["sha256"], hashlib.sha256(PATCH.read_bytes()).hexdigest())
        self.assertEqual({name: lock["patched_files"][name] for name in POST_SHA}, POST_SHA)
        self.assertEqual(set(hunks(PATCH)), set(POST_SHA))
        self.assertNotIn("target/xtensa/op_helper.c", hunks(PATCH))
        self.assertNotIn("target/xtensa/cpu.c", hunks(PATCH))
        self.assertNotIn("target/xtensa/exc_helper.c", hunks(PATCH))
        common, guard, _ = actual_functions()
        self.assertIn("return &icount_high_priority_irq_cpus", common)
        self.assertIn("if (icount_enabled())", guard)
        self.assertNotIn("CF_USE_ICOUNT", guard)
        self.assertNotIn("PS", guard)
        self.assertIn("icount_note_high_priority_irq(cs->cpu_index, false)", fragment(ORIGINAL, "target/xtensa/cpu.c"))
        self.assertIn("icount_note_high_priority_irq(cs->cpu_index, true)", fragment(ORIGINAL, "target/xtensa/exc_helper.c"))

    def test_standard_hunks_forward_and_reverse_without_local_cache(self):
        with tempfile.TemporaryDirectory(prefix="m5-irq-guard-replay-") as directory:
            tree = Path(directory)
            subprocess.run(["git", "init", "-q", str(tree)], check=True, capture_output=True)
            originals = {}
            for name, changes in hunks(PATCH).items():
                rows = []
                for change in changes:
                    while len(rows) < change["start"] - 1:
                        rows.append("\n")
                    self.assertEqual(len(rows), change["start"] - 1)
                    rows += change["before"]
                originals[name] = "".join(rows)
                path = tree / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(originals[name])
            for args in (["--check"], [], ["--reverse", "--check"], ["--reverse"]):
                subprocess.run(["git", "apply", *args, str(PATCH)], cwd=tree, check=True, capture_output=True)
            self.assertTrue(all((tree / name).read_text() == text for name, text in originals.items()))

    def compile_and_run(self, wrong_guard=False):
        helpers, guard, translators = actual_functions()
        if wrong_guard:
            guard = guard.replace("TCG_COND_EQ, active, 0, skip", "TCG_COND_NE, active, 0, skip")
        text = HARNESS.replace("/* ACTUAL_HELPERS */", helpers).replace("/* ACTUAL_TRANSLATORS */", guard + "\n" + translators)
        with tempfile.TemporaryDirectory(prefix="m5-irq-guard-c-") as directory:
            source, binary = Path(directory) / "guard.c", Path(directory) / "guard"
            source.write_text(text)
            subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                            str(source), "-o", str(binary)], check=True, capture_output=True, text=True, timeout=30)
            return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)

    def test_dynamic_mask_sender_replay_return_and_reset(self):
        result = self.compile_and_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INACTIVE_IRQ_GUARD_HOST_PASS controls=24576 skipped_helpers=4096", result.stdout)

    def test_wrong_branch_is_a_required_failing_control(self):
        result = self.compile_and_run(wrong_guard=True)
        self.assertNotEqual(result.returncode, 0, "inverting the runtime mask guard must fail")


if __name__ == "__main__":
    unittest.main()
