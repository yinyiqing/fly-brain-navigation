# 果蝇连接组的方向编码与读出及归巢验证

本项目研究：给果蝇神经网络输入一个方向后，能否根据它的放电把这个方向读出来，并用于返回起点。神经网络采用 FlyWire v783 中央复合体的连接数据，权重固定；外部岭回归模型学习放电次数与方向的对应关系，称为方向读出器。

归巢时，程序把转向观测得到的方向输入网络，再用读出的方向和每步距离累加位置。距离由路线配置提供，位置记录与返程动作由控制程序计算。直接返程后尚未到达，就在附近执行有限搜索；进入起点半径 1 的区域时停止。

## 查看论文与插图

- [最终论文](reports/果蝇连接组方向读出与归巢验证_24025110_尹一清.docx)：按方向输入、放电记录、读出训练和归巢应用解释方法，含关键公式、一张放电图和两张结果表。
- [方向放电与预测图](reports/assets/paper_direction_readout.png)：展示 128 个神经元的放电记录，以及输入方向与预测方向的比较。
- [外出、返程与搜索轨迹](reports/assets/paper_trajectory.png)：蓝色为外出，橙色为返程，紫色为搜索，场地无障碍物。
- [补充材料](docs/paper_supplement.md)：输入公式、参数、各项实验检查的问题、搜索路程比较与数据索引。
- [成果包说明](docs/final_delivery.md)、[图注说明](docs/paper_figures.md)。

## 主要结果

读出器使用 48 个样本训练。在 16 个未参与训练的方向上，平均预测误差为 4.24°，最大误差为 8.75°。测试方向位于相邻训练方向的中点，与最近训练方向相差 11.25°。

以下读出对照使用三条路线、种子 601–605，感知误差标准差为 5°，搜索路程上限为 72。路程均值包含未到达的试验；打乱训练方向一行列出五组结果的范围。

| 读出条件 | 测试方向平均误差 | 归巢到达次数 | 平均返程路程 |
| --- | ---: | ---: | ---: |
| 正常读出 | 4.24° | 15/15 | 15.06 |
| 打乱训练方向（五组） | 65.29°–111.94° | 3/15–13/15 | 38.05–71.14 |
| 关闭读出 | 90.00° | 6/15 | 68.99 |

正常读出的平均返程路程较五组打乱方向的对照至少缩短 60.4%。[完整逐组结果](examples/validation-20261104/ablation_by_variant.csv)与[方向误差](examples/validation-20261104/decoder_controls.csv)保留在仓库中。

换用种子 701–710 后，每档为三条路线与十个种子的 30 个组合，路线之间共用种子。搜索上限仍为 72。

| 外出转向感知误差标准差 | 无返程转向误差 | 返程转向误差标准差 2° |
| --- | ---: | ---: |
| 0° | 30/30 | 30/30 |
| 5° | 30/30 | 30/30 |
| 15° | 21/30 | 20/30 |

几何方法使用相同的运动观测、搜索和到达规则，在 2° 返程执行误差下三档的到达次数与神经方法相同。方向预测用于这一导航流程的效果、增加搜索路程的收益及行走代价，见[结果说明](docs/validation_results.md)和[逐次记录](examples/validation-20261104/robustness_metrics.csv)。

## 核对已有结果

下面的命令用保存的神经输出重放导航，核对结果表，不重新运行神经仿真。需要 Python 3.10，无需 GPU 或连接组原始数据。

```bash
python3.10 -m venv .venv-check
.venv-check/bin/python -m pip install numpy==1.24.4 pandas==1.5.3
.venv-check/bin/python -m unittest discover -s tests -v
.venv-check/bin/python scripts/run_search_homing.py --replay examples/search-20261104
.venv-check/bin/python scripts/run_validation_suite.py --verify examples/validation-20261104
```

单元检查覆盖方向读出、位置计算、到达判定、搜索上限和配对误差。验证脚本核对 10 张结果表；它会检查相关仿真源码的哈希，复查历史结果时应使用对应提交。GitHub Actions 也执行这些轻量检查。

## 完整运行实验

使用 Linux、Python 3.10、Git、curl 和 C/C++ 编译器。神经仿真在 CPU 上运行，脚本启动时检查可用内存。

```bash
python3.10 -m venv .venv-sim
.venv-sim/bin/python -m pip install -r requirements-sim.lock.txt
.venv-sim/bin/python scripts/setup_upstream.py
.venv-sim/bin/python scripts/download_data.py
.venv-sim/bin/python scripts/run_validation_suite.py --config configs/homing_validation.json --output outputs/first-run
.venv-sim/bin/python scripts/run_validation_suite.py --verify outputs/first-run
.venv-sim/bin/python scripts/plot_validation.py outputs/first-run
```

输出目录必须是新目录。模型版本固定在 `upstream.lock.json`，下载来源与校验信息见 `data/sources.json` 和 [数据说明](docs/data_sources.md)。原始公开数据、外部模型副本和虚拟环境由脚本准备，不放入成果包。

## 代码与数据

- `scripts/run_homing.py`：神经刺激、读出训练、方向平均与位置计算。
- `scripts/run_search_homing.py`：三路线归巢、到达判定与有限搜索。
- `scripts/run_validation_suite.py`：读出对照、多路线验证、执行误差及搜索上限比较。
- `configs/`：各项实验的固定参数；`tests/`：轻量单元检查。
- `examples/validation-20261104/`：正文使用的读出对照和多路线结果。
- `examples/search-20261104/`：搜索对照、保存的神经响应及训练数据。
- 其他 `examples/` 目录：补充材料中的观察窗口与方向平均比较。

## 更新论文与导出成果包

安装 `requirements-report.txt` 后，在项目根目录运行：

```bash
python scripts/build_final_report.py --reference /path/to/参考报告.docx
```

论文由保存的结果与图片生成，保留原始参考文件的排版。图一与轨迹图的源文件位于 `reports/assets/`，可用 `scripts/plot_direction_readout.py` 和 `scripts/plot_paper_trajectory.py` 重新绘制，需 matplotlib、NumPy、pandas 和中文字体。修改论文后应检查分页和图表。

在有 Git 历史的项目仓库中，提交完成的改动后导出：

```bash
python scripts/package_delivery.py --output ../最终成果_新版
```

导出目录必须不存在。脚本只读取指定提交的文件，默认 `HEAD`，输出一份论文、静态插图、补充材料和代码数据压缩包。代码包排除所有 Word 报告及旧演示动画；实验记录与配置保留，版本和文件校验信息写入补充材料目录。

GitHub 仓库：[yinyiqing/fly-brain-navigation](https://github.com/yinyiqing/fly-brain-navigation)。按 `add：具体改动`、`fix：具体改动` 或 `update：具体改动` 提交并推送已验证的完整改动，约定见 `AGENTS.md`。

FlyWire 数据、细胞注释和公开模型的出处见 `references.bib`。Shiu 等的上游模型采用 MIT 许可，数据按各自来源许可使用。
