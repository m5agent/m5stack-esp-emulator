# Control Unit Device Service evidence

2026-10-26: five **virtual-device** cases PASS on CoreS3 / QEMU. These are
controller/guest cases, separate from browser visual and physical-hardware
validation. `summary.json` selects one final run per Unit with exact firmware,
serial/frame/ZIP hashes and visible session IDs. All leases were stopped with
`purge=0`; ZIPs were requested before stop. No firmware/ROM image is in this
evidence directory. Build images remain in ignored `.work/`.

Joystick's three raw bytes, Encoder int16/press/two guest RGB writes,
8Encoder eight int32 channels/buttons/switch/reset/address/nine RGB triplets,
CardKB 50 controls/four key tables/modifier locks/FIFO consumption, and RFID2
REQA/cascade-select/authenticated blocks/halt/negative controls have independent
reports. Register emulation does not establish RF, switch mechanics, physical
LED positions or electrical timing equivalence.

`rfid2-attempt1` preserves a real failure: the probe incorrectly read the
vendored official UID container's absent `.size` field. The final probe obtains
UID length from guest ATQA bytes (4/7/10), without changing official drivers or
borrowing injected host UID length. CRC, wrong-key, wrong-sector, halt, bad-CRC
and antenna-off checks remain explicit. The original driver/protocol caveats are
in `docs/unit-research/encoder-protocol-conflicts.md`.

Each run also preserves exact `probe-main.py.txt` and `probe-probe_config.py.txt`
matching the per-report probe hashes. The official driver files are vendored
under `tests/units/controls_probe/control_drivers/` with their own source manifest.
The initial Joystick framebuffer caught an intermediate redraw; the selected
`joystick-v11-settled` run uses bounded three-identical-PNG sampling.

Reproduce using the existing compatible reference base firmware and Python 3.12:

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_control_cases.py \
  --api-url <device-service-url> --case all --out-dir .work/control-unit-validation
```

This creates new visible sessions. `--prepare-only` composes images without
starting QEMU or calling the API. It is not a functional PASS.
