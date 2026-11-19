"""
CyberQazaq — Order Receipt PDF Generator
Clean, readable layout with large fonts and proper Kazakh text.
"""

import io
import os
import re
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

# ── Brand colours ──────────────────────────────────────────
PURPLE       = colors.HexColor('#7c3aed')
PURPLE_LIGHT = colors.HexColor('#a855f7')
PINK         = colors.HexColor('#d946ef')
DARK_BG      = colors.HexColor('#0b1020')
CARD_BG      = colors.HexColor('#111827')
CARD2_BG     = colors.HexColor('#0f172a')
BORDER       = colors.HexColor('#2d3748')
TEXT_MAIN    = colors.HexColor('#f9fafb')
TEXT_MUTED   = colors.HexColor('#9ca3af')
TEXT_PURPLE  = colors.HexColor('#c4b5fd')
TEXT_GREEN   = colors.HexColor('#4ade80')
TEXT_YELLOW  = colors.HexColor('#fbbf24')
WHITE        = colors.white

W, H = A4   # 595 x 842 pt


# ── Қаріптер: қазақ әріптері (ә, ғ, қ, ң, ө, ұ, ү, һ, і) және ₸ белгісі үшін Unicode TTF керек.
# Helvetica оларды көрсете алмайды. Жобадағы fonts/ қалтасындағы DejaVu Sans Condensed қолданылады.
_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_CANDIDATES = [
    (os.path.join(_HERE, 'fonts', 'DejaVuSansCondensed.ttf'), os.path.join(_HERE, 'fonts', 'DejaVuSansCondensed-Bold.ttf')),
    (r'C:\Windows\Fonts\arial.ttf', r'C:\Windows\Fonts\arialbd.ttf'),
]
FONT, FONT_B, UNICODE_OK = 'Helvetica', 'Helvetica-Bold', False
for _reg, _bold in _FONT_CANDIDATES:
    if os.path.exists(_reg) and os.path.exists(_bold):
        pdfmetrics.registerFont(TTFont('CQ', _reg))
        pdfmetrics.registerFont(TTFont('CQ-Bold', _bold))
        FONT, FONT_B, UNICODE_OK = 'CQ', 'CQ-Bold', True
        break
CUR = '₸' if UNICODE_OK else 'T'

PAD  = 32   # left/right margin
CW   = W - PAD * 2  # content width = 531


# ── Helpers ────────────────────────────────────────────────

def rounded_rect(c, x, y, w, h, r=8, fill=None, stroke=None, sw=0.8):
    c.saveState()
    if fill:   c.setFillColor(fill)
    if stroke: c.setStrokeColor(stroke); c.setLineWidth(sw)
    p = c.beginPath()
    p.moveTo(x+r, y)
    p.lineTo(x+w-r, y)
    p.arcTo(x+w-2*r, y, x+w, y+2*r, -90, 90)
    p.lineTo(x+w, y+h-r)
    p.arcTo(x+w-2*r, y+h-2*r, x+w, y+h, 0, 90)
    p.lineTo(x+r, y+h)
    p.arcTo(x, y+h-2*r, x+2*r, y+h, 90, 90)
    p.lineTo(x, y+r)
    p.arcTo(x, y, x+2*r, y+2*r, 180, 90)
    p.close()
    if fill and stroke: c.drawPath(p, fill=1, stroke=1)
    elif fill:          c.drawPath(p, fill=1, stroke=0)
    elif stroke:        c.drawPath(p, fill=0, stroke=1)
    c.restoreState()


def gradient_rect(c, x, y, w, h, col1, col2, steps=60):
    c.saveState()
    step_w = w / steps
    r1,g1,b1 = col1.red, col1.green, col1.blue
    r2,g2,b2 = col2.red, col2.green, col2.blue
    for i in range(steps):
        t = i / steps
        c.setFillColor(colors.Color(r1+(r2-r1)*t, g1+(g2-g1)*t, b1+(b2-b1)*t))
        c.rect(x+i*step_w, y, step_w+0.5, h, fill=1, stroke=0)
    c.restoreState()


