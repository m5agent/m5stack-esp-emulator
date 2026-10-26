# Host9 独立严格选择与配置晋级

本目录只选择 AtomS3R、StickS3、StopWatch 各自的 Button、Relay、ENV III，合计 **9 个实际组合严格功能 PASS**。三份 selection 均覆盖原 canonical27 Unit 清单：guest/controller 与 live-browser 各 3 PASS、24 NOT RUN，整体诚实为 **PARTIAL**。桥契约只证明全27表单/生命周期，不执行固件，也不把其他24款 Unit 放开到这三台主机。

每一组合的 guest/live 两层选择同一 outer wrapper、已承诺 raw controller assertions、同一运行中 ZIP、session/device/runtime/firmware 与 direct PID executable SHA。九个组合均绑定 a8fe runtime 和 worker generation9；没有用间接 service-generation proof。严格CLI每台预期退出2（PARTIAL）；aggregate 只汇总明确选择的9项并为PASS。

**功能与画面分列**：9张 native frame PASS；Button/Relay六张浏览器 framing PASS；三张 ENV 浏览器截图因 sticky header 遮住 session 标题/顶边，framing 为 **PARTIAL**。输入、DOM读回、串口和PID/ZIP的严格功能结果仍PASS，不据此声称完整视觉验收。未重拍或替换截图，也未由本次审核新建任何 guest。

[独立完整性审核](validation.json)验证源归档219条SHA、九份outer共411个artifact哈希引用、每例10个raw browser源指纹与原执行前freeze一致，并完整解码35张公开PNG。原始gen9归档与执行前freeze保持原字节。[helper补充审核](helper-archive-time-audit/report.json)只提供archive-time hash及与既有CoreS3快照/矩阵/HEAD的continuity辅助证据；它不是host9逐执行前hash，没有回填原freeze，也不试图闭合stdlib或整个解释器依赖树。

[配置promotion receipt](configuration-promotion.json)记录runtime-profiles旧/新SHA：仅九个已有准入组合的host_validation从NOT RUN更新为精确证据PASS；整体仍为implemented，三款hosts列表与其余24款profile均未变。CoreS3独立27选择未改。ENV framing PARTIAL同样写入metadata。该变更不代表硬件验证、不代表整台主机27项完成，也没有触发服务重启；旧gen9执行仍使用旧profile SHA。

配置后的离线复验为 **34项平台Unit契约、43项批证据故障测试、9项runtime provenance测试，合计86项PASS、零skip**。新增语义契约遍历实际PASS metadata，核对host/Unit/firmware/session与direct PID、ZIP manifest、worker generation、两层严格选择；7种仅内存中的错主机、错固件、错hash、间接proof和错selection变异均被拒绝。该检查不新增guest执行。

复验例：

```sh
PYTHONPATH=tests/units:.work/py312 python3.12 tests/units/check_batch_evidence.py \
  --selection docs/evidence/2026-10-26-unit-host9-selection-a8fe/atoms3r/selection.json \
  --strict-direct
```

预期PARTIAL/退出2；另外两份selection分别位于sticks3与stopwatch目录。历史正式selection没有被替换。
