"""Compare exact official USB Buffer preimage/candidate inside the guest.

Both isolated modules use real machine IRQ critical sections and owned byte
buffers. This tests Python library bytes/return values, with no synthetic USB
host, endpoint transfer or source-firmware replacement.
"""
import gc
import json
import usb_core_before as before

gc.collect()
import usb_core_candidate as candidate


def emit(phase, status, **details):
    details.update(api="usb.device.core.Buffer.readinto", phase=phase, status=status,
                   scope="isolated-official-python-source-correction")
    print("USB_CANDIDATE " + json.dumps(details))


def corrected_cases(module):
    results = []
    empty = module.Buffer(8)
    target = bytearray(4)
    assert empty.readinto(target) == 0 and bytes(target) == b"\0" * 4
    results.append("empty read returns zero")
    b = module.Buffer(8)
    assert b.write(b"ABCDEF") == 6
    assert b.readinto(bytearray(0)) == 0 and bytes(b.pend_read()) == b"ABCDEF"
    results.append("zero-length destination does not consume")
    target = bytearray(4)
    assert b.readinto(target) == 4 and bytes(target) == b"ABCD" and bytes(b.pend_read()) == b"EF"
    results.append("partial read returns four and preserves tail")
    target = bytearray(8)
    assert b.readinto(target) == 2 and bytes(target[:2]) == b"EF" and b.readable() == 0
    results.append("remaining tail returns two")
    for length in range(9):
        b = module.Buffer(8)
        b.write(b"ABCDEFGH")
        target = bytearray(length)
        assert b.readinto(target) == length
        assert bytes(target) == b"ABCDEFGH"[:length]
        assert bytes(b.pend_read()) == b"ABCDEFGH"[length:]
    results.append("all destination lengths zero through capacity")
    b = module.Buffer(8)
    b.write(b"AB")
    pending = b.pend_write(4)
    pending[:] = b"DEFG"
    b.finish_read(1)
    b.finish_write(4)
    target = bytearray(8)
    assert b.readinto(target) == 5 and bytes(target[:5]) == b"BDEFG" and b.readable() == 0
    results.append("read during pending write preserves compacted byte order")
    return results


try:
    b = before.Buffer(8)
    b.write(b"ABCDEF")
    target = bytearray(4)
    try:
        returned = b.readinto(target)
        emit("official-preimage", "FAIL", error="expected original NameError did not occur", returned=returned)
    except NameError as error:
        assert "to_r4" in str(error) and bytes(target) == b"ABCD" and bytes(b.pend_read()) == b"EF"
        emit("official-preimage", "EXPECTED_FAILURE", error=repr(error), copied=list(target), remaining=list(b.pend_read()))
    emit("corrected-source", "PASS", cases=corrected_cases(candidate))
except Exception as error:
    emit("comparison", "FAIL", error=repr(error))
print("USB_BUFFER_CORRECTION_DONE")
