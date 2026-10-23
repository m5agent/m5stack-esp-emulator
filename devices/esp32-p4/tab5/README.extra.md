### 当前可用的部分

- 官方 UIFlow2 镜像可启动，真实 M5GFX 绘制路径输出 1280×720 帧；
- 触摸、RS-485、C6 ESP-Hosted 和静态 I2C 寄存器探测可用；
- 可通过真实 `esptool write-flash` 分块写入 16 MiB 虚拟 Flash，逐字节校验后从同一镜像启动。

2026-10-22 定向复测结果：

```text
FLASH PASS
BOOT PASS
TAB5_UI_DRAWN PASS
```

该复测只覆盖“虚拟烧录、启动和测试 UI 标记”，不覆盖下表未完成的动态外设。

### 虚拟烧录边界

Tab5 不是“完全不能用”，但也还不是可以无条件审查任意生产镜像的烧录器：

- 当前验证使用与仿真 ELF 匹配的 UIFlow2 镜像；
- 为避免 `esp-emu 0.50.0` P4 下载模式的高位地址回卷限制，仿真分区布局把
  `factory/sys/vfs/storage` 放在 8 MiB 以下；
- 任意生产固件在烧录前仍需确认 Flash 布局、ROM/eFuse、镜像长度和分区地址是否兼容。

完整待办和恢复条件见
[`docs/tab5-deferred-backlog.md`](../../../docs/tab5-deferred-backlog.md)。
