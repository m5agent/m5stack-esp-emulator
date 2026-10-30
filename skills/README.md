# Agent skills

部署 Device Service 后，Agent 可以通过这里的 skill 使用模拟器。helper 在 Agent
所在机器运行，通过 HTTP 连接服务；Agent 机器不需要本仓库、QEMU、ROM 或固件缓存。

| Skill | 适用对象 | 范围 |
| --- | --- | --- |
| [m5stack-esp-emulator](m5stack-esp-emulator/SKILL.md) | 通用 Agent / 自行部署服务的用户 | 设备与 Unit 发现、通用固件上传/合成/Manifest、session、串口/画面/交互/QOM、网络与 Flash 取证、历史与清理；UIFlow 是其中一个专用路径 |
| [uiflow2-simulator](uiflow2-simulator/SKILL.md) | AIFlow UIFlow2 Coding Agent | 完整 Python 模块/资源 checkpoint、同 guest Preview/Run、错误诊断和 UI 迭代，遵循 AIFlow 自身的部署确认流程 |

二者分别携带完整 helper 和参考文件，可单独复制。通用版没有 AIFlow 的
`deploy_mode`、真实设备 ID、Client ID 或推送接口依赖；它也不把所有固件当作
UIFlow。AIFlow 版保留原技能名 `uiflow2-simulator`，与现有选择器兼容，快照来源与
差异记录在 [source.json](uiflow2-simulator/source.json)。原 AIFlow 仓库不因本次分发
而改变。

两套都能在创建时挂接已准入的传感器 Unit，并在同一会话运行中修改其已建模环境
输入。例如 ENV III 的温度、湿度和气压；参考文件给出了初值、实时变化、恢复与
guest 读数/画面验证流程。接线变更需新建会话，输入值不会自动传播到其它传感器。

## 使用和配置

将所需的**整个 skill 目录**复制到 Agent 支持的 skills 目录，让其加载 `SKILL.md`。
不要只复制 Markdown，丢下 `scripts/` 和 `references/`。两份 CLI 当前支持
macOS/Linux 和 Python 标准库：通用版要求 Python 3.10+，AIFlow 版要求 Python 3.9+。
其他平台可依据包内 HTTP 参考使用自己的 API 客户端。

| 配置 | 通用版 | AIFlow 版 |
| --- | --- | --- |
| 服务 origin，必须明确提供 | `M5_EMULATOR_BASE_URL` | `AIFLOW_SIMULATOR_BASE_URL` |
| 私有控制 Token 文件 | `M5_EMULATOR_TOKEN_FILE` | `AIFLOW_SIMULATOR_TOKEN_FILE` |
| 环境中的 Token，可选替代 | `M5_EMULATOR_TOKEN` | `AIFLOW_SIMULATOR_TOKEN` |
| 用户可访问的网页 origin，可选 | `M5_EMULATOR_PUBLIC_URL` | `AIFLOW_SIMULATOR_PUBLIC_URL` |

origin 不带 `/api/v1` 后缀。地址和 Token 由部署者单独配置，分发包不带本机 IP、
`config.local.json`、`.env`、真实凭据、ROM 或固件。远端服务的 Token 文件必须是
Agent 所在机器可读的文件，不是另一台主机的路径。HTTP 允许 loopback 和明确
配置的 RFC1918 IPv4；其他目的地使用 HTTPS。

例如，在已配置上述环境的 Agent 工作目录中：

```bash
python3 <skill-dir>/scripts/emulator.py discover
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json create --json session.json
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json observe --frame
python3 <skill-dir>/scripts/emulator.py --state .m5-emulator/run.json stop
```

`<skill-dir>` 替换为已安装通用 skill 的目录；固件、session 请求和高级操作见其
包内参考。API 成功或 VM `running` 不表示应用功能通过，必须检查真实 guest 行为。

AIFlow 原生接入还要求服务将原名称加入候选 skill，并为配置的服务 origin 精确
开放运行时网络访问。当前上游采用 `deploy_mode=agent` 的两任务确认流程：先运行
和报告预览，后续用户明确确认后再检查代码一致性并推硬件；`none` 不开放模拟器，
`server` 会自动推送。其他版本必须核对实际加载器与部署策略，不能靠 skill 文字
暂停服务端的自动推送。

## 验证与打包

仓库使用 `catalog.json` 的明确文件白名单构建独立 ZIP；未列入的 local config、
cache 和测试产物不会被收集。每包只有一个同名顶层目录，并带文件 SHA256 清单和 MIT 许可。

```bash
python3 platform/tools/agent_skills.py --check
python3 platform/tools/agent_skills.py --out-dir dist/agent-skills
PYTHONPATH=platform/tools python3 -m unittest discover -s platform/tests -p 'test_*skill*.py'
```

仓库检查和 Device Service 请使用项目支持的 Python 3.12。ZIP 位于 ignored
`dist/`，不需要把生成包、原始日志或二进制提交到源码 Git。这里生成本地文件，
不会上传 Skill Hub、安装全局 skill 或发布 release。

更新 AIFlow 快照前先比对 `source.json` 的来源哈希，并检查上游部署模式/技能
选择策略；保留干净配置和独立 helper，重新运行契约、复制后运行与分发测试。
通用 API 参考以当前 OpenAPI 和服务实现为依据，不从 AIFlow 的有限需求反推
整个模拟器的能力。

## 验证服务边界

本仓库的 Agent 功能测试必须使用独立 Device Service：单独端口、state 目录与
控制 Token。`8787` 属于用户测试服务，不能用它跑 Agent 测试，也不能为测试停止
或重启它。分发包默认不选择任何服务；其他用户使用其部署者明确授权的 endpoint。

两包都只做虚拟设备工作。真实硬件烧录、审批/发布固件、服务/worker 管理和公共
暴露不是本次 simulation 的隐含权限。设备、固件、Unit 准入和 functional PASS
仍按各自证据判断；不同型号、固件或 runtime 不继承结论。
