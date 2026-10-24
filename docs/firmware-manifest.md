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
- 含 `espefuse.py summary --format json` 输出（`efuse-summary.json`）的包；
- 单个 sparse/merged bin；
- 带 ELF、MAP、sdkconfig、SPDX/CycloneDX SBOM、license/provenance 的包目录。

导入器会：

1. 校验 ZIP 路径穿越、文件数和解压后总大小；
2. 校验 segment 偏移不重叠且不越界；
3. 将 sparse merged 镜像补齐为目标设备完整 Flash；
4. 分析 bootloader、partition table、app image 和 app descriptor；
5. 从 data partition 识别 LittleFS/FAT/SPIFFS，枚举文件路径、大小、SHA256、
   脚本/证书/配置类型、敏感路径和 SPDX 许可证声明；
6. 静态扫描 URL、凭据特征、私钥标记和高熵编码块，并汇总 SBOM；
7. 生成完整镜像、资源副本和 `*.manifest.json`；
8. 分层记录镜像、sdkconfig、分区 flag 和可选 eFuse summary 的安全证据；
9. 汇总 provenance、文件系统 SPDX 和 SBOM 的许可声明，执行显式
   allowlist/denylist 决策；
10. 在已知 `device_id` 时检查 SoC、Flash、PSRAM、安全配置和所需
    capabilities。

## Manifest 结构

核心字段：

| 字段 | 作用 |
| --- | --- |
| `artifact` | 规范化完整镜像或分段 artifact 的路径、大小、SHA256 |
| `target` | SoC、chip ID、Flash、PSRAM、分区表、应用描述 |
| `target.filesystems` | LittleFS/FAT/SPIFFS 分区、文件路径/大小/SHA256、敏感路径和许可证声明 |
| `security` | 安全启动、Flash Encryption、配置态、eFuse 摘要和 secure version 边界 |
| `provenance` | M5Burner ID、版本、来源 URL/类型、license |
| `resources` | ELF、MAP、sdkconfig、flasher args、SBOM |
| `capabilities.required` | 目标设备必须提供的能力 |
| `review` | 脱敏 URL、凭据/私钥特征、高熵编码块、SBOM 摘要 |
| `license_policy` | 声明来源、allowlist/denylist、发现值、决策、findings、覆盖边界 |
| `validation` | 结构化 `errors[]` / `warnings[]` |

JSON 中不写宿主绝对路径；`file` 均为输出目录内相对文件名。

## 安全证据分层

`security.secure_boot` 和 `security.flash_encryption` 表示当前可取得的最高优先级
证据结论；来源必须结合以下字段解释：

| 证据层 | 字段 | 能证明什么 |
| --- | --- | --- |
| 镜像 | partition `flags`、app descriptor `secure_version` | 镜像声明、加密分区标记和 anti-rollback version |
| sdkconfig | `secure_boot_config`、`flash_encryption_config` | 构建配置原本要求什么，不证明设备实际启用了什么 |
| eFuse summary | `efuse`、`efuse_summary` | 包提供的一份 `espefuse` 读取结果声称设备状态是什么 |
| 真机运行态 | 当前 manifest 不包含 | 必须由同设备、同安全配置的独立真机验证提供 |

生成可导入的 eFuse 证据：

```bash
espefuse.py --chip esp32s3 summary --format json > efuse-summary.json
```

导入器只提取下述非秘密字段，原 JSON 不复制到输出目录：

- `ABS_DONE_0/1`、`SECURE_BOOT_EN`；
- `SPI_BOOT_CRYPT_CNT`；
- `SECURE_VERSION`；
- `KEY_PURPOSE_0..7` 的用途名称；
- 安全启动与 Flash Encryption 的 write-disable 状态；
- 原文件 SHA256 和字段数。

不含 eFuse summary 时，eFuse 状态仍为 `not-included`，安全启动/加密状态只能
由 sdkconfig 和镜像标记推断。包含 summary 时也只标记
`efuse_summary_unverified`：包内 JSON 可以由调用者伪造，不是从真机实时读取。
Device Service 仍拒绝启用 secure boot 或 Flash Encryption 的镜像，因为当前
QEMU profile 没有建模对应的密钥和启动链。

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

## 许可声明策略

Manifest 不把“看到 MIT 字符串”写成法律合规结论。`license_policy` 只评估包内
可审计的声明来源：

- provenance sidecar 的 `license`；
- LittleFS/FAT/SPIFFS 清单中的 SPDX `declared_licenses`；
- SPDX/CycloneDX SBOM 中的 license 字段。

CLI 可建立显式策略：

```bash
python3 platform/tools/firmware_manifest.py /path/to/firmware.bin \
  --out-dir /tmp/m5-firmware \
  --allow-license MIT \
  --allow-license Apache-2.0 \
  --deny-license GPL-3.0-only
```

