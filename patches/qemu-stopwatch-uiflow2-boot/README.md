# QEMU StopWatch UIFlow2 启动补丁

- 上游：`zqqf16/M5StopWatch-QEMU` v0.1.0 @ `32d86576e783988fef1a489cb362dfda92a7aeda`
- 公开基线：`espressif/qemu` tag `esp-develop-9.2.2-20260417`
  （`6cdce334bfa5541a5e46c860a9b40a4fe5a13aae`），先应用
  `zqqf16/M5StopWatch-QEMU` v0.1.0 的 5 个补丁
- 补丁：`0001-qemu-uiflow2-stopwatch-boot.patch`

`da100c909249926b9f4458f18e4f2d216d08f51a` 是开发工作树中的中间对象，
不是公开可获取的上游 pin。不要按该对象重新建树。

应用：

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/0001-qemu-uiflow2-stopwatch-boot.patch
```

回滚：

```bash
git apply -R /path/to/0001-qemu-uiflow2-stopwatch-boot.patch
```

补丁不包含 `build/qemu/meson.build` 的本地 slirp 构建修复。
