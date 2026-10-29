# 2026-10-29：Worker claim response-loss idempotency

## 范围

真实 Device Service HTTP control plane 启动后，注册一个 worker、提交两个
durable jobs，并让真实 `WorkerAgent` 发起 claim。测试在服务端已经签发
`lease` 后，于客户端故意丢弃第一次成功响应；`WorkerAgent` 随后使用同一个
`claim_idempotency_key` 自动重注册并重试。该结果为 control-plane
virtual-device validation，未执行 QEMU guest。

服务使用同一 state directory 重启后再次重放同一 claim，仍返回原
`job_id`/`lease_id`。第二个 queued job 没有被重试误领；只有新的 claim key
才会领取第二个 job。

## 语义

- `claim_idempotency_key` 可选，1–160 个 printable characters；
- 持久 key 是 worker identity + claim key 的 SHA256，不保存 raw key；
- request hash 绑定 worker identity 与可选 `job_id`；
- 相同 key/request 且 lease 仍有效：返回原 job/lease，
  `claim_idempotent_replay=true`；
- 相同 key 但 request 不同：`409 claim_idempotency_conflict`；
- lease 已过期、被撤销或 ownership 改变：`409 claim_idempotency_stale`；
- 空轮询不持久化，避免无任务 poll 无限增长；
- worker 已 drain 时，已存在 lease 的响应丢失 replay 仍可完成，但不会领取
  新 job。

## 结果

真实 HTTP/WorkerAgent 路径的 11 项检查全部 PASS：

- 第一次 committed claim response 被客户端丢弃；
- WorkerAgent 自动重试两次并复用同一 key；
- restart 前后 job 与 lease 完全相同；
- 第二 job 在 replay 后仍为 queued；
- 同 key 改 `job_id` 返回 409 conflict；
- 新 key 可领取第二 job；
- `jobs.json` 不含 raw claim key，mode 为 `0600`；
- service log 不含 token。

| 项目 | SHA256 |
| --- | --- |
| OpenAPI 1.49.0 | `9027209dd5659d5845759638eb9d4ff212b700b5d2d8525199ffb27a4d0a1490` |
| worker queue | `dd1653043dfb9cb4c2975a08647f53ef87a3b89a45f02efb390ab9922bd54b4d` |
| worker agent | `599f5273d717177a3432d8fab6169ee077fea9e2366676fba50ecfd33445a146` |

机器摘要见 [summary.json](summary.json)。

仓库门禁：平台 `1529 OK + 1 skipped`；runtime coverage、peripheral catalog、
QEMU profiles、project snapshot、compileall 和 Node contracts 均 PASS。

## 复现

```bash
PYTHONPATH=platform/tools:.work/py python3 \
  tests/network/worker_claim_idempotency/run_test.py \
  --out-dir /tmp/m5-worker-claim-idempotency
```

## 未覆盖

- 物理跨主机 executor/reattach；
- 真正丢包后的任意 TCP/TLS 网络故障矩阵；
- QEMU guest/controller 内部状态；
- worker 未拥有的外部 side effect；
- physical hardware。
