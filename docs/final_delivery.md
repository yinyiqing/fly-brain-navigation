# 数字果蝇归巢实验成果包

先双击根目录的 `00_打开看效果.html`，浏览器会显示归巢动画、最新结果、图表和论文入口。无需启动服务或连接服务器。移动或发送成果时保留整个目录，页面中的图片与文件使用相对路径。

## 文件放在哪里

| 文件夹 | 内容 |
| --- | --- |
| `01_论文` | 最终学术小论文，沿用指定参考报告的宋体、字号、页边距和图表样式 |
| `02_演示` | 真实轨迹生成的 GIF 和终帧；包含成功与失败 |
| `03_结果图表` | 三张实验图、结果说明、汇总及逐次 CSV 数据 |
| `04_完整项目` | 对应 Git 版本的全部已跟踪文件，包括代码、配置、依赖、各阶段结果、数据来源与文献 |
| `版本与文件校验.json` | 导出源码版本及各文件 SHA-256，便于核对副本 |

以 `01_论文` 中的版本为最终论文。完整项目的 `reports/` 也保留了早期报告，供查看改进过程。源码快照不含 `.git` 历史；完整提交记录保留在 [GitHub](https://github.com/yinyiqing/fly-brain-navigation)。

## 效果怎么理解

三条路线、十个新种子，在无噪声和 5° 观测噪声下均到达 30/30；再加入 2° 返程转向误差仍为 30/30。15° 高噪声下为 21/30，加入执行误差后为 20/30。搜索预算为 72，成功区域半径为 1。路线共享种子，样本量按路线与种子组合报告。

神经网络负责人工方向输入的放电响应和方向读出；记忆、位置积分、运动补偿平均与有限搜索在外部程序中完成。当前结果不支持脑内自主路径积分或优于几何基线的结论。高噪声失败、延长窗口无稳定收益等结果均保留。

## 只核对已有结果

在 `04_完整项目` 内运行以下命令。推荐 Python 3.10；不需要连接组原始大数据、Brian2 或 GPU。新建一个虚拟环境后执行：

```bash
python3.10 -m venv .venv-check
.venv-check/bin/python -m pip install numpy==1.24.4 pandas==1.5.3
.venv-check/bin/python -m unittest discover -s tests -v
.venv-check/bin/python scripts/run_search_homing.py --replay examples/search-20261104
.venv-check/bin/python scripts/run_validation_suite.py --verify examples/validation-20261104
```

这会运行 20 项单元检查，并用已保存的神经输出重放控制器，核对旧导航结果和最新 10 张数据表；不重新运行神经仿真。

## 完整重新仿真

使用 Linux、Python 3.10、Git、curl 和 C/C++ 编译器，按完整项目 `README.md` 的“在新的 Linux 机器重建”操作。依赖固定在 `requirements-sim.lock.txt`；源码底座固定在 `upstream.lock.json`；数据下载及校验见 `scripts/download_data.py`。

原始公开数据、外部模型副本和虚拟环境可由脚本准备，未放入成果包。已有服务器环境可直接运行 README 中的验证命令。当前实验使用 CPU，无需占用 4090 GPU。

## 修改论文或重新导出

在有 Git 历史的项目仓库中，先提交完成的改动，再导出新目录：

```bash
python scripts/package_delivery.py --output ../最终成果_新版
```

导出脚本只使用所选 Git 版本的已跟踪文件，默认 `HEAD`；不会导出未提交改动，也不会覆盖已存在的目录。仅导出不需要第三方 Python 库。

最终论文的生成命令为：

```bash
python scripts/build_final_report.py --reference /path/to/多元时序预测实验报告_24025110_尹一清.docx
```

生成论文需要 `requirements-report.txt`，以及用户提供的原始排版参考；参考文件未复制进成果包。论文插图已随代码保存；需要重画时，在有 matplotlib、pandas 的环境运行 `scripts/plot_paper_trajectory.py`。修改后应重新检查页数和分页。

提交课程前，仍需通过课程交流确认选题未与同学重复，并核对老师指定公共底座与目前采用的 Shiu 公开模型是否一致。这两项尚无确认材料。
