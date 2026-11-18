from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response
import os
import hmac
import html
from dotenv import load_dotenv

load_dotenv()  # .env файлындағы айнымалыларды жүктейді (local dev үшін)

# PDF generation (requires: pip install reportlab)
try:
    from generate_pdf import generate_order_pdf
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False
    print("WARNING: reportlab not installed. Run: pip install reportlab")
import json
from pathlib import Path
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)


def _require_env(name):
    """Қауіпсіздік: маңызды айнымалы жоқ болса, қосымша іске қосылмайды."""
    value = os.environ.get(name, "").strip()
    if not value or value.startswith(("change-me", "dev-only")):
        raise RuntimeError(
            f"{name} орнатылмаған. .env.example файлын .env деп көшіріп, мәнін толтырыңыз."
        )
    return value


app.secret_key = _require_env("SECRET_KEY")

# Claude API кілті (міндетті емес). Жоқ болса, AI Builder локалды логикамен жұмыс істейді.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# ─── EMAIL CONFIG ──────────────────────────────────────────────────────────────
# All values are read from environment variables — see .env.example
# Gmail App Password: myaccount.google.com → Security → 2-Step Verification → App passwords
EMAIL_SENDER   = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER", "")

DATA_PATH = Path(__file__).with_name("data.json")

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DATA = json.load(f)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def find_item(items, item_id):
    """Return the first item whose 'id' matches item_id, or None."""
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def explain_product(product):
    """Return a rich Kazakh-language explanation for any product."""
    if not product:
        return "Ақпарат табылмады."

    text  = []
    cat   = product.get("category", "")
    name  = product.get("name", "")
    price = product.get("price", 0)

    if cat == "gpu":
        vram = product.get("vram", "")
        # Series detection
        for series, desc in [
            ("5090", "RTX 5090 — ең қуатты видеокарта. 4K, 8K, кез-келген ойынды максималды баптауда ойнауға мүмкіндік береді."),
            ("5080", "RTX 5080 — флагман деңгейіне жақын жаңа буын карта. 4K gaming үшін тамаша таңдау."),
            ("5070 Ti", "RTX 5070 Ti — жаңа буын жоғары өнімді карта. 2K-4K аралығында керемет FPS береді."),
            ("5070", "RTX 5070 — жаңа архитектура, 2K gaming үшін тамаша баға-өнімділік балансы."),
            ("5060 Ti", "RTX 5060 Ti — жаңа буын орта сегмент. 1080p-1440p-де жоғары FPS береді."),
            ("5060", "RTX 5060 — жаңа буын, орта сегмент. 1080p gaming үшін тиімді таңдау."),
            ("4090", "RTX 4090 — алдыңғы буынның ең қуатты картасы. 4K-да 100+ FPS береді."),
            ("4080", "RTX 4080 Super — 4K gaming үшін тамаша, барлық ойынды ең жоғары баптауда ойнатады."),
            ("4070 Ti", "RTX 4070 Ti Super — 16GB VRAM, 2K-4K аралығында тамаша өнімділік."),
            ("4070 Super", "RTX 4070 Super — RTX 4070-тен 20% жылдам, 2K gaming үшін ең тиімді таңдау."),
            ("4070", "RTX 4070 — 2K gaming-тің алтын стандарты. Барлық заманауи ойынды жеңіл тартады."),
            ("4060 Ti", "RTX 4060 Ti — 16GB VRAM бар, 1080p-1440p үшін мықты карта."),
            ("4060", "RTX 4060 — жаңа буын 1080p картасы, тиімді энергия тұтынумен жоғары FPS."),
            ("3080 Ti", "RTX 3080 Ti — 12GB VRAM, 2K-4K gaming үшін бұрынғы флагман деңгейі."),
            ("3080", "RTX 3080 — 2K-4K gaming-те тамаша өнімділік беретін сенімді карта."),
            ("3070 Ti", "RTX 3070 Ti — 2K gaming үшін жоғары FPS, тиімді баға."),
            ("3070", "RTX 3070 — 2K gaming-тің ең танымал таңдауы, тиімді баға-өнімділік."),
            ("3060 Ti", "RTX 3060 Ti — 1080p-1440p үшін тамаша карта, RTX 3070-ке жақын өнімділік."),
            ("3060", "RTX 3060 — 12GB VRAM бар 1080p карта, тиімді баға."),
            ("2080 Ti", "RTX 2080 Ti — ескі флагман, бүгінде орта-жоғары деңгейде тұрады."),
            ("2080", "RTX 2080 — ескі жоғары деңгей, қазір орта деңгей ретінде сатылады."),
            ("2070 Super", "RTX 2070 Super — 1080p-1440p үшін жақсы ескі карта."),
            ("2070", "RTX 2070 — 1080p gaming үшін жақсы, ескі буын."),
            ("2060", "RTX 2060 — 1080p gaming үшін базалық RTX карта."),
        ]:
            if series in name:
                text.append(desc)
                break

        if vram:
            gb = int(vram.replace("GB","").strip()) if vram.replace("GB","").strip().isdigit() else 0
            if gb >= 24:
                text.append(f"{vram} VRAM — AI жұмысы, стриминг және 4K текстуралар үшін де жеткілікті.")
            elif gb >= 16:
                text.append(f"{vram} VRAM — заманауи ойындардың барлығы үшін жеткілікті, болашаққа дайын.")
            elif gb >= 12:
                text.append(f"{vram} VRAM — қазіргі ойындар үшін жеткілікті, мод-ойындарды да тартады.")
            else:
                text.append(f"{vram} VRAM — 1080p ойындар үшін жеткілікті.")
        text.append("Ray Tracing және DLSS технологиялары қолдауы бар.")

    elif cat == "cpu":
        for series, desc in [
            ("9800X3D", "Ryzen 7 9800X3D — қазіргі кезде ең жоғары FPS беретін gaming процессор. 3D V-Cache технологиясы ойын жылдамдығын революциялық түрде арттырады."),
            ("9700X",   "Ryzen 7 9700X — жаңа буын Zen 5 архитектурасы, барлық жұмыс үшін тамаша."),
            ("7800X3D", "Ryzen 7 7800X3D — gaming-те i9 мен бәсекелесетін процессор. 3D Cache технологиясы FPS-ті максималды арттырады."),
            ("7700X",   "Ryzen 7 7700X — 8 ядро, стриминг + gaming үшін тамаша баланс."),
            ("7600",    "Ryzen 5 7600 — gaming үшін тиімді 6 ядролы процессор, жаңа AM5 платформасы."),
            ("7500",    "Ryzen 5 7500 — бюджет gaming үшін тиімді AM5 процессоры."),
            ("i9-14900","Intel i9-14900K — максималды өнімділік, стриминг, 3D рендеринг және gaming үшін топ деңгей."),
            ("i9-13900","Intel i9-13900K — 24 ядро (8P+16E), барлық ауыр жұмыс үшін."),
            ("i7-14700","Intel i7-14700F — 20 ядро, стриминг + gaming үшін тамаша."),
            ("i7-13700","Intel i7-13700F — стриминг пен gaming комбинациясы үшін жақсы."),
            ("i5-14600","Intel i5-14600KF — gaming-те Ryzen 7-мен бәсекелесетін i5."),
            ("i5-13600","Intel i5-13600KF — gaming үшін тамаша баға-өнімділік балансы."),
            ("i5-13400","Intel i5-13400F — бюджет gaming процессоры, жақсы баға."),
            ("i5-12400","Intel i5-12400F — тиімді бюджет процессоры, негізгі gaming үшін жеткілікті."),
        ]:
            if series.lower() in name.lower():
                text.append(desc)
                break
        else:
            text.append(f"{name} — gaming пен күнделікті жұмысқа жарамды процессор.")

        cores = product.get("cores")
        if cores:
            text.append(f"{cores} ядро multitasking пен стриминг кезінде артықшылық береді.")

    elif cat == "ram":
        gb   = int(''.join(filter(str.isdigit, name.split('DDR')[0]))) if 'DDR' in name else 16
        gen  = "DDR5" if "DDR5" in name else "DDR4"
        if gb >= 64:
            text.append(f"{name} — видео монтаж, 3D рендеринг және ең ауыр жұмыс үшін артық жад.")
        elif gb >= 32:
            text.append(f"{name} — стриминг, ауыр ойындар және multitasking үшін оптималды жад.")
        else:
            text.append(f"{name} — gaming мен күнделікті жұмыс үшін жеткілікті жад.")
        if gen == "DDR5":
            text.append("DDR5 — жаңа буын стандарты, жоғары bandwidth пен жылдамдық.")
        else:
            text.append("DDR4 — сенімді және кең таралған стандарт.")

    elif cat == "ssd":
        if "2TB" in name:
            text.append("2TB NVMe SSD — 30+ ойынды сақтауға жеткілікті кеңістік, жылдам жүктеу уақыты.")
        elif "1TB" in name:
            text.append("1TB NVMe SSD — Windows + 15-20 ойын сақтауға жеткілікті, өте жылдам.")
        else:
            text.append("512GB NVMe SSD — жүйе мен негізгі ойындарға жеткілікті, жылдам boot уақыты.")
        text.append("NVMe SSD HDD-ге қарағанда 5-10 есе жылдам ойын мен жүйе жүктейді.")

    elif cat == "monitor":
        hz = product.get("hz", 0)
        try:
            hz = int(hz)
        except:
            hz = 0
        if hz >= 600:
            text.append(f"{hz}Hz — кәсіби киберспортшыларға арналған максималды refresh rate. Инпут лаг минималды деңгейде.")
        elif hz >= 360:
            text.append(f"{hz}Hz — pro деңгейлі esports монитор. CS2, Valorant-та бәсекелестіктен озу үшін тамаша.")
        elif hz >= 240:
            text.append(f"{hz}Hz — gaming монитор, ойынды өте жылдам және тегіс көрсетеді.")
        elif hz >= 144:
            text.append(f"{hz}Hz — gaming үшін минималды стандарт, 60Hz-ге қарағанда айтарлықтай жақсы.")
        if product.get("ips"):
            text.append("IPS панелі — кең қарау бұрышы және жарқын түстер.")

    elif cat == "mouse":
        text.append(f"{name} — FPS ойындарына арналған gaming mouse.")
        w = product.get("weight")
        if w:
            text.append(f"{w} жеңіл корпус — ұзақ ойын сессияларында қолды шаршатпайды.")
        pr = product.get("polling_rate")
        if pr:
            text.append(f"{pr} polling rate — инпут лагты минималды деңгейге түсіреді.")
        if product.get("wireless"):
            text.append("Wireless — сымсыз еркіндік, кешігу жоқ.")
        if "Superlight" in name or "superlight" in name:
            text.append("Superlight серия — Logitech-тің ең жеңіл pro деңгейлі mouse-ы, турнирларда қолданылады.")
        elif "ZOWIE" in name:
            text.append("ZOWIE — driver-сіз plug-and-play, pro ойыншылар арасында өте танымал.")
        elif "Paro" in name:
            text.append("Lamzu Paro — PixArt 3395 сенсор, симметриялық форма, ультра жеңіл корпус. FPS-те тамаша дәлдік береді.")
        elif "Thorn" in name:
            color = ""
            if "White" in name:   color = " Ақ түсі white build setтерге тамаша үйлеседі."
            elif "Orange" in name: color = " Қызғылт сары түс — ерекше стиль."
            elif "Black" in name:  color = " Классикалық қара дизайн."
            text.append(f"Lamzu Thorn — ergonomic форма, lightweight корпус, pro aim үшін арналған.{color}")
        elif "Lamzu" in name:
            text.append("Lamzu — honeycomb корпус, өте жеңіл, баға-сапа балансы жоғары.")
        elif "VGN" in name:
            text.append("VGN — бюджет сегменттің ең тиімді таңдауы.")

    elif cat == "keyboard":
        text.append(f"{name} — gaming пернетақта.")
        sw = product.get("switch")
        if sw:
            text.append(f"{sw} switch — басу сезімі мен жауап беру уақытына тікелей әсер етеді.")
        if product.get("rapid_trigger"):
            text.append("Rapid Trigger — актуация нүктесін өзгертуге болады, esports-та бәсекелестіктен озу үшін маңызды.")
        if "Wooting" in name:
            text.append("Wooting — Rapid Trigger технологиясының пионері, pro ойыншылардың таңдауы.")
        elif "Apex Pro" in name:
            text.append("SteelSeries Apex Pro — OmniPoint switch, актуацияны 0.1mm-ден реттеуге болады.")
        elif "HyperX" in name:
            text.append("HyperX Alloy — мықты болат корпус, ұзақ қызмет мерзімі.")
        elif "MIX 87" in name:
            color = "Red" if "Red" in name else "Black"
            text.append(f"MCHOSE MIX 87 ({color}) — compact TKL форматы, aluminum frame, RGB жарық. Бюджет сегменттегі ең тиімді механикалық клавиатура.")
        elif "Aula" in name or "Ajazz" in name or "MCHOSE" in name:
            text.append("Бюджет сегменттегі ең тиімді таңдай, баға-сапа балансы жоғары.")

    elif cat == "headset":
        text.append(f"{name} — gaming headset.")
        if product.get("wireless"):
            text.append("Wireless — еркін қозғалыс, сымсыз байланыс.")
        if product.get("surround"):
            text.append("Surround sound — дыбыс бағытын дәл анықтауға көмектеседі, FPS ойындарда артықшылық.")
        if "G Pro X2 Lightspeed" in name or "X2 Lightspeed" in name:
            color = "Pink" if "Pink" in name else "White" if "White" in name else ""
            c = f" {color} түс — стильді premium нұсқа." if color else ""
            text.append(f"Logitech G Pro X2 Lightspeed — LIGHTSPEED wireless технологиясы, 50 сағат батарея, DTS Headphone:X 2.0 surround.{c}")
        elif "Pro X 2" in name:
            text.append("Logitech G Pro X 2 — жаңа буын, кәсіби деңгейдегі дыбыс сапасы, турнирларда қолданылады.")
        elif "BlackShark V2 Pro" in name:
            color = " Ақ түс — white build setтерге тамаша." if "White" in name else ""
            text.append(f"Razer BlackShark V2 Pro 2023 — THX Spatial Audio, TriForce Titanium 50mm драйвер, wireless.{color}")
        elif "MCHOSE V9" in name:
            text.append("MCHOSE V9 Pro — gaming headset, сапалы стерео дыбыс пен микрофон. Бюджет сегменттің мықты таңдауы.")
        elif "MCHOSE X9" in name:
            color = " Қызғылт түс — стильді." if "Pink" in name else " Ақ түс — таза дизайн." if "White" in name else ""
            text.append(f"MCHOSE X9 — gaming headset, жақсы дыбыс сапасы, ыңғайлы амбушюр.{color}")
        elif "Nova Pro" in name:
            text.append("SteelSeries Arctis Nova Pro — премиум деңгейдегі дыбыс, Hi-Res сертификаты бар.")
        elif "Cloud" in name:
            text.append("HyperX Cloud серия — ойыншылар арасында ең танымал, ыңғайлы және сапалы.")

    return " ".join(text) if text else f"{name} — сапалы өнім."




# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html", data=DATA)


@app.route("/ai-builder")
def ai_builder():
    return render_template("ai.html", data=DATA)


@app.route("/products")
def products():
    return render_template("products.html", data=DATA)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/cart")
def cart():
    return render_template("cart.html")


@app.route("/payment")
def payment():
    return render_template("payment.html")


@app.route("/delivery")
def delivery():
    return render_template("payment.html")


@app.route("/warranty")
def warranty():
    return render_template("payment.html")


@app.route("/favorites")
def favorites():
    return render_template("favorites.html")


@app.route("/order", methods=["POST"])
def order():
    body = request.get_json() or {}

    esc = lambda v: html.escape(str(v))  # HTML injection-нан қорғау

    order_num   = esc(body.get("order_num", "N/A"))
    name        = esc(body.get("name", ""))
    phone       = esc(body.get("phone", ""))
    city        = esc(body.get("city", ""))
    payment     = esc(body.get("payment", ""))
    items       = body.get("items", [])
    total       = body.get("total", 0)

    # Build item rows for the email
    items_html = "".join(
        f"<tr><td style=\"padding:8px 12px;border-bottom:1px solid #1f2937\">{esc(i['name'])}</td>"
        f"<td style=\"padding:8px 12px;border-bottom:1px solid #1f2937;text-align:right\">{int(i['price']):,} ₸</td></tr>"
        for i in items
    )

    gifts       = body.get("gifts", [])
    gifts_html  = ""
    if gifts:
        gift_rows = "".join(f"<li style=\"margin:4px 0;color:#fbbf24\">🎁 {esc(g)}</li>" for g in gifts)
        gifts_html = f"""
        <div style=\"background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);
                      border-radius:16px;padding:20px;margin-top:16px\">
          <p style=\"color:#fbbf24;font-weight:700;margin-bottom:10px\">🎁 Тегін сыйлықтар:</p>
          <ul style=\"list-style:none;padding:0;margin:0\">{gift_rows}</ul>
        </div>"""

    html_body = f"""
    <div style="font-family:Inter,sans-serif;background:#0b1020;color:white;padding:40px;max-width:600px;margin:0 auto;border-radius:24px">
      <h1 style="font-size:28px;margin-bottom:4px">🛒 Жаңа тапсырыс!</h1>
      <p style="color:#6b7280;margin-bottom:28px">CyberQazaq — cybershop</p>

      <div style="background:#111827;border-radius:16px;padding:24px;margin-bottom:20px">
        <p style="color:#9ca3af;font-size:13px;margin-bottom:4px">ТАПСЫРЫС НӨМІРІ</p>
        <p style="font-size:24px;font-weight:900;color:#d8b4fe">{order_num}</p>
      </div>

      <div style="background:#111827;border-radius:16px;padding:24px;margin-bottom:20px">
        <p style="color:#9ca3af;font-size:13px;margin-bottom:16px">КЛИЕНТ МӘЛІМЕТТЕРІ</p>
        <p><strong>Аты:</strong> {name}</p>
        <p style="margin-top:8px"><strong>Телефон:</strong> <a href="tel:{phone}" style="color:#a855f7">{phone}</a></p>
        <p style="margin-top:8px"><strong>Қала / Мекенжай:</strong> {city}</p>
        <p style="margin-top:8px"><strong>Төлем тәсілі:</strong> <span style="color:#4ade80">{payment}</span></p>
      </div>

      <div style="background:#111827;border-radius:16px;padding:24px;margin-bottom:20px">
        <p style="color:#9ca3af;font-size:13px;margin-bottom:16px">ТАУАРЛАР</p>
        <table style="width:100%;border-collapse:collapse">
          {items_html}
          <tr>
            <td style="padding:12px;font-weight:900;font-size:18px">Жалпы сома</td>
            <td style="padding:12px;font-weight:900;font-size:18px;text-align:right;color:#d8b4fe">{int(total):,} ₸</td>
          </tr>
        </table>
      </div>

      <p style="color:#6b7280;font-size:13px;text-align:center">
        CyberQazaq · Сатпаев · +7 776 500 75 02
      </p>
    </div>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🛒 Жаңа тапсырыс {order_num} — {name}"
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECEIVER
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        return jsonify({"ok": True})

    except Exception as e:
        # Don't block the order if email fails — log and continue
        print(f"Email error: {e}")
        return jsonify({"ok": True, "email_sent": False})


@app.route("/ai", methods=["POST"])
def ai():
    import urllib.request as _ureq
    body    = request.get_json() or {}
    text    = str(body.get("request", "")).strip()
    text_lo = text.lower()

    # ── 1. Parse budget ───────────────────────────────────────────────────────
    try:
        budget = int(body.get("budget", 0))
    except (ValueError, TypeError):
        budget = 0

    if budget == 0:
        mln    = re.search(r"(\d+)\s*млн", text_lo)
        k      = re.search(r"(\d{3})\s*k\b", text_lo)  # "500k"; "4k" (рұқсат) бюджет емес
        number = re.search(r"\d+",           text_lo)
        if mln:    budget = int(mln.group(1)) * 1_000_000
        elif k:    budget = int(k.group(1))   * 1_000
        elif number: budget = int(number.group())

    # (минималды бюджет төменде, intent анықталған соң қойылады)

    # ── 2. Detect intent ──────────────────────────────────────────────────────
    intent_map = {
        "gpu":      ["видеокарт", "gpu", "rtx", "gtx", "видео", "карта"],
        "cpu":      ["процессор", "cpu", "intel", "ryzen", "i5", "i7", "i9", "core"],
        "ram":      ["ram", "жедел жад", "память", "ddr"],
        "ssd":      ["ssd", "жинақтауыш", "диск", "nvme"],
        "monitor":  ["монитор", "monitor", "дисплей", "экран", "hz"],
        "mouse":    ["тышқан", "mouse", "мышь", "logitech", "zowie", "lamzu"],
        "keyboard": ["пернетақта", "keyboard", "клавиатур", "wooting"],
        "headset":  ["құлаққап", "headset", "наушник", "гарнитур"],
        "setup":    ["сет", "setup", "компьютер", "пк", "жинақ", "build"],
    }

    detected_cats = []
    for cat, keywords in intent_map.items():
        if any(kw in text_lo for kw in keywords):
            detected_cats.append(cat)

    # Минималды бюджет (350k) тек толық жинақ үшін. Жеке тауар сұралса, нақты бюджет сақталады.
    single_category = len(detected_cats) == 1 and detected_cats[0] != "setup"
    if budget == 0 or (budget < 350_000 and not single_category):
        budget = 350_000

    # Is user asking to ANALYSE / judge a product quality?
    want_analysis = any(w in text_lo for w in [
        "сапа", "quality", "жақсы ма", "тиімді ма", "бағала", "analyze",
        "analysis", "review", "пікір", "vs", "немесе", "or", "compare",
        "салыстыр", "worth", "тұра ма", "ұсынасыз ба", "алу керек пе",
    ])

    # Game / use case detection
    use_case = "general"
    if any(w in text_lo for w in ["valorant", "cs2", "cs", "фпс", "fps", "esports"]):
        use_case = "esports"
    elif any(w in text_lo for w in ["stream", "стрим", "стриминг", "obs"]):
        use_case = "streaming"
    elif any(w in text_lo for w in ["4k", "4к", "рендер", "render", "3d", "монтаж"]):
        use_case = "creative"
    elif any(w in text_lo for w in ["cyberpunk", "rdr2", "elden ring", "ауыр ойын"]):
        use_case = "aaa"

    # ── 3. Tag helpers ────────────────────────────────────────────────────────
    def tagged(items, cat):
        result = []
        for item in items:
            item = dict(item); item["category"] = cat; result.append(item)
        return result

    all_gpus      = tagged(DATA.get("gpus",      []), "gpu")
    all_cpus      = tagged(DATA.get("cpus",      []), "cpu")
    all_ram       = tagged(DATA.get("ram",       []), "ram")
    all_ssd       = tagged(DATA.get("ssd",       []), "ssd")
    all_monitors  = tagged(DATA.get("monitors",  []), "monitor")
    all_mice      = tagged(DATA.get("mice",      []), "mouse")
    all_keyboards = tagged(DATA.get("keyboards", []), "keyboard")
    all_headsets  = tagged(DATA.get("headsets",  []), "headset")

    all_products_flat = (
        all_gpus + all_cpus + all_ram + all_ssd +
        all_monitors + all_mice + all_keyboards + all_headsets
    )

    def get_alternatives(items, target_price, n=4):
        within = [p for p in items if p["price"] <= target_price * 1.4]
        return sorted(within, key=lambda x: abs(x["price"] - target_price))[:n]

    # ── 4. Find mentioned product ─────────────────────────────────────────────
    def find_mentioned(pool):
        best_match = None
        best_len = 0
        for p in pool:
            name_lo = p["name"].lower()
            if name_lo in text_lo:
                if len(name_lo) > best_len:
                    best_match = p; best_len = len(name_lo)
                continue
            parts = [pt.lower() for pt in p["name"].split() if len(pt) > 3]
            matched = sum(1 for pt in parts if pt in text_lo)
            if matched >= max(1, len(parts) - 1) and matched > best_len // 5:
                best_match = p; best_len = matched * 5
        return best_match

    mentioned = find_mentioned(all_products_flat)

    # ── 5. Build compact product catalogue for Claude context ─────────────────
    def compact(items):
        return [{"id": p["id"], "name": p["name"], "price": p["price"],
                 "desc": p.get("description",""), "cat": p.get("category","")}
                for p in items]

    catalogue_json = json.dumps({
        "gpus":      compact(all_gpus),
        "cpus":      compact(all_cpus),
        "ram":       compact(all_ram),
        "ssd":       compact(all_ssd),
        "monitors":  compact(all_monitors),
        "mice":      compact(all_mice),
        "keyboards": compact(all_keyboards),
        "headsets":  compact(all_headsets),
        "setups":    DATA.get("setups", []),
    }, ensure_ascii=False)

    # ── 6. Claude API call ────────────────────────────────────────────────────
    SYSTEM_PROMPT = f"""Сен CyberQazaq дүкенінің Pro деңгейлі AI кеңесшісісің — Қазақстандағы ең ірі gaming жабдықтар дүкені. Сен тек gaming hardware маманысың.

