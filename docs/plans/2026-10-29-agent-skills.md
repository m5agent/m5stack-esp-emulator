# Simulator Agent skills and portable distribution

日期：2026-10-29。归属 `UNIT-01` 的 Agent 调用入口，不修改运行时模型或服务契约。

目标：把既有 AIFlow UIFlow2 skill 的干净快照放进本仓库，同时给自行部署 Device
Service 的用户提供独立通用 skill。两个入口必须区分，通用入口不能依赖 AIFlow
部署模式、设备标识、项目工作区或本机地址。

交付边界：

- `skills/m5stack-esp-emulator`：通用固件、设备与 Unit 能力发现、固件上传/合成/
  Manifest、session、交互、网络/Flash 观测及 evidence；UIFlow Preview 是其中一个
  专用执行流程，不代表全部固件都能经 UART REPL 换代码。
- `skills/uiflow2-simulator`：保留 AIFlow UIFlow2 完整文件包、Preview/Run、
  错误与 UI 迭代、当前 `deploy_mode=agent` 的两阶段确认约束。保持原技能名以兼容
  AIFlow 选择器；快照可单独使用，不修改
  原 AIFlow 服务的运行配置或自动推送逻辑。
- 两包均独立携带所需 helper/参考文件，使用 operator 明确配置的服务与 Token；
  分发清单不包含 local config、真实地址、凭据、ROM、固件或测试 evidence。
- 明确 generic/qemu-unified、单独 network diagnostic、partial 模型、固件准入、
  同 guest 证据和 physical validation 的边界。

验证采用临时 recording HTTP server、独立复制后 CLI、确定性 ZIP 与边界负控；如需
真实虚拟设备验证，单独启动 Device Service，使用独立端口、state 与 Token。
不得把用户的 8787 服务用于 Agent 测试或为本任务重启它。

验收：两个 skill 元数据和 Markdown 链接有效；helper 请求、归属、模糊响应恢复、
证据先于关闭及凭据处理通过测试；目录和单独 ZIP 均可从任意工作目录运行；原
AIFlow skill 未改动，运行时与硬件能力声明不扩大。

## 本轮验证

两包通过 skill-creator 元数据检查与分发白名单检查；41 项新契约/打包测试通过，
覆盖 copied-directory 独立运行、generic session/Preview 幂等与失联恢复、
当前/历史帧区分、资源保留、会话归属、证据先于停止、lease 释放以及私有文件
不入 ZIP。两份独立 ZIP 可确定性重建，并附文件 SHA256 清单。

另在独立 loopback `18787`、独立 state/token 服务上，用通用 helper 的隔离 Python
运行完成 CoreS3 `qemu` 参考固件的 `uiflow-live` 会话、owned `/program`、真实
`APP_READY`、串口/frame/device-state、ZIP 和 `purge=0` 停止。print-only 程序的
320×240 帧为黑屏，不作为 UI 质量结论；虚拟 Flash/lease 已释放，历史保留，独立
server/QEMU 均退出。没有使用、停止或重启用户的 `8787` 服务。

该条固件 SHA 为 `0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`，
ZIP SHA 为 `0403ef64d0ef8c1170817624d6e3936d9aa3d7ad2df0d143325902cfe3b7f322`。
这是 Skill 客户端和该参考固件路径的限定验证；generic Arduino/ESP-IDF 的
segmented/net-fault 流程采用 recording HTTP 契约演练，不声明那些固件已实测。
没有重新验收其它主机、Unit、固件族或物理硬件，也没有部署/重启 AIFlow。

## 环境输入说明补充

用户追问后核对，两个既有 helper 已能发送 Unit 输入，服务的 ENV III 契约已提供
`temperature-c`、`humidity-pct`、`pressure-pa`，但分发文档只给 PIR 示例。本次
仅补两套 Skill 的 ENV III assembly/initial、同会话实时输入、读数/画面/报警或
执行器变化及恢复验证流程，修正 AIFlow 参考中的名称说明，并重建分发包。没有
修改 helper、服务或控制器，也没有重新运行 ENV guest；运行能力仍以现有设备/
固件局部证据和部署实例的实时准入为准，不扩张为所有环境变量或全局天气模型。

补充后两套 Skill 元数据与分发检查通过，41 项 Skill/打包、48 项文档契约及
全量平台 1392 项检查通过（6 项跳过）；coverage/catalog/profile/snapshot 与
diff 检查通过。独立审查确认 ENV 输入路由、字段、单位、初值与 Run 归属正确。
