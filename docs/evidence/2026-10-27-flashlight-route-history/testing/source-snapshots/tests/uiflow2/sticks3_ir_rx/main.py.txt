import M5
import time
from M5 import *
from hardware import IR


log = None
received = {
    "count": 0,
    "address": -1,
    "command": -1,
}


def emit(message):
    print(message)
    if log:
        log.write(message + "\n")


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    if received["count"]:
        d.fillRect(0, 0, 135, 10, d.COLOR.GREEN)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(6, 8)
    d.print("StickS3 IR RX")
    d.setCursor(6, 40)
    d.print("count=%d" % received["count"])
    d.setCursor(6, 60)
    d.print("addr=%d cmd=%d"
            % (received["address"], received["command"]))
    d.setCursor(6, 90)
    d.print("waiting for NEC...")


def ir_rx(data, address, control):
    received["count"] += 1
    received["address"] = address
    received["command"] = data
    draw()
    emit("STICKS3_IR_RX addr=%d data=%d ctrl=%d"
         % (address, data, control))


M5.begin()
draw()
try:
    from hardware import UART
    log = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log = None

status = "init"
try:
    Power.setExtOutput(True)
    Speaker.setPA(False)
    ir = IR()
    ir.rx_cb(ir_rx)
    status = "listening"
except Exception as exc:
    status = "error"
    emit("STICKS3_IR_RX_ERROR " + repr(exc))

display = M5.Display
display.setCursor(6, 110)
display.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(20)
