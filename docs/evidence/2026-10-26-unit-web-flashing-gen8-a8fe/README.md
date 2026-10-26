# Independent cold-flash browser lifecycle

The independent Button session PASSes from a naturally observed `flashing`
page to running, four real Button input POSTs, guest GPIO readback, pre-stop
ZIP and stopped history. Its fresh firmware SHA is
`c6fa0f2f5fb87b5be8047deba198f50ceb7b8633d4d59feb0be02b3ec37f04fe`.
The Device Service used its normal `esp-emu-esptool` cold-flash transport.
No cache was cleared, no delay/state was injected, and no page reload was
forced after opening. The original source/profiles/service stayed unchanged.

Before invoking the existing runner, the new output `files/` directory was
seeded with an unreferenced `lifecycle_receipt.py` containing only a metadata
constant. Its exact contents and hash are in `lifecycle-metadata.json` and the
probe-source snapshot. The existing probe files remain byte for byte equal to
the selected Button case; every firmware byte outside the VFS partition is
also identical. Only the fresh filesystem metadata/module changes the image
hash and avoids the prepared-flash cache. This distinct SHA/session is not
included in the main 27-Unit selection.

The [lifecycle summary](lifecycle-summary.json) binds initial and final PNGs,
ZIP, live a8fe executable/worker generation 8, original probe equality and
cold-flash transport. The initial screenshot was opened and visually checked:
flashing badge, blank display, Unit waiting state and grey disabled Button.
No separate numeric DOM-disabled receipt was recorded at that opening point;
the running controls are subsequently checked by the real input transport.
The session naturally reaches running and updates its readbacks. Firmware
and ROM binaries are excluded. This is virtual-device validation; physical
hardware and electrical equivalence are NOT RUN.
