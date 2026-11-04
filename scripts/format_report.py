#!/usr/bin/env python3
"""Apply the supplied course-report formatting to the existing fly report.

The reference package supplies page geometry, styles and paragraph/table
patterns. Scientific paragraphs, native equations and figure bytes come from
the existing report. Both input documents are left untouched.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import zipfile

from lxml import etree


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def q(name):
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def xml_bytes(element):
    return etree.tostring(element, encoding="UTF-8", xml_declaration=True,
                          standalone=True)


def text_of(element):
    return "".join(element.xpath(".//w:t/text()", namespaces=NS))


def set_prop(parent, name, **attrs):
    element = parent.find(q(name))
    if element is None:
        element = etree.SubElement(parent, q(name))
    for key, value in attrs.items():
        element.set(q(f"w:{key}"), str(value))
    return element


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--source", type=Path,
                        default=root / "reports/数字果蝇归巢课程报告.docx")
    parser.add_argument("--output", type=Path,
                        default=root / "reports/数字果蝇归巢课程报告_排版版.docx")
    args = parser.parse_args()
    if args.output.resolve() in {args.source.resolve(), args.reference.resolve()}:
        raise ValueError("Output must be different from both input documents")
    reference_hash = hashlib.sha256(args.reference.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(args.source.read_bytes()).hexdigest()
    with zipfile.ZipFile(args.reference) as archive:
        reference = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(args.source) as archive:
        source = {name: archive.read(name) for name in archive.namelist()}
    parts = reference.copy()
    document = etree.fromstring(reference["word/document.xml"])
    body = document.find(q("w:body"))
    patterns = body.findall(q("w:p"))
    table_pattern = body.findall(q("w:tbl"))[0]
    section = deepcopy(body.find(q("w:sectPr")))
    source_document = etree.fromstring(source["word/document.xml"])
    source_body = source_document.find(q("w:body"))
    source_paragraphs = source_body.findall(q("w:p"))
    title = text_of(source_paragraphs[0])

    styles = etree.fromstring(reference["word/styles.xml"])
    for style_id, name, index, outline in [
        ("FlyTitle", "Title", 0, None),
        ("FlyHeading1", "heading 1", 2, 0),
        ("FlyHeading2", "heading 2", 7, 1),
    ]:
        style = etree.SubElement(styles, q("w:style"),
                                 {q("w:type"): "paragraph", q("w:styleId"): style_id})
        set_prop(style, "w:name", val=name)
        set_prop(style, "w:basedOn", val="1")
        set_prop(style, "w:next", val="1")
        set_prop(style, "w:qFormat")
        ppr = deepcopy(patterns[index].find(q("w:pPr")))
        run_mark = ppr.find(q("w:rPr"))
        if run_mark is not None:
            ppr.remove(run_mark)
        set_prop(ppr, "w:snapToGrid", val=0)
        set_prop(ppr, "w:keepNext", val=1)
        if outline is not None:
            set_prop(ppr, "w:outlineLvl", val=outline)
        style.append(ppr)
        style.append(deepcopy(patterns[index].find("w:r/w:rPr", NS)))

    def paragraph(original, pattern_index, style_id=None, keep_next=False):
        result = deepcopy(original)
        old_ppr = result.find(q("w:pPr"))
        if old_ppr is not None:
            result.remove(old_ppr)
        ppr = deepcopy(patterns[pattern_index].find(q("w:pPr")))
        for item in ppr.findall(q("w:numPr")):
            ppr.remove(item)
        if style_id:
            ppr.insert(0, etree.Element(q("w:pStyle"), {q("w:val"): style_id}))
        # Honor the explicit line spacing rather than letting the inherited
        # CJK document grid inflate it in different Word-compatible renderers.
        set_prop(ppr, "w:snapToGrid", val=0)
        set_prop(ppr, "w:widowControl", val=1)
        set_prop(ppr, "w:keepNext", val=int(keep_next))
        result.insert(0, ppr)
        template_rpr = patterns[pattern_index].find("w:r/w:rPr", NS)
        for run in result.findall(q("w:r")):
            old = run.find(q("w:rPr"))
            if old is not None:
                run.remove(old)
            if template_rpr is not None:
                run.insert(0, deepcopy(template_rpr))
        for stale in result.xpath(".//w:lastRenderedPageBreak", namespaces=NS):
            stale.getparent().remove(stale)
        return result

    def replace_text(p, value):
        rpr = deepcopy(p.find("w:r/w:rPr", NS))
        for child in list(p):
            if child.tag != q("w:pPr"):
                p.remove(child)
        run = etree.SubElement(p, q("w:r"))
        if rpr is not None:
            run.append(rpr)
        t = etree.SubElement(run, q("w:t"))
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = value

    # Keep reference relationships and opaque package parts; replace only the
    # old topic's figure assets and their document relationships.
    relationships = etree.fromstring(reference["word/_rels/document.xml.rels"])
    for rel in list(relationships):
        if rel.get("Type", "").endswith("/image"):
            relationships.remove(rel)
    for name in list(parts):
        if name.startswith("word/media/") and not name.endswith("/"):
            del parts[name]
    source_rels = etree.fromstring(source["word/_rels/document.xml.rels"])
    image_mapping = {}
    for rel in source_rels:
        if rel.get("Type", "").endswith("/image"):
            old_id, target = rel.get("Id"), rel.get("Target")
            new_id = f"rIdFlyImage{len(image_mapping) + 1}"
            image_mapping[old_id] = new_id
            relationships.append(etree.Element(q("pr:Relationship"), {
                "Id": new_id, "Type": rel.get("Type"), "Target": target}))
            parts[f"word/{target}"] = source[f"word/{target}"]

    def results_table(original):
        result = deepcopy(table_pattern)
        rows = result.findall(q("w:tr"))
        row_patterns = [deepcopy(rows[0]), deepcopy(rows[1]), deepcopy(rows[-1])]
        for row in rows:
            result.remove(row)
        widths = [1400, 2300, 2300, 2306]
        grid = result.find(q("w:tblGrid"))
        for column, width in zip(grid, widths):
            column.set(q("w:w"), str(width))
        tpr = result.find(q("w:tblPr"))
        set_prop(tpr, "w:tblW", w=sum(widths), type="dxa")
        set_prop(tpr, "w:jc", val="center")
        original_rows = original.findall(q("w:tr"))
        for i, old_row in enumerate(original_rows):
            row = deepcopy(row_patterns[0 if i == 0 else 2 if i == len(original_rows)-1 else 1])
            trpr = row.find(q("w:trPr"))
            if trpr is None:
                trpr = etree.Element(q("w:trPr"))
                row.insert(0, trpr)
            for height in trpr.findall(q("w:trHeight")):
                trpr.remove(height)
            set_prop(trpr, "w:cantSplit", val=1)
            if i == 0:
                set_prop(trpr, "w:tblHeader", val=1)
            for j, (cell, old_cell) in enumerate(zip(row.findall(q("w:tc")), old_row.findall(q("w:tc")))):
                tcpr = cell.find(q("w:tcPr"))
                set_prop(tcpr, "w:tcW", w=widths[j], type="dxa")
                set_prop(tcpr, "w:vAlign", val="center")
                if i > 1:
                    borders = tcpr.find(q("w:tcBorders"))
                    set_prop(borders, "w:top", val="nil")
                p = cell.find(q("w:p"))
                for extra in list(cell):
                    if extra.tag != q("w:tcPr"):
                        cell.remove(extra)
                replace_text(p, text_of(old_cell))
                pp = p.find(q("w:pPr"))
                set_prop(pp, "w:snapToGrid", val=0)
                set_prop(pp, "w:keepNext", val=int(i < len(original_rows)-1))
                set_prop(pp, "w:spacing", before=60, after=60, line=240, lineRule="auto")
                set_prop(pp, "w:jc", val="center")
                cell.append(p)
            result.append(row)
        return result

    for child in list(body):
        body.remove(child)
    paragraph_index = 0
    for element in source_body:
        if element.tag == q("w:tbl"):
            body.append(results_table(element))
            continue
        if element.tag != q("w:p"):
            continue
        index = paragraph_index
        paragraph_index += 1
        text = text_of(element)
        drawing = element.find(".//w:drawing", NS)
        math = element.find(".//m:oMath", NS)
        if not text and drawing is None and math is None:
            continue
        if index == 0:
            p = paragraph(element, 0, "FlyTitle", True)
        elif text == "摘要":
            p = paragraph(element, 7, "FlyHeading2", True)
        elif re.match(r"^[1-5] ", text):
            p = paragraph(element, 2, "FlyHeading1", True)
            replace_text(p, "一二三四五"[int(text[0])-1] + "、" + text[2:])
        elif text == "参考文献":
            p = paragraph(element, 143, keep_next=True)
        elif text.startswith("["):
            p = paragraph(element, 144)
            set_prop(p.find(q("w:pPr")), "w:keepLines", val=1)
        elif index in [18, 20, 24]:
            p = paragraph(element, 76 if index == 20 else 84, keep_next=index == 20)
            pp = p.find(q("w:pPr"))
            for ind in pp.findall(q("w:ind")):
                pp.remove(ind)
            set_prop(pp, "w:keepLines", val=1)
        elif drawing is not None:
            p = paragraph(element, 82, keep_next=True)
            for blip in p.findall(".//a:blip", NS):
                blip.set(q("r:embed"), image_mapping[blip.get(q("r:embed"))])
            extent = p.find(".//wp:extent", NS)
            old_width = int(extent.get("cx"))
            target_width = round(14.65 * 360000)
            scale = target_width / old_width
            for size in p.xpath(".//wp:extent | .//a:xfrm/a:ext", namespaces=NS):
                size.set("cx", str(round(int(size.get("cx")) * scale)))
                size.set("cy", str(round(int(size.get("cy")) * scale)))
        elif math is not None:
            p = paragraph(element, 9)
            pp = p.find(q("w:pPr"))
            for ind in pp.findall(q("w:ind")):
                pp.remove(ind)
            set_prop(pp, "w:jc", val="center")
        else:
            p = paragraph(element, 9)
            if index == 27:
                set_prop(p.find(q("w:pPr")), "w:keepLines", val=1)
            if text.startswith("关键词"):
                pp = p.find(q("w:pPr"))
                for ind in pp.findall(q("w:ind")):
                    pp.remove(ind)
        body.append(p)
        if index == 0:
            author = paragraph(patterns[1], 1)
            body.append(author)
    body.append(section)

    parts["word/document.xml"] = xml_bytes(document)
    parts["word/styles.xml"] = xml_bytes(styles)
    parts["word/_rels/document.xml.rels"] = xml_bytes(relationships)
    core = etree.fromstring(parts["docProps/core.xml"])
    for name, value in [("dc:title", title), ("dc:creator", "尹一清")]:
        item = core.find(q(name))
        if item is None:
            item = etree.SubElement(core, q(name))
        item.text = value
    parts["docProps/core.xml"] = xml_bytes(core)
    # All content-bearing strings must remain, apart from documented numbering.
    expected = [text_of(p) for p in source_paragraphs if text_of(p)]
    expected = ["一二三四五"[int(t[0])-1] + "、" + t[2:]
                if re.match(r"^[1-5] ", t) else t for t in expected]
    actual = [text_of(p) for p in body.findall(q("w:p")) if text_of(p)]
    actual.pop(1)  # Confirmed name/student ID slot from reference.
    assert actual == expected, "Unexpected scientific text change"
    source_math = source_document.xpath(".//m:t/text()", namespaces=NS)
    assert document.xpath(".//m:t/text()", namespaces=NS) == source_math
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    assert hashlib.sha256(args.reference.read_bytes()).hexdigest() == reference_hash
    assert hashlib.sha256(args.source.read_bytes()).hexdigest() == source_hash
    print(json.dumps({"output": str(args.output), "reference_sha256": reference_hash,
                      "source_sha256": source_hash, "science_text_preserved": True,
                      "equation_preserved": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
