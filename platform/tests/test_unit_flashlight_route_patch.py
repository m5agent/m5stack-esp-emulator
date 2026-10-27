"""Rebuild the historical 0046 AW3641 stack and exercise its route-commit hunk.

The 26-case suite compiles that fixed patch postimage, never a copied model.
Clock/QOM and surrounding pad storage are synthetic. Independent full-controller
source extraction evidence is separate; this is not guest or hardware evidence.
"""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_patch import STUBS

ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "patches/qemu-m5stack-peripherals"
STACK = (
    "0033-unit-runtime-core-and-routing.patch",
    "0038-unit-pwm-route-refresh.patch",
    "0045-unit-flashlight-aw3641.patch",
    "0046-unit-flashlight-route-lifecycle.patch",
)
UNIT = "hw/m5stopwatch/m5_unit_gpio.c"
GPIO = "hw/gpio/esp32_gpio.c"


def parts(name):
    return {part.splitlines()[0].split(" b/", 1)[1]: part
            for part in (PATCH_ROOT / name).read_text().split("diff --git ")[1:]}


def postimages(part):
    return "\n".join("".join(line[1:] + "\n" for line in hunk.splitlines()
                              if line.startswith((" ", "+")) and not line.startswith("+++"))
                     for hunk in re.split(r"^@@[^\n]*\n", part, flags=re.M)[1:])


def function(source, name):
    match = re.search(r"^[^\n;]*\b" + re.escape(name) + r"\([^;]*?\)\n\{", source, re.M)
    if not match:
        raise AssertionError("missing source function: " + name)
    start = match.start()
    end = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end]


def replay(root, current):
    # A nested temporary Git repository prevents include filters from silently
    # using the caller checkout's path prefix. Only tracked patch bytes apply.
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    names = STACK if current else STACK[:-1]
    for name in names:
        subprocess.run(["git", "apply", "--include=" + UNIT, str(PATCH_ROOT / name)],
                       cwd=root, check=True, capture_output=True)
    gpio = root / GPIO
    gpio.parent.mkdir(parents=True)
    gpio.write_text(postimages(parts(STACK[1])[GPIO]))
    if current:
        subprocess.run(["git", "apply", "--include=" + GPIO, str(PATCH_ROOT / STACK[-1])],
                       cwd=root, check=True, capture_output=True)
    return (root / UNIT).read_text(), gpio.read_text()


def program(unit, gpio):
    # QOM/clock are shared with the original digital-model test, with capacity
    # increased for simultaneous pin/layout instances. No model function is
    # borrowed from that test: the current implementation is replayed above.
    shim = STUBS[:STUBS.index("static int pads[49]")]
    shim = shim.replace("QEMUTimer *timers[8]", "QEMUTimer *timers[128]")
    shim = shim.replace("Property properties[64]", "Property properties[1024]")
    shim = shim.replace("for(unsigned i=0;i<property_count;i++)assert(strcmp(name,properties[i].name));", "")
    commit = gpio[gpio.index("            uint32_t previous"):gpio.index("            /*")]
    registry = unit[unit.index("typedef struct AW3641State AW3641State;"):unit.index("/* BEGIN AW3641 NOMINAL DIGITAL MODEL")]
    begin = unit.index("/* BEGIN AW3641 NOMINAL DIGITAL MODEL")
    end = unit.index("/* END AW3641 NOMINAL DIGITAL MODEL */") + len("/* END AW3641 NOMINAL DIGITAL MODEL */")
    model = unit[begin:end]
    query = function(postimages(parts(STACK[0])[GPIO]), "esp32_gpio_matrix_out_signal")
    hook = function(unit, "m5_unit_gpio_initial_complete")
    if "void m5_unit_gpio_route_changed(" in unit:
        hook += "\n" + function(unit, "m5_unit_gpio_route_changed")
    return shim + GPIO_BEFORE + commit + GPIO_AFTER + query + registry + model + hook + CASES


