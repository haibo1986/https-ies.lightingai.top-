# PRD：内部 IES 快速换算工具

## 1. 文档信息

- 产品名称：内部 IES 快速换算工具
- 使用对象：LED 洗墙灯企业内部销售、产品经理、研发、光学工程人员
- 第一版定位：基于原始实测 IES 文件，按目标光通量比例缩放 candela 光强矩阵，生成“估算版 IES 文件”
- 重要声明：本工具不是认证级光度测试软件，不能替代光度计实测，也不能用于正式认证、验收、第三方检测报告

---

## 2. 项目背景

我们是 LED 户外洗墙灯企业，经常需要向客户提供 IES 文件，用于客户在 DIALux、Relux、AGi32 等软件中模拟灯具照明效果。

当前业务中经常遇到类似需求：

- 原始灯具：24颗 3030 LED，24W，20°，已有实测 IES 文件
- 客户新需求 1：24颗 3030 LED，36W，20°
- 客户新需求 2：36颗 3030 LED，36W，20°

如果每一次功率、LED 数量或长度变化都重新使用光度计测试，会产生较高的人力、时间和测试成本。

因此希望开发一个内部工具，用已有实测 IES 文件作为母版，在一定边界条件内快速生成估算版 IES 文件，用于前期方案模拟、销售沟通和内部评估。

---

## 3. 产品目标

### 3.1 核心目标

开发一个简单、稳定、可本地运行的 IES 快速换算工具，实现：

1. 上传原始实测 IES 文件；
2. 自动解析 IES 文件；
3. 显示原始 IES 关键参数；
4. 输入目标灯具参数；
5. 根据目标光通量 / 原始光通量的比例缩放 candela 数据；
6. 生成新的估算版 IES 文件；
7. 同时生成 Markdown 说明报告；
8. 明确标注输出文件为 ESTIMATED，避免被误认为正式实测 IES。

### 3.2 非目标

第一版不要做以下功能：

1. 不做复杂 AI 预测；
2. 不做 DIALux / Relux / AGi32 的替代品；
3. 不做完整照明场景模拟；
4. 不做 20° 自动变 30° 的配光预测；
5. 不做不同透镜、不同遮光结构、不同光学结构的真实配光预测；
6. 不做认证级、验收级、第三方检测报告级输出；
7. 不做数据库、账号系统、权限系统；
8. 不做云端部署，第一版先支持本地运行。

---

## 4. 使用场景

### 4.1 适用场景

| 场景 | 是否支持 | 风险等级 | 说明 |
|---|---|---|---|
| 同灯具、同透镜、同角度，仅功率变化 | 支持 | 低 | 适合按光通量比例换算 |
| 同光学结构、同角度，LED 数量变化 | 支持，但标注估算 | 中 | 可能影响近场洗墙均匀性 |
| 同光学结构、同角度，灯具长度变化 | 支持，但标注估算 | 中 | 可能影响墙面均匀性 |
| 光束角变化，例如 20° 改 30° | 不建议生成 | 高 | 配光形状改变，不能简单缩放 |
| 透镜变化 | 不建议生成 | 高 | 透镜会改变配光形状 |
| 光学结构变化 | 不允许生成 | 高 | 需要重新实测 |

### 4.2 典型业务流程

```text
上传原始实测 IES
↓
解析原始参数
↓
输入目标型号、目标功率、目标光通量、变更类型
↓
系统判断风险等级
↓
低/中风险：生成估算版 IES + 报告
高风险：阻止生成，并提示需要重新实测
```

---

## 5. 核心计算原则

### 5.1 核心公式

第一版只做光通量比例缩放：

```text
scale_factor = target_luminous_flux_lm / source_luminous_flux_lm

new_candela_value = old_candela_value × scale_factor
```

### 5.2 重要原则

1. 默认不能使用功率比例缩放；
2. 必须使用光通量比例缩放；
3. 原始光通量和目标光通量必须大于 0；
4. 如果原始 IES 中 lumens_per_lamp 为 -1 或无法判断真实总光通量，需要用户手动输入原始实测总光通量；
5. 如果用户未输入目标光通量，禁止生成；
6. 输出文件必须包含 ESTIMATED 标识和免责声明。

---

## 6. 用户角色

### 6.1 销售人员

目标：

- 快速给客户生成前期模拟用 IES；
- 不需要理解 IES 文件结构；
- 只需要上传文件、填写目标参数、下载结果。

### 6.2 产品经理 / 研发人员

