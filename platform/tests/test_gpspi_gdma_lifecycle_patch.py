"""Replay real GP-SPI and GDMA register/FSM logic against independent guest RAM.

Only QOM, IRQ, RAM transports and the SPI sink are shimmed. No channel-active,
START/RESTART/STOP/reset or descriptor-cursor implementation is substituted.
This is C controller logic evidence; visible guest and hardware claims are separate.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack
from test_gdma_link_cursor_patch import STUBS as GDMA_STUBS, RAM as GDMA_RAM, function as gdma_function
from test_gpspi_dma_chunks_patch import function as gpspi_function

PATCH = "patches/qemu-m5stack-peripherals/0061-gpspi-gdma-channel-lifecycle.patch"
GDMA = "hw/dma/esp_gdma.c"
HEADER = "include/hw/dma/esp_gdma.h"
GPSPI = "hw/m5stopwatch/esp32s3_gpspi.c"

GLUE = r'''
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define g_realloc realloc
#define ESP32S3_GDMA_CHANNEL_COUNT 5
#define MEMTXATTRS_UNSPECIFIED 0
#define MEMTX_OK 0
#define LOG_GUEST_ERROR 0
#define R_ADDR 0x04
#define R_USER 0x10
#define R_USER1 0x14
#define R_USER2 0x18
#define R_MS_DLEN 0x1c
#define R_DMA_CONF 0x30
#define R_DMA_INT_RAW 0x3c
#define R_W0 0x98
#define USER_MOSI (1u<<27)
#define USER_MISO (1u<<28)
#define USER_ADDR (1u<<30)
#define USER_COMMAND (1u<<31)
#define DMA_TX_ENA (1u<<28)
#define DMA_RX_ENA (1u<<27)
#define INT_TRANS_DONE (1u<<12)
typedef int Object;
typedef int ResetType;
typedef int Co5300State;
typedef int M5SpiPanelState;
typedef int M5EpdPanelState;
typedef int M5SpiSlaveOps;
#define M5_GPSPI_MAX_SLAVES 4
#undef ESP_GDMA
#define ESP_GDMA(obj) ((ESPGdmaState *)(obj))
static void qemu_irq_lower(qemu_irq irq) {(void)irq;}
static unsigned ram_reads;
static int address_space_memory;
static int address_space_read(void *space,uint32_t address,int attrs,void *dst,uint32_t size) {
    assert(space==&address_space_memory && attrs==0);
    ram_reads++;
    return access_ram(address,dst,size,false)?MEMTX_OK:1;
}
static void qemu_log_mask(int mask,const char *message,...) {(void)mask;(void)message;}
'''

SINK = r'''
static uint8_t output[200000];
static unsigned output_size,irq_count;
static void sink(Esp32s3GpspiState *s,const uint8_t *data,uint32_t size,bool command) {
    (void)s;assert(!command && output_size+size<=sizeof(output));
    memcpy(output+output_size,data,size);output_size+=size;
}
static void gpspi_forward_slave(Esp32s3GpspiState *s,const uint8_t *tx,uint32_t size,uint8_t *rx,bool capture) {
    (void)s;(void)tx;(void)size;(void)rx;assert(!capture);
}
static void gpspi_update_irq(Esp32s3GpspiState *s) {assert(s->regs[R_DMA_INT_RAW/4]&INT_TRANS_DONE);irq_count++;}
bool esp_gdma_write_channel(ESPGdmaState *g,uint32_t channel,uint8_t *data,uint32_t count) {
    (void)g;(void)channel;(void)data;(void)count;assert(!"unexpected receive DMA");return false;
}
'''

MAIN = r'''
#define ADDR(offset) (ESP_GDMA_RAM_ADDR+(offset))
static uint8_t pattern(unsigned index) {return (index*29u+(index/251u)*17u)&255;}
static void chain(unsigned head,unsigned data,unsigned total,unsigned capacity,unsigned seed) {
    unsigned count=(total+capacity-1)/capacity;
    assert(capacity<4096 && head+count*12<data && data+total<=sizeof(ram));
    for(unsigned offset=0;offset<total;offset++)ram[data+offset]=pattern(seed+offset);
    for(unsigned index=0,offset=0;index<count;index++) {
        uint32_t size=MIN(capacity,total-offset);
        uint32_t descriptor[3]={size|(size<<12)|1u<<31,ADDR(data+offset),ADDR(head+(index+1)*12)};
        if(index+1==count){descriptor[0]|=1u<<30;descriptor[2]=ADDR(0xf0000);}
        memcpy(ram+head+index*12,descriptor,12);offset+=size;
    }
}
static void command(ESPGdmaState *g,unsigned channel,unsigned bits,unsigned head) {
    esp_gdma_write_chan_conf(g,ESP_GDMA_OUT_IDX,channel,GDMA_LINK_REG,(ADDR(head)&R_GDMA_OUT_LINK_ADDR_MASK)|bits);
}
static void start(ESPGdmaState *g,unsigned channel,unsigned head) {command(g,channel,R_GDMA_OUT_LINK_START_MASK,head);}
static void stop(ESPGdmaState *g,unsigned channel) {command(g,channel,R_GDMA_OUT_LINK_STOP_MASK,0x1000);}
static void restart(ESPGdmaState *g,unsigned channel) {command(g,channel,R_GDMA_OUT_LINK_RESTART_MASK,0x1000);}
static void reset(ESPGdmaState *g,unsigned channel) {
    esp_gdma_write_chan_conf(g,ESP_GDMA_OUT_IDX,channel,GDMA_CONF0_REG,R_GDMA_OUT_CONF0_RST_MASK);
    esp_gdma_write_chan_conf(g,ESP_GDMA_OUT_IDX,channel,GDMA_CONF0_REG,0);
}
static void transfer(Esp32s3GpspiState *s,unsigned size) {
    assert(size && size<=32768);s->regs[R_MS_DLEN/4]=size*8-1;gpspi_exec(s);
}
static void expect(unsigned offset,unsigned size,unsigned seed) {
    for(unsigned index=0;index<size;index++)assert(output[offset+index]==pattern(seed+index));
}
static void no_transfer(Esp32s3GpspiState *s,unsigned bytes) {
    unsigned read_before=ram_reads,output_before=output_size;
    transfer(s,bytes);assert(output_size==output_before && ram_reads==read_before);
}
int main(int argc,char **argv) {
    assert(argc==2);dma_test_class.m_channel_count=2;
    DmaConfigState in[2]={0},out[2]={0};ESPGdmaState g={0};g.ch_conf[0]=in;g.ch_conf[1]=out;
    Esp32s3GpspiState s={.gdma=&g,.gdma_periph=GDMA_SPI2,.active_slave=-1,.last_slave=-1};
    s.regs[R_USER/4]=USER_MOSI;s.regs[R_DMA_CONF/4]=DMA_TX_ENA;
    #if !FIXED_VERSION
    s.dma_reload=true;gpspi_bind_dma(&s,GDMA_SPI2);gpspi_bind_dma(&s,GDMA_SPI3);
    #endif
    esp_gdma_reset_hold((Object *)&g,0);
    esp_gdma_write_chan_conf(&g,ESP_GDMA_OUT_IDX,0,GDMA_PERI_SEL_REG,GDMA_SPI2);
    esp_gdma_write_chan_conf(&g,ESP_GDMA_OUT_IDX,1,GDMA_PERI_SEL_REG,GDMA_SPI3);
    chain(0x1000,0x10000,128,128,11);
    chain(0x3000,0x50000,128,47,100003);
    switch(atoi(argv[1])) {
    case 0: /* A 64800-byte canvas crosses descriptor and SPI transaction boundaries. */
        chain(0x1000,0x10000,64800,4092,0);start(&g,0,0x1000);
        transfer(&s,32032);transfer(&s,32768);assert(output_size==64800);expect(0,64800,0);break;
    case 1: /* Preserve nonzero in-node offsets through arbitrary chunk sizes. */
        chain(0x1000,0x10000,12000,257,31);start(&g,0,0x1000);
        transfer(&s,17);transfer(&s,113);transfer(&s,3000);transfer(&s,4096);transfer(&s,4774);
        assert(output_size==12000);expect(0,12000,31);break;
    case 2: /* Exact review reproducer: STOP denies the second half, including RAM reads. */
        start(&g,0,0x1000);transfer(&s,64);stop(&g,0);no_transfer(&s,64);expect(0,64,11);break;
    case 3: /* CONF0 reset denies reads from the old cached ring. */
        start(&g,0,0x1000);transfer(&s,64);reset(&g,0);no_transfer(&s,64);expect(0,64,11);break;
    case 4: /* STOP does not rewind a legal RESTART inside a descriptor. */
        start(&g,0,0x1000);transfer(&s,64);stop(&g,0);no_transfer(&s,16);restart(&g,0);
        transfer(&s,64);assert(output_size==128);expect(0,128,11);break;
    case 5: /* Reset followed by a new START can re-use the same head safely. */
        start(&g,0,0x1000);transfer(&s,64);reset(&g,0);start(&g,0,0x1000);
        transfer(&s,64);assert(output_size==128);expect(0,64,11);expect(64,64,11);break;
    case 6: /* Every explicit START resets the in-node offset, even at the same head. */
        start(&g,0,0x1000);transfer(&s,64);start(&g,0,0x1000);
        transfer(&s,64);assert(output_size==128);expect(0,64,11);expect(64,64,11);break;
    case 7: /* Two running channels/slaves preserve independent descriptor offsets. */
        s.slaves[0].gdma_periph=GDMA_SPI2;s.slaves[1].gdma_periph=GDMA_SPI3;
        start(&g,0,0x1000);start(&g,1,0x3000);
        s.active_slave=0;transfer(&s,17);s.active_slave=1;transfer(&s,53);
        s.active_slave=0;transfer(&s,111);s.active_slave=1;transfer(&s,75);
        assert(output_size==256);expect(0,17,11);expect(17,53,100003);expect(70,111,28);expect(181,75,100056);break;
    case 8: /* Different CS targets on the same physical channel do not reset it. */
        s.slaves[0].gdma_periph=GDMA_SPI2;s.slaves[1].gdma_periph=GDMA_SPI2;
        start(&g,0,0x1000);s.active_slave=0;transfer(&s,53);s.active_slave=1;transfer(&s,75);
        assert(output_size==128);expect(0,128,11);break;
    case 9: /* An unrelated peripheral START must not rewind an active split transfer. */
        start(&g,0,0x1000);transfer(&s,64);start(&g,1,0x3000);transfer(&s,64);
        assert(output_size==128);expect(0,128,11);break;
    case 10: /* Whole-SoC reset retains a monotonic identity; no old-generation alias. */
        start(&g,0,0x1000);transfer(&s,64);
        #if FIXED_VERSION
        uint64_t before=g.ch_conf[ESP_GDMA_OUT_IDX][0].transfer_generation;
        #endif
        esp_gdma_reset_hold((Object *)&g,0);
        #if FIXED_VERSION
        assert(g.ch_conf[ESP_GDMA_OUT_IDX][0].transfer_generation>before);
        #endif
        esp_gdma_write_chan_conf(&g,ESP_GDMA_OUT_IDX,0,GDMA_PERI_SEL_REG,GDMA_SPI2);
        start(&g,0,0x1000);transfer(&s,64);assert(output_size==128);expect(0,64,11);expect(64,64,11);break;
    case 11: /* A reset destroys the descriptor; RESTART alone cannot resurrect it. */
        start(&g,0,0x1000);transfer(&s,64);reset(&g,0);restart(&g,0);no_transfer(&s,64);break;
    case 12: /* EOF remains exhausted until a new START; nonzero next is not followed. */
        chain(0x1000,0x10000,80,31,53);start(&g,0,0x1000);transfer(&s,80);no_transfer(&s,16);
        assert(output_size==80);expect(0,80,53);break;
    case 13: /* An address-only write preserves the running descriptor and offset. */
        start(&g,0,0x1000);transfer(&s,64);command(&g,0,0,0x3000);transfer(&s,64);
        assert(output_size==128);expect(0,128,11);break;
    case 14: /* IN START cannot reset an OUT cursor. */
        start(&g,0,0x1000);transfer(&s,64);
        esp_gdma_write_chan_conf(&g,ESP_GDMA_IN_IDX,0,GDMA_LINK_REG,R_GDMA_IN_LINK_START_MASK|(ADDR(0x3000)&R_GDMA_IN_LINK_ADDR_MASK));
        transfer(&s,64);assert(output_size==128);expect(0,128,11);break;
    case 15: /* RESTART itself preserves an active nonzero offset. */
        start(&g,0,0x1000);transfer(&s,64);restart(&g,0);transfer(&s,64);
        assert(output_size==128);expect(0,128,11);break;
    case 16: /* STOP/RESTART resumes both the descriptor index and its byte offset. */
        chain(0x1000,0x10000,128,47,181);start(&g,0,0x1000);transfer(&s,64);
        stop(&g,0);no_transfer(&s,16);restart(&g,0);transfer(&s,64);
        assert(output_size==128);expect(0,128,181);break;
    case 17: /* The same peripheral can select another channel while the first pauses. */
        esp_gdma_write_chan_conf(&g,ESP_GDMA_OUT_IDX,1,GDMA_PERI_SEL_REG,GDMA_SPI2);
        start(&g,0,0x1000);start(&g,1,0x3000);transfer(&s,64);
        stop(&g,0);transfer(&s,64);restart(&g,0);transfer(&s,64);
        assert(output_size==192);expect(0,64,11);expect(64,64,100003);expect(128,64,75);break;
    case 18: /* Reset/new START mounts a different ring without an old offset. */
        start(&g,0,0x1000);transfer(&s,64);reset(&g,0);start(&g,0,0x3000);
        transfer(&s,128);assert(output_size==192);expect(0,64,11);expect(64,128,100003);break;
    default:return 2;
    }
    assert(irq_count);free(s.buf);puts("PASS actual GP-SPI + GDMA active/generation/chunk lifecycle");return 0;
}
'''


def struct(source, beginning, ending):
    start = source.index(beginning)
    return source[start:source.index(ending, start) + len(ending)]


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class GpspiGdmaLifecyclePatchTests(unittest.TestCase):
    def test_actual_combined_controllers_before_after(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for name, expected in ((GDMA, "35b8b37e9d5e2cfb045c28de9c42f6cc5c1080c04cd4cff41c730deafa66bc5b"), (HEADER, "f4d82a9f8bb6301791c93b37f5df1ec4012c1546c9b1ccd62e1b807ef67a1300")):
                seed = ROOT / "platform/tests/fixtures/gdma_upstream" / Path(name).name
                self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(), expected)
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(seed.read_bytes())
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                for name in (GDMA, HEADER, GPSPI):
                    subprocess.run(["git", "apply", "--include=" + name, str(ROOT / patch)], cwd=root, check=True, capture_output=True)
            before = {name: (root / name).read_text() for name in (GDMA, HEADER, GPSPI)}
            subprocess.run(["git", "apply", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "apply", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            after = {name: (root / name).read_text() for name in (GDMA, HEADER, GPSPI)}
            subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)], cwd=root, check=True, capture_output=True)
            names = ("esp_gdma_check_interrupt_status", "esp_gdma_set_status", "esp_gdma_clear_status", "esp_gdma_reset_fifo",
                     "esp_gdma_push_descriptor", "esp_gdma_next_list_node", "esp_gdma_get_restart_buffer", "esp_gdma_get_channel_periph",
                     "esp_gdma_set_start_callback", "esp_gdma_complete_out_descriptor", "esp_gdma_complete_in_descriptor",
                     "esp_gdma_check_and_start_mem_transfer", "esp_gdma_write_chan_conf", "esp_gdma_read_chan_register", "esp_gdma_reset_hold")
            for label, sources in (("baseline", before), ("fixed", after)):
                dma, spi = sources[GDMA], sources[GPSPI]
                header = "\n".join(line for line in sources[HEADER].splitlines() if not line.startswith(("#include", "#pragma")))
                descriptor = struct(dma, "typedef struct GdmaLinkedList", "} GdmaLinkedList;")
                ram = GDMA_RAM.replace("ram[0x4000]", "ram[1<<20]").replace("klass", "dma_test_class")
                types = struct(spi, "typedef struct M5GpspiSlave", "} M5GpspiSlave;")
                if label == "fixed":
                    types += struct(spi, "typedef struct M5GpspiDmaCursor", "} M5GpspiDmaCursor;")
                types += "typedef " + struct(spi, "struct Esp32s3GpspiState {", "};").removesuffix(";") + " Esp32s3GpspiState;"
                gp_names = ["gpspi_active_dma_periph"]
                if label == "baseline":
                    gp_names += ["gpspi_dma_start", "gpspi_bind_dma"]
                gp_names += ["gpspi_dma_pull", "gpspi_exec"]
                path, binary = root / (label + ".c"), root / label
                path.write_text(GDMA_STUBS + header + descriptor + ram + GLUE + types + SINK + "\n".join(gdma_function(dma, name) for name in names)
                                + "\n".join(gpspi_function(spi, name) for name in gp_names) + MAIN)
                compiled = subprocess.run([shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-sign-compare", "-DFIXED_VERSION=" + str(int(label == "fixed")), str(path), "-o", str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                for case in range(19):
                    with self.subTest(version=label, case=case):
                        result = subprocess.run([str(binary), str(case)], capture_output=True, text=True, timeout=5)
                        if label == "baseline" and case in (2, 3, 4, 7, 9, 11, 15, 16, 17):
                            self.assertNotEqual(result.returncode, 0, "preimage must fail the independent active-channel/offset oracle")
                        else:
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
