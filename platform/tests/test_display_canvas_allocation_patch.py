"""Compile the pinned native Canvas constructor with success/failure outcomes."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/uiflow2-api/0020-display-canvas-allocation.patch'
FIXTURE = ROOT / 'platform/tests/fixtures/display_canvas_upstream/gfx_new_canvas.cpp'
STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
using mp_obj_t = void *;
struct mp_map_t {};
union mp_arg_val_t { intptr_t u_int; bool u_bool; };
struct mp_arg_t { int name, flags; mp_arg_val_t def; };
#define MP_ARG_INT 1
#define MP_ARG_BOOL 2
#define MP_ARG_REQUIRED 4
#define MP_ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define MP_QSTR_w 1
#define MP_QSTR_h 2
#define MP_QSTR_bpp 3
#define MP_QSTR_psram 4
#define MP_ERROR_TEXT(x) x
#define MP_OBJ_FROM_PTR(x) ((void *)(x))
static int mp_type_MemoryError;
static int mp_gfxcanvas_type;
static int live=0, wrappers=0;
static bool allocation_succeeds=true;
struct M5Canvas {
 intptr_t width=0,height=0,depth=16;bool psram=false;
 explicit M5Canvas(void *){++live;}
 ~M5Canvas(){--live;}
 void setPsram(bool value){psram=value;}
 void setColorDepth(intptr_t value){depth=value;}
 void *createSprite(int32_t w,int32_t h){width=w;height=h;return allocation_succeeds&&w>0&&h>0?this:nullptr;}
};
struct gfx_obj_t {struct {int *type;} base;M5Canvas *gfx;};
static void *getGfx(const mp_obj_t *args){return args[0];}
static gfx_obj_t *make_wrapper(){++wrappers;return new gfx_obj_t{};}
#define mp_obj_malloc_with_finaliser(type, kind) make_wrapper()
[[noreturn]] static void mp_raise_ValueError(const char *){throw std::invalid_argument("dimension");}
[[noreturn]] static void mp_raise_msg(int *type,const char *){assert(type==&mp_type_MemoryError);throw std::bad_alloc();}
static void mp_arg_parse_all(size_t n,const mp_obj_t *args,mp_map_t *,size_t count,const mp_arg_t *allowed,mp_arg_val_t *out){
 for(size_t i=0;i<count;i++)out[i]=allowed[i].def;
 for(size_t i=0;i<n;i++)out[i].u_int=(intptr_t)args[i];
}
'''
MAIN = r'''
int main(int argc,char **argv){
 assert(argc==2);int test=atoi(argv[1]);
 mp_obj_t args[5]={(void*)1,(void*)(intptr_t)32,(void*)(intptr_t)24,(void*)(intptr_t)8,(void*)(intptr_t)1};
 if(test==0)allocation_succeeds=false;
 if(test==1)args[1]=nullptr;
 if(test==2)args[2]=nullptr;
 if(test==3)args[1]=(void*)(intptr_t)-1;
 if(test==4)args[2]=(void*)(intptr_t)-24;
 if(test==7)args[1]=(void*)(intptr_t)320,args[2]=(void*)(intptr_t)240,allocation_succeeds=false;
 bool expected_invalid=test>=1&&test<=4;
 bool expected_oom=test==0||test==7;
 try{
  auto *obj=(gfx_obj_t*)gfx_newCanvas(test==5?3:5,args,nullptr);
  bool ok=!expected_invalid&&!expected_oom&&live==1&&wrappers==1&&obj->base.type==&mp_gfxcanvas_type&&obj->gfx->width==32&&obj->gfx->height==24&&obj->gfx->depth==(test==5?16:8)&&obj->gfx->psram==(test!=5);
  delete obj->gfx;delete obj;
  return ok&&live==0?0:10;
 }catch(const std::invalid_argument &){return expected_invalid&&live==0&&wrappers==0?0:11;
 }catch(const std::bad_alloc &){return expected_oom&&live==0&&wrappers==0?0:12;}
}
'''


@unittest.skipUnless(shutil.which('c++') and shutil.which('git'), 'C++ compiler and git required')
class DisplayCanvasAllocationPatchTests(unittest.TestCase):
    def test_exact_constructor_before_and_after(self):
        meta=json.loads(PATCH.with_suffix('.json').read_text())
        original=FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),meta['method_fixture_sha256'])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);target=root/meta['path'];target.parent.mkdir(parents=True);target.write_bytes(original)
            subprocess.run(['git','apply','--check',str(PATCH)],cwd=root,check=True,capture_output=True)
            subprocess.run(['git','apply',str(PATCH)],cwd=root,check=True,capture_output=True)
            candidate=target.read_bytes()
            self.assertEqual(hashlib.sha256(candidate).hexdigest(),meta['method_fixture_candidate_sha256'])
            subprocess.run(['git','apply','--reverse','--check',str(PATCH)],cwd=root,check=True,capture_output=True)
            for label,payload in [('preimage',original),('candidate',candidate)]:
                path=root/(label+'.cpp');binary=root/label;path.write_text(STUBS+payload.decode()+MAIN)
                subprocess.run([shutil.which('c++'),'-std=c++20','-Wall','-Wextra','-Werror','-Wno-unused-function',str(path),'-o',str(binary)],check=True,capture_output=True)
                for case in range(8):
                    with self.subTest(version=label,case=case):
                        result=subprocess.run([str(binary),str(case)],capture_output=True,timeout=5)
                        if label=='preimage' and case in (0,1,2,3,4,7):self.assertNotEqual(result.returncode,0)
                        else:self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__=='__main__':
    unittest.main()
