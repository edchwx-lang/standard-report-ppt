# V6.3 蓝图视觉还原修复：实施与验证

## 结论与状态

[文件] 已修改隔离工作树中的后锁定解构运行时，revision 为 **6.3.1**；不是只写方案。基线为 `b7a16f8`，分支 `codex/v6.3-visual-reverse-compiler`。本轮未 commit、未合并、未安装到全局、未上传/打 tag。

[日志/实际图片] TEST 两图及 S3 均完成两次 Windows 实际构建和一次定向视觉修订。最终结构通过、视觉带警告通过；没有第三次构建。不是像素级无损还原，也不代表换一张未见蓝图必然同样成功。

本轮是**已锁定蓝图回放**，没有重新解析 TEST 文档或重调 ImageGen，符合本次边界。历史 TEST/S3 项目未覆盖。

## 三图结果

| 样本 | 实际结果 | 已确认 | 剩余差异 |
| --- | --- | --- | --- |
| TEST-01 市场规模 | pass_with_warnings | 曲线/坐标轴/刻度/数字可编辑；插画、照片、Logo 独立裁剪；首轮文字挤压已消除 | 图表平涂代替渐变；密集正文略缩小；手机中无法辨识的源图字样用可编辑纹理短线表示，不宣称文字精确恢复 |
| TEST-02 区域与竞争 | pass_with_warnings | 世界地图真实底图；4 个品牌 Logo、8 个底部图标全部登记并插入；数据/标注可编辑 | 部分圆角与箭头比例不同，地图细线清理存在轻微接缝；核心判断末尾标点换到下一行属于固定母版区域，本轮不改 |
| S3 | pass_with_warnings | 地区地图/照片/图标/品牌素材恢复；百分号拆行、文案挤压与明显地图重影已消除 | 箭头/卡片渐变简化；省名行内粗细未单独重现；极细地图清理接缝 |

`visual_acceptance_passed:true` 的含义是本次查看未发现尚未处理的重大主体差异，**不是**“无差异”。警告保存在每个项目的 `.build/v63_visual_review.json` 和 `deconstruction_acceptance.json`。

[日志] TEST：181 个可编辑主体对象、33 个局部图片；S3：87 个可编辑主体对象、16 个局部图片。五个母版占位符额外保留，只填文字。对象数不是视觉质量分数；最终逐页图片已实际查看。

## 根因与修改

| 根因 | 修改文件 | 处理 |
| --- | --- | --- |
| 用母版比例猜源主体导致错裁/拉伸 | `v63_visual_tiles.py`、`v63_scene_graph.py` | 明确源 ROI；所有点/框/图片共用等比例 contain 变换 |
| 从旧场景继承缺项；地图身份被改成基础几何 | `v63_visual_census.py`、两个 V6.3 prompt | 独立对象身份/层级/编号预览；逐 Logo、图标、刻度普查；复杂地图默认底图裁剪 |
| 素材混入旧标注或透明方孔产生重影 | `v63_extract_scene_assets.py` | 派生局部蒙版/取色；原生覆盖物绑定；源/配方/alpha/输出哈希账本 |
| COM 富文本 Characters 调用方式错误 | `v63_windows_scene_renderer.py` | 使用索引属性调用及 UTF-16 偏移；真实中文/数字混色测试 |
| 文本框正确但自动换行导致数值/段落溢出 | 同上 | 主体显式 nowrap；可选一次测量/缩放，记录比例；不影响母版 |
| 开放路径闭合或只保留首尾点、曲线箭头缺头 | 场景及 Win/Mac renderer | 点集派生 bbox，保留开放节点与箭头 |
| 渲染/结构通过被误当视觉通过 | `v63_acceptance.py`、`v63_visual_delta.py`、`project_pipeline.py` | 本轮逐对象复核与完整输入哈希绑定；等待复核时不重新构建 |
| 新轮沿用旧复核导致异常终结 | 同上 | 旧证据失效视为未复核；纯 finalize 恢复，绝不授权第三轮 |
| Mac pt 边距写成 inches；第二页缺来源/页码 | `v63_mac_scene_renderer.py` | 修正单位、复用原五占位符 XML；不改母版文件 |
| 新 runtime 被旧版本检查拒绝 | `v6_contracts.py`、编译器与 `v6_mac_spec.py` | 仅 V6.3 后锁定 revision/分支元数据调整，schema6.0/6.3 不变 |

规则固定到 `SKILL.md` 的 V6.3 段与 `references/v63_visual_repair.md`；README、跨平台和质量文档仅补后锁定说明。测试数据/回放工具位于 `tests/*v63*`，不会成为生产中的固定布局库。

## 实际错误与修复证据

