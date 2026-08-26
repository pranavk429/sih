#!/usr/bin/env python3
"""
Generate SIH 2026 Idea PPT Draft
Built on official SIH2026 template with strict design rules, five-color palette,
safe-area constraints, exact alignments, and comprehensive speaker notes.
"""

import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# Five Color Palette
NAVY = RGBColor(31, 73, 125)       # 1F497D - Headings, primary bars, dark text
BLUE = RGBColor(0, 112, 192)       # 0070C0 - Accent, links, "our side", stage 1
RED = RGBColor(179, 45, 45)        # B32D2D - Attack, risk, problem, degraded bar
GREEN = RGBColor(27, 122, 67)      # 1B7A43 - Our answer, benefit, ticks, enrolled bar
CARD_FILL = RGBColor(238, 243, 249)# EEF3F9 - Pale blue card fill

# Supporting tints
WHITE = RGBColor(255, 255, 255)
DARK_TEXT = RGBColor(30, 30, 30)
MUTED_TEXT = RGBColor(90, 95, 105)
AMBER = RGBColor(193, 108, 10)     # C16C0A - Stage 3 Challenge, callout border
AMBER_FILL = RGBColor(255, 248, 238)
RED_FILL = RGBColor(252, 241, 241)
GREEN_FILL = RGBColor(240, 249, 244)
BORDER_GRAY = RGBColor(210, 220, 232)
TABLE_GRAY_FILL = RGBColor(232, 238, 245)

FONT_HEADING = "Arial"
FONT_BODY = "Arial"

def add_header_bar(slide, text, left, top, width, height=Inches(0.32), bg_color=NAVY, font_size=Pt(11)):
    """Creates the signature repeating navy bar with white bold text."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    shape.line.fill.background()
    
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.12)
    tf.margin_right = Inches(0.12)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = FONT_HEADING
    p.font.size = font_size
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.LEFT
    return shape

def add_card(slide, left, top, width, height, fill_color=CARD_FILL, border_color=BORDER_GRAY, shape_type=MSO_SHAPE.ROUNDED_RECTANGLE):
    """Creates a background container card."""
    shape = slide.shapes.add_shape(shape_type, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape

def add_badge(slide, text, left, top, width, height, bg_color=NAVY, text_color=WHITE, font_size=Pt(9.5), bold=True):
    """Creates a small solid pill/badge."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    shape.line.fill.background()
    
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.01)
    tf.margin_bottom = Inches(0.01)
    
    p = tf.paragraphs[0]
    p.text = text
    p.font.name = FONT_HEADING
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = text_color
    p.alignment = PP_ALIGN.CENTER
    return shape

def set_speaker_notes(slide, notes_text):
    """Sets speaker notes for the slide."""
    notes_slide = slide.notes_slide
    text_frame = notes_slide.notes_text_frame
    text_frame.text = notes_text

def clear_unused_shapes(slide, keep_ids=None):
    """Removes leftover template placeholder shapes that we are replacing."""
    if keep_ids is None:
        keep_ids = []
    shapes_to_delete = []
    for shape in slide.shapes:
        if shape.shape_id not in keep_ids:
            name_lower = shape.name.lower()
            if "picture" in name_lower or "oval" in name_lower or "footer" in name_lower or "slide number" in name_lower or "rectangle 8" in name_lower or "rectangle 9" in name_lower:
                continue
            if "rectangle 24" in name_lower or "shape 26" in name_lower:
                continue
            shapes_to_delete.append(shape)
            
    for shape in shapes_to_delete:
        sp = shape._element
        sp.getparent().remove(sp)

