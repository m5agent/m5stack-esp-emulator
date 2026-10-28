"""Run the exact pinned QR setters against old/new framebuffer regions."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/uiflow2-api/0019-widgets-qrcode-geometry.patch'
FIXTURE = ROOT / 'platform/tests/fixtures/widgets_qrcode_upstream/qrcode_methods.cpp'
STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
using mp_obj_t = void *;
struct mp_obj_base_t {};
struct mp_map_t {};
union mp_arg_val_t { intptr_t u_int; void *u_obj; };
struct mp_arg_t { int name, flags; mp_arg_val_t def; };
#define MP_ARG_OBJ 1
#define MP_ARG_INT 2
#define MP_ARG_REQUIRED 4
#define MP_ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define MP_QSTR_text 1
#define MP_QSTR_w 2
#define MP_QSTR_version 3
#define MP_QSTR_x 4
#define MP_QSTR_y 5
static mp_obj_t mp_const_none=nullptr;
static const char *mp_obj_str_get_str(mp_obj_t x){return (const char *)x;}
static void mp_arg_parse_all(size_t n,const mp_obj_t *args,mp_map_t *,size_t count,const mp_arg_t *,mp_arg_val_t *out){assert(n==count);for(size_t i=0;i<count;i++)out[i].u_int=(intptr_t)args[i];}
struct widgets_pos_t {int x0,y0;};
struct widgets_size_t {int w;};
static uint32_t _bg_color_g=0;
struct LGFX_Device {
 unsigned pixels[120][160]{};unsigned raw=9;int last_x=-1,last_y=-1,last_w=-1,last_version=-1;
 uint32_t getRawColor(){return raw;}
 void setRawColor(uint32_t c){raw=c;}
 void fillRect(int x,int y,int w,int h,uint32_t c){assert(x>=0&&y>=0&&x+w<=160&&y+h<=120);for(int j=y;j<y+h;j++)for(int i=x;i<x+w;i++)pixels[j][i]=c;}
 void qrcode(const char *s,int x,int y,int w,int version){assert(strcmp(s,"PAYLOAD")==0);last_x=x;last_y=y;last_w=w;last_version=version;fillRect(x,y,w,w,1);}
};
'''
MAIN = r'''
int main(int argc,char **argv){
 assert(argc==2);int test=atoi(argv[1]);LGFX_Device gfx;widgets_qrcode_obj_t obj{};
 obj.gfx=&gfx;obj.text="PAYLOAD";obj.pos={40,30};obj.size={40};obj.version=3;
 m5widgets_qrcode_draw_helper(&obj);assert(gfx.raw==9);
 mp_obj_t args[3]={&obj,nullptr,nullptr};int x=40,y=30,w=40;
 switch(test){
 case 0:x=60;y=40;args[1]=(void*)(intptr_t)x;args[2]=(void*)(intptr_t)y;m5widgets_qrcode_setCursor(3,args,nullptr);break;
 case 1:x=100;y=60;args[1]=(void*)(intptr_t)x;args[2]=(void*)(intptr_t)y;m5widgets_qrcode_setCursor(3,args,nullptr);break;
 case 2:w=20;args[1]=(void*)(intptr_t)w;m5widgets_qrcode_setSize(2,args,nullptr);break;
 case 3:w=60;args[1]=(void*)(intptr_t)w;m5widgets_qrcode_setSize(2,args,nullptr);break;
 case 4:args[1]=(void*)(intptr_t)x;args[2]=(void*)(intptr_t)y;m5widgets_qrcode_setCursor(3,args,nullptr);break;
 case 5:args[1]=(void*)(intptr_t)w;m5widgets_qrcode_setSize(2,args,nullptr);break;
 case 6:args[1]=(void*)(intptr_t)4;m5widgets_qrcode_setVersion(2,args,nullptr);break;
 default:return 2;
 }
 assert(obj.pos.x0==x&&obj.pos.y0==y&&obj.size.w==w&&strcmp(obj.text,"PAYLOAD")==0);
 assert(gfx.last_x==x&&gfx.last_y==y&&gfx.last_w==w&&gfx.last_version==(test==6?4:3)&&gfx.raw==9);
 for(int j=0;j<120;j++)for(int i=0;i<160;i++)assert(gfx.pixels[j][i]==unsigned(i>=x&&i<x+w&&j>=y&&j<y+w));
 puts("PASS exact QR setters preserve payload/version and erase old exclusive region");
}
'''


@unittest.skipUnless(shutil.which('c++') and shutil.which('git'), 'C++ compiler and git required')
class WidgetsQrGeometryPatchTests(unittest.TestCase):
    def test_exact_native_setters_before_after_and_stack(self):
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
            text_patch=ROOT/'patches/uiflow2-api/0014-widgets-qrcode-text.patch'
            subprocess.run(['git','apply',str(text_patch)],cwd=root,check=True,capture_output=True)
            stacked=target.read_bytes()
            for label,payload in [('preimage',original),('candidate',candidate),('stacked',stacked)]:
                path=root/(label+'.cpp');binary=root/label;path.write_text(STUBS+payload.decode()+MAIN)
                subprocess.run([shutil.which('c++'),'-std=c++20','-Wall','-Wextra','-Werror','-Wno-unused-function',str(path),'-o',str(binary)],check=True,capture_output=True)
                for case in range(7):
                    with self.subTest(version=label,case=case):
                        result=subprocess.run([str(binary),str(case)],capture_output=True,timeout=5)
                        if label=='preimage' and case in (0,1,2):self.assertNotEqual(result.returncode,0)
                        else:self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__=='__main__':
    unittest.main()
