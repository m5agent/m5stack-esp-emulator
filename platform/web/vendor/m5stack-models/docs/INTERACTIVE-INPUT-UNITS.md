# Joystick2 / ByteSwitch / ByteButton 接入

三个产品复用现有模型、Button、VisualJoint、Led 和 Grove 装配 API。模型负责实体姿态及输入意图，下游负责设备逻辑、I2C、霍尔/ADC数值、位图/寄存器和灯效。模型更新不会自动生成传感器读数或根据按键点灯。

| ID | 产品 | 实体控制路径 | 外驱灯光 |
| --- | --- | --- | --- |
| `joystick2` | U024-V2 | `tilt-x` / `tilt-y`，瞬时 `press` | `rgb` |
| `byteswitch` | U191 | 保持档位的 `switch-1`…`switch-8` | `rgb-1`…`rgb-9` |
| `bytebutton` | U192 | 瞬时 `press-1`…`press-8` | `rgb-1`…`rgb-9` |

Byte 系列竖放，按原生 CAD 浮雕，编号1对应底部CH0，编号8对应顶部CH7。前八个灯对应同位置控件，第九个为顶部近CH7的端部灯；这里描述外观位置，不实现串链协议。两款都提供底部 `grove` 与顶部 `grove-out`，输入口连接上游后仍可经输出口级联。层级前缀随真实挂接关系变化。

ByteButton 官方88×24×12 mm描述壳体含抬高操作台，尺寸图另示按钮凸出2 mm；竖放完整模型为24×88×14 mm，catalog分别记录名义壳尺寸和可见包围盒。ByteSwitch完整外观为24×88×19.6 mm。原始结构保持自身尺寸，没有为匹配标称值缩放。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const switches = await loadGroveModule('byteswitch', {cableLength: 60});
const buttons = await loadGroveModule('bytebutton', {cableLength: 70});
const joystick = await loadGroveModule('joystick2', {cableLength: 65});
host.port('grove').attach(switches);
switches.port('grove-out').attach(buttons);
buttons.port('grove-out').attach(joystick);
host.on('input', event => externalRuntime.sendInput(event));

// 外驱稳定档位：移动真实钮子杆，不回送输入。
host.get('grove/switch-1').setPosition(1);
// 下游回送的灯光与按钮状态互相独立。
host.get('grove/grove-out/rgb-1').set({color:'#2aa4c8', brightness:.35});

// 注入按键意图需成对释放；取消不产生click。
const key = host.button('grove/grove-out/press-1');
key.press('external-preview');
key.cancel('external-preview');

const prefix = 'grove/grove-out/grove-out/';
host.get(prefix + 'tilt-x').set({angleDeg:10, durationMs:200});
host.get(prefix + 'tilt-y').set({angleDeg:-10, durationMs:200});
host.button(prefix + 'press').press('external-preview');
host.button(prefix + 'press').release('external-preview');

// 渲染循环推进压放/倾斜插值。
host.update(1 / 60);

// 一次拆下按钮与摇杆子树，保留上游开关和四芯线。
switches.port('grove-out').detach();
host.dispose();
```

`externalRuntime` 由调用者提供。外驱姿态、档位和灯光不回送输入；`press/release/cancel` 是输入注入接口，会发送带完整层级地址的意图。实际交互时应在动作开始前订阅 `input`。

Joystick2 的 X/Y 使用有限视觉角度 −18°…18°，帽压程0.4 mm；这些是照片推导的演示约定，不是实机标定或额定范围。两倾斜关节共同带动红帽、轴柄和球体，Z按压沿倾斜后的局部轴进行。固定壳、Grove座和RGB导光件不跟随摇杆倾斜。

ByteSwitch 松手保持档位；`Button.latching=true`，`getState().position` 为0或1。ByteButton 与 Joystick2 的瞬时键在松开、取消或卸载时回到原位。Byte 系列钮子摆角/按键行程与隐藏组件布局的推导范围，见各产品 research 和 dimensions；没有把图片贴片当作活动实体。

必要级联检查命令为 `node scripts/check-byte-joystick-units.mjs`，覆盖三层真实产品、稳定杆与瞬时帽、取消输入、独立RGB、两轴倾斜与拆离。canvas为Node替身，检查不代表浏览器像素或硬件验收。新款贴纸和细丝印后置，阶段保持 `modeled`。
