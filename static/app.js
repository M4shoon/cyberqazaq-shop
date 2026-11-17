// ─── AI BUILDER ───────────────────────────────────────────────────────────────

async function getAI() {
    const budget    = document.getElementById("budget").value;
    const request   = document.getElementById("request").value;
    const resultBox = document.getElementById("result");

    if (!budget || !request) {
        resultBox.innerHTML = `<div class="result-card"><p>Бюджет пен сұранысты толтыр.</p></div>`;
        return;
    }

    resultBox.innerHTML = `<div class="result-card"><p>AI ойланып жатыр...</p></div>`;

    try {
        const res  = await fetch("/ai", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ budget: Number(budget), request })
        });
        const data = await res.json();

        resultBox.innerHTML = `
            <div class="result-card">
                <h3>${data.name}</h3>
                <p><strong>Бағасы:</strong> ${data.price} ₸</p>
                <p><strong>Себебі:</strong> ${data.reason}</p>
                <div class="setup-specs">
                    <div class="setup-spec"><span>💻 CPU</span>     <b>${data.cpu}</b>      <small>${data.cpu_reason}</small></div>
                    <div class="setup-spec"><span>🎮 GPU</span>     <b>${data.gpu}</b>      <small>${data.gpu_reason}</small></div>
                    <div class="setup-spec"><span>🧠 RAM</span>     <b>${data.ram}</b>      <small>${data.ram_reason}</small></div>
                    <div class="setup-spec"><span>💾 SSD</span>     <b>${data.ssd}</b>      <small>${data.ssd_reason}</small></div>
                    <div class="setup-spec"><span>🖥 Monitor</span> <b>${data.monitor}</b>  <small>${data.monitor_reason}</small></div>
                    <div class="setup-spec"><span>🖱 Mouse</span>   <b>${data.mouse}</b>    <small>${data.mouse_reason}</small></div>
                    <div class="setup-spec"><span>⌨️ Keyboard</span><b>${data.keyboard}</b> <small>${data.keyboard_reason}</small></div>
                    <div class="setup-spec"><span>🎧 Headset</span> <b>${data.headset}</b>  <small>${data.headset_reason}</small></div>
                </div>
            </div>`;
    } catch (e) {
        resultBox.innerHTML = `<div class="result-card"><p>Қате шықты. Серверді тексер.</p></div>`;
    }
}

// ─── SIDEBAR MENU TOGGLE ──────────────────────────────────────────────────────
// FIX: old toggleMenu() looked for id="categoryArrow" which never existed,
//      and no button had onclick at all. Replaced with a generic toggleSection()
//      that each button calls, passing itself so it works for both levels.

function toggleSection(btn) {
    // The content to collapse is the next sibling div after the button
    const content = btn.nextElementSibling;
    if (!content) return;

    const isOpen = content.style.display !== "none";

    content.style.display = isOpen ? "none" : "block";
    btn.textContent        = isOpen ? "›"    : "⌄";
}

// On load: make sure both levels start open (visible)
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".menu-arrow").forEach(btn => {
        const content = btn.nextElementSibling;
        if (content) content.style.display = "block";
        btn.textContent = "⌄";
    });
});

// ─── CATEGORY FILTER ─────────────────────────────────────────────────────────

function filterCategory(category, btn) {
    const sections = document.querySelectorAll(".category-section");
    const buttons  = document.querySelectorAll(".nav-item");

    buttons.forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");

    sections.forEach(section => {
        section.style.display =
            (category === "all" || section.dataset.category === category)
                ? "block"
                : "none";
    });
}

// ─── NEON CLICK EFFECT ────────────────────────────────────────────────────────

