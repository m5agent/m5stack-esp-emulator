"""Compile actual poll/notifier bodies; deterministic host controls, no guest."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_xtensa_high_priority_irq_cooperative import extract_function
from test_xtensa_inactive_irq_yield_guard_patch import hunks

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/qemu-wasm-probe/0032-wasm-wakeable-host-poll.patch'
FIXTURE = ROOT / 'platform/tests/fixtures/wasm_poll_wake_runtime74.json'


def projected_before():
    """Replay U3 against exact old function bodies plus their literal contexts."""
    originals = {}
    for name, changes in hunks(PATCH).items():
        rows = []
        for change in changes:
            while len(rows) < change['start'] - 1:
                rows.append('\n')
            if len(rows) != change['start'] - 1:
                raise AssertionError('overlapping hunks')
            rows.extend(change['before'])
        originals[name] = rows
    for name, item in json.loads(FIXTURE.read_text())['files'].items():
        rows = originals[name]
        offset = item['start_line'] - 1
        body = item['function'].splitlines(keepends=True)
        body[-1] += '\n'
        while len(rows) < offset + len(body):
            rows.append('\n')
        for index, line in enumerate(body, offset):
            if rows[index] != '\n' and rows[index] != line:
                raise AssertionError(f'fixture differs from patch preimage {name}:{index+1}')
            rows[index] = line
    return {name: ''.join(rows) for name, rows in originals.items()}


def actual_sources():
    before = projected_before()
    with tempfile.TemporaryDirectory(prefix='m5-poll-wake-replay-') as directory:
        tree = Path(directory)
        subprocess.run(['git', 'init', '-q', directory], check=True, capture_output=True)
        for name, text in before.items():
            p = tree / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        subprocess.run(['git', 'apply', '--check', str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=tree, check=True, capture_output=True)
        after = {name: (tree/name).read_text() for name in before}
        subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(['git', 'apply', '--reverse', str(PATCH)], cwd=tree, check=True, capture_output=True)
        if any((tree/name).read_text() != text for name, text in before.items()):
            raise AssertionError('reverse replay mismatch')
    timer = after['util/qemu-timer.c']
    start = timer.index('static uint32_t qemu_poll_wake_epoch;')
    end = timer.index('#endif', start)
    prefix = timer[start:end]
    old = extract_function(before['util/qemu-timer.c'], 'int qemu_poll_ns(')
    new = extract_function(timer, 'int qemu_poll_ns(')
    notifier = extract_function(after['util/event_notifier-posix.c'], 'int event_notifier_set(')
    return old, prefix, new, notifier


STUBS = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <sys/types.h>
#include <math.h>
#define __EMSCRIPTEN__ 1
#define MIN(a,b) ((a)<(b)?(a):(b))
typedef unsigned guint;
typedef struct {int fd;short events,revents;} GPollFD;
typedef struct {bool initialized;int wfd;} EventNotifier;
#define pthread_once_t fake_pthread_once_t
#define pthread_once fake_pthread_once
typedef int pthread_once_t;
#define PTHREAD_ONCE_INIT 0
static int pthread_once(pthread_once_t *once,void (*fn)(void)) {if(!*once){fn();*once=1;}return 0;}
static double now_ms,ready_at,error_at,queue_cost,max_wait;
static unsigned polls,sleeps,waits,wakes,cancels,queues,writes,compare_misses;
static int runtime_thread,mode,write_error,eintr_left;
static unsigned env_reads;
static bool ready,injected,spurious;
static const char *option;
static EventNotifier notifier={true,7};
static void qemu_poll_wake(void);
static int event_notifier_set(EventNotifier *);
static const char *fake_getenv(const char *key) {assert(!strcmp(key,"M5SW_POLL_WAKE"));env_reads++;return option;}
#define getenv fake_getenv
#define qatomic_read(ptr) __atomic_load_n((ptr),__ATOMIC_SEQ_CST)
#define qatomic_inc(ptr) ((void)__atomic_fetch_add((ptr),1,__ATOMIC_SEQ_CST))
static double emscripten_get_now(void) {return now_ms;}
static void pthread_testcancel(void) {cancels++;}
static void emscripten_current_thread_process_queued_calls(void) {
 queues++;now_ms+=queue_cost;queue_cost=0;
 if(mode==3&&!injected){injected=true;assert(!event_notifier_set(&notifier));}
}
static int emscripten_is_main_runtime_thread(void) {return runtime_thread;}
static ssize_t mock_write(int fd,const void *data,size_t length) {
 assert(fd==7&&length==8&&*(const uint64_t *)data==1);writes++;
 if(eintr_left){eintr_left--;errno=EINTR;return -1;}
 if(write_error){errno=write_error;return -1;}
 ready=true;return 8;
}
#define write mock_write
static int g_poll(GPollFD *fds,guint nfds,int timeout) {
 assert(!timeout);assert(++polls<1000);
 if(now_ms>=error_at){errno=EINTR;return -1;}
 int result=nfds&&ready;
 if(nfds)fds[0].revents=result?1:0;
 /* Notification deliberately races after poll computed its empty result. */
 if(mode==2&&!injected){injected=true;assert(!event_notifier_set(&notifier));}
 return result;
}
static void emscripten_thread_sleep(double ms) {
 assert(ms>0&&ms<=5);sleeps++;max_wait=fmax(max_wait,ms);now_ms+=ms;
 if(!injected&&now_ms>=ready_at){injected=true;assert(!event_notifier_set(&notifier));}
}
static int emscripten_futex_wake(volatile void *ptr,int count) {
 (void)ptr;assert(count==INT_MAX);wakes++;return 0;
}
static int emscripten_futex_wait(volatile void *ptr,uint32_t value,double ms) {
 assert(ms>0&&ms<=5);waits++;max_wait=fmax(max_wait,ms);
 if(__atomic_load_n((uint32_t *)ptr,__ATOMIC_SEQ_CST)!=value){compare_misses++;return -EWOULDBLOCK;}
 if(spurious){spurious=false;now_ms+=0.1;return 0;}
 if(!injected&&ready_at<=now_ms+ms){
  if(mode==4){now_ms+=ms;injected=true;ready=true;return -ETIMEDOUT;}
  now_ms=ready_at;injected=true;assert(!event_notifier_set(&notifier));return 0;
 }
 now_ms+=ms;return -ETIMEDOUT;
}
'''

CONTROLS = r'''
static void reset(const char *value) {
 now_ms=1000;ready_at=error_at=INFINITY;queue_cost=max_wait=0;
 polls=sleeps=waits=wakes=cancels=queues=writes=compare_misses=0;
 runtime_thread=mode=write_error=eintr_left=0;ready=injected=spurious=false;
 env_reads=0;
 option=value;qemu_poll_wake_epoch=0;qemu_poll_wake_once=0;
 qemu_poll_wake_enabled=false;notifier=(EventNotifier){true,7};
}
int main(void) {
 GPollFD fd={7,1,0};unsigned controls=0;
 for(unsigned legacy=0;legacy<2;legacy++) {
  reset(legacy?"0":NULL);ready=true;
  assert(qemu_poll_ns(&fd,1,1000000)==1&&fd.revents==1&&!waits&&!sleeps);controls++;
  reset(legacy?"0":NULL);
  assert(qemu_poll_ns(&fd,1,0)==0&&!waits&&!sleeps);controls++;
  reset(legacy?"0":NULL);error_at=1000;
  assert(qemu_poll_ns(&fd,1,-1)==-1&&errno==EINTR&&!waits&&!sleeps);controls++;
  reset(legacy?"0":NULL);
  assert(qemu_poll_ns(NULL,0,125000)==0&&fabs(now_ms-1000.125)<1e-6);controls++;
  reset(legacy?"0":NULL);
  assert(qemu_poll_ns(NULL,0,12000000)==0&&now_ms==1012);controls++;
  reset(legacy?"0":NULL);ready_at=1001;
  assert(qemu_poll_ns(&fd,1,-1)==1&&fd.revents==1);
  assert(now_ms==(legacy?1005:1001));controls++;
 }
 for(int race=2;race<=3;race++) {
  reset(NULL);mode=race;
  assert(qemu_poll_ns(&fd,1,-1)==1&&now_ms==1000&&compare_misses==1);controls++;
 }
 reset(NULL);mode=2;qemu_poll_wake_epoch=UINT32_MAX;
 assert(qemu_poll_ns(&fd,1,-1)==1&&qemu_poll_wake_epoch==0&&compare_misses==1);controls++;
 reset(NULL);spurious=true;ready_at=1001;
 assert(qemu_poll_ns(&fd,1,-1)==1&&polls>=3&&now_ms==1001);controls++;
 reset(NULL);mode=4;ready_at=1000.5;
 assert(qemu_poll_ns(&fd,1,-1)==1&&now_ms==1005&&!wakes);controls++;
 reset(NULL);runtime_thread=1;ready_at=1002.5;
 assert(qemu_poll_ns(&fd,1,-1)==1&&now_ms==1002.5&&max_wait<=1);controls++;
 reset(NULL);queue_cost=4;
 assert(qemu_poll_ns(NULL,0,2000000)==0&&now_ms==1004&&!waits&&polls==2);controls++;
 reset(NULL);mode=2; // unrelated notifier wake does not make nfds=0 ready
 assert(qemu_poll_ns(NULL,0,2000000)==0&&now_ms==1002&&polls>=2);controls++;
 reset(NULL);error_at=1002;
 assert(qemu_poll_ns(&fd,1,12000000)==-1&&errno==EINTR&&now_ms==1005);controls++;
 reset(NULL);ready_at=1001;
 assert(qemu_poll_ns(&fd,1,INT64_MAX)==1&&now_ms==1001);controls++;
 reset(NULL);ready_at=1001;
 assert(qemu_poll_ns(&fd,1,1000000)==1&&now_ms==1001);controls++;
 reset(NULL);notifier.initialized=false;
 assert(event_notifier_set(&notifier)==-1&&!writes&&!wakes);controls++;
 reset(NULL);write_error=EBADF;
 assert(event_notifier_set(&notifier)==-EBADF&&writes==1&&!wakes);controls++;
 reset(NULL);write_error=EAGAIN;
 assert(!event_notifier_set(&notifier)&&writes==1&&wakes==1);controls++;
 reset(NULL);eintr_left=2;
 assert(!event_notifier_set(&notifier)&&writes==3&&wakes==1);controls++;
 const char *values[]={NULL,"0","1","false",""};
 for(unsigned i=0;i<5;i++) {
  reset(values[i]);qemu_poll_wake();assert(wakes==1&&!env_reads&&!qemu_poll_wake_once);
  assert(qemu_poll_can_wake()==(i!=1)&&env_reads==1);
  option=i==1?"1":"0";qemu_poll_wake();assert(wakes==2&&env_reads==1);
  assert(qemu_poll_can_wake()==(i!=1)&&env_reads==1);controls++;
 }
 printf("WAKEABLE_POLL_HOST_PASS controls=%u\n",controls);return 0;
}
'''


class WasmPollWakeTests(unittest.TestCase):
    def test_selected_source_lock_binds_exact_patch_and_postimages(self):
        lock = json.loads((ROOT / 'scripts/qemu-wasm-build/sources.lock.json').read_text())
        row = next(row for row in lock['patches'] if row['path'] == str(PATCH.relative_to(ROOT)))
        self.assertEqual(row['sha256'], hashlib.sha256(PATCH.read_bytes()).hexdigest())
        self.assertEqual({name: lock['patched_files'][name] for name in (
            'util/qemu-timer.c', 'util/event_notifier-posix.c', 'include/qemu/timer.h')}, {
                'util/qemu-timer.c': '826348b1f908855849738834af68a21738901950e1765d71c5ce5249e73796a9',
                'util/event_notifier-posix.c': 'd3d3207171b3f1e929c6870a38049bd9d88c8a3faf79f459c406d35aa19ef36d',
                'include/qemu/timer.h': 'dd57255e9a10dfed370573636fde996bb79aedb842abbb27313e93f900655365',
            })

    def test_literal_hunks_replay_and_preserve_native_branch(self):
        old, prefix, new, notifier = actual_sources()
        self.assertEqual(old[old.index('#elif defined(CONFIG_PPOLL)'):],
                         new[new.index('#elif defined(CONFIG_PPOLL)'):])
        self.assertNotIn('QEMU_CLOCK_', prefix + new)
        self.assertLess(notifier.index('ret = write('), notifier.index('qemu_poll_wake();'))
        self.assertIn('pthread_testcancel();', new)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('git'), 'host compiler and git required')
    def test_actual_poll_notifier_and_race_controls(self):
        _, prefix, new, notifier = actual_sources()
        source = STUBS + prefix + new + notifier + CONTROLS
        with tempfile.TemporaryDirectory(prefix='m5-poll-wake-c-') as directory:
            path = Path(directory)/'probe.c';binary=Path(directory)/'probe'
            path.write_text(source)
            result = subprocess.run([shutil.which('cc'), '-std=c11', '-Wall', '-Werror',
                                     str(path), '-lm', '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('WAKEABLE_POLL_HOST_PASS controls=32', result.stdout)
            # Snapshotting after poll loses the deliberate poll-to-wait race.
            bad = source.replace('uint32_t epoch = qatomic_read(&qemu_poll_wake_epoch);\n        int result = g_poll(fds, nfds, 0);',
                                 'int result = g_poll(fds, nfds, 0);\n        uint32_t epoch = qatomic_read(&qemu_poll_wake_epoch);')
            self.assertNotEqual(source, bad)
            path.write_text(bad)
            subprocess.run([shutil.which('cc'), '-std=c11', str(path), '-lm', '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, 'late snapshot negative control was not detected')
            bad_notifier = notifier.replace('    qemu_poll_wake();', '', 1).replace(
                '    do {', '    qemu_poll_wake();\n    do {', 1)
            self.assertNotEqual(notifier, bad_notifier)
            path.write_text(STUBS + prefix + new + bad_notifier + CONTROLS)
            subprocess.run([shutil.which('cc'), '-std=c11', str(path), '-lm', '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, 'wake before actual write/error negative control was not detected')
            bad_poll = new.replace('emscripten_futex_wait(&qemu_poll_wake_epoch, epoch, wait_ms);',
                                   'emscripten_futex_wait(&qemu_poll_wake_epoch, epoch, wait_ms); return 1;')
            self.assertNotEqual(new, bad_poll)
            path.write_text(STUBS + prefix + bad_poll + notifier + CONTROLS)
            subprocess.run([shutil.which('cc'), '-std=c11', str(path), '-lm', '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, 'wake-as-ready negative control was not detected')


if __name__ == '__main__':
    unittest.main()
