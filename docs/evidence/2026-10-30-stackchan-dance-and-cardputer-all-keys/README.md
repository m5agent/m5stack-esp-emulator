# StackChan 跳舞固件舵机与 Cardputer-ADV 全键复核

日期：`2026-10-30`

结果只覆盖下列完整镜像 SHA、browser QEMU WASM、导出 manifest 和原始
guest 路径。物理硬件为 `NOT RUN`；本记录不是机械、电气或 RF PASS。

## StackChan

用户完整 Flash：

- SHA256：`c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`
- 对应源码 SHA256：
  `7ee22ca570acd7f105d8205b3bc67ecc19e60ce11b1533f3481fc1288081bb9e`
- browser QEMU WASM：
  `5d6c36bdafc1129c2652b5ba9422f3deb5ab170475748cea96fdc4cf9520a993`
- 最终本地导出 manifest：
  `c27de9d6cc7230829d368b82fbf23a9f0cc39146dc716cab1e1eefd05f17b985`

根因不在 SCS 帧格式或网页状态读取。默认 1:1 虚拟时钟下，该固件的
`M5GFX` 首帧在 TCG/WASM 中约耗时 2.2 秒，超过跳舞 cue 的 400 ms 间隔。
循环每轮都会先吸收多个 cue、重置运动起点，再进入下一次重绘，因此长期
没有产生位置写包。最小 UART/SCS 固件与最小绘图探针分别证明 UART1、广播
`SYNC_WRITE`、QOM 和模型运动路径本身可用。

修复仅将这份完整 Flash SHA 绑定到
`stackchan-wasm-dance-div6`。同一探针的真实 6:1 虚拟时钟把首帧缩短到约
300 ms；官方参考固件和其他固件仍保持原 profile，不继承该选择。

同 guest 结果：

- 30 个有效 SCS 包，`rejected_packets=0`；
- 左右 present/goal 均为 `307..613`；
- 抬头 present/goal 均为 `677..850`；
- 23 个状态样本、1056 个真实帧；
- 3D 关节使用 present position，DOM ticks 和角度标签消费同一快照；
- 原跳舞固件串口初始化与 cue 序列保持；
- 正常 Stop 后 engine 与 5 个嵌套 pthread 目标全部关闭。

该 profile 是慢速虚拟设备兼容路径，虚拟时间不是物理实时性能。真机仍需
确认实际 SCSCL 舵机接受广播扭矩和位置写入。

## Cardputer-ADV

使用锁定源码、M5Cardputer `bf64d317`、M5Unified `0.2.28`、M5GFX
`0.2.35` 重建的 8 MiB 完整 Flash：

- SHA256：`4faaccde28367c257f7f140c139c434cf223be47de41ad853a168d9c25c2bd7b`
- browser QEMU WASM：
  `5d6c36bdafc1129c2652b5ba9422f3deb5ab170475748cea96fdc4cf9520a993`
- 最终本地导出 manifest：
  `c27de9d6cc7230829d368b82fbf23a9f0cc39146dc716cab1e1eefd05f17b985`

规范映射同时保存逻辑 4×14 键位、真实 TCA8418 7×8 坐标、CAD component
名、物理键帽字面和 PC `KeyboardEvent.code` 别名。测试通过真实模型输入和
原 `M5Cardputer.update()` / TCA8418 GPIO11 IRQ reader：

- 56/56 个物理键的按下、位置与松开；
- 55 个直接 PC code 到达各自真实物理开关；
- 左右 Shift、Ctrl、Meta、Alt 别名；
- `Escape` → Fn + grave，`Delete` → Fn + Backspace；
- 四个方向键 → 对应 Fn 和弦；
- 双 Shift 同时持有和分别释放；
- 四旋转、四角、局部 64 像素和原生纹理绑定；
- 正常 Stop 的 Worker/iframe 清理。

## 复现入口

```bash
node platform/tests/test_cardputer_keymap.mjs
node platform/tests/test_model_shell.mjs --case controller:cardputer-adv
node platform/tests/test_public_qemu_profiles.mjs

M5_PUBLIC_SITE=<reviewed-export> \
M5_STACKCHAN_IMAGE=<full-merged.bin> \
M5_STACKCHAN_IMAGE_SHA256=<sha256> \
M5_STACKCHAN_WASM_SHA256=<sha256> \
M5_STACKCHAN_MANIFEST_SHA256=<sha256> \
M5_STACKCHAN_OUT=.work/stackchan-dance-new \
node platform/tests/test_stackchan_dance_user_firmware.mjs

M5_PUBLIC_SITE=<reviewed-export> \
M5_CARDPUTER_IMAGE=<full-merged.bin> \
M5_CARDPUTER_IMAGE_SHA256=<sha256> \
M5_CARDPUTER_WASM_SHA256=<sha256> \
M5_CARDPUTER_OUT=.work/cardputer-all-keys-new \
node platform/tests/test_public_qemu_cardputer_input_display.mjs
```

原始报告、串口、帧和截图保存在忽略的 `.work/` 中，不提交固件、ROM、
设备标识或原始执行资产。
