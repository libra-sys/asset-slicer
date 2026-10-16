---
name: asset-slicer
description: 把设计稿/图片/PDF 材料拆成可继续编辑的资产——出图→切图一体化流水线（artgen+detect/grid-detect）、独立图层、透明 PNG、PSD/SVG 分层，批量/网格切图（雪碧图、游戏 UI），SLG 外观主题批量探索与规格落位，PDF 转图+隐私打码，以及 PPT 配图可编辑化。当用户要抠图、切图、拆图层、去背景、批量切图、导出透明素材、出图后切片、游戏 UI 切图、PDF 材料进 PPT、PPT 配图可编辑化时使用。
agent_created: true
---

# 资产切片 / 切图（通用多模式）

一个 skill 覆盖「出图 + 拆图层 + 切图 + 规格化 + 批量外观工作流」。主场景是**游戏开发**，同时为 `contest-ppt-generator` 提供可编辑配图。

**最快上手**：想出图并切成素材，直接看下面「⚡ 模式 E」——一条命令链跑完，不需要先想文案。

## 何时用
抠图去背景 / 拆成独立图层 / 批量或网格切图（雪碧图、游戏 UI）/ SLG 外观主题批量探索 / 给 PPT 配图做可编辑化 / **出图后自动切片** / PDF 材料转图进 PPT / **整页死图 PPT 的 OCR 复活**。

## 🔧 是否需要配置
**本地切图命令（trim / grid / detect / grid-detect / debg / dedup / adapt / batch）无需任何配置或API**，装好依赖即可用。
只有「AI语义拆层」才需要 API——走`contest-ppt-generator` 的配置（见其 `references/api-config.md`）。

## 模式
| 模式 | 用途 | 关键产出 |
|---|---|---|
| **A · 拆图层/PSD** | 设计稿 → 可编辑分层 | 独立图层 PNG、PSD / SVG 分层 |
| **B · 批量/网格切图** | 雪碧图、UI 批量 | 按网格 / 透明边界切片 |
| **C · SLG 外观工作流** | 主题探索→选型→规格落位 | 多候选独立编号 + 规格化资产 |
| **D · PPT 配图处理** | 给 PPT skill 配可替换配图 | 透明 PNG / 统一规格 |
| **E · 出图→切图流水线** | API 出图后自动切分，直接可切 | 出图 → detect/grid → cards |
| **F · 死图复活（OCR）** | 整页死图 PPT → 文字可编辑 | OCR → 抹字 → 重建文本框 |

>⚠️ **切图不是终点**。切件是**中游资产**，必须交给 `contest-ppt-generator`
> 落位成 .pptx 才算交付。完整闭环 = 出图 → 切图 → **落位** → 自检。
> 只交PNG 切片等于没做完。

> 🚨 **另一条铁律**：如果拿到的 PPT 是「整页死图」（每页 1 张整图 + 0 个文本框），
> **切图救不了**——图里没有可切的对象。必须走**模式 F：OCR 复活**。

## ⚡ 模式 E：出图 → 切图（可独立跑，不依赖文案环节）

**这是最常用的模式**：不需要先想文案，传个prompt 就能跑完整链路。

```bash
# 1) 出图（自动先预估积分 → 同步优先，失败转异步并轮询）
python scripts/slice.py artgen \
  --prompt-file prompt.txt --name hero --size 1K --outdir ./out

# 批量出图（一次跑多张，各独立命名，默认 4 路并发）
python scripts/slice.py artgen --jobsjson jobs.json --outdir ./out --jobs 4
# jobs.json: [{"name":"a","prompt":"...","model":"gpt-image-2","size":"1K"}, ...]

# 2) 切图 —— ⚠️ 深色底图必须先 debg，否则 detect 只认到 1 个
python scripts/slice.py debg out/hero.png --tolerance 28 --trim -o out/hero_nobg.png
python scripts/slice.py detect out/hero_nobg.png --min-size 200   # ✅ 元素大小不一/位置随机
python scripts/slice.py grid-detect out/hero_nobg.png --force     # 规则雪碧图（⚠️深色底要 --mode dark）

# 3) 去重 + 规格化
python scripts/slice.py dedup out/hero_detect --outdir ./dups
python scripts/slice.py cards --input out/hero_detect --outdir ./cards --width 600 --height 840
```

### ⚠️ 模式 E 最重要的一条：深色底图先 debg

