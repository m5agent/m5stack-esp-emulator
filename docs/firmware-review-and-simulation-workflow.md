# 固件审查与仿真测试工作流

- 状态：工作流基线，持续更新
- 日期：2026-10-24
- 适用对象：UIFlow/UIFlow2、ESP-IDF、Arduino、MicroPython 和自研 ESP32 固件
- 相关文档：
  - [项目当前状态](project-status.md)
  - [项目 Backlog](project-backlog.md)
  - [代码与验证入口地图](code-map.md)
  - [外设仿真架构](peripheral-simulation-architecture.md)
  - [虚拟主机适配矩阵](qemu-device-adaptation-matrix.md)
  - [UIFlow2 外设 API 测试矩阵](uiflow2-peripheral-test-matrix.md)
  - [跨设备显示、输入与音频回归审计](uiflow2-cross-device-regression-audit.md)

## 1. 结论

模拟器不应只用于回答“固件能不能启动”。在板级模型、总线和数据面覆盖到的范围内，
它可以把固件审查扩展为：

1. 制品完整性和镜像格式检查；
2. 启动、串口、画面和文件系统检查；
3. UIFlow/ESP-IDF/Arduino 驱动与业务逻辑回归；
4. 外设交互和异常状态测试；
5. 网络访问、DNS、局域网扫描和异常外传审计；
6. Flash、NVS、文件系统和安全配置的运行前后差异；
7. 可疑持久化、远程控制、资源滥用和未声明能力检测。

模拟器不能单独证明固件安全；对于 RF、功耗、声学、光学、机械和电气属性，
它也不能替代真机测量。

最终原则：

> 仿真 PASS 表示声明的虚拟设备数据面通过。
>
> 仿真 FAIL 先按高优先级缺陷处理，同时排除模型错误。
>
> 仿真未发现问题，不等于固件没有恶意行为。
>
> 对外结论必须执行同一固件和实现路径；validated virtual-device 或真机证据
> 都可以使用，但 RF/功耗/声学/光学/机械/电气结论必须来自真机。

## 2. 仿真结果的可信边界

### 2.1 通常在真机也会复现

当仿真使用官方固件、真实驱动、真实控制器寄存器和完整数据面时，以下问题具有较高参考价值：

- UIFlow/ESP-IDF API 参数错误；
- 初始化和关闭顺序错误；
- I2C、SPI、GPIO、UART 协议错误；
- 寄存器位定义、字节序和单位转换错误；
- DMA、GDMA、FIFO 和中断使用错误；
- UI 坐标、颜色、旋转、裁剪和刷新问题；
- 内存越界、空指针、异常重启和看门狗问题；
- 多外设初始化冲突；
- Flash、NVS、分区和文件系统操作错误；
- 网络协议、DNS、HTTP/MQTT、重连和超时逻辑错误。

### 2.2 只能作为线索

以下问题即使仿真失败，也需要排除模型偏差：

- 中断竞争和微小时间窗口；
- DMA 缓存一致性和边界条件；
- 掉电、复位、启动时序和 Flash 忙碌状态；
- 高频 GPIO、SPI、I2S 和 USB PHY 时序；
- 多任务低概率竞态；
- 真实射频、Wi-Fi 漫游、BLE 连接和干扰；
- 安全启动、Flash 加密和 eFuse 的完整上电流程。

### 2.3 仿真不能替代真机

- Wi-Fi/BLE 射频性能、距离和天线；
- 音频响度、音色、回声和扬声器声压；
- 麦克风灵敏度、信噪比和频响；
- 摄像头曝光、对焦、色彩和光学缺陷；
- 屏幕亮度、色偏、残影和可视角度；
- 触摸手感、玻璃、多点触控和机械结构；
- 电池、充电、功耗、温升和电源纹波；
- 传感器校准、机械安装、真实运动和噪声；
- 焊接、器件批次、产线和长期可靠性。

## 3. 输入和输出如何模拟

### 3.1 麦克风

当前不是让模拟扬声器真实发声后再被麦克风采集。

测试链路：

