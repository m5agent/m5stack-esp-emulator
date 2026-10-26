"""Generate finite UIFlow2 Scroll probes; never execute guest source on the host.

The runner owns visible Device Service sessions and source-count injection.
``snapshot-prime`` ends after selecting a register/optional short reads;
``snapshot-read`` makes no Unit constructor, scan, or pointer write, so an
injection and a later program submission can test the original TX snapshot.
All events are complete JSON lines prefixed by ``SCROLL_PROTOCOL ``.
"""
from __future__ import annotations

import re
import textwrap
from collections.abc import Mapping, Sequence

PHASES = (
    "registers", "driver-live", "snapshot-prime", "snapshot-read",
    "set-counter", "versions", "address-change", "address-restore", "bootloader",
)


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def build_probe_source(
    pins: Mapping[str, int],
    phase: str,
    *,
    address: int = 0x40,
    target_address: int = 0x41,
    expected_counter: int | None = None,
    expected_increment: int | None = None,
    expected_direction: int | None = None,
    ab_direction: int = 0,
    source_count: int | None = None,
    pressed: bool = False,
    reg: int = 0x11,
    reads: Sequence[int] = (),
    expected_hex: Sequence[str] = (),
    raw_counter: int = 0,
    bootloader_version: int | None = None,
    marker: str = "SCROLL_PROTOCOL",
    wait_ms: int = 10000,
    led_rgb: int = 0x123456,
) -> str:
    """Return source only; each phase finishes or raises within a finite bound.

    ``driver-live`` constructs the real ScrollUnit (which resets counters),
    writes FB, emits ``kind=ready``, and waits for the runner's source input.
    The runner must establish its source baseline before submission. Expected
    direction is the physical timer direction, independent of FB.

    ``snapshot-*`` and ``set-counter`` deliberately avoid the constructor.
    Expected hex strings bind each raw read; no reads is valid for a prime.
    A None bootloader version means an explicit unsupported-I2C rejection is
    expected, rather than inventing a version absent a matched flash fixture.
    """
    if phase not in PHASES:
        raise ValueError("unknown Scroll probe phase")
    if not isinstance(pins, Mapping) or "white" not in pins or "yellow" not in pins:
        raise ValueError("pins must contain the session's white/yellow GPIOs")
    white = _integer(pins["white"], "white", 0, 63)
    yellow = _integer(pins["yellow"], "yellow", 0, 63)
    if white == yellow:
        raise ValueError("SCL and SDA must differ")
    address = _integer(address, "address", 1, 127)
    target_address = _integer(target_address, "target_address", 1, 127)
    ab_direction = _integer(ab_direction, "ab_direction", 0, 1)
    reg = _integer(reg, "reg", 0, 255)
    raw_counter = _integer(raw_counter, "raw_counter", -(2**31), 2**31 - 1)
    wait_ms = _integer(wait_ms, "wait_ms", 100, 30000)
    led_rgb = _integer(led_rgb, "led_rgb", 0, 0xFFFFFF)
    if type(pressed) is not bool:
        raise ValueError("pressed must be a boolean")
    if not isinstance(marker, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", marker):
        raise ValueError("marker must be an uppercase serial token")
    if bootloader_version is not None:
        _integer(bootloader_version, "bootloader_version", 0, 255)
    if source_count is not None:
        _integer(source_count, "source_count", -32768, 32767)
    if phase == "driver-live":
        _integer(expected_counter, "expected_counter", -(2**31), 2**31 - 1)
        _integer(expected_increment, "expected_increment", -(2**31), 2**31 - 1)
        _integer(expected_direction, "expected_direction", 0, 1)
        if expected_counter == 0:
            raise ValueError("driver-live needs a nonzero counter target after READY")
    if phase in {"address-change", "address-restore"} and address == target_address:
        raise ValueError("address transition needs two distinct addresses")
    if not isinstance(reads, (list, tuple)) or not isinstance(expected_hex, (list, tuple)):
        raise ValueError("reads and expected_hex must be explicit lists or tuples")
    lengths = tuple(_integer(n, "read length", 1, 32) for n in reads)
    if len(lengths) > 16 or len(lengths) != len(expected_hex):
        raise ValueError("each bounded raw read needs one exact expected hex string")
    expected_bytes = []
    for length, value in zip(lengths, expected_hex):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{" + str(length * 2) + "}", value):
            raise ValueError("expected hex must exactly match the raw read length")
        expected_bytes.append(bytes.fromhex(value))
    if phase == "snapshot-read" and not lengths:
        raise ValueError("snapshot-read needs at least one raw read")

    source = f'''import json, struct, time, binascii
import M5
from hardware import I2C, Pin
from unit import ScrollUnit
M5.begin()
_i2c = I2C(0, scl=Pin({white}), sda=Pin({yellow}), freq=100000)
_address = {address}
_phase = {phase!r}
_marker = {marker!r}
def _event(kind, **fields):
 fields['kind'] = kind
 fields['phase'] = _phase
 print(_marker + ' ' + json.dumps(fields))
def _check(value, expected, name):
 if type(value) is not type(expected) or value != expected:
  raise AssertionError(name + ': ' + repr(value) + ' != ' + repr(expected))
 _event('check', name=name, observed=_hex(value) if isinstance(value, (bytes, bytearray)) else value)
def _write(data, address=None):
 target = _address if address is None else address
 acknowledged = _i2c.writeto(target, data)
 if acknowledged != len(data):
  raise OSError(5, 'short I2C write: ' + repr(acknowledged))
def _read(length, address=None):
 return _i2c.readfrom(_address if address is None else address, length)
def _register(reg, length, address=None):
 _write(bytes([reg]), address)
 return _read(length, address)
def _hex(data):
 return binascii.hexlify(data).decode()
def _counter():
 return struct.unpack('<i', _register(0x10, 4))[0]
def _set_counter(value):
 _write(b'\\x10' + struct.pack('<i', value))
def _signed16(value):
 value &= 65535
 return value - 65536 if value >= 32768 else value
def _must_nack(operation, name):
 try:
  value = operation()
 except OSError as error:
  _event('unsupported', name=name, exception=type(error).__name__, details=str(error))
 else:
  raise AssertionError(name + ' unexpectedly accepted: ' + repr(value))
'''
    blocks = {
        "registers": f'''
            _scroll = ScrollUnit(_i2c, _address)
            _check(_scroll.get_rotary_value(), 0, 'constructor-reset')
            _check(_scroll.get_rotary_status(), False, 'status-initial')
            _set_counter(0x12345678)
            _check(_scroll.get_rotary_value(), 22136, 'original-low16')
            _write(b'\\x11\\xab')
            _check(_counter(), 0x1234AB78, 'partial-counter-write')
            _check(_scroll.get_rotary_value(), -21640, 'partial-original-low16')
            _check(struct.unpack('<i', _register(0x50, 4))[0], 0, 'count-write-no-increment')
            _set_counter(0x12345678)
            _write(b'\\x11')
            _check(_hex(_read(2)), '5634', 'finite-short-read')
            _check(_hex(_read(4)), '12563412', 'finite-continuation-after-stop')
            _write(b'\\x99')
            _check(_hex(_read(4)), '56341256', 'unknown-pointer-preserves-tx')
            _set_counter(5)
            _write(b'\\x10')
            _write(b'\\x40\\x01')
            _check(_hex(_read(4)), '05000000', 'reset-preserves-old-tx')
            _check(_counter(), 0, 'reset-clears-counter')
            for _raw in (0, 1, -1, 32767, 32768, 65535, 65536, -32769):
             _set_counter(_raw)
             _check(_scroll.get_rotary_value(), _signed16(_raw), 'original-low16-' + str(_raw))
            _scroll.reset_rotary_value()
            _set_counter(1)
            _check(_scroll.get_rotary_status(), True, 'status-first')
            _check(_scroll.get_rotary_status(), True, 'status-query-does-not-consume')
            _check(_scroll.get_rotary_value(), 1, 'value-consumes-status')
            _check(_scroll.get_rotary_status(), False, 'status-after-value')
            _set_counter(100)
            _scroll.set_rotary_value(7)
            _check(_scroll.get_rotary_value(), 107, 'setter-software-offset')
            _check(_counter(), 100, 'setter-no-register-write')
            _set_counter(0)
            _scroll.set_rotary_value(70000)
            _check(_scroll.get_rotary_value(), 70000, 'setter-no-int16-truncation')
            _scroll.reset_rotary_value()
            _scroll.set_color(99, 0x123456)
            _check(_hex(_register(0x30, 6)), '001234560012', 'rgb-word-finite-tx')
            # Quiescent/latest-value subset only; the MCU multi-slot RGB queue
            # and burst-dependent partial-write scheduling are not modeled.
            time.sleep_ms(20)
            _write(b'\\x32\\xab')
            _check(_hex(_register(0x31, 3)), '12ab56', 'rgb-partial-quiescent-model')
            _scroll.fill_color({led_rgb})
            _write(b'\\xfb\\x02')
            _check(_hex(_register(0xFB, 3)), '010101', 'fb-nonzero-normalized')
            _write(b'\\xfb\\x00')
            _check(_scroll.get_button_status(), {pressed!r}, 'original-button')
            _check(_scroll.get_firmware_version(), '1', 'original-firmware-version-string')
            _event('done', counter=_counter(), led_rgb={led_rgb}, original_driver=True)
        ''',
        "driver-live": f'''
            _scroll = ScrollUnit(_i2c, _address)
            _write(bytes([0xFB, {ab_direction}]))
            _event('ready', expected_counter={expected_counter!r}, source_count={source_count!r}, ab_direction={ab_direction})
            _deadline = time.ticks_add(time.ticks_ms(), {wait_ms})
            while _counter() != {expected_counter!r}:
             if time.ticks_diff(_deadline, time.ticks_ms()) <= 0:
              raise AssertionError('runner source-count injection did not arrive')
             time.sleep_ms(25)
            _check(_scroll.get_rotary_status(), _signed16({expected_counter!r}) != 0, 'live-status-first')
            _check(_scroll.get_rotary_status(), _signed16({expected_counter!r}) != 0, 'live-status-second')
            _check(_scroll.get_rotary_value(), _signed16({expected_counter!r}), 'live-original-value')
            _check(_scroll.get_rotary_status(), False, 'live-status-after-value')
            _check(_scroll.get_rotary_increments(), _signed16({expected_increment!r}), 'live-original-increment')
            _check(_scroll.get_rotary_increments(), 0, 'live-original-increment-consumed')
            _check(_register(0x60, 1)[0], {expected_direction!r}, 'live-physical-direction')
            _check(_register(0xFB, 1)[0], {ab_direction}, 'live-ab-direction')
            _check(_scroll.get_button_status(), {pressed!r}, 'live-original-button')
            _scroll.fill_color({led_rgb})
            _event('done', counter=_counter(), source_count={source_count!r}, direction={expected_direction!r}, led_rgb={led_rgb}, original_driver=True)
        ''',
        "set-counter": f'''
            _set_counter({raw_counter})
            _check(_counter(), {raw_counter}, 'raw-count-prepared')
            _event('done', counter={raw_counter})
        ''',
        "versions": f'''
            _scroll = ScrollUnit(_i2c, _address)
            _check(_scroll.get_firmware_version(), '1', 'original-firmware-version-string')
            {'_must_nack(_scroll.get_bootloader_version, "bootloader-version-no-fixture")' if bootloader_version is None else '_check(_scroll.get_bootloader_version(), ' + repr(str(bootloader_version)) + ', "declared-bootloader-fixture")'}
            _event('done', firmware_version='1', bootloader_fixture={bootloader_version!r})
        ''',
        "address-change": f'''
            _scroll = ScrollUnit(_i2c, _address)
            _write(bytes([0xFF, {target_address}]))
            _must_nack(lambda: _write(b'\\xfe'), 'old-address')
            _check(_hex(_register(0xFF, 1, {target_address})), {bytes([target_address]).hex()!r}, 'new-address-register')
            _check(_hex(_register(0xFE, 1, {target_address})), '01', 'new-address-data-plane')
            _event('done', old_address=_address, address={target_address}, original_driver_address=_scroll._address)
        ''',
        "address-restore": f'''
            _write(bytes([0xFF, {target_address}]))
            _check(_hex(_register(0xFF, 1, {target_address})), {bytes([target_address]).hex()!r}, 'restored-address-register')
            _check(_hex(_register(0xFE, 1, {target_address})), '01', 'restored-address-data-plane')
            _event('done', old_address=_address, address={target_address})
        ''',
        "bootloader": '''
            _must_nack(lambda: _write(b'\\xfd\\x01'), 'bootloader-mode-unimplemented')
            _check(_hex(_register(0xFE, 1)), '01', 'bootloader-rejection-keeps-application')
            _event('done', bootloader_supported=False)
        ''',
    }
    if phase.startswith("snapshot-"):
        body = ""
        if phase == "snapshot-prime":
            body += f"_write(bytes([{reg}]))\n"
        for index, (length, expected) in enumerate(zip(lengths, expected_bytes)):
            body += f"_check(_read({length}), {expected!r}, 'snapshot-read-{index}')\n"
        # No register access after the reads: the next execution owns the
        # remaining TX index, even if source-count changes between programs.
        body += f"_event('done', register={reg}, read_lengths={list(lengths)!r}, pointer_written={phase == 'snapshot-prime'!r})\n"
    else:
        body = textwrap.dedent(blocks[phase])
    return source + body
