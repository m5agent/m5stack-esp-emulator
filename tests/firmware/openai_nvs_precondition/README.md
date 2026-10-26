# OpenAI first-boot NVS precondition

Last reviewed: `2026-10-26`

This probe separates missing external NVS configuration from a firmware or
emulator boot defect for the public
`OpenAI Voice Assistant For AtomS3R` firmware
(`1897200000000000358`, source SHA256
`b3597fcabbff57c98618caa8754af84745e9eac35b2868ab3c4cb0935b7c59b3`).

The public binary declares a 24 KiB NVS partition at offset `0x9000`, but the
partition is entirely erased. The application reads the `config` namespace and
the `wifi_ssid`, `wifi_password` and `openaikey` string keys. Without that
external data it logs:

```text
NVS: Error opening NVS handle: ESP_ERR_NVS_NOT_FOUND
main: Failed to load user data
main_task: Returned from app_main()
```

The probe uses `platform/tools/nvs_image.py` to generate two synthetic NVS
fixtures. The encoder output is checked byte-for-byte against
`esp-idf-nvs-partition-gen 0.3.0`.

Run against a Device Service with the AtomS3R QEMU runtime:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/openai_nvs_precondition/run_test.py \
  --service-url http://127.0.0.1:8787 \
  --firmware /path/to/atoms3r-openai-v1.0.bin \
  --out-dir /tmp/m5-openai-nvs-precondition
```

If `--firmware` is omitted, the runner force-refreshes the current public
metadata and downloads the artifact into its cache.

The three cases are:

1. `wpa2-qemu-ap.nvs.bin` sets a non-empty password. The guest loads the
   values, raises the authentication threshold to WPA2, completes the four-way
   EAPOL handshake, receives pairwise-key CCMP data, obtains DHCP, resolves
   `api.openai.com` and opens TCP/443.
2. `open-qemu-ap.nvs.bin` sets an empty password. The same guest loads the
   values, associates with the Open QEMU AP, obtains DHCP, resolves
   `api.openai.com`, opens TCP/443 and attempts the HTTPS request. The
   synthetic OpenAI key then fails, which is expected.
3. `wrong-password.nvs.bin` supplies a password that does not match the QEMU
   AP. The AP rejects M2 at MIC verification, deauthenticates the station and
   the guest retries without obtaining DHCP or starting HTTP.

The evidence result is `PASS` for the investigation and `PARTIAL` for the
firmware's full behavior. A black framebuffer is not used as the root-cause
signal: this firmware does not expose a provisioning or error UI before a
successful cloud session. Real OpenAI credentials, Realtime/WebRTC media,
physical WPA2 association, WPA3, group-key multicast delivery, RF and hardware
remain `NOT RUN`.

Canonical evidence:
[`evidence-2026-10-25-openai-nvs-precondition.json`](../evidence-2026-10-25-openai-nvs-precondition.json).
