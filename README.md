# Standard Report PPT · V6.3.1

**中文** | [English](README.en.md)

面向 Codex 的固定母版研究报告 PPT Skill：先理解材料、生成视觉蓝图，再选择保留蓝图观感的位图版，或便于后续修改的可编辑解构版。

V6.3.1 的核心是**蓝图锁定后的视觉反向编译**：观察对象的实际位置、颜色、层级与关联，而不是把蓝图重新套进矩阵模板。Windows 使用 PowerPoint COM；macOS 使用共享场景的 python-pptx/OOXML 路线。

## 同一页，三张实际示意图

TEST 文档中的市场规模、全球区域销售市场、企业竞争合为一页。两份 PPT 使用同一张锁定蓝图，不是分别生成的设计。

### 1. ImageGen 原始蓝图

![TEST 单页原始蓝图](docs/images/S01.png)

### 2. 位图模式 PPT

![位图版 PowerPoint 原生导出](docs/images/S02.png)

五个骨架区域可编辑，主体为一张裁切图片，适合快速交付并直接保留蓝图观感。

### 3. 解构模式 PPT

![解构版 PowerPoint 原生导出](docs/images/S03.png)

此实例主体包含 **195 个可编辑对象、11 张局部图片**，另外保留五个母版占位符。文字、数字、图表组件和基础图形可以修改；地图底图和产品插画保留图像细节。

> 这是视觉恢复示例，不是经审校的行业研究发布。原蓝图的欧洲引线与部分条形比例存在误差，示意图保留原样；生成的品牌插画不代表授权或背书。重叠产品的可见图像带不等同于完整透明抠图。

## 两种模式怎么选

| | 位图模式 | 解构模式 |
|---|---|---|
| 蓝图 | 必须生成并锁定 | 必须生成并锁定 |
| 五个骨架区域 | 可编辑 | 保留原母版占位符，只替换文字 |
| 主体 | 一张裁切图片 | 按蓝图逐对象重建 |
| 主体文字、数字、图表、表格、基础几何 | 不可单独编辑 | 可编辑 |
| 复杂地图、Logo、照片、插画 | 包含在主体图中 | 允许无正文的局部裁剪，Logo 自带文字可保留 |
| 使用取向 | 更快，直接保留观感 | 较慢，便于后续修改 |

图表可由原生轴、路径、矩形、节点、文字组成，不承诺全部为附带 Excel 数据表的 Chart 对象。两种模式不相互静默降级。

## 安装

需要支持本地 Skill 且有内置 ImageGen 权限的 Codex 环境。Windows 需要桌面版 Microsoft PowerPoint、Python 3.12 及锁定依赖；Mac 使用 Python 3.12，视觉验证需要 PowerPoint for Mac 或受支持的本地渲染环境。

Windows 全新安装：

```powershell
git clone --branch v6.3.1 --single-branch https://github.com/edchwx-lang/standard-report-ppt.git "$env:USERPROFILE/.codex/skills/standard-report-ppt"
python -m pip install -r "$env:USERPROFILE/.codex/skills/standard-report-ppt/requirements-windows.lock"
```

macOS 全新安装：

```bash
git clone --branch v6.3.1 --single-branch https://github.com/edchwx-lang/standard-report-ppt.git "$HOME/.codex/skills/standard-report-ppt"
python3 -m pip install -r "$HOME/.codex/skills/standard-report-ppt/requirements-macos.lock"
```

已有安装请先备份并检查本地修改，不要覆盖未提交文件。标签固定本次发布；跟随开发版本可使用 `main`。安装后重新加载技能列表或开启新任务。

## 怎么用：从材料到 PPT

上传文档并明确页数和模式：

```text
$standard-report-ppt 用 TEST.docx 做 1 页 PPT，解构模式。
解析市场规模、全球区域市场和企业竞争三个部分，合为一页。
```

也可以指定“位图模式”，或明确要求用同一张蓝图分别验证两个模式。

1. **确定页数与模式。** 这是仅有的两个常规用户确认；不额外增加未要求的封面、目录。
2. **结构化解析材料。** 读取正文、表格及嵌入图片，保留数字、年份、单位、限定条件和来源；组织结论与证据，不把销售额写成产能。
3. **生成蓝图。** 依据证据选择图表、地图、关系结构或图文表达；不为方便重建而限制成矩阵。每页接受一次成功 ImageGen 结果。
4. **锁定原图。** 正式蓝图保持原始字节与哈希；不能因为还原困难反复生成。
5. **进入所选路径。** 位图检查全页并裁除骨架；解构观察真实主体边界，查看整图与六块重叠切片，先写独立视觉清单，再编译原子场景。
6. **重建并分离素材。** 正文、数字、图表、表格、连线和基础几何可编辑；复杂视觉局部裁剪，地图标注与引线单独重建。母版的章节、标题、核心判断、来源、页码只填文字。
7. **真实渲染与有限修正。** 查看实际 PPT 导出，检查遗漏、重影、裁剪、几何与字体；明显视觉差异最多定向修正一次，不进入第三次自动构建。
8. **验收与交付。** 检查真实 PPT、母版、素材和哈希，再交付。打包失败只恢复打包，不重做已验收 PPT；普通残差明确说明。

默认 ZIP 包含最终 PPTX、`blueprints.zip`、`py.zip`，后两者保留蓝图/素材/场景及生成入口。重新运行入口仍需要匹配的技能运行时和项目清单，并非独立应用。明确只要 PPTX 时不强制 ZIP。

## V6.3.1 的修复与边界

- 独立普查、逐 Logo/图标登记；复杂地图保留真实底图，不改成示意多边形。
- 同一主体坐标变换，避免图片、文字、引线分别拉伸；主体文字可按实际字体度量适配一次。
- 支持源像素圆角半径，两端共用可编辑轮廓，不再只能依赖默认大圆角。
- 打包识别 V6.3 验收/编译协议，按真实素材账本收集图片，仍拒绝失效哈希。
- 补充 Windows 配套 Node 发现；位图外部预览失败可对现有 PPT 做一次原生导出恢复，不重新构建。
- 区分 PPT 已验收与 ZIP 已打包，保留失败信息；最多两次实际构建、一次视觉修订。

**边界：** 蓝图生成前的内容与 ImageGen 链路不变，正式蓝图字节不变，位图裁切与排版逻辑不变。位图补丁仅限锁定后的预览环境和恢复。用户母版不变。

**平台验证：** Windows 双模式实例已实际运行。Mac 共享几何/编译有自动化覆盖，但本版本未完成 Mac 实机原生渲染验证，须标记 `mac_native_render_unverified`，不能把 Windows 结果当作 Mac 视觉证明。

## 开发与验证

```bash
python -m unittest discover -s tests -p "test_*.py"
```

普通用户无需手写场景或逐条执行 CLI。调试已经准备好的工程时：

```bash
python scripts/project_pipeline.py <project> --init
# Agent 按 SKILL.md 准备内容、真实 ImageGen 调用记录、蓝图和模式专属视觉记录
python scripts/project_pipeline.py <project> --materialize
python scripts/project_pipeline.py <project> --run --output <project>/output/report.pptx
```

`awaiting_visual_review` 是内部继续状态：Agent 查看实际渲染、记录判断后，再次 `--run` 完成验收，不应要求用户审批或重新构建。

详细标准：[SKILL.md](SKILL.md) · [后锁定解构规范](references/v63_visual_repair.md) · [发布验证](docs/releases/v6.3.1.md)。仓库不包含 TEST 原始 Word 或完整用户工程；使用者须确认素材、Logo、母版及生成内容的使用权限。