实测踩过：AI 出的图往往是「深色底 + 深色元素」（如深蓝底上的深蓝圆角图标块）。
此时元素与底图颜色接近，**alpha 通道和连通域都识别不到边界**：

| 直接 detect | 先 debg 再 detect |
|---|---|
| ❌ 识别 1 个元素（整张当成一块） | ✅ 正确识别 9 个元素（~570×580） |

**判断标准**：出图 prompt 里出现 `dark background` / `deep navy` / `black bg` 时，**一律先跑 `debg`**。

> `grid-detect` 对深色底图要用 `--mode dark`（找深色分隔线），否则默认的 `--mode light` 找不到缝。实测深底图即使 debg 后用 grid-detect 仍会误判（7×7），**深色底图优先用 `detect`**。

### detect 参数怎么调（实测，别只会用默认值）

`--min-size` / `--min-area` / `--alpha-threshold` **必须按图的元素大小调**，默认值只适合大块面板：

| 参数 | 管什么 | 什么时候调 |
|---|---|---|
| `--min-size` | 元素**宽高**（像素） | 碎片太窄/太矮 → 调大 |
| `--min-area` | 元素**面积**（像素²） | 碎片宽高够但面积小（热力图格子、图表小柱子）→ 调大 |
| `--alpha-threshold` | alpha 二值化阈值 | 浅色描边没被识别 → 调小 |

**症状 → 病因**：
- `识别 0 个元素` → `min-size` / `min-area` 太大（大元素被一起滤掉）
- `识别 1 个元素` → 没跑 debg，元素和底色连成一片
- `识别数远多于预期` → 元素内部被笔画分割，或图里有大量小碎片 → 调大 `min-area`
- `大面板消失只剩内部碎片` → **debg 容差太大，把白卡片当背景吃掉了**，见下

### ⚠️ debg 容差不是越大越好（本轮最关键的一条）

实测用 `--tolerance 30` 时，**白卡片（255,255,255）和浅灰底（245,246,248）差异只有 ~10，
被一起当背景吃掉了** → dashboard 的 5 个完整面板被切成 9 个柱子/扇形碎片。

**正确做法：容差要远小于「元素与背景的实际色差」**。浅底扁平图用 `--tolerance 4`。

| 容差 | dashboard 结果 |
|---|---|
| 30 |❌ 9 个碎片（柱子、扇形、小格子），面板没了 |
| **4** | ✅ **5 个完整面板**，尺寸与原图布局完全对上 |

### 一套通用的出图→切图参数（浅底扁平图标类，2026-10 实测）
```bash
python scripts/slice.py debg   raw/x.png --tolerance 4 --trim -o raw/x_nobg.png
python scripts/slice.py detect raw/x_nobg.png --min-size 100 --alpha-threshold 30 --min-area 60000 -o slices/x
```

**⚠️ 重切前必须清空输出目录**，否则新旧文件累积（实测一度显示 24/81 个，实际只有 9 个）。

### 切完必做：拼一张 contact sheet 自查

切完不要只看「识别 N 个」就收工——**拼成一张网格图肉眼过一遍**，才能发现某个元素粘连、缺角、被腰斩。10 行代码搞定：

```python
import os, glob
from PIL import Image, ImageDraw
files = sorted(glob.glob(r'slices/x/e*.png'))
cols, cell, pad = 5, 220, 14
rows = (len(files)+cols-1)//cols
sheet = Image.new('RGB', (cols*(cell+pad)+pad, rows*(cell+pad+26)+pad), (245,246,248))
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert('RGBA'); im.thumbnail((cell-20, cell-20))
    bg = Image.new('RGBA', (cell, cell), (255,255,255,255))
    bg.paste(im, ((cell-im.width)//2, (cell-im.height)//2), im)
    x = pad+(i % cols)*(cell+pad); y = pad+(i//cols)*(cell+pad+26)
    sheet.paste(bg.convert('RGB'), (x, y))
    d.rectangle([x, y, x+cell, y+cell], outline=(200,203,208))
    d.text((x+4, y+cell+6), os.path.basename(f)[:14], fill=(60,64,72))
sheet.save(r'slices/x_contact.png')
```

**artgen 已内建的三条实测铁律**（不写进去就会踩）：
1. **必须带 `provider` 字段**，否则 400。取值只有 `openai / google / quotaflow / alibaba / bytedance`；脚本已按 model 自动映射，也可用 `--provider-name` 强制指定。
2. **自动先调 `estimate-credits` 预估**，`canGenerate=false` 直接退出不烧积分。
3. **轮询必须容错**——实测 1K 出图 60–90 秒，且轮询会偶发 read timeout，脚本已内置重试。

