#!/bin/bash
# Build review-sta control images into OUT (default: ignored .work storage).
# Requires IDF_PATH (ESP-IDF v5.5.4) and an IDF Python environment.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:?usage: build.sh <out-dir>}"
mkdir -p "$out"
python="${IDF_PYTHON_ENV_PATH:?set IDF_PYTHON_ENV_PATH}/bin/python"
export IDF_CCACHE_ENABLE=0

# label chip flash_size mode [setup_gpio]
targets=(
  "s3-8mb-good esp32s3 8MB good"
  "s3-8mb-wrong esp32s3 8MB wrong"
  "s3-8mb-offline esp32s3 8MB offline"
  "s3-16mb-good esp32s3 16MB good"
  "s3-16mb-wrong esp32s3 16MB wrong"
  "s3-16mb-offline esp32s3 16MB offline"
  "sticks3-setup-b esp32s3 8MB setup 12"
  "stopwatch-setup-b esp32s3 16MB setup 1"
  "paperdiy-setup-b esp32s3 16MB setup 3"
  "classic-8mb-good esp32 8MB good"
  "classic-8mb-wrong esp32 8MB wrong"
  "classic-8mb-offline esp32 8MB offline"
  "classic-16mb-good esp32 16MB good"
  "classic-16mb-wrong esp32 16MB wrong"
  "classic-16mb-offline esp32 16MB offline"
  "stickcplus2-setup-b esp32 8MB setup 39"
  "core2-setup-b esp32 16MB setup 39"
)

for row in "${targets[@]}"; do
  read -r label chip size mode gpio <<<"$row"
  [[ -n "${ONLY:-}" && ",$ONLY," != *",$label,"* ]] && continue
  lower=$(tr '[:upper:]' '[:lower:]' <<<"$size")
  build="$out/build-$label"
  args=(-D "REVIEW_MODE=$mode" -D "SDKCONFIG=$build/sdkconfig"
        -D "SDKCONFIG_DEFAULTS=$here/sdkconfig.defaults.$chip-$lower")
  [[ -n "${gpio:-}" ]] && args+=(-D "REVIEW_SETUP_GPIO=$gpio")
  IDF_TARGET=$chip "$python" "$IDF_PATH/tools/idf.py" -C "$here" -B "$build" "${args[@]}" build >"$out/$label.log" 2>&1 \
    || { echo "BUILD FAIL $label (see $out/$label.log)"; exit 1; }
  if [[ $chip == esp32s3 ]]; then bootloader=0; freq=80m; else bootloader=0x1000; freq=40m; fi
  "$python" -m esptool --chip "$chip" merge_bin -o "$out/review-ctrl-$label.bin" --fill-flash-size "$size" \
    --flash_mode dio --flash_size "$size" --flash_freq "$freq" \
    "$bootloader" "$build/bootloader/bootloader.bin" \
    0x8000 "$build/partition_table/partition-table.bin" \
    0x10000 "$build/review_sta_control.bin" >>"$out/$label.log" 2>&1
  cp "$build/review_sta_control.elf" "$out/review-ctrl-$label.elf"
  echo "BUILT $label $(shasum -a 256 "$out/review-ctrl-$label.bin" | cut -c1-64)"
done
