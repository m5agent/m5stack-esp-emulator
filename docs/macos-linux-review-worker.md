# macOS 托管 Linux 审核 Worker

最近核对：`2026-11-19`。

这个组件在 Apple Silicon macOS 上启动无网卡的 Linux 虚拟机，将专用 IPv4 回环入口经 Virtio VSOCK 接到来宾中的 Device Service。Reviewer 通过令牌、固定 Worker 身份和 OpenAPI 摘要选择该入口。原版固件的准入仍由 Reviewer 和来宾策略决定。

宿主控制器、Swift 运行器和安装命令由本仓库维护。Linux 内核、initrd、离线 Debian 依赖、来宾运行时和审核夹具由操作者提供已验证的输入。安装时复制这些输入并重新核对 SHA-256。清单记录读取到的内容，资格证据由该批输入的原版虚拟设备验证提供。

## 准备安装

- 使用 Apple Silicon macOS 26 或更新版本和 Xcode 命令行工具构建 ARM64 运行器。仓库工具用 Python 3.12 或更新版本执行。LaunchAgent 使用系统 Python，宿主网络转发另用已验证的指定解释器。
- 准备已有资格的 `pinned` 和 `scenario` 目录。`pinned` 包含 `cloud-kernel` 和 `readonly-share/`，后者包含 Linux 根文件系统、离线依赖和运行时。`scenario` 包含 `vsock-initrd.img`、`host-relay.py` 和 `scenarios/` 来宾审核输入。保留一份已验证输入的来源、清单和证据。
- 选择 LaunchAgent 能访问的本机私有目录、独立实例名和未占用的回环端口。安装要求新目录，后续启停使用同一目录和令牌。启动预留空间为 4 GiB 加 180 MiB。

## 构建、封存及安装

以下变量由操作者提前设定。`RELAY_PYTHON` 应是解释器的规范路径，例如可执行文件本身。`DEVICE_SOURCE` 和 `DEVICE_OPENAPI_SHA256` 来自该套来宾输入的资格记录。

```sh
tool=platform/tools/macos_linux_worker
python3 "$tool/build_runner.py" --output "$RUNNER"
python3 "$tool/install.py" manifest \
  --pinned "$PINNED" --scenario "$SCENARIO" --output "$PAYLOAD_MANIFEST" \
  --device-source "$DEVICE_SOURCE" --device-openapi-sha256 "$DEVICE_OPENAPI_SHA256"

python3 "$tool/install.py" stage \
  --package "$PACKAGE" --instance "$INSTANCE" --port "$WORKER_PORT" \
  --pinned "$PINNED" --scenario "$SCENARIO" --payload-manifest "$PAYLOAD_MANIFEST" \
  --payload-manifest-sha256 "$PAYLOAD_SHA256" \
  --runner "$RUNNER" --runner-sha256 "$RUNNER_SHA256" \
  --relay-python "$RELAY_PYTHON" --relay-python-sha256 "$RELAY_PYTHON_SHA256"
```

从构建和封存命令的 JSON 输出保存 `runner_sha256` 和 `sha256`，使用已核对的解释器摘要。安装创建新控制令牌、空结果卷、固定清单和 LaunchAgent 定义，完成签名、资产及布局预检。命令输出只含安装状态和摘要。

## 就绪与审核准入

```sh
python3 "$tool/install.py" control --package "$PACKAGE" check
python3 "$tool/install.py" control --package "$PACKAGE" start
python3 "$tool/install.py" control --package "$PACKAGE" status
```

启动返回 `worker_ready: true` 后，从认证的 `/api/v1/worker` 读回 `worker_id`，从认证的 `/api/v1/openapi.yaml` 核对摘要。无需复制或输出令牌，文件在 `$PACKAGE/$INSTANCE/scenarios/control-token`。使用这些值配置 Reviewer 的 `managed_linux_worker`。先运行该配置允许的原版保存快照 dry-run，再核对同一会话的固件、输入、输出和证据。

Reviewer 0.31 支持 `POST /api/reviews/{job_id}/snapshots`。指定
`sourceMode=saved_snapshot`、独立的 `idempotencyKey` 和需要的验证选项，即可从
原任务保存的 BIN 和描述生成新 dry-run。使用返回的新任务 ID 查状态和证据，
原任务的终态、事件和证据入口保持可读。遇到响应丢失时，以原请求和同一键重发。

常驻 [Core2 2048 独立复审](validation-ledger.md#2026-11-19-常驻-linux-的-core2-独立复审)已由 `core2_2048` 放行并核对真实四向棋盘变化。调用方可先读 Reviewer 的 `/api/ready/linux-snapshot`，确认目标档案已准入再创建任务。

原版 CardputerDict ADV 发音复审使用 Worker 档案 `cardputer_adv_pronunciation`。
请求中的 `validation.cardputerdict_pronunciation` 为 `{"expect":"playback"}`，
`validation.storage.sd_image_artifact_id` 指向同一 Worker 的已验证 SD 种子。
`cardputerdict_pronunciation_ipv4` 使用同一封存包批准的两处固定服务地址。配置切换
前，使用目标版本的 Reviewer 配置解析器核对完整候选。发起复审前，从运行器和
Device Service 实际使用的共享卷核对可用空间，为固件、可写 Flash 和证据留出余量。

来宾没有直接网络接口。需要联网的已验证快照使用原有受控转发策略。这个路径的证据覆盖所用固件和策略，虚拟结果的范围见[原版审核证据台账](validation-ledger.md#2026-11-19-reviewer-的-linux-保存快照分流)。

## 正常排空与故障处理

暂停新审核时将 Reviewer 的 `admit` 设为空数组，同时保留入口与 Worker 绑定供旧审核恢复。请求正常排空，等待 `status` 显示 `stopped`，再卸载 LaunchAgent。现有会话可在排空期间继续读证据。

```sh
python3 "$tool/install.py" control --package "$PACKAGE" drain
python3 "$tool/install.py" control --package "$PACKAGE" status
python3 "$tool/install.py" control --package "$PACKAGE" unload
```

LaunchAgent 由操作者在当前图形登录域显式启动。进程突然退出后，控制器撤下入口并隔离卷。`quarantined` 状态允许在控制器退出后卸载作业，保留原卷和证据。原卷普通启动需要已确认的停机状态。需要清理隔离卷时，按[可信恢复契约](device-service-api.md#recover-an-interrupted-reviewer-session-create)取得恰当的停机和资源回收证据。
