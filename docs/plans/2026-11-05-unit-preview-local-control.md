# Unit 目录预览与本机 Preview 访问修复

用户反馈统一工作台丢失了独立 Unit 模型预览，且无 Token 的本机服务点击运行
返回 `preview_auth_unavailable`。本轮恢复两项实际入口，不修改 QEMU、固件、
Guest UART、板级时钟、Unit 数据面或既有运行时缺口。

Unit 目录保留独立模型与“添加到主机”两种操作。独立模型只查看外观，不更改
正在运行的拓扑或注入数据；主机草稿和运行 UnitPanel 继续分别拥有自身状态。
独立预览有自己的异步代际、挂载点和销毁流程。浏览器 Guest 加载/启动期间
主机和 Unit 预览同时暂停绘制，就绪、失败、停止或取消后恢复。
这调整了[原统一设计](2026-11-05-unified-web-workbench.md)中去除独立模型的决定。

Preview 原来比其它本地接口额外要求配置 Bearer。无 Token 的实例现在只有在
监听 socket 和 peer 均为 loopback、唯一 Host 是合法 loopback 地址且端口匹配、
浏览器上下文同源时才可直接使用。匹配 Origin 是正向依据；Fetch Metadata
若存在也必须符合规则。没有 Origin/Fetch Metadata 的本机原始 HTTP CLI 可用。
配置过 Token 的实例继续强制验证当前或轮换 Bearer；不以本机身份绕过。
这只是 Preview 的受限兼容方式，不宣称所有旧 API 获得新的 CSRF 或沙箱保护。

验收分开执行：真实模型 Chrome 合同与四宽度；无 Bearer 的 CoreS3 + PIR
同页原生完整运行；打开独立 Unit 模型的 CoreS3 browser-WASM 完整编辑器；
配置 Bearer、跨源、Host、peer、通配监听等 HTTP 负控。功能通过不能授予所有
设备/Unit、物理测量或性能结论。用户服务的发布交接与独立测试服务保持分离。
