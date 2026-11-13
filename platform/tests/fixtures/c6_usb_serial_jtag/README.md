# C6 fixed CDC endpoint preimage

These two files are the unchanged C6 USB Serial-JTAG implementation at
canonical QEMU `febae182e132e4055529be423a818225ebddaa3a`, also present after
the native C6 recipe through patch 0019. The host test extracts their actual
MMIO/reset functions and compares them with patch 0020. Chardev writes, host
packets, clocks and IRQ lines are the only stubs. Positive and negative cases
exercise FIFO bytes, backpressure, status/masks, gate and reset semantics;
they are not Python copies of the model. Guest results are separate.
