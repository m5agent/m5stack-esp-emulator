CoreS3 official main-loader candidate: reproducible local build evidence

Classification: LOCAL_BUILD_PASS_NOT_GUEST_ADMITTED.
The earlier preflight remains PREFLIGHT_ONLY_NO_FIRMWARE_BUILD. The later owned
build completed the official patch series and CoreS3 pack_all. These records
must not be interpreted as main.mpy guest runtime, stock-reference compatibility,
physical hardware, publication, or integration acceptance.

Pinned sources: UIFlow 3a86d8f611b3639cca755a933e01a5a829771ef1;
MicroPython 78ff170de9e32c79db6e64d3e33d2bd60002bdcd;
ESP-IDF v5.5.4 / 735507283d5b2f9fb363a1901172dbd9e847945d.
Official source, applied source diffs, tool/download hashes, resolved managed
component lock, constraints, Python freeze, exact target command and actual
preprocessor output are retained as text. The complete 115 MB compile_commands
file is fingerprinted, with one explicitly derived builtinimport target row.

The CoreS3-only local patch enables official
MICROPY_MODULE_OVERRIDE_MAIN_IMPORT=1 and MICROPY_CPYTHON_COMPAT=1.
The actual target translation-unit preprocessor confirms both flags. This is
configuration evidence; same-guest main identity/if-main/cache/interruption and
recovery validation remains NOT RUN for this build record.

The final merged image is 16121856 bytes, SHA256
7ce5ca0744a27508913c4dd69dd06f30454fb27c54a920faf486d3350cf2267b.
No firmware, ROM, ELF, object, SDK, tool executable, or other binary is archived.
Image checksum/validation hash and partition-table verification passed using
esptool 4.12 image_info. Artifact metadata describes local files only.

Bootstrap boundary: SDK, sources, tools and Python environments are owned local
directories. On macOS, Component Manager ignores XDG_CACHE_HOME and may have
written its first dependency cache under the user Library/Caches directory.
Subsequent stages explicitly set IDF_COMPONENT_CACHE_PATH. No shared cache was
deleted or moved. This is not a zero-outside-writes claim.

Every copied/derived archived file has original/archive size and SHA256 in
index.json. Exact path substitutions are declared there; a changed copy is not
claimed byte-identical. .md source documents use .md.txt suffixes. Stage failures
and repairs remain in separate records; the first image-inspection CLI spelling
error and all bootstrap failures are preserved.

Reproduction: commands/ contains the exact bounded helpers used by this build;
preflight/future-build-steps.txt contains the earlier planned recipe. Adjust
owned roots and install host prerequisites locally, fetch the pinned sources,
initialize recorded required gitlinks, apply official patch series and the local
CoreS3 patch, then execute pack_all. Official logs may print flash examples;
none was executed. Do not infer firmware admission from compilation success.
