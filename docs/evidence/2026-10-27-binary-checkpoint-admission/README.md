# 二进制 checkpoint、旧程序保护与兼容固件构建

日期：2026-10-27。分类：限定 virtual-device validation；hardware NOT RUN。

API 1.44可保存显式main.mpy完整包并按原字节取回。当前stock固件没有受验
二进制脚本loader，普通session和Preview仍声明不支持；Run前返回409，不把
普通import或保存成功称为脚本执行。Web继续使用main.py。

四主机统一r2完成普通session和Preview两lane：8台独立VM内各A/B源码运行，
共16次源码执行、12次MPY入口拒绝、36次fresh PIR串口/QOM/选定PNG像素。
拒绝前后旧执行REST/磁盘记录不变，Preview generation/活动Run/取消状态不变；
inline拒绝不消耗包配额，随后同PID/固件/VM nonce运行源码B。
8个ZIP在关闭前取得，152成员核验；停止历史帧精确SHA保留，Flash/PID/owned
lease均清理。此批的main.mpy只有保存/读取，始终没有部署或执行。

[最终报告与原HTTP](hosts/index.json)、[实际范围](acceptance.json)及
[执行源码快照](sources/index.json)绑定同一最终runner/core代码；没有浏览器或
光学/电气/PIR物理时序结论。原stock固件SHA、runtime与session身份逐lane保存。

[原r1尝试](attempts/index.json)保留三host PASS/superseded，以及StopWatch
圆屏角落像素oracle FAIL。该轮串口/QOM正确但角落不可见；cleanup PASS不升级
整lane。把marker移至中心下方并增加几何负控后，四host全部用同版r2重验。
[最终宿主验证](verification.json)另保留首轮旧断言失败、修复及旧schema记录回读。

[官方兼容固件构建](firmware-build/index.json)已在固定UIFlow/MicroPython/IDF
源码上完成CoreS3 pack_all、两宏实际预处理及image/partition检查。合并镜像SHA
`7ce5ca0744a27508913c4dd69dd06f30454fb27c54a920faf486d3350cf2267b`，
16121856字节；二进制不入库。它仍是LOCAL_BUILD_PASS_NOT_GUEST_ADMITTED，
没有替换stock reference，也没有启用公共MPY入口；下一步经8787独立验收。

[下一批Unit研究](research/index.json)核对4Relay通道位序冲突与FlashLight的
AW3641E全16编码，保留官方原驱动、datasheet页面和accepted反馈。尚未增加
Unit功能准入；未定义的锁存/超时起点/动态模式切换不能伪称芯片事实。

[归档清单](artifact-manifest.json)和[隐私检查](privacy-final.json)用于完整性核对。
整体UNIT-01/AIFlow、二进制执行、其它Unit与真机同路径仍继续开放。
