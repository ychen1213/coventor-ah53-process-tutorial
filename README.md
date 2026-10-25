# AH53 凸起 Si mark：SEMulator3D 9.3 完整教程

本仓库包含此前实际 AH53 教学工艺的详细中文教程、配图，以及从零生成输入、调用原生 ModelBuilder、核查结果和导出 VDATA 的代码。

**结构极性：三条 Si mark 保留为凸起，周围 Si 被刻掉。**这是简化单方向教学版图；非理想参数是未用真实机台标定的行为模型输入。

## 从哪里开始

1. 在 GitHub 点击 **Code → Download ZIP**，解压到英文路径，例如 `D:\CoventorProjects\AH53_Process_Tutorial`。
2. 用本地浏览器打开 [tutorial.html](tutorial.html)。HTML 共 16 节，逐项解释手动画版图、层映射、材料、6/8 步工艺、构建、截面检查、VDATA 和代码原理。GitHub 文件页显示源码；下载后打开可看排版。
3. 初次先运行理想版，确认凸起方向，再运行非理想版。

## 环境

- Windows；已合法安装 **Coventor SEMulator3D 9.3**，包含 ModelBuilder、随附 Python 3.6 和示例文件。
- 非理想版的 Multi Etch 需要相应 Advanced Modeling 功能许可。
- 控制入口和 VDATA 完整性检查使用 Python 标准库。生成器所需的 gdspy 由本机 SEMulator3D Python 提供。
- 旧原生 SDK 使用随附 Python 3.6，在隔离子进程中运行；不能直接给任意新版 Python 加载其 `.pyd`。
- 脚本读取本机安装里的示例步骤模板；SDK、示例原件、材料数据库和许可证均未捆绑。

## 双击一键运行

- `run_ideal.cmd`：生成并实际仿真理想 300 nm 凸 Si。
- `run_nonideal.cmd`：生成并实际仿真非理想八步流程，通常更慢。

双击入口会调用控制程序，默认输出在仓库的 `runs/<时间戳>_ideal` 或 `runs/<时间戳>_nonideal`。窗口结束时暂停并保留退出码。默认搜索 `D:\SEMulator3D9`，也支持环境变量 `SEMULATOR_ROOT`/`MEMULATOR_ROOT` 和部分常见安装位置；其他位置请用下面的显式命令。

## PowerShell 命令

先设置本机安装路径和解压位置：

```powershell
$install = "D:\SEMulator3D9"
$tutorial = "D:\CoventorProjects\AH53_Process_Tutorial"
$py = Join-Path $install "runtime\python\v3.6\NT40_x64\python.exe"
$runner = Join-Path $tutorial "code\run_process.py"
& $py $runner --help
```

仅生成输入；没有工艺求解：

```powershell
& $py $runner --mode ideal --generate-only --output "D:\CoventorProjects\AH53_Inputs_01" --semulator-root $install --voxel-nm 20
```

从零生成并运行理想工艺：

```powershell
& $py $runner --mode ideal --run --output "D:\CoventorProjects\AH53_Ideal_Run_01" --semulator-root $install --voxel-nm 20
```

从零生成并运行非理想工艺：

```powershell
& $py $runner --mode nonideal --run --output "D:\CoventorProjects\AH53_Nonideal_Run_01" --semulator-root $install --voxel-nm 20
```

默认只模拟同一组三条，范围 X=16…32、Y=−14…14 µm；GDS 保留四组上下文。`--full-layout` 改为完整四组，代价更高。`--planes` 请求导出体素内界面平面信息，文件更大。

输出目录必须新建或为空，以免覆盖已有结果。生成后如需续建本入口项目，可用 `--run --resume --output 原目录 --semulator-root $install`，不会重新生成输入；改变网格/范围应新建项目。GUI 改参数后，也可以在 GUI Save All、Build。

从本入口已完成项目的最终去胶 wafer 另名导出，**不重做工艺**：

