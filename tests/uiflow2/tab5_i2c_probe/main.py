# Diagnose the native ESP32-P4 I2C register-device semantics.
import machine
import time


def dump(label, address, register, length=8):
    try:
        data = bytes(i2c.readfrom_mem(address, register, length))
        print(label, "0x%02X" % register, data.hex())
    except Exception as error:
        print(label, "ERROR", repr(error))


print("TAB5_I2C_PROBE_START")
i2c = machine.I2C(1, scl=machine.Pin(32), sda=machine.Pin(31), freq=100000)
print("TAB5_I2C_PROBE_SCAN", i2c.scan())

# The device is preloaded with reg 0x00=0x24, 0x01=0x25, ... 0x07=0x2B.
dump("TAB5_I2C_PROBE_ID_BEFORE", 0x68, 0x00)
dump("TAB5_I2C_PROBE_REGS_BEFORE", 0x68, 0x00, 8)

# Confirm that register address zero itself is usable. This distinguishes a
# controller/backend addressing bug from boot-time code overwriting the ID.
i2c.writeto_mem(0x68, 0x00, b"\x24")
dump("TAB5_I2C_PROBE_ID_AFTER_WRITE", 0x68, 0x00)

# A write should update the register file and leave the pointer on the next
# register, matching the documented auto-increment behaviour.
i2c.writeto_mem(0x68, 0x02, b"\xA1\xA2\xA3")
dump("TAB5_I2C_PROBE_AFTER_WRITE_02", 0x68, 0x02, 6)

# Try a bare write followed by a raw read. Some I2C controllers coalesce the
# register-address write differently from readfrom_mem().
i2c.writeto(0x68, b"\x00")
print("TAB5_I2C_PROBE_RAW_AFTER_PTR0", bytes(i2c.readfrom(0x68, 8)).hex())

# Exercise every documented 1-byte-register device in one pass.
for address, label in (
    (0x32, "RX8130"),
    (0x41, "INA226"),
    (0x43, "PI4IOE1"),
    (0x44, "PI4IOE2"),
):
    dump("TAB5_I2C_PROBE_" + label, address, 0x00, 8)

print("TAB5_I2C_PROBE_DONE")
while True:
    time.sleep(1)