ДҮКЕН ТАУАРЛАРЫ (толық каталог JSON):
{catalogue_json}

КЛИЕНТ БЮДЖЕТІ: {budget:,} ₸
ҚОЛДАНЫС СЦЕНАРИЙІ: {use_case}

═══════════════════════════════════════════════════════
БІРІНШІ ЕРЕЖЕ — ДЕРЕКТЕР МЕН ДӘЛДІК
═══════════════════════════════════════════════════════

1. ТЕК каталогтағы тауарларды ұсын. Каталогтан тыс ешнәрсе жоқ.
2. Бюджетті қатаң сыйла — 10%-тан аспайтын шектен асу ғана рұқсат.
3. НАҚТЫ БОЛ — жалпы мадақтама жоқ, нақты спецификация + нақты FPS.
4. Scores реалистикалық болсын (асыра мақтама жоқ).

═══════════════════════════════════════════════════════
НАҚТЫ FPS ДЕРЕКТЕРІ (реалистикалық жуықтама)
═══════════════════════════════════════════════════════

CS2 1080p (High settings):
  RTX 2080 Ti→250+, RTX 4070→450+, RTX 4080S→500+, RTX 4090→550+
  RTX 5060→300+, RTX 5060 Ti→380+, RTX 5070→480+, RTX 5070 Ti→560+, RTX 5080→620+, RTX 5090→700+

