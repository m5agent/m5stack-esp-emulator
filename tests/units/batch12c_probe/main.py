"""Batch-12c guest probes: Chain x2, Cat1-CN, mini-imu-pro."""
import time, sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)
MARKER = "BATCH12C_PROBE_READY"
def print(*p): _console.write(" ".join(str(x) for x in p) + "\n")
def wait_ms(ms):
    start=time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update(); time.sleep_ms(10)
def show(screen,text):
    screen.setCursor(6,42); screen.print(str(text))
def frame(index, cmd, data=b""):
    length=len(data)+3; total=length+6
    crc=index+cmd
    for b in data: crc+=b
    return bytes([0xAA,0x55,length&0xFF,(length>>8)&0xFF,index,cmd])+bytes(data)+bytes([crc&0xFF,0x55,0xAA])
print("BATCH12C_PROBE_START", CASE)
M5.begin(); screen=M5.Display
if DEVICE_ID=="cores3": screen.setRotation(1)
screen.setBrightness(255); screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB,0xFFFFFF); screen.setTextSize(2); screen.setCursor(6,6)
screen.print("Batch12c Unit: "+CASE)
def make_bus(): return I2C(0,scl=Pin(WHITE),sda=Pin(YELLOW),freq=100000)

if CASE in ("8servos2-chain","chainbus"):
    from machine import UART as MUART
    uart=MUART(1,tx=YELLOW,rx=WHITE,baudrate=115200,rxbuf=512)
    print("CHAIN_DRIVER raw-UART driver-gap")
    print(MARKER,CASE); wait_ms(300)
    def tx(index,cmd,data=b"",label=""):
        while uart.any():
            uart.read()
        req=frame(index,cmd,data)
        uart.write(req)
        buf=b""
        deadline=time.ticks_add(time.ticks_ms(),1000)
        while time.ticks_diff(deadline,time.ticks_ms())>0:
            if uart.any(): buf += uart.read()
            if len(buf)>=9 and buf[0]==0xAA and buf[1]==0x55:
                length=buf[2] | (buf[3]<<8); total=length+6
                if len(buf)>=total: break
            wait_ms(20)
        print("CHAIN_RESP",label,buf.hex())
    try:
        if CASE=="8servos2-chain":
            tx(1,0x10,bytes([0,4]),"set_mode_ch0_4")
            tx(1,0x13,b"","get_modes")
            tx(1,0x60,bytes([0,90]),"set_angle_ch0_90")
            tx(1,0x63,b"","get_angles")
            tx(1,0x51,b"","get_adc8")
            tx(1,0x74,bytes([0,0x11,0x22,0x33]),"set_rgb_ch0")
            tx(1,0x77,b"","get_rgb8")
            tx(1,0xa3,b"","get_current")
        else:
            tx(1,0xfb,b"","get_device_type")
            tx(1,0x11,bytes([0x00,0x00]),"i2c_forward_fail_closed")
            tx(1,0x22,bytes([55]),"set_brightness_55")
            tx(1,0x23,b"","get_brightness")
            tx(1,0x31,bytes([1,1]),"set_gpio1_high")
            tx(1,0x32,bytes([1]),"get_gpio1")
            tx(1,0x41,bytes([1]),"get_gpio_in1")
            tx(1,0x61,bytes([1]),"get_adc1")
            tx(1,0x70,b"","get_work_status")
        show(screen,CASE)
    except Exception as e:
        import io; t=io.StringIO(); sys.print_exception(e,t); print("CHAIN_ERROR",t.getvalue().replace("\n"," | "))
    print("CHAIN_END")

elif CASE=="cat1-cn":
    from machine import UART as MUART
    uart=MUART(1,tx=YELLOW,rx=WHITE,baudrate=115200,rxbuf=512)
    print("CAT1_DRIVER raw-UART driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        for cmd in (b"AT\r\n",b"ATE0\r\n",b"AT+CPIN?\r\n",b"AT+CREG?\r\n",b"AT+CSQ\r\n",b"AT+CGSN\r\n",b"AT+CGMM\r\n"):
            uart.write(cmd); time.sleep(0.3)
            data=uart.read() or b""
            print("CAT1_RESP",cmd.strip().decode(),(data or b"").hex())
        show(screen,"cat1-cn")
    except Exception as e:
        import io; t=io.StringIO(); sys.print_exception(e,t); print("CAT1_ERROR",t.getvalue().replace("\n"," | "))
    print("CAT1_END")

elif CASE=="mini-imu-pro":
    from driver.bmi270_bmm150 import BMI270
    from driver.bmp280 import BMP280
    bus=make_bus()
    try:
        imu=BMI270(bus, address=0x68)
        bmp=BMP280(bus)
    except Exception as e:
        import io; t=io.StringIO(); sys.print_exception(e,t); print("IMU_INIT_ERROR",t.getvalue().replace("\n"," | ")); raise
    print(MARKER,CASE); wait_ms(300)
    try:
        print("IMU_ACCEL",imu.accel())
        print("IMU_GYRO",imu.gyro())
        print("IMU_TEMP",imu.temperature())
        t,p=bmp.measure(); print("BMP280_MEASURE",t,p)
        show(screen,"mini-imu-pro")
    except Exception as e:
        import io; t=io.StringIO(); sys.print_exception(e,t); print("IMU_ERROR",t.getvalue().replace("\n"," | "))
    print("IMU_END")

elif CASE=="mini-bps-v11":
    # Optional address-ambiguity probe: no model exists; raw guest scan evidence.
    bus=make_bus()
    print("BPS_DRIVER raw-I2C driver-gap")
    print(MARKER,CASE); wait_ms(300)
    try:
        print("BPS_SCAN",bus.scan())
        for addr in (0x56,0x70):
            try:
                bus.writeto(addr,bytes([0x00]))
                data=bus.readfrom(addr,1)
                print("BPS_READ",hex(addr),(data or b"").hex())
            except Exception as e: print("BPS_READ_ERR",hex(addr),repr(e))
        show(screen,"mini-bps")
    except Exception as e: print("BPS_ERROR",repr(e))
    print("BPS_END")

else:
    raise ValueError("unknown batch12c case")
while True:
    M5.update(); time.sleep_ms(200)
