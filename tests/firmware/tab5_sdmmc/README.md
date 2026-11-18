# Tab5 SDMMC 槽位 0

示例从 ESP-IDF v5.5.4（`735507283d5b2f9fb363a1901172dbd9e847945d`）的
`examples/storage/sd_card/sdmmc` 来。补丁使用官方 Tab5 BSP 的槽位 0、
CLK43、CMD44、D0–D3 GPIO39–42、4-bit 与板载 LDO4。该固件用于验证
原生 SDMMC 控制器和 Device Service 会话。PC98、UIFlow2 和实体卡行为各自验收。
[官方 Tab5 BSP](https://github.com/m5stack/M5Tab5-UserDemo/blob/fe8aa051beb9385468f7e46b909e764169df3f7a/platforms/tab5/components/m5stack_tab5/m5stack_tab5.c#L558-L630)

使用 ESP-IDF 安装的 ESP32-P4 工具链。保留仓库根目录为当前目录，
并使用可丢弃的独立构建目录。

```sh
source "${IDF_PATH}/export.sh"
probe_dir="${PWD}/.work/tab5-sdmmc"
mkdir -p "${probe_dir}"
cp -R "${IDF_PATH}/examples/storage/sd_card/sdmmc" "${probe_dir}/source"
(
  cd "${probe_dir}/source"
  patch -p1 < ../../../tests/firmware/tab5_sdmmc/vendor-fixture.patch
)
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" set-target esp32p4
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" build
idf.py -C "${probe_dir}/source" -B "${probe_dir}/build" merge-bin --fill-flash-size 16MB
python3 platform/tools/sd_image.py --out "${probe_dir}/blank.img" \
  --format fat16-superfloppy --size-mib 32
```

在独立 Device Service 中用 `/artifacts` 上传合并镜像和卡镜像，
用 `/firmware/import` 导入 Tab5 固件。通过导入结果获得规范化 SHA。
设置固定哈希的 esp-emu 1.1.0、Tab5 ROM、eFuse、C6 companion 和
原生 DSI 板型，并将规范化 SHA 加入独立服务的 DSI 准入列表。

1. 在 `POST /api/v1/sessions` 中提交 `device_id=tab5`、`runtime=qemu`
   和 `storage.sd_image_artifact_id`。等待串口的槽位接线、FAT 挂载、
   两个不同文件的写入/读回及卸载标记。
2. 导出会话证据 ZIP，再以 `purge=0` 停机。对照 ZIP 的存储收据和串口，
   使用停机 SD inventory 核对两个文件并导出修改后的镜像。
3. 用导出 artifact 启动第二个会话，并核对已复用同一输出镜像。示例会重写
   每个文件并读回。单独去掉 SD 字段可验收空卡槽。错误后端或待准入固件
   必须在创建会话前拒绝。
4. 核对原始卡镜像哈希及每次停止后的租约。Tab5 的片上 SDMMC 几何以
   esp-emu 1.1.0 的 512 KiB 容量单位为准。
   [官方命令行说明](https://github.com/espressif/esp-emulator/blob/v1.1.0/docs/guides/CLI.md#sd-card)

也可用本仓库的解析工具检查 ZIP 与停机导出：

```sh
PYTHONPATH=platform/tools python3 tests/firmware/tab5_sdmmc/verify_evidence.py   EVIDENCE_ZIP EXPORTED_SD_IMAGE SOURCE_SD_SHA256
```

[同会话验证](summary.json) · [容量正反对照](capacity-summary.json) · [Device Service API](../../../docs/device-service-api.md)
