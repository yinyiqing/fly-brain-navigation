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
    paragraph(f"本文研究如何从果蝇神经网络的放电中预测方向，并用于返回起点。基于 FlyWire 数据与公开模型，把已知方向转换为神经刺激，再用放电次数与对应方向训练岭回归读出器。48 个样本训练后，16 个未参与训练的方向的平均预测误差为 {normal_mae:.2f}°。在转向感知误差标准差为 5°、额外搜索路程上限为 72 的对照中，正常读出到达 {count(normal_trial)}，平均返程路程较五组打乱训练方向的对照至少缩短 {minimum_distance_reduction:.1f}%。相同感知误差与搜索上限下，三条路线、十个新种子的验证到达 30/30，说明读出的方向能够用于归巢。", indent=False)
    heading("一、引言")
    paragraph("归巢是从起点外出后，再找到并返回起点。完成这一任务，需要知道每一步朝哪个方向、走了多远，才能逐步估计当前位置。FlyWire 提供果蝇神经元之间的连接数据与细胞注释[1–2]，Shiu 等的公开模型可据此模拟神经元放电[3]。这些放电如何转化为导航可用的方向，是本文关注的问题。本文实现方向输入与读出训练，并用二维归巢任务检验读出结果的作用。")
    heading("二、研究方法")
    paragraph("本文使用 FlyWire v783 中央复合体（CX）的连接数据[4]构建神经网络，通过 Brian2[5]模拟放电。先输入已知方向，再检查能否从放电中恢复这个方向，以此检验网络响应是否保留了方向信息。网络产生放电；方向训练、读出和位置估计由外部程序完成。")
    paragraph("输入时，选取 47 个 EPG 神经元，为每个神经元人工指定一个偏好方向，并将这些方向均匀分布一周。输入方向越接近某个神经元的偏好方向，对它的刺激频率越高。刺激沿连接传播后，统计另外 128 个神经元在 250 ms 内各自放电了多少次。这 128 个数与对应的输入方向，构成一条训练样本。每次刺激前网络恢复静息状态；输入公式与神经元筛选规则见补充材料。")
    paragraph("训练时，每隔 22.5° 取一个方向，共 16 个方向，各用不同随机种子重复三次，得到 48 个样本。用这些样本训练岭回归模型，让它根据放电次数预测方向，训练得到的模型称为方向读出器。由于 359° 与 1° 实际相邻，读出器先预测方向的余弦和正弦，再换算为角度，避免把接近 0° 的两个方向当作相距很远。")
    paragraph(["将标准化后的放电次数记为 x，读出器预测余弦、正弦分量 ", equation("(", math_hat("c"), ",", math_hat("s"), ")=xW+b"), "，再用 ", equation(math_hat("θ"), "=atan2(", math_hat("s"), ",", math_hat("c"), ")"), " 恢复方向。W 表示各神经元放电在预测中的权重，b 为偏置。岭回归通过减小预测误差并约束 W 的大小求解权重。学习调整的是读出器参数，果蝇网络的连接权重固定。"])
    paragraph("外出时，程序在真实转角上加入随机误差，模拟转向感知不准确，再累加这些观测得到方向输入。该方向按照前述规则输入网络，由读出器根据放电给出方向估计。为减小单次读数的波动，程序还会利用过去的读数：先按期间的转向把旧读数调整为对当前朝向的估计，再对这些方向取平均。")
    paragraph("得到方向后，程序将它与每一步的移动距离结合，累加位移，估计当前位置相对起点的变化，这一过程称为路径积分。距离由路线配置按准确值提供，位置记录保存在控制程序中。外出结束后，从估计位置指向起点的向量给出返程方向和距离；它与当前估计朝向的夹角，就是需要转动的角度。")
    paragraph("感知误差会使估计位置偏离真实位置，直接返程后可能还没有到家。因此，程序在返程终点附近沿扩展方形路线搜索，线间隔为 1.5，额外路程最多为 72。进入真实起点半径 1 的区域时，环境提供到达信号，程序据此停止；该信号只判断是否到达。")
    heading("三、实验设计")
    paragraph("方向测试选取相邻训练方向的中点，共 16 个，与最近训练方向相差 11.25°，各生成一次新随机种子的放电响应。误差取预测方向与输入方向之间的最小夹角。为检验读出器学到的对应关系，保持放电数据不变，打乱每条记录对应的训练方向，再训练五组对照。另将放电次数置零，检查关闭读出后的归巢表现；在 0° 输入下断开 CX 连接，检查所记录的放电是否依赖连接传播。")
    paragraph("归巢场地没有障碍物，设置三条总长均为 18 的路线。外出时的转向感知误差服从独立零均值高斯分布，标准差取 0°、5°、15°；返程时另设置标准差为 0° 或 2° 的转向执行误差。读出与搜索对照在每条路线使用五个随机种子，每档共 15 次；多路线验证改用十个新种子，每档共 30 次，路线之间共用种子。")
    paragraph("实验统计到达次数和平均返程路程，路程均值包含未到达的试验。搜索上限取 0、18、36、72，距离均为仿真单位。另设几何方法作为参照：直接用同一份方向观测累加位移，采用相同的搜索与到达规则。具体参数、种子编号和配对方式见补充材料。")
    heading("四、结果与分析")
    paragraph(f"图一检验读出器能否预测没有参与训练的方向。平均角误差为 {normal_mae:.2f}°，最大为 {float(normal_decoder['heldout_max_deg']):.2f}°，均小于测试方向与最近训练方向之间的 11.25°，说明它能够预测这些训练方向之间的角度。在 0° 输入下断开 CX 连接后，所选读出神经元的放电次数为零，说明该输入下的响应依赖连接传播。")
    figure(ROOT / 'reports/assets/paper_direction_readout.png',
           '图一 16 个测试方向的放电与预测结果。左图为 128 个神经元在 250 ms 内的放电次数；右图的点越接近虚线，方向预测越准确。')
    rows=[["读出条件","测试方向\n平均角误差","归巢到达次数","平均返程路程"]]
    for label,method,variant in [("正常读出","cx_normal",0),("关闭读出","readout_off",0)]:
        a=one(controls,method=method,variant=variant,noise_deg=5,budget=72)
        d=one(decoders,method=method,variant=variant)
        rows.append([label,f"{float(d['heldout_mae_deg']):.2f}°",count(a),f"{float(a['mean_return_distance']):.2f}"])
    rows.insert(2,["打乱训练方向（五组）",shuffled_range,
                   f"{min(shuffled_successes)}/15–{max(shuffled_successes)}/15",
                   f"{min(shuffled_distances):.2f}–{max(shuffled_distances):.2f}"])
    table("表一 读出对照 感知误差标准差 5° 搜索上限 72",rows,[2500,1900,1700,2206])
    paragraph(f"表一比较正常读出、打乱训练方向和关闭读出三种条件。打乱方向一行给出五组结果的范围。正常读出获得更多到达次数，平均返程路程较五组打乱方向的对照至少缩短 {minimum_distance_reduction:.1f}%。这说明，学到正确的放电与方向对应关系，有助于把返程引向起点附近，减少后续搜索需要行走的路程。")
    low_direct = one(old, method="cx_direct", noise_deg=5)
    low_search = one(old, method="cx_search", noise_deg=5)
    paragraph(f"在 5° 感知误差下，加入搜索后，到达次数由 {count(low_direct)} 增至 {count(low_search)}，平均返程路程由 {float(low_direct['mean_return_distance']):.2f} 增至 {float(low_search['mean_return_distance']):.2f}。表二用三条路线和十个新种子检验归巢表现。")
    rows = [["感知误差\n标准差", "0° 执行误差\n到达次数", "2° 执行误差\n到达次数", "平均返程路程\n0° / 2° 执行误差"]]
    for noise in [0, 5, 15]:
        a,b=trial(noise),trial(noise,2)
        rows.append([f"{noise}°",count(a),count(b),f"{float(a['mean_return_distance']):.2f} / {float(b['mean_return_distance']):.2f}"])
    table("表二 三条路线与十个新随机种子的归巢验证 搜索上限 72",rows,[1300,2050,2050,2906])
    paragraph("两种返程执行条件在 0° 和 5° 感知误差下均到达 30/30。感知误差更大时，扩大搜索范围可提高到达次数，也会增加路程，详见补充材料。在 2° 执行误差下，几何方法的三档到达次数与神经方法相同，表明读出方向能用于这一归巢流程。")
    heading("五、讨论与结论")
    paragraph(f"本文用 48 个样本训练方向读出器，将固定果蝇网络的放电转换为方向，测试平均误差为 {normal_mae:.2f}°。正确的放电与方向对应关系提高了归巢到达次数，并缩短了返程路程，验证了读出方向在位置估计与返程控制中的作用。")
    code_note = paragraph("代码与补充材料：github.com/yinyiqing/fly-brain-navigation。", indent=False)
    set_prop(code_note.find(q("w:pPr")), "w:jc", val="left")
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
