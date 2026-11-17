# Tab5 ST7123 virtual contact hold and Arduventure power request

Virtual-device validation, 2026-11-17. The unchanged original Arduventure
1.0.0 and the ESP-IDF fixture both use the native Device Service path
with a pinned esp-emu and ESP Part. No matching ELF was supplied.

- The standalone guest received one continuous contact at (240,780) for
  a requested 1.2 seconds. The guest's ESP timer measured 1,201,970 μs.
  The same contact appeared in 69 consecutive GPIO23/I²C1 readouts, with
  68 refresh acknowledgements and one release. Three preceding taps retained
  their press and release semantics.
- A short tap on Arduventure's power icon (672,53) left its frame unchanged.
  A 3-second hold at (660,1100), outside that icon, had 186 refresh reads,
  full press and release evidence, and left the application active.
- A 3-second hold at (672,53) drew the original `POWER OFF` frame
  (`84f04dbb5fa1edffcd6acd0977b33aab77d99b8d03bfc951c38d50217f4c0097`).
  On an instrumented repeat, the guest then wrote ten alternating
  `0x89/0x99` values to PI4IO address `0x44`, register `0x05` over HP
  I²C1 at 49 ms intervals. The changed bit is bit 4, the Tab5 power-off
  pulse output. The corresponding original negative controls did not
  issue that pulse train.
- The terminal action interrupted input receipt and gave HTTP 409
  `tab5_st7123_unavailable`. One uninstrumented run subsequently produced a
  ROM `HP_SYS_HP_WDT_RESET`; the instrumented capture did not
  contain a reset marker. There is no modeled power latch or confirmed
  native terminal power-off in this result. The original power request
  and frame are verified; terminal behavior remains partial.
- The same worker replayed the original CarPlay GT911 independent profile.
  Its blank drag received all reports and opening the pairing confirmation
  still produced the known frame. The confirmation was left unaccepted.

Use the [probe runner](../../../tests/firmware/tab5_st7123/README.md) for
standalone controller validation and the
[Device Service API](../../device-service-api.md#create-a-reference-uiflow2-device)
for original uploads and ordered touch requests. To observe the hardware
side of the power command, keep the same original and attach the pinned
esp-emu `--cosim-log` option to the isolated P4 launcher, filtering
`BusRequest,BusReply,ChipReset`. Artifacts were captured before stopping
and mutable Flash was released. Multitouch, physical hardware, browser
touch and full saved-snapshot power-off review are outside this proof.
Burner submission was disabled.

[Bounded evidence](summary.json)
