print("CORES3_SD_MAIN")
import M5
from machine import Pin, SDCard


M5.begin()
d = M5.Display
print("CORES3_SD_READY")

try:
    card = SDCard(slot=3, width=1, sck=Pin(36), mosi=Pin(37),
                  miso=Pin(35), cs=Pin(4), freq=1000000)
    expected = bytes((i * 7 + 0x31) & 255 for i in range(512))
    observed = bytearray(512)
    assert card.writeblocks(100, expected)
    assert card.readblocks(100, observed)
    assert bytes(observed) == expected
    card.deinit()
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(6, 14)
    d.print("CoreS3 SPI SD")
    d.fillRect(0, 0, 320, 8, d.COLOR.GREEN)
    print("CORES3_SD_RW_PASS")
    print("CORES3_SD_DRAW_COMPLETE")
except Exception as error:
    print("CORES3_SD_RW_FAIL", repr(error))

while True:
    M5.update()
