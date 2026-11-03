# Brian2 基础运行验证

2026-11-03，在远程项目内完成两次真实连接组短时仿真，均通过。上游代码保持原样；测试入口为 `scripts/smoke_simulation.py`。

## 环境

Python 3.10.20、Brian2 2.5.1、NumPy 1.24.4、pandas 1.5.3、PyArrow 11.0.0、Cython 0.29.33。核心依赖在 `requirements-sim.txt`，完整安装锁定在 `requirements-sim.lock.txt`，解释器来源记录在 `data/metadata/simulation_environment.json`。

`.venv-sim` 隔离了 Python 包，使用现有 vggt 环境中的 Python 3.10 解释器建立，没有向 vggt 或 Conda base 安装包。在本机继续使用时，该解释器路径需保留。在其他机器上可用任意兼容的 Python 3.10 按锁定文件重建。

两次均使用 CPU/Cython 后端、单进程、单次试验、100 ms 生物模拟时间、0.1 ms 默认步长和随机种子 20261103。向一个已核对的 EPG 神经元施加原版默认的 150 Hz 人工 Poisson 刺激，其余动力学参数保持原版默认。此刺激仅用于检查运行和输出。

## 实测记录

| 范围 | 神经元 | 连接记录 | 总墙钟时间 | 主进程峰值 RSS | 放电事件 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 中央复合体诱导子图 | 2,869 | 300,065 | 9.78 s | 255.2 MiB | 41 |
| 原版 v783 全脑模型 | 138,639 | 15,091,983 | 4.21 s | 2359.2 MiB | 41 |

两次均有 13 个神经元放电，其中被刺激神经元产生 13 次放电，其余神经元共 28 次。输出已检查时间范围、神经元 ID、试验编号、非空和有限值。

子网络先运行，包含首次编译；全脑随后运行，可利用已有编译缓存。总时间包括输入准备、网络构建、必要的编译、仿真及结果写出。以上数据用于基础运行验证，不能据此推断长时任务、更多刺激或多次并行试验的速度。RSS 仅统计主 Python 进程，不是包含编译子进程在内的整机增量内存。

子网络由注释中 `cell_class == CX` 的 2,869 个神经元构成，保留两端均在该集合内的连接，并重新映射索引；映射已逐批核对。所有连接到集合外神经元的边均未纳入，因此它不是完整全脑动力学的等价替代。

## 重跑

在 `/home/jiutian/projects/fly-brain-navigation` 执行：

```bash
.venv-sim/bin/python scripts/smoke_simulation.py --scope cx --duration-ms 100
.venv-sim/bin/python scripts/smoke_simulation.py --scope full --duration-ms 100
```

脚本分别为 CX 和全脑进程设置 2 GiB、4 GiB 虚拟地址空间上限，并在启动前要求额外 1 GiB 可用主存。这里只限制当前测试进程；不修改系统或其他作业的资源配置。

新结果保存在带时间戳的 `outputs/smoke/` 目录，含 `probe.parquet` 和 `summary.json`；CX 目录另含该次生成的神经元和连接子表。本次终端日志保存在 `logs/smoke-cx-20261103.log`、`logs/smoke-full-20261103.log`，可版本管理的结果摘要在 `data/metadata/runtime_validation.json`。

重建隔离环境：

```bash
python3.10 -m venv .venv-sim
.venv-sim/bin/python -m pip install -r requirements-sim.lock.txt
```

## 当前边界与下一步

已验证原版软件、真实 v783 输入、刺激与放电输出兼容，且当前服务器可完成受限的全脑短时仿真。归巢控制、运动输入接口和多智能体通信尚未实现；本结果不构成方向记忆、路径积分或归巢功能验证。

下一步按 `docs/experiment_plan.md` 建立二维单体任务及几何基线，同时验证神经输入/读出接口。本次按课程作业规模完成单体小实验及报告，范围以 `docs/experiment_plan.md` 为准。