目标：

- 快速评估不同功率版本的方案；
- 管理不同型号估算文件；
- 判断是否需要安排正式光度计测试。

### 6.3 光学工程师

目标：

- 检查估算逻辑是否合理；
- 根据风险等级决定是否允许销售使用；
- 后续可以扩展产品族数据库和误差校准。

---

## 7. 功能需求

## 7.1 文件上传功能

### 功能描述

用户可以上传 `.ies` 文件。

### 要求

1. 仅允许上传 `.ies` 后缀文件；
2. 文件大小第一版限制为 10MB 以内；
3. 上传后自动解析；
4. 解析失败时返回清晰错误；
5. 上传文件保存到 `backend/uploads/`；
6. 系统生成唯一 uploaded_file_id，用于后续生成操作。

### 错误提示示例

- 文件格式不是 .ies；
- 暂不支持 TILT=INCLUDE；
- 暂不支持 TILT=FILE；
- IES 数字字段数量不完整；
- 垂直角数量不匹配；
- 水平角数量不匹配；
- candela 数据数量不匹配。

---

## 7.2 IES 解析功能

### 支持范围

第一版至少支持：

- IESNA:LM-63-1995
- IESNA:LM-63-2002
- TILT=NONE

### 暂不支持

- TILT=INCLUDE
- TILT=FILE
- 复杂非标准 IES
- 多灯泡复杂结构
- 非法格式自动修复

### 需要解析字段

解析结果至少包括：

```text
ies_version
header_lines
keywords
tilt_type
number_of_lamps
lumens_per_lamp
candela_multiplier
num_vertical_angles
num_horizontal_angles
photometric_type
units_type
width
length
height
ballast_factor
ballast_lamp_photometric_factor
input_watts
vertical_angles
horizontal_angles
candela_values
max_candela
original_file_name
```

### 解析要求

1. IES 文件中的数字可能跨多行；
2. candela_values 应为二维矩阵；
3. candela_values 数量必须等于：

```text
num_horizontal_angles × num_vertical_angles
```

4. 需要保留原始 header 信息；
5. 解析错误不能导致后端崩溃。

---

## 7.3 原始 IES 信息展示功能

上传成功后，前端展示：

```text
原始文件名
IES 版本
TILT 类型
原始功率 W
lumens_per_lamp
candela_multiplier
垂直角数量
水平角数量
最大光强 cd
是否可能为绝对光度文件
是否支持自动换算
```

如果 lumens_per_lamp = -1，需要提示：

```text
该文件可能为绝对光度文件，请手动输入原始实测总光通量。
```

---

## 7.4 目标参数输入功能

用户需要输入：

```text
原始实测总光通量 lm
目标型号
目标功率 W
目标光通量 lm
变更类型
```

变更类型选项：

```text
power_only：仅功率变化
led_count_change：LED 数量变化
length_change：灯具长度变化
beam_angle_change：光束角变化
lens_change：透镜变化
optical_structure_change：光学结构变化
```

### 表单校验

1. 原始实测总光通量必须大于 0；
2. 目标光通量必须大于 0；
3. 目标功率必须大于 0；
4. 目标型号不能为空；
5. 变更类型不能为空。

---

## 7.5 风险判断功能

系统根据 change_type 自动判断是否允许生成。

### 风险规则

#### power_only

```text
allow_generate = true
risk_level = low
message = 适合同系列、同光学结构、同角度，仅功率变化的估算换算。
```

#### led_count_change

```text
allow_generate = true
risk_level = medium
message = LED 数量变化可能影响近场洗墙均匀性，生成文件仅适合初步模拟。
```

#### length_change

```text
allow_generate = true
risk_level = medium
message = 灯具长度变化可能影响墙面均匀性，生成文件仅适合初步模拟。
```

#### beam_angle_change

```text
allow_generate = false
risk_level = high
message = 光束角变化会改变配光形状，不建议通过简单缩放生成 IES，请重新实测。
```

#### lens_change

```text
allow_generate = false
risk_level = high
message = 透镜变化会改变配光形状，需要重新实测。
```

#### optical_structure_change

```text
allow_generate = false
risk_level = high
message = 光学结构变化风险高，需要重新实测。
```

---

## 7.6 IES 缩放功能

### 输入

```text
parsed_ies_data
source_luminous_flux_lm
target_luminous_flux_lm
target_model
target_power_w
change_type
```

### 输出

```text
scaled_ies_data
scale_factor
risk_result
```

