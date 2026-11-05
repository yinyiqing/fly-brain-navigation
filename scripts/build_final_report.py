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
import struct
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
    image_pattern = next(p for p in patterns if p.find('.//w:drawing', NS) is not None)
    embedded_media = {}
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

    def figure(path, caption):
        image_bytes = path.read_bytes()
        if image_bytes[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Paper figure must be a PNG')
        width, height = struct.unpack('>II', image_bytes[16:24])
        cx = int(14.65 * 360000)
        cy = round(cx * height / width)
        p = deepcopy(image_pattern)
        pp = p.find(q('w:pPr'))
        set_prop(pp, 'w:jc', val='center')
        set_prop(pp, 'w:keepNext', val=1)
        set_prop(pp, 'w:snapToGrid', val=0)
        set_prop(pp, 'w:spacing', before=60, after=60, line=240, lineRule='auto')
        for extent in p.findall('.//wp:extent', NS) + p.findall('.//a:xfrm/a:ext', NS):
            extent.set('cx', str(cx))
            extent.set('cy', str(cy))
        for node in p.findall('.//wp:effectExtent', NS):
            for key in ['l', 't', 'r', 'b']:
                node.set(key, '0')
        picture_props = p.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/picture}cNvPr')
        for node in p.findall('.//wp:docPr', NS) + picture_props:
            node.set('name', '方向放电响应与读出')
            node.set('descr', '16个未见方向的128维放电计数及方向预测；平均角误差4.24度。')
        for blip in p.findall('.//a:blip', NS):
            blip.set(q('r:embed'), 'rIdDirectionReadout')
        embedded_media['word/media/paper_direction_readout.png'] = image_bytes
        body.append(p)
        paragraph(caption, 76, indent=False)

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
    normal_trial = one(controls, method="cx_normal", variant=0, noise_deg=5, budget=72)
    shuffled_trials = [one(controls, method="cx_shuffled_labels", variant=s, noise_deg=5, budget=72)
                       for s in range(801, 806)]
    shuffled_successes = [int(row["successes"]) for row in shuffled_trials]
    shuffled_distances = [float(row["mean_return_distance"]) for row in shuffled_trials]
    normal_distance = float(normal_trial["mean_return_distance"])
    minimum_distance_reduction = 100 * (1 - normal_distance / min(shuffled_distances))
    paragraph(TITLE, 0, keep=True)
    paragraph(text_of(patterns[1]), 1)
    paragraph("摘要", 7, keep=True)
    paragraph(f"本文研究果蝇连接组的下游放电能否被读成连续方向，并将读出结果用于归巢。基于 FlyWire 数据与公开模型，构建人工方向刺激和岭回归读出接口。48 个样本训练后，读出器在 16 个未见输入方向上的平均角误差为 {normal_mae:.2f}°。在 5° 观测噪声、搜索预算 72 的标签对照中，正常读出到达 {count(normal_trial)}，平均返程路程较五组标签置换至少缩短 {minimum_distance_reduction:.1f}%。相同噪声与预算下，三条路线、十个新种子的验证到达 30/30。结果表明，放电中的方向信息可以通过监督学习读出，并用于后续归巢控制。", indent=False)
    paragraph("关键词  果蝇连接组；方向编码；神经读出；岭回归；归巢验证", indent=False)
    heading("一、引言")
    paragraph("归巢是离开起点后，依据运动信息估计起点位置并返回的过程。FlyWire 提供果蝇连接图与细胞注释[1–2]，Shiu 等的公开模型提供放电仿真[3]。本文在此基础上实现方向编码、监督读出和二维归巢任务。未见方向测试检验读出精度，标签置换检验正确映射的作用，多路线实验评价读出结果在归巢中的表现。")
    heading("二、研究方法")
    paragraph("方法包含方向编码、读出训练和归巢控制。连接组负责产生放电，外部读出器学习方向，控制程序累积位置并计算动作。采用 FAFB v783 数据[4]与 v2.1.0 注释，提取 2,869 个中央复合体（CX）神经元及内部 300,065 条连接记录。沿用公开模型的带符号权重和泄漏积分发放（LIF）方程，在 Brian2 2.5.1[5]中模拟，步长 0.1 ms。神经元达到阈值后放电并复位；网络权重固定，每个 250 ms 刺激窗口从静息状态开始。")
    paragraph(["选择 47 个 EPG 神经元作为输入，按原始行序均匀分配人工偏好角 ", equation(math_sub("φ", "i")), "。方向 θ 对应的 Poisson 刺激频率为 ", equation(math_sub("r", "i"), "(θ)=15+67.5[1+cos(θ−", math_sub("φ", "i"), ")]"), "，单位为 Hz。方向越接近偏好角，刺激频率越高。刺激沿连接传播后，统计 128 个非输入神经元的放电次数，得到 128 维特征。读出神经元按 EPG 输出连接绝对权重之和选取，选择过程先于训练。"])
    paragraph("训练时，将每组放电特征与产生它的输入方向配对。方向每隔 22.5° 取一个，共 16 个，各用不同随机种子重复三次，得到 48 个样本。特征减去训练均值，再除以标准差与 1 的较大值。岭回归拟合方向的余弦和正弦，最小化分量预测的平方误差，并加入系数为 10 的权重平方惩罚，约束回归权重。")
    paragraph(["用正弦、余弦表示方向，可以处理 359° 与 1° 相邻这类跨零点情况。令标准化特征为 x，两个预测分量为 ", equation("(", math_hat("c"), ",", math_hat("s"), ")=xW+b"), "，方向由 ", equation(math_hat("θ"), "=atan2(", math_hat("s"), ",", math_hat("c"), ")"), " 恢复。训练求解的是读出权重 W，它决定各神经元的放电如何参与方向估计；b 为训练目标均值。连接组中的突触权重保持固定。"])
    paragraph("归巢时，仿真程序在每次实际转向上加入噪声，生成转向观测。控制器累积这些观测得到估计朝向，将其编码为刺激，再从放电中读出方向。历次读数按观测转向旋转到当前朝向并作圆周平均。每步距离由路线配置直接提供，按准确值使用；控制器将距离按读出方向分解并累加，保存当前位置相对起点的估计。")
    paragraph("返程向量取估计位置的相反向量，其长度给出返程距离，其方向与当前估计朝向之差给出转角。转角由几何计算得到。直接返程未到达时，执行间隔 1.5、额外路程预算 72 的方形搜索。环境在进入起点半径 1 的区域时提供到达信号，运动随即停止。")
    heading("三、实验设计")
    paragraph("方向测试采用 16 个未见输入角度，位于相邻训练方向的中点，偏移量为 11.25°，各生成一次新随机种子的响应。读出误差取预测方向与输入方向的圆周最短夹角。用种子 801–805 置换训练标签，同方向的三次样本共享置换标签，特征和拟合设置不变；五组置换复用相同数据。另将放电特征置零作为关闭读出对照，断开 CX 连接检验下游响应对连接传播的依赖。")
    paragraph("归巢场地无障碍，三条路线分别为原折线、往复折线和渐变转向，总长均为 18。外出转向观测加入独立零均值高斯噪声，标准差为 0°、5°、15°；返程转向执行误差标准差为 0° 或 2°。标签与搜索对照用种子 601–605，每档 15 个路线与种子组合；多路线验证用种子 701–710，每档 30 个组合，路线间共用种子。搜索预算取 0、18、36、72。几何基线直接积分同一份观测，共用搜索与到达规则，执行误差按动作序号对齐。统计到达次数和包含失败试验的平均路程，距离均为仿真单位。")
    heading("四、结果与分析")
    paragraph(f"图一展示未见方向的放电响应与读出结果。平均角误差为 {normal_mae:.2f}°，最大为 {float(normal_decoder['heldout_max_deg']):.2f}°，均小于测试角度与最近训练方向之间的 11.25°。这说明读出器能恢复这些训练点之间的方向。在 0° 输入下断开 CX 连接后，下游读出神经元的放电计数为零，说明该响应依赖连接传播。")
    figure(ROOT / 'reports/assets/paper_direction_readout.png',
           '图一 16 个未见输入方向的放电响应与读出。左图为 128 个神经元在 250 ms 内的放电次数，右图虚线表示输入与读出一致。')
    rows=[["读出条件","未见方向\n平均角误差","归巢到达次数","平均返程路程"]]
    for label,method,variant in [("正常读出","cx_normal",0),("关闭读出","readout_off",0)]:
        a=one(controls,method=method,variant=variant,noise_deg=5,budget=72)
        d=one(decoders,method=method,variant=variant)
        rows.append([label,f"{float(d['heldout_mae_deg']):.2f}°",count(a),f"{float(a['mean_return_distance']):.2f}"])
    rows.insert(2,["标签置换（五组）",shuffled_range,
                   f"{min(shuffled_successes)}/15–{max(shuffled_successes)}/15",
                   f"{min(shuffled_distances):.2f}–{max(shuffled_distances):.2f}"])
    table("表一 读出对照 归巢采用种子 601–605 观测噪声 5° 预算 72",rows,[2500,1900,1700,2206])
    paragraph(f"表一置换行各列给出五组结果范围。正常读出获得更多到达次数，平均路程较五组置换至少缩短 {minimum_distance_reduction:.1f}%。置换 804 到达 13/15，平均路程为 38.05，说明搜索能补救部分方向错误；正确映射进一步减少了行走代价。")
    low_direct = one(old, method="cx_direct", noise_deg=5)
    low_search = one(old, method="cx_search", noise_deg=5)
    paragraph(f"在 5° 观测噪声下，加入局部搜索使到达次数由 {count(low_direct)} 增至 {count(low_search)}，平均路程由 {float(low_direct['mean_return_distance']):.2f} 增至 {float(low_search['mean_return_distance']):.2f}。表二检验三条路线与十个不同随机种子下的归巢表现。")
    rows = [["观测噪声\n标准差", "0° 执行误差\n到达次数", "2° 执行误差\n到达次数", "平均返程路程\n0° / 2° 执行误差"]]
    for noise in [0, 5, 15]:
        a,b=trial(noise),trial(noise,2)
        rows.append([f"{noise}°",count(a),count(b),f"{float(a['mean_return_distance']):.2f} / {float(b['mean_return_distance']):.2f}"])
    table("表二 多路线与不同随机种子下的归巢验证 搜索预算 72",rows,[1300,2050,2050,2906])
    paragraph("两种执行条件在 0° 和 5° 观测噪声下均到达 30/30。观测误差沿外出过程累积，改变位移投影，使估计起点偏移。几何基线提供相同观测下的参考：在 2° 执行误差下，三档噪声中的到达次数与神经方法相同，说明读出的方向能作为位置积分的有效输入。")
    paragraph(f"预算从 36 增至 72 时，5° 观测噪声下两种执行条件分别由 {count(trial(5,0,36))}、{count(trial(5,2,36))} 增至 30/30。15° 观测噪声、2° 执行误差下，到达次数由 {count(trial(15,2,36))} 增至 {count(trial(15,2,72))}，平均路程由 {float(trial(15,2,36)['mean_return_distance']):.2f} 增至 {float(trial(15,2,72)['mean_return_distance']):.2f}。增加预算扩大了搜索覆盖范围，也增加了行走成本。")
    heading("五、讨论与结论")
    paragraph(f"本文用 48 个样本训练外部读出器，将固定果蝇连接组的放电转换为方向，未见输入方向的平均误差为 {normal_mae:.2f}°。标签置换对照中，正确映射同时提高到达次数并缩短路程。实验从方向恢复精度和归巢行为两方面，验证了这些方向读数在位置积分与动作计算中的作用。")
    paragraph("代码与补充材料见 github.com/yinyiqing/fly-brain-navigation，包含置换明细、归巢轨迹、预算曲线、窗口与运动平均比较。保存的神经输出可重放导航并核对 10 张结果表。")
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
    parts.update(embedded_media)
    E.SubElement(rels, q('pr:Relationship'), {
        'Id': 'rIdDirectionReadout',
        'Type': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',
        'Target': 'media/paper_direction_readout.png',
    })
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