GPIO_BEFORE = r'''
#include <inttypes.h>
#define BIT(x) (1ULL << (x))
typedef uint64_t hwaddr;
static uint32_t g_regs[512];
static bool g_gpio_s3;
static void *g_gpio_device;
static uint64_t g_ext_in,g_open_drain,g_force_mask,g_force_level;
typedef void (*PadFn)(void *,int,int);
static struct { PadFn cb;void *opaque; } g_listeners[54][8];
static uint8_t g_listener_count[54];
static unsigned ledc_route_notifications;
void m5_unit_gpio_route_changed(bool s3,unsigned pin);
static void esp32_ledc_gpio_route_changed(bool s3) { ledc_route_notifications++; }
static uint64_t line(void) {
    uint64_t out=g_regs[0x04/4]|((uint64_t)g_regs[0x10/4]<<32);
    uint64_t enabled=g_regs[0x20/4]|((uint64_t)g_regs[0x2c/4]<<32);
    return (out&enabled)|(g_ext_in&~enabled);
}
static int esp32_gpio_get_line(int pin) { return (line()>>pin)&1; }
static void esp32_gpio_set_input(int pin,int value) {
    if(value)g_ext_in|=1ULL<<pin;else g_ext_in&=~(1ULL<<pin);
}
static void esp32_gpio_add_out_listener(int pin,PadFn cb,void *opaque) {
    assert(g_listener_count[pin]<8);unsigned n=g_listener_count[pin]++;
    g_listeners[pin][n].cb=cb;g_listeners[pin][n].opaque=opaque;
}
static void esp32_gpio_write(void *opaque,hwaddr addr,uint64_t value,unsigned size) {
    uint64_t before=line();
    switch(addr) {
    case 0x08:g_regs[0x04/4]|=value;break;
    case 0x0c:g_regs[0x04/4]&=~value;break;
    case 0x14:g_regs[0x10/4]|=value;break;
    case 0x18:g_regs[0x10/4]&=~value;break;
    case 0x24:g_regs[0x20/4]|=value;break;
    default:
        if(addr<sizeof(g_regs)) {
'''

GPIO_AFTER = r'''
        }
    }
    uint64_t after=line(),diff=before^after;
    for(unsigned pin=0;pin<54;pin++)if(diff&(1ULL<<pin))
        for(unsigned n=0;n<g_listener_count[pin];n++)
            g_listeners[pin][n].cb(g_listeners[pin][n].opaque,pin,(after>>pin)&1);
}
'''

