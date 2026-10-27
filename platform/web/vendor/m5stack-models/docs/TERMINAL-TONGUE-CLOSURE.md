# 端子插舌孔口闭合修复

2026-10-26。在118款检查点后，修复AC Measure、AIN4-20mA、BLDC Driver三款可拆端子的插舌缺面：原2.5mm剖面叠加局部孔位偏移与0.025mm倒角后，四个下孔边与端面外缘相切，每款产生20条单边界。将剖面高改为2.9mm，保留孔下材料，坐标焊接后的15018条边均成对反向，正体积268.792612mm³，四孔轴向畅通且FrontSide孔壁可见。

只改每款TerminalPlug的这一尺寸字面量。旧/新对照确认外包络、端口、四个外驱螺钉、标签、所有非插舌几何及所有世界矩阵保持。原壳/PCB和其余型号未改，不用贴图或双面材质遮缺面。本次不提供制造公差或实物配合结论。

`node scripts/check-terminal-tongue-closure.mjs`检查三款实际插舌的闭合边、正体积、48条FrontSide孔壁射线及24条轴向空孔射线。额外局部检查覆盖12组Model/GroveModule裸座/插头配置的印刷开关、各自四螺钉角度插值/精确回位/无RPM/无输入回声、旧/新其他几何与包络保持。两份构建与回归通过；5188现有预览的118款catalog、修复三款和新批三款共6个运行chunk及13张对应PNG均与dist同字节。

[修订与新旧SHA](../artifacts/terminal-tongue-closure/repair.json) · [最终范围检查](../artifacts/terminal-tongue-closure/check.json)。三款研究目录另有 `terminal-tongue-closure.json`，当前sources/global manifest已更新SHA。原批22/23及批25的freeze、smoke和progress保留为各自源码快照，不能拿旧SHA当当前源。其余844个Unit文件、19core和7私有Scroll文件指纹保持，批25三款冻结源保持。

本次修订保存时为118款、全部modeled/0verified；当时GitHub为112款32c95e0，随后6款和本次端子修复未再提交推送。当前型号数量与Git同步状态以catalog、README顶部和Git日志为准。不做逐面浏览器、全量历史或实物验收。CSV、私有链接/映射、矢量原稿与中间件继续留仓库外，原贴纸PNG未改变。