### 处理逻辑

1. 计算：

```text
scale_factor = target_luminous_flux_lm / source_luminous_flux_lm
```

2. 遍历 candela_values：

```text
new_candela_value = old_candela_value × scale_factor
```

3. 更新：

```text
input_watts = target_power_w
max_candela = old_max_candela × scale_factor
target_model = 用户输入目标型号
estimated = true
```

4. 保留：

```text
vertical_angles
horizontal_angles
photometric_type
units_type
width
length
height
```

5. 小数位建议：

```text
candela_values 保留 3 位
scale_factor 保留 4 位
```

---

## 7.7 IES 文件写入功能

### 输出文件名规则

```text
目标型号_ESTIMATED.ies
```

如果目标型号中存在非法文件名字符，需要自动清理。

### 文件内容要求

1. 保留原始 IES 版本；
2. 保留原始 header；
3. 增加估算说明；
4. TILT=NONE；
5. 写入更新后的数字字段；
6. 写入原始 vertical angles；
7. 写入原始 horizontal angles；
8. 写入缩放后的 candela values；
9. 文件应尽量能被常见 IES Viewer 打开。

### 必须增加的备注

```text
[MORE] Generated by IES Scaling Tool.
[MORE] This file is estimated from measured IES data by luminous-flux scaling.
[MORE] For preliminary lighting simulation only.
[MORE] Not a certified photometric test report.
[MORE] Scale factor: {scale_factor}
[MORE] Source luminous flux: {source_luminous_flux_lm} lm
[MORE] Target luminous flux: {target_luminous_flux_lm} lm
[MORE] Target power: {target_power_w} W
```

---

## 7.8 Markdown 报告生成功能

输出文件：

```text
目标型号_ESTIMATED_report.md
```

报告内容：

```markdown
# IES 估算文件生成报告

## 1. 原始文件信息

- 原始文件名：
- IES 版本：
- TILT 类型：
- 原始功率：
- 原始光通量：
- 最大光强：
- 垂直角数量：
- 水平角数量：

## 2. 目标参数

- 目标型号：
- 目标功率：
- 目标光通量：
- 变更类型：

## 3. 换算方法

- 缩放公式：
- 缩放比例：
- candela 数据处理方式：

## 4. 风险等级

- 风险等级：
- 风险说明：

## 5. 使用声明

本文件由原始实测 IES 文件按目标光通量比例换算生成，仅适用于前期方案模拟、内部评估和客户初步沟通，不应作为正式光度测试报告、认证文件、验收依据或法律争议依据。如项目进入投标、验收、认证或正式交付阶段，应重新进行光度计实测。
```

---

## 8. 页面需求

## 8.1 页面结构

第一版只需要一个主页面：

```text
页面标题：内部 IES 快速换算工具

区域 1：上传原始 IES
区域 2：原始 IES 信息
区域 3：目标参数输入
区域 4：风险提示与生成结果
```

---

## 8.2 上传区域

组件名建议：

```text
UploadForm.jsx
```

功能：

1. 选择 IES 文件；
2. 点击上传；
3. 显示上传状态；
4. 上传成功后显示解析结果；
5. 上传失败后显示错误原因。

---

## 8.3 原始信息展示区域

组件名建议：

```text
IesInfoPanel.jsx
```

显示字段：

```text
文件名
IES 版本
TILT 类型
原始功率
lumens_per_lamp
candela_multiplier
最大光强
垂直角数量
水平角数量
是否支持自动换算
```

---

## 8.4 目标参数输入区域

组件名建议：

```text
TargetForm.jsx
```

字段：

```text
原始实测总光通量 lm
目标型号
目标功率 W
目标光通量 lm
变更类型
```

按钮：

```text
生成估算 IES 文件
```

---

## 8.5 结果区域

组件名建议：

```text
ResultPanel.jsx
```

显示：

```text
风险等级
风险提示
缩放比例
下载 IES 文件
下载 Markdown 报告
```

如果 allow_generate = false，显示：

```text
该变更会改变配光形状，不建议通过简单光通量缩放生成 IES，请重新实测。
```

并且不生成下载文件。

---

## 9. 推荐技术方案

### 9.1 技术栈

```text
前端：React + Vite
后端：Python + FastAPI
核心计算：Python
文件存储：本地 uploads/ 和 outputs/
测试：pytest
```

### 9.2 项目结构

