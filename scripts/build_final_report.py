#!/usr/bin/env python3
"""Build the final coursework paper from saved results and the supplied DOCX style.

The reference is copied at the ZIP-part level. Unrelated package parts and all
previous reports remain untouched. No neural experiment is run here.
"""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import zipfile
from lxml import etree as E
from docx import Document
from docx.shared import Cm
from format_report import NS, q, set_prop, text_of, xml_bytes

ROOT = Path(__file__).resolve().parents[1]
TITLE = "果蝇连接组神经读出与有限搜索归巢实验"
FINAL_NAME = "数字果蝇归巢研究_24025110_尹一清.docx"


def read_rows(name):
    with (ROOT / name).open() as stream:
        return list(csv.DictReader(stream))


def one(rows, **keys):
    def matches(actual, expected):
        if isinstance(expected, (int, float)):
            return float(actual) == expected
        return str(actual) == str(expected)
    selected = [r for r in rows if all(matches(r[k], v) for k, v in keys.items())]
    if len(selected) != 1:
        raise ValueError(f"Expected one result for {keys}; got {len(selected)}")
    return selected[0]


def count(row):
    return f"{row['successes']}/{row['trials']}"


def build(reference, output):
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    with zipfile.ZipFile(reference) as archive:
        original = {n: archive.read(n) for n in archive.namelist()}
    parts = original.copy()
    document = E.fromstring(original["word/document.xml"])
    body = document.find(q("w:body"))
    patterns = body.findall(q("w:p"))
    table_pattern = deepcopy(body.find(q("w:tbl")))
    section = deepcopy(body.find(q("w:sectPr")))
    styles = E.fromstring(parts["word/styles.xml"])
    for sid, name, index, outline in [("FinalTitle", "Title", 0, None),
                                       ("FinalHeading1", "heading 1", 2, 0),
                                       ("FinalHeading2", "heading 2", 7, 1)]:
        style = E.SubElement(styles, q("w:style"), {q("w:type"): "paragraph", q("w:styleId"): sid})
        set_prop(style, "w:name", val=name)
        set_prop(style, "w:basedOn", val="1")
        set_prop(style, "w:qFormat")
        pp = deepcopy(patterns[index].find(q("w:pPr")))
        if outline is not None:
            set_prop(pp, "w:outlineLvl", val=outline)
        style.append(pp)
        style.append(deepcopy(patterns[index].find("w:r/w:rPr", NS)))
    for child in list(body):
        body.remove(child)

    def paragraph(text, index=9, *, keep=False, page=False, indent=True):
        p = E.Element(q("w:p"))
        pp = deepcopy(patterns[index].find(q("w:pPr")))
        for n in list(pp):
            if n.tag in [q("w:numPr"), q("w:pStyle")] or (not indent and n.tag == q("w:ind")):
                pp.remove(n)
        sid = {0: "FinalTitle", 2: "FinalHeading1", 7: "FinalHeading2"}.get(index)
        if sid:
            pp.insert(0, E.Element(q("w:pStyle"), {q("w:val"): sid}))
        set_prop(pp, "w:snapToGrid", val=0)
        set_prop(pp, "w:widowControl", val=1)
        set_prop(pp, "w:keepNext", val=int(keep))
        if page:
            set_prop(pp, "w:pageBreakBefore", val=1)
        p.append(pp)
        run = E.SubElement(p, q("w:r"))
        rp = deepcopy(patterns[index].find("w:r/w:rPr", NS))
        if rp is not None:
            set_prop(rp, "w:color", val="000000")
            run.append(rp)
        t = E.SubElement(run, q("w:t"))
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
        body.append(p)
        return p

    def heading(text, *, page=False):
        return paragraph(text, 2, keep=True, page=page)

    def table(caption, rows, widths):
        paragraph(caption, 76, keep=True, indent=False)
        t = deepcopy(table_pattern)
        old_rows = t.findall(q("w:tr"))
        for r in old_rows:
            t.remove(r)
        grid = t.find(q("w:tblGrid"))
        for c in list(grid):
            grid.remove(c)
        for width in widths:
            E.SubElement(grid, q("w:gridCol"), {q("w:w"): str(width)})
        set_prop(t.find(q("w:tblPr")), "w:tblW", w=sum(widths), type="dxa")
        set_prop(t.find(q("w:tblPr")), "w:jc", val="center")
        for i, values in enumerate(rows):
            r = deepcopy(old_rows[0 if i == 0 else -1 if i == len(rows) - 1 else 1])
            rp = r.find(q("w:trPr"))
            if rp is None:
                rp = E.SubElement(r, q("w:trPr"))
            for h in rp.findall(q("w:trHeight")):
                rp.remove(h)
            set_prop(rp, "w:cantSplit", val=1)
            if i == 0:
                set_prop(rp, "w:tblHeader", val=1)
            for c, value, width in zip(r.findall(q("w:tc")), values, widths):
                cp = c.find(q("w:tcPr"))
                set_prop(cp, "w:tcW", w=width, type="dxa")
                set_prop(cp, "w:vAlign", val="center")
                borders = cp.find(q("w:tcBorders"))
                if i > 1 and borders is not None:
                    set_prop(borders, "w:top", val="nil")
                p0 = deepcopy(c.find(q("w:p")))
                run_format = deepcopy(p0.find("w:r/w:rPr", NS))
                pp = p0.find(q("w:pPr"))
                set_prop(pp, "w:snapToGrid", val=0)
                set_prop(pp, "w:spacing", before=60, after=60, line=240, lineRule="auto")
                set_prop(pp, "w:jc", val="center")
                set_prop(pp, "w:keepNext", val=int(i < len(rows) - 1))
                for item in list(p0):
                    if item.tag != q("w:pPr"):
                        p0.remove(item)
                run = E.SubElement(p0, q("w:r"))
                if run_format is not None:
                    run.append(run_format)
                for line_index, line in enumerate(str(value).splitlines()):
                    if line_index:
                        E.SubElement(run, q("w:br"))
                    E.SubElement(run, q("w:t")).text = line
                for child in list(c):
                    if child.tag != q("w:tcPr"):
                        c.remove(child)
                c.append(p0)
            t.append(r)
        body.append(t)

    latest = read_rows("examples/validation-20261104/robustness_summary.csv")
    controls = read_rows("examples/validation-20261104/ablation_by_variant.csv")
    decoders = read_rows("examples/validation-20261104/decoder_controls.csv")
    old = read_rows("examples/search-20261104/summary.csv")
    def trial(noise, execution=0, budget=72, method="cx"):
        return one(latest, method=method, noise_deg=noise, execution_noise_deg=execution, budget=budget)
    paragraph(TITLE, 0, keep=True)
    paragraph(text_of(patterns[1]), 1)
    paragraph("摘要", 7, keep=True)
    paragraph("本文将果蝇中央复合体的神经方向读出接入二维归巢任务，研究观测误差下的返程效果与搜索代价。使用 FlyWire v783 连接组与人工方向输入，由外部程序完成运动补偿平均、路径积分和有限搜索。三条路线、十个新种子中，无噪声和 5° 观测噪声下均到达 30/30；加入 2° 返程转向误差后仍为 30/30，15° 高噪声下为 20/30。标签打乱降低了解码与归巢效果。神经读出参与了该流程，但改进主要来自外部处理与搜索。", indent=False)
    paragraph("关键词  果蝇连接组；Brian2；方向读出；路径积分；有限搜索", indent=False)
    heading("一、引言")
    paragraph("归巢需要依据自身运动估计起点，方向偏差会随路径积分累积。FlyWire 连接图与细胞注释提供了神经网络数据[1–2]，Shiu 等的公开模型提供了从连接权重到放电活动的实现[3]。本实验检验神经方向读出能否接入归巢流程，以及估计起点不准时，有限搜索能补救多少失败；通过成对对照区分神经读出与外部控制器的作用。")
    heading("二、研究方法")
    paragraph("采用 FAFB v783 数据[4]与 v2.1.0 注释，提取 2,869 个 CX 神经元及内部 300,065 条连接记录，省略其他脑区连接。记录不等于单个化学突触。沿用公开模型的带符号权重与 LIF 方程，在 Brian2 2.5.1[5]中运行，步长 0.1 ms，观察窗口 250 ms。")
    paragraph("用余弦调制的 15–150 Hz Poisson 输入刺激 47 个 EPG 神经元；相位按原版行序分配，不代表真实生物罗盘。按输出连接绝对权重选取 128 个非输入神经元，以放电次数为特征。16 个方向各重复三次，形成 48 个训练样本；标准化后以正则系数 10 的岭回归预测方向的正弦和余弦。偏移 11.25° 的 16 个未见方向用于测试。")
    paragraph("外部程序累加带噪声转向并送入网络，将历次神经方向按已观测转向旋转到当前朝向，作因果圆周平均，再结合准确距离累积位置。每个神经窗口从静息状态重置，跨步记忆均在外部。根据估计位置与朝向先转向、直行，未到达则作间隔 1.5、额外路程不超过 72 的扩展方形搜索。首次进入起点半径 1 的区域即停止；二值到达信号不提供目标坐标或方位。")
    heading("三、实验设计")
    paragraph("使用原折线路线、往复折线和渐变转向三条路线，总长均为 18。外出每步转向增量叠加独立零均值高斯噪声，标准差为 0°、5°、15°；距离观测准确。几何基线与神经方法共用运动观测、搜索参数和首次到达判定。路程均值包含失败，避免将较早停止误判为高效率。")
    paragraph("首轮用种子 601–605，每档噪声有 15 个路线与种子组合。方向对照复用放电计数，用 801–805 五个固定种子置换训练标签，同方向的三次样本共享标签，特征与样本数不变；另设正常、关闭读出对照。五组置换共享数据，不增加独立样本数。")
    paragraph("新种子 701–710 形成 90 个神经导航试验，每条返程转向加入 0° 或 2° 标准差的执行误差，比较预算 0、18、36、72。同路线、种子的各条件共用按动作序号对齐的执行误差。路线共享种子，每档的 30 个组合不等于 30 个独立种子。演示预定为原路线、种子 701、2° 执行误差。")
    heading("四、结果与分析")
    paragraph("早期单路线实验中，原神经读出在无噪声条件的平均终点误差为 2.04，成功 1/3；运动补偿平均将误差降至 0.19，成功 3/3，另三个新种子也达到 3/3。有观测噪声时未见稳定收益。将窗口从 250 ms 延长至 1,000 ms 同样没有稳定提高成功率，因此保留短窗口。")
    low_direct = one(old, method="cx_direct", noise_deg=5)
    low_search = one(old, method="cx_search", noise_deg=5)
    paragraph(f"首轮三路线验证中，5° 噪声下直接返程只到达 {count(low_direct)}，加入搜索后为 {count(low_search)}；平均返程路程由 {float(low_direct['mean_return_distance']):.2f} 增至 {float(low_search['mean_return_distance']):.2f}。新种子结果见表一：低噪声效果保持，高噪声仍会耗尽预算。")
    rows = [["观测噪声", "理想返程到达", "2° 误差到达", "平均路程\n理想 / 有误差"]]
    for noise in [0, 5, 15]:
        a,b=trial(noise),trial(noise,2)
        rows.append([f"{noise}°",count(a),count(b),f"{float(a['mean_return_distance']):.2f} / {float(b['mean_return_distance']):.2f}"])
    table("表一 新种子的神经归巢结果 搜索预算为 72",rows,[1300,2050,2050,2906])
    paragraph("高噪声下，执行误差使一例成功变为失败，无反向变化。低噪声路程略缩短是有限样本的轨迹扰动，不能说明噪声有益。几何方法理想返程的三档结果为 30/30、29/30、21/30，有执行误差时为 30/30、30/30、20/30，与神经方法接近。")
    # Generate only the new inline image element; the retained DOCX remains the package base.
    image_doc = Document()
    shape = image_doc.add_paragraph().add_run().add_picture(str(ROOT / "reports/assets/paper_trajectory.png"), width=Cm(14.65))
    drawing = deepcopy(image_doc.paragraphs[0]._p.find('.//' + q('w:drawing')))
    drawing.find('.//wp:docPr',NS).set('descr','种子701的成功与失败轨迹：蓝虚线出发、橙实线返程、紫点划线搜索；A为家，B开始返程，C开始搜索，箭头指示移动方向，无障碍物')
    drawing.find('.//a:blip',NS).set(q('r:embed'),'rIdFinalTrajectory')
    p = paragraph('',82,keep=True)
    p.find(q('w:r')).append(drawing)
    paragraph("图一 固定种子 701 的归巢轨迹。A 为家，B 开始返程，C 开始搜索；蓝虚线为出发，橙实线为返程，紫点划线为搜索，箭头示方向。无障碍物，两图均含 2° 转向执行误差。",84,indent=False)
    paragraph("方向标签对照见表二。五组置换均明显增大未见方向误差，低噪声归巢成功次数下降且路程增加。置换 804 仍到达 13/15，表明后续搜索能补救部分读出错误。这检验的是正确方向对应关系，不是连接组相对随机网络的优势。")
    rows=[["读出条件","方向误差","到达次数","平均返程路程"]]
    for label,method,variant in [("正常读出","cx_normal",0)]+[(f"标签置换 {s}","cx_shuffled_labels",s) for s in range(801,806)]+[("关闭读出","readout_off",0)]:
        a=one(controls,method=method,variant=variant,noise_deg=5,budget=72)
        d=one(decoders,method=method,variant=variant)
        rows.append([label,f"{float(d['heldout_mae_deg']):.2f}°",count(a),f"{float(a['mean_return_distance']):.2f}"])
    table("表二 旧种子的方向对照 观测噪声 5° 搜索预算 72",rows,[2500,1700,1600,2506])
    paragraph(f"表三显示增加预算的收益与代价。旧样本预算 36 曾覆盖低噪声全部成功，新样本只有 27/30 或 28/30，故保留主预算 72。高噪声且有执行误差时，预算从 36 增至 72，成功由 15 增至 20，平均路程由 {float(trial(15,2,36)['mean_return_distance']):.2f} 增至 {float(trial(15,2,72)['mean_return_distance']):.2f}。")
    rows=[["搜索预算","5° 到达\n理想 / 有误差","15° 到达\n理想 / 有误差","15° 有误差\n平均路程"]]
    for budget in [0,18,36,72]:
        rows.append([budget,f"{count(trial(5,0,budget))} / {count(trial(5,2,budget))}",f"{count(trial(15,0,budget))} / {count(trial(15,2,budget))}",f"{float(trial(15,2,budget)['mean_return_distance']):.2f}"])
    table("表三 新种子的搜索预算与代价",rows,[1300,2500,2500,2006])
    heading("五、讨论")
    paragraph("主要改进来自减少读出波动和增加搜索。正确的方向接口有用，但结果不支持神经方法优于几何积分。高噪声会使估计起点偏离搜索覆盖区，执行误差进一步扰动轨迹；增加预算需要多走路，也无法保证到达。")
    paragraph("本实验使用人工输入、窗口重置、准确距离和理想到达检测，没有障碍物。记忆与积分在外部，不能证明果蝇脑自主完成路径积分；固定路线与共享种子也限制了推广。后续可优先检验距离误差和新路线。")
    paragraph("本轮 CPU 实验约 106.77 秒，单个神经进程峰值 RSS 约 611.72 MiB。项目通过 20 项单元检查与 10 张结果表重放；重放使用保存的神经输出，不等于重跑神经仿真。代码、配置、数据来源及各阶段结果见 github.com/yinyiqing/fly-brain-navigation。")
    paragraph("参考文献",143,keep=True)
    for text in [
        "[1] Dorkenwald S, et al. Neuronal wiring diagram of an adult brain. Nature, 2024. DOI: 10.1038/s41586-024-07558-y.",
        "[2] Schlegel P, et al. Whole-brain annotation and multi-connectome cell typing of Drosophila. Nature, 2024. DOI: 10.1038/s41586-024-07686-5.",
        "[3] Shiu P K, et al. A Drosophila computational brain model reveals sensorimotor processing. Nature, 2024. DOI: 10.1038/s41586-024-07763-9.",
        "[4] FlyWire Consortium. FlyWire Whole-brain Connectome Connectivity Data, v783.0. Zenodo, 2024. DOI: 10.5281/zenodo.10676866.",
        "[5] Stimberg M, Brette R, Goodman D F M. Brian 2, an intuitive and efficient neural simulator. eLife, 2019, 8: e47314. DOI: 10.7554/eLife.47314.",
    ]:
        paragraph(text,144)
    body.append(section)
    rels=E.fromstring(parts['word/_rels/document.xml.rels'])
    for r in list(rels):
        if r.get('Type','').endswith('/image'):rels.remove(r)
    for name in list(parts):
        if name.startswith('word/media/') and not name.endswith('/'):del parts[name]
    E.SubElement(rels,q('pr:Relationship'),Id='rIdFinalTrajectory',Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',Target='media/final_trajectory.png')
    parts['word/media/final_trajectory.png']=(ROOT/'reports/assets/paper_trajectory.png').read_bytes()
    parts['word/document.xml']=xml_bytes(document)
    parts['word/styles.xml']=xml_bytes(styles)
    parts['word/_rels/document.xml.rels']=xml_bytes(rels)
    core=E.fromstring(parts['docProps/core.xml'])
    for name,value in [('dc:title',TITLE),('dc:creator','尹一清')]:
        node=core.find(q(name))
        if node is None:node=E.SubElement(core,q(name))
        node.text=value
    parts['docProps/core.xml']=xml_bytes(core)
    editable={'word/document.xml','word/styles.xml','word/_rels/document.xml.rels','docProps/core.xml'}
    assert all(parts.get(n)==v for n,v in original.items() if n not in editable and not n.startswith('word/media/'))
    assert hashlib.sha256(reference.read_bytes()).hexdigest()==reference_hash
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)
    print(json.dumps({'output':str(output),'reference_sha256':reference_hash,'preserve_only_parts_unchanged':True},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'reports'/FINAL_NAME)
    args=parser.parse_args()
    if args.output.resolve()==args.reference.resolve():raise ValueError('Preserve the reference')
    build(args.reference,args.output)