- 首次新增负例出现 11 个失败/错误，覆盖缺失变换/蒙版/普查语义和过早接受，不是把环境错误当成功。
- COM 实际错误：`(-2147352559, '不支持集合', ...)`，发生在 `TextRange.Characters(...)`；已以真实 COM 混合 runs 测试验证修复。
- 首轮三页结构通过但视觉不通过，记录并保存到 `.build/attempt_1/`，不能用结构测试掩盖文字重叠。
- 第二轮 TEST 构建与渲染已成功后出现 `V63_VISUAL_REVIEW_STALE`；未重建，修复状态处理后用原文件纯 finalize 恢复。
- Mac 两页首次结构编译报 `V63_SKELETON_MISSING_ROLE: source, page_number`；补多页回归后修复。
- 一次测试文件清理失败来自测试 PPT 未关闭，修测试关闭顺序；一次全量测试的 2 个错误来自 Mac 旧 `6.3.0` 校验，已修对应解构判断。

## 验证命令与边界

```powershell
python -m unittest discover -s tests -q
python -m unittest tests.test_v63_boundary -v
python C:/Users/edchw/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
python -m tests.check_v63_sample_delivery
git diff --check
```

最终全量测试结果见本报告末尾的最终核验记录。Skill 校验返回 `Skill is valid!`。真实缓存再次运行 TEST/S3，均返回 `cached:true`，PPT SHA 不变，build_attempt 保持 2、visual_refinement_count 保持 1。

[日志] 同一三页场景已通过 Mac 分支的 python-pptx/OOXML 实际结构编译与母版/素材/可编辑性审计。**未运行 PowerPoint for Mac；mac_native_render_unverified=true。** Office 字体自适配与真实排版仍需 Mac 验证。

冻结边界测试比较 V6.2.2 上游、位图专属文件与模板哈希；未修改冻结清单消除失败。共享文件改动仅在 V6.3 解构路由；未改 intake、ImageGen、锁图规则、位图链或交付包格式。

## 速度与实现偏差

[日志] TEST 首轮：预检 1.434s、编译 0.189s、COM 构建 25.712s、渲染 5.187s；第二轮：0.779s、0.138s、10.901s、4.712s。S3 第二轮构建+渲染+审计合计 13.360s。三图资产校验/提取第二轮：TEST 1.872s、S3 1.074s。缓存命中约 0.04s。

这些是机器执行记录，**不是整轮工作耗时**。人工视觉普查、场景编写和复核没有完整独立计时，不能据此声称“全流程只要十几秒”。本轮总体主要时间用于诊断、场景测量、代码/负例修正与回归，而非 COM 卡死。

保持原架构，未引入外部视觉服务或大型依赖。最终图表等仍由可编辑原子对象组成；不保证可恢复原始图表数据工作簿。完整任意自由形状轮廓的自动等价性证明、未知遮挡地理的无损恢复没有实现，依赖实际看图复核并记录残差。

按用户要求 Inline 实施；未运行独立子 Agent/新会话压力测试，也没有把本次三图成功当作 Skill 泛化能力的独立证明。

## 文件入口

- TEST 两页：`C:/Users/edchw/Documents/START PPT/V63_visual_repair_validation/TEST/output/TEST_V6.3_修复验证.pptx`
- S3：`C:/Users/edchw/Documents/START PPT/V63_visual_repair_validation/S3/output/S3_V6.3_修复验证.pptx`
- 源主体/实际 PPT 对照：验证目录下 `TEST_S01_comparison.png`、`TEST_S02_comparison.png`、`S3_S01_comparison.png`。
- 每项目保留 `attempt_1` / `attempt_2` 的 PPT、渲染、普查、场景和资产证据；当前接受记录在 `.build/deconstruction_acceptance.json`。
- Mac 结构产物：验证目录 `mac_structure/`，明确标为未原生渲染，不替代 Windows 成品。
- TEST 成品 SHA256：`0a130f3e509574cac3cd7c1899465deb629fa08c39247e8d1d5790321a8f5f66`。
- S3 成品 SHA256：`433b1e4276b9306169b8d96f5ebcf46fef0c192e1673247adb0cd73f8c11d12d`。

## 最终核验记录

[日志] 最终代码树全量测试：`Ran 475 tests in 75.499s`，`OK`，退出码 0。另行运行冻结边界 2 项：`OK`；Skill 格式校验：`Skill is valid!`；`git diff --check` 退出码 0（只有 Git LF/CRLF 提示，无差异格式错误）。

[日志] 母版及三张源蓝图 SHA-256 均与验证前 manifest 一致。全局 `C:/Users/edchw/.codex/skills/standard-report-ppt/SKILL.md` 仍显示 V6.2.2；本工作树 HEAD 仍为 `b7a16f8`，证实本轮未提交或全局替换。

[文件] 当前候选包含代码、指令和测试改动；本轮新增负例覆盖源 ROI、零宽高路径、层级/地图身份、蒙版、COM runs/适配、图片哈希/轮廓、验收终结/缓存以及 Mac 多页占位符。三页实际渲染与自动化测试是不同证据，均已分别记录。