CASES = r'''
/* Tests are independent of the candidate helper: all route changes enter the
 * actual replayed GPIO route-commit hunk; pad storage outside that hunk is a shim. */
static M5Unit fixture_units[8];
static GPIOUnit fixture_links[8];
static AW3641State *fixture_states[8];
static unsigned fixture_count, checks, failures, cases,case_begin_checks,case_begin_failures;
static const char *case_name;
static void escaped(const char *text) {
    putchar('"');for(const unsigned char *p=(const unsigned char *)text;*p;p++) {
        if(*p=='"'||*p=='\\')putchar('\\');
        if(*p<32)printf("\\u%04x",*p);else putchar(*p);
    }putchar('"');
}
static bool get_state_bool(AW3641State *s,const char *name) {
    Visitor v={0}; aw3641_bool_get(NULL,&v,name,s,NULL); return v.boolean;
}
static void check(bool ok,const char *expr,int line,AW3641State *s) {
    checks++; if(ok)return; failures++;
    printf("{\"event\":\"FAIL\",\"case\":\"%s\",\"line\":%d,\"assertion\":",case_name,line);escaped(expr);
    printf(",\"known_internal\":%d,\"active_internal\":%d,\"known_getter\":%d,\"phase\":%d,\"edges\":%" PRIu64 ",\"rising_edges\":%" PRIu64 ",\"decoded\":%" PRIu64 ",\"low_since_ns\":%" PRId64 ",\"reset_at_ns\":%" PRId64 ",\"settle_at_ns\":%" PRId64 ",\"timeout_at_ns\":%" PRId64 "}\n",
           s->known,s->active,get_state_bool(s,"output-known"),s->phase,
           s->edge_count,s->rising_edges,s->decoded_programs,s->low_since_ns,s->reset_at_ns,s->settle_at_ns,s->timeout_at_ns);
}
#define CHECK(s,x) check(!!(x),#x,__LINE__,s)
static void mmio(hwaddr address,uint32_t value) { esp32_gpio_write(NULL,address,value,4); }
static void route(bool s3,unsigned pin,uint32_t signal) {
    bool previous_layout=g_gpio_s3; g_gpio_s3=s3;
    mmio((s3?0x554:0x530)+pin*4,signal); g_gpio_s3=previous_layout;
}
static void pad_at(unsigned pin,bool value) {
    mmio(pin<32?(value?0x08:0x0c):(value?0x14:0x18),1u<<(pin&31));
}
static void pad(AW3641State *s,bool value) { pad_at(s->unit->yellow,value); }
static void fresh(const char *name) {
    if(case_name) printf("{\"event\":\"CASE_RESULT\",\"case\":\"%s\",\"checks\":%u,\"failures\":%u}\n",case_name,checks-case_begin_checks,failures-case_begin_failures);
    for(unsigned i=0;i<timer_count;i++)free(timers[i]);
    for(unsigned i=0;i<fixture_count;i++)free(fixture_states[i]);
    fixture_count=timer_count=property_count=0; gpio_units=NULL; now_ns=0;
    memset(g_regs,0,sizeof(g_regs)); memset(g_listeners,0,sizeof(g_listeners));
    memset(g_listener_count,0,sizeof(g_listener_count));
    memset(fixture_units,0,sizeof(fixture_units)); memset(fixture_links,0,sizeof(fixture_links));
    g_ext_in=g_open_drain=g_force_mask=g_force_level=0; g_gpio_device=NULL;
    ledc_route_notifications=0;g_gpio_s3=true;case_name=name;cases++;
    case_begin_checks=checks;case_begin_failures=failures;
    mmio(0x24,(1u<<2)|(1u<<3));
    route(true,2,256);route(true,3,256);route(false,2,256);route(false,3,256);
}
static AW3641State *create(bool flash,bool s3,unsigned pin) {
    assert(fixture_count<ARRAY_SIZE(fixture_states));unsigned i=fixture_count++;
    M5Unit *u=&fixture_units[i];*u=(M5Unit){.white=1,.yellow=pin,.s3=s3};
    AW3641State *s=aw3641_new(u);fixture_states[i]=s;
    GPIOUnit *g=&fixture_links[i];g->unit=u;g->flashlight=s;g->s3=s3;g->next=gpio_units;gpio_units=g;
    Visitor v={.input=true,.boolean=flash};Error *e=NULL;aw3641_mode_set(NULL,&v,"flash-mode",s,&e);assert(!e);
    m5_unit_gpio_initial_complete(u);assert(s->mode_frozen);
    return s;
}
static AW3641State *active(bool flash) {
    AW3641State *s=create(flash,true,2);advance(now_ns+600000);
    CHECK(s,s->phase==AW3641_READY_LOW&&s->known&&!s->active);
    pad(s,true);advance(now_ns+500000);
    CHECK(s,s->known&&s->active&&s->qualified&&get_state_bool(s,"output-known"));
    return s;
}
static void no_output(AW3641State *s) {
    CHECK(s,!s->known&&!s->active&&!s->qualified&&!s->ready);
    CHECK(s,!get_state_bool(s,"output-known")&&!get_state_bool(s,"active")&&!get_state_bool(s,"waveform-qualified"));
}
static void no_timers(AW3641State *s) {
    CHECK(s,!s->reset_timer->pending&&!s->settle_timer->pending&&!s->timeout_timer->pending);
    CHECK(s,s->reset_at_ns==-1&&s->settle_at_ns==-1&&s->timeout_at_ns==-1);
}
static void recover(AW3641State *s) {
    pad(s,true);pad(s,false);advance(now_ns+500000);no_output(s);
    advance(now_ns+1);CHECK(s,s->known&&!s->active&&s->ready&&s->qualified);
    pad(s,true);advance(now_ns+500000);CHECK(s,s->known&&s->active&&s->qualified);
}
static void roundtrip(bool flash,unsigned unsupported,const char *name) {
    fresh(name);AW3641State *s=active(flash);
    uint64_t edges=s->edge_count,rises=s->rising_edges,decoded=s->decoded_programs,epoch=s->epoch;
    int64_t original_timeout=s->timeout_at_ns;
    route(true,2,unsupported);
    /* Internal assertions happen before any read of a QOM getter. */
    CHECK(s,!s->known&&!s->active&&!s->qualified&&!s->ready);
    CHECK(s,s->epoch>epoch);no_timers(s);
    CHECK(s,s->low_since_ns==-1&&s->first_rise_ns==-1);
    route(true,2,256);no_output(s);no_timers(s);
    printf("{\"event\":\"ROUNDTRIP_OBSERVED\",\"case\":\"%s\",\"known_internal\":%d,\"active_internal\":%d,\"known_getter\":%d,\"edges_before\":%" PRIu64 ",\"edges_after\":%" PRIu64 ",\"decoded_before\":%" PRIu64 ",\"decoded_after\":%" PRIu64 ",\"now_ns\":%" PRId64 ",\"original_timeout_ns\":%" PRId64 "}\n",case_name,s->known,s->active,get_state_bool(s,"output-known"),edges,s->edge_count,decoded,s->decoded_programs,now_ns,original_timeout);
    CHECK(s,s->edge_count==edges&&s->rising_edges==rises&&s->decoded_programs==decoded);
    CHECK(s,!flash||now_ns<original_timeout);
    advance(now_ns+2000000000LL);no_output(s);
    CHECK(s,s->edge_count==edges&&s->rising_edges==rises&&s->decoded_programs==decoded);
    recover(s);
}
static void phase_loss(unsigned phase,const char *name) {
    fresh(name);AW3641State *s=create(true,true,2);
    if(phase>=1)advance(now_ns+600000);
    if(phase>=2)pad(s,true);
    if(phase>=3)advance(now_ns+500000);
    if(phase==4)pad(s,false);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs;
    route(true,2,73);no_timers(s);route(true,2,256);no_output(s);
    advance(now_ns+2000000000LL);no_output(s);
    CHECK(s,s->edge_count==edges&&s->decoded_programs==decoded);
    recover(s);
}
static void stale_low(unsigned kind,const char *name) {
    fresh(name);AW3641State *s=active(true);uint64_t resets=s->reset_events;
    if(kind==0) { pad(s,false);advance(now_ns+200000);route(true,2,73); }
    else { route(true,2,73);pad(s,false); }
    if(kind==1) { advance(now_ns+200000);route(true,2,256);advance(now_ns+600000); }
    else {
        /* Delayed dispatch is deliberate: edge shortcut must not borrow the
         * invalid interval even when reset callback was never delivered. */
        now_ns+=600000;route(true,2,256);pad(s,true);advance(now_ns+500000);
    }
    no_output(s);CHECK(s,s->reset_events==resets);
    if(!s->en) { pad(s,true);advance(now_ns+500000);no_output(s); }
    recover(s);
}
static void stale_callbacks(unsigned kind,const char *name) {
    fresh(name);AW3641State *s=create(true,true,2);
    if(kind>0){advance(now_ns+600000);pad(s,true);}
    if(kind>1)advance(now_ns+500000);
    route(true,2,73);route(true,2,256);uint64_t decoded=s->decoded_programs,reset=s->reset_events,timeout=s->timeout_events;
    now_ns+=2000000000LL;
    /* Invoke real saved callback entrypoints despite timer_del, then invoke
     * the scheduler. They must not revive state or increment decoder counts. */
    aw3641_reset_expired(s);aw3641_settle_expired(s);aw3641_timeout_expired(s);
    advance(now_ns);no_output(s);no_timers(s);
    CHECK(s,s->decoded_programs==decoded&&s->reset_events==reset&&s->timeout_events==timeout);
}
static void repeated_and_ignored(void) {
    fresh("repeated-and-ignored-register-writes");AW3641State *s=active(false);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs,epoch=s->epoch;
    unsigned notices=ledc_route_notifications;
    route(true,2,256);route(true,2,256|BIT(10));
    CHECK(s,s->known&&s->active&&s->epoch==epoch);
    CHECK(s,ledc_route_notifications==notices);
    route(true,2,73);uint64_t unqualified=s->unqualified_programs;
    CHECK(s,unqualified==1);route(true,2,73);route(true,2,81);route(true,2,256|BIT(9));
    no_output(s);CHECK(s,s->unqualified_programs==unqualified);
    route(true,2,256);no_output(s);CHECK(s,s->edge_count==edges&&s->decoded_programs==decoded);
}
static void instance_isolation(void) {
    fresh("other-pin-and-layout-isolation");
    AW3641State *s=create(false,true,2),*other=create(false,true,3),*classic=create(false,false,2);
    advance(now_ns+600000);pad(s,true);pad(other,true);advance(now_ns+500000);
    CHECK(s,s->known&&s->active);CHECK(other,other->known&&other->active);CHECK(classic,classic->known&&classic->active);
    uint64_t s_edges=s->edge_count,other_edges=other->edge_count,classic_edges=classic->edge_count;
    route(false,2,73);CHECK(s,s->known&&s->active);CHECK(other,other->known&&other->active);no_output(classic);
    route(true,3,73);CHECK(s,s->known&&s->active);no_output(other);no_output(classic);
    route(true,2,73);no_output(s);
    CHECK(s,s->edge_count==s_edges&&other->edge_count==other_edges&&classic->edge_count==classic_edges);
}
static void short_low(void) {
    fresh("new-supported-short-low-does-not-requalify");AW3641State *s=active(true);
    route(true,2,73);route(true,2,256);pad(s,false);advance(now_ns+500000);pad(s,true);
    advance(now_ns+500000);no_output(s);recover(s);
}
static void unsupported_constructor(bool delayed,const char *name) {
    fresh(name);route(true,2,73);AW3641State *s=create(true,true,2);
    uint64_t edges=s->edge_count,decoded=s->decoded_programs;
    if(delayed) now_ns+=600000; else advance(now_ns+200000);
    route(true,2,256);no_output(s);no_timers(s);
    if(delayed) { pad(s,true);advance(now_ns+500000); }
    else advance(now_ns+600000);
    no_output(s);CHECK(s,s->decoded_programs==decoded);
    CHECK(s,s->edge_count==edges+(delayed?1:0));recover(s);
}
int main(void) {
    const unsigned unsupported[]={73,81,0,511,256|BIT(9)};
    const char *torch_names[]={"torch-ledc-roundtrip-before-any-getter","torch-rmt-roundtrip","torch-zero-roundtrip","torch-signal511-roundtrip","torch-out-inv-roundtrip"};
    const char *flash_names[]={"flash-ledc-roundtrip-before-deadline","flash-rmt-roundtrip-before-deadline","flash-zero-roundtrip-before-deadline","flash-signal511-roundtrip-before-deadline","flash-out-inv-roundtrip-before-deadline"};
    for(unsigned i=0;i<ARRAY_SIZE(unsupported);i++){roundtrip(false,unsupported[i],torch_names[i]);roundtrip(true,unsupported[i],flash_names[i]);}
    phase_loss(0,"reset-pending-loss");phase_loss(1,"ready-low-loss");phase_loss(2,"programming-settle-pending-loss");phase_loss(3,"flash-timeout-pending-loss");phase_loss(4,"falling-reset-pending-loss");
    stale_low(0,"pre-loss-low-cannot-cross-unsupported-with-delayed-timer");
    stale_low(1,"unsupported-fall-return-low-before-timer");
    stale_low(2,"unsupported-fall-return-rise-delayed-timer");
    stale_callbacks(0,"cancel-reset-and-stale-callback");stale_callbacks(1,"cancel-settle-and-stale-callback");stale_callbacks(2,"cancel-timeout-and-stale-callback");
    repeated_and_ignored();instance_isolation();short_low();
    unsupported_constructor(false,"unsupported-constructor-return-low-before-deadline");
    unsupported_constructor(true,"unsupported-constructor-return-rise-after-delayed-deadline");
    printf("{\"event\":\"CASE_RESULT\",\"case\":\"%s\",\"checks\":%u,\"failures\":%u}\n",case_name,checks-case_begin_checks,failures-case_begin_failures);
    printf("{\"event\":\"SUMMARY\",\"cases\":%u,\"checks\":%u,\"failures\":%u,\"result\":\"%s\",\"api_contacted\":false,\"guest_execution\":\"NOT RUN\",\"hardware_execution\":\"NOT RUN\"}\n",cases,checks,failures,failures?"FAIL":"PASS");
    return failures?1:0;
}
'''