状态语义：

| 状态 | 含义 |
| --- | --- |
| `PASS` | 至少发现一个具体声明，且所有发现值都在显式 allowlist 内、未被 denylist 命中 |
| `REVIEW_REQUIRED` | 未配置 allowlist、没有声明或存在 `NONE`/`NOASSERTION`/`unknown` |
| `REJECTED` | 命中 denylist，或发现值不在 allowlist 内；Manifest validation 同步为 `REJECTED` |

`license_policy.limits` 固定声明该结果不是法律意见，也不是完整源码级许可证
扫描。文件系统记录 `permissions=not-recorded`，因此“运行时文件权限”仍是
`NOT RUN`，不能由许可策略结果推断。

## 文件系统清单

当前支持矩阵：

| 文件系统 | 当前行为 | 证据 / 边界 |
| --- | --- | --- |
| LittleFS | 只读挂载、目录/文件清单、大小、SHA256、敏感路径脱敏、SPDX 提取 | 真实 StickS3 UIFlow2 `sys`/`vfs` 分区 PASS |
| FAT12/16/32 | 只读 BPB/FAT 解析、目录递归、LFN、文件 SHA256、敏感路径和 SPDX | 合成 FAT12/16/32 与真实 PaperColor FAT12 样本；不挂载宿主文件系统 |
| SPIFFS | 只读 LUT/对象查找/索引/数据页解析、文件路径/大小/SHA256、敏感路径和 SPDX | ESP-IDF canonical `spiffsgen.py` 镜像和 8 个声明的自包含多索引配置；只支持下表明确列出的 little-endian、默认未对齐 object-index 布局 |

LittleFS 数据分区的具体行为：

- 从 merged/segmented flash 的 data partition 直接挂载；
- 自动尝试常见 block size，并记录实际 block size/count；
- 为每个常规文件记录路径、大小、SHA256、类型和
  `permissions=not-recorded`；
- 对 `.key`、`.env`、credential/secret 等敏感路径只保留脱敏标记、
  路径哈希和内容哈希；
- 从 LICENSE/NOTICE/COPYING 文件提取 `SPDX-License-Identifier`；
- 文件数、目录数达到上限时显式记录 truncation。

FAT 解析器：

- 校验 bytes/sector、sectors/cluster、reserved/FAT/root/data 几何和 FAT 表容量；
- 支持 FAT12、FAT16、FAT32 cluster chain 与 FAT32 root cluster；
- 校验 LFN sequence/checksum，异常时回退 8.3 名称；
- 拒绝循环链、越界 cluster、bad/free cluster、无效子目录和超限目录项；
- 对 0x00/0xFF 全填充的 FAT 分区返回 `UNFORMATTED`，不伪造空文件清单；
- 对截断、表不一致或无效 boot sector 返回 `INVALID/PARTIAL`；
- 不挂载或执行镜像，不恢复已删除文件，也不检查文件 slack space。

SPIFFS 解析器：

- 从 data partition 扫描 active object-index page，不挂载或执行镜像；
- 自动尝试 page size `256/512`、block size `4096/65536`、object-name
  length `32/64` 与 metadata length `4/0` 的 8 个声明组合，并记录
  `config_attempts`；
- 对每个候选按完整对象数、有效 data page、index page 和 object 数评分，
  避免 4096/65536 block 同时看似可解析时被第一个候选误选；
- 校验每页对应的 block LUT object ID、index/data page object ID、span、
  flags、data page 顺序和页号范围；LUT 与 page header 不一致的页不会被
  当成文件；
- 按 object index 顺序拼接 data page，记录文件大小、SHA256 和类型；
- 支持跨多个 object-index page 的文件，并记录 index/data page 数量；
- 对 `.key`、`.env`、credential/secret 路径只保留脱敏标记和路径哈希；
- 对 erased 分区返回 `UNFORMATTED`，无法识别时返回 `INVALID`，不猜测文件名；
- 暂不声明 big-endian，或
  `SPIFFS_ALIGNED_OBJECT_INDEX_TABLES=1` 的镜像；
- 不恢复已删除对象，也不执行镜像中的代码。

LittleFS/FAT/SPIFFS 都不记录 Unix mode，因此运行时文件权限仍为 `NOT RUN`。
LittleFS 清单依赖 `littlefs-python`；依赖缺失时返回 `UNAVAILABLE`，不会
自动格式化或改写输入镜像。

## 可恢复流式上传

Device Service 现在还接受不把完整 artifact 放进 JSON/base64 的 chunk
上传：

1. `POST /api/v1/artifact-uploads` 声明 expected size 和 final SHA256；
2. `POST /api/v1/artifact-uploads/<id>/chunks` 追加 ≤8 MiB 的连续 raw
   chunk，`X-Chunk-Offset` 必须等于当前 received bytes，
   `X-Chunk-SHA256` 必须匹配 chunk body；
