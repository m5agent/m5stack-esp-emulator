"""Replay native DPORT cache synchronization against observable C memory shims."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack
from test_unit_flashlight_route_patch import function

PATCH = 'patches/qemu-m5stack-peripherals/0193-classic-cache-dirty-sync.patch'
SOURCE = 'hw/misc/esp32_dport.c'
HEADER = 'include/hw/misc/esp32_dport.h'
FIXTURE = ROOT / 'platform/tests/fixtures/classic_cache_upstream'

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MiB (1024*1024)
#define MMU_ENTRY_MASK 0x1ff
#define ESP32_CPU_COUNT 2
typedef uint64_t hwaddr;
typedef int SysBusDevice;
typedef int qemu_irq;
typedef struct {uint8_t *data;unsigned reads;} BlockBackend;
typedef struct {bool enabled;uint8_t *data;uint64_t offset;} MemoryRegion;
typedef int Esp32FlashEncryptionState;
static Esp32FlashEncryptionState encryption;
static bool decrypt;
static unsigned flushes,decrypt_calls,ready[2];
static unsigned transaction_depth,topology_commits;
static bool topology_dirty;
static Esp32FlashEncryptionState *esp32_flash_encryption_find(void){return &encryption;}
static bool esp32_flash_decryption_enabled(Esp32FlashEncryptionState *e){return decrypt;}
static void *memory_region_get_ram_ptr(MemoryRegion *m){return m->data;}
static void changed_topology(void){if(transaction_depth)topology_dirty=true;else topology_commits++;}
static void memory_region_transaction_begin(void){transaction_depth++;}
static void memory_region_transaction_commit(void){assert(transaction_depth);if(!--transaction_depth && topology_dirty){topology_commits++;topology_dirty=false;}}
static void memory_region_set_enabled(MemoryRegion *m,bool enabled){if(m->enabled!=enabled){m->enabled=enabled;changed_topology();}}
static void memory_region_set_alias_offset(MemoryRegion *m,uint64_t offset){if(m->offset!=offset){m->offset=offset;changed_topology();}}
static void qemu_set_irq(qemu_irq irq,bool level){assert(irq<2 && !transaction_depth);ready[irq]=level;}
static int blk_pread(BlockBackend *b,uint32_t off,uint32_t n,void *to,int flags){
 assert((uint64_t)off+n<=16*MiB);b->reads++;memcpy(to,b->data+off,n);return 0;
}
static void esp32_flash_decrypt_inplace(Esp32FlashEncryptionState *e,uint32_t off,uint32_t *data,uint32_t words){
 decrypt_calls++;for(unsigned i=0;i<words;i++)data[i]^=0xa5a5a5a5;
}
static void memory_region_flush_rom_device(MemoryRegion *m,uint64_t off,uint64_t n){
 assert(off==0 && n==4*MiB);flushes++;
}
#define FIELD_EX32(v,reg,field) (((v)>>reg##_##field##_SHIFT)&1)
#define DPORT_PRO_CACHE_CTRL_CACHE_ENA_SHIFT 3
#define DPORT_PRO_CACHE_CTRL_CACHE_FLUSH_ENA_SHIFT 4
#define DPORT_PRO_CACHE_CTRL1_MASK_DROM0_SHIFT 4
#define DPORT_PRO_CACHE_CTRL1_MASK_IRAM0_SHIFT 0
#define DPORT_PRO_CACHE_CTRL1_MASK_DRAM1_SHIFT 3
#define R_DPORT_PRO_CACHE_CTRL_CACHE_FLUSH_DONE_MASK (1U<<5)
#define R_DPORT_PRO_CACHE_CTRL_CACHE_FLUSH_ENA_MASK (1U<<4)
#define A_DPORT_PRO_CACHE_CTRL 0x40
'''

CASES = r'''
static Esp32DportState *fresh(void) {
 Esp32DportState *d=calloc(1,sizeof(*d));assert(d);d->has_psram=true;d->psram_size_mib=4;
 d->psram.data=calloc(1,4*MiB);d->flash_blk=calloc(1,sizeof(BlockBackend));
 d->flash_blk->data=malloc(16*MiB);assert(d->psram.data && d->flash_blk->data);
 for(unsigned i=0;i<16*MiB;i++)d->flash_blk->data[i]=(i/65536)^0x59;
 for(unsigned c=0;c<2;c++) {
  Esp32CacheState *s=&d->cache_state[c];s->dport=d;s->core_id=c;d->cache_ready[c]=c;
  Esp32CacheRegionState *regions[]={&s->drom0,&s->iram0,&s->dram1};
  for(unsigned r=0;r<3;r++) {regions[r]->cache=s;regions[r]->illegal_access_retval=0xbad00bad;
   regions[r]->mem.data=r==2?d->psram.data:calloc(1,4*MiB);
   for(unsigned i=0;i<64;i++)regions[r]->mmu_table[i]=i;
  }
 }
 flushes=decrypt_calls=transaction_depth=topology_commits=0;topology_dirty=false;decrypt=false;return d;
}
static void destroy(Esp32DportState *d){
 for(unsigned c=0;c<2;c++){free(d->cache_state[c].drom0.mem.data);free(d->cache_state[c].iram0.mem.data);}
 free(d->psram.data);free(d->flash_blk->data);free(d->flash_blk);free(d);
}
static void clean_enable(void){
 Esp32DportState *d=fresh();Esp32CacheState *s=&d->cache_state[0];
 memset(s->iram0.mem.data,0x64,4*MiB);
 for(unsigned i=0;i<8;i++) {s->cache_ctrl_reg=0;esp32_cache_state_update(s);assert(!ready[0] && !s->dram1.mem.enabled);
  s->cache_ctrl_reg=8;esp32_cache_state_update(s);assert(ready[0] && s->dram1.mem.enabled);}
 assert(d->flash_blk->reads==0 && s->iram0.mem.data[17]==0x64);
 assert(topology_commits==(OLD_SYNC?45:15) && !transaction_depth);
 assert(flushes==(OLD_SYNC?16:0));destroy(d);
 puts(OLD_SYNC?"clean-enable-repeated-full-region-flush-negative PASS":"clean-enable-no-ROM-write-or-flush PASS");
}
static void remap_and_flush(void){
 Esp32DportState *d=fresh();Esp32CacheState *s=&d->cache_state[0];
 set_mmu_entry(&s->drom0,0,4,7);esp32_cache_data_sync(&s->drom0);
 assert(d->flash_blk->reads==1 && flushes==1 && s->drom0.mmu_table[1]==7);
 assert(s->drom0.mem.data[65536]==(7^0x59));
 unsigned f=flushes;set_mmu_entry(&s->drom0,0,4,7);esp32_cache_data_sync(&s->drom0);
 assert(d->flash_blk->reads==1 && flushes==f+(OLD_SYNC?1:0));
 set_mmu_entry(&s->drom0,0,4,ESP32_CACHE_MMU_INVALID_VAL);esp32_cache_data_sync(&s->drom0);
 assert(d->flash_blk->reads==1 && ((uint32_t*)s->drom0.mem.data)[65536/4]==0xbad00bad);
 set_mmu_entry(&s->drom0,0,4,7);esp32_cache_data_sync(&s->drom0);
 d->flash_blk->data[7*65536]=0x42;
 /* Clean cache remains unchanged until the real register flush request. */
 esp32_cache_data_sync(&s->drom0);assert(s->drom0.mem.data[65536]==(7^0x59));
 unsigned reads=d->flash_blk->reads;f=flushes;
 cache_control_write(d,A_DPORT_PRO_CACHE_CTRL,16,4);
 assert(d->flash_blk->reads==reads+128 && flushes==f+2);
 assert(s->drom0.mem.data[65536]==0x42 && (s->cache_ctrl_reg&32) && !(s->cache_ctrl_reg&16));
 decrypt=true;set_mmu_entry(&s->drom0,0,4,8);esp32_cache_data_sync(&s->drom0);
 assert(decrypt_calls==1 && s->drom0.mem.data[65536]==(8^0x59^0xa5));
 destroy(d);puts("MMU-remap-invalid-page-explicit-flush-new-bytes-decrypt-path PASS");
}
static void psram_alias_and_gate(void){
 Esp32DportState *d=fresh();
 for(unsigned c=0;c<2;c++) {
  Esp32CacheState *s=&d->cache_state[c];esp32_cache_psram_set_mapping(&s->dram1,2,5);
  s->cache_ctrl_reg=8;esp32_cache_state_update(s);
  assert(s->dram1.mem.enabled && s->dram1.psram_page_mem[2].enabled);
 }
 Esp32CacheState *a=&d->cache_state[0],*b=&d->cache_state[1];
 uint64_t offset=a->dram1.psram_page_mem[2].offset;assert(offset==5*32768);
 /* QEMU aliases share the same RAM: cache gating must not copy stale ROM
  * bytes over an external-RAM write, including a write by the other CPU. */
 d->psram.data[offset+9]=0x71;a->cache_ctrl_reg=0;esp32_cache_state_update(a);
 assert(!a->dram1.mem.enabled && b->dram1.mem.enabled);
 d->psram.data[b->dram1.psram_page_mem[2].offset+9]=0x82;
 a->cache_ctrl_reg=8;esp32_cache_state_update(a);assert(d->psram.data[offset+9]==0x82);
 a->cache_ctrl1_reg=8;esp32_cache_state_update(a);assert(!a->dram1.mem.enabled && a->iram0.mem.enabled);
 esp32_cache_psram_set_mapping(&a->dram1,2,ESP32_CACHE_MMU_INVALID_VAL);
 assert(!a->dram1.psram_page_mem[2].enabled && a->dram1.psram_page_ill[2].enabled);
 assert(d->flash_blk->reads==0);destroy(d);puts("PSRAM-shared-writes-survive-cache-gates-and-invalid-map PASS");
}
int main(void){clean_enable();remap_and_flush();psram_alias_and_gate();return 0;}
'''


@unittest.skipUnless(shutil.which('cc'), 'C compiler required')
class ClassicCacheDirtySyncTests(unittest.TestCase):
    def test_full_native_prefix_replay_and_cache_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            for name in (SOURCE, HEADER):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                data = (FIXTURE / Path(name).name).read_bytes()
                expected = ('f0a0c8cfc88d01eb86319132c6636474155c66b547a9a2a2f374c78074e9eeeb'
                            if name == SOURCE else '74997ff8cad53481d69ffb0fb59454037ee89a20b9587b0a2074b66d93844ecd')
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                p.write_bytes(data)
            for patch in bootstrap_stack(full=True):
                if patch == PATCH:
                    break
                subprocess.run(['git', 'apply', '--include=' + SOURCE, '--include=' + HEADER,
                                str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(['git', 'apply', '--check', str(ROOT / PATCH)], cwd=root, check=True)
            subprocess.run(['git', 'apply', str(ROOT / PATCH)], cwd=root, check=True)
            after = (root / SOURCE).read_text()
            header = (root / HEADER).read_text()
            declarations = header[header.index('typedef struct Esp32DportState Esp32DportState;'):header.index('void esp32_dport_clear_ill_trap_state')]
            for old, source in ((True, before), (False, after)):
                funcs = '\n'.join(function(source, name) for name in (
                    'set_mmu_entry', 'esp32_cache_psram_set_mapping', 'esp32_cache_data_sync',
                    'esp32_cache_invalidate_all_entries', 'esp32_cache_state_update'))
                write = function(source, 'esp32_dport_write')
                case = write[write.index('    case A_DPORT_PRO_CACHE_CTRL:'):write.index('    case A_DPORT_PRO_CACHE_CTRL1:')]
                register = 'static void cache_control_write(Esp32DportState *s,hwaddr addr,uint64_t value,unsigned size){uint32_t old_val;switch(addr){' + case + 'default:abort();}}'
                c = root / 'test.c'
                c.write_text('#define OLD_SYNC ' + str(int(old)) + '\n' + STUBS + declarations + funcs + register + CASES)
                binary = root / 'test'
                compiled = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-Wno-unused-parameter', '-Wno-sign-compare', '-fsanitize=address,undefined',
                    str(c), '-o', str(binary)], capture_output=True, text=True)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                ran = subprocess.run([str(binary)], capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertIn('PSRAM-shared-writes', ran.stdout)
            subprocess.run(['git', 'apply', '--reverse', str(ROOT / PATCH)], cwd=root, check=True)
            self.assertEqual((root / SOURCE).read_text(), before)


if __name__ == '__main__':
    unittest.main()