Valorant 1080p (High):
  RTX 2080 Ti→350+, RTX 4070→550+, RTX 5060→400+, RTX 5070 Ti→700+, RTX 5090→900+

Cyberpunk 2077 1440p Ultra (RT off):
  RTX 4070→65+, RTX 4080S→95+, RTX 4090→110+, RTX 5070→90+, RTX 5080→120+, RTX 5090→150+

Cyberpunk 2077 4K Ultra:
  RTX 4090→60+, RTX 5080→80+, RTX 5090→100+

GTA V 1080p High: RTX 4060→180+, RTX 4070→250+, RTX 5060→200+

DLSS/FSR 3 с Frame Gen дегенде барлық FPS мәндерін ×1.5-2 арттыруға болады.

═══════════════════════════════════════════════════════
SCORES КАЛИБРОВКАСЫ
═══════════════════════════════════════════════════════

overall 95-100: RTX 5090, Ryzen 9 9950X, G Pro X2 Lightspeed — абсолютті топ
overall 88-94:  RTX 5080, RTX 5070 Ti, 9800X3D, Wooting 80HE — жоғары топ
overall 80-87:  RTX 4090, RTX 5070, 7800X3D, Apex Pro TKL — жақсы
overall 70-79:  RTX 4080S, RTX 5060 Ti, i7-14700F — орта-жоғары
overall 60-69:  RTX 4070, i5-13600KF, HyperX Cloud — орта
overall 50-59:  RTX 2080 Ti, i5-12400F — орта-төмен (ескі буын)

