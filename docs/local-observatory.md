# 本地虚拟设备实验室

最近核对：`2026-11-06`。

Device Service 启动后访问同源的 `/observatory`。本地工作台导航中的
“设备中心展示”也会打开此页。它观察当前服务中由工作台、API 或任务创建的
会话，不创建或控制设备。已有服务进程需要正常更新启动后才具备新 API；
静态页面导出不包含展示页，不要求 GitHub Pages 或其它托管服务。

## 无人值守展示

- 顶部的设备数来自实际会话，排队任务来自真实 worker 队列，两者不混算。
- 同型号设备保持各自标识、独立屏幕和稳定槽位；分组只表示型号，不表示测试批次。
- 页面没有操作按钮、筛选、鼠标或触控逻辑。默认全景 12 秒，再自动巡展设备组
  5 秒、单台 8 秒；只有一个型号时跳过组巡展。全景期间详情也每 6 秒轮换。
- 新设备进入或任务结束时优先回全景，忙碌期间延长全景，避免短任务在其它设备
  特写期间完全错过。任务减少后自动继续巡展，不需要操作。
- 屏幕、Unit 连接和串口随当前观察对象切换，串口自动跟随最新尾部；活动卡和
  多 Unit 列表自动轮播。宽屏和窄屏均按整个视口排布，无需滚动页面。
- 有鉴权的服务沿用同一浏览器会话中工作台已配置的 Token；展示页不提供设置
  表单。信息屏的浏览器全屏或 kiosk 模式由部署侧配置，不依赖全屏按钮。

## 短任务与黑屏

黑屏不表示失败，也不会补演示画面。串口字节数、真实生命周期和运行时长
仍可说明设备活动。普通结束设备保留 8 秒，异常设备保留 30 秒；同时最多显示
12 台结束设备，其余进入最近活动。运行数量始终按实际状态统计，展示不延长 guest。

晚收到的结束任务直接显示结束状态，不重演其运行过程。“已结束”不等于测试通过；
没有明确任务判据时不生成 PASS。purge 后仍可看到有限生命周期元数据，串口、
屏幕和源码等会话内容不会因此保留，详情显示“已清理”。

## 观察数据与资源

`/api/v1/observatory/snapshot` 与 `/events` 提供有界、带游标的生命周期观察，
参见 [Device Service API](device-service-api.md)。SQLite 索引位于服务状态目录中，
独立于会话目录。默认保留 24 小时、最多 5,000 个结束会话和 50,000 条事件。
断线或游标缺口会重新同步；存储故障明确提示观测可能不完整，不阻止设备清理。

页面采用一个 WebGL 上下文，最多装入 32 个详细模型；超出预算的设备保留独立
槽位和状态标签，特写时优先加载。当前观察设备画面最高每秒 8 次，其余可见设备每秒
2 次，所有观察 HTTP 请求共用最多 4 个并发；刷新频率不保证 guest 帧率。
页面隐藏时停止渲染并降低同步频率，关闭页面只释放本页资源。

此入口只覆盖当前 Device Service。其它服务实例和各用户浏览器中的独立 WASM
设备不自动汇入；未 purge 前的屏幕与外设观察仍受原会话和运行时权限约束。

## 验证入口

```sh
node platform/tests/test_observatory_state.mjs
node platform/tests/test_observatory_tour.mjs
node platform/tests/test_model_output.mjs
node platform/tests/test_observatory_scene.mjs
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_observation_store.py'
```

上面是宿主协议、状态或模型测试，不执行固件。真实服务验收由显式 opt-in 的
`platform/tests/test_observatory_browser.mjs --execute` 完成；要求独立服务、状态目录、
Token 文件和新的 ignored 证据目录，禁止使用用户保留的测试端口。运行
`node platform/tests/test_observatory_browser.mjs` 可查看参数与验收范围。

真实会话结果标为 `virtual-device validation`。64 个逻辑设备的布局压力场景
单独报告，不代表 64 台固件并发、物理硬件验证或性能承诺。
