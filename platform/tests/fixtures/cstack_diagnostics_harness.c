/* SPDX-License-Identifier: GPL-2.0-or-later
 * Host-only CSTACK gate differential fixture. Actual MMU and coroutine
 * algorithms are inserted from the complete committed patch context.
 * The small MMU entry layout below follows pinned Espressif QEMU commit
 * 40edccac415693c5130f91c01d84176ae6008566, include/hw/misc/esp32s3_cache.h.
 * Block/IOMMU/fiber/stack helpers are deterministic host shims; this fixture
 * never proves guest, Emscripten-fiber, hardware or performance behavior.
 */
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <pthread.h>
#define ESP32S3_PAGE_SIZE 65536
#define ESP32S3_MMU_TYPE_FLASH 0
#define ESP32S3_MMU_TYPE_PSRAM 1
#define CACHE_DEBUG 0
#define IOMMU_NOTIFIER_UNMAP 1
#define DO_UPCAST(t,m,p) ((t *)(p))
typedef uint64_t hwaddr;
typedef int CoroutineAction;
typedef struct {int token;} Coroutine;
typedef struct {void *stack_ptr,*stack_base,*stack_limit;} emscripten_fiber_t;
typedef union ESP32S3MMUEntry {
    struct {
        uint32_t page_number : 14;
        uint32_t invalid : 1;
        uint32_t type : 1;
        uint32_t reserved : 16;
    };
    uint32_t val;
} ESP32S3MMUEntry;
_Static_assert(sizeof(ESP32S3MMUEntry) == sizeof(uint32_t), "MMU entry layout");

/* ACTUAL_COROUTINE_TYPE */
typedef struct {void *data;} MemoryRegion;
typedef struct {int token;} AddressSpace;
typedef struct {int token;} IOMMUMemoryRegion;
typedef struct {bool encrypted;} Cipher;
typedef struct {int type;struct {AddressSpace *target_as;uint64_t iova,translated_addr,addr_mask;} entry;} IOMMUTLBEvent;
typedef struct {ESP32S3MMUEntry mmu[512];void *flash_blk;MemoryRegion flash_mr;AddressSpace flash_as,psram_as;IOMMUMemoryRegion iommu;Cipher *xts_aes;} ESP32S3CacheState;
typedef struct {bool (*is_flash_enc_enabled)(Cipher *);void (*decrypt)(Cipher *,uint32_t,uint8_t *,size_t);} ESP32S3XtsAesClass;
static _Thread_local struct {unsigned env,sp,heap,base,end,tid,logs,reads,invalidations,decrypts,swaps,sets;uint64_t behavior;} stats;
static _Thread_local const char *flag;
static _Thread_local Coroutine *current;
static void mark(uint64_t n){stats.behavior^=n;stats.behavior*=1099511628211ULL;}
static char *test_getenv(const char *name){assert(!strcmp(name,"M5_WASM_CSTACK_TRACE"));stats.env++;return (char *)flag;}
static uintptr_t emscripten_stack_get_current(void){stats.sp++;return 0x1110;}
static size_t emscripten_get_heap_size(void){stats.heap++;return 0x100000;}
static uintptr_t emscripten_stack_get_base(void){stats.base++;return 0x2100;}
static uintptr_t emscripten_stack_get_end(void){stats.end++;return 0x1100;}
static pthread_t test_pthread_self(void){stats.tid++;return (pthread_t)0x2220;}
static int test_fprintf(FILE *f,const char *fmt,...){stats.logs++;va_list a;va_start(a,fmt);int n=vfprintf(f,fmt,a);va_end(a);return n;}
static void *memory_region_get_ram_ptr(MemoryRegion *mr){return mr->data;}
static void memory_region_notify_iommu(IOMMUMemoryRegion *m,int n,IOMMUTLBEvent e){(void)m;assert(n==0&&e.type==IOMMU_NOTIFIER_UNMAP);stats.invalidations++;mark(0x1001);mark(e.entry.iova);mark(e.entry.translated_addr);mark(e.entry.addr_mask);mark(e.entry.target_as->token);}
static bool encrypted(Cipher *c){return c->encrypted;}
static void decrypt(Cipher *c,uint32_t p,uint8_t *data,size_t n){assert(c->encrypted);stats.decrypts++;mark(0x1003);mark(p);for(size_t i=0;i<n;i++)data[i]^=0xa5;}
static ESP32S3XtsAesClass cipher_class={encrypted,decrypt};
#define ESP32S3_XTS_AES_GET_CLASS(a) (&cipher_class)
static int blk_pread(void *blk,uint32_t p,size_t n,uint8_t *data,int flags){assert(blk&&flags==0&&p/ESP32S3_PAGE_SIZE<16);stats.reads++;mark(0x1002);mark(p);for(size_t i=0;i<n;i++)data[i]=(uint8_t)((p/ESP32S3_PAGE_SIZE)*17+i);return 0;}
static void set_current(Coroutine *co){current=co;stats.sets++;mark(0x2001);mark(co->token);}
static void emscripten_fiber_swap(emscripten_fiber_t *from,emscripten_fiber_t *to){CoroutineEmscripten *f=(void *)((char *)from-offsetof(CoroutineEmscripten,fiber)),*t=(void *)((char *)to-offsetof(CoroutineEmscripten,fiber));stats.swaps++;mark(0x2002);mark(f->base.token);mark(t->base.token);f->action=11;set_current(&f->base);}
#define getenv test_getenv
#define pthread_self test_pthread_self
#define fprintf test_fprintf
/* ACTUAL_FUNCTIONS */
#undef getenv
#undef pthread_self
#undef fprintf

