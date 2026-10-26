# HUB 布局 candidate

候选只改 shadow 中的 `platform/web/model-shell.js`，新增 `platform/web/unit-assembly-layout.js`。产品源、已有 freeze、工作队列和公共归档没有改动。

核心交付：

- `candidate.patch`：两文件的可审查补丁，已用 `git apply --check` 检查。
- `manifest.json`：base、candidate、最终执行源、证据和后续依赖 freeze 清单。
- `DESIGN.md`：公开模型/API 依据、布局策略、适用范围和失败隔离。
- `results-r9/report.json`：最终四档 before/after bbox、12 张截图、线缆、pointer 与生命周期结果。
- `bbox-summary.json`、`visual-review.json`：紧凑量测和人工视觉检查。
- `promotion-dependencies.json`：新增 module 变成运行依赖后，需要同步的命名源清单；本候选没有修改这些 helper。

浏览器主场景是 CoreS3 module → HUB → ENV III / ToF / Color。13 组浏览器检查 PASS；额外的 annotation 17/17、P2/frontend recovery 23/23 PASS，品牌 token audit 0 issues。所有读数是浏览器夹具，固件、Device Service、QEMU 和硬件均 **NOT RUN**。

手机总览的原生 Button pad 约 23.76×19.07 px；真实手势成功，触控舒适度仍 **PARTIAL**。没有改 vendor 几何、隐藏外壳、缩放单个 Unit、扩大原生 hitbox 或改默认 camera fit。

可复现最终浏览器检查（输出必须使用新目录）：

```sh
M5_HUB_LAYOUT_OUT=results-recheck node .work/unit-hub-layout-candidate-20261026/browser-layout.mjs
```

该脚本只提供冻结静态文件与浏览器夹具，拦截 `/api/` 并记录所有非 GET 请求。它不会启动 Device Service 或固件会话。

历史迭代保持在各自 `results-r1` 到 `results-r8`，未覆盖：r1 是过宽的线缆 bbox 误报；r2 检出主机到 HUB 的实际穿壳；r3 是几何初版通过；r4 保留原生小 Button pad 未达自设 24px 的失败；r5/r6 补范围、focus 和回滚；r7 补适配层失败隔离；r8 补表面抽样器的故意碰壳负控；r9 仅更正槽位微量重新居中的源码注释后，绑定最终字节重新验证。旧迭代没有全量候选源 freeze，不能把最终 source hash 追溯套用到旧迭代。`versions/r6-before-adapter-isolation` 保留其当时确切候选源。
