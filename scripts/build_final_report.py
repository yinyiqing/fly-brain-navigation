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
from format_report import NS, q, set_prop, text_of, xml_bytes

ROOT = Path(__file__).resolve().parents[1]
TITLE = "果蝇连接组的方向编码与读出及归巢验证"
FINAL_NAME = "果蝇连接组方向读出与归巢验证_24025110_尹一清.docx"


def math_run(text):
    run = E.Element(q("m:r"))
    props = E.SubElement(run, q("w:rPr"))
    set_prop(props, "w:rFonts", ascii="Cambria Math", hAnsi="Cambria Math")
    set_prop(props, "w:sz", val=24)
    E.SubElement(run, q("m:t")).text = text
    return run


def math_sub(base, subscript):
    node = E.Element(q("m:sSub"))
    E.SubElement(node, q("m:e")).append(math_run(base))
    E.SubElement(node, q("m:sub")).append(math_run(subscript))
    return node


def math_hat(base):
    node = E.Element(q("m:acc"))
    props = E.SubElement(node, q("m:accPr"))
    E.SubElement(props, q("m:chr"), {q("m:val"): "\u0302"})
    E.SubElement(node, q("m:e")).append(math_run(base))
    return node


def equation(*parts):
    node = E.Element(q("m:oMath"))
    for part in parts:
        node.append(math_run(part) if isinstance(part, str) else part)
    return node


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
        for part in [text] if isinstance(text, str) else text:
            if not isinstance(part, str):
                p.append(part)
                continue
            run = E.SubElement(p, q("w:r"))
            rp = deepcopy(patterns[index].find("w:r/w:rPr", NS))
            if rp is not None:
                set_prop(rp, "w:color", val="000000")
                run.append(rp)
            t = E.SubElement(run, q("w:t"))
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = part
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
    paragraph(f"本文基于 FlyWire v783 与 Brian2 研究果蝇中央复合体的方向读出，并用于归巢验证。固定连接组网络接收人工方向刺激，岭回归学习下游放电与方向的对应关系。48 个样本训练后，16 个未见方向的平均角误差为 {normal_mae:.2f}°；五组标签置换后升至 {shuffled_range}。读出结果接入位置积分与有限搜索后，三条路线、十个新种子在 5° 观测噪声下到达 30/30。实验表明，下游放电保留了可解码的方向信息，可为归巢提供有效的初始返程估计。", indent=False)
    paragraph("关键词  果蝇连接组；方向编码；神经读出；岭回归；归巢验证", indent=False)
    heading("一、引言")
    paragraph("归巢是离开起点后，依据运动信息估计起点位置并返回的过程。每段距离都需按方向分解为位移，因此方向估计会影响最终位置。FlyWire 提供果蝇连接图与细胞注释[1–2]，Shiu 等的公开模型支持连接组放电模拟[3]。本文据此研究方向信息经过网络后的可读出性：以已知方向训练读出器，在未见方向上检验精度，再通过归巢观察读出误差对行为的影响。")
    heading("二、研究方法")
    paragraph("采用 FAFB v783 数据[4]与 v2.1.0 注释，提取 2,869 个中央复合体（CX）神经元及内部 300,065 条连接记录。沿用公开模型的带符号权重和泄漏积分发放（LIF）方程，在 Brian2 2.5.1[5]中模拟，步长 0.1 ms、窗口 250 ms。神经元累积输入，达到阈值后产生脉冲并复位，脉冲再沿连接传播。网络连接与权重固定，每个刺激窗口从静息状态开始。")
    paragraph(["选择 47 个 EPG 神经元接收方向刺激，按原始行序均匀分配人工偏好角 ", equation(math_sub("φ", "i")), "。方向 θ 对应的 Poisson 输入频率为 ", equation(math_sub("r", "i"), "(θ)=15+67.5[1+cos(θ−", math_sub("φ", "i"), ")]"), "，单位为 Hz。输入方向越接近某神经元的偏好角，其刺激频率越高；方向改变时，高频刺激随之转移。按 EPG 输出连接绝对权重之和选取 128 个非输入神经元，统计各自在窗口内的放电次数，形成一个 128 维响应向量。固定窗口下，计数与平均发放率等价，保留了不同神经元响应强弱的差异。"])
    paragraph("读出器用监督学习建立放电与方向的映射。训练方向每隔 22.5° 取一个，共 16 个，每个方向使用不同随机种子重复三次，得到 48 个样本。重复刺激用于呈现同一方向下的放电波动。各维特征减去训练均值，再除以标准差与 1 的较大值，避免低变化特征被过度放大。岭回归同时拟合方向的余弦和正弦，最小化预测分量与目标分量的平方误差，并加入系数为 10 的权重平方惩罚，以约束小样本条件下的回归权重。")
    paragraph(["角度采用正弦和余弦表示，是为了保留圆周连续性。例如 359° 与 1° 相邻，直接回归角度数值会遇到跨零点的突变。令标准化特征为 x，读出结果为 ", equation("(", math_hat("c"), ",", math_hat("s"), ")=xW+b"), "，再用 ", equation(math_hat("θ"), "=atan2(", math_hat("s"), ",", math_hat("c"), ")"), " 恢复方向。训练得到的 W 决定各神经元的放电如何参与两个分量的估计，b 为训练目标均值。一组放电响应通过群体计数及学习到的组合权重，被转换为连续方向读数。"])
    paragraph("归巢阶段，外部程序累积带噪声的转向观测，将估计朝向编码为上述刺激。历次方向读数按观测转向旋转到当前朝向，再作圆周平均；随后将每段准确距离按方向分解并累加，保存当前位置相对起点的估计。这就是本实验的路径记忆。返程目标取估计位置的相反向量，长度决定行走距离，方向与当前估计朝向之差决定转角。直接返程后仍未到达时，执行间隔 1.5、额外路程最多 72 的扩展方形搜索；环境检测到进入起点半径 1 的区域便停止。")
    heading("三、实验设计")
    paragraph("方向测试取训练方向之间的中点，即整体偏移 11.25°，用新随机种子生成 16 个测试响应。误差取预测方向与输入方向在圆周上的最短夹角。另用种子 801–805 置换训练标签，同一方向的三次样本共用置换标签，再按相同流程拟合读出器；由此检验正确对应关系的作用。关闭读出对照将输入读出器的放电特征置零。五组置换共享原始数据。")
    paragraph("归巢场地无障碍，原折线、往复折线和渐变转向路线总长均为 18。各次转向观测叠加独立零均值高斯噪声，标准差为 0°、5°、15°，用于模拟运动感知偏差。首轮种子 601–605 每档有 15 个路线与种子组合；新种子 701–710 每档有 30 个组合。比较 0°、2° 返程转向执行误差和 0、18、36、72 搜索预算。几何基线直接积分同一份运动观测，共用搜索与到达规则；执行误差按动作序号对齐。统计到达次数和包含失败的平均返程路程，距离均采用仿真单位。")
    heading("四、结果与分析")
    paragraph(f"正常读出在未见方向上的平均误差为 {normal_mae:.2f}°，最大为 {float(normal_decoder['heldout_max_deg']):.2f}°，均小于训练方向的 22.5° 间隔。测试角度处于训练点之间，说明学习到的映射具有一定的方向插值能力。标签置换保留了同样的放电特征，却将平均误差提高至 {shuffled_range}，表明正确的方向标签是获得有效读出的关键。断开 CX 连接后，所选下游神经元的放电计数为零，进一步确认这些特征来自网络中的连接传播。")
    rows=[["读出条件","未见方向\n平均角误差","归巢到达次数","平均返程路程"]]
    for label,method,variant in [("正常读出","cx_normal",0),("关闭读出","readout_off",0)]:
        a=one(controls,method=method,variant=variant,noise_deg=5,budget=72)
        d=one(decoders,method=method,variant=variant)
        rows.append([label,f"{float(d['heldout_mae_deg']):.2f}°",count(a),f"{float(a['mean_return_distance']):.2f}"])
    shuffled_trials = [one(controls,method="cx_shuffled_labels",variant=s,noise_deg=5,budget=72)
                       for s in range(801,806)]
    shuffled_successes = [int(row['successes']) for row in shuffled_trials]
    shuffled_distances = [float(row['mean_return_distance']) for row in shuffled_trials]
    rows.insert(2,["标签置换（五组）",shuffled_range,
                   f"{min(shuffled_successes)}/15–{max(shuffled_successes)}/15",
                   f"{min(shuffled_distances):.2f}–{max(shuffled_distances):.2f}"])
    table("表一 读出对照 归巢采用首轮种子 5° 观测噪声与预算 72",rows,[2500,1900,1700,2206])
    paragraph("表一置换行列出五组结果范围。正常读出的到达次数较多，平均路程较短，说明有效方向估计有助于减少后续搜索。置换 804 仍到达 13/15，但平均路程增至 38.05，体现了搜索对错误的补救及其代价。因此，到达次数需结合读出误差和行走路程分析。")
    low_direct = one(old, method="cx_direct", noise_deg=5)
    low_search = one(old, method="cx_search", noise_deg=5)
    paragraph(f"首轮 5° 噪声下，加搜索使到达次数由 {count(low_direct)} 增至 {count(low_search)}，平均路程由 {float(low_direct['mean_return_distance']):.2f} 增至 {float(low_search['mean_return_distance']):.2f}。新种子结果见表二。")
    rows = [["观测噪声", "理想返程到达", "2° 误差到达", "平均路程\n理想 / 有误差"]]
    for noise in [0, 5, 15]:
        a,b=trial(noise),trial(noise,2)
        rows.append([f"{noise}°",count(a),count(b),f"{float(a['mean_return_distance']):.2f} / {float(b['mean_return_distance']):.2f}"])
    table("表二 新种子的归巢应用结果 搜索预算为 72",rows,[1300,2050,2050,2906])
    paragraph("表二中，到达次数在高噪声下减少。转向误差随外出过程累积，改变后续位移的投影，使估计起点偏离真实起点。即使距离准确，按这个估计返程仍可能错过家。补充轨迹图显示：搜索经过起点区域时成功，预算耗尽前仍未进入则失败。几何基线在有执行误差时到达 30/30、30/30、20/30，与神经方法接近。")
    paragraph(f"搜索预算决定可用于补救的额外路程。旧种子在低噪声下用预算 36 已全部到达，新种子则为 27/30 或 28/30，主配置采用 72 后均达到 30/30。高噪声且有执行误差时，预算从 36 增至 72，到达次数由 15/30 增至 20/30，平均路程由 {float(trial(15,2,36)['mean_return_distance']):.2f} 增至 {float(trial(15,2,72)['mean_return_distance']):.2f}。额外搜索提高了目标被覆盖的机会，也增加了行走成本。")
    heading("五、讨论与结论")
    paragraph("本实验从固定 CX 网络的下游放电中恢复连续方向，并将学习到的映射用于归巢。读出误差 4.24° 衡量输入方向的恢复精度；归巢还叠加运动观测与执行误差。标签对照说明方向对应关系对后续行为有实际作用，预算比较则体现了搜索成功率与路程的权衡。")
    paragraph("前期无噪声单路线实验中，运动补偿平均使终点误差由 2.04 降至 0.19；有噪声时收益不稳定，窗口从 250 ms 延至 1,000 ms 也未带来稳定改善。本文保留短窗口，并用有限搜索处理剩余位置偏差。当前结论适用于人工相位编码、准确距离、无障碍及二值到达检测的设置。后续可在相同输入和读出条件下加入随机连接组对照，进一步分析连接结构对方向信息保留的影响。")
    paragraph("代码与补充材料见 github.com/yinyiqing/fly-brain-navigation，含逐组置换结果、轨迹图和预算曲线。保存的神经输出可用于重放导航，并核对全部 10 张结果表。")
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