value_for_money: баға/өнімділік балансы — арзан+жоғары өнімді = жоғары балл
future_proof:   AM5/DDR5/RTX 5000 жоғары, AM4/DDR4/RTX 2000-3000 төмен

═══════════════════════════════════════════════════════
САЛЫСТЫРУ ЛОГИКАСЫ (vs/compare сұрау)
═══════════════════════════════════════════════════════

- Нақты FPS айырмашылығы, баға айырмашылығы, VRAM айырмашылығы атап өт
- WINNER анық атап өт — "RTX 5080 жеңеді" немесе "9800X3D артық"
- Бюджет тиімділігі бойынша да winner анықта
- Платформа айырмасын атап өт (AM5 vs LGA1700)

═══════════════════════════════════════════════════════
ЖАУАП ФОРМАТЫ — ТЕК JSON
═══════════════════════════════════════════════════════

━━━ MODE: analysis (тауар бағалау, vs, сапа, review) ━━━
{{
  "mode": "analysis",
  "product_name": "тауар атауы",
  "price": баға,
  "category_label": "Видеокарта / Процессор / т.б.",
  "scores": {{
    "overall": 0-100,
    "value_for_money": 0-100,
    "performance": 0-100,
    "future_proof": 0-100,
    "reliability": 0-100
  }},
  "verdict": "buy / skip / wait / best_value",
  "verdict_reason": "1 сөйлемде неге осы вердикт",
  "analysis": "4-6 сөйлем. Нақты FPS деректері (CS2: X FPS, Cyberpunk: Y FPS). VRAM/ядро/MHz нақты атап өт. Кімге ұсынады, кімге ұсынбайды.",
  "technical_specs": {{
    "key1": "мән1",
    "key2": "мән2"
  }},
  "pros": ["нақты артықшылық (мысалы: 16GB VRAM болашаққа дайын)", "артықшылық 2", "артықшылық 3", "артықшылық 4"],
  "cons": ["нақты кемшілік (мысалы: TDP 320W — қуатты БП керек)", "кемшілік 2"],
  "use_cases": [
    {{"label": "1080p Gaming", "fit": "great/good/ok/none", "fps_note": "CS2: 450+ FPS"}},
    {{"label": "1440p Gaming", "fit": "great/good/ok/none", "fps_note": ""}},
    {{"label": "4K Gaming", "fit": "great/good/ok/none", "fps_note": ""}},
    {{"label": "Esports (CS2/Val)", "fit": "great/good/ok/none", "fps_note": ""}},
    {{"label": "Стриминг", "fit": "great/good/ok/none", "fps_note": ""}},
    {{"label": "Рендеринг/3D", "fit": "great/good/ok/none", "fps_note": ""}}
  ],
  "vs_comparison": null,
  "alternatives": [
    {{"name": "тауар аты", "price": баға, "reason": "нақты неге — FPS немесе спецификация атап өт", "cheaper": true, "verdict": "best_budget"}},
    {{"name": "тауар аты", "price": баға, "reason": "нақты неге артық — FPS/VRAM айырмашылығы", "cheaper": false, "verdict": "upgrade"}}
  ]
}}

