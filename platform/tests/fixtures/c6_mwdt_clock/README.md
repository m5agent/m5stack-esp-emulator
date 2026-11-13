# C6 MWDT clock preimage

These four QEMU controller files are the host-tested preimages of patch 0017 after the
canonical C6 base `febae182e132e4055529be423a818225ebddaa3a` and the 18 patches
in `scripts/bootstrap-c6-runtime.py` through C6 patch 0016. The host test replays
the four controller files from the patch, then compiles the actual PCR register-write and watchdog
functions with only clock, timer and IRQ observations stubbed. It checks both
the original behavior and the changed model under ASan/UBSan. It does not
emulate guest execution or grant virtual-device PASS.

The legacy source has no external clock input. Its compatibility shim does
nothing, matching the original PCR's unconnected write path; its prescaler
write shim is the original register handler assignment. Before/after oracles
are explicit deadlines, counter values, IRQs, gates and stages, not Python
copies of the new timer logic. C3's legacy APB/XTAL controls remain included.

`unsafe-off-stage.patch` restores only the two clock-event sections of the
first 0017 candidate (source commit e31feb8f, runtime d7a6/ef3c). Its actual C
negative proves the OFF-stage and zero-hold failures without depending on Git
history or private evidence. The final positive checks use C6 TRM v1.2 p547:
each expiry resets the count, including Disabled actions. Zero hold retains
register value zero and is quantized to the next MWDT edge; exact silicon
zero-value semantics were not measured.