**⚠️ 批量出图必须并发**：实测单张 1K 出图 **3–10 分钟**（同步端点常超时转异步），
串行 6 张 ≈ 1 小时。`artgen` 已内置 `--jobs N`（默认 **4**）线程池并发，
`--jobs 1` 才是串行。2026-10-08 实测：串行跑 14 分钟只出1 张，改并发后 5 张同时在跑。

## 🚨 模式 F：整页死图 PPT → 全可编辑（OCR 复活）

**触发条件**（三者同时满足）：每页只有 1 张整图 + 0 个文本框 + 用户要求「文字也要可编辑」。
典型来源：NotebookLM / Gamma / Canva导出的 PPT——文字全烧进像素。

**先判定，别白干**：

```bash
python -c "from pptx import Presentation;from pptx.util import Emu
p=Presentation(r'x.pptx')
for i,s in enumerate(p.slides,1):
    pics=sum(1 for sh in s.shapes if sh.shape_type==13)
    tbs=sum(1 for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip())
    print(i,pics,tbs)"
# 每页 pics==1 且 tbs==0 → 死图，必须走模式 F
```

### 三步流水线（参考实现：`nb_ppt/step1~3_*.py`）

```
① OCR 识别  → step1_ocr.py      → ocr/pNN.json（坐标+文本+置信度+字色）
② 抹字留图  → step2_clean.py    → clean/pNN.png（无字底图）
③ 重建文本框 → step3_rebuild.py  → 可编辑版.pptx
```

#### ① OCR 选型

| 方案 | 结论 |
|---|---|
| **`rapidocr_onnxruntime`**（RapidAI/RapidOCR, Apache-2.0） | ✅ **首选**：纯 ONNX、免 Tesseract 可执行文件、单页 ~1.8s、199 块均置信 0.87 |
| pytesseract / easyocr / paddleocr / cnocr / doctr | ❌ 本机未装且多需额外模型或GPU |

后处理必做：数字与单位间补空格（`$292M`）、OCR 丢标点补回、`score = float(score)`。

#### ② 抹字：**必须整块重建底板，绝不能逐像素修补**（本轮最贵的一条经验）

四种方案连续失败：

| 方案 | 结果 |
|---|---|
| 整矩形填背景色 | 表格高亮块、选中列、描边按钮被一起抹掉 |
| 只抹与OCR 字色相近的像素 | 白字变灰影、橙字残留 |
| 自适应阈值逐像素筛 | 白字与浅灰底色差太小，仍有残影 |
| 同行左右邻域插值 | 仍有残影 |

> **结论：只要旧字迹还残留哪怕 10%，新文字叠上去必然出鬼影。必须按文字块整块填纯色，
> 完全不保留原字迹像素。**

🔴🔴 **底色必须在文字框【外圈】采样，绝不能在框内采样**（本轮第二个最贵的坑）：

`block_bg_color()` 用 `inset = min(ring, (x1-x0)//3)` 取四角与边中点。对**高而窄**的文字框
（如 1187×45 的页标题），`inset_y = 45//3 = 15`，采样点 `y0+15 / y1-15` **正好落在笔画上**
（大标题字高就有 40px）→ 中位数取到白色字色 → 把标题区填成灰白块。

实测证据（p07 标题下方那条灰条）：

```
原图 (543,215)=[34 37 46]   底图=[150 147 149]   ← 深色被填成灰白
原图 (669,240)=[251 253 252] 底图=[150 147 149]   ← 白字被填成灰白
```

✅ 正确做法：**在框外 3 / 8 / 16px 三层外圈采样**（那里必然没有该文字的笔画），
并且只取外圈里**最暗的那 45%**像素的中位数——页面底色永远是最暗的，
这样能自动排除邻近的装饰线、电路纹理。

```python
for pad in (3, 8, 16):
    ring = 外扩 pad 的矩形 - 原矩形   # bool mask
    samples.append(a[ring])
px = concat(samples)
lum = px.mean(axis=1)
bg  = median(px[lum <= percentile(lum, 55)])   # 只取暗的那批
```

`pad` 用 **1**，不要放大到 5——OCR 框本身已含笔画余量，pad 大了会露出一圈纯色矩形。

#### ③ 重建时的三个硬要求

1. **像素→EMU 线性映射**，不能靠猜：
   `EMU = px / PX_W * SLIDE_W_IN * 914400`
