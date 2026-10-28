# UIFlow2 全接口双主机验证

日期：`2026-10-27`

用户要求 CoreS3（LVGL/M5UI）与 Cardputer-ADV（无 LVGL）覆盖全部
UIFlow2 接口，选取 Unit 联合测试，并在真实 Device Service 调用中修复问题。
本计划定义验收方式；唯一执行队列仍在 `../project-backlog.md`。

## 范围与分母

以固定版本官方文档、对应固件冻结源码及 guest 实际导出三方对账。
清单按 UI、硬件、系统/通信和 Device Service HTTP operation 分组。
外接 Unit/Module/Base/HAT 的完整目录必须入账，联合功能验证按用户允许选型；
不把未选外设算作主机 API 功能通过。原生 LVGL 继承接口与动态对象同样
记录，不用文档页数或冷态 `dir(m5ui)` 代替真实接口数。

每条功能接口关联具体 recipe、适用主机、前置 fixture、预期行为与证据。
常量和反射只算清单对账。功能结果区分 `PASS`、`FAIL`、`NOT_RUN`、
`UNAVAILABLE_ON_DEVICE`、`BLOCKED_MODEL`、`BLOCKED_FIXTURE`；
不把无异常、import 成功或拒绝请求升级为正向功能 PASS。

## 执行与证据

所有 agent 触发的固件功能测试通过独立端口/状态目录/控制凭据的 `/api/v1` 可见会话，
用户明确保留 8787 作为自己的测试服务；后续不得使用、停止或重启它。
绑定固件 SHA、runtime SHA/profile、源码、串口、输入、帧及相关控制器状态。
先使用现有 runtime 留失败对照，再用独立构建验证最小修复。
取 evidence ZIP 后 `stop?purge=0`，核验历史、最后帧和串口保留、进程退出及
默认 Flash 释放。原始大文件保留 ignored `.work/api-sweep/`；提交可复现
源码、紧凑清单和小型摘要，遵守证据保留规则。

系统/网络测试使用本地确定性 fixture；需要外部账户或未实现控制器的接口
保留逐项 blocker。HTTP 清单逐 operation 区分正向行为、错误边界与副作用；
drain、prune 等管理操作使用隔离服务，不污染共享会话。

## 收尾门禁

覆盖审计逐项核对分母和结果，公开尚未执行/受阻项，不用代表性 smoke
冒充全量完成。修复需通过受影响控制器回归、服务契约检查及项目规定检查；
共享 QEMU 变更和 PR 交付需完整矩阵。更新权威状态、backlog、台账和生成
快照，按工作记录流程归档。所有结果仅为 virtual-device validation，
不替代真机或物理电气/RF/声学/光学验证。

## 2026-10-28 交付记录

QEMU 0051–0061、Device Service 与独立 SDK 0001–0020 候选修正已取得
分层证据，入口为[本轮审计](../evidence/2026-10-27-uiflow2-api-sweep/README.md)。
最终 runtime `cc21773f…` 通过28补丁/112文件exact-upstream往返回放，
完整外设矩阵68/68、自动重试0；摄像头、两板SD与PCM/WAV另有可见session。
原生LVGL own/module分母1845，接口观察、状态、数据面、原厂失败与配置/
绑定/模型阻塞分开。系统表每板5624槽位包含未选外设，硬件表460×2仍为
AUDIT_PARTIAL。继续执行项保留在API-01，不用审计完成冒充全部功能通过。
