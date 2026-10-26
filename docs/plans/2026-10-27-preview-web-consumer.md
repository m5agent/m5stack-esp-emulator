# Preview Web 消费者与完整包编辑

日期：2026-10-27。归属 UNIT-01 / UNIT-HOST-34，状态：限定 Web 验收完成。
执行顺序只在 project-backlog.md 维护；不关闭 AIFlow 后端接入或其它 Unit 工作。

同一 SessionVisual 使用共享 Preview 客户端读取权威 epoch/generation/Run，统一
编程、主机/Unit 输入、续租、取消/关闭与帧身份。所有旧接口路径保留给普通会话，
托管会话不回退到旧 mutation；没有 Preview reset 时明确禁用复位。

增加完整不可变 checkpoint 文件读取 API，让 Web 修改 main.py 时保留原模块、
MPY 和资源；保存仍提交完整包，再引用 Run。轮询不覆盖本地草稿，外部更新与
不明请求结果须明确呈现，不能静默替换他人的新包或重复运行。

Run 切换要使旧输入队列、按钮 held intent、Unit GET、frame fetch/decode/texture
提交失效；actual guest 的 permit/drain 与 raw prompt fence 继续由服务负责。
帧必须使用 Run URL 并核 Preview/Run/execution/revision/PNG hash。Unit/设备状态
在权威 Run 查询前后分别采样，不声明与帧构成原子快照。保留明确历史末帧。

验收先跑确定性浏览器阻塞点、坏身份、旧 GET/解码、未知输入结果、完整包保留
与旧普通会话回归，再经8787可见CoreS3 PIR/Relay做真实 Web/Unit/guest/QOM/PNG
输入输出、快速Run/取消/续租/关闭与历史验证；先ZIP再关闭并核PID/Flash/lease。
新增视觉沿用现有M5Stack token/组件，检查390/768/1024/1440布局与键盘/错误状态。
本块无C/QEMU修改时不跑完整矩阵，不授予物理硬件结论。

实际结果见[仓内验收](../evidence/2026-10-27-preview-web-consumer/README.md)：
CoreS3 PIR/Relay 的完整包/真实 MPY、Web 编辑、当前 Run 输入/输出/选定帧像素、
取消恢复、续租关闭、ZIP 与资源清理均通过独审。首次 Token 恢复、raw-paste
marker 误拒和 ready 创建按钮文案的原始失败/修复留证。窄屏 3D 构图裁切按
UNIT-HOST-35 保留；AIFlow、SSE、main.mpy、GC 和其它 Unit/主机不随本块关闭。
