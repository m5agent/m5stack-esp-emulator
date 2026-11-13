"""Replay real panel RDDID and GP-SPI FIFO code; this is host C evidence."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack
from test_gpspi_dma_chunks_patch import STUBS as DMA_STUBS
PATCH = 'patches/qemu-m5stack-peripherals/0186-spi-panel-read-cursor.patch'
SPI = 'hw/m5stopwatch/esp32s3_gpspi.c'
PANEL = 'hw/m5stopwatch/m5_spi_panel.c'
def function(source, name):
    match = re.search(r'(?:static )?(?:void|uint32_t|uint64_t) ' + name + r'\(', source)
    if not match: raise AssertionError(name)
    start = source.index('{', match.start()); depth = 0
    for i in range(start, len(source)):
        depth += (source[i] == '{') - (source[i] == '}')
        if not depth: return source[match.start():i + 1]
    raise AssertionError(name)
STUBS = DMA_STUBS.replace('typedef struct Esp32s3GpspiState {', '''
typedef struct { uint32_t read_id,read_offset; uint8_t cmd; } M5SpiPanelState;
void m5_spi_panel_read(M5SpiPanelState *,uint8_t *,uint32_t);
uint32_t m5_spi_panel_read_id(M5SpiPanelState *);
typedef struct Esp32s3GpspiState {
    M5SpiPanelState *spi_panel; int panel_cs_pin,panel_cs_level,debug_id;
''') + r'''
typedef uint64_t hwaddr;
#define R_CMD 0x00
#define R_DATE 0xf0
#define R_DMA_INT_ST 0x40
#define R_DMA_INT_ENA 0x34
#define CMD_USR (1u<<24)
static uint32_t gpspi_dma_pull(Esp32s3GpspiState *s,uint8_t *data,uint32_t n) {
    (void)s;(void)data;(void)n;assert(!"unexpected DMA TX");return 0;
}
'''
MAIN = r'''
static uint32_t read_word(Esp32s3GpspiState *s,unsigned bits) {
    s->regs[R_USER/4]=USER_MISO;s->regs[R_MS_DLEN/4]=bits-1;
    gpspi_exec(s);return gpspi_read_reg(s,R_W0);
}
int main(int argc,char **argv) {
    assert(argc==2);int which=atoi(argv[1]);
    M5SpiPanelState panel={.read_id=0x00079100,.cmd=4};
    Esp32s3GpspiState s={.spi_panel=&panel,.active_slave=-1,.last_slave=-1,
                        .panel_cs_pin=15,.panel_cs_level=0};
    if(which==0) {
        const uint8_t expected[]={0x00,0x91,0x07,0x00};
        for(unsigned i=0;i<4;i++)assert((read_word(&s,8)&255)==expected[i]);
    } else if(which==1) {
        assert(read_word(&s,32)==0x00079100);
    } else if(which==2) {
        assert(read_word(&s,32)==0x00079100);s.panel_cs_level=1;
        assert(gpspi_read_reg(&s,R_W0)==0x00079100);
        assert(gpspi_read_reg(&s,R_W0)==0x00079100);
        assert((read_word(&s,8)&255)==255);
    } else if(which==3) {
        assert(read_word(&s,0x40000)==0x00079100);assert(panel.read_offset==4);
    } else return 2;
    puts("PASS SPI RDDID and RX FIFO");return 0;
}
'''
@unittest.skipUnless(shutil.which('git') and shutil.which('cc'), 'git and C compiler required')
class SpiPanelReadCursorTests(unittest.TestCase):
    def test_actual_split_read_and_fifo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); subprocess.run(['git','init','-q',str(root)],check=True)
            for patch in bootstrap_stack():
                if patch == PATCH: break
                subprocess.run(['git','apply','--include='+SPI,'--include='+PANEL,str(ROOT/patch)],cwd=root,check=True,capture_output=True)
            before=(root/SPI).read_text()
            subprocess.run(['git','apply','--include='+SPI,'--include='+PANEL,str(ROOT/PATCH)],cwd=root,check=True,capture_output=True)
            after=(root/SPI).read_text();panel=(root/PANEL).read_text()
            for label,source in (('before',before),('after',after)):
                code=STUBS+function(panel,'m5_spi_panel_read')+function(panel,'m5_spi_panel_read_id')
                code+='\n'.join(function(source,n) for n in ('gpspi_active_dma_periph','gpspi_exec','gpspi_read_reg'))+MAIN
                c,binary=root/(label+'.c'),root/label;c.write_text(code)
                result=subprocess.run(['cc','-std=c11','-fsanitize=address',str(c),'-o',str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                for case in range(4):
                    with self.subTest(version=label,case=case):
                        result=subprocess.run([str(binary),str(case)],capture_output=True,text=True)
                        if label=='before' and case in (0,2,3):self.assertNotEqual(result.returncode,0)
                        else:self.assertEqual(result.returncode,0,result.stderr)