```text
宿主生成确定性 PCM
  -> I2S RX / GDMA 模型
  -> 固件 Mic.record()
  -> UIFlow2 或原生驱动读取
```

宿主通过 `M5SW_I2S_RX_PCM_FILE` 注入 PCM，例如 440 Hz、16 kHz、1 秒。

可证明：

- Codec I2C 初始化；
- I2S RX、GDMA 和中断；
- 录音缓冲区和驱动；
- API 返回非静音数据。

不能证明：

- 麦克风咪头、模拟增益和信噪比；
- 真实环境声音和声学传播。

### 3.2 扬声器

测试链路：

```text
固件 Speaker.tone()/playRaw()
  -> I2S TX
  -> 循环 GDMA
  -> 宿主捕获 PCM
```

宿主通过 `M5SW_I2S_PCM_FILE` 保存固件实际写入的数据，再检查采样率、非零样本、
峰峰值、频率、连续性和 WAV。

可证明：

- 固件确实生成并提交了音频；
- I2S/GDMA 数据面可用；
- Codec/功放控制路径正常。

不能证明：

- 物理扬声器是否出声；
- 音量、音色和声压；
- 模拟电路和机械腔体效果。

### 3.3 屏幕和触摸

屏幕通过 QEMU `screendump` 直接读取显示控制器 framebuffer：

- 校验分辨率；
- 保存 PNG；
- 检查非黑像素和颜色数量；
- 比较输入前后画面；
- 检查固定坐标像素；
- 捕获动画帧。

单指触摸通过 QMP `input-send-event` 注入绝对坐标、按下和抬起。长按和拖动通过
保持或连续发送坐标模拟。板级触摸控制器模型再将状态提供给固件。

特殊触摸通过 QOM 注入，例如：

```text
/machine/si12t touch-bits=2
```

不存在“模拟一只手”的视觉模型。屏幕中是否出现手指由被测固件自己决定。

### 3.4 按键

按键使用两类输入：

- QMP 键盘事件，例如 `key:a` 的按下和抬起；
- QOM 输入位注入，例如 AW9523、M5IOE1 或 M5PM1 的输入位。

固件仍需经过真实 GPIO/I2C/中断/驱动路径读取，不是测试脚本直接修改应用状态。

当前可模拟按键持续时间，但不模拟真实机械抖动、接触电阻和寿命。

### 3.5 IMU 和其他传感器

通过 QOM 写入芯片模型内部物理量，例如：

```text
/machine/bmi270 accel-x=0.25
/machine/bmi270 accel-y=-0.50
/machine/bmi270 accel-z=0.75
/machine/bmi270 gyro-x=10
/machine/bmi270 gyro-y=-20
/machine/bmi270 gyro-z=30
```

固件通过真实 I2C、芯片寄存器和驱动读取。

这表示“设备当前处于某个姿态或运动状态”，不是让设备物理运动。当前多数用例注入
静态状态；后续可以按时间序列修改 QOM，模拟倾斜、旋转、碰撞和运动轨迹，但仍不是
完整物理引擎。

## 4. 非 UIFlow 固件支持

模拟器架构不依赖 UIFlow。

可以运行：

- UIFlow1/UIFlow2；
- ESP-IDF；
- Arduino ESP32；
- MicroPython；
- 自研产品固件；
- 其他能生成兼容完整 flash image 的 ESP32 固件。

基本前提：

1. SoC 和内存映射与 QEMU machine 一致；
2. 存在对应板级 profile；
3. Flash、PSRAM、eFuse 和分区布局兼容；
4. 固件依赖的控制器和设备已经建模；
5. 固件镜像包含 bootloader、分区表、应用和所需文件系统。

这里的“烧录”是把完整镜像加载到虚拟 flash，不是写入真实设备。

如果换用完全未适配的板卡，即使 SoC 相同，也可能需要补齐：

- GPIO 映射；
- I2C/SPI/UART 总线和地址；
- 屏幕和触摸 controller；
- 电源、RTC、传感器和扩展芯片；
- USB、SD、CAN、音频和摄像头数据面；
- 板级 device tree、profile 和测试固件。

## 5. 固件安全审查范围

