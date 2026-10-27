# RollerCAN / RollerCAN Lite / Vibrator

三款复用 `VisualJoint`：`rotor` 接受外部角度或连续 `rpm`，默认静止，由调用者逐帧执行 `update(dt)`，dt单位秒。这里绘制实体姿态，不实现电机、CAN、电气、编码器反馈或扭矩控制。

| ID / 型号 | 真实随转实体 | 固定实体与其他控制 |
| --- | --- | --- |
| `rollercan` / U188 | D3504外转子、扩展盘、顶部PCB、`grove-top`、`top-led`，及端口上的下级装配 | 外壳、`grove`、`can-1` / `can-2`、`debug`、`lcd`、`press`、`rgb-1` / `rgb-2` |
| `rollercan-lite` / U188-Lite | D3504裸外转子 | 外壳、`grove`、双CAN座、`debug`、`lcd`、`press`、两RGB；无顶部Grove |
| `vibrator` / U059 | 实际外露金属偏心轮、输出轴与端部紧固件 | 原壳、N20电机固定部分、PCB和Grove |

两款Roller的 `lcd` 为固定底部64×48白色OLED，仍使用RGBA/RGB565/RGB888外部framebuffer。两个RGB独立外驱，标准版顶部红灯也独立外驱。按下 `press` 会让原生CAD弹舌的实际顶点形变，松开/取消时准确恢复；它只产生输入意图，不在模型内打开配置菜单。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
const roller = await loadGroveModule('rollercan', {cableLength:65});
hub.port('grove-1').attach(roller);
hub.port('grove-2').attach(await loadGroveModule('rollercan-lite', {cableLength:75}));
hub.port('grove-3').attach(await loadGroveModule('vibrator', {cableLength:55}));

// 标准版真实移动输出；其下的四芯线和Unit跟随顶部端口。
roller.port('grove-top').attach(await loadGroveModule('key', {cableLength:45}));
host.get('grove/grove-1/rotor').set({rpm:12});
host.get('grove/grove-2/rotor').set({angleDeg:45, durationMs:200});
host.get('grove/grove-3/rotor').set({rpm:12});
host.display('grove/grove-1/lcd').fill('#dedede');
host.get('grove/grove-1/rgb-1').set({color:'#27a4cb', brightness:.4});

// 放入调用者的渲染循环；不另建内部定时器。
host.update(1 / 60);

const press = host.button('grove/grove-2/press');
press.press('external-preview');
press.cancel('external-preview');
host.update(1 / 60);

// 停在当前视觉角度；也可用angleDeg:0明确回到模型零位。
host.get('grove/grove-1/rotor').set({rpm:0});
roller.port('grove-top').detach();
host.dispose();
```

Vibrator只旋转真实偏心轮和同轴输出件，不自动抖动整机或线缆；视觉转速不换算振幅、PWM或额定转速。其官方基体名义为24×32×8 mm，原壳电机凸包深12.2 mm，完整可见轮组使本模型包络为24×37×12.2 mm。两款Roller的零相位是来源装配姿态，不是实物编码器零位或机械标定。

Lite的官方表格沿用40×40×40 mm，但原壳和D3504图纸组合得到本模型约41×30×41 mm的可见包络；安装位置和总高仍有外观推导，未将电机拉长匹配表格。标准版模型可见包络约41×40×41 mm。各自source、nominal、CAD和visual口径见catalog及research；不能据此作制造配合。

必要接入检查为 `node scripts/check-rotating-unit-expansion.mjs`，覆盖三实际转子、单帧转速、固定接口、标准版移动输出与四芯线端点、真实弹舌形变/取消回位、外部画面所有权和独立拆离。canvas为Node替身；按用户要求不逐面浏览器复核，新款印刷后置，阶段保持 `modeled`。
