# C6 SPI2 length and DMA host regression

`preimage.c` contains six complete production functions, from
`esp32c3_spi_txrx_buffer` through `esp32c3_spi_begin_transaction`, copied from
`hw/ssi/esp32c3_spi.c`. The source is Espressif QEMU commit
`febae182e132e4055529be423a818225ebddaa3a`, with the C6 bootstrap patch sequence
through `0014-c6-nesso-panel-madctl.patch`. The complete pre-0015 file SHA-256 is
`c5b9387c4efcff7953b5ad4d2bd77177dbe0350a4ede93bfaff2d23ede15730e`.
Only these functions and the original license notice are retained. This is a
bounded compilation fixture, not a runtime source snapshot.

The test applies the current canonical `0015-c6-spi2-data-length.patch` directly
to these real functions, checks reverse application, and compiles them using
ASan and UBSan. The preserved `unsafe-length.patch` is the initial 18-bit length
candidate before independent review found an unbound-DMA overread and a mixed
RX-DMA/TX-FIFO data corruption. It is used only as a negative control and is
never part of a runtime bootstrap. The negative source's complete original
file SHA-256 is
`72ee9e5fe861d03717f499c4334c82d02bb5d1a9df02e41f22b44898528fc5ab`.

Run the checked-in test after the model's 0015 commit is present:

```sh
python3 platform/tests/test_c6_spi_data_length_patch.py -v
```

Independent pre-merge review can select a candidate explicitly:

```sh
python3 platform/tests/test_c6_spi_data_length_patch.py --patch /path/to/0015-c6-spi2-data-length.patch -v
```

There are 15 cases for each version. Seven negative cases fail on the unsafe
candidate; all 15 pass on the reviewed fix. Case 0 requires an actual ASan
`heap-buffer-overflow` diagnostic, rather than accepting any nonzero exit.
The other negative cases require assertions. Both versions retain passing
controls for the 352-byte display payload, buffer cap, short supplied payload,
FIFO bounds, and SPI1's separate 10-bit field.

The cases exercise the real SPI transaction, byte-transfer, command/address,
dummy-clock, and completion paths. Stubbed GDMA boundaries return an explicit
supplied byte count or an absent channel; a byte-level SSI stub records MOSI
and produces deterministic MISO bytes independently of the transaction code.
Assertions check the actual bus bytes, received bytes, completion status, and
channel calls. These stubs are used only in host tests and never in the emulator.

Coverage includes absent OUT channel at the maximum 18-bit length, missing
GDMA object, RX DMA plus TX FIFO, 352-byte TX, 4096-byte DMA cap, short and empty
descriptor returns, maximum-length RX, FIFO-only full duplex, SPI1 isolation,
MOSI-disabled DMA, absent IN channel, and shorter TX than RX. Empty or unbound
TX data must not emit bytes or report completion. Buffer limits describe the
current single-descriptor implementation; they do not claim full-length or
chained-DMA hardware equivalence.

The descriptor RAM parser, ownership bits, descriptor chaining, hardware chip
select, GPIO matrix, panel pixel mapping, DMA-TX/FIFO-RX register readback, and
physical timing are outside this host fixture. The original-firmware Device
Service runs and the panel probe provide separate virtual-device evidence;
host test success alone does not establish those outcomes.

Review execution on 2026-11-13 used patch SHA-256
`559c7dd083e6eae5247762cbdbd3a531e11774f475e400acd60a08595e638cc8`.
All 15 fixed cases and the expected 15 negative/control outcomes passed under
ASan/UBSan. A separate replay of the full C6 prefix from the pinned upstream
source confirmed the fixture's complete functions and the patched functions
matched the fresh build source exactly. Its complete SPI source SHA-256 was
`dd061ec21e374a2b9ffe581fb002ae0c36570fbf82f4e07cfa2a44827b07c689`.