### 5.1 制品完整性

- 下载大小和 SHA-256；
- 声明型号、版本和设备是否与镜像一致；
- ESP image、分区表和文件系统是否合法；
- 是否存在重复制品或设备声明冲突；
- 签名、安全启动和 Flash 加密状态。

### 5.2 静态检查

- 字符串、脱敏 URL、域名和证书标记；
- OTA、远程控制和调试端点；
- 高风险命令和调试后门；
- 第三方库、版本、来源和 SPDX/CycloneDX SBOM 摘要；
- 文件系统内容；
- 配置漂移和未声明能力；
- 凭据/私钥特征和高熵编码载荷；
- 文件系统异常资产、权限和许可策略仍待补齐。

### 5.3 动态行为

- 串口和屏幕；
- 文件、NVS 和 Flash 写入；
- 外设访问；
- 任务、定时器和资源占用；
- QOM 寄存器变化；
- 网络连接、DNS 和传输量；
- 重启、掉电和异常恢复路径。

### 5.4 网络审计

在隔离网络中观察：

- 目标 IP、端口和协议；
- DNS 域名和查询频率；
- TCP/UDP 连接和包大小；
- HTTP 明文请求；
- TLS SNI、证书和目标地址；
- 周期 beacon；
- 局域网扫描；
- 异常大流量上传；
- 未声明的外部服务；
- 下载二次载荷或远程命令。

TLS 正文通常不可见。若固件没有证书固定，可使用专用测试 CA 进行受控中间人分析；
若存在固定证书或双向 TLS，只能先观察元数据和行为。

### 5.5 持久化审计

运行前后比较：

- Flash 镜像；
- NVS；
- LittleFS/FAT/SPIFFS；
- OTA 和恢复分区；
- 启动脚本；
- 设备配置；
- 安全相关寄存器和 eFuse 文件。

重点检查：

- 未知启动项；
- 隐藏配置文件；
- 远程地址和凭据；
- 异常写入频率；
- 未声明的 OTA 或恢复逻辑。

## 6. 隔离和安全要求

待审固件必须视为不可信输入，QEMU 也必须视为攻击面。

禁止：

- 直接桥接到生产局域网；
- 向虚拟机共享宿主目录；
- 注入真实 Wi-Fi、云平台或 Git 凭据；
- 复用生产 DNS、网关和 OTA 服务；
- 在长期运行的宿主机上直接执行未知固件。

推荐：

- 一次性虚拟机、容器或专用审查节点；
- user-mode NAT、隔离 TAP 或断网模式；
- DNS sinkhole、假网关和 honeypot；
- 出站 allowlist；
- 禁止或限制 ICMP、组播和局域网访问；
- CPU、内存、磁盘和运行时间限制；
- 完整记录 pcap、DNS、串口、画面和 Flash diff；
- 任务结束后销毁虚拟磁盘和网络。

## 7. 建议的审查流水线

```text
待审固件
  -> 1. 下载与 SHA-256/大小校验
  -> 2. FirmwareManifest 规范化、WebBurner/M5Burner 导入
  -> 3. 静态镜像、分区、文件和字符串检查
  -> 4. 选择设备 profile、安全策略和隔离网络
  -> 5. 仿真启动，记录串口和首帧
  -> 6. UI、API、外设和驱动回归
  -> 7. 网络、DNS、radio/AP 丢失重连、局域网扫描和外传审计
  -> 8. Flash/NVS/文件系统前后差异
  -> 9. 异常规则和人工复核
  -> 10. 必要时真机隔离网络复核
  -> 11. 生成证据包和最终结论
```

规范化命令：

```bash
python3 platform/tools/firmware_manifest.py /path/to/package \
  --out-dir /tmp/m5-review --print summary
```

QEMU radio session 默认生成 `network/capture.pcap` 和
`network/pcap-summary.json`。`POST /sessions/{id}/network-fault` 可执行
link down/up，或用 `target=radio` 停止/恢复 WiFi 模型信标和管理帧；连接
恢复 PASS 还必须包含 guest 扫描、重新 DHCP 和一次新的受控数据面请求。

最终提交前要求：