```text
ies-scaling-tool/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ ies_parser.py
│  │  ├─ ies_scaler.py
│  │  ├─ ies_writer.py
│  │  ├─ risk_rules.py
│  │  └─ report_generator.py
│  ├─ tests/
│  │  ├─ test_parser.py
│  │  ├─ test_scaler.py
│  │  ├─ test_risk_rules.py
│  │  └─ sample_files/
│  ├─ uploads/
│  ├─ outputs/
│  └─ requirements.txt
│
├─ frontend/
│  ├─ src/
│  │  ├─ App.jsx
│  │  ├─ api.js
│  │  └─ components/
│  │     ├─ UploadForm.jsx
│  │     ├─ IesInfoPanel.jsx
│  │     ├─ TargetForm.jsx
│  │     └─ ResultPanel.jsx
│  └─ package.json
│
└─ README.md
```

---

## 10. 后端接口需求

## 10.1 健康检查

```http
GET /api/health
```

返回：

```json
{
  "status": "ok"
}
```

---

## 10.2 上传并解析 IES

```http
POST /api/upload
```

请求：

```text
multipart/form-data
file: .ies
```

成功返回：

```json
{
  "uploaded_file_id": "string",
  "file_name": "string",
  "parsed_info": {
    "ies_version": "string",
    "tilt_type": "NONE",
    "input_watts": 24,
    "lumens_per_lamp": 2400,
    "candela_multiplier": 1,
    "num_vertical_angles": 19,
    "num_horizontal_angles": 37,
    "max_candela": 12345.6
  }
}
```

失败返回：

```json
{
  "error": "错误说明"
}
```

---

## 10.3 生成估算版 IES

```http
POST /api/generate
```

请求 JSON：

```json
{
  "uploaded_file_id": "string",
  "source_luminous_flux_lm": 2400,
  "target_luminous_flux_lm": 3300,
  "target_model": "WWL-3030-36W-20D",
  "target_power_w": 36,
  "change_type": "power_only"
}
```

成功返回：

```json
{
  "allow_generate": true,
  "risk_level": "low",
  "risk_message": "适合同系列、同光学结构、同角度，仅功率变化的估算换算。",
  "scale_factor": 1.375,
  "ies_file": "WWL-3030-36W-20D_ESTIMATED.ies",
  "report_file": "WWL-3030-36W-20D_ESTIMATED_report.md",
  "ies_download_url": "/api/download/WWL-3030-36W-20D_ESTIMATED.ies",
  "report_download_url": "/api/download/WWL-3030-36W-20D_ESTIMATED_report.md"
}
```

高风险返回：

```json
{
  "allow_generate": false,
  "risk_level": "high",
  "risk_message": "光束角变化会改变配光形状，不建议通过简单缩放生成 IES，请重新实测。"
}
```

---

## 10.4 下载文件

```http
GET /api/download/{file_name}
```

功能：

下载 outputs 文件夹中的生成文件。

要求：

1. 防止路径穿越；
2. 只允许下载 outputs 目录内文件；
3. 文件不存在时返回 404。

---

## 11. 后端模块设计

## 11.1 ies_parser.py

建议实现：

```python
class IESParser:
    def parse(file_path: str) -> dict:
        pass
```

职责：

1. 读取 IES 文件；
2. 识别版本；
3. 读取 header；
4. 识别 TILT；
5. 解析数字字段；
6. 解析 vertical_angles；
7. 解析 horizontal_angles；
8. 解析 candela_values；
9. 校验数据完整性；
10. 返回结构化 dict。

---

## 11.2 ies_scaler.py

建议实现：

```python
class IESScaler:
    def scale(parsed_data: dict, source_luminous_flux_lm: float, target_luminous_flux_lm: float, target_model: str, target_power_w: float, change_type: str) -> dict:
        pass
```

职责：

1. 校验输入；
2. 计算 scale_factor；
3. 缩放 candela_values；
4. 更新 input_watts；
5. 更新 max_candela；
6. 写入 target_model；
7. 返回 scaled_data。

---

## 11.3 risk_rules.py

建议实现：

```python
def evaluate_risk(change_type: str) -> dict:
    pass
```

返回：

```python
{
    "allow_generate": True,
    "risk_level": "low",
    "risk_message": "..."
}
```

---

## 11.4 ies_writer.py

建议实现：

```python
class IESWriter:
    def write(scaled_data: dict, output_path: str) -> str:
        pass
```

职责：

1. 生成 IES 文本；
2. 保留必要 header；
3. 增加 ESTIMATED 说明；
4. 写入 TILT=NONE；
5. 写入数字字段；
6. 写入角度数组；
7. 写入 candela 数据矩阵；
8. 保存文件。

