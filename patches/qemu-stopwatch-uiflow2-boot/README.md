# QEMU StopWatch UIFlow2 启动补丁

- 上游：`zqqf16/M5StopWatch-QEMU` v0.1.0 @ `32d86576e783988fef1a489cb362dfda92a7aeda`
- 应用树：`build/qemu` base @ `da100c909249926b9f4458f18e4f2d216d08f51a`
- 补丁：`0001-qemu-uiflow2-stopwatch-boot.patch`

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
