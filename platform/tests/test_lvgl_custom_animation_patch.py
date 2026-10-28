"""Compile the exact LVGL custom-animation functions from the reviewable patch."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/uiflow2-api/0016-lvgl-custom-animation-lookup.patch"

STUBS = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef struct Anim lv_anim_t;
typedef void (*lv_anim_exec_xcb_t)(void *,int);
typedef void (*lv_anim_custom_exec_cb_t)(lv_anim_t *,int);
struct Anim {void *var;lv_anim_exec_xcb_t exec_cb;lv_anim_custom_exec_cb_t custom_exec_cb;lv_anim_t *next;};
static lv_anim_t *head;
static unsigned mutations;
#define anim_ll_p (&head)
#define LV_LL_READ(list,item) for((item)=*(list);(item);(item)=(item)->next)
static lv_anim_t *lv_ll_get_head(lv_anim_t **list){return *list;}
static lv_anim_t *lv_ll_get_next(lv_anim_t **list,lv_anim_t *item){(void)list;return item->next;}
static void remove_anim(void *ptr){lv_anim_t *item=ptr;lv_anim_t **link=&head;while(*link && *link!=item)link=&(*link)->next;assert(*link);*link=item->next;}
static void anim_mark_list_change(void){mutations++;}
static lv_anim_t *lv_anim_get(void *var,lv_anim_exec_xcb_t cb){for(lv_anim_t *a=head;a;a=a->next)if(a->var==var && (!cb || a->exec_cb==cb))return a;return NULL;}
static bool lv_anim_delete(void *var,lv_anim_exec_xcb_t cb){bool result=false;lv_anim_t *a=head;while(a){lv_anim_t *next=a->next;if((!var || a->var==var)&&(!cb || a->exec_cb==cb)){remove_anim(a);result=true;}a=next;}return result;}
static void custom1(lv_anim_t*a,int v){(void)a;(void)v;}
static void custom2(lv_anim_t*a,int v){(void)a;(void)v;}
'''

MAIN = r'''

int main(int argc,char **argv){
 assert(argc==2);int key1=1,key2=2;
 lv_anim_t third={.var=&key2,.custom_exec_cb=custom1};
 lv_anim_t second={.var=&key1,.custom_exec_cb=custom2,.next=&third};
 lv_anim_t first={.var=&key1,.custom_exec_cb=custom1,.next=&second};
 head=&first;
 switch(atoi(argv[1])){
 case 0:assert(lv_anim_custom_get(&first,custom1)==&first);break;
 case 1:assert(lv_anim_custom_get(&first,custom2)==&second);break;
 case 2:assert(lv_anim_custom_delete(&first,custom1));assert(head==&second && second.next==&third && mutations==1);break;
 case 3:assert(lv_anim_custom_delete(NULL,custom1));assert(head==&second && second.next==NULL && mutations==2);break;
 case 4:assert(lv_anim_custom_get(&third,custom2)==NULL && !lv_anim_custom_delete(&third,custom2));break;
 case 5:assert(lv_anim_custom_get(&first,NULL)==&first);assert(lv_anim_custom_delete(NULL,NULL));assert(head==NULL);break;
 default:return 2;
 }
 puts("PASS exact custom callback, variable, wildcard and deletion boundaries");return 0;
}
'''

def functions(before):
    lines = []
    for line in PATCH.read_text().splitlines():
        if line.startswith(("---", "+++", "@@", "diff ")):
            continue
        if line.startswith(" ") or line.startswith("-" if before else "+"):
            lines.append(line[1:])
    source = "\n".join(lines)
    output = []
    for name in ("lv_anim_custom_get", "lv_anim_custom_delete"):
        match = re.search(r"(?:bool|lv_anim_t \*)\s*" + name + r"\(", source)
        if match is None:
            raise AssertionError("exact patched function missing")
        brace = source.index("{", match.start())
        depth = 0
        for index in range(brace, len(source)):
            depth += (source[index] == "{") - (source[index] == "}")
            if depth == 0:
                output.append(source[match.start():index + 1])
                break
    return "\n".join(output)


@unittest.skipUnless(shutil.which("cc"), "C compiler required")
class LvglCustomAnimationPatchTests(unittest.TestCase):
    def test_actual_custom_lookup_delete_and_wildcards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, before in (("preimage", True), ("candidate", False)):
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + functions(before) + MAIN)
                subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", str(path), "-o", str(binary)], check=True, capture_output=True)
                for case in range(6):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, timeout=5)
                        if before and case < 4:
                            self.assertNotEqual(result.returncode, 0, "preimage must fail callback-specific lookup/deletion")
                        else:
                            self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
