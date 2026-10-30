# README 图片来源

日期：`2026-10-30`。中英文首页共用这两张图片；旧图片保留供历史文档引用。
图片用于说明界面和模型外观，不代替设备功能验收。

| 图片 | 内容与边界 |
| --- | --- |
| [browser-workbench.png](browser-workbench.png) | 当前公众工作台中的 CoreS3 浏览器 guest。画面来自真实 QEMU framebuffer，并与模型纹理逐像素核对；使用显式 LVGL 调度候选固件，保留实际 `Clicks: 0` / `PIR: CLEAR`。本次取图只验证 ready 与显示，没有验证触摸、PIR 输入或性能。 |
| [device-models.png](device-models.png) | 用当前模型加载器渲染 Atom Lite、AtomS3、StickC Plus2、StickS3。文档专用画廊不是产品页面截图；未启动固件，屏幕保持黑色、LED 不以虚构值点亮。Atom Lite 仅调整相机姿态以显示顶面与 USB/Grove 接口，未修改模型几何。 |

两张图片均在桌面 Chrome 中重新截取，未使用 AI 生成，也没有替换客体像素。
构图先在浏览器中完成，再直接输出 PNG。截图时未访问 Device Service、用户测试端口或物理设备。
准确的源提交、站点与运行时/固件 SHA、图片尺寸/哈希和清理结果见
[capture.summary.json](capture.summary.json)。

## 重新生成

准备与当前生产 Web 源码匹配的公开静态导出，以及 `platform/tests` 已锁定的
Playwright 依赖。导出不包含 ROM 或固件；运行示例时仍需要访问固定官方下载来源。

```bash
npm ci --prefix platform/tests
M5_README_SITE=/path/to/reviewed-export \
M5_README_OUT=.work/readme-images-new \
M5_README_MANIFEST_SHA256=<actual-public-site-manifest-sha256> \
M5_README_SOURCE_COMMIT=<source-commit> \
M5_README_GPU=hardware \
node scripts/docs/capture_readme_images.mjs
```

上述硬件渲染配置对应本次 macOS Chrome/ANGLE Metal；Chrome 路径可通过
`M5_README_CHROME` 指定。只调整画廊构图时增加 `M5_README_MODE=gallery`，
不会启动 guest 或重写工作台主图。每轮须使用新的输出目录。
脚本自行选择临时静态端口，并阻止用户测试端口及 `/api/v1` 请求。

原始报告、串口、运行记录和早期取图尝试保存在忽略存储中，不进入源码 Git。
早期两个平面屏点按取图尝试未取得 `touch_clicked`，也没有足以判断驱动的控制器
证据，不能据此新增触摸 PASS 或归因为驱动缺陷；最终图片明确只展示 ready/frame。
物理硬件、本次输入功能与完整设备回归均不由这些插图授予通过。