2. **字号双源反推**，并封顶：
   ```python
   by_h = h_px * 0.9375 / 1.35
   by_w = w_px * 0.9375 / (字符数 * 0.52)
   sz = max(by_h, min(by_w, by_h * 1.6))   # 只按框高→大数字偏小；直接 max→算出 200pt
   sz = min(sz, 72.0)
   ```
3. **框宽要能装下反推后的字号**：字号是反推的（偏大），只按 OCR 框宽给会把长句裁掉
   （实测 `Conversion (Bottom Funnel)` 右侧被切）。先估`need = len(t)*sz*0.52/72*PX_W/SLIDE_W_IN`，
   `need<=右侧可用宽` 就加宽框，否则等比缩字号（锁 0.55 倍兜底）。

#### ⚠️④ 装饰过滤**会直接丢内容**，规则必须极度保守

这是本轮踩得最贵的坑：激进规则**误删了约 10 块真实正文**——
p02 的两句结论、p05 的 `+One-clickSnapEcosystem`、p07 的 `MostPopular/推荐` 徽章、p08 的 `Management`。

**OCR score 完全不能用来区分**：实测装饰代码雨 score **0.895**，真实正文 score **0.933**，
装饰比正文还高。任何基于置信度的阈值判据都是错的。

只能靠**结构特征 + 页面白名单**，且必须写死边界：

```python
CODE_RAIN_PAGES = {"p01"}   # 只有这页有代码雨背景，其他页一律不启用
CODE_RAIN_MAX_Y = 320# 该页装饰区 y 上界（实测装饰块最大 y=260，正文最小 y=445）
```

- 「无空格长串乱码」这类判据**必须废弃**（`initramfs` / `DNF / RPM` 会被误杀）。
- 阈值宁高不低：宁可漏放几个装饰，**绝不能误删正文**。
- step2（抹字）与 step3（重建）**必须共用同一套规则和常量**，否则会「抹掉却没重建」造成永久内容丢失。
- 去重只认**完全相同坐标**的框。不要用「文本相同 + y 接近」——
  实测 p08 原图本身就有两个 `Management`（NotebookLM 生成的冗余内容），宽松去重会误删。

**重建完的自检三件套**：对象数 / 真文本框数 / 出血检测。
交付后仍建议人工校对英文粘连词（`WeTransform`、`Codeinto`）。

---

## 🚨 模式 G：死图 PPT 的「元素切件 → 单独文件夹 → 原位回贴」

文字可编辑只是半程。用户真正要的是**连背景里的插图/图标/卡片也能单独选中、移动、替换**。

### 三层落位结构（顺序不能换）

```
①无字无元素底图   clean_flat/pNN.png   ← 文字抹掉 + 元素区域扩散抹掉
② 元素切件        elements_new/pNN/*.png → 各自独立 PICTURE，按原坐标 1:1
③ 真文本框        重建的 textbox
```

漏掉①的「元素抹除」→ 切件与底图上的原元素**重影**。这是本模式唯一真正的难点。

### 🔴🔴 头号铁律：坐标必须实测，**禁止目测网格图**

这是本轮最贵的教训。目测100px 网格图定位 p07 三张卡片给出 `30~270 / 258~508 / 520~760`，
而描边强度峰实测是`61~460 / 473~901 / 915~1314`，**偏差 100~200px**：

- 切件宽度只有 240 → **盖不住真实卡片（宽 399）** → 必然重影
- 框与框互相重叠 → 切件叠在一起 → 更严重的错位

**目测坐标在任何情况下都不可用于切图。**

#### 实测三件套（按可靠性排序）

```python
# ① 描边强度峰 —— 卡片左右边最可靠
#    实测 p07：描边列强度 500+，而橙色正文文字只有 25~200 → 阈值 350 干净分离
m    = 橙色掩膜(HSV: H5~42, S>=55, V>=45)
cp   = 各列「连续>=25px 的竖线」累计长度
强竖线 = 聚类(cp >= 350)   # 相邻两两配对成卡片左右边
# ⚠️ 必须只配【相邻】对。两两自由组合会把三张卡并成一块1253px 的巨卡。

# ② 横描边 —— 卡片上下边
#    在【卡片 x 区间内】统计每行橙色像素，取 >= 0.52*卡宽 的行
#    ⚠️ 不能在全页找橙线：会把页面外框/装饰线当成卡片边（实测 p07 卡1 被判成 y=0~716）
rowcnt = m[:, x0:x1].sum(axis=1)
上边 = 距内容最近的、位于内容之上的横描边；下边反之

# ③ 梯度峰 —— 描边不是橙色时（如 p03 玻璃卡是浅蓝灰）
gy = |diff(GaussianBlur(gray, 1.2))|;沿 y 投影找峰
```

