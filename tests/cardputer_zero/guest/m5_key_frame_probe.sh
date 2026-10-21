#!/bin/sh

exec >/dev/console 2>&1

if ! grep -q 'm5.key_probe=1' /proc/cmdline; then
    exit 0
fi

fb_sysfs=
for _ in $(seq 1 120); do
    for candidate in /sys/class/graphics/fb*; do
        [ -e "$candidate" ] || continue
        fb_name=$(cat "$candidate/name" 2>/dev/null)
        if [ "$fb_name" = "panel-mipi-dbid" ] || \
           [ "$fb_name" = "panel-mipi-dbi" ] || \
           [ "$(basename "$candidate")" != "fb0" ]; then
            fb_sysfs=$candidate
            break
        fi
    done
    if [ -n "$fb_sysfs" ]; then
        break
    fi
    sleep 0.25
done

if [ -z "$fb_sysfs" ]; then
    echo "M5_KEY_FRAME_ERROR=missing-framebuffer"
    exit 1
fi
fb_device="/dev/$(basename "$fb_sysfs")"

event=
for candidate in /sys/class/input/event*; do
    [ -e "$candidate" ] || continue
    input_name=$(cat "$candidate/device/name" 2>/dev/null)
    if [ "$input_name" = "tca8418c" ]; then
        event="/dev/input/$(basename "$candidate")"
        break
    fi
done

if [ -z "$event" ] || [ ! -e "$event" ]; then
    echo "M5_KEY_FRAME_ERROR=missing-input"
    exit 1
fi

