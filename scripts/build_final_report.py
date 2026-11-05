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
TITLE = "果蝇连接组的方向编码与读出及归巢验证"
FINAL_NAME = "果蝇连接组方向读出与归巢验证_24025110_尹一清.docx"


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
    normal_decoder = one(decoders, method="cx_normal", variant=0)
    shuffled_errors = [float(row["heldout_mae_deg"]) for row in decoders
                       if row["method"] == "cx_shuffled_labels"]
    normal_mae = float(normal_decoder["heldout_mae_deg"])
    shuffled_range = f"{min(shuffled_errors):.2f}°–{max(shuffled_errors):.2f}°"
    paragraph(TITLE, 0, keep=True)
    paragraph(text_of(patterns[1]), 1)
    paragraph("摘要", 7, keep=True)
    paragraph(f"本文检验人工方向信息经过果蝇中央复合体连接组后，能否从下游放电读出，并以归巢作为应用验证。基于 FlyWire v783 与 Brian2 模拟固定网络，仅训练外部岭回归读出器。48 个样本训练后，16 个未见方向的平均角误差为 {normal_mae:.2f}°；五组标签置换后为 {shuffled_range}。位置积分与搜索由外部程序完成。结果支持方向信息可被解码，不表明果蝇网络学会归巢。", indent=False)
    paragraph("关键词  果蝇连接组；方向编码；神经读出；岭回归；归巢验证", indent=False)
    heading("一、引言")
    paragraph("FlyWire 提供果蝇连接图与细胞注释[1–2]，Shiu 等的公开模型实现了从连接权重到放电活动的模拟[3]。本文用已知方向训练外部读出器，在未见方向上检验下游放电的方向信息，再接入归巢程序。研究重点是方向对应关系的学习与检验；回家成功率还受外部控制规则影响，不能单独代表神经网络的能力。")
    heading("二、研究方法")
    paragraph("采用 FAFB v783 数据[4]与 v2.1.0 注释，保留 2,869 个中央复合体（CX）神经元及内部 300,065 条连接记录，省略其他脑区连接。记录不等于单个化学突触。沿用公开模型的带符号权重与 LIF 方程，在 Brian2 2.5.1[5]中运行，步长 0.1 ms、窗口 250 ms，连接及权重固定。")
    paragraph("人工编码采用 15–150 Hz 余弦调制 Poisson 输入，刺激 47 个 EPG 神经元；相位按原版行序分配，不代表生物罗盘。按 EPG 输出连接绝对权重选取 128 个非输入神经元，以放电次数为特征。待识别方向已包含在输入中，网络不额外获得真实朝向或家的位置。")
    paragraph("学习发生在外部读出器。16 个已知方向各重复三次，得到 48 组放电特征与标签；标准化后，用正则系数 10 的岭回归预测输入方向的正弦和余弦，再恢复角度。只拟合外部回归参数，不训练果蝇网络或导航策略。每个神经窗口恢复静息状态，网络不保留跨步记忆。")
    paragraph("归巢时，程序累加带噪声转向，将估计朝向编码输入网络。历次读出按观测转向旋转到当前朝向后作圆周平均，再结合准确距离累积位置，计算返程方向与距离。未到达时执行间隔 1.5、额外路程不超过 72 的方形搜索。首次进入起点半径 1 的区域即停止；二值到达信号不提供方位。记忆、积分和搜索均在外部。")
    heading("三、实验设计")
    paragraph("方向测试将训练角度偏移 11.25°，得到 16 个未见方向，并更换放电随机种子；主要指标为相对输入方向的平均角误差。用种子 801–805 置换训练标签，同方向三次样本共享标签，特征、样本数与回归设置不变；另设关闭读出对照。五组置换共享数据，不增加独立样本数。")
    paragraph("归巢采用原折线、往复折线和渐变转向三条预定路线，总长均为 18，场地无障碍。转向观测加入独立零均值高斯噪声，标准差为 0°、5°、15°；实际路线不变，距离准确。噪声控制任务难度，不是训练信号。几何基线与神经方法共用观测、搜索参数及到达判定；路程均值包含失败。")
    paragraph("首轮种子 601–605 每档有 15 个路线与种子组合。新种子 701–710 形成 90 个神经导航试验，返程转向执行噪声标准差为 0° 或 2°，搜索预算为 0、18、36、72。各条件共用按动作序号对齐的执行误差。每档 30 个组合共享十个种子；图示预定为原路线、种子 701、2° 执行误差。")
    heading("四、结果与分析")
    paragraph(f"正常读出的未见方向平均误差为 {normal_mae:.2f}°，最大为 {float(normal_decoder['heldout_max_deg']):.2f}°；标签置换后平均误差为 {shuffled_range}。这表明读出器能利用当前特征中的方向对应关系。误差衡量输入方向的恢复精度，不等于归巢时相对真实朝向的误差。")
    rows=[["读出条件","未见方向\n平均角误差","归巢到达次数","平均返程路程"]]
    for label,method,variant in [("正常读出","cx_normal",0)]+[(f"标签置换 {s}","cx_shuffled_labels",s) for s in range(801,806)]+[("关闭读出","readout_off",0)]:
        a=one(controls,method=method,variant=variant,noise_deg=5,budget=72)
        d=one(decoders,method=method,variant=variant)
        rows.append([label,f"{float(d['heldout_mae_deg']):.2f}°",count(a),f"{float(a['mean_return_distance']):.2f}"])
    table("表一 方向读出对照 归巢列采用旧种子及 5° 噪声 预算 72",rows,[2500,1700,1600,2506])
    paragraph("表一中，标签置换降低归巢效果，但置换 804 仍到达 13/15，说明搜索能补救部分错误。断开 CX 连接后，非输入读出神经元不再放电，说明特征依赖连接传播；这不证明真实结构优于随机网络。")
    low_direct = one(old, method="cx_direct", noise_deg=5)
    low_search = one(old, method="cx_search", noise_deg=5)
    paragraph(f"首轮 5° 噪声下，加搜索使到达次数由 {count(low_direct)} 增至 {count(low_search)}，平均路程由 {float(low_direct['mean_return_distance']):.2f} 增至 {float(low_search['mean_return_distance']):.2f}。新种子结果见表二。")
    rows = [["观测噪声", "理想返程到达", "2° 误差到达", "平均路程\n理想 / 有误差"]]
    for noise in [0, 5, 15]:
        a,b=trial(noise),trial(noise,2)
        rows.append([f"{noise}°",count(a),count(b),f"{float(a['mean_return_distance']):.2f} / {float(b['mean_return_distance']):.2f}"])
    table("表二 新种子的归巢应用结果 搜索预算为 72",rows,[1300,2050,2050,2906])
    paragraph("几何方法理想返程的三档结果为 30/30、29/30、21/30，有执行误差时为 30/30、30/30、20/30，与神经方法接近。低噪声路程略缩短是样本内的轨迹扰动，不能说明执行噪声有益。")
    # Generate only the new inline image element; the retained DOCX remains the package base.
    image_doc = Document()
    shape = image_doc.add_paragraph().add_run().add_picture(str(ROOT / "reports/assets/paper_trajectory.png"), width=Cm(14.65))
    drawing = deepcopy(image_doc.paragraphs[0]._p.find('.//' + q('w:drawing')))
    drawing.find('.//wp:docPr',NS).set('descr','种子701的成功与失败轨迹：蓝虚线出发、橙实线返程、紫点划线搜索；A为家，B开始返程，C开始搜索，箭头指示移动方向，无障碍物')
    drawing.find('.//a:blip',NS).set(q('r:embed'),'rIdFinalTrajectory')
    p = paragraph('',82,keep=True)
    p.find(q('w:r')).append(drawing)
    paragraph("图一 固定种子 701 的归巢轨迹。A 为家，B 开始返程，C 开始搜索；蓝虚线为出发，橙实线为返程，紫点划线为搜索，箭头示方向。无障碍物，两图均含 2° 转向执行误差。",84,indent=False)
    paragraph(f"预算分析保留了不符合预期的结果：旧样本预算 36 曾覆盖低噪声全部成功，新样本只有 27/30 或 28/30，故保留主预算 72。高噪声且有执行误差时，预算从 36 增至 72，成功由 15 增至 20，平均路程由 {float(trial(15,2,36)['mean_return_distance']):.2f} 增至 {float(trial(15,2,72)['mean_return_distance']):.2f}。完整预算数据与曲线保留在仓库及成果包中。")
    heading("五、讨论与结论")
    paragraph("本实验表明，人工方向信息经过固定 CX 网络后，可由外部读出器从下游放电恢复。学到的是放电到输入方向的映射；果蝇网络没有根据归巢反馈更新，也未学习记忆或搜索。该结果不支持脑内自主归巢或真实生物罗盘机制的结论。")
    paragraph("前期单路线、无噪声时，外部运动平均将终点误差从 2.04 降至 0.19，成功从 1/3 增至 3/3，另三个新种子也为 3/3；有噪声时未见稳定收益。窗口由 250 ms 延至 1,000 ms 未稳定改善归巢，故保留短窗口。这些是控制器与参数比较，不是果蝇网络的训练。")
    paragraph("归巢效果受观测误差、读出精度与搜索预算共同影响。改进主要来自外部平均与搜索，几何基线表现接近；减小噪声或扩大搜索不能证明网络学会导航。人工输入、窗口重置、准确距离、理想到达检测和少量路线限制了推广。后续可固定编码与读出条件，增加连接结构对照。")
    paragraph("代码与完整结果见 github.com/yinyiqing/fly-brain-navigation。10 张结果表通过保存神经输出的重放核对，不等于重跑神经仿真。")
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