━━━ ЕГЕР vs/compare СҰРАЛСА — analysis mode + vs_comparison толтыр ━━━
"vs_comparison": {{
  "product_a": "бірінші тауар аты",
  "product_b": "екінші тауар аты",
  "winner_overall": "product_a немесе product_b",
  "winner_value": "product_a немесе product_b",
  "winner_gaming": "product_a немесе product_b",
  "price_diff": баға_айырмашылығы_теңге,
  "performance_diff_pct": пайыздық_айырмашылық,
  "verdict": "Нақты 2 сөйлем: қайсысы жеңді, бюджет пен өнімділік бойынша нақты жауап"
}}

━━━ MODE: single_product (бір категория сұралса) ━━━
{{
  "mode": "single_product",
  "cat": "gpu/cpu/monitor/mouse/keyboard/headset/ram/ssd",
  "use_case": "esports/streaming/creative/aaa/general",
  "query_summary": "Клиент нені сұрады — 1 сөйлем",
  "mentioned": {{"name": "аты", "price": баға, "reason": "нақты неге жақсы/нашар — спецификация + FPS", "score": 0-100}},
  "best_match": {{"name": "аты", "price": баға, "reason": "бюджетке сай ең жақсысы — нақты артықшылықты атап өт", "score": 0-100}},
  "top_3": [
    {{"rank": 1, "name": "аты", "price": баға, "reason": "нақты неге 1-ші орын", "tag": "ең жақсы"}},
    {{"rank": 2, "name": "аты", "price": баға, "reason": "нақты неге 2-ші орын", "tag": "баға-сапа"}},
    {{"rank": 3, "name": "аты", "price": баға, "reason": "нақты неге 3-ші орын", "tag": "бюджет"}}
  ],
  "alternatives": [
    {{"name": "аты", "price": баға, "reason": "нақты неге балама", "cheaper": true}},
    {{"name": "аты", "price": баға, "reason": "нақты неге жақсырақ", "cheaper": false}}
  ]
}}

━━━ MODE: full_setup (толық конфигурация) ━━━
{{
  "mode": "full_setup",
  "name": "Сет атауы",
  "price": жалпы_баға,
  "reason": "Неге бұл конфигурация таңдалды — use_case пен бюджет негізінде 2 сөйлем",
  "use_case": "esports/streaming/creative/aaa/general",
  "performance_summary": "Нақты FPS болжамы: CS2: X FPS, Valorant: Y FPS, Cyberpunk 1440p: Z FPS",
  "bottleneck_note": "Осы конфигурацияда кем тұс немесе null",
  "upgrade_path": "Болашақта нені апгрейд жасау тиімді — 1 сөйлем немесе null",
  "gpu": "аты", "gpu_reason": "нақты неге — FPS немесе VRAM", "gpu_price": баға, "gpu_score": 0-100,
  "cpu": "аты", "cpu_reason": "нақты неге — ядро немесе 3D Cache", "cpu_price": баға, "cpu_score": 0-100,
  "ram": "аты", "ram_reason": "нақты неге — GB және DDR типі", "ram_price": баға,
  "ssd": "аты", "ssd_reason": "нақты неге — GB және NVMe", "ssd_price": баға,
  "monitor": "аты", "monitor_reason": "нақты неге — Hz және панель типі", "monitor_price": баға,
  "mouse": "аты", "mouse_reason": "нақты неге — сенсор немесе салмақ", "mouse_price": баға,
  "keyboard": "аты", "keyboard_reason": "нақты неге — switch немесе Rapid Trigger", "keyboard_price": баға,
  "headset": "аты", "headset_reason": "нақты неге — driver немесе wireless", "headset_price": баға,
  "gpu_alternatives": [
    {{"name": "аты", "price": баға, "reason": "нақты неге балама — баға/өнімділік", "type": "cheaper"}},
    {{"name": "аты", "price": баға, "reason": "жоғары бюджет болса — артықшылық", "type": "upgrade"}}
  ]
}}