def wrap_text(text, max_width, font=None, size=11):
    """Мәтінді нақты ені (pt) бойынша жолдарға бөледі. Тым ұзын сөзді де бөлшектейді."""
    font = font or FONT
    lines, line = [], ''
    for w in str(text).split():
        while stringWidth(w, font, size) > max_width:        # бір сөздің өзі сыймаса
            k = len(w)
            while k > 1 and stringWidth(w[:k], font, size) > max_width:
                k -= 1
            if line: lines.append(line); line = ''
            lines.append(w[:k]); w = w[k:]
        t = (line + ' ' + w).strip()
        if stringWidth(t, font, size) <= max_width:
            line = t
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines or ['']


def fit_text(text, max_width, font, size):
    """Бір жолға сыймаса, соңын «…» қылып қысқартады."""
    text = str(text)
    if stringWidth(text, font, size) <= max_width:
        return text
    while len(text) > 1 and stringWidth(text + '…', font, size) > max_width:
        text = text[:-1]
    return text.rstrip() + '…'


def is_satpaev(city):
    """Қала Сәтбаев (Сатпаев) екенін анықтайды. Мекенжайдағы «Сатбаев көшесі» сияқты көше аттары есепке алынбайды."""
    street_words = ('көше', 'кош.', 'улиц', 'ул.', 'даңғыл', 'проспект', 'пр.', 'мкр', 'шағын', 'street', 'st.')
    for part in str(city).lower().replace('ә', 'а').replace('ё', 'е').replace(';', ',').replace('/', ',').split(','):
        part = part.strip()
        if any(w in part for w in street_words):
            continue
        if any(k in part for k in ('сатпаев', 'сатбаев', 'satpaev', 'satpayev', 'satbayev', 'satbaev')):
            return True
    return False


def info_block(c, x, y, label, value, label_col=None, value_col=None,
               label_size=9, value_size=11, max_width=230):
    """Draw a label + value pair, wrapping value if needed. Returns new y."""
    c.setFont(FONT, label_size)
    c.setFillColor(label_col or TEXT_MUTED)
    c.drawString(x, y, label)
    y -= label_size + 3

    lines = wrap_text(value, max_width, FONT_B, value_size)
    for line in lines:
        c.setFont(FONT_B, value_size)
        c.setFillColor(value_col or TEXT_MAIN)
        c.drawString(x, y, line)
        y -= value_size + 2
    return y - 6


# ── Main builder ────────────────────────────────────────────

