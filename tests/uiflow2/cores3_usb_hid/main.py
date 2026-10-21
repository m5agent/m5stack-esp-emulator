import M5
import time
from M5 import *
from module import USBModule
from driver.max3421e import Max3421e


# QEMU's CoreS3 SPI DMA path rejects buffers allocated in PSRAM. Keep the
# official MAX3421E protocol but read the FIFO in stack-sized (<= 4 byte)
# chunks; the manually controlled CS stays asserted between chunks.
def _read_multi_bytes_chunked(self, address, nbytes):
    response = []
    self.cs.off()
    self.spi.write(bytes([address]))
    remaining = nbytes
    while remaining:
        chunk = 4 if remaining > 4 else remaining
        response.extend(self.spi.read(chunk))
        remaining -= chunk
    self.cs.on()
    return response


Max3421e.read_multi_bytes = _read_multi_bytes_chunked


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("CoreS3 USB HID")
d.setCursor(8, 42)
d.print("MAX3421E / HID report probe")

try:
    usb = USBModule(pin_cs=0, pin_int=14)
    for _ in range(500):
        usb.poll_data()
        if usb.is_left_btn_pressed():
            x, y = usb.read_mouse_move()
            if x == 5 and y == -3:
                break
        time.sleep_ms(10)
except Exception as exc:
    # Keep the probe UI static.  The QMP-enumerated/last-report properties
    # below are the authoritative model-level evidence for this test.
    d.setCursor(8, 78)
    d.print(repr(exc)[:48])

while True:
    M5.update()
    time.sleep_ms(100)