### 元素切分三种切法

| mode | 适用 | 做法 |
|---|---|---|
| `icon` | 发光小图标 | Alpha 解混 → 透明 PNG |
| `block` | 玻璃卡片、展台 | 矩形切，**保留原背景像素**，内部文字抹成玻璃底色 |
| `art` | 完整插画、圆环 | 矩形切，保留原背景像素 |
| 四边形 | 透视展台（p09） | `fillPoly` 出 mask，外部 alpha=0，否则矩形切会切掉斜边 |

#### Alpha 解混标准解法（不能用亮度提亮）

```python
# ⚠️ 背景色取【框内最暗的 30% 像素中位数】，不要用四边外圈
#    实测 p04 `图标_现代窗口` 外圈压在蓝色电路纹理上 → 采到 [27,56,124] 蓝紫底，
#    而图标是低饱和橙(30,90,200)，色彩距离被压扁→ Otsu 失效 → 抠出 98% 全透明。
lum = sub.reshape(-1,3).mean(axis=1)
bg  = median(sub.reshape(-1,3)[lum <= percentile(lum,30)])

dist = |sub - bg|
thr  = Otsu(dist)
alpha= clip((dist - thr*0.85) / (fmax - thr*0.85), 0, 1)
# 强 alpha 区解混前景色；弱 alpha 区保留原像素（避免除以小alpha 放大噪声）
```

#### 卡片切件必须抹掉内部文字

卡片既是插画又是容器，内部装着已成为独立文本框的文字。原样切 → 贴回后叠字→ 重影。

```python
① 收集切框内的 OCR 文字框
② merge_boxes(gap=6~8) 合并 —— OCR 常把一行拆成多块，块间有 1~3px 缝隙，
   不合并会残留 2px 旧字迹，贴回后是刺眼的横向条纹
③ 玻璃底色 = 切框内【所有非文字像素的中位数】
   ⚠️ 不能用文字框四边采样 —— 会命中笔画取到深色，p07 三张卡出现黑斑
④ 填充文字区域
```

### 底图元素残留：像素扩散（cv2.inpaint）

```python
mask = 元素框外扩 PAD=3   # 外扩确保盖住描边残留
out  = cv2.inpaint(bgr, mask, 12, cv2.INPAINT_TELEA)
# 大块区域 inpaint 会有X 形扩散伪影，但它会被切件完全覆盖，不可见
```

❌ **不能用环带中位数**：元素若有发光描边，环带正好压在描边高亮上，取到描边灰 → 底图脏灰块。
❌ **不能用纯色填充**：玻璃卡是渐变 + 电路纹理，纯色块极其扎眼。

### 斜置元素的字号陷阱

p07 橙色丝带上的 `Most Popular/推荐`，OCR 给出**正方形**框（实测 138×140），
框内其实只有一小行斜字。`by_h ≈ 96pt` 被 72pt 封顶 → 渲染出巨大字。

```python
ratio = h_px / float(w_px)
if 0.72 <= ratio <= 1.4 and by_h > 40.0 and 字符数 <= 16:
    return min(round(by_w * 2) / 2, 32.0)   # 方形大框 + 短文本 = 斜排元素
```

### 元素框不能压住正文

插画框的下边界必须**止于标题上方**。实测 p03 圆环框到 y=490，
而 `Core Carrier` 在 y=447 → 渲染出来是「标题被卡片盖住」。

### 交付物

```
切出的元素/
  README.md          元素名 + 坐标 + 切法对照表
  manifest.json
  pNN/00_卡片_xxx.png ...
```

**验证顺序固定为**：① 坐标叠加图肉眼核对 → ② 切图 → ③ 落位 → ④ 渲染。
跳过① 会把坐标错误一路带到最终成品，而成品截图上看不出「框错位」只显示「重影」。

## 材料流水线（PPT 配图 / 归档材料专用）

