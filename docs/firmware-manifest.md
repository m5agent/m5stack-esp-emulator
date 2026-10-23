# 固件清单与 WebBurner 导入

日期：`2026-10-24`

## 目标

把 M5Burner 下载物、WebBurner/ESP Web Tools 的 part 列表、ESP-IDF
`flasher_args.json` 或显式 merged/segmented 输入，规范化为同一个完整虚拟
Flash 和版本化 manifest。manifest 只记录可核验事实；镜像本身无法证明的
eFuse、安全启动和 Flash Encryption 状态保持 `unknown`。静态审查输出只保留
脱敏指纹，不把镜像中的 URL query、凭据或编码载荷明文写入 manifest。

Schema：

- `platform/tools/firmware_manifest.schema.json`
- `platform/tools/firmware_manifest.py`
- `platform/tools/firmware_static_review.py`

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
- 带 ELF、MAP、sdkconfig、SPDX/CycloneDX SBOM、license/provenance 的包目录。

导入器会：

1. 校验 ZIP 路径穿越、文件数和解压后总大小；
2. 校验 segment 偏移不重叠且不越界；
3. 将 sparse merged 镜像补齐为目标设备完整 Flash；
4. 分析 bootloader、partition table、app image 和 app descriptor；
5. 从 data partition 识别 LittleFS，枚举文件路径、大小、SHA256、脚本/证书/
  配置类型、敏感路径和 SPDX 许可证声明；
6. 静态扫描 URL、凭据特征、私钥标记和高熵编码块，并汇总 SBOM；
7. 生成完整镜像、资源副本和 `*.manifest.json`；
8. 在已知 `device_id` 时检查 SoC、Flash、PSRAM、安全配置和所需 capabilities。

## Manifest 结构

核心字段：

| 字段 | 作用 |
| --- | --- |
| `artifact` | 规范化完整镜像或分段 artifact 的路径、大小、SHA256 |
| `target` | SoC、chip ID、Flash、PSRAM、分区表、应用描述 |
| `target.filesystems` | LittleFS 分区、文件路径/大小/SHA256、敏感路径和许可证声明 |
| `security` | 安全启动、Flash Encryption、eFuse 和 secure version 边界 |
| `provenance` | M5Burner ID、版本、来源 URL/类型、license |
| `resources` | ELF、MAP、sdkconfig、flasher args、SBOM |
| `capabilities.required` | 目标设备必须提供的能力 |
| `review` | 脱敏 URL、凭据/私钥特征、高熵编码块、SBOM 摘要 |
| `validation` | 结构化 `errors[]` / `warnings[]` |

JSON 中不写宿主绝对路径；`file` 均为输出目录内相对文件名。

## 静态审查

导入器始终写入 `review`。旧版 v1 manifest 可以不带该字段，保持向后兼容。

```json
{
  "review": {
    "schema_version": 1,
    "status": "REVIEW_REQUIRED",
    "coverage": {
      "bytes_scanned": 8388608,
      "strings_scanned": 52240,
      "url_count": 22,
      "credential_finding_count": 3,
      "encoded_blob_count": 1
    },
    "urls": [
      {
        "scheme": "https",
        "host": "example.com",
        "url_sha256": "<sha256>",
        "path_sha256": "<sha256>",
        "offset": 1234,
        "length": 64
      }
    ],
    "encoded_blobs": [],
    "findings": [
      {
        "code": "credential_like_material",
        "category": "private-key",
        "severity": "critical",
        "message": "credential-like material detected; value is redacted",
        "offset": 4567,
        "evidence_sha256": "<sha256>"
      }
    ],
    "sbom": {
      "status": "PASS",
      "format": "spdx-json",
      "spec_version": "SPDX-2.3",
      "component_count": 12,
      "licenses": ["Apache-2.0", "MIT"]
    },
    "limits": {
      "strings_truncated": false,
      "urls_truncated": false,
      "credentials_truncated": false,
      "encoded_blobs_truncated": false,
      "findings_truncated": false
    }
  }
}
```