static uint64_t bytes_hash(const void *p,size_t n){uint64_t h=1469598103934665603ULL;const unsigned char *a=p;while(n--){h^=*a++;h*=1099511628211ULL;}return h;}
static void run(const char *thread,const char *mode){
 flag=!strcmp(mode,"unset")?NULL:mode;stats.behavior=1469598103934665603ULL;
 uint8_t *flash=malloc(16*ESP32S3_PAGE_SIZE);assert(flash);memset(flash,0x55,16*ESP32S3_PAGE_SIZE);
 Cipher c={0};ESP32S3CacheState s={.flash_blk=&s,.flash_mr={flash},.flash_as={1},.psram_as={2},.xts_aes=&c};
 for(unsigned i=0;i<512;i++)s.mmu[i].invalid=1;
 const struct {unsigned index,value;bool backend,enc;} cases[]={
 {0,1,true,false},{0,1,true,false},{1,0xffff0002,true,false},
 {1,0x4002,true,false},{1,0xc003,true,false},{1,0x8003,true,false},
 {1,0x0003,true,true},{511,0x000f,true,false},{511,0x400f,true,false},
 {2,0x0004,false,false},{2,0x8005,false,false},{2,0x0006,true,false},
 };
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  s.flash_blk=cases[i].backend?&s:NULL;c.encrypted=cases[i].enc;
  esp32s3_write_mmu_value(&s,cases[i].index*4,cases[i].value);
  printf("BEHAVIOR %s mmu%u val=%08x mirror=%016"PRIx64" tape=%016"PRIx64"\n",thread,i,s.mmu[cases[i].index].val,bytes_hash(flash,16*ESP32S3_PAGE_SIZE),stats.behavior);
 }
 s.flash_blk=&s;c.encrypted=false;
 for(unsigned i=0;i<160;i++)esp32s3_write_mmu_value(&s,12,(i&1)+7);
 CoroutineEmscripten a={.base={1},.action=3,.fiber={(void *)0x1010,(void *)0x3100,(void *)0x2100}},b={.base={2},.action=5,.fiber={(void *)0x2010,(void *)0x4100,(void *)0x3100}};
 for(unsigned i=0;i<150;i++){int r=qemu_coroutine_switch(&a.base,&b.base,(i%3)+1);assert(r==11&&current==&a.base&&b.action==(int)(i%3)+1);}
 /* Both per-thread caches have initialized. A late test-only ENV change must
  * not silently toggle an existing worker; product ENV is startup-only. */
 flag=mode[0]=='1'&&mode[1]=='\0'?"0":"1";
 esp32s3_write_mmu_value(&s,12,10);assert(qemu_coroutine_switch(&a.base,&b.base,7)==11&&b.action==7);
 printf("BEHAVIOR %s final mmu=%016"PRIx64" mirror=%016"PRIx64" tape=%016"PRIx64" reads=%u invalidations=%u decrypts=%u swaps=%u sets=%u\n",thread,bytes_hash(s.mmu,sizeof(s.mmu)),bytes_hash(flash,16*ESP32S3_PAGE_SIZE),stats.behavior,stats.reads,stats.invalidations,stats.decrypts,stats.swaps,stats.sets);
 printf("METRICS %s env=%u sp=%u heap=%u base=%u end=%u tid=%u logs=%u cacheid=%u cachelogs=%u swapid=%u swaplogs=%u\n",thread,stats.env,stats.sp,stats.heap,stats.base,stats.end,stats.tid,stats.logs,m5_cache_write_id,m5_cache_logs,m5_swap_id,m5_swap_logs);
 free(flash);
}
static void *worker(void *mode){run("worker",mode);return NULL;}
int main(int argc,char **argv){assert(argc==2);run("main",argv[1]);pthread_t t;assert(pthread_create(&t,NULL,worker,argv[1])==0);assert(pthread_join(t,NULL)==0);return 0;}
