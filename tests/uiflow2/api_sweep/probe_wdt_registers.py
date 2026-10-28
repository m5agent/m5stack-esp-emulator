"""Read-only watchdog register diagnostics on the actual ESP32-S3 guest.

This does not configure registers directly. The public WDT API owns all
configuration and feeding; snapshots distinguish firmware setup from the
controller's interrupt/reset behavior.
"""
import json
import machine
import time
import M5


def snapshot(stage):
    groups = []
    for base in (0x6001F000, 0x60020000):
        groups.append({"config": [machine.mem32[base + offset]
                                  for offset in range(0x48, 0x60, 4)],
                       "interrupts": [machine.mem32[base + offset]
                                      for offset in (0x70, 0x74, 0x78)]})
    print("WDT_REGISTERS " + json.dumps({"stage": stage, "ticks_ms": time.ticks_ms(),
                                         "groups": groups, "reset_cause": machine.reset_cause()}))


M5.begin()
snapshot("before")
watchdog = machine.WDT(timeout=2000)
snapshot("configured")
for index in range(12):
    watchdog.feed()
    time.sleep_ms(250)
snapshot("fed-three-seconds")
for index in range(12):
    time.sleep_ms(500)
    snapshot("unfed-%d" % index)
print("WDT_REGISTER_DIAGNOSTIC_DONE")
