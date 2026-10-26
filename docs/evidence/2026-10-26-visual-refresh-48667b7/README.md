# 固定公开外壳更新：48667b7

日期：2026-10-26。结果：**browser visual integration PASS**；firmware、QEMU 和 hardware execution **NOT RUN**。

从公开模型仓库 Git 对象固定导入 `48667b728736fbfd4365a06575473ce538d3c972`，不读取其不断变化的工作树。
包含14主机、29视觉Unit，新增Scroll与Roller485；内部协议库仍27种，新增两款没有controller/firmware准入。
原有controller与Unit历史功能证据仍绑定原来源，不因贴纸或外观更新自动升级为新外观的同guest整批PASS。

导入工具只接受已审核的65 PNG精确路径、SHA256与第三方许可通知哈希；验证静态ESM、动态import和资源URL闭包。
65图共10,655,483字节，保留provider公开分发许可及其图像/商标权利，不归入代码MIT许可。
补齐同一Three.js包的DecalGeometry，下载包按lock SHA512认证，不引入第二份Three实例。
未复制私有研究、原始CAD、矢量中间件或未提交资产。清单见 [vendor-manifest.json](vendor-manifest.json)。

[浏览器报告](report.json)记录14主机的帧像素、输入、实际背贴材质加载，以及29视觉Unit的挂载、输入、反馈不回声、释放和dispose。
全部65 PNG逐个执行image.decode，51层主机raster材质textureStatus为ready；无页面错误与缺失资源。
保留主机正背面及部分Unit截图；这是外观/桥接证据，不证明机械尺寸、电气功能、物理控制器或新固件运行。

重放：

```bash
PYTHONPATH=platform/tools:.work/py312 /opt/miniconda3/bin/python3.12 \
  platform/tools/sync_visual_models.py --source /path/to/public/m5stack-models --check
M5_MODEL_TEST_OUT=/tmp/m5-visual-replay node platform/tests/test_model_shell.mjs
```

来源、许可及资源闭包的失败控制由 `test_sync_visual_models.py` 单独覆盖。
