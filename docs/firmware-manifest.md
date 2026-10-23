# 固件清单与 WebBurner 导入

日期：`2026-10-23`

## 目标

把 M5Burner 下载物、WebBurner/ESP Web Tools 的 part 列表、ESP-IDF
`flasher_args.json` 或显式 merged/segmented 输入，规范化为同一个完整虚拟
Flash 和版本化 manifest。manifest 只记录可核验事实；镜像本身无法证明的
eFuse、安全启动和 Flash Encryption 状态保持 `unknown`。

Schema：

- `platform/tools/firmware_manifest.schema.json`
- `platform/tools/firmware_manifest.py`

## 导入

```bash
python3 platform/tools/firmware_manifest.py /path/to/firmware.bin \
  --out-dir /tmp/m5-firmware --print summary
```

支持输入：

- 带同名 `.json` provenance sidecar 的 M5Burner `.bin`；
- WebBurner `manifest.json` 的 `builds[].parts[]`；
- 含 `flasher_args.json` 的 ESP-IDF 构建目录/ZIP；
- 单个 sparse/merged bin；
- 带 ELF、MAP、sdkconfig、license/provenance 的包目录。

导入器会：

1. 校验 ZIP 路径穿越、文件数和解压后总大小；
2. 校验 segment 偏移不重叠且不越界；
3. 将 sparse merged 镜像补齐为目标设备完整 Flash；
4. 分析 bootloader、partition table、app image 和 app descriptor；
5. 生成完整镜像、资源副本和 `*.manifest.json`；
6. 在已知 `device_id` 时检查 SoC、Flash、PSRAM、安全配置和所需 capabilities。

## Manifest 结构

核心字段：

| 字段 | 作用 |
| --- | --- |
| `artifact` | 规范化完整镜像或分段 artifact 的路径、大小、SHA256 |
| `target` | SoC、chip ID、Flash、PSRAM、分区表、应用描述 |
| `security` | 安全启动、Flash Encryption、eFuse 和 secure version 边界 |
| `provenance` | M5Burner ID、版本、来源 URL/类型、license |
| `resources` | ELF、MAP、sdkconfig、flasher args |
| `capabilities.required` | 目标设备必须提供的能力 |
| `validation` | 结构化 `errors[]` / `warnings[]` |

JSON 中不写宿主绝对路径；`file` 均为输出目录内相对文件名。

## Device Service

先上传规范化完整镜像，再创建 `kind=manifest` firmware：

```json
{
  "device_id": "sticks3",
  "kind": "manifest",
  "manifest": {
    "schema_version": 1,
    "kind": "m5stack-firmware-manifest",
    "artifact": {
      "kind": "merged-flash",
      "file": "firmware-flash.bin",
      "artifact_id": "<sha256>",
      "size": 8388608,
      "sha256": "<sha256>"
    },
    "target": {"soc": "esp32s3", "flash_size": 8388608},
    "security": {
      "secure_boot": "unknown",
      "flash_encryption": "unknown",
      "efuse": "not-included"
    },
    "provenance": {
      "importer": "m5stack-firmware-manifest/1",
      "source_format": "merged-bin"
    },
    "validation": {"status": "PASS", "errors": [], "warnings": []}
  }
}
```

服务会重新核对 artifact hash/size、目标 Flash、SoC/PSRAM 和 capabilities。
若模型缺少固件要求的能力，返回：

```json
{
  "error": {
    "code": "unsupported_firmware_capability",
    "issues": [
      {
        "code": "unsupported_capability",
        "requirement": "camera",
        "available": ["wifi", "display", "audio"]
      }
    ]
  }
}
```

这类错误表示 **设备 profile 覆盖不足**，不是固件崩溃。

## 已验证样本

已使用缓存中的三个真实公开固件完成 round-trip：

| 样本 | 类型 | 结果 |
| --- | --- | --- |
| UIFlow2 StickS3 `1897200000000001693` | 8 MiB sparse merged | PASS，规范化 8 MiB |
| CYBER CLOCK `1897200000000003332` | 1.3 MiB sparse merged | PASS，补齐 8 MiB |
| StickS3 Weather `2108939572843147265` | 7.9 MiB sparse merged | PASS，补齐 8 MiB |

对 StickS3 声明 `camera` capability 时，Device Service 返回结构化
`unsupported_firmware_capability`，未创建 session。

## 边界

- 镜像文件本身不能证明 eFuse/OEM key 状态；
- 没有 sdkconfig 时安全启动/Flash Encryption 只能是 `unknown`；
- 分区 flag 的 encrypted bit 是镜像声明，不等于运行态 key 完整；
- ELF/MAP 只用于符号化，不证明固件来源；
- license/provenance 缺失不会自动变成合法授权；
- 真机安全启动、Flash Encryption 和生产 key 流程仍须真机验证。