- 仿真证据完整；
- 模型缺口明确；
- 所有异常已分类为固件问题、模型问题或待确认；
- 发布所需路径至少完成 validated virtual-device 或真机验证；
- 涉及物理测量或环境行为的断言单独执行真机验证；
- 结论不把 `SIM PASS` 当作 `HW PASS`。

## 8. 证据包建议

```text
evidence/
|-- manifest.json
|-- artifact.json
|-- static/
|-- boot/
|-- ui/
|-- peripherals/
|-- network/
|   |-- pcap/
|   |-- dns.json
|   `-- connections.json
|-- persistence/
|   |-- flash-before.bin
|   |-- flash-after.bin
|   `-- filesystem-diff.json
|-- hardware/
`-- summary.json
```

每个结果至少记录：

- 固件 SHA-256 和大小；
- 声明的设备型号和实际测试型号；
- QEMU machine、构建版本和板级 profile；
- 使用的注入文件和输入序列；
- 串口、截图和关键像素；
- 网络目标、DNS、包数量和时序；
- Flash 前后哈希和文件差异；
- 模型状态：`simulated`、`partial`、`planned`；
- 验证层级：`SIM_ONLY`、`PARTIAL`、`HW_VERIFIED`、`NOT_RUN`。

## 9. 当前固件审核 API 的约束

现网 Agent Review API 已具备：

- pending 列表；
- claim 和 lease token；
- 幂等提交；
- `deviceCodes`。

仍缺少：

- 单条详情和历史回读；
- 分阶段结果；
- 证据上传或证据 URL；
- 显式 release/renew；
- 结构化原因码。

因此建议由本地 Review Broker 保存完整的仿真和网络证据，服务端仅接收经过归类的
最终结论。若验收目标明确要求物理测量，没有真机证据时不得提交
`passed=true`；纯软件/user-path 断言可以使用 validated virtual-device
证据并明确标注范围。模型缺口和无匹配运行时不能混同为固件安全失败。

## 10. 实施状态和后续

当前 P0 基础已经具备：

1. 版本化 FirmwareManifest、M5Burner/WebBurner/ESP-IDF 导入和
   artifact hash/size 复核；
2. capability mismatch、安全状态 `unknown` 和静态 review 的结构化结果；
3. 脱敏 URL、凭据/私钥特征、高熵编码块与 SBOM 摘要；
4. QEMU pcap、DNS/DHCP/ARP/flow/payload-hash 摘要；
5. Linux private namespace、fail-closed 和单 guest 无外网路径；
6. 错误密码负向用例与 StickS3 radio/AP 丢失/reconnect；
7. Device Service session 的统一 evidence ZIP。

仍开放的工作按 [项目 Backlog](project-backlog.md) 管理，近期重点为：

1. SPIFFS 只读清单、运行时权限/许可审批、证书链校验和许可证策略；
   LittleFS 与 FAT12/16/32 文件清单、哈希和 SPDX 已具备；
2. 正式 CI/worker、外部 IPv6 egress 和双设备 lab fabric；
3. 生产 eFuse/secure boot/Flash Encryption key 流程的真机验证；
4. 更广的 ESP-IDF/Arduino/MicroPython/vendor 固件回归；
5. Tab5、CardputerZero 和时间序列 QOM 等覆盖增强。

网络部分已经具备 controlled DNS、TLS/Host allowlist、精确 IPv4
IP/协议/端口 egress、pcap、DHCP renewal 和虚拟 radio/AP 丢失恢复；仍未
完成的是双设备 fabric、自托管 QEMU worker 和外部 IPv6。固件文件系统 PASS
只表示清单可解析且结果可追踪，不表示镜像安全或许可证合规。

## 11. 结论

模拟器最适合承担固件审查中的“可重复行为实验平台”：

- 让官方固件在不修改的情况下运行；
- 把输入、输出、网络和持久化变成可观测数据；
- 在真机之前发现大部分软件、驱动、协议和可疑行为问题；
- 把无法在仿真中证明的部分明确交给真机。

它应成为固件审查流程的前置层和证据层，而不是最终安全认证层。
