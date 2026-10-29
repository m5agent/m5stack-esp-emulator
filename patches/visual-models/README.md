# Reviewed visual runtime patches

These patches are applied only by `platform/tools/sync_visual_models.py` after
reading the fixed public upstream Git objects. Every patch has an exact target,
upstream preimage SHA256, patch SHA256 and effective output SHA256 in the
synchronizer. Unexpected bytes, targets or file membership fail closed. The
upstream and effective JavaScript/resource closures are both checked.

`0001-device-viewer-pause-rendering.patch` rebases the emulator mainline rendering
pause/resume/dispose change from commit
`3de27e88edf4e8897f8408c5f6b82ef2b881d421` onto the model upstream
`4879ab51eb8bb11ce024e670ae6880529e3d0f42`. It preserves that upstream's hidden
viewport fit fix. It adds no assets, model identities or runtime admission.

The generated vendor manifest records both upstream and effective identities.
The vendored `source-manifest.json` remains the unchanged upstream preparation
receipt, including its historical baseline; it does not claim to describe the
patched runtime. Do not edit vendored runtime files directly: review and pin a
new patch and its preimage/result before regenerating the snapshot.
