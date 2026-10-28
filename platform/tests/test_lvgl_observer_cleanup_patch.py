"""Exact observer cleanup functions preserve unrelated event subscriptions."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'patches/uiflow2-api/0017-lvgl-observer-object-cleanup.json'
FIXTURE = ROOT / 'platform/tests/fixtures/lvgl_observer_upstream/lv_observer.c'

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
typedef struct Observer lv_observer_t;
typedef struct Subject {lv_observer_t *subs_ll;bool notify_restart_query;} lv_subject_t;
typedef struct Event {void *user_data;} lv_event_t;
typedef void (*Callback)(lv_event_t*);
typedef struct {Callback cb;void *user_data;} lv_event_dsc_t;
typedef struct {unsigned count;lv_event_dsc_t items[16];} EventList;
typedef struct {EventList event_list;} Spec;
typedef struct {Spec *spec_attr;} lv_obj_t;
struct Observer {lv_subject_t *subject;lv_obj_t *target;bool for_obj,auto_free_user_data,freed;void *user_data;lv_observer_t *next;};
#define LV_ASSERT_NULL(x) assert(x)
static void unsubscribe_on_delete_cb(lv_event_t * e);
void lv_observer_remove(lv_observer_t *observer);
static void *lv_event_get_user_data(lv_event_t *e){return e->user_data;}
static lv_observer_t *lv_ll_get_head(lv_observer_t **list){return *list;}
static lv_observer_t *lv_ll_get_next(lv_observer_t **list,lv_observer_t *node){(void)list;return node->next;}
static void lv_ll_remove(lv_observer_t **list,lv_observer_t *node){while(*list && *list!=node)list=&(*list)->next;assert(*list);*list=node->next;}
static void lv_ll_clear(lv_observer_t **list){assert(!*list);}
static void lv_free(void *p){((lv_observer_t*)p)->freed=true;}
static unsigned lv_event_get_count(EventList *list){return list->count;}
static lv_event_dsc_t *lv_obj_get_event_dsc(lv_obj_t *obj,int index){assert(index>=0 && (unsigned)index<obj->spec_attr->event_list.count);return &obj->spec_attr->event_list.items[index];}
static bool lv_obj_remove_event(lv_obj_t *obj,int index){EventList*l=&obj->spec_attr->event_list;if(index<0 || (unsigned)index>=l->count)return false;for(unsigned i=index;i+1<l->count;i++)l->items[i]=l->items[i+1];l->count--;return true;}
static unsigned lv_obj_remove_event_cb_with_user_data(lv_obj_t *obj,Callback cb,void *data){EventList*l=&obj->spec_attr->event_list;unsigned n=0;for(int i=(int)l->count-1;i>=0;i--)if((!cb || l->items[i].cb==cb)&&l->items[i].user_data==data){lv_obj_remove_event(obj,i);n++;}return n;}
static bool lv_obj_remove_event_cb(lv_obj_t *obj,Callback cb){EventList*l=&obj->spec_attr->event_list;for(unsigned i=0;i<l->count;i++)if(l->items[i].cb==cb){lv_obj_remove_event(obj,i);return true;}return false;}
static void other(lv_event_t *e){(void)e;}
static void add(lv_obj_t *obj,Callback cb,void *data){EventList*l=&obj->spec_attr->event_list;assert(l->count<16);l->items[l->count++]=(lv_event_dsc_t){cb,data};}
'''

MAIN = r'''
int main(int argc,char **argv){
 assert(argc==2);Spec spec={0};lv_obj_t obj={&spec};lv_subject_t one={0},two={0};
 lv_observer_t a={.subject=&one,.target=&obj,.for_obj=true};
 lv_observer_t b={.subject=&two,.target=&obj,.for_obj=true};one.subs_ll=&a;two.subs_ll=&b;
 add(&obj,unsubscribe_on_delete_cb,&a);add(&obj,unsubscribe_on_delete_cb,&b);add(&obj,other,&obj);
 switch(atoi(argv[1])){
 case 0:lv_observer_remove(&a);assert(a.freed && !one.subs_ll && spec.event_list.count==2 && spec.event_list.items[0].user_data==&b && spec.event_list.items[1].cb==other);break;
 case 1:lv_subject_deinit(&two);assert(!a.freed && b.freed && spec.event_list.count==2 && spec.event_list.items[0].user_data==&a);break;
 case 2:lv_obj_remove_from_subject(&obj,&one);assert(a.freed && !b.freed && spec.event_list.count==2 && spec.event_list.items[0].user_data==&b && spec.event_list.items[1].cb==other);break;
 case 3:lv_obj_remove_from_subject(&obj,NULL);assert(a.freed && b.freed && spec.event_list.count==1 && spec.event_list.items[0].cb==other);break;
 case 4:{lv_event_t e={&a};unsubscribe_on_delete_cb(&e);assert(a.freed && spec.event_list.count==2 && spec.event_list.items[0].user_data==&b);break;}
 case 5:a.for_obj=false;a.target=NULL;lv_observer_remove(&a);assert(a.freed && !one.subs_ll && spec.event_list.count==3);break;
 default:return 2;
 }
 puts("PASS exact observer cleanup and shared-object subscription boundaries");return 0;
}
'''


def function(source, name):
    match = re.search(r'(?:static )?void ' + name + r'\([^;]*?\)\s*\{', source)
    if match is None:
        raise AssertionError('exact source function missing: ' + name)
    depth = 0
    for i in range(source.index('{', match.start()), len(source)):
        depth += (source[i] == '{') - (source[i] == '}')
        if depth == 0:
            return source[match.start():i + 1]
    raise AssertionError('unclosed function')


@unittest.skipUnless(shutil.which('git') and shutil.which('cc'), 'git and C compiler required')
class LvglObserverCleanupPatchTests(unittest.TestCase):
    def test_exact_cleanup_membership_and_callback_ownership(self):
        manifest = json.loads(MANIFEST.read_text())
        before = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), manifest['preimage_sha256'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / manifest['path']
            source.parent.mkdir(parents=True)
            source.write_bytes(before)
            patch = MANIFEST.with_suffix('.patch')
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=root, check=True, capture_output=True)
            after = source.read_bytes()
            self.assertEqual(hashlib.sha256(after).hexdigest(), manifest['candidate_sha256'])
            subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=root, check=True, capture_output=True)
            for label, data in (('preimage', before), ('candidate', after)):
                text = data.decode()
                path, binary = root / (label + '.c'), root / label
                path.write_text(STUBS + '\n'.join(function(text, name) for name in ('lv_subject_deinit', 'lv_observer_remove', 'lv_obj_remove_from_subject', 'unsubscribe_on_delete_cb')) + MAIN)
                subprocess.run([shutil.which('cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', str(path), '-o', str(binary)], check=True, capture_output=True)
                for case in range(6):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, timeout=5)
                        if label == 'preimage' and case in (0, 1, 4):
                            self.assertNotEqual(result.returncode, 0)
                        else:
                            self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