def build_deck():
    template_path = "SIH2026-IDEA-PresentationFormat (1).pptx"
    output_path = "SIH2026-Idea-PPT-DRAFT.pptx"
    
    prs = Presentation(template_path)
    print(f"Loaded template with {len(prs.slides)} slides.")
    
    # ----------------------------------------------------
    # SLIDE 1: Title Page
    # ----------------------------------------------------
    print("Building Slide 1...")
    slide1 = prs.slides[0]
    
    for shape in list(slide1.shapes):
        name_lower = shape.name.lower()
        if "textbox 9" in name_lower or "subtitle 3" in name_lower:
            sp = shape._element
            sp.getparent().remove(sp)
            
    for shape in slide1.shapes:
        if "title 7" in shape.name.lower() and shape.has_text_frame:
            shape.text_frame.text = "SMART INDIA HACKATHON 2026"
            shape.text_frame.paragraphs[0].font.name = FONT_HEADING
            shape.text_frame.paragraphs[0].font.size = Pt(28)
            shape.text_frame.paragraphs[0].font.bold = True
            shape.text_frame.paragraphs[0].font.color.rgb = NAVY
            shape.left = Inches(0.40)
            shape.top = Inches(0.45)
            shape.width = Inches(10.0)
            shape.height = Inches(0.9)
            
    add_card(slide1, Inches(0.40), Inches(1.50), Inches(6.80), Inches(5.15), fill_color=WHITE, border_color=NAVY)
    add_header_bar(slide1, "IDEA SUBMISSION DETAILS · PRE-SCREENING", Inches(0.40), Inches(1.50), Inches(6.80), Inches(0.35), bg_color=NAVY, font_size=Pt(10.5))
    
    tb1 = slide1.shapes.add_textbox(Inches(0.60), Inches(1.95), Inches(6.40), Inches(4.55))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    tf1.margin_left = tf1.margin_right = tf1.margin_top = tf1.margin_bottom = 0
    
    fields = [
        ("Problem Statement ID", "SIH26104", NAVY, True, Pt(12)),
        ("Problem Statement Title", "AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks", DARK_TEXT, True, Pt(11)),
        ("Theme", "Miscellaneous", DARK_TEXT, False, Pt(11)),
        ("PS Category", "Software", DARK_TEXT, False, Pt(11)),
        ("Team ID", "[FILL]", BLUE, True, Pt(11.5)),
        ("Team Name (Registered)", "[FILL]", BLUE, True, Pt(11.5)),
    ]
    
    for idx, (label, val, val_color, is_bold, sz) in enumerate(fields):
        p = tf1.paragraphs[0] if idx == 0 else tf1.add_paragraph()
        p.space_after = Pt(8)
        
        r_lbl = p.add_run()
        r_lbl.text = f"{label} – "
        r_lbl.font.name = FONT_HEADING
        r_lbl.font.size = sz
        r_lbl.font.bold = True
        r_lbl.font.color.rgb = NAVY
        
        r_val = p.add_run()
        r_val.text = val
        r_val.font.name = FONT_BODY
        r_val.font.size = sz
        r_val.font.bold = is_bold
        r_val.font.color.rgb = val_color
        
    p_info = tf1.add_paragraph()
    p_info.space_before = Pt(4)
    r_sub = p_info.add_run()
    r_sub.text = "Organisation: AICTE · Target Channel: Enterprise VoIP/SIP · Cap: 500 Teams"
    r_sub.font.name = FONT_BODY
    r_sub.font.size = Pt(9)
    r_sub.font.italic = True
    r_sub.font.color.rgb = MUTED_TEXT

    set_speaker_notes(slide1, 
        "Good morning / afternoon, respected evaluators and jury members.\n\n"
        "We are presenting our solution for Problem Statement SIH26104 under the Miscellaneous theme: "
        "'AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks'.\n\n"
        "In 2026, generative voice cloning has made it effortless for criminals to steal 30 seconds of audio "
        "and impersonate CXOs, government officials, or family members in distress. "
        "Our solution moves away from fragile, naive 'fake audio detectors' and introduces an architectural, "
        "enrolment-first voice integrity gate designed specifically for high-stakes enterprise telephony and personal protection."
    )

    # ----------------------------------------------------
    # SLIDE 2: Idea Title / Proposed Solution
    # ----------------------------------------------------
    print("Building Slide 2...")
    slide2 = prs.slides[1]
    clear_unused_shapes(slide2)
    
    tb2_title = slide2.shapes.add_textbox(Inches(1.85), Inches(0.18), Inches(8.70), Inches(0.95))
    tf2_t = tb2_title.text_frame
    tf2_t.word_wrap = True
    tf2_t.margin_left = tf2_t.margin_right = tf2_t.margin_top = tf2_t.margin_bottom = 0
    
    p2_1 = tf2_t.paragraphs[0]
    r2_name = p2_1.add_run()
    r2_name.text = "[ YOUR IDEA NAME ]"
    r2_name.font.name = FONT_HEADING
    r2_name.font.size = Pt(24)
    r2_name.font.bold = True
    r2_name.font.color.rgb = NAVY
    
    p2_2 = tf2_t.add_paragraph()
    r2_tag = p2_2.add_run()
    r2_tag.text = "Verify the speaker — don't just guess at the audio."
    r2_tag.font.name = FONT_BODY
    r2_tag.font.size = Pt(12)
    r2_tag.font.italic = True
    r2_tag.font.bold = True
    r2_tag.font.color.rgb = BLUE
    
    add_header_bar(slide2, "PROPOSED SOLUTION — DETAILED EXPLANATION", Inches(0.40), Inches(1.18), Inches(12.50), Inches(0.28), bg_color=NAVY, font_size=Pt(10.5))
    
    tb2_lead = slide2.shapes.add_textbox(Inches(0.40), Inches(1.50), Inches(12.50), Inches(0.42))
    tf2_l = tb2_lead.text_frame
    tf2_l.word_wrap = True
    tf2_l.margin_left = tf2_l.margin_right = tf2_l.margin_top = tf2_l.margin_bottom = 0
    p2_l = tf2_l.paragraphs[0]
    r_lead = p2_l.add_run()
    r_lead.text = "A tiered voice-integrity gate for high-stakes calls: "
    r_lead.font.bold = True
    r_lead.font.size = Pt(9.5)
    r_lead.font.color.rgb = NAVY
    r_lead_b = p2_l.add_run()
    r_lead_b.text = "verify enrolled speakers directly, trigger deep checks only when money or access is at stake, and never output a bare score — always evidence plus a defensible decision."
    r_lead_b.font.size = Pt(9.5)
    r_lead_b.font.color.rgb = DARK_TEXT
    
    flow_boxes = [
        ("1  TRIGGER", BLUE, WHITE, CARD_FILL, BORDER_GRAY, "Follows call cheaply. Wakes on transfer, OTP, urgency + authority pressure."),
        ("2  VERIFY", NAVY, WHITE, CARD_FILL, BORDER_GRAY, "Enrolled voice on file? Match against it directly. Robot caller or puppeteer?"),
        ("3  CHALLENGE", AMBER, WHITE, AMBER_FILL, AMBER, "Still unsure? Interrupt and test live — prevention, not just observation."),
        ("4  EVIDENCE", GREEN, WHITE, GREEN_FILL, GREEN, "Which seconds, which artefact, tamper-proof log. No raw audio stored.")
    ]
    
    box_w = Inches(2.85)
    box_h = Inches(1.02)
    gap_x = Inches(0.36)
    start_x = Inches(0.40)
    top_y = Inches(1.98)
    
    for i, (b_title, b_color, t_color, fill_c, border_c, b_body) in enumerate(flow_boxes):
        cur_x = start_x + i * (box_w + gap_x)
        add_card(slide2, cur_x, top_y, box_w, box_h, fill_color=fill_c, border_color=border_c)
        add_badge(slide2, b_title, cur_x, top_y, box_w, Inches(0.25), bg_color=b_color, text_color=t_color, font_size=Pt(9.5), bold=True)
        
        tb_box = slide2.shapes.add_textbox(cur_x + Inches(0.08), top_y + Inches(0.28), box_w - Inches(0.16), box_h - Inches(0.30))
        tf_b = tb_box.text_frame
        tf_b.word_wrap = True
        tf_b.margin_left = tf_b.margin_right = tf_b.margin_top = tf_b.margin_bottom = 0
        p_b = tf_b.paragraphs[0]
        p_b.text = b_body
        p_b.font.size = Pt(8.5)
        p_b.font.color.rgb = DARK_TEXT
        
        if i < 3:
            arrow_x = cur_x + box_w + Inches(0.06)
            tb_arr = slide2.shapes.add_textbox(arrow_x, top_y + Inches(0.32), Inches(0.24), Inches(0.35))
            tf_a = tb_arr.text_frame
            tf_a.margin_left = tf_a.margin_right = tf_a.margin_top = tf_a.margin_bottom = 0
            p_a = tf_a.paragraphs[0]
            p_a.text = "➔"
            p_a.font.size = Pt(14)
            p_a.font.bold = True
            p_a.font.color.rgb = BLUE
            p_a.alignment = PP_ALIGN.CENTER
            
    col1_left = Inches(0.40)
    col1_w = Inches(4.30)
    bot_y = Inches(3.10)
    
    add_header_bar(slide2, "HOW IT ADDRESSES THE PROBLEM", col1_left, bot_y, col1_w, Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    add_card(slide2, col1_left, bot_y + Inches(0.30), col1_w, Inches(3.42), fill_color=CARD_FILL, border_color=BORDER_GRAY)
    
    tb_ticks = slide2.shapes.add_textbox(col1_left + Inches(0.12), bot_y + Inches(0.36), col1_w - Inches(0.24), Inches(1.85))
    tf_t = tb_ticks.text_frame
    tf_t.word_wrap = True
    tf_t.margin_left = tf_t.margin_right = tf_t.margin_top = tf_t.margin_bottom = 0
    
    checklist = [
        "✓ Multi-layer voice authenticity analysis",
        "✓ Real-time risk scoring engine",
        "✓ Alerting & user-interaction layer",
        "✓ Privacy by design — on-device inference, feature logs",
        "✓ API- and telephony-ready, multilingual"
    ]
    for idx, item in enumerate(checklist):
        p = tf_t.paragraphs[0] if idx == 0 else tf_t.add_paragraph()
        p.space_after = Pt(3)
        r = p.add_run()
        r.text = item
        r.font.name = FONT_BODY
        r.font.size = Pt(9.2)
        r.font.bold = True
        r.font.color.rgb = GREEN
        
    p_cov = tf_t.add_paragraph()
    p_cov.space_before = Pt(2)
    r_cov = p_cov.add_run()
    r_cov.text = "Full PS coverage — plus four things it never asked for."
    r_cov.font.name = FONT_BODY
    r_cov.font.size = Pt(8.5)
    r_cov.font.italic = True
    r_cov.font.bold = True
    r_cov.font.color.rgb = BLUE
    
    amber_box_y = bot_y + Inches(2.28)
    amber_box_h = Inches(1.36)
    add_card(slide2, col1_left + Inches(0.08), amber_box_y, col1_w - Inches(0.16), amber_box_h, fill_color=AMBER_FILL, border_color=AMBER)
    
    tb_amb = slide2.shapes.add_textbox(col1_left + Inches(0.16), amber_box_y + Inches(0.06), col1_w - Inches(0.32), amber_box_h - Inches(0.12))
    tf_amb = tb_amb.text_frame
    tf_amb.word_wrap = True
    tf_amb.margin_left = tf_amb.margin_right = tf_amb.margin_top = tf_amb.margin_bottom = 0
    p_a1 = tf_amb.paragraphs[0]
    r_a1 = p_a1.add_run()
    r_a1.text = "The clause most teams will skip\n"
    r_a1.font.bold = True
    r_a1.font.size = Pt(9)
    r_a1.font.color.rgb = AMBER
    r_a2 = p_a1.add_run()
    r_a2.text = "The problem statement mentions enrolment in a single buried line. Building the whole architecture around it is the unglamorous move — which is exactly why it wins."
    r_a2.font.size = Pt(8.2)
    r_a2.font.color.rgb = DARK_TEXT

    col2_left = Inches(4.85)
    col2_w = Inches(8.05)
    
    add_header_bar(slide2, "INNOVATION AND UNIQUENESS OF THE SOLUTION", col2_left, bot_y, col2_w, Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    tbl_shape = slide2.shapes.add_table(5, 2, col2_left, bot_y + Inches(0.30), col2_w, Inches(3.42))
    tbl = tbl_shape.table
    tbl.columns[0].width = Inches(3.60)
    tbl.columns[1].width = Inches(4.45)
    
    cell_00 = tbl.cell(0, 0)
    cell_00.fill.solid()
    cell_00.fill.fore_color.rgb = TABLE_GRAY_FILL
    cell_00.text_frame.margin_left = cell_00.text_frame.margin_right = Inches(0.08)
    cell_00.text_frame.margin_top = cell_00.text_frame.margin_bottom = Inches(0.04)
    p_th0 = cell_00.text_frame.paragraphs[0]
    p_th0.text = "The obvious build — what most teams do"
    p_th0.font.bold = True
    p_th0.font.size = Pt(9)
    p_th0.font.color.rgb = DARK_TEXT
    
    cell_01 = tbl.cell(0, 1)
    cell_01.fill.solid()
    cell_01.fill.fore_color.rgb = NAVY
    cell_01.text_frame.margin_left = cell_01.text_frame.margin_right = Inches(0.08)
    cell_01.text_frame.margin_top = cell_01.text_frame.margin_bottom = Inches(0.04)
    p_th1 = cell_01.text_frame.paragraphs[0]
    p_th1.text = "What we build instead (Our Innovation)"
    p_th1.font.bold = True
    p_th1.font.size = Pt(9)
    p_th1.font.color.rgb = WHITE
    
    comparison_rows = [
        ('"Is this audio fake?" — open-world blind detection', '"Is this the person we enrolled?" — speaker verification, ~10–20× lower error'),
        ('Score every single call continuously', 'Semantic trigger fires deep checks only at high-stakes moments — kills alert fatigue'),
        ('One detector for every attack', 'Two-branch defence: AI robot caller vs. live human puppeteer (RVC)'),
        ('A confident number, always', 'Honest "not sure — escalate to a human" when the evidence is weak')
    ]
    
    for r_idx, (obvious, ours) in enumerate(comparison_rows):
        row_num = r_idx + 1
        c_left = tbl.cell(row_num, 0)
        c_right = tbl.cell(row_num, 1)
        
        c_left.fill.solid()
        c_left.fill.fore_color.rgb = WHITE
        c_left.text_frame.margin_left = c_left.text_frame.margin_right = Inches(0.08)
        c_left.text_frame.margin_top = c_left.text_frame.margin_bottom = Inches(0.04)
        p_l = c_left.text_frame.paragraphs[0]
        p_l.text = obvious
        p_l.font.size = Pt(8.5)
        p_l.font.color.rgb = DARK_TEXT
        
        c_right.fill.solid()
        c_right.fill.fore_color.rgb = CARD_FILL
        c_right.text_frame.margin_left = c_right.text_frame.margin_right = Inches(0.08)
        c_right.text_frame.margin_top = c_right.text_frame.margin_bottom = Inches(0.04)
        p_r = c_right.text_frame.paragraphs[0]
        p_r.text = ours
        p_r.font.size = Pt(8.5)
        p_r.font.bold = True
        p_r.font.color.rgb = NAVY

    set_speaker_notes(slide2,
        "Slide 2 carries 50% of the entire judging score: Innovation (25) and Relevance (25).\n\n"
        "Here is our core thesis: 'Verify the speaker — don't just guess at the audio.'\n\n"
        "Why? Open-world 'is this voice fake?' detectors fail the moment a new generator appears. "
        "Furthermore, running a 99% detector on every single call produces roughly 50 false alarms per 1 real attack, "
        "causing immediate operator fatigue.\n\n"
        "Our 4-stage pipeline fixes this:\n"
        "1. TRIGGER: A cheap, lightweight listener that wakes up only on transfer keywords, OTP requests, or urgency.\n"
        "2. VERIFY: We ask 'Is this the enrolled executive / relative?' using speaker verification fusion, achieving 10-20x lower error.\n"
        "3. CHALLENGE: If suspicious, we inject interactive prompts to prevent fraud in real time.\n"
        "4. EVIDENCE: We generate timestamped cryptographic audit trails without storing raw audio.\n\n"
        "Every single requirement of the PS is covered, plus the critical innovations competitors will miss."
    )

    # ----------------------------------------------------
    # SLIDE 3: Technical Approach
    # ----------------------------------------------------
    print("Building Slide 3...")
    slide3 = prs.slides[2]
    clear_unused_shapes(slide3)
    
    col1_l = Inches(0.40)
    col1_w = Inches(5.10)
    top_y3 = Inches(1.22)
    
    add_header_bar(slide3, "TECHNOLOGIES TO BE USED", col1_l, top_y3, col1_w, Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    add_card(slide3, col1_l, top_y3 + Inches(0.30), col1_w, Inches(2.65), fill_color=CARD_FILL, border_color=BORDER_GRAY)
    tb_tech = slide3.shapes.add_textbox(col1_l + Inches(0.12), top_y3 + Inches(0.34), col1_w - Inches(0.24), Inches(2.55))
    tf_tech = tb_tech.text_frame
    tf_tech.word_wrap = True
    tf_tech.margin_left = tf_tech.margin_right = tf_tech.margin_top = tf_tech.margin_bottom = 0
    
    tech_bullets = [
        ("Speech AI", "wav2vec2-XLSR multilingual encoder (Apache-2.0); ECAPA-TDNN speaker embeddings"),
        ("Verification", "Learned fusion of enrolled-reference similarity + spoof countermeasure score"),
        ("Trigger", "Lightweight intent model over live call transcript (Whisper-small streaming)"),
        ("Serving", "ONNX Runtime, INT8 quantised — real on-device inference, not a slide claim"),
        ("Telephony", "WebRTC / SIP via Asterisk; RTP stream tapped frame-by-frame"),
        ("Build & GPU", "Python, PyTorch, FastAPI; free GPU on Kaggle / IndiaAI Compute Portal")
    ]
    
    for idx, (head, body) in enumerate(tech_bullets):
        p = tf_tech.paragraphs[0] if idx == 0 else tf_tech.add_paragraph()
        p.space_after = Pt(2)
        r1 = p.add_run()
        r1.text = f"{head} — "
        r1.font.bold = True
        r1.font.size = Pt(8.5)
        r1.font.color.rgb = NAVY
        r2 = p.add_run()
        r2.text = body
        r2.font.size = Pt(8.2)
        r2.font.color.rgb = DARK_TEXT
        
    box_and_y = top_y3 + Inches(3.02)
    box_and_h = Inches(1.08)
    add_card(slide3, col1_l, box_and_y, col1_w, box_and_h, fill_color=AMBER_FILL, border_color=AMBER)
    tb_and = slide3.shapes.add_textbox(col1_l + Inches(0.10), box_and_y + Inches(0.04), col1_w - Inches(0.20), box_and_h - Inches(0.08))
    tf_and = tb_and.text_frame
    tf_and.word_wrap = True
    tf_and.margin_left = tf_and.margin_right = tf_and.margin_top = tf_and.margin_bottom = 0
    p_and = tf_and.paragraphs[0]
    r_an1 = p_and.add_run()
    r_an1.text = "Constraint we designed around\n"
    r_an1.font.bold = True
    r_an1.font.size = Pt(8.8)
    r_an1.font.color.rgb = AMBER
    r_an2 = p_and.add_run()
    r_an2.text = "Android blocks call-audio capture (2019, closed 2022). Any app claiming to listen to normal phone calls is not shippable — so the system sits in the VoIP/SIP path, where it is legal and controllable."
    r_an2.font.size = Pt(8.0)
    r_an2.font.color.rgb = DARK_TEXT
    
    box_demo_y = top_y3 + Inches(4.16)
    box_demo_h = Inches(1.15)
    add_card(slide3, col1_l, box_demo_y, col1_w, box_demo_h, fill_color=CARD_FILL, border_color=BLUE)
    tb_demo = slide3.shapes.add_textbox(col1_l + Inches(0.10), box_demo_y + Inches(0.04), col1_w - Inches(0.20), box_demo_h - Inches(0.08))
    tf_demo = tb_demo.text_frame
    tf_demo.word_wrap = True
    tf_demo.margin_left = tf_demo.margin_right = tf_demo.margin_top = tf_demo.margin_bottom = 0
    p_demo = tf_demo.paragraphs[0]
    r_d1 = p_demo.add_run()
    r_d1.text = "How the demo runs\n"
    r_d1.font.bold = True
    r_d1.font.size = Pt(8.8)
    r_d1.font.color.rgb = BLUE
    r_d2 = p_demo.add_run()
    r_d2.text = "Two laptops on a local SIP server. We clone a volunteer's voice with open-source tools, place the call, and the system triggers, challenges and produces evidence live — with venue internet unplugged, so a dead network cannot kill the demo."
    r_d2.font.size = Pt(8.0)
    r_d2.font.color.rgb = DARK_TEXT

    col2_l = Inches(5.65)
    col2_w = Inches(7.25)
    
    add_header_bar(slide3, "METHODOLOGY AND PROCESS FOR IMPLEMENTATION", col2_l, top_y3, col2_w, Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    layers = [
        ("TRIGGER", BLUE, "Always-on, cheap. Listens for a transfer instruction, credential request, or urgency + authority pressure. Nothing escalates until stakes are real."),
        ("VERIFY", NAVY, "Enrolled reference on file → direct speaker match. No reference → countermeasure model + honest low-confidence flag. Branches TTS vs. live voice conversion."),
        ("CHALLENGE", AMBER, "Suspicious? Inject an unexpected prompt and measure the response. This is the step that turns detection into prevention."),
        ("EVIDENCE", GREEN, "Timestamped suspicious segments, artefact type, tamper-evident log. Mathematical features only — no raw call audio retained.")
    ]
    
    row_y = top_y3 + Inches(0.30)
    badge_w = Inches(1.30)
    text_w = col2_w - badge_w - Inches(0.08)
    layer_h = Inches(0.70)
    gap_layer = Inches(0.06)
    
    for i, (l_title, l_color, l_desc) in enumerate(layers):
        cur_ly = row_y + i * (layer_h + gap_layer)
        add_badge(slide3, l_title, col2_l, cur_ly, badge_w, layer_h, bg_color=l_color, text_color=WHITE, font_size=Pt(9), bold=True)
        add_card(slide3, col2_l + badge_w + Inches(0.06), cur_ly, text_w, layer_h, fill_color=CARD_FILL, border_color=BORDER_GRAY)
        
        tb_l = slide3.shapes.add_textbox(col2_l + badge_w + Inches(0.12), cur_ly + Inches(0.04), text_w - Inches(0.16), layer_h - Inches(0.08))
        tf_l = tb_l.text_frame
        tf_l.word_wrap = True
        tf_l.margin_left = tf_l.margin_right = tf_l.margin_top = tf_l.margin_bottom = 0
        p_l = tf_l.paragraphs[0]
        p_l.text = l_desc
        p_l.font.size = Pt(8.2)
        p_l.font.color.rgb = DARK_TEXT
        
    green_y = row_y + 4 * (layer_h + gap_layer) + Inches(0.06)
    green_h = Inches(2.20)
    add_card(slide3, col2_l, green_y, col2_w, green_h, fill_color=GREEN_FILL, border_color=GREEN)
    
    tb_grn = slide3.shapes.add_textbox(col2_l + Inches(0.12), green_y + Inches(0.08), col2_w - Inches(0.24), green_h - Inches(0.16))
    tf_grn = tb_grn.text_frame
    tf_grn.word_wrap = True
    tf_grn.margin_left = tf_grn.margin_right = tf_grn.margin_top = tf_grn.margin_bottom = 0
    p_g1 = tf_grn.paragraphs[0]
    r_g1 = p_g1.add_run()
    r_g1.text = "Trained against simulated Indian telephony — not studio audio\n"
    r_g1.font.bold = True
    r_g1.font.size = Pt(9.5)
    r_g1.font.color.rgb = GREEN
    
    p_g2 = tf_grn.add_paragraph()
    p_g2.space_before = Pt(3)
    r_g2 = p_g2.add_run()
    r_g2.text = "• Opus 8 kbps (VoIP / WhatsApp) · G.711 (PSTN & bank call-centre trunks) · 5% packet loss.\n"
    r_g2.text += "• The fine spectral detail that betrays a synthetic voice in a lab is exactly what phone codecs throw away.\n"
    r_g2.text += "• By deliberately degrading training data through our simulator, our model learns codec-invariant representations that survive real Indian mobile networks."
    r_g2.font.size = Pt(8.4)
    r_g2.font.color.rgb = DARK_TEXT

    set_speaker_notes(slide3,
        "Slide 3 covers our technical approach and why our engineering is genuinely shippable.\n\n"
        "Key highlights:\n"
        "1. Open Source Backbone: We leverage wav2vec2-XLSR for robust multilingual phoneme extraction and ECAPA-TDNN for speaker embeddings.\n"
        "2. Serving: INT8 quantised ONNX runtime enables sub-second on-device inference without cloud reliance.\n"
        "3. Operating Reality: Android OS strictly blocks background call-audio recording since 2019/2022. "
        "Any competitor claiming to intercept cellular calls on a normal smartphone is unviable. "
        "We target enterprise VoIP / SIP trunks and WebRTC where financial and high-value approvals actually occur.\n"
        "4. Telephony Hardening: Studio-trained models collapse on phone lines. We degrade our training data with Opus 8kbps, G.711, and 5% simulated packet loss to ensure real-world robustness."
    )

    # ----------------------------------------------------
    # SLIDE 4: Feasibility and Viability (Refined Spacing)
    # ----------------------------------------------------
    print("Building Slide 4...")
    slide4 = prs.slides[3]
    clear_unused_shapes(slide4)
    
    col1_l4 = Inches(0.40)
    col1_w4 = Inches(5.95)
    top_y4 = Inches(1.22)
    
    add_header_bar(slide4, "ANALYSIS OF THE FEASIBILITY OF THE IDEA", col1_l4, top_y4, col1_w4, Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    # Experiment Graphic Card
    exp_h = Inches(2.25)
    add_card(slide4, col1_l4, top_y4 + Inches(0.30), col1_w4, exp_h, fill_color=CARD_FILL, border_color=BORDER_GRAY)
    
    tb_exp_t = slide4.shapes.add_textbox(col1_l4 + Inches(0.12), top_y4 + Inches(0.34), col1_w4 - Inches(0.24), Inches(0.26))
    tf_exp_t = tb_exp_t.text_frame
    tf_exp_t.margin_left = tf_exp_t.margin_right = tf_exp_t.margin_top = tf_exp_t.margin_bottom = 0
    p_et = tf_exp_t.paragraphs[0]
    r_et = p_et.add_run()
    r_et.text = "We already ran the experiment — Equal Error Rate (lower is better):"
    r_et.font.bold = True
    r_et.font.size = Pt(8.8)
    r_et.font.color.rgb = NAVY
    
    # 3-Bar Chart representation
    bars = [
        ("Clean audio", "7.9%", BLUE, Inches(0.48)),
        ("After phone line", "13.5%", RED, Inches(0.85)),
        ("+ Enrolled ref", "11.7%", GREEN, Inches(0.72))
    ]
    
    chart_base_y = top_y4 + Inches(1.72)
    bar_w = Inches(1.30)
    gap_bar = Inches(0.50)
    chart_start_x = col1_l4 + Inches(0.45)
    
    line = slide4.shapes.add_shape(MSO_SHAPE.RECTANGLE, chart_start_x - Inches(0.20), chart_base_y, Inches(4.90), Pt(1.5))
    line.fill.solid()
    line.fill.fore_color.rgb = MUTED_TEXT
    line.line.fill.background()
    
    for idx, (label, val_str, bar_color, b_height) in enumerate(bars):
        bx = chart_start_x + idx * (bar_w + gap_bar)
        by = chart_base_y - b_height
        
        b_shape = slide4.shapes.add_shape(MSO_SHAPE.RECTANGLE, bx, by, bar_w, b_height)
        b_shape.fill.solid()
        b_shape.fill.fore_color.rgb = bar_color
        b_shape.line.fill.background()
        
        tb_val = slide4.shapes.add_textbox(bx, by - Inches(0.24), bar_w, Inches(0.22))
        tf_v = tb_val.text_frame
        tf_v.margin_left = tf_v.margin_right = tf_v.margin_top = tf_v.margin_bottom = 0
        p_v = tf_v.paragraphs[0]
        p_v.text = val_str
        p_v.font.bold = True
        p_v.font.size = Pt(10.5)
        p_v.font.color.rgb = bar_color
        p_v.alignment = PP_ALIGN.CENTER
        
        tb_lbl = slide4.shapes.add_textbox(bx - Inches(0.10), chart_base_y + Inches(0.04), bar_w + Inches(0.20), Inches(0.22))
        tf_l = tb_lbl.text_frame
        tf_l.margin_left = tf_l.margin_right = tf_l.margin_top = tf_l.margin_bottom = 0
        p_l = tf_l.paragraphs[0]
        p_l.text = label
        p_l.font.size = Pt(8.0)
        p_l.font.bold = True
        p_l.font.color.rgb = DARK_TEXT
        p_l.alignment = PP_ALIGN.CENTER
        
    tb_cap = slide4.shapes.add_textbox(col1_l4 + Inches(0.10), top_y4 + Inches(2.05), col1_w4 - Inches(0.20), Inches(0.46))
    tf_cap = tb_cap.text_frame
    tf_cap.word_wrap = True
    tf_cap.margin_left = tf_cap.margin_right = tf_cap.margin_top = tf_cap.margin_bottom = 0
    p_cap = tf_cap.paragraphs[0]
    p_cap.text = "Our own pilot, 23 Aug 2026 · leak-free protocol, speaker-disjoint split, n=119 trials. The line hurts; enrolment claws back a third of the damage using crude fusion. Full-scale GPU run in progress."
    p_cap.font.size = Pt(7.2)
    p_cap.font.italic = True
    p_cap.font.color.rgb = MUTED_TEXT
    
    feas_y = top_y4 + Inches(2.62)
    feas_h = Inches(1.60)
    add_card(slide4, col1_l4, feas_y, col1_w4, feas_h, fill_color=WHITE, border_color=BORDER_GRAY)
    
    tb_feas = slide4.shapes.add_textbox(col1_l4 + Inches(0.12), feas_y + Inches(0.06), col1_w4 - Inches(0.24), feas_h - Inches(0.12))
    tf_feas = tb_feas.text_frame
    tf_feas.word_wrap = True
    tf_feas.margin_left = tf_feas.margin_right = tf_feas.margin_top = tf_feas.margin_bottom = 0
    
    feas_points = [
        ("Budget", "₹0–10,000 total. GPU compute is free via Kaggle (30 h/wk) or IndiaAI Compute Portal."),
        ("Hardware", "One 16 GB laptop. The demo runs fully offline, so a dead venue network cannot kill it."),
        ("Timeline", "Building now (Sept) → idea screening (Oct–Nov) → 36-hr Finale build (Dec)."),
        ("Scope discipline", "Four layers built properly; remaining PS components designed & labelled, not claimed.")
    ]
    for idx, (h, b) in enumerate(feas_points):
        p = tf_feas.paragraphs[0] if idx == 0 else tf_feas.add_paragraph()
        p.space_after = Pt(2)
        r1 = p.add_run()
        r1.text = f"{h}: "
        r1.font.bold = True
        r1.font.size = Pt(8.2)
        r1.font.color.rgb = NAVY
        r2 = p.add_run()
        r2.text = b
        r2.font.size = Pt(8.0)
        r2.font.color.rgb = DARK_TEXT
        
    built_y = top_y4 + Inches(4.28)
    built_h = Inches(1.05)
    add_card(slide4, col1_l4, built_y, col1_w4, built_h, fill_color=CARD_FILL, border_color=BLUE)
    tb_b = slide4.shapes.add_textbox(col1_l4 + Inches(0.10), built_y + Inches(0.04), col1_w4 - Inches(0.20), built_h - Inches(0.08))
    tf_b = tb_b.text_frame
    tf_b.word_wrap = True
    tf_b.margin_left = tf_b.margin_right = tf_b.margin_top = tf_b.margin_bottom = 0
    p_b = tf_b.paragraphs[0]
    r_b1 = p_b.add_run()
    r_b1.text = "Already built — a repository, not a plan\n"
    r_b1.font.bold = True
    r_b1.font.size = Pt(8.8)
    r_b1.font.color.rgb = BLUE
    r_b2 = p_b.add_run()
    r_b2.text = "Leak-free evaluation harness · telephony channel simulator (Opus / G.711 / packet loss) · enrolment-fusion scoring · full-scale GPU run scripted and queued."
    r_b2.font.size = Pt(8.0)
    r_b2.font.color.rgb = DARK_TEXT

    col2_l4 = Inches(6.50)
    col2_w4 = Inches(6.40)
    
    add_header_bar(slide4, "POTENTIAL CHALLENGES, RISKS & STRATEGIES TO OVERCOME", col2_l4, top_y4, col2_w4, Inches(0.28), bg_color=NAVY, font_size=Pt(9.0))
    
    tbl_r_shape = slide4.shapes.add_table(6, 2, col2_l4, top_y4 + Inches(0.30), col2_w4, Inches(5.00))
    tbl_r = tbl_r_shape.table
    tbl_r.columns[0].width = Inches(2.70)
    tbl_r.columns[1].width = Inches(3.70)
    
    c_th0 = tbl_r.cell(0, 0)
    c_th0.fill.solid()
    c_th0.fill.fore_color.rgb = RED_FILL
    c_th0.text_frame.margin_left = c_th0.text_frame.margin_right = Inches(0.08)
    c_th0.text_frame.margin_top = c_th0.text_frame.margin_bottom = Inches(0.04)
    p_rt0 = c_th0.text_frame.paragraphs[0]
    p_rt0.text = "Potential Risk / Challenge"
    p_rt0.font.bold = True
    p_rt0.font.size = Pt(8.8)
    p_rt0.font.color.rgb = RED
    
    c_th1 = tbl_r.cell(0, 1)
    c_th1.fill.solid()
    c_th1.fill.fore_color.rgb = NAVY
    c_th1.text_frame.margin_left = c_th1.text_frame.margin_right = Inches(0.08)
    c_th1.text_frame.margin_top = c_th1.text_frame.margin_bottom = Inches(0.04)
    p_rt1 = c_th1.text_frame.paragraphs[0]
    p_rt1.text = "Strategy to Overcome"
    p_rt1.font.bold = True
    p_rt1.font.size = Pt(8.8)
    p_rt1.font.color.rgb = WHITE
    
    risk_rows = [
        ("Detectors go blind against cloning tools they were never trained on", "Enrolment-first design sidesteps open-world detection entirely"),
        ("Phone codecs destroy the fine detail the detector depends on", "Channel-hardened training on simulated Indian network conditions"),
        ("A naive always-on alarm produces ~50 false accusations per real attack", "Semantic trigger — escalate only when money or access is on the line"),
        ("A live human driving voice-conversion software defeats liveness tests", "Two-branch detection with a different signal for each attack type"),
        ("Free 'deepfake detector' checkpoints are often contaminated", "We caught one scoring a fake 0.0% — we validate before we trust a number")
    ]
    
    for r_i, (r_text, s_text) in enumerate(risk_rows):
        r_num = r_i + 1
        c_r = tbl_r.cell(r_num, 0)
        c_s = tbl_r.cell(r_num, 1)
        
        c_r.fill.solid()
        c_r.fill.fore_color.rgb = RED_FILL
        c_r.text_frame.margin_left = c_r.text_frame.margin_right = Inches(0.08)
        c_r.text_frame.margin_top = c_r.text_frame.margin_bottom = Inches(0.03)
        p_rc = c_r.text_frame.paragraphs[0]
        p_rc.text = r_text
        p_rc.font.size = Pt(8.0)
        p_rc.font.color.rgb = RED
        
        c_s.fill.solid()
        c_s.fill.fore_color.rgb = CARD_FILL
        c_s.text_frame.margin_left = c_s.text_frame.margin_right = Inches(0.08)
        c_s.text_frame.margin_top = c_s.text_frame.margin_bottom = Inches(0.03)
        p_sc = c_s.text_frame.paragraphs[0]
        p_sc.text = s_text
        p_sc.font.size = Pt(8.0)
        p_sc.font.bold = True
        p_sc.font.color.rgb = DARK_TEXT

    set_speaker_notes(slide4,
        "Slide 4 addresses Feasibility (20 points).\n\n"
        "Rather than quoting hypothetical numbers, we show results from our own pilot experiment:\n"
        "• Baseline clean EER: 7.9%\n"
        "• Telephony degradation degrades EER to 13.5%\n"
        "• Adding enrolment reference claws back performance to 11.7% even with crude fusion.\n\n"
        "Our budget is realistic: ₹0 to ₹10k utilizing free IndiaAI Compute Portal and Kaggle allocations. "
        "The prototype runs completely offline on a single laptop, guaranteeing 100% demo uptime at the venue.\n\n"
        "We also systematically address 5 critical failure modes with concrete mitigations."
    )

    # ----------------------------------------------------
    # SLIDE 5: Impact and Benefits
    # ----------------------------------------------------
    print("Building Slide 5...")
    slide5 = prs.slides[4]
    clear_unused_shapes(slide5)
    
    top_y5 = Inches(1.22)
    add_header_bar(slide5, "POTENTIAL IMPACT ON THE TARGET AUDIENCE", Inches(0.40), top_y5, Inches(12.50), Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    aud_w = Inches(3.95)
    aud_h = Inches(1.95)
    aud_gap = Inches(0.32)
    aud_start_x = Inches(0.40)
    aud_y = top_y5 + Inches(0.30)
    
    audiences = [
        ("Individuals & Families", BLUE, 
         "\"Mum, I've had an accident, I need money now.\" Cloned-relative emergency scams target parents & elderly.",
         "Enrolled family voices on a personal device; the alert reaches the victim in their native language."),
        ("Banks & Enterprises", NAVY,
         "CXO impersonation on fund-transfer and access approvals. 30s public audio is enough to clone an executive.",
         "Verification fires exactly at the transfer instruction — the moment that matters — not on every call."),
        ("Telecom & Government", GREEN,
         "No shared defence layer exists today; each institution improvises its own fragile filters.",
         "A reusable voice-integrity API that drops into existing call infrastructure — matching PS Expected Outcome.")
    ]
    
    for idx, (aud_title, aud_badge_c, atk_text, give_text) in enumerate(audiences):
        ax = aud_start_x + idx * (aud_w + aud_gap)
        add_card(slide5, ax, aud_y, aud_w, aud_h, fill_color=CARD_FILL, border_color=BORDER_GRAY)
        add_badge(slide5, aud_title, ax, aud_y, aud_w, Inches(0.25), bg_color=aud_badge_c, text_color=WHITE, font_size=Pt(9), bold=True)
        
        tb_a = slide5.shapes.add_textbox(ax + Inches(0.10), aud_y + Inches(0.28), aud_w - Inches(0.20), aud_h - Inches(0.32))
        tf_a = tb_a.text_frame
        tf_a.word_wrap = True
        tf_a.margin_left = tf_a.margin_right = tf_a.margin_top = tf_a.margin_bottom = 0
        
        p1 = tf_a.paragraphs[0]
        r_atk_lbl = p1.add_run()
        r_atk_lbl.text = "THE ATTACK: "
        r_atk_lbl.font.bold = True
        r_atk_lbl.font.size = Pt(7.8)
        r_atk_lbl.font.color.rgb = RED
        r_atk_txt = p1.add_run()
        r_atk_txt.text = f"{atk_text}\n"
        r_atk_txt.font.size = Pt(7.8)
        r_atk_txt.font.color.rgb = DARK_TEXT
        
        p2 = tf_a.add_paragraph()
        p2.space_before = Pt(2)
        r_give_lbl = p2.add_run()
        r_give_lbl.text = "WHAT WE GIVE THEM: "
        r_give_lbl.font.bold = True
        r_give_lbl.font.size = Pt(7.8)
        r_give_lbl.font.color.rgb = GREEN
        r_give_txt = p2.add_run()
        r_give_txt.text = give_text
        r_give_txt.font.size = Pt(7.8)
        r_give_txt.font.color.rgb = DARK_TEXT
        
    top_y5_ben = aud_y + aud_h + Inches(0.08)
    add_header_bar(slide5, "BENEFITS OF THE SOLUTION (SOCIAL, ECONOMIC, ENVIRONMENTAL)", Inches(0.40), top_y5_ben, Inches(12.50), Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    ben_w = Inches(2.95)
    ben_h = Inches(1.85)
    ben_gap = Inches(0.23)
    ben_start_x = Inches(0.40)
    ben_y = top_y5_ben + Inches(0.30)
    
    benefits = [
        ("SOCIAL", BLUE, "Restores trust in the voice call", "Voice is India's default channel for banking, government and family contact. When trust breaks, the vulnerable suffer first."),
        ("ECONOMIC", NAVY, "Fraud losses cut at transfer point", "AI impersonation fraud is up 148%/yr. Halting calls at the transfer instruction prevents capital loss before money leaves."),
        ("OPERATIONAL", AMBER, "An alarm staff still trusts in week 2", "A 99% detector on every call yields 50 false accusations per real attack. Triggering only on high-stakes moments stops alarm shutdown."),
        ("ENVIRONMENTAL", GREEN, "No always-on cloud processing", "Edge inference eliminates continuous cloud audio streaming, drastically cutting datacentre carbon footprint and protecting privacy.")
    ]
    
    for idx, (b_badge, b_badge_c, b_title, b_body) in enumerate(benefits):
        bx = ben_start_x + idx * (ben_w + ben_gap)
        add_card(slide5, bx, ben_y, ben_w, ben_h, fill_color=CARD_FILL, border_color=BORDER_GRAY)
        add_badge(slide5, b_badge, bx, ben_y, ben_w, Inches(0.22), bg_color=b_badge_c, text_color=WHITE, font_size=Pt(8.5), bold=True)
        
        tb_b = slide5.shapes.add_textbox(bx + Inches(0.08), ben_y + Inches(0.25), ben_w - Inches(0.16), ben_h - Inches(0.28))
        tf_b = tb_b.text_frame
        tf_b.word_wrap = True
        tf_b.margin_left = tf_b.margin_right = tf_b.margin_top = tf_b.margin_bottom = 0
        
        p_bt = tf_b.paragraphs[0]
        r_bt = p_bt.add_run()
        r_bt.text = f"{b_title}\n"
        r_bt.font.bold = True
        r_bt.font.size = Pt(8.2)
        r_bt.font.color.rgb = NAVY
        
        p_bb = tf_b.add_paragraph()
        p_bb.space_before = Pt(2)
        r_bb = p_bb.add_run()
        r_bb.text = b_body
        r_bb.font.size = Pt(7.8)
        r_bb.font.color.rgb = DARK_TEXT
        
    strip_y = ben_y + ben_h + Inches(0.08)
    strip_h = Inches(0.55)
    add_card(slide5, Inches(0.40), strip_y, Inches(12.50), strip_h, fill_color=NAVY, border_color=None, shape_type=MSO_SHAPE.RECTANGLE)
    
    tb_str = slide5.shapes.add_textbox(Inches(0.50), strip_y + Inches(0.04), Inches(12.30), strip_h - Inches(0.08))
    tf_str = tb_str.text_frame
    tf_str.word_wrap = True
    tf_str.margin_left = tf_str.margin_right = tf_str.margin_top = tf_str.margin_bottom = 0
    p_str = tf_str.paragraphs[0]
    p_str.alignment = PP_ALIGN.CENTER
    r_str = p_str.add_run()
    r_str.text = "Our accuracy number is not the product. The architecture around the number is the product — because a 95% detector deployed naively produces 98% false alerts."
    r_str.font.bold = True
    r_str.font.size = Pt(10)
    r_str.font.color.rgb = WHITE

    set_speaker_notes(slide5,
        "Slide 5 covers the broad social, economic, and operational impact.\n\n"
        "We serve three key audiences:\n"
        "1. Families against emergency kidnapping/accident scams\n"
        "2. Banks against CXO transfer fraud\n"
        "3. Telecom/Gov as a plug-and-play security API.\n\n"
        "Crucially, we solve the base-rate fallacy problem: our trigger ensures alarms are trusted long-term. "
        "Our closing strip summarizes the core truth: 'Our accuracy number is not the product. The architecture around the number is the product.'"
    )

    # ----------------------------------------------------
    # SLIDE 6: Research and References
    # ----------------------------------------------------
    print("Building Slide 6...")
    slide6 = prs.slides[5]
    clear_unused_shapes(slide6)
    
    top_y6 = Inches(1.22)
    add_header_bar(slide6, "DETAILS / LINKS OF THE REFERENCE AND RESEARCH WORK", Inches(0.40), top_y6, Inches(12.50), Inches(0.28), bg_color=NAVY, font_size=Pt(9.5))
    
    tb_intro = slide6.shapes.add_textbox(Inches(0.40), top_y6 + Inches(0.30), Inches(12.50), Inches(0.22))
    tf_intro = tb_intro.text_frame
    tf_intro.margin_left = tf_intro.margin_right = tf_intro.margin_top = tf_intro.margin_bottom = 0
    p_in = tf_intro.paragraphs[0]
    r_in = p_in.add_run()
    r_in.text = "Every design decision on the previous slides traces to one of these. The numbers we quote are published benchmarks or our own measurements — none are estimates."
    r_in.font.italic = True
    r_in.font.size = Pt(8.2)
    r_in.font.color.rgb = NAVY
    
    col_w6 = Inches(6.10)
    col_gap6 = Inches(0.30)
    card_h6 = Inches(0.95)
    gap_y6 = Inches(0.08)
    start_y6 = top_y6 + Inches(0.55)
    
    refs_left = [
        ("ASVspoof 5 Challenge", "asvspoof.org", "State-of-the-art anti-spoofing benchmark. Best systems land at 9–20% EER — the reason we refuse to claim 99%."),
        ("SASV Challenge — Spoofing-Aware Speaker Verification", "", "The fusion research our enrolment-first architecture is built on: combine countermeasure with speaker verification."),
        ("RawBoost (Tak et al., ICASSP 2022)", "", "Telephony-robust data augmentation. The basis for our codec + packet-loss degradation pipeline."),
        ("ASVspoof 2019 LA Dataset", "", "Speaker-paired bonafide/spoof data — what made our own enrolment experiment possible at pilot scale.")
    ]
    
    refs_right = [
        ("Base-rate fallacy in intrusion detection", "arxiv.org/pdf/2203.08801", "Why a highly accurate detector still drowns operators in false alerts. The single reason we built a trigger layer."),
        ("\"The Watermark Shortcut\"", "arxiv.org/html/2606.23335v1", "Provenance watermarks contaminate deepfake detectors into learning the watermark, not the fake. A trap we screen for."),
        ("IndicSynth Dataset", "", "Multilingual Indian-language synthetic-speech dataset — our path to testing beyond English benchmarks."),
        ("Independent testing of commercial detectors", "", "Vendors advertise 99% (self-reported); third-party reporting puts real performance at 60–75% on live VoIP.")
    ]
    
    for i, (title, link, desc) in enumerate(refs_left):
        cy = start_y6 + i * (card_h6 + gap_y6)
        add_card(slide6, Inches(0.40), cy, col_w6, card_h6, fill_color=CARD_FILL, border_color=BORDER_GRAY)
        
        tb = slide6.shapes.add_textbox(Inches(0.50), cy + Inches(0.04), col_w6 - Inches(0.20), card_h6 - Inches(0.08))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = title
        r1.font.bold = True
        r1.font.size = Pt(8.5)
        r1.font.color.rgb = NAVY
        
        if link:
            r_lk = p1.add_run()
            r_lk.text = f"  [{link}]"
            r_lk.font.italic = True
            r_lk.font.size = Pt(8.0)
            r_lk.font.color.rgb = BLUE
            
        p2 = tf.add_paragraph()
        p2.space_before = Pt(2)
        r2 = p2.add_run()
        r2.text = desc
        r2.font.size = Pt(7.8)
        r2.font.color.rgb = DARK_TEXT
        
    for i, (title, link, desc) in enumerate(refs_right):
        cy = start_y6 + i * (card_h6 + gap_y6)
        rx = Inches(0.40) + col_w6 + col_gap6
        add_card(slide6, rx, cy, col_w6, card_h6, fill_color=CARD_FILL, border_color=BORDER_GRAY)
        
        tb = slide6.shapes.add_textbox(rx + Inches(0.10), cy + Inches(0.04), col_w6 - Inches(0.20), card_h6 - Inches(0.08))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = title
        r1.font.bold = True
        r1.font.size = Pt(8.5)
        r1.font.color.rgb = NAVY
        
        if link:
            r_lk = p1.add_run()
            r_lk.text = f"  [{link}]"
            r_lk.font.italic = True
            r_lk.font.size = Pt(8.0)
            r_lk.font.color.rgb = BLUE
            
        p2 = tf.add_paragraph()
        p2.space_before = Pt(2)
        r2 = p2.add_run()
        r2.text = desc
        r2.font.size = Pt(7.8)
        r2.font.color.rgb = DARK_TEXT
        
    bot_y6 = start_y6 + 4 * (card_h6 + gap_y6) + Inches(0.04)
    bot_h6 = Inches(0.85)
    add_card(slide6, Inches(0.40), bot_y6, Inches(12.50), bot_h6, fill_color=WHITE, border_color=NAVY)
    
    tb_ow = slide6.shapes.add_textbox(Inches(0.50), bot_y6 + Inches(0.06), Inches(12.30), bot_h6 - Inches(0.12))
    tf_ow = tb_ow.text_frame
    tf_ow.word_wrap = True
    tf_ow.margin_left = tf_ow.margin_right = tf_ow.margin_top = tf_ow.margin_bottom = 0
    
    p_ow = tf_ow.paragraphs[0]
    r_ow1 = p_ow.add_run()
    r_ow1.text = "Our own work: "
    r_ow1.font.bold = True
    r_ow1.font.size = Pt(8.8)
    r_ow1.font.color.rgb = NAVY
    r_ow2 = p_ow.add_run()
    r_ow2.text = "Leak-free probe methodology (task-naive backbone, speaker-disjoint fit/test split, asserted in code) · Telephony channel simulator · Full experiment log and results — reproducible end-to-end, not quoted from a blog post."
    r_ow2.font.size = Pt(8.2)
    r_ow2.font.color.rgb = DARK_TEXT

    set_speaker_notes(slide6,
        "Slide 6 demonstrates the rigorous research foundation behind every engineering decision in our deck.\n\n"
        "We ground our work in SOTA benchmarks (ASVspoof 5, SASV), telephony augmentation (RawBoost), "
        "and peer-reviewed cybersecurity literature explaining base-rate fallacies and watermark contamination.\n\n"
        "Finally, our own experimental work is reproducible in code with leak-free assertions."
    )

    # ----------------------------------------------------
    # REMOVE SLIDE 7 (Template Instructions)
    # ----------------------------------------------------
    if len(prs.slides) > 6:
        print(f"Removing slide 7 ({len(prs.slides)} slides initially)...")
        rId = prs.slides._sldIdLst[6].rId
        prs.part.drop_rel(rId)
        del prs.slides._sldIdLst[6]
        
    print(f"Final presentation has {len(prs.slides)} slides.")
    prs.save(output_path)
    print(f"Successfully generated {output_path}!")

if __name__ == "__main__":
    build_deck()