function enableNeonClick(selector) {
    document.querySelectorAll(selector).forEach(item => {
        item.addEventListener("click", function () {
            document.querySelectorAll(selector).forEach(el => el.classList.remove("neon-active"));
            this.classList.add("neon-active");
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    enableNeonClick(".nav-item");
    enableNeonClick(".spec-item");
    enableNeonClick(".card");
});

// ─── CART ─────────────────────────────────────────────────────────────────────

let cart = JSON.parse(localStorage.getItem("cart")) || [];

function saveCart() {
    localStorage.setItem("cart", JSON.stringify(cart));
}

function toggleCart() {
    document.getElementById("cartPanel").classList.toggle("active");
    document.getElementById("cartOverlay").classList.toggle("active");
}

function updateCartUI() {
    const cartCount = document.getElementById("cartCount");
    const cartItems = document.getElementById("cartItems");
    const cartTotal = document.getElementById("cartTotal");

    if (!cartCount || !cartItems || !cartTotal) return;

    cartCount.textContent = cart.length;

    if (cart.length === 0) {
        cartItems.innerHTML    = `<p class="empty-cart">Себет бос</p>`;
        cartTotal.textContent  = "0";
        return;
    }

    let total = 0;
    cartItems.innerHTML = cart.map((item, index) => {
        total += item.price;
        return `
            <div class="cart-item">
                <div class="cart-item-info">
                    <h4>${item.name}</h4>
                    <p>${item.price.toLocaleString()} ₸</p>
                </div>
                <button class="remove-btn" onclick="removeFromCart(${index})">Өшіру</button>
            </div>`;
    }).join("");

    cartTotal.textContent = total.toLocaleString();
}

function removeFromCart(index) {
    cart.splice(index, 1);
    saveCart();
    updateCartUI();
}

function initCartButtons() {
    document.querySelectorAll(".cart-btn").forEach(button => {
        button.addEventListener("click", () => {
            const card = button.closest(".product-card");
            if (!card) return;

            const name      = card.querySelector("h3")?.textContent.trim() || "Товар";
            const priceText = card.querySelector(".price")?.textContent || "0";
            const price     = Number(priceText.replace(/[^\d]/g, ""));

            cart.push({ name, price });
            saveCart();
            updateCartUI();

            button.textContent = "Қосылды ✓";
            setTimeout(() => { button.textContent = "Себетке қосу"; }, 1200);
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initCartButtons();
    updateCartUI();
});

// ─── FAVOURITES ───────────────────────────────────────────────────────────────

let favorites = JSON.parse(localStorage.getItem("favorites")) || [];

// FIX: original code ran favButtons.forEach at top-level before DOMContentLoaded,
//      so card.dataset.name crashed when cards didn't exist yet on some page loads.
document.addEventListener("DOMContentLoaded", () => {
    updateFavCount();

    document.querySelectorAll(".fav-btn").forEach(btn => {
        const card  = btn.closest(".product-card");
        if (!card) return;

        const name  = card.dataset.name;
        const price = card.dataset.price;

        if (favorites.find(item => item.name === name)) {
            btn.classList.add("active");
            btn.innerHTML = "❤️";
        }

        btn.addEventListener("click", () => {
            const exists = favorites.find(item => item.name === name);

            if (exists) {
                favorites = favorites.filter(item => item.name !== name);
                btn.classList.remove("active");
                btn.innerHTML = "❤";
            } else {
                favorites.push({ name, price });
                btn.classList.add("active");
                btn.innerHTML = "❤️";
            }

            localStorage.setItem("favorites", JSON.stringify(favorites));
            updateFavCount();
        });
    });
});

function updateFavCount() {
    const count = document.getElementById("favCount");
    if (count) count.innerText = favorites.length;
}

// ─── SEARCH ───────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("searchInput");
    if (!searchInput) return;

    searchInput.addEventListener("input", () => {
        const value = searchInput.value.toLowerCase();

        document.querySelectorAll(".product-card").forEach(card => {
            const name = (card.dataset.name || "").toLowerCase();
            card.style.display = name.includes(value) ? "block" : "none";
        });
    });
});


// ── PDF Receipt Download ────────────────────────────────────
async function downloadOrderPDF(orderData) {
  try {
    const res = await fetch('/order/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(orderData)
    });
    if (!res.ok) throw new Error('PDF error');
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `CyberQazaq-${orderData.order_num}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) {
    console.error('PDF жүктеу қатесі:', e);
  }
}

// Show PDF download button after successful order
function showOrderSuccess(orderData) {
  // Remove existing success banners
  document.querySelectorAll('.order-success-banner').forEach(el => el.remove());

  const banner = document.createElement('div');
  banner.className = 'order-success-banner';
  banner.style.cssText = `
    position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
    background:#111827; border:1px solid #7c3aed; border-radius:24px;
    padding:40px 48px; z-index:99999; text-align:center;
    box-shadow:0 0 60px rgba(168,85,247,0.3); max-width:420px; width:90%;
  `;
  banner.innerHTML = `
    <div style="font-size:52px;margin-bottom:16px;">✅</div>
    <h2 style="font-size:22px;font-weight:800;color:white;margin-bottom:8px;">
      Тапсырыс қабылданды!
    </h2>
    <p style="color:#6b7280;margin-bottom:6px;">Тапсырыс нөмірі:</p>
    <p style="font-size:20px;font-weight:900;color:#d8b4fe;margin-bottom:24px;">
      #${orderData.order_num}
    </p>
    <p style="color:#9ca3af;font-size:14px;margin-bottom:28px;">
      Жақын арада WhatsApp арқылы хабарласамыз.<br>
      Тапсырыс квитанциясын PDF форматында жүктей аласыз.
    </p>
    <button onclick="downloadOrderPDF(${JSON.stringify(orderData).replace(/"/g,'&quot;')})" style="
      width:100%; padding:14px; border:none; border-radius:14px;
      background:linear-gradient(90deg,#7c3aed,#c026d3); color:white;
      font-weight:700; font-size:15px; cursor:pointer; margin-bottom:10px;
      box-shadow:0 0 18px rgba(168,85,247,0.25);
    ">📄 PDF Квитанция жүктеу</button>
    <button onclick="this.closest('.order-success-banner').remove();document.querySelector('.cart-overlay')?.classList.remove('active');" style="
      width:100%; padding:12px; border:1px solid rgba(255,255,255,0.1);
      border-radius:14px; background:rgba(255,255,255,0.05);
      color:#9ca3af; font-weight:600; font-size:14px; cursor:pointer;
    ">Жабу</button>
  `;

  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:99998;backdrop-filter:blur(4px);';
  overlay.onclick = () => { banner.remove(); overlay.remove(); };

  document.body.appendChild(overlay);
  document.body.appendChild(banner);
}
