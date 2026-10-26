import time


def _bcd(value):
    return ((value // 10) << 4) | (value % 10)


def _unbcd(value):
    return ((value >> 4) & 0x0F) * 10 + (value & 0x0F)


def check_rx8130(i2c, address=0x32):
    target = (2026, 10, 22, 7, 8, 9)
    values = (
        _bcd(target[5]),
        _bcd(target[4]),
        _bcd(target[3]),
        4,
        _bcd(target[2]),
        _bcd(target[1]),
        _bcd(target[0] % 100),
    )
    i2c.writeto_mem(address, 0x10, bytes(values))
    first = i2c.readfrom_mem(address, 0x10, 7)
    decoded = (
        2000 + _unbcd(first[6]),
        _unbcd(first[5]),
        _unbcd(first[4]),
        _unbcd(first[2]),
        _unbcd(first[1]),
        _unbcd(first[0]),
    )
    if decoded != target:
        raise RuntimeError("RX8130 readback %r" % (decoded,))
    time.sleep_ms(1200)
    second = i2c.readfrom_mem(address, 0x10, 1)
    if _unbcd(second[0]) == decoded[5]:
        raise RuntimeError("RX8130 did not advance")
    return decoded


def check_pcf8563(i2c, address=0x51):
    target = (2026, 10, 22, 6, 7, 8)
    values = (
        _bcd(target[5]),
        _bcd(target[4]),
        _bcd(target[3]),
        _bcd(target[2]),
        4,
        _bcd(target[1]),
        _bcd(target[0] % 100),
    )
    i2c.writeto_mem(address, 0x02, bytes(values))
    first = i2c.readfrom_mem(address, 0x02, 7)
    decoded = (
        2000 + _unbcd(first[6]),
        _unbcd(first[5]),
        _unbcd(first[3]),
        _unbcd(first[2]),
        _unbcd(first[1]),
        _unbcd(first[0]),
    )
    if decoded != target:
        raise RuntimeError("PCF8563 readback %r" % (decoded,))
    time.sleep_ms(1200)
    second = i2c.readfrom_mem(address, 0x02, 1)
    if _unbcd(second[0]) == decoded[5]:
        raise RuntimeError("PCF8563 did not advance")
    return decoded
