# 果蝇连接组神经读出与二维归巢

这是一份小规模课程实验：一条外出路线、三档方向噪声、每档三个随机种子。基于 FlyWire v783 的真实中央复合体连接组，将人为编码的方向输入转成神经活动，再由外部程序做路径积分和直线返程。

**已完成代码、真实实验、两张结果图和课程报告草稿。没有实现连接组自主路径积分，也没有恢复真实果蝇的生物罗盘。**

## 先看结果

- `examples/coursework-20261103/figure1_trajectories.png`：第一枚预定种子下的外出与返程轨迹。
- `examples/coursework-20261103/figure2_errors.png`：三档噪声的归巢误差和独立方向读出检验。
- `examples/coursework-20261103/summary.csv`：汇总结果；`metrics.csv` 保留每次试验。
- `reports/数字果蝇归巢课程报告.docx`：课程报告草稿。

| 单步转向噪声标准差 | 普通路径积分误差 | CX 神经读出加路径积分误差 |
| --- | ---: | ---: |
| 0° | 0.00 ± 0.00 | 2.04 ± 1.54 |
| 5° | 2.82 ± 1.89 | 2.39 ± 1.40 |
| 15° | 8.30 ± 5.65 | 6.88 ± 5.60 |

数值为三个种子的均值 ± 样本标准差，距离使用任意单位。总外出路长为 18，成功阈值为终点距起点不超过 1。无噪声时，神经读出的随机性会增加误差；有噪声时的均值差异不足以支持“神经网络更好”的结论。5° 条件下关闭神经读出，误差为 6.57，三次都未成功。

## 在当前服务器运行

项目位于 `/home/jiutian/projects/fly-brain-navigation`。已有 `.venv-sim`、公开模型及数据，不需要重复安装或下载。

```bash
cd /home/jiutian/projects/fly-brain-navigation
.venv-sim/bin/python -m unittest discover -s tests -v
.venv-sim/bin/python scripts/run_homing.py --output outputs/my-run
.venv-sim/bin/python scripts/plot_homing.py outputs/my-run
```

输出目录必须不存在，避免覆盖结果。省略 `--output` 会自动使用时间戳。只重新出图时，第三条命令可直接指向已有结果目录，不会重新仿真。

本次原始实验位于 `outputs/homing/coursework-20261103/`。同一环境另起进程重复运行后，指标、轨迹、观测、标定数据和神经计数完全一致，证据在 `reproducibility.json`。

## 在新的 Linux 机器重建

需要 Python 3.10、Git、curl 和 C/C++ 编译器。脚本使用 Linux 的内存信息和进程资源上限；本地 Mac 上的副本主要用于查看代码、结果和报告，仿真在服务器运行。

```bash
python3.10 -m venv .venv-sim
.venv-sim/bin/python -m pip install -r requirements-sim.lock.txt
.venv-sim/bin/python scripts/setup_upstream.py
.venv-sim/bin/python scripts/download_data.py
.venv-sim/bin/python -m unittest discover -s tests -v
.venv-sim/bin/python scripts/run_homing.py --output outputs/first-run
.venv-sim/bin/python scripts/plot_homing.py outputs/first-run
```

数据脚本校验大小和上游 MD5/Git blob 哈希，支持已有文件检查和断点续传。原始数据及依赖不放入代码仓库。下载来源见 `data/sources.json`、`docs/data_sources.md`；模型版本见 `upstream.lock.json`。

## 实验怎样工作

1. 读取注释为 CX 的 2,869 个神经元，保留其内部 300,065 条连接记录，沿用作者的带符号权重与 LIF 参数。
2. 按原版行序给 47 个 EPG 神经元分配人工方向相位，用 15–150 Hz 的 Poisson 输入编码方向。相位没有解剖学含义。
3. 按结构连接强度选取 128 个非 EPG 下游神经元，以 250 ms 窗口内的放电次数作为特征。用 48 个标定样本拟合一个岭回归读出；16 个未见方向的平均误差为 4.24°。
4. 外部程序累积带噪声的转向观测，把得到的方向送入神经网络，再按神经读出的方向和精确距离累积位置。每个神经窗口从静息状态开始，因此神经网络本身不承担跨步记忆。
5. 根据估计位置和最后方向计算一次转向与返程距离；环境执行该指令。返程执行理想化，没有新传感噪声、障碍物或碰撞。

该设置检验神经读出能否参与一个可复现的导航流程。它不能证明原生的方向保持、路径积分机制或相对其他网络的优越性。完整方法与边界见报告和 `docs/experiment_plan.md`。

## 实际开销与检查

- 单进程 CPU/Cython 仿真；没有使用 4090 GPU。
- 首轮完整标定与归巢实验约 19.24 秒，主进程峰值 RSS 约 596 MiB；同环境复跑约 14.18 秒。编译、缓存和机器负载会影响耗时。
- 启动时检查至少 3 GiB 可用主存，当前试验进程限制为 2 GiB 虚拟地址空间。
- 四项单元检查验证已知位移的精确归巢、相对转向、增量噪声累积和未见方向的读出。
- 断开 CX 连接后，非输入读出神经元的放电计数为 0。5° 噪声下另做读出关闭对照。以上检查不证明该连接组优于随机连接。

## 文件

- `configs/homing.json`：唯一的课程实验配置。
- `scripts/run_homing.py`：神经标定、运动观测、归巢和统计。
- `scripts/plot_homing.py`：从 CSV/NPZ 生成两张图。
- `scripts/smoke_simulation.py`：此前的 CX/全脑短时验证和子图提取。
- `scripts/setup_upstream.py`、`scripts/download_data.py`：依赖源码和数据准备。
- `examples/coursework-20261103/`：小型结果样例，纳入版本管理。
- `docs/`：数据来源、环境验证、实验范围和结果说明。

代码版本管理应包括源文件、配置、依赖、示例结果和报告；`.gitignore` 已排除环境、原始大数据、外部仓库和临时输出。服务器项目已建立 Git 版本管理，尚未绑定远程 Git 仓库。

## 来源

FlyWire v783 数据与注释、Shiu 等的公开模型均保留版本和出处。文献条目见 `references.bib`。上游模型采用 MIT 许可；数据按各自来源许可使用。