3. `GET /api/v1/artifact-uploads/<id>` 返回已接收字节和
   `next_offset`，可连接中断后续传；
4. `POST /api/v1/artifact-uploads/<id>/complete` 验证 total size 和完整
   SHA256，再原子发布普通 content-addressed artifact；
5. `DELETE /api/v1/artifact-uploads/<id>` 清理未完成 staging 文件。

chunk 只在请求期间进入内存，staging artifact 直接顺序写盘；最终 manifest
仍引用普通 artifact，不引入第二种下游格式。

每次 append 先写 staging 再原子替换 upload metadata；任何写入、`fsync` 或
metadata 提交失败都会把 part 截断回最后一个已确认 offset，客户端可重新
`GET` 后从 `next_offset` 续传。未完成上传、孤立 staging 文件和过期完成
记录由 storage janitor 按 `M5_SERVICE_CACHE_GRACE` 回收。

浏览器入口是 `/platform/web/firmware.html`：

- 流式计算完整 SHA256，不把整个固件一次性读入内存；
- 4 MiB chunk、进度、瞬态重试、取消和 staging 清理；
- 上传完成后调用 `POST /api/v1/firmware/import`，服务端执行同一套
  WebBurner/M5Burner/ESP-IDF 导入、文件系统审查、安全检查和 capability
  mismatch；
- 上传完成后的 artifact 可以刷新后直接继续 import；
- 未完成上传刷新后会保留 upload ID，浏览器重新选择同一文件并校验内容后
  从已确认 offset 续传。

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
      "secure_boot_config": "unknown",
      "flash_encryption_config": "unknown",
      "efuse": "not-included",
      "efuse_summary": null
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
证明 LittleFS 路径；文件中的 `fat_inventory=NOT RUN` 是该次只含
LittleFS 样本的历史边界，FAT 支持由下面的独立 follow-up evidence 证明。

FAT 证据：
[`tests/firmware/evidence-2026-10-24-fat-inventory.json`](../tests/firmware/evidence-2026-10-24-fat-inventory.json)
包含：

- 合成 FAT12/FAT16/FAT32 的 LFN、嵌套目录、多簇文件、敏感 `.key` 路径、
  SPDX 和 manifest round-trip；
- 循环 cluster chain 被标记 `PARTIAL`，不会错误 PASS；
- 全 0xFF 的 FAT 分区被标记 `UNFORMATTED`；
- 真实 PaperColor FAT12 样本解析出 11 个 PNG 文件及其 SHA256；一个未初始化的
  `System Volume Information` 子目录被安全拒绝，所以该样本整体保持 `PARTIAL`。

SPIFFS 证据：
[`tests/firmware/evidence-2026-10-24-spiffs-inventory.json`](../tests/firmware/evidence-2026-10-24-spiffs-inventory.json)
记录：

- 8 个声明配置均有自包含回归，每个配置的主文件跨多个 object-index page；
- ESP-IDF v5.5.4 `spiffsgen.py` canonical 镜像完成 LUT 校验、文件哈希、
  SPDX 和敏感路径脱敏；
- 60000-byte canonical 多索引文件从 3 个 index page 拼接 240 个 data
  page，SHA256 与输入一致；
- LUT mismatch、随机损坏和 erased 分区分别得到确定结果，不抛异常也不产生
  伪造文件；
- FirmwareManifest integration 不序列化敏感文件原始路径。

## 边界

- 镜像文件本身不能证明 eFuse/OEM key 状态；
- 没有 sdkconfig 且没有可解析 eFuse 证据时，安全启动/Flash Encryption
  只能是 `unknown`；
- 包内 eFuse summary 是自报证据，必须记录来源哈希，并保持
  `efuse_summary_unverified`；
- eFuse summary 中的 key material / raw value 不进入 manifest 或规范化输出；
- 分区 flag 的 encrypted bit 是镜像声明，不等于运行态 key 完整；
- ELF/MAP 只用于符号化，不证明固件来源；
- SBOM 存在只证明包内声明，不证明组件版本或许可证声明真实；
- URL/凭据/高熵扫描是启发式审查，压缩资源可能产生待人工确认项；
- manifest 中不得出现凭据、私钥、URL query/fragment 或编码载荷明文；
- license/provenance 缺失不会自动变成合法授权；
- 真机安全启动、Flash Encryption 和生产 key 流程仍须真机验证。

文件系统内容清单已经覆盖 LittleFS、FAT12/16/32 和常见 ESP-IDF SPIFFS
配置；声明级许可 allowlist/denylist 已实现。仍未完成的是运行时文件权限、
完整源码级许可扫描、证书审批和具有法律效力的产品级许可结论。
