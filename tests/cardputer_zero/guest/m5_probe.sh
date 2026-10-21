#!/bin/sh

exec >/dev/console 2>&1

echo M5_CZ_PROBE_START
echo "MODEL=$(tr -d '\000' </proc/device-tree/model 2>/dev/null)"
echo "I2C_DEVICES:"
ls -l /dev/i2c-* 2>/dev/null || true
echo "SPI_DEVICES:"
ls -l /dev/spidev* 2>/dev/null || true
echo "SD_DEVICES:"
ls -l /dev/mmcblk* 2>/dev/null || true

echo "USB_DEVICES:"
for device in /sys/bus/usb/devices/*; do
    [ -e "$device/idVendor" ] || continue
    echo "USB_DEVICE=$(basename "$device")"
    echo "USB_ID=$(cat "$device/idVendor" 2>/dev/null):$(cat "$device/idProduct" 2>/dev/null)"
    echo "USB_PRODUCT=$(cat "$device/product" 2>/dev/null)"
    echo "USB_MANUFACTURER=$(cat "$device/manufacturer" 2>/dev/null)"
    if [ -e "$device/driver" ]; then
        echo "USB_DRIVER=$(basename "$(readlink "$device/driver")")"
    fi
done

echo "NETWORK_INTERFACES:"
for device in /sys/class/net/*; do
    [ -e "$device" ] || continue
    echo "NET_DEVICE=$(basename "$device")"
    echo "NET_ADDRESS=$(cat "$device/address" 2>/dev/null)"
    echo "NET_OPERSTATE=$(cat "$device/operstate" 2>/dev/null)"
    if [ -e "$device/device/driver" ]; then
        echo "NET_DRIVER=$(basename "$(readlink "$device/device/driver")")"
    fi
done
if grep -q 'm5.usb_eth_probe=1' /proc/cmdline; then
    for _ in $(seq 1 30); do
        if find /sys/class/net -path '*/device/driver' -exec readlink {} \; \
            2>/dev/null | grep -q '/r8152$'; then
            break
        fi
        sleep 0.5
    done
    echo "USB_ETH_INTERFACES:"
    for device in /sys/class/net/*; do
        [ -e "$device/device/driver" ] || continue
        echo "USB_ETH_DEVICE=$(basename "$device")"
        echo "USB_ETH_ADDRESS=$(cat "$device/address" 2>/dev/null)"
        echo "USB_ETH_OPERSTATE=$(cat "$device/operstate" 2>/dev/null)"
        echo "USB_ETH_DRIVER=$(basename "$(readlink "$device/device/driver")")"
    done
    if [ -x /usr/local/sbin/m5-eth-probe ]; then
        ip link set eth0 up 2>/dev/null || true
        for _ in $(seq 1 120); do
            [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" = "1" ] && break
            sleep 0.5
        done
        echo "USB_ETH_CARRIER=$(cat /sys/class/net/eth0/carrier 2>/dev/null)"
        sleep 25
        python3 /usr/local/sbin/m5-eth-probe || true
    fi
fi

echo "I2C_SYSFS:"
for device in /sys/bus/i2c/devices/*; do
    [ -e "$device" ] || continue
    echo "I2C_NODE=$(basename "$device")"
    cat "$device/name" 2>/dev/null || true
    cat "$device/uevent" 2>/dev/null || true
done

echo "I2C_SCAN:"
if command -v i2cdetect >/dev/null 2>&1; then
    i2cdetect -y 1 || true
else
    echo "i2cdetect unavailable"
fi
if command -v i2cget >/dev/null 2>&1; then
    ES8389_ID0=$(i2cget -f -y 1 0x10 0xfd 2>/dev/null || true)
    ES8389_ID1=$(i2cget -f -y 1 0x10 0xfe 2>/dev/null || true)
    ES8389_STATE=$(i2cget -f -y 1 0x10 0xf1 2>/dev/null || true)
    echo "ES8389_CHIP_ID=$ES8389_ID0:$ES8389_ID1"
    echo "ES8389_STATE=$ES8389_STATE"
fi

echo "RTC:"
for device in /sys/class/rtc/rtc*; do
    [ -e "$device" ] || continue
    echo "RTC_NAME=$(cat "$device/name" 2>/dev/null)"
    echo "RTC_DATE=$(cat "$device/date" 2>/dev/null)"
    echo "RTC_TIME=$(cat "$device/time" 2>/dev/null)"
done

echo "IIO:"
for device in /sys/bus/iio/devices/iio:device*; do
    [ -e "$device" ] || continue
    echo "IIO_NAME=$(cat "$device/name" 2>/dev/null)"
done

echo "MEDIA:"
if grep -q 'm5.camera_probe=1' /proc/cmdline; then
    mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
    if [ -r /sys/kernel/debug/dynamic_debug/control ]; then
        echo 'file bcm2835-unicam.c +p' \
            >/sys/kernel/debug/dynamic_debug/control 2>/dev/null || true
        echo 'file drivers/media/i2c/imx219.c +p' \
            >/sys/kernel/debug/dynamic_debug/control 2>/dev/null || true
    fi
    for _ in $(seq 1 120); do
        [ -e /sys/bus/i2c/devices/10-0010/driver ] && break
        sleep 0.5
    done
    echo "IMX219_DRIVER=$(basename "$(readlink /sys/bus/i2c/devices/10-0010/driver 2>/dev/null)" 2>/dev/null)"
    echo "IMX219_DRIVER_LINK=$(readlink /sys/bus/i2c/devices/10-0010/driver 2>/dev/null)"
    echo "IMX219_MODALIAS=$(cat /sys/bus/i2c/devices/10-0010/modalias 2>/dev/null)"
    echo "IMX219_DEVICE_LINKS:"
    ls -l /sys/bus/i2c/devices/10-0010/consumer:* 2>/dev/null || true
    echo "UNICAM_NODE:"
    ls -l /sys/bus/platform/devices/3f801000.csi 2>/dev/null || true
    echo "UNICAM_DRIVER_LINK=$(readlink /sys/bus/platform/devices/3f801000.csi/driver 2>/dev/null)"
    echo "UNICAM_SUPPLIERS:"
    ls -l /sys/bus/platform/devices/3f801000.csi/supplier:* 2>/dev/null || true
    echo "UNICAM_ENDPOINTS:"
    find /sys/firmware/devicetree/base/soc -path '*csi@7e801000*' \
        -o -path '*imx219@10*' 2>/dev/null | sort
    echo "DEFERRED_DEVICES:"
    cat /sys/kernel/debug/devices_deferred 2>/dev/null || true
    if [ ! -e /sys/bus/platform/devices/3f801000.csi/driver ] &&
        [ -e /sys/bus/platform/drivers/unicam/bind ]; then
        echo "UNICAM_REBIND_RESULT=$(echo 3f801000.csi >/sys/bus/platform/drivers/unicam/bind 2>&1; echo rc=$?)"
    fi
    for _ in $(seq 1 120); do
        [ -e /dev/video0 ] && break
        sleep 0.5
    done
    echo "UNICAM_DRIVER=$(basename "$(readlink /sys/bus/platform/devices/3f801000.csi/driver 2>/dev/null)" 2>/dev/null)"
    echo "UNICAM_DRIVER_LINK_AFTER=$(readlink /sys/bus/platform/devices/3f801000.csi/driver 2>/dev/null)"
    echo "CAMERA_MEDIA_DEVICES:"
    ls -l /dev/media* 2>/dev/null || true
fi
ls -l /dev/media* 2>/dev/null || true
echo "VIDEO:"
ls -l /dev/video* 2>/dev/null || true
if command -v v4l2-ctl >/dev/null 2>&1; then
    echo "V4L2_DEVICES:"
    v4l2-ctl --list-devices 2>&1 || true
    for device in /dev/video*; do
        [ -e "$device" ] || continue
        echo "V4L2_FORMATS=$device"
        v4l2-ctl -d "$device" --list-formats-ext 2>&1 || true
    done
fi
if grep -q 'm5.camera_probe=1' /proc/cmdline && [ -c /dev/video0 ]; then
    echo "MEDIA_TOPOLOGY:"
    cat /sys/kernel/debug/clk/clk_summary 2>/dev/null || true
    if command -v media-ctl >/dev/null 2>&1; then
        media-ctl -d /dev/media0 -p 2>&1 || true
        media-ctl -d /dev/media0 --set-v4l2 \
            '"imx219 10-0010":0[fmt:SRGGB10_1X10/640x480]' 2>&1 || true
    fi
    if grep -q 'm5.camera_controls_probe=1' /proc/cmdline &&
        command -v v4l2-ctl >/dev/null 2>&1; then
        sensor_subdev=
        for node in /dev/v4l-subdev*; do
            [ -e "$node" ] || continue
            name=$(cat "/sys/class/video4linux/$(basename "$node")/name" 2>/dev/null)
            case "$name" in
                *imx219*) sensor_subdev="$node" ;;
            esac
        done
        echo "CAMERA_SENSOR_SUBDEV=$sensor_subdev"
        echo "CAMERA_CONTROLS_BEFORE:"
        v4l2-ctl -d "$sensor_subdev" --list-ctrls 2>&1 || true
        v4l2-ctl -d "$sensor_subdev" \
            --set-ctrl=test_pattern=2,exposure=1000,analogue_gain=64,digital_gain=320 \
            2>&1 || true
        echo "CAMERA_CONTROLS_AFTER:"
        v4l2-ctl -d "$sensor_subdev" \
            --get-ctrl=test_pattern,exposure,analogue_gain,digital_gain \
            2>&1 || true
    fi
    v4l2-ctl -d /dev/video0 \
        --set-fmt-video=width=640,height=480,pixelformat=RG10 2>&1 || true
    echo "CAMERA_STREAM:"
    rm -f /tmp/m5-camera.raw
    timeout 30 v4l2-ctl -d /dev/video0 --stream-mmap=4 --stream-count=1 \
        --stream-to=/tmp/m5-camera.raw 2>&1
    echo "CAMERA_STREAM_RC=$?"
    echo "CAMERA_FRAME_BYTES=$(wc -c </tmp/m5-camera.raw 2>/dev/null || echo 0)"
    echo "CAMERA_FRAME_SHA256=$(sha256sum /tmp/m5-camera.raw 2>/dev/null | cut -d' ' -f1)"
    v4l2-ctl -d /dev/video0 --get-fmt-video 2>&1 || true
    v4l2-ctl -d /dev/video0 --log-status 2>&1 || true
fi
echo "CAMERA_DMESG:"
dmesg 2>/dev/null | grep -Ei 'unicam|imx219|csi|video' | tail -80 || true

echo "INPUT:"
for device in /sys/class/input/input*; do
    [ -e "$device" ] || continue
    echo "INPUT_NAME=$(cat "$device/name" 2>/dev/null)"
done

echo "IR:"
ls -l /dev/lirc* 2>/dev/null || true
for device in /sys/class/rc/rc*; do
    [ -e "$device" ] || continue
    echo "RC_DEVICE=$(basename "$device")"
    cat "$device/device/name" 2>/dev/null || true
    cat "$device/protocols" 2>/dev/null || true
done
if grep -q 'm5.ir_probe=1' /proc/cmdline; then
    receive_dev=
    send_dev=
    for device in /dev/lirc*; do
        [ -e "$device" ] || continue
        echo "IR_FEATURES_DEVICE=$device"
        features=$(ir-ctl -d "$device" --features 2>&1)
        echo "$features"
        if echo "$features" | grep -q 'Device can receive raw IR'; then
            receive_dev=$device
        fi
        if echo "$features" | grep -q 'Device can send raw IR'; then
            send_dev=$device
        fi
    done
    echo "IR_RECEIVE_DEVICE=$receive_dev"
    echo "IR_SEND_DEVICE=$send_dev"
    echo "IR_RX_CAPTURE:"
    timeout 12 ir-ctl -d "$receive_dev" --receive=/tmp/m5-ir-rx.txt \
        --mode2 >/tmp/m5-ir-rx.log 2>&1 &
    ir_rx_pid=$!
    sleep 0.5
    echo M5_IR_RX_READY
    wait "$ir_rx_pid"
    echo "IR_RX_RC=$?"
    echo "IR_RX_BYTES=$(wc -c </tmp/m5-ir-rx.txt 2>/dev/null || echo 0)"
    cat /tmp/m5-ir-rx.log 2>/dev/null || true
    head -20 /tmp/m5-ir-rx.txt 2>/dev/null || true
    echo "IR_TX_SEND:"
    timeout 10 ir-ctl -d "$send_dev" --scancode=nec:0x10ef \
        >/tmp/m5-ir-tx.txt 2>&1
    echo "IR_TX_RC=$?"
    cat /tmp/m5-ir-tx.txt 2>/dev/null || true
fi

echo "POWER_SUPPLIES:"
for device in /sys/class/power_supply/*; do
    [ -e "$device" ] || continue
    echo "POWER_NAME=$(basename "$device")"
    for property in type status online voltage_now current_now capacity charge_full charge_full_design; do
        if [ -r "$device/$property" ]; then
            property_upper=$(printf '%s' "$property" | tr '[:lower:]' '[:upper:]')
            echo "POWER_${property_upper}=$(cat "$device/$property" 2>/dev/null)"
        fi
    done
done
if grep -q 'm5.charge_probe=1' /proc/cmdline; then
    CHARGE_STATUS_BEFORE=$(cat /sys/class/power_supply/*/status 2>/dev/null | tr '\n' ',')
    CHARGE_CURRENT_BEFORE=$(cat /sys/class/power_supply/*/current_now 2>/dev/null | tr '\n' ',')
    echo "CHARGE_STATUS_BEFORE=$CHARGE_STATUS_BEFORE"
    echo "CHARGE_CURRENT_BEFORE=$CHARGE_CURRENT_BEFORE"
    echo "M5_CHARGE_PROBE_READY"
    sleep 7
    CHARGE_STATUS_AFTER=$(cat /sys/class/power_supply/*/status 2>/dev/null | tr '\n' ',')
    CHARGE_CURRENT_AFTER=$(cat /sys/class/power_supply/*/current_now 2>/dev/null | tr '\n' ',')
    echo "CHARGE_STATUS_AFTER=$CHARGE_STATUS_AFTER"
    echo "CHARGE_CURRENT_AFTER=$CHARGE_CURRENT_AFTER"
fi

echo "SOUND:"
cat /proc/asound/cards 2>/dev/null || true
ls -l /dev/snd/* 2>/dev/null || true
if grep -q 'm5.audio_probe=1' /proc/cmdline; then
    echo "AUDIO_CONTROLS:"
    amixer -c 0 contents 2>/dev/null || true
    amixer -c 0 sset 'Speaker Switch' off >/dev/null 2>&1
    amixer -c 0 sset 'Speaker Switch' on >/dev/null 2>&1
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i 'sine=frequency=1000:sample_rate=48000' \
        -t 0.2 -ac 2 -c:a pcm_s16le /tmp/m5-playback.wav
    echo "AUDIO_PLAYBACK:"
    timeout 10 aplay -D hw:0,0 /tmp/m5-playback.wav 2>&1
    echo "AUDIO_PLAYBACK_RC=$?"
    echo "AUDIO_CAPTURE:"
    timeout 10 arecord -D hw:0,0 -f S16_LE -r 16000 -c 2 -d 1 \
        /tmp/m5-capture.wav 2>&1
    echo "AUDIO_CAPTURE_RC=$?"
    if [ -s /tmp/m5-capture.wav ]; then
        echo "AUDIO_CAPTURE_BYTES=$(wc -c </tmp/m5-capture.wav)"
        echo "AUDIO_CAPTURE_SHA256=$(sha256sum /tmp/m5-capture.wav | cut -d' ' -f1)"
    fi
fi

echo "DRM:"
for device in /sys/class/drm/card*; do
    [ -e "$device" ] || continue
    echo "DRM_NAME=$(basename "$device")"
    cat "$device/status" 2>/dev/null || true
    cat "$device/modes" 2>/dev/null || true
done

echo "INTERRUPTS:"
cat /proc/interrupts 2>/dev/null || true

echo "GPIO_DEBUG:"
cat /sys/kernel/debug/gpio 2>/dev/null || true

echo "DRIVER_ERRORS:"
dmesg | grep -Ei 'tca8418|bmi270|bmm150|rx8130|bq27220|m5ioe|es8389|imx219|r8152|usb.*eth|i2c|spi|panel|st7789|failed|error' | tail -160 || true

echo M5_CZ_PROBE_DONE
