# Paper两板：显式PM1应用配置与独立验收

日期与最近核对：`2026-11-04`。执行层级：**virtual-device validation**。
准确Flash/runtime/source/test SHA、原始工件bytes/SHA、实际配置和清场见
[summary.json](summary.json)。本记录保留R6的fixture准备失败，并追加两个独立
Paper按键run及PaperMono编辑器run；**R7完整60例仍RUNNING / PENDING**，未读取其active raw。

| 独立范围 | 实际结果 | 限定 |
| --- | --- | --- |
| R6 PaperColor旧fixture | 1个UI-start check，输入0；导入helper失败 | 准备失败，不是PWR控制器/路由失败 |
| PaperColor显式I2C配置按键 | `23/23 PASS`、8个键鼠trial | 三GPIO键及PWR，500 ms应用识别窗、250 ms输入 |
| PaperMono显式I2C配置按键 | `19/19 PASS`、6个键鼠trial | 两GPIO键及PWR，保持独立固件身份 |
| PaperMono完整编辑器 | `63/63 PASS` | 实际8f9控制脚本、默认两次Run、黑白帧、hardware reset与正常清场 |

这些结果不授予默认PM1模式、所有helper/BIN版本、物理pinmux或完整19板/60例通过。

## 先前R6失败停在导入阶段

R6的PaperColor按键case已启动原默认工作台，但执行fixture时发生：

```text
ImportError: no module named 'driver.m5pm1'
```

旧fixture在建立其I2C、配置/readback和发出ready之前，统一导入Python helper。
当时只有1个UI-start检查，真实input trial为0。原报告为7,232,025字节，SHA
`73d40cb1448bb369a2556338082eee7830d783348294eacd0ae35a87d25a08c9`。
它不能证明PWR路由或原native `M5.update()/BtnPWR`失效；R6全矩阵以
26started/25PASS和该FAIL停止，未获得全60验收。

失败后实际normal-QMP exit0、零强制/兜底终止、六实际CDP关闭。
保留iframe时的CDP围栏为 **NOT CAPTURED**。正常清场不把准备失败变成按钮PASS，
后续成功也不覆盖原ImportError。

## 配置API按精确设备显式选择

实现提交`1f69290976a139cd7ca666581b744b3544526b96`只修fixture的显式API选择。
产品V5、runtime75/C、默认Flash、时钟与WDT不改：

| 设备 | configuration_api | I2C / SCL / SDA / address |
| --- | --- | --- |
| StopWatch | `m5pm1-python-driver` | 1 / 48 / 47 / `0x6e` |
| StickS3 | `m5pm1-python-driver` | 1 / 48 / 47 / `0x6e` |
| PaperColor | `machine-i2c-register-rmw` | 1 / 2 / 3 / `0x6e` |
| PaperMono | `machine-i2c-register-rmw` | 1 / 48 / 47 / `0x6e` |

StopWatch/StickS3保留其独立实测过的Python helper分支。Paper两板明确选择公开
`machine.I2C.readfrom_mem/writeto_mem`，不尝试导入helper，不使用`except`自动
fallback。未知API、错误board/window/readback都拒绝继续，未登记的非PM1板不配置PM1。

PaperColor的精确BIN已用真实ImportError证明该Python helper不可用。
PaperMono的运行时helper import仍 **UNKNOWN / NOT RUN**；静态字符串缺失只能
作为提示，新的I2C成功没有证明其helper存在，也没有借用其它BIN的class版本。
原native M5Unified的PM1/BtnPWR路径与可选Python helper是不同层次。

## 原公开总线上的寄存器语义

固定官方driver commit
`3404a0667985334393af05f53f27006ac954579a`的
`m5stack/libs/driver/m5pm1.py`，SHA
`021b3632c6583118ac3eb23b0d2addb7a16e0bb116a0b4ae5c728af5e4ff31b3`，
定义BTN_CFG1为`0x49`：single-click reset关闭用mask1/value1；CLICK500用
shift1、编码2，即mask6/value4。合并后的公开bus操作等效为：

```python
before = bus.readfrom_mem(0x6e, 0x49, 1)[0]
before4a = bus.readfrom_mem(0x6e, 0x4a, 1)[0]
target = (before & 0xf8) | 0x05
bus.writeto_mem(0x6e, 0x49, bytes((target,)))
assert bus.readfrom_mem(0x6e, 0x49, 1)[0] == target
assert bus.readfrom_mem(0x6e, 0x4a, 1)[0] == before4a
```

实际guest均回读49从`0x2a`变为`0x2d`，高5位保留，4a维持0。
这选择single-click IRQ与500 ms识别窗，**真实输入仍固定请求250 ms**，释放后才等
guest观察；没有延长为500 ms输入或hold-until-ack。
配置期间不读消费式IRQ42或status48，事件只由原native `M5.update/Power/BtnPWR`
消费；没有private ISR、host事件回声、QOM寄存器替换或默认Flash改写。