class UnitFlashlightRoutePatchTests(unittest.TestCase):
    def test_patch_scope_and_bootstrap_order(self):
        self.assertEqual(set(parts(STACK[-1])), {
            GPIO, UNIT, "hw/m5stopwatch/m5_unit_runtime.h"})
        tree = ast.parse((ROOT / "scripts/bootstrap-unit-runtime.py").read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "PATCHES"
                                  for target in node.targets))
        patches = ast.literal_eval(assignment.value)
        position = patches.index("patches/qemu-m5stack-peripherals/" + STACK[-1])
        self.assertEqual(patches[position - 1:position + 1], tuple(
            "patches/qemu-m5stack-peripherals/" + name for name in STACK[-2:]))
        # Keep the 0046 negative control fixed. The full successor stack and
        # its changed pad semantics are covered by the cold-pad patch suite.
        touching = [Path(name).name for name in patches
                    if f"diff --git a/{UNIT} b/{UNIT}\n" in (ROOT / name).read_text()]
        self.assertEqual(touching, [*STACK, "0047-unit-flashlight-cold-pad-observation.patch"])

    @unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler or Git unavailable")
    def test_current_patch_routes_lifecycle_and_old_postimage_is_negative_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for current, expected_failures in ((False, 152), (True, 0)):
                with self.subTest(current=current):
                    folder = root / ("current" if current else "old")
                    folder.mkdir()
                    unit, gpio = replay(folder, current)
                    source = folder / "route.c"
                    source.write_text(program(unit, gpio))
                    binary = folder / "route"
                    build = subprocess.run([
                        shutil.which("cc"), "-std=c11", "-O0", "-Wall", "-Wextra",
                        "-Werror", "-Wno-unused-function", "-Wno-unused-parameter",
                        str(source), "-o", str(binary)], capture_output=True, text=True)
                    self.assertEqual(build.returncode, 0, build.stderr)
                    result = subprocess.run([str(binary)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1 if expected_failures else 0, result.stdout + result.stderr)
                    events = [json.loads(line) for line in result.stdout.splitlines()]
                    summary = events[-1]
                    self.assertEqual(summary["cases"], 26)
                    self.assertEqual(summary["checks"], 357)
                    self.assertEqual(summary["failures"], expected_failures)
                    self.assertFalse(summary["api_contacted"])
                    self.assertEqual(summary["guest_execution"], "NOT RUN")
                    self.assertEqual(summary["hardware_execution"], "NOT RUN")
                    self.assertEqual(len([item for item in events if item["event"] == "CASE_RESULT"]), 26)
                    self.assertEqual(sum(item["failures"] for item in events
                                         if item["event"] == "CASE_RESULT"), expected_failures)


if __name__ == "__main__":
    unittest.main()
