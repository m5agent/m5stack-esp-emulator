# FlashLight 冷 pad 观察与共享 I2C 回归收尾

日期：2026-10-27。状态：本轮按用户要求修复当前回归后收尾；UNIT-HOST-37 继续开放。

`0047-unit-flashlight-cold-pad-observation.patch` 建立真实 GPIO pad snapshot/commit
事件，FlashLight 从新的可信低电平 t0 连续观察 >500us 后取得 known-off，不补造
高→低，也不借用 unknown 期间的旧 low。GPIO OUT/ENABLE/route/OD、IO_MUX、
外部输入/force、reset 和 RTC 接管都参与来源与失效；OUT_INV/OEN_INV 按实际
有效 pad 计算，GPIO256 的 OEN_SEL 两值等价。IE 接收器与物理 pad 分开。
未实现的 RTC 波形、hold 保持电平、sleep/power/USB 接管均不能授予旧资格。

旧 session 冻结的 Unit/Web 读取契约保持原样；新 QOM pad 诊断尚未加入公共读取字段。
这是局部功能模型。相反弱拉没有电阻求解器，保持 conflict/unknown；兼容 CPU
读取值不等于电气 known。GPIO IRQ 仍沿用既有物理 line 路径，不能声称完整
IE→IRQ 接收器等价；同进程多 SoC/热拔插、PWM、动态 S1、光度/电流/热及真机
均未在本块完成。

## 当前 bug 与修复

首候选 `825fd698…` 的 40 个实际 C 场景通过，但共享回归中 CoreS3 的
`cores3-peripherals`、`cores3-aw9523-full` 初始帧空白，电源为 `-2/0/1`；
Core2 AXP 对照通过。该失败保留于 `testing/first-candidate/`，没有改写成 PASS。

M5GFX 会先对 SDA/SCL 启用内部下拉，再确认外部上拉仍可读高。原 soft-I2C
bridge 依赖默认兼容 high，未显式登记上拉；新 resolver 因而错误地把仅有内部
下拉认作确定 low，板卡探测在发送 I2C 地址前失败。官方 CoreS3 v1.0 原理图
第3页确认 SDA12/R20、SCL11/R32 均经 2.2kΩ/1% 上拉到 VDD_3V3。

最终修复仅为现有 soft-I2C bridge 的两条实际总线线注册独立、owned 弱上拉；
没有关闭 IE、常驻注入 strong high 或改写 ACK。CoreS3 阻值不外推其它主机。
相反弱源仍 unknown，GPIO reset 和硬 I2C handoff 保留板级连接。

## 证据与复验入口

- [官方原理图与固定 M5GFX 来源](research/cores3-pullups/README.md)。源码来源
  固定，不据此声称某个 stock BIN 已证明逐字对应。
- [首阶段真实控制器/AW/aux C 组合](controller/combined-r1/README.md)：40场景、
  500000/500001ns、writer/反相/RTC/reset/迟到 timer；旧实际源码冷路径失败。
  原阶段的 runtime 回归 FAIL 保持不变。
- `controller/soft-i2c-fix/`：真实 bridge 初始化的前后负控及只读审阅。
- `build/fixed/`：最终固定13补丁、109源文件的完整重放、逆序回退与冷构建。
  只复用依赖工具，不复用 QEMU 对象；不提交 executable、ROM 或固件。
- `testing/fixed/`：受影响设备组、平台测试和必要 validator 的实际结果。

最终候选 runtime SHA256：
`faee96da9f041583a6003a26523fa5378a88a4bc8f01b15492922076abf73096`。
首候选与最终候选分开记录。原平台首次运行环境漏配 Pillow/兼容 LittleFS，
结果原文保留于 `testing/environment-attempt-r1/`；修正既有依赖路径后窄58项
通过，不把环境失败改写成原轮通过。

## 本轮最终验证

- 修复后受影响四主机设备组加 Core2 AXP 对照：22/22 PASS，92个检查；
  无重试，CoreS3画面已打开核对，电源恢复为87%/4000mV。
- 平台1226项通过；runtime coverage、peripheral catalog、QEMU profiles、Unit
  catalog 检查通过。两个原有离线Web契约检查通过，不等于新guest/Web验收。
- 服务仅在idle时重载到最终候选，保留516个包文件、408个源码revision记录；
  无新托管会话，最终active/lease/本块QEMU进程均0。
- 源码重放的旧命名字段`nine_file_bindings`实际包含10项，完整清单/断言为10；
  109源、正序/逆序/再正序与最终树哈希相同，没有减少重放范围。

## 明确未做

本块新的 FlashLight 四主机 API/Preview、原 constructor 和 mounted Web 验收均
**NOT RUN**。准备的112个包只做了离线语法检查，没有虚拟设备或真机 PASS。
新完整矩阵 **NOT RUN**；原 `3f1617` 的66/67属于旧运行时，不能继承给新候选。
本轮只完成当前共享回归的必要验证，不关闭 UNIT-HOST-37/36，也不扩展 AIFlow、
SSE、其它 Unit 或固件入口。后续从项目 Backlog 和本块计划继续。

所有结果只覆盖各自的 C、源码/构建或虚拟回归层；physical hardware NOT RUN。
