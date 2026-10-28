"""Actual LCD_CAM C data path with independent sensor-wire/field oracles."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_camera_dma_chunk_patch import STUBS as DMA_STUBS, function
from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack

PATCH = "patches/qemu-m5stack-peripherals/0059-lcd-cam-dvp-wire-order.patch"
SOURCE = "hw/m5stopwatch/m5_lcd_cam.c"
STUBS = DMA_STUBS.replace("uint32_t width,height", "uint32_t regs[64];\n    uint32_t width,height") + r'''
#define R_CAM_CTRL 4
#define R_CAM_CTRL1 8
#define R_CAM_RGB 12
#define CAM_BIT_ORDER (1u<<6)
#define CAM_2BYTE_EN (1u<<24)
#define CAM_CONV_ENABLE (1u<<31)
#define LOG_GUEST_ERROR 1
static unsigned guest_errors;
#define qemu_log_mask(mask,...) ((void)(mask),guest_errors++)
'''
MAIN = r'''
int main(int argc,char **argv) {
    assert(argc==2);unsigned test=atoi(argv[1]);
    M5LcdCamState s={.gdma=&s,.capture_timer=&s,.width=320,.height=240,
        .frame_bytes=153600,.chunk_len=15360,.chunks_left=10,
        .int_ena=CAM_VSYNC_INT,.started=true};
    uint8_t data[6]={0};s.frame_offset=(3*320+3)*2;
    if(test<=2) {
        if(test==1)s.regs[1]=1u<<5; /* BYTE_ORDER is ignored on an 8-bit bus. */
        if(test==2)s.regs[1]=1u<<6; /* BIT_ORDER reverses each 8-bit sample. */
        lcd_cam_fill_frame(&s,data,6);
        for(unsigned i=0;i<6;i++)assert(data[i]==(test==2?(i&1?0x61:0x97):(i&1?0x86:0xe9)));
    }else if(test==3 || test==7) {
        uint8_t *wire=calloc(1,153600);assert(wire);
        wire[0]=0xe9;wire[1]=0x86;wire[2]=0x12;wire[3]=0x34;wire[4]=0x56;wire[5]=0x78;
        s.frame_data=wire;s.frame_data_size=153600;s.frame_offset=1;
        if(test==3)s.regs[1]=1u<<6;
        lcd_cam_fill_frame(&s,data,5);
        const uint8_t original[]={0x86,0x12,0x34,0x56,0x78};
        const uint8_t reversed[]={0x61,0x48,0x2c,0x6a,0x1e};
        assert(!memcmp(data,test==3?reversed:original,5));assert(s.frame_offset==6);
        free(wire);
    }else if(test==4 || test==5) {
        s.frame_offset=0;
        if(test==4)s.regs[2]=1u<<24;else s.regs[3]=1u<<31;
        lcd_cam_capture(&s);
        assert(output_size==0 && descriptor_calls==0 && vsyncs==0 && guest_errors==1 && s.frame_offset==0);
    }else if(test==6) {
        s.frame_offset=153599;lcd_cam_fill_frame(&s,data,3);
        assert(data[0]==0x5d && data[1]==0xf7 && data[2]==0xbe && s.frame_offset==2);
    }else if(test==8) {
        s.frame_offset=0;
        for(unsigned n=0;n<10;n++){pending=false;now+=2;lcd_cam_capture(&s);}
        assert(output_size==153600 && descriptor_calls==40);
        const uint16_t bands[]={0xe986,0xede4,0x2dea,0x235d};
        for(unsigned y=0;y<240;y++)for(unsigned x=0;x<320;x++) {
            uint16_t color=(x%40<2 || y%40<2)?0xf7be:bands[y/60];
            unsigned offset=(y*320+x)*2;
            assert(output[offset]==(color>>8) && output[offset+1]==(color&255));
        }
    }else return 2;
    puts("PASS actual LCD_CAM 8-bit DVP wire/bit-order/unsupported-mode boundary");return 0;
}
'''


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class CameraDvpOrderPatchTests(unittest.TestCase):
    def test_actual_sensor_wire_order_and_controller_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                subprocess.run(["git", "apply", "--include=" + SOURCE, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = (root / SOURCE).read_text()
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            for label, source in (("baseline", before), ("fixed", after)):
                path, binary = root / (label + ".c"), root / label
                path.write_text(STUBS + "\n".join(function(source, name) for name in ("camera_pattern_pixel", "lcd_cam_fill_frame", "lcd_cam_capture")) + MAIN)
                result = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                for case in range(9):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "fixed" or case == 7:
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        else:
                            self.assertNotEqual(result.returncode, 0, "preimage must fail the new wire/field oracle")


if __name__ == "__main__":
    unittest.main()
