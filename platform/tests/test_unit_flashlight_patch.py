"""Compile actual patch C; controller logic evidence, never a guest/hardware PASS."""
import ast
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0045-unit-flashlight-aw3641.patch"
OFFICIAL = ROOT / "platform/tests/fixtures/uiflow-flash_light-2.5.3.py"
OFFICIAL_SHA = "10546386ee156034c268404e96f4d086b88c52254da1fcd2aa19130ce2f6629f"

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define QEMU_CLOCK_VIRTUAL 1
#define g_new0(type,n) ((type *)calloc((n),sizeof(type)))
#define g_free free
static char *g_strdup(const char *v) { size_t n=strlen(v)+1; char *p=malloc(n); memcpy(p,v,n); return p; }
typedef struct Object { int unused; } Object;
#define OBJECT(o) ((Object *)(o))
typedef struct M5Unit { int white,yellow; bool s3; uint64_t input_events,output_transitions; } M5Unit;
typedef struct Error { const char *message; } Error;
static Error last_error;
static void error_setg(Error **e,const char *message,...) { if(e) { last_error.message=message; *e=&last_error; } }
typedef struct QObject { unsigned kind; } QObject;
typedef struct QInt { QObject base; int64_t value; } QInt;
typedef struct QList { QObject base; size_t count; QObject *items[1024]; } QList;
#define QOBJECT(o) ((QObject *)(o))
static QList *qlist_new(void) { QList *q=calloc(1,sizeof(*q)); q->base.kind=1; return q; }
static void qlist_append_obj(QList *q,QObject *value) { assert(q->count<ARRAY_SIZE(q->items)); q->items[q->count++]=value; }
static void qlist_append_int(QList *q,int64_t value) { QInt *n=calloc(1,sizeof(*n));n->base.kind=2;n->value=value;qlist_append_obj(q,QOBJECT(n)); }
static void qobject_unref(QObject *q) { if(q->kind==1) { QList *a=(QList *)q;for(size_t i=0;i<a->count;i++)qobject_unref(a->items[i]); }free(q); }
typedef struct Visitor { bool input,boolean; uint64_t u64; int64_t i64; size_t pairs; char text[1024]; } Visitor;
static bool visit_type_bool(Visitor *v,const char *n,bool *p,Error **e) { if(v->input)*p=v->boolean;else v->boolean=*p;return true; }
static bool visit_type_uint64(Visitor *v,const char *n,uint64_t *p,Error **e) { v->u64=*p;return true; }
static bool visit_type_int64(Visitor *v,const char *n,int64_t *p,Error **e) { v->i64=*p;return true; }
static bool visit_type_str(Visitor *v,const char *n,char **p,Error **e) { snprintf(v->text,sizeof(v->text),"%s",*p);return true; }
static bool visit_type_any(Visitor *v,const char *n,QObject **p,Error **e) {
 QList *a=(QList *)*p;v->pairs=a->count;
 for(size_t i=0;i<a->count;i++) { QList *pair=(QList *)a->items[i]; assert(pair->count==2);assert(((QInt *)pair->items[1])->value==0||((QInt *)pair->items[1])->value==1); }
 return true;
}
typedef void (*PropertyFn)(Object *,Visitor *,const char *,void *,Error **);
typedef struct Property { const char *name,*type;PropertyFn get,set;void *opaque; } Property;
static Property properties[64];static unsigned property_count;
static void object_property_add(Object *o,const char *name,const char *type,PropertyFn get,PropertyFn set,void *release,void *opaque) {
 assert(property_count<ARRAY_SIZE(properties));for(unsigned i=0;i<property_count;i++)assert(strcmp(name,properties[i].name));
 properties[property_count++]=(Property){name,type,get,set,opaque};
}
typedef struct QEMUTimer { bool pending;int64_t at;void (*cb)(void *);void *opaque; } QEMUTimer;
static QEMUTimer *timers[8];static unsigned timer_count;static int64_t now_ns;
static int64_t qemu_clock_get_ns(int clock) { assert(clock==QEMU_CLOCK_VIRTUAL);return now_ns; }
static QEMUTimer *timer_new_ns(int clock,void (*cb)(void *),void *opaque) { assert(clock==QEMU_CLOCK_VIRTUAL);assert(timer_count<ARRAY_SIZE(timers));QEMUTimer *t=calloc(1,sizeof(*t));t->cb=cb;t->opaque=opaque;timers[timer_count++]=t;return t; }
static void timer_mod_ns(QEMUTimer *t,int64_t at) { assert(at>=now_ns);t->at=at;t->pending=true; }
static void timer_del(QEMUTimer *t) { t->pending=false; }
static void advance(int64_t target)
{
    assert(target >= now_ns);
    unsigned count = 0;
    for (;;) {
        QEMUTimer *next = NULL;
        for (unsigned i = 0; i < timer_count; i++) {
            if (timers[i]->pending && timers[i]->at <= target &&
                (!next || timers[i]->at < next->at)) {
                next = timers[i];
            }
        }
        if (!next) {
            break;
        }
        assert(++count < 10000);
        now_ns = next->at;
        next->pending = false;
        next->cb(next->opaque);
    }
    now_ns = target;
}
static int pads[49],routes[49];static bool driven[49];
typedef void (*PadFn)(void *,int,int);
static PadFn pad_listener;static void *pad_opaque;static int listener_pin;
static int esp32_gpio_get_line(int pin) { assert(pin>=0&&pin<49);return pads[pin]; }
static int esp32_gpio_matrix_out_signal(int pin,bool s3) { return routes[pin]; }
static void esp32_gpio_set_input(int pin,int value) { if(!driven[pin])pads[pin]=!!value; }
static void esp32_gpio_add_out_listener(int pin,PadFn cb,void *opaque) { assert(!pad_listener);pad_listener=cb;pad_opaque=opaque;listener_pin=pin; }
typedef struct AW3641State AW3641State;
'''

TESTS = r'''
typedef struct GPIOUnit { M5Unit *unit;AW3641State *flashlight;struct GPIOUnit *next; } GPIOUnit;
static GPIOUnit *gpio_units;
/* FREEZE_HOOK */
static Property *property(const char *name) { for(unsigned i=0;i<property_count;i++)if(!strcmp(properties[i].name,name))return &properties[i];abort(); }
static bool get_bool(const char *name) { Property *p=property(name);Visitor v={0};p->get(NULL,&v,name,p->opaque,NULL);return v.boolean; }
static bool set_mode(bool value) { Property *p=property("flash-mode");Visitor v={.input=true,.boolean=value};Error *e=NULL;p->set(NULL,&v,p->name,p->opaque,&e);return e==NULL; }
static AW3641State *create(M5Unit *u,bool flash,bool frozen,bool high) {
 now_ns=0;property_count=timer_count=0;pad_listener=NULL;pad_opaque=NULL;gpio_units=NULL;
 memset(pads,0,sizeof(pads));memset(driven,0,sizeof(driven));for(unsigned i=0;i<49;i++)routes[i]=256;
 *u=(M5Unit){.white=1,.yellow=2,.s3=true};pads[2]=high;driven[2]=high;
 AW3641State *s=aw3641_new(u);assert(pad_listener==aw3641_pad_changed&&listener_pin==2);assert(set_mode(flash));
 if(frozen) { GPIOUnit g={.unit=u,.flashlight=s};gpio_units=&g;m5_unit_gpio_initial_complete(u);gpio_units=NULL;assert(s->mode_frozen); }
 return s;
}
static void destroy(AW3641State *s) { for(unsigned i=0;i<timer_count;i++){timer_del(timers[i]);free(timers[i]);}timer_count=0;free(s);pad_listener=NULL;pad_opaque=NULL; }
static void pad(int value) { value=!!value;driven[listener_pin]=true;if(pads[listener_pin]!=value){pads[listener_pin]=value;pad_listener(pad_opaque,listener_pin,value);} }
static void reset_low(AW3641State *s) { pad(0);advance(now_ns+600000);assert(s->phase==AW3641_READY_LOW&&get_bool("output-known")&&!get_bool("active")); }
static void train(AW3641State *s,unsigned n,int64_t hi,int64_t lo) {
 assert(!s->en);for(unsigned i=0;i<n;i++){pad(1);if(i+1<n){advance(now_ns+hi);pad(0);advance(now_ns+lo);}}
}
static void stable(AW3641State *s) { advance(now_ns+500000); }
static void table(void) {
 for(unsigned n=1;n<=16;n++) { M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,n,2000,2000);int64_t first=s->first_rise_ns,last=s->last_edge_ns;
  advance(last+499999);assert(!get_bool("output-known"));advance(last+500000);assert(s->phase==AW3641_FLASH_ACTIVE&&get_bool("active")&&get_bool("output-known"));
  assert(s->pulses==n&&s->last_program==n&&s->flash_level_pct==100-((n-1)%8)*10&&s->timeout_ms==(n<=8?220:1300));assert(s->timeout_at_ns==first+(int64_t)s->timeout_ms*1000000);
  advance(s->timeout_at_ns-1);assert(get_bool("active"));advance(now_ns+1);assert(!get_bool("active")&&get_bool("output-known")&&s->phase==AW3641_FLASH_EXPIRED&&s->timeout_events==1);advance(now_ns+5000000);assert(s->timeout_events==1);pad(1);assert(!get_bool("active"));destroy(s);
 }
}
static void recommended_boundaries(void) {
 int64_t widths[]={750,10000};for(unsigned j=0;j<2;j++){M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,16,widths[j],widths[1-j]);stable(s);assert(get_bool("active")&&s->last_program==16&&s->flash_level_pct==30);destroy(s);}
}
static void outside_window(void) {
 int64_t widths[]={749,10001};for(unsigned j=0;j<2;j++)for(unsigned high=0;high<2;high++){M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,2,high?widths[j]:2000,high?2000:widths[j]);stable(s);assert(!get_bool("output-known")&&s->phase==AW3641_UNQUALIFIED&&s->unqualified_programs==1);reset_low(s);train(s,1,2000,2000);stable(s);assert(get_bool("active"));destroy(s);}
}
static void reset_boundary(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);advance(499999);assert(!get_bool("output-known"));advance(500000);assert(!get_bool("output-known"));advance(500001);assert(get_bool("output-known")&&s->reset_events==1);advance(600000);assert(s->reset_events==1);pad(1);assert(s->reset_events==1);stable(s);assert(s->reset_events==1);destroy(s);
}
static void duplicate_and_wrong_pin(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);pad(1);uint64_t edges=s->edge_count;aw3641_pad_changed(s,2,1);aw3641_pad_changed(s,1,0);pad(1);assert(s->edge_count==edges&&s->pulses==1);stable(s);assert(get_bool("active"));destroy(s);
}
static void torch(void) {
 M5Unit u;AW3641State *s=create(&u,false,true,false);reset_low(s);pad(1);stable(s);assert(get_bool("active")&&s->phase==AW3641_TORCH_ACTIVE&&s->timeout_ms==0&&s->flash_level_pct==0&&s->last_program==0&&!s->timeout_timer->pending);advance(now_ns+3000000000LL);assert(get_bool("active")&&s->timeout_events==0);reset_low(s);train(s,2,2000,2000);stable(s);assert(!get_bool("output-known")&&!strcmp(s->reason,"torch-modulation-not-qualified"));destroy(s);
}
static void frozen_mode(void) {
 M5Unit u;AW3641State *s=create(&u,true,false,false);assert(!get_bool("mode-frozen"));assert(set_mode(false)&&!s->flash_mode);GPIOUnit g={.unit=&u,.flashlight=s};gpio_units=&g;M5Unit other={0};m5_unit_gpio_initial_complete(&other);assert(!s->mode_frozen);m5_unit_gpio_initial_complete(&u);assert(s->mode_frozen);gpio_units=NULL;uint64_t events=u.input_events;assert(!set_mode(true)&&!s->flash_mode&&u.input_events==events);reset_low(s);pad(1);stable(s);assert(!set_mode(true)&&!s->flash_mode&&u.input_events==events);destroy(s);
}
static void initial_high(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,true);assert(s->en&&!get_bool("output-known"));advance(1000000);assert(!get_bool("output-known"));reset_low(s);train(s,3,2000,2000);stable(s);assert(s->flash_level_pct==80&&get_bool("active"));destroy(s);
}
static void too_many(void) {
 for(unsigned n=17;n<=18;n++){M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,n,2000,2000);stable(s);assert(!get_bool("output-known")&&s->decoded_programs==0&&s->unqualified_programs==1&&s->pulses==17&&s->pulse_count_capped==(n>17));assert(!strcmp(s->reason,"pulse-count-outside-documentation"));destroy(s);}
}
static void trace_bound(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);for(unsigned i=0;i<400;i++){pad(!(i&1));advance(now_ns+2000);}assert(s->edge_count==400&&s->rising_edges==200&&s->trace_count==256&&s->trace_overflows==144);assert(s->trace[s->trace_head].at_ns==600000+144*2000);Visitor v={0};aw3641_trace_get(NULL,&v,"edge-trace-ns",s,NULL);assert(v.pairs==256);destroy(s);
}
static void missing_pad_callback(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,1,2000,2000);stable(s);assert(get_bool("active"));AW3641Phase before=s->phase;pads[2]=0;assert(!get_bool("output-known")&&!get_bool("active")&&!get_bool("pad-synchronized")&&!get_bool("en-level"));assert(s->phase==before&&s->known);assert(!get_bool("reset-observation-supported"));advance(s->timeout_at_ns);assert(s->phase==AW3641_UNQUALIFIED&&!strcmp(s->reason,"pad-callback-not-synchronized"));destroy(s);
}
static void route_guard(void) {
 int bad[]={73,-1};for(unsigned i=0;i<2;i++){M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,1,2000,2000);stable(s);assert(get_bool("active"));routes[2]=bad[i];assert(!get_bool("gpio-route-supported")&&!get_bool("active")&&!get_bool("output-known"));advance(s->timeout_at_ns);assert(s->phase==AW3641_UNQUALIFIED);routes[2]=256;reset_low(s);train(s,1,2000,2000);stable(s);assert(get_bool("active"));destroy(s);}
}
static void short_low(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,1,2000,2000);stable(s);pad(0);advance(now_ns+100000);pad(1);stable(s);assert(s->phase==AW3641_UNQUALIFIED&&!get_bool("output-known"));reset_low(s);train(s,2,2000,2000);stable(s);assert(s->flash_level_pct==90&&get_bool("active"));destroy(s);
}
static void old_timer(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,1,2000,2000);stable(s);int64_t old=s->timeout_at_ns;advance(now_ns+10000000);reset_low(s);train(s,9,2000,2000);stable(s);int64_t current=s->timeout_at_ns;assert(current>old);advance(old);assert(get_bool("active")&&s->timeout_events==0);advance(current);assert(!get_bool("active")&&s->timeout_events==1);destroy(s);
}
static void original_driver_negative(void) {
 unsigned wrong=0;for(unsigned requested=1;requested<=8;requested++){M5Unit u;AW3641State *s=create(&u,true,true,false);reset_low(s);train(s,requested*2,2000,2000);stable(s);assert(get_bool("active"));bool match=s->timeout_ms==1300&&s->flash_level_pct==110-requested*10;if(!match)wrong++;assert(match==(requested==8));destroy(s);}assert(wrong==7);
}
static void zero_and_readonly(void) {
 M5Unit u;AW3641State *s=create(&u,true,true,false);advance(1000000000);assert(!get_bool("active")&&get_bool("output-known")&&s->decoded_programs==0&&s->edge_count==0);uint64_t edges=s->edge_count,events=u.input_events;
 for(unsigned i=0;i<property_count;i++){if(strcmp(properties[i].name,"flash-mode"))assert(!properties[i].set);Visitor v={0};properties[i].get(NULL,&v,properties[i].name,s,NULL);}
 assert(s->edge_count==edges&&u.input_events==events);assert(!get_bool("bit-exact-supported")&&!get_bool("live-mode-change-supported"));Visitor v={0};aw3641_string_get(NULL,&v,"timing-policy",s,NULL);assert(strstr(v.text,"nominal-model")&&strstr(v.text,"last-rise+500us")&&strstr(v.text,"first-rise+220/1300ms")&&strstr(v.text,"model policy"));destroy(s);
}
int main(int argc,char **argv) {
 assert(argc==2);
 if(!strcmp(argv[1],"table"))table();else if(!strcmp(argv[1],"boundaries"))recommended_boundaries();else if(!strcmp(argv[1],"outside"))outside_window();else if(!strcmp(argv[1],"reset"))reset_boundary();else if(!strcmp(argv[1],"duplicates"))duplicate_and_wrong_pin();else if(!strcmp(argv[1],"torch"))torch();else if(!strcmp(argv[1],"mode"))frozen_mode();else if(!strcmp(argv[1],"initial-high"))initial_high();else if(!strcmp(argv[1],"many"))too_many();else if(!strcmp(argv[1],"trace"))trace_bound();else if(!strcmp(argv[1],"missing-pad"))missing_pad_callback();else if(!strcmp(argv[1],"route"))route_guard();else if(!strcmp(argv[1],"short-low"))short_low();else if(!strcmp(argv[1],"old-timer"))old_timer();else if(!strcmp(argv[1],"original-negative"))original_driver_negative();else if(!strcmp(argv[1],"readonly"))zero_and_readonly();else abort();
 return 0;
}
'''


class FlashLightPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text()
        cls.added = "\n".join(line[1:] for line in cls.patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        start = cls.added.index("/* BEGIN AW3641 NOMINAL DIGITAL MODEL")
        end = cls.added.index("/* END AW3641 NOMINAL DIGITAL MODEL */") + len("/* END AW3641 NOMINAL DIGITAL MODEL */")
        cls.fragment = cls.added[start:end]
        hook = cls.added[cls.added.index("void m5_unit_gpio_initial_complete(M5Unit *unit)"):]
        hook = hook[:hook.index("\n}") + len("\n}")]
        cls.harness = STUBS + cls.fragment + TESTS.replace("/* FREEZE_HOOK */", hook)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.tmp.name) / "aw3641"
        if shutil.which("cc"):
            source = cls.binary.with_suffix(".c")
            source.write_text(cls.harness)
            result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                                     "-Wno-unused-function", str(source), "-o", str(cls.binary)], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case):
        if not shutil.which("cc"):
            self.skipTest("C compiler unavailable")
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_patch_only_adds_unit_model_and_initial_freeze_hook(self):
        files = [line[6:] for line in self.patch.splitlines() if line.startswith("+++ b/")]
        self.assertEqual(set(files), {"hw/m5stopwatch/m5_unit_gpio.c", "hw/m5stopwatch/m5_unit_runtime.c", "hw/m5stopwatch/m5_unit_runtime.h"})
        self.assertIn('"hub", "flashlight"', self.added)
        self.assertIn("aw3641_new(unit)", self.added)
        self.assertNotIn("m5_unit_pwm_observe", self.fragment)
        self.assertNotIn("QEMU_CLOCK_REALTIME", self.fragment)
        self.assertIn("esp32_gpio_add_out_listener(unit->yellow, aw3641_pad_changed, s)", self.fragment)

    def test_creation_freeze_hook_follows_all_initial_fields_even_when_absent(self):
        runtime = self.patch.split("diff --git a/hw/m5stopwatch/m5_unit_runtime.c", 1)[1].split("diff --git", 1)[0]
        self.assertIn("m5_unit_gpio_initial_complete(u);", runtime)
        # The two closing braces precede the new call, so it is outside both
        # the field loop and optional initial object, not only the last field.
        self.assertIn("             }\n         }\n+        m5_unit_gpio_initial_complete(u);", runtime)

    def test_original_driver_bytes_keep_seven_long_flash_negative_controls(self):
        data = OFFICIAL.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), OFFICIAL_SHA)
        tree = ast.parse(data.decode())
        expressions = [ast.unparse(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "pulse" for t in n.targets)]
        self.assertEqual(expressions, ["brightness * time"])
        self.run_case("original-negative")

    def test_all_sixteen_documented_codes_and_nominal_timeout_origins(self): self.run_case("table")
    def test_recommended_pulse_window_endpoints(self): self.run_case("boundaries")
    def test_outside_recommended_window_is_unknown_and_long_low_recovers(self): self.run_case("outside")
    def test_strict_long_low_reset_boundary_and_no_repeated_reset(self): self.run_case("reset")
    def test_same_level_and_unrelated_pin_do_not_invent_edges(self): self.run_case("duplicates")
    def test_torch_static_truth_has_no_flash_percentage_or_deadline(self): self.run_case("torch")
    def test_creation_mode_freezes_and_rejects_idle_or_active_setter(self): self.run_case("mode")
    def test_initial_high_requires_observed_long_low(self): self.run_case("initial-high")
    def test_seventeen_plus_pulses_are_unknown_without_wrap_or_clamp(self): self.run_case("many")
    def test_trace_is_bounded_and_chronological_with_overflow_count(self): self.run_case("trace")
    def test_missing_reset_callback_withdraws_known_output_without_repairing_gpio(self): self.run_case("missing-pad")
    def test_unobserved_peripheral_or_inverted_matrix_route_is_unknown(self): self.run_case("route")
    def test_short_low_cannot_silently_start_a_new_program(self): self.run_case("short-low")
    def test_cancelled_old_deadline_cannot_turn_off_a_new_program(self): self.run_case("old-timer")
    def test_zero_pulses_readonly_state_and_explicit_partial_policy(self): self.run_case("readonly")


if __name__ == "__main__":
    unittest.main()