═══════════════════════════════════════════════════════
МІНДЕТТІ ЕРЕЖЕЛЕР
═══════════════════════════════════════════════════════
- ТЕК каталогтағы тауарлар — каталогтан тыс ешнәрсе айтпа
- Бюджетті сыйла — 10% артық шек ғана рұқсат
- Қазақша жаз (техникалық терминдер ағылшынша болуы мүмкін)
- НАҚТЫ БОЛ — "жақсы" деп жазбай, "CS2-де 450+ FPS, VRAM 16GB болашаққа дайын" деп жаз
- Scores реалистикалық болсын: RTX 5060 → 65-70, RTX 5090 → 95, i5-12400F → 55
- vs/compare сұралса — vs_comparison міндетті түрде толтыр, winner анық атап өт
- top_3 single_product mode-та — бюджетке сай ең жақсы 3 нұсқа беру міндетті
- technical_specs — analysis mode-та GPU: VRAM/TDP, CPU: ядро/clock, Monitor: Hz/panel type
- full_setup mode-та gpu_alternatives МІНДЕТТІ — cheaper + upgrade нұсқалары
- gpu_alternatives ішіндегі барлық тауар атаулары каталогпен дәл сәйкес болуы тиіс
- Жауапта ```json немесе басқа markdown болмасын — тек таза JSON"""

    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY жоқ — локалды fallback қолданылады")
    try:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("no api key")
        import json as _json
        payload = _json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 3000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": text}]
        }).encode("utf-8")

        req = _ureq.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": ANTHROPIC_API_KEY,
            },
            method="POST"
        )

        with _ureq.urlopen(req, timeout=25) as resp:
            raw = _json.loads(resp.read().decode("utf-8"))

        content = raw.get("content", [{}])[0].get("text", "")
        # Strip markdown fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())
        result = _json.loads(content)
        return jsonify(result)

    except Exception as e:
        # Graceful fallback to local logic
        print(f"Claude API error: {e}")

    # ── 7. Fallback: local logic (if Claude unavailable) ──────────────────────
    if want_analysis and mentioned:
        cat_pool = {
            "gpu": all_gpus, "cpu": all_cpus, "ram": all_ram,
            "ssd": all_ssd, "monitor": all_monitors, "mouse": all_mice,
            "keyboard": all_keyboards, "headset": all_headsets,
        }.get(mentioned.get("category",""), all_gpus)

        alts = get_alternatives(cat_pool, mentioned["price"])
        alts = [a for a in alts if a["id"] != mentioned["id"]][:3]

        price = mentioned["price"]
        overall = 80
        if price > budget * 1.1: overall = 60
        elif price < budget * 0.5: overall = 72

        return jsonify({
            "mode": "analysis",
            "product_name": mentioned["name"],
            "price": price,
            "category_label": {"gpu":"Видеокарта","cpu":"Процессор","ram":"Жедел жад",
                               "ssd":"SSD","monitor":"Монитор","mouse":"Тышқан",
                               "keyboard":"Пернетақта","headset":"Құлаққап"}.get(mentioned.get("category",""), "Тауар"),
            "scores": {"overall": overall, "value_for_money": overall-5,
                       "performance": overall+3, "future_proof": overall-8, "reliability": 82},
            "analysis": explain_product(mentioned),
            "pros": ["Жақсы баға-сапа балансы", "CyberQazaq дүкенінде бар", "Кепілдік қамтамасыз етіледі"],
            "cons": ["Баламалары бар"],
            "use_cases": [{"label":"Gaming","fit":"great"},{"label":"Стриминг","fit":"good"}],
            "alternatives": [{"name":a["name"],"price":a["price"],
                              "reason":explain_product(a),
                              "cheaper":a["price"]<price} for a in alts],
        })

    # Category single-product fallback
    if len(detected_cats) == 1 and detected_cats[0] != "setup":
        cat = detected_cats[0]
        cat_items = {"gpu":all_gpus,"cpu":all_cpus,"ram":all_ram,"ssd":all_ssd,
                     "monitor":all_monitors,"mouse":all_mice,"keyboard":all_keyboards,"headset":all_headsets}[cat]
        mentioned_loc = find_mentioned(cat_items)
        target_price = mentioned_loc["price"] if mentioned_loc else budget
        within_budget = [p for p in cat_items if p["price"] <= budget]
        best = max(within_budget, key=lambda x: x["price"]) if within_budget else None
        alternatives = get_alternatives(cat_items, target_price)
        if mentioned_loc and mentioned_loc in alternatives:
            alternatives.remove(mentioned_loc)
        return jsonify({
            "mode": "single_product", "cat": cat, "use_case": use_case,
            "mentioned": {"name":mentioned_loc["name"],"price":mentioned_loc["price"],
                          "reason":explain_product(mentioned_loc)} if mentioned_loc else None,
            "best_match": {"name":best["name"],"price":best["price"],
                           "reason":explain_product(best)} if best else None,
            "alternatives": [{"name":p["name"],"price":p["price"],"reason":explain_product(p),
                               "cheaper":p["price"]<target_price} for p in alternatives[:3]],
        })

    # Full setup fallback
    setups = DATA.get("setups", [])
    def score_setup(s):
        n = s.get("name","").lower(); p = s.get("price",0); score = 0
        if p <= budget: score += 100
        if use_case == "esports" and any(w in n for w in ["pro","budget","студент"]): score += 20
        if use_case == "streaming" and any(w in n for w in ["pro","sheikh","ultra"]): score += 20
        if use_case == "creative" and any(w in n for w in ["sheikh","ultra"]): score += 20
        score -= abs(p - budget) / 100000; return score
    available = [s for s in setups if s.get("price",0) <= budget]
    best_setup = max(available, key=score_setup) if available else min(setups, key=lambda x: x.get("price",0))
    comps = best_setup.get("components",{})
    def tag_one(item, cat):
        if not item: return None
        d = dict(item); d["category"] = cat; return d
    cpu_it = tag_one(find_item(DATA.get("cpus",[]), comps.get("cpu")), "cpu")
    gpu_it = tag_one(find_item(DATA.get("gpus",[]), comps.get("gpu")), "gpu")
    ram_it = tag_one(find_item(DATA.get("ram",[]), comps.get("ram")), "ram")
    ssd_it = tag_one(find_item(DATA.get("ssd",[]), comps.get("ssd")), "ssd")
    mon_it = tag_one(find_item(DATA.get("monitors",[]), comps.get("monitor")), "monitor")
    mou_it = tag_one(find_item(DATA.get("mice",[]), comps.get("mouse")), "mouse")
    kbd_it = tag_one(find_item(DATA.get("keyboards",[]), comps.get("keyboard")), "keyboard")
    hds_it = tag_one(find_item(DATA.get("headsets",[]), comps.get("headset")), "headset")
    gpu_alts = get_alternatives(all_gpus, gpu_it["price"] if gpu_it else budget//3)[:2]
    reasons = {"esports":"CS2/Valorant үшін жоғары FPS беруге оптималданған.",
               "streaming":"Стриминг+gaming үшін тамаша баланс.",
               "creative":"4K рендеринг пен монтажға оптималданған.",
               "aaa":"Ауыр AAA ойындарды максималды баптауда ойнатады.",
               "general":"Бюджет пен өнімділікке сай ең тиімді сет."}
    return jsonify({
        "mode":"full_setup", "name":best_setup.get("name"), "price":best_setup.get("price"),
        "reason":reasons.get(use_case, reasons["general"]), "use_case":use_case,
        "budget_note": (f"Бюджетіңіз {budget:,} ₸. Ең арзан дайын сет {best_setup.get('price', 0):,} ₸ тұрады."
                        if best_setup.get("price", 0) > budget else None),
        "gpu":gpu_it.get("name") if gpu_it else "-", "gpu_reason":explain_product(gpu_it), "gpu_price":gpu_it.get("price") if gpu_it else 0,
        "cpu":cpu_it.get("name") if cpu_it else "-", "cpu_reason":explain_product(cpu_it), "cpu_price":cpu_it.get("price") if cpu_it else 0,
        "ram":ram_it.get("name") if ram_it else "-", "ram_reason":explain_product(ram_it), "ram_price":ram_it.get("price") if ram_it else 0,
        "ssd":ssd_it.get("name") if ssd_it else "-", "ssd_reason":explain_product(ssd_it), "ssd_price":ssd_it.get("price") if ssd_it else 0,
        "monitor":mon_it.get("name") if mon_it else "-", "monitor_reason":explain_product(mon_it), "monitor_price":mon_it.get("price") if mon_it else 0,
        "mouse":mou_it.get("name") if mou_it else "-", "mouse_reason":explain_product(mou_it), "mouse_price":mou_it.get("price") if mou_it else 0,
        "keyboard":kbd_it.get("name") if kbd_it else "-", "keyboard_reason":explain_product(kbd_it), "keyboard_price":kbd_it.get("price") if kbd_it else 0,
        "headset":hds_it.get("name") if hds_it else "-", "headset_reason":explain_product(hds_it), "headset_price":hds_it.get("price") if hds_it else 0,
        "gpu_alternatives":[{"name":p["name"],"price":p["price"],"reason":explain_product(p)}
                             for p in gpu_alts if not gpu_it or p["id"]!=gpu_it.get("id")],
    })




@app.route("/product-image/<path:filename>")
def product_image(filename):
    """Serve product images from static folder, or return SVG placeholder if not found."""
    # Look in static/products/ first (product images), then static/
    for subdir in ["products", ""]:
        p = Path(__file__).parent / "static" / subdir / filename if subdir else Path(__file__).parent / "static" / filename
        if p.exists():
            return send_file(p)
    label = filename.replace(".jpg","").replace(".png","").replace("_"," ").replace("-"," ")[:28]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">' +
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0%" stop-color="#0a0a1a"/>' +
        '<stop offset="100%" stop-color="#111827"/>' +
        '</linearGradient></defs>' +
        '<rect width="400" height="300" fill="url(#bg)" rx="12"/>' +
        '<rect x="1" y="1" width="398" height="298" fill="none" stroke="#1f2937" stroke-width="2" rx="12"/>' +
        f'<text x="200" y="140" text-anchor="middle" font-family="Inter,sans-serif" font-size="14" fill="#9ca3af">{label}</text>' +
        '<text x="200" y="165" text-anchor="middle" font-family="Inter,sans-serif" font-size="11" fill="#4b5563">CyberQazaq</text>' +
        '</svg>'
    )
    from flask import Response
    return Response(svg, mimetype="image/svg+xml")



ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = _require_env("ADMIN_PASS")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        data = request.get_json() or {}
        if (hmac.compare_digest(str(data.get("user", "")), ADMIN_USER)
                and hmac.compare_digest(str(data.get("pass", "")), ADMIN_PASS)):
            session["admin"] = True
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Логин немесе пароль қате"}), 401
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

@app.route("/admin")
def admin():
    # Allow access - login page handles authentication
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return render_template("admin.html")

@app.route("/api/admin-data")
def admin_data():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(DATA)


@app.route("/order/pdf", methods=["POST"])
def order_pdf():
    """Generate and return a PDF receipt for the order."""
    import io
    if not PDF_ENABLED:
        return jsonify({"error": "PDF not available. Run: pip install reportlab"}), 503
    body = request.get_json() or {}
    pdf_bytes = generate_order_pdf(body)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"CyberQazaq-{body.get('order_num','order')}.pdf"
    )

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Debug тек FLASK_DEBUG=1 болғанда; әдепкіде localhost-та ғана тыңдайды
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1" if debug else "0.0.0.0", port=5000, debug=debug)
