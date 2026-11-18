# StickS3 原生 RTC 定时深睡

用 ESP-IDF v5.5.4（`735507283d5b2f9fb363a1901172dbd9e847945d`）
构建 StickS3 的 8 MiB 合并镜像。构建目录应在仓库的忽略目录中。

```sh
source "${IDF_PATH}/export.sh"
mkdir -p .work/sticks3-rtc-deep-sleep
idf.py -C tests/firmware/sticks3_rtc_deep_sleep \
  -B "${PWD}/.work/sticks3-rtc-deep-sleep" \
  -D "SDKCONFIG=${PWD}/.work/sticks3-rtc-deep-sleep/sdkconfig" build
idf.py -C tests/firmware/sticks3_rtc_deep_sleep \
  -B "${PWD}/.work/sticks3-rtc-deep-sleep" merge-bin --fill-flash-size 8MB
```

在隔离的 Device Service 将合并镜像以 `sticks3`、`runtime=qemu` 启动，
使用静态 8 MiB Flash。调用路径见 [Device Service API](../../../docs/device-service-api.md)。

1. 首次启动检查 `RTC_DEEP_BOOT reset=1 cause=0`。来宾依次从
   `esp_deep_sleep_start()` 发起 650 ms 与 1,500 ms 定时深睡。
2. 每轮检查 QMP 从 `suspended` 回到 `running`，收到 `SUSPEND`、
   `RESET`、`WAKEUP` 事件。串口必须报告 `reset=8 cause=4`，并通过
   RTC 数据与慢时钟保留、数字域普通内存重新初始化和耗时范围断言。
   最后一行检查 `RTC_DEEP_PASS cycles=2`。两轮使用同一进程和 Flash。
3. 在该标记后调用 `POST /api/v1/sessions/{id}/reset`，检查上电复位原因、
   未定义的唤醒源及小于 2 秒的 RTC 启动时间。随后同一会话必须再次完成两轮，
   以排除旧校准影响冷启动和旧闹钟影响重新入睡。
4. 调用 `GET /api/v1/sessions/{id}/evidence`，对照 ZIP 清单的固件 SHA、
   串口和同一会话。以 `purge=0` 停止，核对租约归零与可写 Flash 已释放。

[验证摘要](summary.json)保存同一探针在旧运行时上的失败和新运行时的
结果，以及原版 All day watch 0.3.8 的独立浅睡回归。
[RC_FAST_D256 定时深睡](https://github.com/m5agent/agent-work-logs/blob/122ba36b10b565de62db2fc089beb00943b45dc5/records/esp-emulator/2026-11-18-sticks3-rtc-deep-sleep/followups/2026-11-18-sticks3-d256-deep-sleep/README.md)以同源探针通过两次独立回放。用 `CONFIG_RTC_CLK_SRC_INT_8MD256=y` 选择分频内部慢钟，运行期间在挂起的两次查询之间读取 RTC 选择器。复验范围为定时唤醒、RTC 保留和同会话 HTTP 复位。EXT0/EXT1、ULP、touch、外部慢钟、其他 RTC RAM 电源域组合和物理功耗仍待验证。
