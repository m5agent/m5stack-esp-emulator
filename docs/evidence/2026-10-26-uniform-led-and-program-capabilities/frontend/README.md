# Uniform LED frontend verification - 2026-10-26

**Browser/HTTP fixture PASS; guest/controller/hardware NOT RUN.** The actual mounted model components are real; the HTTP state values are synthetic. No physical LED permutation or mechanical angle conversion is established.

- `uniform-r4/`: original report and all 12 screenshots, byte-for-byte. Eight checks cover all RGB(3), Encoder(2), 8Encoder(9) mounted LED colors/brightness/emissive/glow and Encoder shell diffusion; uniform -> nonuniform -> recovery/off; explicit synthetic binding priority; malformed/missing/unavailable/error readback; initial/poll HTTP503; six panel-first/shell-first delayed-GET teardown cases; invalid command/failed-handle guards; zero input echo and inferred shaft movement.
- `scroll-r4/`: original report and three screenshots; seven existing Scroll fixture checks PASS, including held disposal and readonly negatives.
- `model-shell-r4/`: original full regression report and all 32 screenshots; 14 controller shells and 29 Unit models passed frame/input/output/lifecycle/fallback checks.
- `source-freeze.json`, `sources/`, `source-export.json`: exact original product/probe/source bytes as `.txt`, verified against report hashes. The root later bumped cache references to g. Where needed, exact original bytes were recovered from Git HEAD, or only the two UnitPanel g tags were restored to executed f in an archive copy. Original reports/hash fields are unmodified; these runs do not claim the later g cache executed.
- `pure-mappings-report.json`: mapping contract PASS. The existing UnitPanel browser test also returned `UNIT_PANEL_BROWSER_OK` in the terminal.
- `implementation-verification.json`: frozen implementation/result summary. `implementation-report.md.txt` is the original short implementation note.

Unknown is Led.runtimeKnown=false and matching object3d.userData.runtimeKnown. Old emission is cleared as a neutral unknown appearance, with an explicit UnitPanel notice and retained numeric readback. This is not a claim that electrical LEDs are off. Legal uniform/all-off or evidenced explicit mappings restore known=true and hide the notice. Individual physical LED positions and shaft-angle UNIT-HOST-29 remain OPEN.

Original reports retain their `/tmp` paths; resources are archived here under the same basenames. Tests and all source hashes appear in the frozen records. Later actual Device Service/cache-g execution is a separate evidence layer.
