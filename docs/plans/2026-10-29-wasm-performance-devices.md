# WASM 性能与多设备继续推进

日期：2026-10-29。来源为用户反馈网页约1 FPS、只开放CoreS3，并要求同步最新main后继续处理。

## 目标与约束

在浏览器实际运行固件的前提下改善帧率、输入反馈和正常时钟；将CoreS3硬编码整理成真实板型配置，并逐设备取得可发布证据。保留既有SoC/控制器/固件驱动，禁止主机画假帧或拼接其它guest结果。原生服务和硬件结果不转授WASM。

先同步上游main@0769ae7c；新分支codex/wasm-performance-devices沿用独立worktree。用户8787/8830服务、主checkout与既有会话保持不动。浏览器验证只用独立静态端口或授权测试fork，公开原仓库部署仍由管理员执行。

## 工作与验收

1. 基线：在固定旧执行产物上量测采帧频率、真实画面变化、触摸到guest及可见帧延迟、CPU与内存；记录统计口径、guest/runtime/firmware SHA及退出。
2. 显示数据通路：去除750ms串行等待与每帧QMP/PPM临时文件。使用真实QEMU显示surface的受控共享快照，带序列校验避免读写撕裂；不绕过面板/总线。静态画面不制造新guest帧，不能拿重复采样宣称动画FPS。
3. 正常时钟：沿实际SDK Timer→m5ui.port路径定位双层schedule。显式候选保留真实guest tick、触摸/PIR/动画及异常清理；在div1下验证时间推进和队列压力，不以关闭WDT或慢放代替修复，不把候选冒充stock。
4. 多设备：通用profile覆盖machine、ROM、eFuse、Flash、屏幕、输入和示例。先处理已有Xtensa-S3机器，再Core2；C6/P4/ARM64独立目标继续单列。只发布有同设备实际guest证据的profile，候选预览不能混入Pages公开准入。
5. 主线修复：为Core2回移0068/0069的功能语义，固定来源和重放hash。0074需先核实现有SPI语义；冻结WASM栈已延后并只消费一次DMA，不能直接套用原生补丁或声称继承其测试。不为了声称同步而默认引入trace/CAS诊断。WASM源码/依赖/链接/对应源码的锁定和分发规则继续适用。
6. 交付：相关平台/Node/生成器、实际浏览器回归、性能对照和逐机输入/帧/清理完成后更新状态/Backlog/台账，归档原始证据并提交后续PR。未闭合范围持续保留，不以单个样例通过关闭整条工作流。

## 进行状态

main 已同步至 `38a7e8be`；新增原生 ESP-NOW 修复保持独立，本轮浏览器执行源码与已测 WASM 未变化。共享快照、宿主 poll 等待、正常时钟 SDK 候选及其新旧浏览器组合均已取得运行证据，量测见[性能摘要](../evidence/2026-10-29-wasm-performance-devices/README.md)。

四板五示例已完成实际公众 UI：公开 v4 四例通过84项，新增 Core2 在公开 v5 单独通过17项；执行 JS/runtime 与其余1929资产身份一致，两个site manifest 分别记录，不冒称v5全聚合。Core2 首次 probe 因重复安装已占用 UART0 而未执行 main；专属 boot 保留固件 console 后已通过。AtomS3R 既有2行面板偏移仍保留边界，所有结果不从 native 或其它设备继承。最终 authority 文档、归档、scope 检查及后续 PR 正在收尾；正式 Pages 仍为既有部署，后续管理员重建发布另验。
