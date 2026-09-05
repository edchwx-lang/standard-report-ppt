# V6.3.1 后锁定解构标准

仅适用于正式蓝图锁定后的 `construction_mode: deconstruct`。沿用 V6.3 七线模型与原子场景，不重写上游、位图、母版或旧版兼容路线。本文件优先于 V6.3.0 的同名后锁定说明。

## 1. 视觉权威与独立观察

母版拥有章节、页标题、核心判断、来源、页码五个原占位符：只替换文字，其他设置不动。蓝图主体才是视觉还原权威；两者分别验收，不把源图标题样式复制到母版。

先看原图，不读旧场景生成普查。记录 `.build/v63_source_body_rois.json`：

```json
{"pages":{"S01":{"blueprint_sha256":"实际源图SHA256","source_body_roi_px":[48,210,1588,643],"review_basis":"已查看全页；排除五个母版区域"}}}
```

ROI 是源像素 `x,y,width,height`。调用 `v63_visual_tiles.generate_review_tiles(project)` 生成 PAGE、FULL 和 B01–B06；查看全部切片。无 ROI 时由当前 Agent 补齐，不把内部准备状态变成用户审批。

逐项记录 census：对象身份 `observed_subject`、bbox、层级、预期处理与查看证据。Logo、图标、图表刻度、数字、单位、连线不能因小而省略。父面板不能代替子项。查看编号预览并查漏一次。程序只证明已声明对象的覆盖，不证明机器识别了图中全部对象。

## 2. 原子场景与可编辑性

所有可辨识报告文字/数字、表格、图表与基础几何编译为原生可编辑对象。图表允许由原生路径、轴、文字、图例组成，不要求改成另一种图表样式。复杂地图、Logo、图标、照片、插画可裁剪；Logo 自带字样除外，不能把正文留在图片中。

每页声明 `coordinate_mode: source_pixels_contain`。bbox 是源像素 `x1,y1,x2,y2`；所有路径点、裁剪和文字共用一个等比例变换：

`s=min(target_width/source_width,target_height/source_height)`，居中放进母版主体框。

不分别拉伸 X/Y。线的 bbox 从点集派生；开放路径声明 `closed:false`，保留所有节点和箭头，不能只取首尾点。旧场景默认兼容解释，不偷偷换坐标语义。

源图是小圆角时，`round_rect.style.corner_radius_px` 显式记录实际源像素半径。
两端将其归一化为同一可编辑 freeform 轮廓；不填时保留历史默认行为。
不得用 PowerPoint 默认圆角半径冒充已经测量的蓝图轮廓。

主体文字先量字宽、字高和原换行，再选字号；中文/数字混色使用 runs。无源换行的短标签用 `word_wrap:false`。确需有限适配时可显式用 `fit:"shrink_to_box"`：Windows 按实际 COM 字形包围框测量一次、统一缩放一次，不改变文本内容或框位置。缩放比写入对象账本；明显缩小要在视觉复核记录，不能以“放得下”代替还原。该功能不作用于五个母版占位符。

Mac 仅写入同义 nowrap 和 Office text-to-fit 请求；其最终字体度量需真实 Mac 打开验证，当前始终标记未验证。

## 3. 复杂素材分层

复杂地图优先使用真实底图局部裁剪，不把地图身份改为 basic_geometry 后画示意多边形。地名、定位点、连线、数字、图例分别原生还原。

`image_crop.crop_recipe` 支持：

- `rect_crop`：无正文、无外框、单主体紧边界裁剪。
- `masked_crop`：局部透明排除；各多边形绑定原生 `overlay_element_ids`。
- `local_cleanup`：仅对已检查的局部近似纯色区域取源像素填补；含 `sample_px` 和 `uniform_background_reviewed:true`。不生成未知地理、不改原蓝图。

多边形和取色点都是裁剪内局部坐标。每次排除都要有实际原生覆盖物，不能靠“contains_text:false”自证干净。透明孔洞只在最终原生对象确实覆盖时使用；圆定位点别用方孔，斜线别挖大矩形，先查旧线真实端点。底图与可编辑标注使用同一坐标变换。

