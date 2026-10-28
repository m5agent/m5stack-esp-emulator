"""Execute the complete pinned LVGL cache-entry source before/after patch 0018."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "platform/tests/fixtures/lvgl_cache_entry_upstream/lv_cache_entry.c"
PATCH = ROOT / "patches/uiflow2-api/0018-lvgl-cache-entry-allocation.patch"
META = PATCH.with_suffix(".json")

STUBS = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef struct { unsigned nonce; } lv_cache_t;
typedef struct _lv_cache_entry_t lv_cache_entry_t;
static void *allocation;
static size_t requested;
static unsigned freed;
static bool fail_allocation;
static void *lv_malloc_zeroed(size_t n) {
    requested=n;
    if(fail_allocation) return NULL;
    assert(allocation==NULL);
    allocation=calloc(1,n);
    assert(allocation);
    return allocation;
}
static void lv_free(void *p) {
    assert(p==allocation); /* A shifted pointer must never reach the allocator. */
    free(p); allocation=NULL; freed++;
}
#define LV_ASSERT_NULL(p) assert((p)!=NULL)
#define LV_ASSERT_MALLOC(p) ((void)(p));
#define LV_UNUSED(x) ((void)(x))
#define LV_LOG_WARN(...) ((void)0)
#define LV_LOG_ERROR(...) ((void)0)
void lv_cache_entry_init(lv_cache_entry_t *,const lv_cache_t *,const uint32_t);
'''

MAIN = r'''
int main(int argc,char **argv) {
    assert(argc==3);
    const unsigned test=(unsigned)atoi(argv[1]);
    const uint32_t n=(uint32_t)atoi(argv[2]);
    lv_cache_t cache={0x7ca5e},other={0x18};
    if(test==6) {
        fail_allocation=true;
        assert(lv_cache_entry_alloc(n,&cache)==NULL);
        assert(requested==lv_cache_entry_get_size(n) && freed==0);
        puts("PASS allocation failure returns NULL");
        return 0;
    }
    lv_cache_entry_t *e=lv_cache_entry_alloc(n,&cache);
    assert(e && requested==n+sizeof(*e));
    assert((uint8_t *)e==(uint8_t *)allocation+n);
    switch(test) {
    case 0:
        assert(lv_cache_entry_get_node_size(e)==n);
        assert(lv_cache_entry_get_ref(e)==0);
        assert(lv_cache_entry_get_cache(e)==&cache);
        assert(!lv_cache_entry_is_invalid(e));
        break;
    case 1:
        assert(lv_cache_entry_get_data(e)==allocation);
        assert(lv_cache_entry_get_entry(allocation,n)==e);
        break;
    case 2:
        for(unsigned i=0;i<n;i++) assert(((uint8_t *)allocation)[i]==0);
        break;
    case 3:
        /* Write the owned payload directly, without repairing returned fields. */
        memset(allocation,0xa5,n);
        assert(lv_cache_entry_get_cache(e)==&cache);
        assert(lv_cache_entry_get_node_size(e)==n);
        assert(lv_cache_entry_get_ref(e)==0);
        assert(!lv_cache_entry_is_invalid(e));
        assert(lv_cache_entry_get_data(e)==allocation);
        break;
    case 4:
        assert(lv_cache_entry_acquire_data(e)==allocation);
        assert(lv_cache_entry_get_ref(e)==1);
        lv_cache_entry_inc_ref(e);
        assert(lv_cache_entry_get_ref(e)==2);
        lv_cache_entry_release_data(e,NULL);
        assert(lv_cache_entry_get_ref(e)==1);
        lv_cache_entry_dec_ref(e);
        lv_cache_entry_dec_ref(e); /* Existing underflow clamp is preserved. */
        assert(lv_cache_entry_get_ref(e)==0);
        lv_cache_entry_inc_ref(e);
        lv_cache_entry_reset_ref(e);
        assert(lv_cache_entry_get_ref(e)==0);
        lv_cache_entry_release_data(e,NULL);
        assert(lv_cache_entry_get_ref(e)==0);
        lv_cache_entry_set_invalid(e,true);
        assert(lv_cache_entry_is_invalid(e));
        lv_cache_entry_set_cache(e,&other);
        assert(lv_cache_entry_get_cache(e)==&other);
        lv_cache_entry_set_node_size(e,n);
        assert(lv_cache_entry_get_node_size(e)==n);
        break;
    case 5:
        lv_cache_entry_delete(e);
        assert(allocation==NULL && freed==1);
        puts("PASS free uses the original allocation base exactly once");
        return 0;
    default: return 2;
    }
    /* Test-specific assertions precede cleanup, so a failure stays diagnostic. */
    lv_cache_entry_delete(e);
    assert(allocation==NULL && freed==1);
    puts("PASS unmodified native metadata, payload, pointer, reference and free contracts");
    return 0;
}
'''


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class LvglCacheEntryPatchTests(unittest.TestCase):
    def test_complete_pinned_source_before_after(self):
        metadata = json.loads(META.read_text())
        source = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), metadata["preimage_sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / metadata["path"]
            target.parent.mkdir(parents=True)
            target.write_bytes(source)
            subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True, capture_output=True)
            candidate = target.read_bytes()
            self.assertEqual(hashlib.sha256(candidate).hexdigest(), metadata["candidate_sha256"])
            for label, payload in (("preimage", source), ("candidate", candidate)):
                # Only includes are substituted. Private struct and all actual
                # upstream functions remain byte-for-byte intact in the body.
                body = re.sub(r"^#include[^\n]*$", "", payload.decode(), flags=re.MULTILINE)
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + body + MAIN)
                subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)], check=True, capture_output=True)
                for size in (0, 16, 32, 64):
                    for case in range(7):
                        with self.subTest(version=label, payload=size, case=case):
                            result = subprocess.run([str(binary), str(case), str(size)], capture_output=True, timeout=5)
                            if label == "preimage" and size and case < 6:
                                self.assertNotEqual(result.returncode, 0, "unaltered preimage must fail without a manual init repair")
                            else:
                                self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
