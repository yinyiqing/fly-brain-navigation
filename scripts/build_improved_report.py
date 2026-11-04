#!/usr/bin/env python3
"""Build the improvement report from both fixed seed groups, preserving the original report."""
import argparse
import csv
import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data", type=Path, default=Path("examples/motion-average-20261104"))
    parser.add_argument("--confirmation", type=Path, default=Path("examples/motion-confirm-20261104"))
    parser.add_argument("--output", type=Path, default=Path("reports/数字果蝇归巢改进实验报告.docx"))
    args = parser.parse_args()
    root = args.root
    data = args.data if args.data.is_absolute() else root / args.data
    confirmation = args.confirmation if args.confirmation.is_absolute() else root / args.confirmation
    destination = args.output if args.output.is_absolute() else root / args.output
    if destination.resolve() in {(root / "reports/数字果蝇归巢课程报告.docx").resolve(),
                                 (root / "reports/数字果蝇归巢课程报告_排版版.docx").resolve()}:
        raise ValueError("Preserve both original reports; use a new output path")
    manifest = json.loads((data / "manifest.json").read_text())
    cal = manifest["calibration"]
    with (data / "summary.csv").open() as stream:
        summary = {(r["method"], int(r["noise_deg"])): r for r in csv.DictReader(stream)}
    with (confirmation / "summary.csv").open() as stream:
        confirmed = {(r["method"], int(r["noise_deg"])): r for r in csv.DictReader(stream)}
    def successes(rows, method):
        return "、".join(f"{rows[(method, n)]['successes']}/{rows[(method, n)]['trials']}" for n in [0, 5, 15])

    def means(rows, method):
        return "、".join(f"{float(rows[(method, n)]['mean_error']):.2f}" for n in [0, 5, 15])
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(1.85), Cm(1.85)
    sec.left_margin, sec.right_margin = Cm(2), Cm(2)
    sec.footer_distance = Cm(.8)
    for style_name in ["Normal", "Title", "Heading 1", "Heading 2", "Caption"]:
        style = doc.styles[style_name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for key in list(fonts.attrib):
            if "theme" in key.lower():
                del fonts.attrib[key]
        fonts.set(qn("w:eastAsia"), "Songti SC")
        for border in list(style.element.xpath("./w:pPr/w:pBdr")):
            border.getparent().remove(border)
    normal = doc.styles["Normal"]
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.widow_control = True
    title = doc.styles["Title"]
    title.font.size, title.font.bold = Pt(17), True
    title.paragraph_format.space_after = Pt(10)
    for name, size in [("Heading 1", 12), ("Heading 2", 11)]:
        style = doc.styles[name]
        style.font.size, style.font.bold = Pt(size), True
        style.paragraph_format.space_before = Pt(7)
        style.paragraph_format.space_after = Pt(4)
    doc.styles["Caption"].font.size = Pt(9)
    doc.styles["Caption"].font.bold = False
    doc.styles["Caption"].paragraph_format.space_after = Pt(6)

    def para(text, indent=True, size=None):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if indent:
            p.paragraph_format.first_line_indent = Pt(21)
        if size:
            for run in p.runs:
                run.font.size = Pt(size)
        return p

    def equation(text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        math = OxmlElement("m:oMath")
        run = OxmlElement("m:r")
        t = OxmlElement("m:t")
        t.text = text
        run.append(t)
        math.append(run)
        p._p.append(math)
        p.paragraph_format.space_after = Pt(5)

    def picture(name, caption):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run()
        shape = run.add_picture(str(data / name), width=Cm(17))
        shape._inline.docPr.set("descr", caption)
        p = doc.add_paragraph(caption, style="Caption")
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    p = doc.add_paragraph("基于果蝇连接组神经读出的二维归巢实验", style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_heading("摘要", level=2)
    para("本文构建一个小规模归巢实验，考察方向观测噪声及果蝇神经读出对返程误差的影响。"
         "使用 FlyWire v783 中 2,869 个中央复合体神经元及其内部连接，人工编码方向输入，"
         "从下游放电次数读出方向，再由外部程序完成路径积分。"
         f"在 16 个未参与标定的方向上，读出平均误差为 {cal['heldout_mae_deg']:.2f}°。"
         "在神经方向读数上使用因果的运动补偿圆周平均。原有三个种子和三个新种子的无噪声条件均达到 3/3 归巢，"
         "但有噪声时没有稳定增益。结果表明这一外部处理能改善本路线的无噪声返程，不证明连接组具备自主路径积分能力。", False)
    para("关键词  果蝇连接组  Brian2  方向读出  路径积分  归巢", False, 9.5)

    doc.add_heading("1 引言", level=1)
    para("路径积分通过累积自身运动估计相对起点的位置，不依赖持续观测起点。方向测量偏差会逐步影响位置估计，"
         "因此归巢误差可以直观反映运动信息处理的局限。FlyWire 提供成年果蝇全脑连接组及神经元注释[1–2]，"
         "Shiu 等公开的脉冲神经模型提供了从连接数据到放电活动的计算基础[3]。"
         "本实验只研究一个问题：在一个固定二维任务中，真实连接组的神经读出能否作为方向接口，"
         "以及方向噪声对最终归巢误差有什么影响。")

    doc.add_heading("2 研究方法", level=1)
    para("数据采用 FAFB v783 连接组[4]和 v2.1.0 注释。选取 cell_class 为 CX 的 2,869 个神经元，"
         "保留两端均在该集合内的 300,065 条连接记录，重新映射索引后使用作者的带符号连接权重。"
         "这些记录是模型连接，不是单个化学突触。子图未包含到其他脑区的连接，不能视为全脑动力学的等价替代。")
    para("神经仿真使用 Brian2 2.5.1[5]和上游 LIF 方程，步长 0.1 ms、读出窗口 250 ms。"
         "选取注释为 EPG 的 47 个输入神经元，按上游行序均匀分配人工方向相位。"
         "输入率随方向与相位之差的余弦变化，范围为 15–150 Hz；刺激权重沿用上游的 250 倍基础权重。"
         "这些相位仅用于工程编码，不对应经验证的生物罗盘位置。")
    para("按照 EPG 到非 EPG 神经元连接的绝对权重和，预先选出最强的 128 个下游神经元。"
         "以其放电次数作为特征，使用 16 个均匀方向、每方向 3 次刺激共 48 个样本标定。"
         "特征按训练集均值和标准差标准化，标准差下限为 1；用正则系数 10 的岭回归预测方向的余弦和正弦。"
         "测试方向相对训练网格偏移 11.25°，使用独立刺激种子。未见方向平均误差不超过 30° 才进入归巢实验，"
         "该阈值在运行前固定。")
    para("外部程序先累积带噪声的转向增量，再把方向送入神经模型。神经读出的方向与精确位移长度共同用于位置累积。"
         "在改进方法中，外部程序把历次神经方向读数按已观测转向转到当前朝向后取圆周平均；每步只使用当前和过去读数。"
         "每个神经窗口仍从静息状态重新开始，跨步记忆、方向平均和位置积分都由外部程序完成。"
         "返程时依据估计位置和最后读出方向，计算一次相对转向及直线行走距离。")

    doc.add_page_break()
    doc.add_heading("3 实验设计", level=1)
    para("起点为原点，初始方向为 0°。外出路线依次采用 0°、60°、145°、50°，对应路长为 6、5、4、3；"
         "每段分成五步，共 20 个运动观测，总路长 18。距离采用任意单位。"
         "每步真实转向增量加入独立高斯噪声，标准差设为 0°、5°、15°；噪声在方向累积后形成漂移。"
         "距离观测精确，返程执行理想化，不添加新的感知或执行误差。")
    equation("θ_obs(t) = wrap(θ_obs(t−1) + Δθ(t) + ε(t))")
    para("比较普通几何路径积分与 CX 神经读出加路径积分，使用相同观测序列。"
         "在发现无噪声返程对最后一次神经读数敏感后，比较未经处理的方向与运动补偿圆周平均方向。"
         "原实验种子为 7、21、42；另用预先固定的新种子 401、402、403 做复核。"
         "主指标为返程终点到起点的欧氏距离，距离不超过 1 计为成功。5° 条件下另把所有读出特征置零，"
         "重放同一外出观测并分别记录原读出及平均读出对照。")

    doc.add_heading("4 结果与分析", level=1)
    picture("figure1_trajectories.png", "图 1 预定种子 7 下的外出与返程轨迹。灰色虚线为外出路线，蓝色为几何积分，橙色为原始 CX 读出，绿色为运动补偿平均读出，紫色为平均读出关闭对照。圆圈半径为成功阈值 1。")
    before, after = summary[("cx_readout", 0)], summary[("cx_motion_average", 0)]
    para(f"表 1 显示，无噪声时原始 CX 读出的平均终点误差为 {float(before['mean_error']):.2f}，成功 {before['successes']}/{before['trials']}；"
         f"加入运动补偿平均后，误差降为 {float(after['mean_error']):.2f}，成功 {after['successes']}/{after['trials']}。"
         "同一处理没有改善全部有噪声条件，因此不能据此声称神经读出增强了抗噪能力。", False)
    caption = doc.add_paragraph("表 1 原种子组归巢误差 均值 ± 样本标准差 每档 n = 3", style="Caption")
    caption.paragraph_format.keep_with_next = True
    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = [Cm(2.1), Cm(4.9), Cm(5.1), Cm(4.9)]
    headers = ["转向噪声", "几何积分", "CX 原始读出", "CX 运动补偿平均"]
    for cell, width, label in zip(table.rows[0].cells, widths, headers):
        cell.width = width
        cell.text = label
    for sigma in [0, 5, 15]:
        a = summary[("geometric", sigma)]
        b = summary[("cx_readout", sigma)]
        c = summary[("cx_motion_average", sigma)]
        values = [f"{sigma}°", f"{float(a['mean_error']):.2f} ± {float(a['std_error']):.2f}",
                  f"{float(b['mean_error']):.2f} ± {float(b['std_error']):.2f}",
                  f"{float(c['mean_error']):.2f} ± {float(c['std_error']):.2f}"]
        for cell, width, value in zip(table.add_row().cells, widths, values):
            cell.width = width
            cell.text = value
    borders = OxmlElement("w:tblBorders")
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        element = OxmlElement("w:" + edge)
        for key, value in [("val", "single"), ("sz", "4"), ("color", "D9D9D9")]:
            element.set(qn("w:" + key), value)
        borders.append(element)
    table._tbl.tblPr.append(borders)
    for index, row in enumerate(table.rows):
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        if index == 0:
            row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            margins = OxmlElement("w:tcMar")
            for edge in ["top", "left", "bottom", "right"]:
                node = OxmlElement("w:" + edge)
                node.set(qn("w:w"), "75")
                node.set(qn("w:type"), "dxa")
                margins.append(node)
            cell._tc.get_or_add_tcPr().append(margins)
            if index == 0:
                fill = OxmlElement("w:shd")
                fill.set(qn("w:fill"), "E9ECEF")
                cell._tc.get_or_add_tcPr().append(fill)
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_after = Pt(1)
                p.paragraph_format.line_spacing = 1.05
                for run in p.runs:
                    run.font.size = Pt(9)
                    run.font.bold = index == 0
    para(f"按 0°、5°、15° 顺序，原种子组的几何、CX 原始读出、补偿平均成功次数分别为 {successes(summary, 'geometric')}、"
         f"{successes(summary, 'cx_readout')}、{successes(summary, 'cx_motion_average')}。新种子组的原读出平均误差为 {means(confirmed, 'cx_readout')}，"
         f"补偿平均为 {means(confirmed, 'cx_motion_average')}；补偿平均的成功次数为 {successes(confirmed, 'cx_motion_average')}。"
         "原种子组 5° 关闭读出后，原方法三次均为 6.57；补偿平均为 8.02 ± 2.91，差异来自转向观测。"
         "关闭对照与完整方法共享观测，按配对结果解释。")

    doc.add_page_break()
    picture("figure2_errors.png", "图 2 左图为归巢误差，误差棒表示三个种子的样本标准差，淡色点表示逐次结果。右图为 16 个未见人工输入方向与神经读出方向的对应关系，虚线表示理想读出。")
    para(f"方向接口的独立检验平均误差为 {cal['heldout_mae_deg']:.2f}°，中位数为 {cal['heldout_median_deg']:.2f}°，"
         f"最大误差为 {cal['heldout_max_deg']:.2f}°，通过预设的 30° 门槛。"
         "额外将所有 CX 突触权重置零后，非输入读出神经元的放电计数为 0，而包含输入神经元的总放电数为 948。"
         "因此接口确实读取了经连接传递的活动；这仍不能证明该连接结构比随机网络更适合方向编码。")

    doc.add_heading("5 讨论", level=1)
    para("运动补偿平均减少了最后一次方向读数对返程转角的瞬时影响，两个互不重合的三种子样本都在无噪声条件下达到 3/3。"
         "但 250 ms 的神经窗口和人工方向输入并未改变；平均仅在外部程序中进行。"
         "把窗口延长到 1,000 ms 的单项对照没有稳定增加成功次数，也没有继续保留为默认方法。")
    para("该处理依赖按已观测转向对方向序列作正确补偿。转向噪声仍会累积成漂移，实验中两档有噪声的归巢成功次数没有稳定改善。"
         "一条路线、每组三个种子只能作描述性比较，不能支持普遍性能结论。"
         "人工 EPG 相位、外部方向与位置累积、每窗重置及理想返程均简化了问题。"
         "因此实验没有验证真实果蝇的内生罗盘、长期方向记忆或自主路径积分，也没有进行环路特异性比较。")
    para(f"完整标定和主归巢实验采用单进程 CPU 仿真，实测耗时 {manifest['wall_seconds']:.2f} 秒，"
         f"主进程峰值常驻内存约 {manifest['max_rss_kib']/1024:.0f} MiB。"
         "主试验另起进程复跑后，轨迹、观测、指标、标定数据和神经计数一致。"
         "代码保留固定配置、逐次结果、对照及复现入口。本实验只支持该路线和当前输入设定下的结果。")

    doc.add_heading("参考文献", level=1)
    references = [
        "[1] Dorkenwald S, et al. Neuronal wiring diagram of an adult brain. Nature, 2024. DOI: 10.1038/s41586-024-07558-y.",
        "[2] Schlegel P, et al. Whole-brain annotation and multi-connectome cell typing of Drosophila. Nature, 2024. DOI: 10.1038/s41586-024-07686-5.",
        "[3] Shiu P K, et al. A Drosophila computational brain model reveals sensorimotor processing. Nature, 2024. DOI: 10.1038/s41586-024-07763-9. Code: github.com/philshiu/Drosophila_brain_model.",
        "[4] FlyWire Consortium. FlyWire Whole-brain Connectome Connectivity Data, version 783.0. Zenodo, 2024. DOI: 10.5281/zenodo.10676866.",
        "[5] Stimberg M, Brette R, Goodman D F M. Brian 2, an intuitive and efficient neural simulator. eLife, 2019, 8: e47314. DOI: 10.7554/eLife.47314.",
    ]
    for text in references:
        p = para(text, False, 8.5)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.0
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    doc.core_properties.title = "基于果蝇连接组神经读出的二维归巢实验"
    doc.core_properties.subject = "果蝇连接组课程实验"
    doc.core_properties.author = ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destination)
    print(destination)


if __name__ == "__main__":
    main()