```powershell
& $py $runner --export-only --planes --output "D:\CoventorProjects\AH53_Ideal_Run_01" --semulator-root $install
```

另名文件和导出报告写到该项目的 `exports/`。这不是任意 `.zam` 的通用导出器；其阶段约定为 ideal 第 5 步、nonideal 第 7 步。

纯文件检查，无需 SDK 导入或工艺求解；此动作也可使用普通 Python 3.6+：

```powershell
& $py $runner --check-only --vdata "D:\CoventorProjects\AH53_Ideal_Run_01\AH53_Ideal.vdata"
```

检查 XML/元数据、压缩块及字节长度不等于标定工艺物理精度。本检查器针对本教程所用 9.3 VoxelXML 结构，不宣称适用任意版本/封装。

## 运行后查看什么

- `AH53_Ideal.zam` / `AH53_Nonideal.zam`：在 SEMulator3D 中打开。
- 同名 `.vdata`：最终去胶后体素结果。
- `build.log`：实际 ModelBuilder 日志。
- `native_verification.json`：保存 wafer 的原生量测与完整性检查。
- `run_report.json`：动作、阶段状态、命令和耗时。
- `parameters.json`：生成参数的记录。**仅编辑该 JSON 不会自动改变 GDS/vproc/zam。**

修改配方请在 Process Editor 修改真实 `.vproc` 并保存重建，或修改生成器后使用另一个新输出目录。

## 工艺摘要

理想：Si 1 µm → PR 0.5 µm → AH53_KEEP、Light、整层曝光 → Straight Si Etch 300 nm → 去胶 → VDATA。

非理想：粗糙 PR → Taper/loading 220 nm → tilted Visibility 40 nm → Basic 横向收尾 40 nm → 去胶 → VDATA。名义深度和 300 nm **不保证最终各处都刻 300 nm**。PR RMS 60 nm、seed=53 等是输入；最终 Si LER、CD、侧壁角要另测。

手动画三条可用于理解流程；如需严格对照历史 loading 数字，应使用代码生成的同一完整 GDS 上下文和相同范围。

## 已完成的验证

2026-10-25，在原电脑实际新建并构建单组 20 nm 理想模型：

- 生成输入 2.469 s、Build 35.250 s、审计 1.218 s；阶段累计 **38.937 s**。
- Si 体积 448 → 342.4 µm³，去除 105.6 µm³；最终 PR=0。
- 三条采样顶面 Z=0.5 µm；沟底样点 Z=0.2 µm；凸高 300 nm。
- 11 项原生检查通过；VDATA 921,597 B，800×1400×50，完整性通过。
- 另测仅导出 31.375 s，未重跑刻蚀，源模型哈希不变；该次导出没有开启 planes。
- 非理想本次只生成并核查输入；教程所列非理想形貌数字与图来自**此前已完成的工艺结果**。

见 [原生验证记录](evidence/ideal_20nm_native_verification.json)、[执行记录](evidence/ideal_20nm_run_report.json)、[构建日志](evidence/ideal_20nm_build.log)。记录内绝对路径是原电脑的溯源信息，对应大型模型不包含在仓库。

20 nm 体素、插值小数或平面方程不自动证明亚体素物理精度；本教程也没有完成真实机台标定或网格收敛认证。

## 仓库范围

包含：中文教程、六个 Python 源文件、两个 CMD 入口、我们生成的示意图/结果图及少量验证记录。

运行时在本机生成 GDS、vproc/vmpd/zam、保存 wafer 和 VDATA。原生模型、FDTD 工程、浏览器缓存、厂家手册/SDK/许可证不上传。教程中的官方帮助链接依赖本机安装路径，换安装目录时需相应调整。历史 FDTD 资源报告保留在原电脑。

本教程的工艺仿真与电磁求解是两个阶段。后续读取真实 VDATA 转 Lumerical，可参见独立的 [VDATA→Lumerical 转换器](https://github.com/ychen1213/coventor-vdata-to-lumerical)。