---

## 11.5 report_generator.py

建议实现：

```python
class ReportGenerator:
    def generate(parsed_data: dict, scaled_data: dict, risk_result: dict, output_path: str) -> str:
        pass
```

职责：

1. 生成 Markdown 报告；
2. 写入原始文件信息；
3. 写入目标参数；
4. 写入缩放公式；
5. 写入风险等级；
6. 写入免责声明。

---

## 12. 前端设计要求

### 12.1 风格

1. 简洁；
2. 清楚；
3. 面向非专业人员；
4. 不需要复杂动画；
5. 优先保证稳定可用。

### 12.2 页面文案

页面顶部说明：

```text
本工具用于将原始实测 IES 文件按目标光通量比例换算为估算版 IES 文件。输出文件仅适用于前期方案模拟、内部评估和客户初步沟通，不能作为正式测试报告、认证文件或验收依据。
```

按钮文案：

```text
上传 IES 文件
生成估算 IES 文件
下载 IES 文件
下载说明报告
```

---

## 13. 测试需求

请使用 pytest 至少完成以下测试：

1. 可以正常解析一个 TILT=NONE 的 IES 文件；
2. vertical_angles 数量正确；
3. horizontal_angles 数量正确；
4. candela_values 数量等于 num_horizontal_angles × num_vertical_angles；
5. scale_factor 计算正确；
6. candela_values 缩放正确；
7. source_luminous_flux_lm <= 0 时抛出错误；
8. target_luminous_flux_lm <= 0 时抛出错误；
9. risk_rules 正确允许 power_only；
10. risk_rules 正确允许 led_count_change，但风险为 medium；
11. risk_rules 正确阻止 beam_angle_change；
12. risk_rules 正确阻止 lens_change；
13. risk_rules 正确阻止 optical_structure_change；
14. 生成 IES 文件包含 ESTIMATED；
15. 生成 IES 文件包含免责声明；
16. 生成 Markdown 报告包含使用声明。

如果没有真实 IES 样本，请先创建一个最小可用 sample IES 文件用于单元测试。

---

## 14. README 要求

README 必须包含：

1. 项目介绍；
2. 适用场景；
3. 不适用场景；
4. 重要免责声明；
5. 后端安装和启动方法；
6. 前端安装和启动方法；
7. 如何上传 IES；
8. 如何生成估算版 IES；
9. 为什么使用光通量比例，而不是功率比例；
10. 为什么角度变化、透镜变化、光学结构变化不能自动生成；
11. 如何运行测试；
12. 第一版限制；
13. 后续升级方向。

---

## 15. 启动方式要求

请确保最终可以通过以下方式启动：

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 测试

```bash
cd backend
pytest
```

---

## 16. 验收标准

开发完成后，需要满足：

1. 可以上传 `.ies` 文件；
2. 可以解析并展示 IES 基础信息；
3. 可以填写目标参数；
4. 可以根据光通量比例生成新的 candela 数据；
5. 可以输出 ESTIMATED `.ies` 文件；
6. 可以输出 Markdown 报告；
7. 高风险变更类型不允许生成；
8. 所有错误有清晰提示；
9. 后端不崩溃；
10. 前端可以正常操作；
11. README 写清楚启动方式；
12. pytest 测试通过。

---

## 17. 后续升级方向

第一版完成后，后续可以逐步升级：

1. 批量生成多个功率版本；
2. 建立产品族实测数据库；
3. 增加误差校准功能；
4. 增加 IES Viewer 预览；
5. 增加墙面照度热力图快速模拟；
6. 增加客户 PDF 报告；
7. 增加产品型号管理；
8. 增加销售使用权限；
9. 增加正式实测 IES 与估算 IES 对比功能。

---

## 18. 给 Codex 的执行要求

请你按照本 PRD 完成 MVP 开发，不要过度设计。

开发顺序：

1. 先完成 backend 的 IES 解析、缩放、风险判断、写入、报告生成；
2. 写 pytest 测试；
3. 完成 FastAPI 接口；
4. 完成 React 前端页面；
5. 完成 README；
6. 最后自测并告诉我启动方法和测试结果。

请在开发完成后输出：

1. 已创建和修改的文件列表；
2. 后端启动命令；
3. 前端启动命令；
4. 测试命令；
5. 已实现功能；
6. 当前限制；
7. 后续建议。
