# Tab5 stable-backend original-firmware follow-up

Date: `2026-11-14`. Native **virtual-device validation** through normal Device
Service upload/import/session/evidence APIs. Both original applications remain
**FAIL**; execution integrity and cleanup pass. No resident backend was upgraded.

The fixed service source is `a5990e720a8c79310456bf5868141f4cfd50afe8`;
official esp-emu v1.0.0 is
`cdfe1e8f3d447af4af12f0699457e958af0ea6ff8601d909079801c8655c6ef5`.
It differs from the previously tested rc2 executable, so its result was not
inferred from the old run. ROM, revision eFuse, C6 adapter, normalized Flash,
unchanged application partitions and ZIP hashes are in the summaries.

| Original | Observation | Result |
| --- | --- | --- |
| UIFlow2 V2.5.4, `94b6b43c02a95cfac1e7c70a6166ad669f308d0d16389c272de5ca7c2d45ef37` | 120.909 s; 134 ROM boots; 133 occurrences of MEPC `0x4ff0255c` / MTVAL `0x34602773` | FAIL; no MicroPython banner |
| Maker Fighter 1.4, `d96962362b262bcc4e5abcf6a720a2de1a53f0869c87916fd3f798eb845e08b6` | 60.516 s; 80 ROM boots; 79 occurrences of MEPC `0x4ff01d82` / MTVAL `0x34602773` | FAIL; USB stage not reached |

The instruction reads older-P4 `mintstatus` CSR `0x346`. Maker Fighter's missing
DWC assertion here is not a USB fix: the earlier CSR failure prevents reaching
that stage. Prior DSI/USB failures remain separate. Read-only GDB snapshots
occurred after the observation windows during repeated boots, not at fault
stops; neither their sampled instruction words nor zero DSI registers prove a
PHY result. Original images were not patched and no unrelated ELF was attached.

Each run retains a four-entry valid ZIP captured before stop, exact original
application bytes, 116 / 58 session samples with the same original P4 process,
and verified P4/C6 role, lease, Flash and dedicated-service cleanup.
Physical hardware, browser-WASM, USB enumeration/transfer and UI/touch readiness
are not established. Issues #188 and #226 remain open.

[UIFlow2 execution](issue188-execution-summary.json),
[Maker Fighter execution](issue226-execution-summary.json),
[independent audit](independent-audit-summary.json), and
[full reproducible work record](https://github.com/m5agent/agent-work-logs/blob/b8de787432b1aafeb3d9c2c6aea5be4a6a895dc4/records/esp-emulator/2026-11-14-p4-v1-originals/README.md).
