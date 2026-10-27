# Unit 可拆螺钉端子

Weight-I2C U180 与 Unit 8Servos U165 都保留默认空座，并可显示各自随附的四芯插头。在预览的配置选择中切换“固定4P座”与“安装4P螺钉插头”。四螺钉出现在“可动部件”中，改变的是头部角度。

## 构造与 Grove 连接

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const unit = await loadGroveModule('8servos', {
  terminalPlug: true,
  cableLength: 80,
});
host.port('grove').attach(unit);

// 通过真实的层级地址改变第四个螺钉头部方向。
host.handle({type:'joint', target:'grove/terminal/screw-4', angleDeg:67});

// 只卸下端子插头，保留 Unit 和渲染中的四芯 Grove 线。
const plug = unit.port('terminal').detach({dispose:false});
// 同一插头可重新安装，保留已设置的螺钉方向。
unit.port('terminal').attach(plug);

// 不再需要插头时，让端口卸载并释放它。
unit.port('terminal').detach();
```

将ID换成 `weight-i2c`，接口保持相同。独立展示用 `loadModel(id, {terminalPlug:true})`。两个产品目录的 `index.js` 都导出各自 `TerminalPlug`；也可先构造默认空座，再 `unit.port('terminal').attach(new TerminalPlug())`。

## 地址和职责

| 产品 | 四个螺钉的标签顺序 | 独立模型路径 |
| --- | --- | --- |
| Weight-I2C | A+、A−、E−、E+ | `terminal/screw-1`…`terminal/screw-4` |
| 8Servos | HPWR、GND、GND、5V | `terminal/screw-1`…`terminal/screw-4` |

挂接后路径增加实际主机端口前缀；经过HUB时也保留完整层级。`angleDeg` 只驱动螺钉头部的几何朝向；非零 `rpm` 不接受。没有螺纹升降、夹线位移、自动拧紧、电气连通、称重、供电或舵机控制。角度设置不发送用户输入意图，端口的装卸沿用既有 `attach` / `detach` 输入事件。

插头的壁厚、孔深、弹片和夹笼尺寸参考精确型号官方照片推导；同一接口名称不作为制造配合的证据。来源和局部检查见各产品的 `terminal-accessory.md`。本批没有浏览器逐面或硬件验收。