看派生素材以及最终组合，不只看原始裁剪。跨渐变/海岸的局部清理可能留接缝；不能声称可恢复被原始标注遮住的未知地图。保留警告，不进入生成式补图或第三轮。

资产账本绑定源蓝图、source_px、配方/alpha/输出哈希、候选 ID、场景 ID 与插入次数；最终审计图片字节一致、无轮廓/显式效果、不可重复或漏插。不同品牌/不同图标不能合成一张资产来冒充覆盖。

重叠遮挡的产品逐项登记可见区域，不编造被遮挡部分。无法干净分离时明确记录
裁剪残差或可见图像带的限制，不能宣称完整透明抠图；仍不得以大块复合截图替代
正文、图表或漏掉独立 Logo。蓝图自身的地理定位/图形刻度错误单独报告，视觉
相似不等于事实正确；原始蓝图字节不可改写。

## 4. 一次汇总检查与有界终结

当前任务内 Inline 执行，不按阶段启动独立 Agent。准备数据后一次汇总预检；构建整份 PPT，保存并原生渲染。查看每页实际结果，对照源主体和独立普查记录，不以相似度分数代替看图。

写 `.build/v63_visual_review.json`：`reviewed:true`、`bindings`（由 `v63_acceptance.visual_bindings(project,pptx)` 生成）、各页 `object_checks`（candidate_id/status/evidence）、`differences`（severity/message/candidate_ids）。检查是人工视觉判断记录，严禁从元素存在数量自动填成“视觉通过”。

`status` 为 present/difference/missing；差异 severity 为 warning/material/blocker。明细绑定实际证据框；原生渲染、结构可编辑、视觉还原是三种不同证据。

- 待复核：`awaiting_visual_review`，当前 Agent 补记录后继续 `--run`；只 finalize，不构建。
- 首轮重大视觉差异：合并为唯一修订清单，最多一次定向主体修订。
- 普查可有证据补录/纠错，保留 `.build/v63_census_original.json` 和 `v63_census_amendments.json`；不能删除候选、降级可编辑内容、改上游事实或改蓝图。
- 第二次结构有效且仅普通视觉残差：`deliver_with_warnings`，结束。若仍有重大残差，`visual_acceptance_passed:false`，不能说视觉通过。
- 结构损坏/缺失关键内容：失败结束并交付诊断，不增加第三次构建，不通过新工程重置预算。
- 新渲染让旧复核失效属于正常状态；旧复核不能放行新文件，也不能被当成一次新的构建故障。

每工程最多两次实际构建、最多一次视觉修订，故障恢复不增加预算。缓存同时绑定蓝图/母版/场景/普查/资产/渲染/PPT/复核；已接受且未变的文件直接复用。上游事实、源 ROI 和五个母版对象不属于视觉修订范围。

## 5. 跨平台与交付口径

Windows 使用现有 COM；Mac 使用 python-pptx/OOXML 共享语义和资产，不调用远程 Windows、不以截图替代本应可编辑的元素。Windows 上跑通 Mac 分支只能证明结构编译，不证明 Mac 原生渲染。

交付分别报告：本地代码是否修改/提交/安装、实际构建次数、结构结果、逐页视觉结果、残差和 `mac_native_render_unverified`。三图回放使用 TEST 两张既有正式蓝图和 S3，不重调 ImageGen、不覆盖旧项目。冻结边界与自动化测试通过不等于像素级一致。

V6.3.1 发布补丁：打包识别 V6.3 验收和编译 schema，校验本轮哈希绑定，按
`v63_asset_ledger.json` 收集真实素材，不从旧 visual_plan 推测已经插入的图片。
`pptx_accepted:true` 与 `delivery_status:packaged` 分开记录；ZIP 失败写
`delivery_status:failed` 和错误，后续 `--run` 只补打包，不重新构建/渲染。
