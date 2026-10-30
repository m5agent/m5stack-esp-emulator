"""Exercise replayed SCS UART packet code with synthetic clock/UART/QOM peers.

This compiles the tracked C implementation, not a Python duplicate. It is a
controller protocol regression, not a virtual-device or physical-hardware run.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'patches/qemu-m5stack-peripherals'
PATCH = PATCHES / '0101-stackchan-scs-motion-observer.patch'
WIRING_PATCH = PATCHES / '0105-stackchan-scs-uart-wiring.patch'
COMMAND_EDGES_PATCH = PATCHES / '0107-stackchan-scs-command-edges.patch'
COMMAND_EDGES_FIXTURE = ROOT / 'platform/tests/fixtures/stackchan_scs_command_edges.c'
UNIT = 'hw/m5stopwatch/m5_scs_servo.c'

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define CLAMP(x,lo,hi) MIN(MAX(x,lo),hi)
#define g_new0(type,count) ((type *)calloc(count,sizeof(type)))
#define QEMU_CLOCK_VIRTUAL 0
static int64_t now_ms;
static int64_t qemu_clock_get_ms(int clock) { return now_ms; }
typedef struct QObject QObject;
struct QObject { int kind; const char *key[32]; QObject *value[32]; int count; int64_t number; const char *str; };
typedef QObject QDict;
typedef QObject QList;
typedef struct Object { int unused; } Object;
typedef Object DeviceState;
typedef struct Error { int unused; } Error;
typedef struct Visitor { QObject *value; } Visitor;
#define QOBJECT(value) ((QObject *)(value))
static QObject *qnew(int kind) { QObject *o=calloc(1,sizeof(*o));o->kind=kind;return o; }
static QDict *qdict_new(void) { return qnew(1); }
static QList *qlist_new(void) { return qnew(2); }
static void qdict_put_obj(QDict *o,const char *key,QObject *v) { assert(o->count<32);o->key[o->count]=key;o->value[o->count++]=v; }
static void qdict_put_int(QDict *o,const char *key,int64_t n) { QObject *v=qnew(3);v->number=n;qdict_put_obj(o,key,v); }
static void qdict_put_bool(QDict *o,const char *key,bool b) { qdict_put_int(o,key,b); }
static void qdict_put_str(QDict *o,const char *key,const char *s) { QObject *v=qnew(4);v->str=s;qdict_put_obj(o,key,v); }
static void qlist_append_obj(QList *o,QObject *v) { assert(o->count<32);o->value[o->count++]=v; }
static void visit_type_any(Visitor *v,const char *name,QObject **value,Error **errp) { v->value=*value; }
static void qobject_unref(QObject *o) { /* Kept until harness process exit for assertions. */ }
static QObject *field(QObject *o,const char *name) { for(int i=0;i<o->count;i++)if(!strcmp(o->key[i],name))return o->value[i];assert(!"missing snapshot field");return NULL; }
static Object root_object;
static Object *object_new(const char *name) { assert(!strcmp(name,"container"));return &root_object; }
static Object *qdev_get_machine(void) { return &root_object; }
static void object_unref(Object *o) { }
static void object_property_add_child(Object *root,const char *name,Object *child) { assert(!strcmp(name,"scs_servo")); }
typedef void (*Getter)(Object *,Visitor *,const char *,void *,Error **);
static Getter getter;
static void *getter_opaque;
static void object_property_add(Object *o,const char *name,const char *type,Getter read,void *write,void *release,void *opaque) {
    assert(!strcmp(name,"state")&&!strcmp(type,"any")&&write==NULL);getter=read;getter_opaque=opaque;
}
typedef struct ESP32UARTState { void (*tx)(void *,uint8_t);void *opaque;uint8_t rx[256];unsigned rx_len; } ESP32UARTState;
#define ESP32_UART(uart) ((ESP32UARTState *)(uart))
static void esp32_uart_set_tx_byte_callback(ESP32UARTState *uart,void (*cb)(void *,uint8_t),void *opaque) { uart->tx=cb;uart->opaque=opaque; }
static void esp32_uart_inject_rx(ESP32UARTState *uart,const uint8_t *data,int count) { assert(count<=256);memcpy(uart->rx,data,count);uart->rx_len=count; }
static int tx_signal=15,rx_pin=7;
static int esp32_gpio_matrix_out_signal(int pin,bool s3) { assert(pin==6&&s3);return tx_signal; }
static int esp32_gpio_matrix_in_pin(unsigned signal,bool s3) { assert(signal==15&&s3);return rx_pin; }
static bool rail_enabled;
static bool m5sw_stackchan_servo_power_enabled(void) { return rail_enabled; }
void m5_scs_servo_power_changed(bool enabled);
'''

CASES = r'''
static ESP32UARTState uart;
static void fresh(void) {
    memset(&uart,0,sizeof(uart));rail_enabled=false;now_ms=0;tx_signal=15;rx_pin=7;
    scs_peer=NULL;m5_scs_servo_attach((DeviceState *)&uart);
}
static void power(bool on) { rail_enabled=on;m5_scs_servo_power_changed(on); }
static void packet(int id,int instruction,const uint8_t *params,unsigned count,bool valid) {
    uint8_t bytes[256]={0xff,0xff,id,count+2,instruction};
    uint8_t sum=id+count+2+instruction;
    assert(count+6<=sizeof(bytes));
    for(unsigned i=0;i<count;i++){bytes[5+i]=params[i];sum+=params[i];}
    bytes[5+count]=(uint8_t)~sum;if(!valid)bytes[5+count]^=1;
    uart.rx_len=0;
    for(unsigned i=0;i<count+6;i++)uart.tx(uart.opaque,bytes[i]);
}
static void write_bytes(int id,int instruction,uint8_t addr,const uint8_t *bytes,unsigned count) {
    uint8_t params[128];assert(count<sizeof(params));params[0]=addr;memcpy(params+1,bytes,count);
    packet(id,instruction,params,count+1,true);
}
static void torque(int id,int value) { uint8_t v=value;write_bytes(id,3,40,&v,1); }
static void move(int id,int instruction,int goal,int time) {
    uint8_t params[]={goal>>8,goal,time>>8,time,0,0};write_bytes(id,instruction,42,params,sizeof(params));
}
static int read_position(int id) {
    uint8_t params[]={56,2};packet(id,2,params,2,true);
    assert(uart.rx_len==8&&uart.rx[2]==id&&uart.rx[4]==0);
    uint8_t sum=0;for(unsigned i=2;i<uart.rx_len;i++)sum+=uart.rx[i];assert(sum==0xff);
    return (uart.rx[5]<<8)|uart.rx[6];
}
static QObject *snapshot(void) { Visitor v={0};getter(&root_object,&v,"state",getter_opaque,NULL);return v.value; }
static int present(int id) { return scs_get_be16(scs_peer->mem[id],56); }
int main(void) {
    /* An unpowered peer is unreachable, including well-formed writes. */
    fresh();packet(1,1,NULL,0,true);assert(uart.rx_len==0);
    move(1,3,900,20);assert(present(1)==460);
    power(true);packet(1,1,NULL,0,true);assert(uart.rx_len==6);
    packet(9,1,NULL,0,true);assert(uart.rx_len==0);
    assert(read_position(1)==460&&read_position(2)==620);
    /* Torque off retains goal without moving the shaft. */
    move(1,3,650,100);now_ms=50;assert(read_position(1)==460);
    torque(1,1);now_ms=100;assert(read_position(1)==555);
    assert(scs_peer->mem[1][66]==1);now_ms=150;assert(read_position(1)==650);
    assert(scs_peer->mem[1][66]==0);
    /* New commands start from current position, including reverse direction. */
    move(1,3,450,100);now_ms=200;assert(read_position(1)==550);
    torque(1,0);now_ms=1000;assert(read_position(1)==550);
    torque(1,1);now_ms=1050;assert(read_position(1)==500);
    /* Rail loss freezes actual intermediate position and resets drive SRAM. */
    now_ms=1075;power(false);assert(present(1)==475);
    assert(scs_peer->mem[1][40]==0&&scs_peer->mem[1][66]==0);
    power(true);now_ms=2000;assert(read_position(1)==475);
    torque(1,1);assert(read_position(1)==475);
    /* REG_WRITE is pending until ACTION and does not overwrite later torque. */
    move(1,4,600,100);assert(read_position(1)==475);
    torque(1,0);packet(0xfe,5,NULL,0,true);now_ms+=200;assert(read_position(1)==475);
    assert(scs_get_be16(scs_peer->mem[1],42)==600&&scs_peer->mem[1][40]==0);
    torque(1,1);now_ms+=100;assert(read_position(1)==600);
    move(1,4,700,20);assert(read_position(1)==600);
    packet(1,5,NULL,0,true);assert(uart.rx_len==6);now_ms+=20;assert(read_position(1)==700);
    /* A power cycle discards deferred actions instead of replaying stale motion. */
    move(1,4,800,20);power(false);power(true);torque(1,1);
    packet(0xfe,5,NULL,0,true);now_ms+=100;assert(read_position(1)==700);
    /* Broadcast WRITE and SYNC_WRITE are genuine UART packet paths. */
    torque(0xfe,1);assert(scs_peer->mem[1][40]==1&&scs_peer->mem[2][40]==1);
    uint8_t sync[]={42,6,1,0x01,0xf4,0,20,0,0,2,0x01,0x2c,0,20,0,0};
    packet(0xfe,0x83,sync,sizeof(sync),true);assert(uart.rx_len==0);
    now_ms+=10;assert(read_position(1)==600&&read_position(2)==460);
    now_ms+=10;assert(read_position(1)==500&&read_position(2)==300);
    /* Invalid checksum/length/telemetry writes never forge shaft feedback. */
    uint8_t invalid_goal[]={42,0x03,0x84};
    packet(1,3,invalid_goal,sizeof(invalid_goal),false);now_ms+=200;assert(read_position(1)==500);
    uint8_t short_read[]={56};packet(1,2,short_read,sizeof(short_read),true);assert(uart.rx_len==0);
    uint8_t fake[]={0x03,0xe8};write_bytes(1,3,56,fake,sizeof(fake));assert(read_position(1)==500);
    uint8_t broken_sync[]={42,6,1,0,1};packet(0xfe,0x83,broken_sync,sizeof(broken_sync),true);assert(read_position(1)==500);
    uint8_t bad_torque=255;write_bytes(1,3,40,&bad_torque,1);assert(scs_peer->mem[1][40]==1);
    /* PWM sign is observed, but no unimplemented physical rotation is invented. */
    uint8_t pwm_mode[]={0,0,0,0};write_bytes(1,3,9,pwm_mode,sizeof(pwm_mode));
    uint8_t pwm_negative[]={0x06,0x00};write_bytes(1,3,44,pwm_negative,sizeof(pwm_negative));
    now_ms+=1000;assert(read_position(1)==500&&scs_peer->mem[1][66]==0);
    QObject *state=snapshot();assert(field(state,"schema_version")->number==1);
    assert(!strcmp(field(state,"source")->str,"qemu-uart1-scs-controller"));
    assert(field(state,"powered")->number==1&&field(state,"rejected_packets")->number>=4);
    assert(field(state,"pwm_motion_modelled")->number==0);
    QObject *servos=field(state,"servos");assert(servos->count==2);
    assert(field(servos->value[0],"present_position")->number==500);
    assert(field(servos->value[0],"pwm")->number==-512);
    assert(field(servos->value[0],"moving")->number==0);
    /* A deferred lock/EEPROM update cannot extend a running motion. */
    fresh();power(true);torque(1,1);move(1,3,1000,1000);
    now_ms=400;assert(read_position(1)==676);
    uint8_t lock=1;write_bytes(1,4,48,&lock,1);packet(0xfe,5,NULL,0,true);
    now_ms=1000;assert(read_position(1)==1000&&scs_peer->mem[1][66]==0);
    /* Wrong TX pins cannot operate servos; wrong RX pins cannot return feedback.
     * Restoring the real route must recover without a reset or host-side values.
     */
    fresh();power(true);torque(1,1);tx_signal=14;
    move(1,3,800,100);now_ms=1000;scs_sync_power(scs_peer);
    assert(present(1)==460&&scs_get_be16(scs_peer->mem[1],42)==460);
    assert(scs_peer->disconnected_tx_bytes>0);tx_signal=15;
    rx_pin=8;move(1,3,800,100);assert(uart.rx_len==0);
    now_ms+=100;scs_sync_power(scs_peer);assert(present(1)==800);
    uint8_t read_params[]={56,2};packet(1,2,read_params,2,true);assert(uart.rx_len==0);
    assert(scs_peer->disconnected_rx_packets>=2);rx_pin=7;assert(read_position(1)==800);
    /* 20ms BSP updates follow intermediate feedback without host interpolation. */
    for(int i=0;i<200;i++){move(1,3,100+i*4,20);now_ms+=10;int middle=read_position(1);now_ms+=10;int end=read_position(1);assert(middle>=0&&middle<=1000);assert(end==100+i*4);}
    /* Full raw bounds and the longest unsigned move duration stay monotonic. */
    move(1,3,0,65535);now_ms+=32767;assert(read_position(1)>0);now_ms+=32768;assert(read_position(1)==0);
    move(1,3,1000,65535);now_ms+=32767;assert(read_position(1)>0&&read_position(1)<1000);now_ms+=32768;assert(read_position(1)==1000);
    /* Locked torque never turns position writes into displacement. */
    torque(1,2);move(1,3,0,20);now_ms+=100;assert(read_position(1)==1000);
    scs_command_edges_cases();
    puts("SCS UART protocol, timed feedback, torque/rail, deferred/sync writes, rejection and observer cases passed");
    return 0;
}
'''


class StackchanScsPatchTests(unittest.TestCase):
    def _replayed_model(self, root, with_command_edges=True):
        baseline = (PATCHES / '0002-m5stack-peripheral-data-paths.patch').read_text()
        section = baseline.split('+++ b/' + UNIT, 1)[1].split('\n@@', 1)[1]
        section = section.split('\ndiff ', 1)[0]
        original = ''.join(line[1:] + '\n' for line in section.splitlines() if line.startswith('+'))
        source = root / UNIT
        source.parent.mkdir(parents=True)
        source.write_text(original)
        patches = [PATCH, WIRING_PATCH]
        if with_command_edges:
            patches.append(COMMAND_EDGES_PATCH)
        for patch in patches:
            result = subprocess.run(['patch', '--batch', '-p1', '-i', str(patch)], cwd=root,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return re.sub(r'^#include[^\n]*\n', '', source.read_text(), flags=re.M)

    def _run_controller(self, root, model, edge_case=0):
        compiler = shutil.which('cc')
        if compiler is None:
            self.skipTest('C compiler is unavailable')
        harness = root / 'harness.c'
        cases = CASES.replace('int main(void)',
                              COMMAND_EDGES_FIXTURE.read_text() + '\nint main(void)', 1)
        harness.write_text(STUBS + model + cases)
        executable = root / 'harness'
        result = subprocess.run([compiler, '-std=c11', '-Wall', '-Werror',
                                 '-Wno-unused-parameter',
                                 '-DSCS_COMMAND_EDGES_CASE=' + str(edge_case),
                                 str(harness), '-o', str(executable)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return subprocess.run([str(executable)], cwd=root, text=True, capture_output=True)

    def test_replayed_controller_packets(self):
        with tempfile.TemporaryDirectory(prefix='m5-scs-patch-') as folder:
            root = Path(folder)
            result = self._run_controller(root, self._replayed_model(root))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('observer cases passed', result.stdout)

    def test_command_edges_fail_without_fix(self):
        for edge_case in (1, 2):
            with self.subTest(edge_case=edge_case):
                with tempfile.TemporaryDirectory(prefix='m5-scs-before-fix-') as folder:
                    root = Path(folder)
                    model = self._replayed_model(root, with_command_edges=False)
                    result = self._run_controller(root, model, edge_case)
                    self.assertNotEqual(result.returncode, 0,
                                        'Pre-fix controller unexpectedly passed regression')


if __name__ == '__main__':
    unittest.main()
