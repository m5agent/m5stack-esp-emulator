# Agent skills

Agent 可使用浏览器工作台预览固件画面，也可连接已部署的 Device Service 做更完整的联调。

| Skill | 适用对象 | 范围 |
| --- | --- | --- |
| [m5stack-esp-emulator](m5stack-esp-emulator/SKILL.md) | 通用 Agent / 自行部署服务的用户 | 设备与 Unit 发现、通用固件上传/合成/Manifest、session、串口/画面/交互/QOM、网络与 Flash 取证、历史与清理；UIFlow 是其中一个专用路径 |
| [uiflow2-simulator](uiflow2-simulator/SKILL.md) | AIFlow UIFlow2 Coding Agent | 完整 Python 模块/资源 checkpoint、同 guest Preview/Run、错误诊断和 UI 迭代，遵循 AIFlow 自身的部署确认流程 |
| [m5stack-browser-simulator](m5stack-browser-simulator/SKILL.md) | 可操作桌面 Chromium 的 Agent | 在 GitHub Pages 选择已准入设备，导入兼容的完整 Flash 镜像，运行、查看画面并停止 |

网页版使用浏览器 WASM，无需部署服务或配置 Token。服务版和 AIFlow 版分别携带
完整 helper 和参考文件，可单独复制。helper 在 Agent 机器上通过 HTTP 连接服务，
无需本地 QEMU、ROM 或固件缓存。通用版没有 AIFlow 的
`deploy_mode`、真实设备 ID、Client ID 或推送接口依赖；它也不把所有固件当作
UIFlow。AIFlow 版保留原技能名 `uiflow2-simulator`，与现有选择器兼容，快照来源与
差异记录在 [source.json](uiflow2-simulator/source.json)。原 AIFlow 仓库不因本次分发
而改变。

两套服务 Skill 都能在创建时挂接已准入的传感器 Unit，并在同一会话运行中修改其已建模环境
输入。以 ENV III 为例，参考文件给出了温度、湿度和气压的初值、实时变化、恢复与
guest 读数和画面验证流程。接线变更需新建会话，输入值不会自动传播到其它传感器。

## 使用和配置

将所需的**整个 skill 目录**复制到 Agent 支持的 skills 目录，让其加载 `SKILL.md`。
网页版只需按指南操作浏览器。通用服务版和 AIFlow 版需要保留 `scripts/` 和
`references/`。两份 CLI 在 macOS/Linux 上使用 Python 标准库。通用版要求 Python 3.10+，
AIFlow 版要求 Python 3.9+。其他平台可依据包内 HTTP 参考使用自己的 API 客户端。

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

## 验证边界

服务路径的 Agent 功能测试必须使用独立 Device Service，并配置单独端口、state 目录与
控制 Token。`8787` 属于用户测试服务，不能用它跑 Agent 测试，也不能为测试停止
或重启它。两套服务 Skill 由部署者明确指定 endpoint。浏览器路径使用独立标签页，
在当前运行中确认 guest 画面并停止该次运行。

三个 Skill 都只做虚拟设备验证。设备、固件和 Unit 准入以及功能结果按各自证据判断。
结果只适用于实际执行的设备、固件和 runtime。真实硬件烧录、固件审批与发布、
服务管理和公共暴露各需独立授权。
