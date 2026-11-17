# Native SPIFFS partition fixture

The guest uses ESP-IDF's SPIFFS VFS to list, read, write, unmount and remount
the `storage` partition at `0x110000`. It checks for its previous write before
opening the output file. This permits a same-guest reset to verify persistence.
The partition is 1 MiB. The Flash image is unsigned and unencrypted. The test
payloads are synthetic strings and patterns.

Use ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`. In the
activated SDK environment, run these commands from this directory.

```sh
idf.py -B build build
python3 prepare_images.py --idf "$IDF_PATH" --build build --out "$TEST_OUTPUT"
```

The preparation script uses the pinned SDK's `spiffsgen.py` defaults. Both
images use 256-byte pages, 4,096-byte blocks, 32-byte object names and
4 bytes of metadata. Each has two files and enough data pages to identify its
layout. `baseline-flash.bin` contains a readable SPIFFS partition with
`BASELINE.TXT`. `seed.spiffs.bin` contains the independent `FIXTURE.TXT`
used by the guest. `blank-flash.bin` contains the same boot and application
bytes with erased storage. All artifacts are test outputs and stay outside Git.

Upload the baseline Flash and seed partition through an owned native Device
Service on separate state, port and credentials. Register the baseline as a
merged firmware image for Cardputer, StickS3 or Dial and create a session with
`storage.filesystem.image_artifact_id` pointing to the fixture,
`partition_label="storage"`, and `format="spiffs"`. Confirm the unchanged
firmware SHA from the session and the effective Flash SHA from the fixture
receipt. Compute the expected effective hash from the baseline with only
the declared partition replaced.

The mounted guest emits `SPIFFS_PROBE_READ seeded=1 listed=1 prior=0` and
`SPIFFS_PROBE_REMOUNT wrote=1 restored=1 listed=1` before
`SPIFFS_PROBE_DONE`. Resetting that session must show `prior=1`.
A session with the original baseline and no fixture should report
`seeded=0 listed=0` with the original SPIFFS still mountable.

Collect evidence before stop. Stop with `purge=0&retain_flash=1` when a Flash
comparison is needed, and independently verify both file digests after stop.
The bytes outside `storage` and both uploaded inputs must keep their original
hashes. Release the retained Flash afterward when a replay copy is unnecessary.