```bash
# PDF 逐页转 PNG（2x 缩放，投影清晰）；--only 过滤 zip 内文件名
python scripts/slice.py pdf2png --path <材料目录> --outdir ./mats --only <姓名>

# 隐私打码（按比例，不写死像素）；多块用分号隔开
python scripts/slice.py mask --input ./mats --outdir ./mats_masked \
  --ratios "0.545,0.045,1.0,0.108;0.545,0.108,1.0,0.140"

# 批量等比统一规格卡片 + manifest.json（contain，不拉伸）
python scripts/slice.py cards --input ./mats_masked --outdir ./cards --width 600 --height 840

# 按 spec.json 落位留白 / 安全区 / 九宫格（--guides 画参考线）
python scripts/slice.py spec --input ./cards --outdir ./final --spec spec.json --guides
```

⚠️ **打码原则**：手机号 / 邮箱 / 家庭住址一律遮；**姓名 + 学号保留**（要证明身份）。
⚠️ **按比例定位，不要写死像素**——不同 PDF 转图尺寸不同，写死必打歪。

## 通用铁律
- **拆图层必须写清规则**（独立图层、背景、顺序、可继续编辑），不能只说「帮我拆图层」。
- **三个易混淆边界**：裁透明空边 ≠ 去素材黑底；外侧留白 ≠ 内部内容安全区；切成九份 ≠ 拉伸后不变形。

## 处理流程
1. **先定义差异（批量前）**：同主题出可比较的「解法」差异（符号 / 材质 / 轮廓 / 装饰密度），不是换 N 种颜色。
2. **一次交代、候选独立管理**：主题 + 参考 + 方向清单 + 组件用途 + 候选数 + 项目要求一次给全；各组件编号（头像框 / 气泡 / 名牌），跑偏只重做对应项、保留已选。
3. **人工选型（放回使用场景）**：按实际显示尺寸看——能否建立身份感 / 是否留足文字空间 / 昵称徽章是否拥挤；缩到实际尺寸再评主题识别与整套协调。
4. **规格处理（配置化）**：见 `references/spec.md`（目标像素 / 裁切框 / 四边留白 / 对齐点 / 内容安全区 / 九宫格边距）。取单件 → 裁透明空边 → 等比适配 → 留白对齐；**保住轮廓，不为铺满而拉伸**。
5. **检查交付**：自检图层偏移 / 尺寸变化 / 顺序错误 / 白底残留 / 元素误删；透明边缘、长文本、深浅背景、引擎实装分别测。固定装饰保形，伸缩区域测试。

## 工具
- **统一入口**：`scripts/slice.py`，13 个子命令

| 分类 | 命令 | 说明 |
|---|---|---|
| **切图** | `trim` | 裁透明空边 |
| | `grid` | 网格切图（已知行列） |
| | **`detect`** | 连通域算法切图（大小不一/位置随机首选） |
| | **`grid-detect`** | 智能网格检测（自动推断行列） |
| | **`debg`** | 边缘种子洪水填充去背景（保元素内部同色） |
| | **`dedup`** | 感知哈希去重 |
| | `adapt` / `batch` | 等比适配 + 留白对齐 / 批量处理目录 |
| **材料** | **`pdf2png`** | PDF 逐页转 PNG |
| | **`mask`** | 隐私打码（按比例） |
| | **`cards`** | 批量统一规格卡片 + manifest |
| | `spec` | 按 spec.json 落位留白/安全区/九宫格 |
| **出图** | **`artgen`** | 调图片生成 API，出图结果可直接被 detect/grid 切 |

- **依赖**：Pillow（必需）、numpy（debg/artgen）、scipy（detect 加速）、imagehash（dedup）、pymupdf（pdf2png）
- 去背 / 语义拆层可走 AI API 或本地 `rembg`

## 选型速查
| 素材形态 | 用哪个 |
|---|---|
| API 出图后要切元素 | `artgen` → `detect` / `grid-detect` |
| 元素大小不一、位置随机 | `detect`（连通域算法切图） |
| 规则雪碧图 / 已知行列 | `grid` |
| 规则但不知行列（AI 生成图） | `grid-detect` |
| 纯色底要去透明（保内部同色） | `debg` |
| 复杂背景要抠图 | rembg / AI 抠图（`debg` 不行） |
| 切完想去重 | `dedup` |
| PDF 材料要进 PPT | `pdf2png` → `mask` → `cards` |
| 整页死图 PPT 要文字可编辑 | 模式 F：OCR → 抹字 → 重建（切图无效） |
| 统一尺寸/留白对齐 | `adapt` / `batch` / `cards` / `spec` |

## 参考
- 算法实现要点与 GitHub 出处：`references/algorithms.md`
- 规格定义（配置化）：`references/spec.md`