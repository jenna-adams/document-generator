#!/usr/bin/env python3
"""
BOL (Bill of Lading) PDF Generator
------------------------------------
Usage:
    python generate_bol.py --json bol_data.json --output bol_output.pdf

    Or override the signature URL:
    python generate_bol.py --json bol_data.json --sig-url https://example.com/sig.png

Dependencies:
    pip install reportlab requests
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1B2A4A")
MID_BLUE    = colors.HexColor("#2E5090")
LIGHT_BLUE  = colors.HexColor("#D6E4F7")
ACCENT      = colors.HexColor("#E8A020")
LIGHT_GRAY  = colors.HexColor("#F4F5F7")
MID_GRAY    = colors.HexColor("#CBD0D8")
TEXT_DARK   = colors.HexColor("#1A1A2E")
TEXT_LIGHT  = colors.HexColor("#5A6478")
WHITE       = colors.white
HAZMAT_RED  = colors.HexColor("#C0392B")
HAZMAT_BG   = colors.HexColor("#FDECEA")


# ── Styles ────────────────────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()

    def s(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "title": s("title",
                   fontName="Helvetica-Bold", fontSize=18,
                   textColor=WHITE, leading=22),
        "subtitle": s("subtitle",
                      fontName="Helvetica", fontSize=9,
                      textColor=LIGHT_BLUE, leading=13),
        "section_hdr": s("section_hdr",
                         fontName="Helvetica-Bold", fontSize=7.5,
                         textColor=MID_BLUE, leading=10,
                         spaceAfter=1),
        "field_label": s("field_label",
                         fontName="Helvetica", fontSize=7,
                         textColor=TEXT_LIGHT, leading=9),
        "field_value": s("field_value",
                         fontName="Helvetica-Bold", fontSize=8.5,
                         textColor=TEXT_DARK, leading=11),
        "small": s("small",
                   fontName="Helvetica", fontSize=7,
                   textColor=TEXT_LIGHT, leading=9),
        "body": s("body",
                  fontName="Helvetica", fontSize=8,
                  textColor=TEXT_DARK, leading=11),
        "hazmat": s("hazmat",
                    fontName="Helvetica-Bold", fontSize=7.5,
                    textColor=HAZMAT_RED, leading=10),
        "sig_name": s("sig_name",
                      fontName="Helvetica-Bold", fontSize=8.5,
                      textColor=TEXT_DARK, leading=11),
        "sig_title": s("sig_title",
                       fontName="Helvetica", fontSize=7.5,
                       textColor=TEXT_LIGHT, leading=10),
        "footer": s("footer",
                    fontName="Helvetica", fontSize=6.5,
                    textColor=TEXT_LIGHT, leading=9),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def download_image(url: str) -> str | None:
    """Download image from URL to a temp file; return path or None on failure."""
    if not url:
        return None
    try:
        suffix = ".png" if "svg" not in url.lower() else ".svg"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        headers = {"User-Agent": "BOL-Generator/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            with open(path, "wb") as f:
                f.write(resp.read())
        return path
    except Exception as e:
        print(f"  [warn] Could not download image from {url}: {e}", file=sys.stderr)
        return None


def lbl(text, styles, key="field_label"):
    return Paragraph(text, styles[key])


def val(text, styles, key="field_value"):
    return Paragraph(str(text) if text is not None else "—", styles[key])


def address_block(party: dict, styles) -> list:
    lines = [
        val(party.get("name", ""), styles),
        lbl(party.get("address", ""), styles, "body"),
        lbl(f"{party.get('city','')}, {party.get('state','')}  {party.get('zip','')}", styles, "body"),
        lbl(party.get("phone", ""), styles, "small"),
    ]
    return lines


def section_table(rows, col_widths, style_cmds=None):
    base = [
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("TEXTCOLOR",   (0, 0), (-1, -1), TEXT_DARK),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",        (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]
    if style_cmds:
        base.extend(style_cmds)
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle(base))
    return t


def two_col_info(left_pairs, right_pairs, styles, page_width):
    """Render two columns of label/value pairs side by side."""
    col_w = (page_width - 0.5 * inch) / 2

    def cell_block(pairs):
        rows = []
        for label, value in pairs:
            rows.append([lbl(label, styles), val(value, styles)])
        t = Table(rows, colWidths=[col_w * 0.42, col_w * 0.58])
        t.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t

    outer = Table(
        [[cell_block(left_pairs), cell_block(right_pairs)]],
        colWidths=[col_w, col_w],
    )
    outer.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return outer


# ── Main builder ──────────────────────────────────────────────────────────────
def generate_bol(data: dict, output_path: str, sig_url_override: str = None):
    styles = build_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
    )

    page_w = letter[0] - 1.2 * inch
    story  = []

    # ── 1. Header banner ──────────────────────────────────────────────────────
    bol_num  = data.get("bol_number", "")
    bol_date = data.get("date", "")
    pro_num  = data.get("pro_number", "")

    header_data = [[
        Paragraph("BILL OF LADING", styles["title"]),
        Table([
            [lbl("BOL NUMBER", {**styles, "field_label": ParagraphStyle("wl", fontName="Helvetica", fontSize=7, textColor=LIGHT_BLUE)},
                 "field_label"),
             lbl("DATE", {**styles, "field_label": ParagraphStyle("wl", fontName="Helvetica", fontSize=7, textColor=LIGHT_BLUE)},
                 "field_label"),
             lbl("PRO NUMBER", {**styles, "field_label": ParagraphStyle("wl", fontName="Helvetica", fontSize=7, textColor=LIGHT_BLUE)},
                 "field_label")],
            [Paragraph(bol_num,  ParagraphStyle("wv", fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT)),
             Paragraph(bol_date, ParagraphStyle("wv", fontName="Helvetica-Bold", fontSize=10, textColor=WHITE)),
             Paragraph(pro_num,  ParagraphStyle("wv", fontName="Helvetica-Bold", fontSize=10, textColor=WHITE))],
        ], colWidths=[1.6*inch, 1.2*inch, 1.6*inch],
        style=TableStyle([
            ("LEFTPADDING",  (0,0),(-1,-1),0),
            ("RIGHTPADDING", (0,0),(-1,-1),8),
            ("TOPPADDING",   (0,0),(-1,-1),1),
            ("BOTTOMPADDING",(0,0),(-1,-1),1),
        ])),
    ]]

    header_table = Table(header_data, colWidths=[page_w * 0.45, page_w * 0.55])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), DARK_BLUE),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LINEBELOW",    (0, 0), (-1, 0),  2, ACCENT),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # ── 2. Shipper / Consignee / Carrier ──────────────────────────────────────
    story.append(lbl("▸  PARTIES", styles, "section_hdr"))

    shipper    = data.get("shipper",   {})
    consignee  = data.get("consignee", {})
    carrier    = data.get("carrier",   {})
    billing    = data.get("billing",   {})

    def party_cell(title, party):
        inner = [[Paragraph(title, ParagraphStyle("ph", fontName="Helvetica-Bold",
                                                   fontSize=7.5, textColor=WHITE))]]
        for item in address_block(party, styles):
            inner.append([item])
        t = Table(inner, colWidths=[(page_w / 3) - 8])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), MID_BLUE),
            ("BACKGROUND",   (0, 1), (-1, -1), WHITE),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("BOX",          (0, 0), (-1, -1), 0.5, MID_GRAY),
        ]))
        return t

    carrier_rows = [
        [Paragraph("CARRIER", ParagraphStyle("ph", fontName="Helvetica-Bold",
                                              fontSize=7.5, textColor=WHITE))],
        [val(carrier.get("name",""), styles)],
        [lbl(f"SCAC: {carrier.get('scac','—')}", styles, "small")],
        [lbl(f"Trailer: {carrier.get('trailer_number','—')}", styles, "small")],
        [lbl(f"Seal: {carrier.get('seal_number','—')}", styles, "small")],
        [lbl(f"Billing: {billing.get('type','—')}", styles, "small")],
    ]
    carrier_cell = Table(carrier_rows, colWidths=[(page_w / 3) - 8])
    carrier_cell.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), MID_BLUE),
        ("BACKGROUND",   (0, 1), (-1, -1), WHITE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("BOX",          (0, 0), (-1, -1), 0.5, MID_GRAY),
    ]))

    parties_table = Table(
        [[party_cell("SHIPPER", shipper),
          party_cell("CONSIGNEE", consignee),
          carrier_cell]],
        colWidths=[page_w/3, page_w/3, page_w/3],
    )
    parties_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 8))

    # ── 3. Special instructions ───────────────────────────────────────────────
    special = data.get("special_instructions", "")
    if special:
        instr_table = Table(
            [[lbl("SPECIAL INSTRUCTIONS / REMARKS", styles, "section_hdr")],
             [Paragraph(special, styles["body"])]],
            colWidths=[page_w],
        )
        instr_table.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), LIGHT_BLUE),
            ("BACKGROUND",   (0, 1), (-1, -1), WHITE),
            ("BOX",          (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ]))
        story.append(instr_table)
        story.append(Spacer(1, 8))

    # ── 4. Commodity / line-items table ───────────────────────────────────────
    story.append(lbl("▸  COMMODITY DESCRIPTION", styles, "section_hdr"))

    col_widths_items = [
        page_w * 0.34,  # description
        page_w * 0.09,  # qty
        page_w * 0.09,  # unit
        page_w * 0.12,  # weight
        page_w * 0.09,  # class
        page_w * 0.13,  # nmfc
        page_w * 0.10,  # hazmat
        page_w * 0.04,  # filler
    ]

    header_row = [
        Paragraph("DESCRIPTION", ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("QTY",         ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("UNIT",        ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("WEIGHT (LBS)", ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("CLASS",       ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("NMFC",        ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("HAZMAT",      ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
        Paragraph("",            ParagraphStyle("th", fontName="Helvetica-Bold",
                                                  fontSize=7.5, textColor=WHITE)),
    ]

    item_rows = [header_row]
    items = data.get("items", [])
    for item in items:
        is_hazmat = item.get("hazmat", False)
        haz_para = Paragraph(
            "⬥ HAZMAT" if is_hazmat else "—",
            styles["hazmat"] if is_hazmat else styles["small"],
        )
        row = [
            Paragraph(item.get("description", ""), styles["body"]),
            Paragraph(str(item.get("quantity", "")), styles["body"]),
            Paragraph(item.get("unit", ""), styles["body"]),
            Paragraph(f"{item.get('weight_lbs', 0):,}", styles["body"]),
            Paragraph(item.get("class", ""), styles["body"]),
            Paragraph(item.get("nmfc", ""), styles["body"]),
            haz_para,
            Paragraph("", styles["body"]),
        ]
        item_rows.append(row)

    totals = data.get("totals", {})
    total_row = [
        Paragraph("TOTALS", ParagraphStyle("tot", fontName="Helvetica-Bold",
                                            fontSize=8, textColor=DARK_BLUE)),
        Paragraph(str(totals.get("total_pieces", "")),
                  ParagraphStyle("tot", fontName="Helvetica-Bold", fontSize=8, textColor=DARK_BLUE)),
        Paragraph("", styles["small"]),
        Paragraph(f"{totals.get('total_weight_lbs', 0):,}",
                  ParagraphStyle("tot", fontName="Helvetica-Bold", fontSize=8, textColor=DARK_BLUE)),
        Paragraph("", styles["small"]),
        Paragraph("", styles["small"]),
        Paragraph("", styles["small"]),
        Paragraph("", styles["small"]),
    ]
    item_rows.append(total_row)

    n_data = len(item_rows)
    items_table = Table(item_rows, colWidths=col_widths_items, repeatRows=1)
    items_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND",     (0, 0), (-1, 0), DARK_BLUE),
        ("TOPPADDING",     (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, 0), 5),
        # Data rows
        ("ROWBACKGROUNDS", (0, 1), (-1, n_data - 2), [WHITE, LIGHT_GRAY]),
        ("TOPPADDING",     (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 1), (-1, -1), 4),
        # Totals row
        ("BACKGROUND",     (0, n_data-1), (-1, n_data-1), LIGHT_BLUE),
        ("LINEABOVE",      (0, n_data-1), (-1, n_data-1), 1, MID_BLUE),
        # Grid
        ("GRID",           (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # ── 5. Signatures ─────────────────────────────────────────────────────────
    story.append(lbl("▸  SIGNATURES", styles, "section_hdr"))

    shipper_sig_data  = data.get("shipper_signature", {})
    driver_sig_data   = data.get("driver_signature", {})

    # Apply URL overrides if provided
    if sig_url_override:
        shipper_sig_data = {**shipper_sig_data, "image_url": sig_url_override}
        driver_sig_data  = {**driver_sig_data,  "image_url": sig_url_override}

    def sig_cell(label, sig_data, col_w):
        sig_url   = sig_data.get("image_url", "")
        sig_name  = sig_data.get("name", "")
        sig_title = sig_data.get("title", "")
        sig_path  = download_image(sig_url) if sig_url else None

        inner_rows = [
            [Paragraph(label, ParagraphStyle("sl", fontName="Helvetica-Bold",
                                              fontSize=7.5, textColor=WHITE))],
        ]

        if sig_path:
            try:
                img = Image(sig_path, width=col_w - 20, height=0.55 * inch,
                            kind="proportional")
                inner_rows.append([img])
            except Exception:
                inner_rows.append([Paragraph("[signature]", styles["small"])])
        else:
            inner_rows.append([Paragraph("________________________", styles["body"])])

        inner_rows.append([HRFlowable(width=col_w - 20, thickness=0.5, color=MID_GRAY)])
        inner_rows.append([Paragraph(sig_name,  styles["sig_name"])])
        inner_rows.append([Paragraph(sig_title, styles["sig_title"])])
        inner_rows.append([Paragraph(f"Date: {data.get('date','')}", styles["small"])])

        t = Table(inner_rows, colWidths=[col_w - 8])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), MID_BLUE),
            ("BACKGROUND",   (0, 1), (-1, -1), WHITE),
            ("BOX",          (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",        (0, 1), (-1, -2), "CENTER"),
        ]))
        return t

    sig_col_w = page_w / 2
    sig_table = Table(
        [[sig_cell("SHIPPER SIGNATURE", shipper_sig_data, sig_col_w),
          sig_cell("CARRIER / DRIVER SIGNATURE", driver_sig_data, sig_col_w)]],
        colWidths=[sig_col_w, sig_col_w],
    )
    sig_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 8))

    # ── 6. Legal footer ───────────────────────────────────────────────────────
    footer_text = (
        "This Bill of Lading is a contract of carriage between the shipper and the carrier. "
        "The carrier agrees to transport the goods described above subject to the terms and "
        "conditions of the applicable tariff and NMFC rules. Received in apparent good order "
        "except as noted. NOTE: Liability limitation may apply per 49 U.S.C. § 14706."
    )
    story.append(HRFlowable(width=page_w, thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(footer_text, styles["footer"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  BOL: {bol_num}",
        ParagraphStyle("gen", fontName="Helvetica", fontSize=6, textColor=MID_GRAY, leading=8),
    ))

    doc.build(story)
    print(f"✓  BOL PDF saved → {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate a Bill of Lading PDF")
    parser.add_argument("--json",    required=True,  help="Path to BOL JSON data file")
    parser.add_argument("--output",  default="bol_output.pdf", help="Output PDF path")
    parser.add_argument("--sig-url", default=None,
                        help="Override signature image URL for both signatures")
    args = parser.parse_args()

    with open(args.json, "r") as f:
        data = json.load(f)

    generate_bol(data, args.output, sig_url_override=args.sig_url)


if __name__ == "__main__":
    main()