固定官方source解释寄存器语义，不证明该Python class被某个BIN包含或其字节版本。
实际总线readback与原Button事件由下面每个精确镜像独立证明。

## 两个正式按键run

| 身份 | PaperColor | PaperMono |
| --- | --- | --- |
| 完整工作台Flash SHA256 | `c4486aba3d494048a8dd9e464a610bce0d19369b51ae814f2f221ddc630b6b34` | `f03a6fccab31e3f3b1a3c83aabff6953f822744b5672e5b46df2ee7e57b5a9f0` |
| checks / trials | 23 / 8 | 19 / 6 |
| 原报告bytes | 12,593,087 | 20,061,822 |
| 原报告SHA256 | `924e84ea26cd67a0af581a48521581cc99720f70ebe8e9e5dd69ef1a96fde35f` | `5778c802dded1584656be3b6ea55dea09bce3b6ac48de085389a9eb05361e93f` |

两者actual API都为`machine.I2C.readfrom_mem+writeto_mem`，明确选择
`configuration_api=machine-i2c-register-rmw`。GPIO键各键盘/真实raycast鼠标路径
都有原Button press/release；两种PWR输入均由原`wasClicked`报告。
真实请求pulse均250 ms；宿主观测PaperColor约251.553–254.384 ms，PaperMono
约251.581–253.952 ms，只记录本次实际输入，不把它当虚拟PMIC内部hold或物理时序。

实际按键控制脚本SHA为
`7e1ca495b0006f7976914ded0d51b6f137da9c8155b806ee371820620ac20989`；
observer SHA为`889b00d77edd0f076815b9e3a0a05fbd48ead181e62922f77988630d541bd7d4`。
两个case分别绑定自己的base/Flash、profile和同一V5/runtime75：WASM
`96ea9f91956aa80926182ed174ea426f3f4c84e96ca58754fa249063fdda5ca1`，
site manifest `6123a283c5a32254d76b9de64aaba2bae64de22aecd7207b48dd2ce0af2c8bbb`。
两者divisor1，无clock/icount/oneInsn override。

各自normal-QMP exit0、nested workers0、零forced disposal、零engine fallback，
六个实际CDP在context关闭前全部消失。**两个按键runner的held-iframe CDP均为
NOT CAPTURED**；不能借下面Mono编辑器的两阶段结果补齐。

6项Python host合同含全部256种before49高位保留、无helper模块的显式I2C分支、
未知API/readback错误及非PM1边界；根代理另报告28项Node合同和peer审查通过。
本文未重复这些host执行，且不把mock中的register响应称为guest证据。

## 独立PaperMono完整编辑器

另一次Mono run用实际最终验收脚本
`8f9dad6414db348a315acdaceab73f4e95abdbe10440056edb7eed42356c93c2`
完成 **63/63 PASS**。原报告20,066,031字节，SHA
`e3b4d3bf6a1b434c178de4894fc34b75838e2eaaebe717f87b31001d4649c0b6`。

原textarea源码SHA为
`93ebf6c7166ac121b8f6163c836ed1001e4ba469c47e3cfd3a90f47908ccc1db`，
第一次和重复直接Run都从真实UART返回`Hello, UIFlow!`，stderr空、session/console
一致。随后原完整程序、暂停/中断和hardware reset后新console源码执行通过。

原`M5.Display`在rotation0、EPD_QUALITY、startWrite/endWrite中绘制480×800
左黑右白；实际192000点黑、192000点白，位置逐像素检查通过，帧SHA
`362211ea15a8ea592bce4cab143bfd7ac0722c2e22cb9c9ad483ffe0c6a88c21`。
报告没有expected-red字段。硬件reset的console epoch由0变1，旧执行AbortError，
新源码执行及正常QMP退出通过；零兜底终止，保留iframe时和context关闭前实际六
CDP两阶段均通过。这只属于该Mono/image/controller，不转授其它板或完整矩阵。

## 复验与不可继承范围

```sh
M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE="$PAPER_DEVICE" \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_qemu_buttons_guest.mjs

M5_PUBLIC_SITE="$SITE" M5_QEMU_DEVICE=papermono \
M5_PUBLIC_QEMU_OUT="$NEW_OUT" M5_WASM_CHROME="$CHROME" \
node platform/tests/test_public_uiflow_guest.mjs
```

使用准确默认镜像、static export/runtime/profile、Chrome/Playwright及每次全新
ignored输出。历史ImportError须保留旧fixture身份；本记录不覆盖
[早期StopWatch应用模式](../2026-11-04-browser-input-acceptance/README.md)或
[PaperColor帧观察器首FAIL](../2026-11-04-papercolor-frame-oracle/README.md)。

模型的I2C0/I2C1接在共享slave bus，成功的公开I2C事务和审核过的pins参数不能
证明物理GPIO pinmux约束。configured application PASS也不证明PM1默认复位模式、
长按/双击、其它固件class版本或物理电气行为。
R7完整60例当前仍PENDING，active raw未读取；最终host汇总、PR和部署另行立证。
