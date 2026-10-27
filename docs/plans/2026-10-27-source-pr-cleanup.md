# Unit 源码 PR 精简收尾

日期：`2026-10-27`。范围：修复 PR 体积、证据依赖和干净检出门禁。

审查发现源码 PR 混入大量逐帧/请求响应/ZIP 归档，平台测试依赖本机 `.work`
与历史 source blob，Node 门禁未安装声明的依赖。这些问题妨碍代码审查和复现。

## 交付约定

1. 从最新主线重建分支，仅迁入最终功能净改动；旧分支及原证据保留，不改写。
2. 不迁入新增 raw evidence。保留必要 fixture、精简结论、版本/哈希和复现入口；
   历史引用固定到旧提交，详见[证据保留规则](../evidence-retention.md)。
3. 普通 CI 验证代码和离线契约；完整历史附件审计改用显式命令，缺材料失败。
4. 补 Node 依赖安装，在无 `.work`、无既有 `node_modules` 的独立检出运行门禁。
5. 核对 diff、体积和敏感字段后提交替代 PR，保留原分支供历史审计。

## 验收记录

已对源码提交 `e85e8e2cdbe61e0fdf414123db55faec13f98a71` 创建独立 clone，
使用 `--no-local --single-branch`，确认旧大分支提交对象不可用，且开始时没有
`.work` 和 `node_modules`。另建 Python 3.12.8 环境安装 Pillow 及
`littlefs-python==0.19.0`，Node 为 22.22.2，浏览器依赖通过锁文件重新安装。

| 检查 | 结果 |
| --- | --- |
| 平台 `unittest discover -s platform/tests -p 'test_*.py'` | 1237 项，1234 通过、3 跳过 |
| CI 的 10 组离线 Unit 契约/负控 | 194 项，191 通过、3 跳过 |
| `npm ci --prefix platform/tests` 和 `test:contracts` | 8 个 Node 入口通过，包含实际 Chromium 音频契约检查与 PreviewClient |
| runtime coverage、peripheral catalog、QEMU profiles、project snapshot | 全部 `--check` 通过 |
| Python compileall；独立 clone 的 Git 状态 | 通过；工作树干净 |
| PR scope（以主线 `f2061759` 为基线） | 通过；新增 Git blob 约 112 MB，新增 raw evidence 为 0 |

原分支约 2.27 GB 的文件内容缩减至约 137 MB（约减少 94%）；没有迁入原来的
83,096 个新增证据文件。保留的三维运行资源约 104 MB，属于功能所需模型和
纹理，不是运行归档。新增摘要未检出本机 home 路径或凭据签名；新增网络内容
保留明确的合成测试输入与协议地址，不把这些地址改成真实服务端点。

历史核对另行显式执行：42 个 host 记录和 4 个 Scroll 记录的原归档校验通过，
29 个历史工具 source digest 通过，缺失材料的负控失败。它们是历史材料完整性
审计，不是重跑设备。本计划不把旧分支的平台 PASS 当作本次测试结果。
没有重新运行新 FlashLight 四主机 API/Web 或完整外围矩阵，也没有硬件验证。

本轮只收尾源码交付，不恢复新 Unit、AIFlow/SSE、保存开机或运行时清场开发。