virtual_size=$(cat "$fb_sysfs/virtual_size")
stride=$(cat "$fb_sysfs/stride")
bpp=$(cat "$fb_sysfs/bits_per_pixel")
width=${virtual_size%,*}
height=${virtual_size#*,}
frame_bytes=$((stride * height))

capture_frame() {
    output=$1
    blocks=$(((frame_bytes + 4095) / 4096))
    timeout 3 dd if="$fb_device" of="$output.tmp" bs=4096 count="$blocks" \
        iflag=fullblock 2>/dev/null || return 1
    head -c "$frame_bytes" "$output.tmp" >"$output" || return 1
    sha256sum "$output" | cut -d' ' -f1
}

before_hash=$(capture_frame /tmp/m5-frame-before.raw) || {
    echo "M5_KEY_FRAME_ERROR=framebuffer-capture-timeout"
    exit 1
}
if grep -q 'm5.ui_probe=1' /proc/cmdline; then
    factory_log=/tmp/m5-factory-ui.log
    if grep -q 'm5.frame_dump=1' /proc/cmdline; then
        factory_log=/root/m5-factory-ui.log
    fi
    if ! grep -q 'm5.ui_no_shim=1' /proc/cmdline; then
        export LD_PRELOAD=/usr/local/lib/m5-fb-shim.so
    fi
    if grep -q 'm5.ui_trace=1' /proc/cmdline; then
        LV_LINUX_FBDEV_DEVICE="$fb_device" HOME=/root XDG_RUNTIME_DIR=/run/user/0 \
            strace -ff -tt -o /tmp/m5-factory.strace \
            -e trace=openat,ioctl,mmap,munmap,read,write,close \
            /usr/bin/factory_test >"$factory_log" 2>&1 &
    else
        LV_LINUX_FBDEV_DEVICE="$fb_device" HOME=/root XDG_RUNTIME_DIR=/run/user/0 \
            stdbuf -oL -eL /usr/bin/factory_test >"$factory_log" 2>&1 &
    fi
    factory_ui_pid=$!
    echo "M5_FACTORY_UI_PID=$factory_ui_pid"
    for _ in $(seq 1 240); do
        grep -q 'LVGL app started at' "$factory_log" 2>/dev/null && break
        kill -0 "$factory_ui_pid" 2>/dev/null || break
        sleep 0.25
    done
    sleep 20
    ui_hash=$before_hash
    ui_changed=0
    if grep -q 'm5.ui_log_only=1' /proc/cmdline; then
        echo "M5_UI_CAPTURE_SKIPPED=1"
    elif kill -0 "$factory_ui_pid" 2>/dev/null; then
        if ui_hash=$(capture_frame /tmp/m5-frame-ui.raw); then
            if [ "$ui_hash" != "$before_hash" ]; then
                ui_changed=1
            fi
        else
            echo "M5_UI_FRAME_CAPTURE_ERROR=timeout"
            ui_hash=$before_hash
        fi
    else
        echo "M5_FACTORY_UI_EXITED=1"
    fi
    echo "M5_UI_FRAME_HASH=$ui_hash"
    echo "M5_UI_FRAME_CHANGED=$ui_changed"
    if [ -f /tmp/m5-frame-ui.raw ] && command -v python3 >/dev/null 2>&1; then
        python3 - <<'PY'
from pathlib import Path

data = Path("/tmp/m5-frame-ui.raw").read_bytes()
if len(data) % 2:
    data = data[:-1]
nonblack = 0
colors = set()
for offset in range(0, len(data), 2):
    pixel = data[offset] | (data[offset + 1] << 8)
    if pixel:
        nonblack += 1
        if len(colors) < 1024:
            colors.add(pixel)
print(f"M5_UI_FRAME_PIXELS={len(data) // 2}")
print(f"M5_UI_FRAME_NONBLACK={nonblack}")
print(f"M5_UI_FRAME_UNIQUE_RGB565={len(colors)}")
PY
    fi
    if kill -0 "$factory_ui_pid" 2>/dev/null; then
        kill -TERM "$factory_ui_pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$factory_ui_pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$factory_ui_pid" 2>/dev/null || true
    fi
    echo "M5_FACTORY_UI_STOPPED=1"
    if [ "$ui_changed" = "1" ]; then
        before_hash=$ui_hash
    fi
    tail -20 "$factory_log" 2>/dev/null || true
    echo "M5_FACTORY_LOG_DONE"
    if grep -q 'm5.ui_trace=1' /proc/cmdline; then
        for trace_file in /tmp/m5-factory.strace*; do
            [ -e "$trace_file" ] || continue
            echo "M5_FACTORY_TRACE=$trace_file"
            tail -40 "$trace_file"
        done
    fi
    if grep -q 'm5.frame_dump=1' /proc/cmdline; then
        cp /tmp/m5-frame-ui.raw /m5-frame-ui.raw 2>/dev/null || true
    fi
    sync
fi
timeout 30 dd if="$event" of=/tmp/m5-input-event.bin bs=24 count=1 2>/dev/null &
event_reader_pid=$!

echo "M5_KEY_FRAME_READY EVENT=$event FB=$fb_device WIDTH=$width HEIGHT=$height BPP=$bpp STRIDE=$stride FRAME_BYTES=$frame_bytes FRAME_SHA256=$before_hash"

wait "$event_reader_pid"
event_rc=$?
if [ -s /tmp/m5-input-event.bin ]; then
    event_hex=$(od -An -v -tx1 /tmp/m5-input-event.bin | tr -d ' \n')
else
    event_hex=
fi

sleep 0.5
after_hash=$(capture_frame /tmp/m5-frame-after.raw) || after_hash=$before_hash
if grep -q 'm5.frame_dump=1' /proc/cmdline; then
    cp /tmp/m5-frame-before.raw /m5-frame-before.raw
    cp /tmp/m5-frame-after.raw /m5-frame-after.raw
    sync
fi
echo "M5_KEY_EVENT_RC=$event_rc"
echo "M5_KEY_EVENT_HEX=$event_hex"
echo "M5_FRAME_BEFORE_SHA256=$before_hash"
echo "M5_FRAME_AFTER_SHA256=$after_hash"
echo "M5_KEY_FRAME_DONE"