def generate_order_pdf(order_data: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"CyberQazaq — Тапсырыс {order_data.get('order_num','')}")
    c.setAuthor('CyberQazaq')

    order_num      = str(order_data.get('order_num', 'N/A'))
    name           = str(order_data.get('name',  '—'))
    phone          = str(order_data.get('phone', '—'))
    city           = str(order_data.get('city',  '—'))
    payment        = str(order_data.get('payment','—'))
    items          = order_data.get('items', [])
    total          = order_data.get('total', 0)
    gifts          = order_data.get('gifts', [])
    payment_status = str(order_data.get('payment_status', 'Растауды күтуде'))
    order_date     = order_data.get('order_date', '')
    now            = order_date if order_date else datetime.now().strftime('%Y-%m-%d %H:%M')

    # payment: first line = method, second line = installment detail
    p_lines  = payment.split('\n')
    p_method = p_lines[0].strip()
    p_extra  = p_lines[1].strip() if len(p_lines) > 1 else ''
    p_extra  = p_extra.replace('Айлық төлем:', '').strip()     # белгі «Ай сайын:» жолағында бөлек тұр

    FOOT_H = 52

    def draw_bg():
        c.setFillColor(DARK_BG)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Subtle glow blobs
        for gx, gy, gcol in [(-20, H+10, (0.31,0.14,0.93,0.10)),
                              (W+20, -20,  (0.85,0.27,0.94,0.08))]:
            c.saveState()
            c.setFillColor(colors.Color(*gcol))
            c.circle(gx, gy, 220, fill=1, stroke=0)
            c.restoreState()

        # Left accent bar
        gradient_rect(c, 0, 0, 6, H, PURPLE, PINK)

    # ── FOOTER ──────────────────────────────────────────────
    def draw_footer():
        gradient_rect(c, 0, 0, W, FOOT_H, PURPLE, PINK)
        c.setFont(FONT_B, 11)
        c.setFillColor(WHITE)
        c.drawCentredString(W / 2, FOOT_H - 16,
            'CyberQazaq — Gaming компьютерлер мен комплектілер интернет-дүкені')
        c.setFont(FONT, 9)
        c.setFillColor(colors.Color(1, 1, 1, 0.85))
        c.drawCentredString(W / 2, FOOT_H - 32,
            'Тел: +7 776 500 75 02  |  WhatsApp: wa.me/77765007502  |  Сәтбаев қ., Қазақстан')


    draw_bg()

    # ── HEADER ─────────────────────────────────────────────
    HEADER_H = 72
    gradient_rect(c, 0, H - HEADER_H, W, HEADER_H, PURPLE, PINK)

    c.setFont(FONT_B, 28)
    c.setFillColor(WHITE)
    c.drawString(PAD, H - 38, 'CyberQazaq')

    c.setFont(FONT, 10)
    c.setFillColor(colors.Color(1, 1, 1, 0.80))
    c.drawString(PAD, H - 55, 'Gaming компьютерлер мен комплектілер интернет-дүкені')

    c.setFont(FONT_B, 11)
    c.setFillColor(WHITE)
    c.drawRightString(W - PAD, H - 33, 'ТАПСЫРЫС ҚҰЖАТЫ')
    c.setFont(FONT, 10)
    c.setFillColor(colors.Color(1, 1, 1, 0.80))
    c.drawRightString(W - PAD, H - 49, now)

    # Accent line
    gradient_rect(c, 0, H - HEADER_H - 4, W, 4, PURPLE, PINK)

    # ── CURRENT Y ──────────────────────────────────────────
    y = H - HEADER_H - 20

    def ensure(h):
        """Келесі блок (биіктігі h) бетке сыймаса, жаңа бет ашады."""
        nonlocal y
        if y - h < FOOT_H + 6:
            draw_footer()
            c.showPage()
            draw_bg()
            y = H - 40

    # ── ORDER NUMBER + STATUS ──────────────────────────────
    CARD_H = 62
    rounded_rect(c, PAD, y - CARD_H, CW, CARD_H, r=12,
                 fill=CARD_BG, stroke=BORDER, sw=1)
    # Left colour bar
    gradient_rect(c, PAD, y - CARD_H, 5, CARD_H,
                  colors.HexColor('#7c3aed'), colors.HexColor('#d946ef'))

    c.setFont(FONT, 9)
    c.setFillColor(TEXT_MUTED)
    c.drawString(PAD + 18, y - 16, 'ТАПСЫРЫС НӨМІРІ')

    c.setFont(FONT_B, 24)
    c.setFillColor(TEXT_PURPLE)
    c.drawString(PAD + 18, y - 46, f'# {order_num}')

    # Status pill
    s_bg  = colors.HexColor('#14532d') if 'күт' in payment_status.lower() or 'kut' in payment_status.lower() else colors.HexColor('#1e3a5f')
    rounded_rect(c, W - PAD - 170, y - CARD_H + 14, 160, 30, r=8, fill=s_bg)
    c.setFont(FONT_B, 10)
    c.setFillColor(TEXT_GREEN)
    # Truncate status label
    s_label = fit_text(payment_status, 148, FONT_B, 10)
    c.drawCentredString(W - PAD - 90, y - CARD_H + 32, s_label)

    y -= CARD_H + 14

    # ── TWO-COLUMN INFO ─────────────────────────────────────
    COL_W  = CW // 2 - 8
    COL2_X = PAD + COL_W + 16

    # Compute heights
    client_rows = [
        ('Аты-жөні:',         name),
        ('Телефон:',          phone),
        ('Қала / мекенжай:',  city),
        ('Төлем тәсілі:',    p_method),
    ]

    # Each row: label line (9pt+3) + value line(s) (11pt+2) + gap(6)
    def row_height(label, value, max_w=None):
        n_val_lines = len(wrap_text(value, max_w or (CW // 2 - 8 - 28), FONT_B, 11))
        return (9+3) + n_val_lines*(11+2) + 6

    client_h = sum(row_height(l, v) for l,v in client_rows) + 36  # +36 for heading
    delivery_rows = [
        ('Тапсырыс күні:',   now),
        ('Төлем күйі:',      payment_status),
        ('Жеткізу мерзімі:', '1–3 жұмыс күні' if is_satpaev(city) else '7–15 күн'),
        ('Жеткізу аймағы:',  'Сәтбаев қаласы' if is_satpaev(city) else 'Қазақстан бойынша'),
    ]
    delivery_h = sum(row_height(l, v) for l, v in delivery_rows) + 36
    BLOCK_H = max(client_h, delivery_h, 130)

    # Client card
    rounded_rect(c, PAD, y - BLOCK_H, COL_W, BLOCK_H, r=12,
                 fill=CARD_BG, stroke=BORDER, sw=1)
    c.setFont(FONT_B, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawString(PAD + 14, y - 20, 'КЛИЕНТ МӘЛІМЕТТЕРІ')
    ry = y - 38
    for label, val in client_rows:
        ry = info_block(c, PAD + 14, ry, label, val or '—', max_width=COL_W - 28)

    # Delivery card
    rounded_rect(c, COL2_X, y - BLOCK_H, COL_W, BLOCK_H, r=12,
                 fill=CARD_BG, stroke=BORDER, sw=1)
    c.setFont(FONT_B, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawString(COL2_X + 14, y - 20, 'ЖЕТКІЗУ ШАРТТАРЫ')
    ry2 = y - 38
    for label, val in delivery_rows:
        ry2 = info_block(c, COL2_X + 14, ry2, label, val or '—', max_width=COL_W - 28)

    y -= BLOCK_H + 16

    # ── ITEMS TABLE ─────────────────────────────────────────
    c.setFont(FONT_B, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawString(PAD, y, 'ТАУАРЛАР ТІЗІМІ')
    y -= 14

    # Header row
    HDR_H = 28
    gradient_rect(c, PAD, y - HDR_H, CW, HDR_H, PURPLE, PINK)
    c.setFont(FONT_B, 9)
    c.setFillColor(WHITE)
    # Columns:  Name | Desc | Warranty | Qty | Price
    cols = {
        'name':     PAD + 12,
        'desc':     PAD + CW * 0.44,
        'warranty': PAD + CW * 0.61,
        'qty':      PAD + CW * 0.76,
        'price':    PAD + CW - 10,
    }
    c.drawString(cols['name'],     y - 18, 'Тауар атауы')
    c.drawString(cols['desc'],     y - 18, 'Сипаттама')
    c.drawString(cols['warranty'], y - 18, 'Кепілдік')
    c.drawString(cols['qty'],      y - 18, 'Саны')
    c.drawRightString(cols['price'], y - 18, 'Бағасы')
    y -= HDR_H

    # Item rows — dynamic height based on wrapped name
    for idx, item in enumerate(items):
        item_name = str(item.get('name', ''))
        qty_n = item.get('qty')
        m = re.search(r'\s*\(\s*[×x]\s*(\d+)\s*\)\s*$', item_name)      # «Атауы (× 2)» → атауы + саны
        if m:
            item_name = item_name[:m.start()]
            qty_n = qty_n or int(m.group(1))
        qty_n = qty_n or 1
        name_lines = wrap_text(item_name, cols['desc'] - cols['name'] - 24, FONT_B, 10)
        ROW_H = max(34, 14 * len(name_lines) + 16)
        ensure(ROW_H + 4)

        bg = CARD_BG if idx % 2 == 0 else CARD2_BG
        rounded_rect(c, PAD, y - ROW_H, CW, ROW_H, r=5, fill=bg)

        # Index dot
        cy_dot = y - ROW_H / 2
        c.setFillColor(PURPLE)
        c.circle(PAD + 12, cy_dot, 9, fill=1, stroke=0)
        c.setFont(FONT_B, 8)
        c.setFillColor(WHITE)
        c.drawCentredString(PAD + 12, cy_dot - 3, str(idx + 1))

        # Name (wrapped)
        ny = y - 14
        for line in name_lines:
            c.setFont(FONT_B, 10)
            c.setFillColor(TEXT_MAIN)
            c.drawString(cols['name'] + 12, ny, line)
            ny -= 13

        mid = y - ROW_H / 2 - 4

        # Description
        desc = fit_text(item.get('description', 'Gaming'), cols['warranty'] - cols['desc'] - 8, FONT, 9)
        c.setFont(FONT, 9)
        c.setFillColor(TEXT_MUTED)
        c.drawString(cols['desc'], mid, desc)

        # Warranty
        warranty = fit_text(item.get('warranty', '12 ай'), cols['qty'] - cols['warranty'] - 6, FONT_B, 10)
        c.setFont(FONT_B, 10)
        c.setFillColor(TEXT_GREEN)
        c.drawString(cols['warranty'], mid, warranty)

        # Qty
        qty = f'{qty_n} дана'
        c.setFont(FONT_B, 10)
        c.setFillColor(TEXT_MAIN)
        c.drawString(cols['qty'], mid, qty)

        # Price
        price = item.get('price', 0)
        c.setFont(FONT_B, 11)
        c.setFillColor(TEXT_PURPLE)
        c.drawRightString(cols['price'], mid, f"{int(price):,} {CUR}".replace(',', ' '))

        y -= ROW_H

    # ── TOTAL ───────────────────────────────────────────────
    ensure(40 + 6 + 12)
    y -= 6
    TOTAL_H = 40
    gradient_rect(c, PAD, y - TOTAL_H, CW, TOTAL_H, PURPLE, PINK)
    c.setFont(FONT_B, 12)
    c.setFillColor(WHITE)
    c.drawString(PAD + 18, y - 25, 'ЖАЛПЫ СОМА:')
    c.setFont(FONT_B, 20)
    c.setFillColor(WHITE)
    c.drawRightString(PAD + CW - 14, y - 27, f"{int(total):,} {CUR}".replace(',', ' '))
    y -= TOTAL_H + 12

    # ── MONTHLY PAYMENT (if installment) ───────────────────
    if p_extra:
        ensure(44)
        rounded_rect(c, PAD, y - 30, CW, 30, r=10,
                     fill=colors.HexColor('#0d1f3c'), stroke=colors.HexColor('#1e3a5f'), sw=1)
        c.setFont(FONT, 9)
        c.setFillColor(TEXT_MUTED)
        c.drawString(PAD + 14, y - 19, 'Ай сайын:')
        c.setFont(FONT_B, 13)
        c.setFillColor(TEXT_PURPLE)
        c.drawString(PAD + 80, y - 20, fit_text(p_extra, CW - 100, FONT_B, 13))
        y -= 40

    # ── GIFTS ───────────────────────────────────────────────
    if gifts:
        GIFT_H = 24 + len(gifts) * 20
        ensure(GIFT_H + 12)
        rounded_rect(c, PAD, y - GIFT_H, CW, GIFT_H, r=10,
                     fill=colors.HexColor('#1c1407'),
                     stroke=colors.HexColor('#92400e'), sw=1)
        c.setFont(FONT_B, 10)
        c.setFillColor(TEXT_YELLOW)
        c.drawString(PAD + 14, y - 17, 'ТЕГІН СЫЙЛЫҚТАР:')
        gy = y - 34
        for gift in gifts:
            c.setFont(FONT, 10)
            c.setFillColor(TEXT_YELLOW)
            c.drawString(PAD + 14, gy, fit_text(f'• {gift}', CW - 28, FONT, 10))
            gy -= 20
        y -= GIFT_H + 10

    # ── WARRANTY & TERMS ────────────────────────────────────
    terms = [
        '• Барлық тауарлар 12–36 ай кепілдікпен жеткізіледі.',
        '• Тауарды алған күннен бастап 14 күн ішінде қайтаруға болады.',
        '• Техникалық ақау шықса, тауар ауыстырылады немесе ақша қайтарылады.',
        '• Барлық тауарлар ресми дистрибьютор арқылы алынады — түпнұсқа.',
    ]
    TERMS_H = 24 + len(terms) * 15
    ensure(TERMS_H + 2)
    rounded_rect(c, PAD, y - TERMS_H, CW, TERMS_H, r=10,
                 fill=CARD_BG, stroke=BORDER, sw=1)
    c.setFont(FONT_B, 10)
    c.setFillColor(TEXT_MUTED)
    c.drawString(PAD + 14, y - 17, 'КЕПІЛДІК ЖӘНЕ ШАРТТАР')
    ty = y - 33
    for term in terms:
        c.setFont(FONT, 9)
        c.setFillColor(TEXT_MUTED)
        c.drawString(PAD + 14, ty, term)
        ty -= 15
    y -= TERMS_H + 10

    draw_footer()

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
