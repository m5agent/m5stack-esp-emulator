# StickS3 RTC 慢时钟校准与定时浅睡

这个 ESP-IDF 探针在同一来宾中读取原始 RTC 慢计数、独立 SYSTIMER 计数和 SDK 慢时钟校准值，然后请求 500 ms 定时浅睡。两个镜像的源码和其他配置一致，仅切换默认 RC 慢钟与内部 RC_FAST/256。

使用未修改的 ESP-IDF v5.5.4 `735507283d5b2f9fb363a1901172dbd9e847945d` 和仓库根目录下独立忽略目录。两个变体都使用 8 MiB Flash 和单个 factory 分区。

```sh
source "${IDF_PATH}/export.sh"
fixture="$PWD/tests/firmware/sticks3_rtc_slowclk"
for variant in rc_slow rc_fast_div256; do
  build="$PWD/.work/sticks3-rtc-slowclk-$variant"
  mkdir -p "$build"
  idf.py -C "$fixture" -B "$build" \
    -D "SDKCONFIG=$build/sdkconfig" \
    -D "SDKCONFIG_DEFAULTS=$fixture/sdkconfig.defaults;$fixture/sdkconfig.$variant" build
  idf.py -C "$fixture" -B "$build" -D "SDKCONFIG=$build/sdkconfig" \
    merge-bin --fill-flash-size 8MB
done
```

通过独立 [Device Service](../../../docs/device-service-api.md) 标准上传、组合并启动 `sticks3` / `runtime=qemu` 会话，禁用来宾网络。用同一个构建镜像分别复跑旧运行时与待测运行时。开启该会话自身的第二只读 QMP 连接，在来宾启动前做好事件监听。记录 `SUSPEND` 和 `WAKEUP` 各一次，使用各自 QMP 时间戳和宿主单调接收计时核对实际挂起间隔。SDK 会在浅睡唤醒时重新校正 SYSTIMER，两次浅睡采样间的 SDK 时间仅作交叉观测。

- `RTC_CLOCK_PROBE_BOOT` 确认实际慢钟选择：默认 RC 为 0，内部 RC_FAST/256 为 2。它还记录 SDK 已保存的校准值和读出的实时校准值。
- `RTC_CLOCK_AWAKE` 按清醒期间原始 RTC tick 与 SYSTIMER 时间计算频率，并与时钟标称频率和 SDK 校准频率对照。
- `RTC_CLOCK_SLEEP_RETURN` 要求 `status=0`、`cause=4`（timer）和 `timer_ok=1`。`RTC_CLOCK_PROBE_DONE` 应为 `PASS`。宿主根据事件时间另验实际挂起时间接近 500 ms。
- 停止前收集 `manifest,serial,logs` ZIP，核对清单的来宾和固件身份、串口与实际应用 Flash 字节。以 `purge=0&retain_flash=0` 停止，确认租约释放和所属进程退出。

[对照结果](summary.json)保留了原版运行时上 D256 选源后计数偏慢而 SDK 校准一致的失败，以及时钟修正前后两种慢钟的真实浅睡时间。范围为原生虚拟 StickS3 的浅睡定时器、两种内部慢钟和相应 RTC/SYSTIMER 行为。其他慢钟、深睡、原版应用体验、真机和浏览器是独立验收项。
