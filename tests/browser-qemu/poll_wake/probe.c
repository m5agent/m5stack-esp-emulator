/* SPDX-License-Identifier: MIT
 * Real SDK pipe/notifier/futex controls, without QEMU or guest execution.
 * actual-poll.inc is reconstructed from the replayable candidate patch.
 */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <poll.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <emscripten/emscripten.h>
#include <emscripten/threading.h>
typedef unsigned guint;
typedef struct pollfd GPollFD;
typedef struct {bool initialized;int rfd,wfd;} EventNotifier;
#define MIN(a,b) ((a)<(b)?(a):(b))
#define qatomic_read(ptr) __atomic_load_n((ptr),__ATOMIC_SEQ_CST)
#define qatomic_inc(ptr) ((void)__atomic_fetch_add((ptr),1,__ATOMIC_SEQ_CST))
#define ROUNDS 24
static EventNotifier target;
static unsigned phase,iteration,completed;
static uint64_t ready_us;
static bool capture,notified;
static uint64_t host_us(void) {return (uint64_t)(emscripten_get_now()*1000.0);}
static int measured_poll(struct pollfd *fds,nfds_t nfds,int timeout) {
 int result=poll(fds,nfds,timeout);
 if(capture&&!result)__atomic_store_n(&phase,iteration,__ATOMIC_SEQ_CST);
 return result;
}
static ssize_t measured_write(int fd,const void *data,size_t count) {
 ssize_t result=write(fd,data,count);
 if(capture&&fd==target.wfd&&result>0)__atomic_store_n(&ready_us,host_us(),__ATOMIC_SEQ_CST);
 return result;
}
#define g_poll measured_poll
#define write measured_write
#include "actual-poll.inc"
#undef write
static int (*tested_poll)(GPollFD *,guint,int64_t);
static unsigned cancel_entered,cancel_cleaned;
static void cancel_cleanup(void *unused) {
 (void)unused;__atomic_store_n(&cancel_cleaned,1,__ATOMIC_SEQ_CST);
}
static void make_notifier(EventNotifier *e) {
 int fds[2];assert(!pipe(fds));assert(!fcntl(fds[0],F_SETFL,O_NONBLOCK));
 assert(!fcntl(fds[1],F_SETFL,O_NONBLOCK));*e=(EventNotifier){true,fds[0],fds[1]};
}
static void close_notifier(EventNotifier *e) {assert(!close(e->rfd));assert(!close(e->wfd));e->initialized=false;}
static void *producer(void *unused) {
 (void)unused;
 for(unsigned i=1;i<=ROUNDS;i++) {
  while(__atomic_load_n(&phase,__ATOMIC_SEQ_CST)<i)emscripten_thread_sleep(0.1);
  emscripten_thread_sleep(0.75);
  if(notified){assert(!event_notifier_set(&target));}
  else {const uint64_t value=1;assert(measured_write(target.wfd,&value,8)==8);}
  __atomic_store_n(&completed,i,__ATOMIC_SEQ_CST);
 }
 return NULL;
}
static int compare_double(const void *a,const void *b) {double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);}
static unsigned cancel_returned;
static void *cancel_waiter(void *unused) {
 (void)unused;GPollFD fd={target.rfd,POLLIN,0};
 __atomic_store_n(&cancel_entered,1,__ATOMIC_SEQ_CST);
 pthread_cleanup_push(cancel_cleanup,NULL);
 tested_poll(&fd,1,-1);
 pthread_cleanup_pop(0);
 __atomic_store_n(&cancel_returned,1,__ATOMIC_SEQ_CST);
 return (void *)42;
}
static int cancel_control(void) {
 pthread_t thread;make_notifier(&target);
 assert(!pthread_create(&thread,NULL,cancel_waiter,NULL));
 double deadline=emscripten_get_now()+1000;
 while(!__atomic_load_n(&cancel_entered,__ATOMIC_SEQ_CST)&&emscripten_get_now()<deadline)emscripten_thread_sleep(0.1);
 fprintf(stderr,"M5_CANCEL_PHASE entered=%u\n",__atomic_load_n(&cancel_entered,__ATOMIC_SEQ_CST));
 int canceled=pthread_cancel(thread);fprintf(stderr,"M5_CANCEL_PHASE post-cancel=%d\n",canceled);
 /* Match the SDK cancellation fixture's bounded shared-memory observation.
  * Processing caller proxy queues here is a separate SDK teardown variable. */
 deadline=emscripten_get_now()+100;
 while(!__atomic_load_n(&cancel_cleaned,__ATOMIC_SEQ_CST)&&emscripten_get_now()<deadline){}
 unsigned cleaned=__atomic_load_n(&cancel_cleaned,__ATOMIC_SEQ_CST);
 fprintf(stderr,"M5_CANCEL_PHASE cleanup=%u\n",cleaned);
 if(!cleaned) {
  /* Real pipe input permits a cooperative return if cancellation was not
   * consumed. This fallback never counts as cancellation PASS. */
  assert(!event_notifier_set(&target));deadline=emscripten_get_now()+100;
  while(!__atomic_load_n(&cancel_returned,__ATOMIC_SEQ_CST)&&!__atomic_load_n(&cancel_cleaned,__ATOMIC_SEQ_CST)&&emscripten_get_now()<deadline){}
 }
 unsigned returned=__atomic_load_n(&cancel_returned,__ATOMIC_SEQ_CST);
 unsigned cleaned_after=__atomic_load_n(&cancel_cleaned,__ATOMIC_SEQ_CST);
 fprintf(stderr,"M5_CANCEL_PHASE target-returned=%u cleanup=%u\n",returned,cleaned_after);
 bool joined=false;void *status=NULL;
 if(cleaned_after||returned) {assert(!pthread_join(thread,&status));joined=true;}
 fprintf(stderr,"M5_CANCEL_PHASE joined=%u\n",joined);
 printf("M5_POLL_CANCEL {\"cleanup_before_fallback\":%u,\"cleanup_after_fallback\":%u,\"cooperative_return\":%u,\"joined\":%s,\"canceled_status\":%s}\n",cleaned,cleaned_after,returned,joined?"true":"false",joined&&status==PTHREAD_CANCELED?"true":"false");
 if(joined)close_notifier(&target);
 return cleaned&&joined&&status==PTHREAD_CANCELED?0:1;
}
typedef struct {EventNotifier *e;unsigned done;} Waiter;
static void *ready_waiter(void *opaque) {
 Waiter *w=opaque;GPollFD fd={w->e->rfd,POLLIN,0};
 assert(tested_poll(&fd,1,1000000000)==1&&(fd.revents&POLLIN));
 __atomic_store_n(&w->done,1,__ATOMIC_SEQ_CST);return NULL;
}
int main(int argc,char **argv) {
 fprintf(stderr,"M5_POLL_PHASE start\n");
 assert(argc==2||argc==3);assert(!setenv("M5SW_POLL_WAKE",strcmp(argv[1],"wake")?"0":"1",1));
 tested_poll=!strcmp(argv[1],"original")?original_poll_ns:qemu_poll_ns;
 if(argc==3){assert(!strcmp(argv[2],"cancel"));return cancel_control();}
 double latencies[2][ROUNDS],finite_ms,start;pthread_t thread;
 make_notifier(&target);GPollFD fd={target.rfd,POLLIN,0};
 assert(tested_poll(&fd,1,0)==0);
 start=emscripten_get_now();assert(!tested_poll(NULL,0,2500000));finite_ms=emscripten_get_now()-start;
 assert(finite_ms>=2.3&&finite_ms<1000);
 fprintf(stderr,"M5_POLL_PHASE finite\n");
 for(unsigned lane=0;lane<2;lane++) {
  capture=false;phase=iteration=completed=0;notified=lane==0;
  assert(!pthread_create(&thread,NULL,producer,NULL));capture=true;
  for(iteration=1;iteration<=ROUNDS;iteration++) {
   fd.revents=0;
   assert(tested_poll(&fd,1,iteration==ROUNDS?-1:1000000000)==1&&(fd.revents&POLLIN));
   uint64_t end=host_us(),ready=__atomic_load_n(&ready_us,__ATOMIC_SEQ_CST);
   assert(ready&&end>=ready);latencies[lane][iteration-1]=(end-ready)/1000.0;
   uint64_t value=0;assert(read(target.rfd,&value,8)==8&&value==1);
   while(__atomic_load_n(&completed,__ATOMIC_SEQ_CST)<iteration)emscripten_thread_sleep(0.1);
  }
  capture=false;assert(!pthread_join(thread,NULL));
  qsort(latencies[lane],ROUNDS,sizeof(double),compare_double);
  fprintf(stderr,"M5_POLL_PHASE lane=%u\n",lane);
 }
 printf("M5_POLL_LATENCY {\"mode\":\"%s\",\"notified_median_ms\":%.3f,\"js_only_median_ms\":%.3f}\n",argv[1],latencies[0][ROUNDS/2],latencies[1][ROUNDS/2]);
 /* An unrelated global wake cannot manufacture readiness for another pipe. */
 EventNotifier other;make_notifier(&other);Waiter a={&target,0},b={&other,0};pthread_t workers[2];
 assert(!pthread_create(&workers[0],NULL,ready_waiter,&a));assert(!pthread_create(&workers[1],NULL,ready_waiter,&b));
 emscripten_thread_sleep(2);assert(!event_notifier_set(&target));
 while(!__atomic_load_n(&a.done,__ATOMIC_SEQ_CST))emscripten_thread_sleep(0.1);
 assert(!__atomic_load_n(&b.done,__ATOMIC_SEQ_CST));assert(!event_notifier_set(&other));
 assert(!pthread_join(workers[0],NULL)&&!pthread_join(workers[1],NULL));
 close_notifier(&target);close_notifier(&other);
 printf("M5_POLL_WAKE {\"mode\":\"%s\",\"main_runtime\":%d,\"rounds\":%u,\"finite_ms\":%.3f,"
  "\"notified_median_ms\":%.3f,\"notified_p95_ms\":%.3f,\"js_only_median_ms\":%.3f,"
  "\"cancel_join\":\"separate lane\",\"unrelated_waiter\":true}\n",argv[1],emscripten_is_main_runtime_thread(),ROUNDS,
  finite_ms,latencies[0][ROUNDS/2],latencies[0][ROUNDS-2],latencies[1][ROUNDS/2]);
 return 0;
}
