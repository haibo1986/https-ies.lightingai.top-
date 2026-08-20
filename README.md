# 内部 IES 快速换算工具

本项目是一个本地运行的内部工具：上传原始实测 IES 文件，按“目标光通量 ÷ 原始实测总光通量”的比例缩放 candela 光强矩阵，并输出明确标注为 `ESTIMATED` 的 IES 文件和 Markdown 说明报告。

当前版本同时提供由目标 IES 直接生成的 13 页经典版式专业估算光度报告。报告由统一的 LM-63 Type C 插值与对称性引擎驱动，包含产品与电气参数、极坐标/直角坐标配光曲线、归一化配光、真实平面与空间等照度、投影发光面亮度、照度距离、球面积分区域光通量、光度数据质量校验、完整 C-Gamma 光强表、换算依据与使用声明。未经标准算法验证的利用系数页不再输出。原始企业 PDF 只作为可选溯源附件，不再作为标准报告模板；当源 PDF 被识别为已知版式（惠谱 CPM-1800B）或用户完成人工字段标定时，可**额外**生成一份在原版式上覆盖估算数据的原版式报告，默认标准报告不受影响。

生成前必须填写发光面长宽，用于亮度曲线计算；还可补充企业 Logo、名称、网址、电话、制造商、报告编号、日期、电压、电流、功率因数、CCT、CRI、灯具外形尺寸、等照度计算条件和备注。补充字段标记为用户提供数据，光度结果始终来自目标 IES。图表采用参考报告的角度方向、坐标刻度、10级等照度图例、双单位照度距离表达，以及含 Imean 的5度区域光通量表。生成后执行 22 项校验，包括 IES 矩阵与插值采样、C0-C180 复合轴、独立球面积分、真实平面/空间等照度网格、投影亮度、5度区域积分、图表字段、功率、最大光强、光效、发光面尺寸、PDF 页数、型号、估算声明和负光强。

> **重要声明：**输出文件仅适用于前期方案模拟、内部评估和客户初步沟通，不是认证级光度测试结果，不可用于正式认证、验收、第三方检测报告或法律争议依据。

## 适用与不适用场景

适合相同灯具系列、透镜、光束角和光学结构下的功率变化；LED 数量或灯具长度变化也可估算，但可能影响近场和墙面均匀性，系统会标记为中风险。

光束角、透镜或光学结构变化会改变配光形状，不能通过统一倍率获得可信结果，系统会阻止生成并要求重新实测。本版本也不提供 DIALux/Relux/AGi32 场景模拟、AI 配光预测、数据库、账号或云端部署。

## 项目结构

```text
backend/                 FastAPI 服务和 IES 核心逻辑
  app/                   解析、缩放、风险、写入、报告及 API
  tests/                 pytest 测试与最小 IES 样本
  uploads/               运行时上传文件（不提交）
  outputs/               运行时生成文件（不提交）
frontend/                React + Vite 单页应用
```

## 后端安装与启动

需要 Python 3.10 或更高版本。在项目根目录执行：

**Windows（PowerShell）：**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**WSL / Linux（推荐，性能更好）：**

```bash
cd backend
python3 -m venv .venv
.venv/bin/activate
pip install -r requirements.txt python-docx
uvicorn app.main:app --reload
```

后端默认地址为 `http://127.0.0.1:8000`，健康检查为 `GET /api/health`。

## 前端安装与启动

需要 Node.js 20 或更高版本。另开一个终端，在项目根目录执行：

**Windows（PowerShell）：**

```powershell
cd frontend
npm install
npm run dev
```

**WSL / Linux：**

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 开发服务器会把 `/api` 请求代理到本地后端。若前后端分开部署，可通过 `VITE_API_BASE_URL` 指定 API 地址。

## 备份

项目主目录位于 WSL Linux 文件系统（`~/projects/ies`），Windows 常规备份不覆盖该位置。每次大改动后请执行：

```bash
bash tools/backup.sh      # 打包到 E:\ies-backups\（排除 venv/node_modules/.git）
git push                  # 源码推送 GitHub
```

## 使用方法

1. 选择不超过 10MB、`TILT=NONE` 的 `.ies` 文件并点击“上传并解析”。
2. 检查解析出的版本、功率、光通量、角度数量和最大光强。
3. 填写原始实测总光通量、目标型号、目标功率、目标光通量和变更类型。绝对光度文件（`lumens_per_lamp=-1`）必须人工填写原始总光通量。
4. 低风险或中风险场景可生成并下载估算 IES 与 Markdown 报告；高风险场景会被阻止。

工具使用光通量比而非功率比，因为 LED 光效、驱动效率和热状态可能随功率改变，电功率不能可靠代表光输出。即便使用实测光通量比例，缩放结果仍只是假设配光形状不变的估算。

## 测试与构建

```powershell
cd backend
pytest

cd ..\frontend
npm run build
```

测试覆盖合法和非法 IES 解析、跨行数字、矩阵完整性、光通量缩放、六种风险规则、输出声明、API 上传/生成/下载及路径安全。

## API 摘要

- `GET /api/health`：健康检查。
- `POST /api/upload`：multipart 上传字段 `file`，返回上传 ID 与解析摘要。
- `POST /api/generate`：提交上传 ID、源/目标光通量、目标型号/功率和变更类型。
- `GET /api/download/{file_name}`：下载本次运行期间生成的文件。

上传 ID 保存在后端进程内存中，服务重启后需要重新上传。程序会在上传或生成时清理超过24小时的运行文件；长期归档仍应由使用者按内部数据管理要求完成。

## 常见启动问题

- 如果 `python --version` 无法执行，请先安装 Python 3.10 或更高版本，并在安装时启用 `Add Python to PATH`。
- 如果虚拟环境提示 `Unable to create process`，通常是原 Python 安装位置已经变化。删除失效的 `backend/.venv` 后，重新执行 `python -m venv .venv` 和依赖安装命令。
- 如果 PowerShell 不允许激活脚本，可先执行 `Set-ExecutionPolicy -Scope Process Bypass`，然后重新运行 `.venv\Scripts\activate`。
- 如果5173端口被占用，Vite 会显示新的访问地址；请以终端输出为准。
- 如果前端能打开但无法上传，请确认后端8000端口正在运行，并访问 `http://127.0.0.1:8000/api/health` 检查。

## 第一版限制与后续方向

- 仅支持 LM-63-1995、LM-63-2002 和 `TILT=NONE`，不自动修复非标准文件。
- 不预测角度、透镜或光学结构变化后的配光，也不校正不同灯具长度造成的空间均匀性误差。
- 暂无产品族数据库、批量生成、IES 图形预览、误差校准、权限管理和 PDF 客户报告。
- 后续可基于更多同系列实测数据增加误差对比、产品族管理、批量输出和预览，但正式交付仍应以光度实测为准。