`REVIEW_REQUIRED` 表示有人需要查看脱敏 finding；它不自动等于恶意固件，也不会
绕过 SoC/capability 的兼容性检查。

## 文件系统清单

当前支持矩阵：

| 文件系统 | 当前行为 | 证据 / 边界 |
| --- | --- | --- |
| LittleFS | 只读挂载、目录/文件清单、大小、SHA256、敏感路径脱敏、SPDX 提取 | 真实 StickS3 UIFlow2 `sys`/`vfs` 分区 PASS |
| FAT12/16/32 | 分区可识别，但内容清单返回 `UNSUPPORTED` | 尚未实现只读 parser；不能用“挂载失败”冒充 `PASS` |
| SPIFFS | 分区可识别，但内容清单返回 `UNSUPPORTED` | 尚未实现可审计 host parser；不能根据文件名/字符串猜测 |

LittleFS 数据分区的具体行为：

- 从 merged/segmented flash 的 data partition 直接挂载；
- 自动尝试常见 block size，并记录实际 block size/count；
- 为每个常规文件记录路径、大小、SHA256、类型和
  `permissions=not-recorded`；
- 对 `.key`、`.env`、credential/secret 等敏感路径只保留脱敏标记、
  路径哈希和内容哈希；
- 从 LICENSE/NOTICE/COPYING 文件提取 `SPDX-License-Identifier`；
- 文件数、目录数达到上限时显式记录 truncation。

SPIFFS 和 FAT 目前只做分区识别并返回 `UNSUPPORTED`，不会伪装成已解析。
LittleFS 不记录 Unix mode，因此文件权限仍为 `NOT RUN`。
LittleFS 清单依赖 `littlefs-python`；依赖缺失时返回 `UNAVAILABLE`，不会
自动格式化或改写输入镜像。

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

同一批公开样本也执行了脱敏静态审查：结构/capability validation 为 `PASS`，
review 状态为 `REVIEW_REQUIRED`，分别记录 URL、凭据特征、高熵编码块和
SBOM 缺失；输出 manifest 中未出现原始 query、凭据值或编码载荷。证据：
[`tests/firmware/evidence-2026-10-23-static-review.json`](../tests/firmware/evidence-2026-10-23-static-review.json)。
StickS3 UIFlow2 `sys`/`vfs` LittleFS 清单与哈希证据：
[`tests/firmware/evidence-2026-10-24-filesystem-inventory.json`](../tests/firmware/evidence-2026-10-24-filesystem-inventory.json)。
其中 `sys` 为 39 个文件、5 个目录、632603 bytes，`vfs` 为 17 个文件、
7 个目录、16306 bytes；两个分区均完成 manifest round-trip。该样本
证明 LittleFS 路径，不代表 FAT/SPIFFS 已支持。

## 边界

- 镜像文件本身不能证明 eFuse/OEM key 状态；
- 没有 sdkconfig 时安全启动/Flash Encryption 只能是 `unknown`；
- 分区 flag 的 encrypted bit 是镜像声明，不等于运行态 key 完整；
- ELF/MAP 只用于符号化，不证明固件来源；
- SBOM 存在只证明包内声明，不证明组件版本或许可证声明真实；
- URL/凭据/高熵扫描是启发式审查，压缩资源可能产生待人工确认项；
- manifest 中不得出现凭据、私钥、URL query/fragment 或编码载荷明文；
- license/provenance 缺失不会自动变成合法授权；
- 真机安全启动、Flash Encryption 和生产 key 流程仍须真机验证。

下一步先实现有严格文件/簇上限的只读 FAT12/16/32 解析和 fixture；
SPIFFS 要么实现窄范围只读 parser，要么从 ESP-IDF 源码构建可审计 helper，
在直接测试前保持 `UNSUPPORTED`。
