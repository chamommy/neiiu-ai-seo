"""
Pustaka blok halaman.

Halaman baru tidak lagi dirakit dari satu fungsi panjang, tapi dari
blok-blok yang berdiri sendiri di sini. Blok mana saja yang dipasang
ditentukan DNA desain (lihat `inspiration.py`), jadi halaman acuan
yang punya bilah mengambang menghasilkan halaman baru yang juga
punya bilah mengambang, tanpa satu baris pun HTML mereka ikut
tersalin.

Semua blok menerima `amp`. Bedanya bukan kosmetik:

- Popup memakai kotak centang tersembunyi supaya bisa ditutup tanpa
  JavaScript sama sekali. AMP melarang `<input>` di luar amp-form,
  jadi di versi AMP blok ini tidak dipasang.
- Bilah mengambang memakai `position: fixed`, dan AMP hanya
  mengizinkan itu untuk segelintir elemen bawaannya. Di versi AMP
  bilahnya tetap ada, tapi duduk di akhir halaman sebagai bilah
  biasa.
- Tidak ada satu pun atribut `style` maupun `onclick` di berkas ini.
  Besar bintang penilaian ditentukan kelas `st-NN`, bukan variabel
  CSS sebaris, karena atribut `style` melanggar AMP.
"""

from generators.html_utils import escape
from generators.page_text import text_of


def rating_class(value: float) -> str:
    """
    Mengubah angka penilaian jadi nama kelas lebar bintang.

    Dibulatkan ke satu angka di belakang koma, lalu dijepit di
    rentang 3.0–5.0. Nilai di luar itu bukan penilaian yang masuk
    akal untuk ditampilkan, dan tanpa penjepitan kelasnya tidak
    punya padanan di CSS sehingga bintangnya hilang sama sekali.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 5.0

    number = max(3.0, min(5.0, number))

    return f"st-{round(number * 10)}"


def render_stars(value: float, brand: dict) -> str:
    """
    Satu baris bintang beserta angkanya untuk pembaca layar.
    """
    words = text_of(brand)

    try:
        shown = f"{float(value):.1f}"
    except (TypeError, ValueError):
        shown = "5.0"

    label = f"{shown} {words['out_of_5']}"

    return (
        f'<span class="stars {rating_class(value)}" '
        f'role="img" aria-label="{escape(label)}"></span>'
    )


def cta_link(brand: dict) -> str:
    """
    Alamat tujuan tombol ajakan.

    Kalau tidak diisi, tombolnya menunjuk ke beranda situs itu
    sendiri. Menunjuk ke "#" akan membuat seluruh tombol halaman
    terlihat rusak.
    """
    return (
        str(brand.get("cta_url") or "").strip()
        or (brand.get("base_url", "") + "/")
    )


def cta_attrs(brand: dict) -> str:
    """
    Atribut tautan keluar untuk tombol ajakan.

    `nofollow` dipasang karena tautan ini komersial dan bukan
    rujukan editorial; `noopener` menutup akses halaman tujuan ke
    `window.opener`.
    """
    target = cta_link(brand)

    if target.startswith(brand.get("base_url", "\0")):
        return f'href="{escape(target)}"'

    return (
        f'href="{escape(target)}" target="_blank" '
        'rel="nofollow noopener"'
    )


def section_links(plan: dict, limit: int = 8) -> list[tuple[str, str]]:
    """
    Daftar (judul, anchor) dari section yang sudah punya anchor.

    Anchor diberikan `page_body.assign_anchors` sebelum blok apa pun
    dirender, jadi menu, tag, dan footer semuanya menunjuk ke id yang
    benar-benar ada di halaman.
    """
    result: list[tuple[str, str]] = []

    for section in plan.get("sections", [])[:limit]:
        anchor = section.get("_anchor")
        heading = section.get("heading", "")

        if anchor and heading:
            result.append((heading, anchor))

    return result


def render_navbar(plan: dict, brand: dict) -> str:
    """
    Kepala halaman: nama brand, menu kategori, dan tombol daftar.
    """
    words = text_of(brand)
    links = section_links(plan, limit=6)

    items = "\n        ".join(
        f'<a href="#{escape(anchor)}">{escape(heading)}</a>'
        for heading, anchor in links
    )

    return f"""
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/">{escape(brand["site_name"])}</a>
    <nav class="site-nav" aria-label="{escape(words["menu_label"])}">
        {items}
        <a href="#faq">{escape(words["faq_nav"])}</a>
    </nav>
    <a class="nav-cta" {cta_attrs(brand)}>{escape(words["cta_register"])}</a>
  </div>
</header>
""".strip()


def render_cta_duo(brand: dict) -> str:
    """
    Sepasang tombol besar login dan daftar.
    """
    words = text_of(brand)
    attrs = cta_attrs(brand)

    return f"""
<div class="cta-duo">
      <a class="cta-btn cta-login" {attrs}>{escape(words["cta_login"])}</a>
      <a class="cta-btn cta-reg" {attrs}>{escape(words["cta_register"])}</a>
    </div>
""".strip()


def render_floatbar(brand: dict, amp: bool = False) -> str:
    """
    Bilah menu cepat.

    Di halaman kanonik ia mengambang di bawah layar. Di AMP ia
    dipasang sebagai bilah biasa di akhir halaman, karena AMP hanya
    mengizinkan `position: fixed` untuk elemen bawaannya sendiri.
    """
    words = text_of(brand)
    attrs = cta_attrs(brand)

    labels = (
        words["cta_promo"],
        words["cta_login"],
        words["cta_register"],
        words["cta_alt"],
        words["cta_chat"],
    )

    items = "\n    ".join(
        f'<a class="fb-item" {attrs}>{escape(label)}</a>'
        for label in labels
    )

    kind = "floatbar floatbar-static" if amp else "floatbar"

    return f"""
<nav class="{kind}" aria-label="{escape(words["quick_menu_label"])}">
    {items}
  </nav>
""".strip()


def render_popup(plan: dict, brand: dict, amp: bool = False) -> str:
    """
    Popup pembuka berisi tombol login dan daftar.

    Dibuka lewat kotak centang tersembunyi yang sudah tercentang,
    dan ditutup lewat label yang menunjuk balik ke kotak itu. Tidak
    ada JavaScript sama sekali, jadi popupnya tetap bisa ditutup di
    peramban yang memblokir skrip.

    Versi AMP tidak memakainya: `<input>` di luar amp-form membuat
    halaman AMP langsung tidak valid.
    """
    if amp:
        return ""

    words = text_of(brand)
    attrs = cta_attrs(brand)

    return f"""
<input class="pop-switch" id="pop-switch" type="checkbox" checked>
  <div class="pop-overlay">
    <div class="pop-card">
      <label class="pop-close" for="pop-switch"
             aria-label="{escape(words["popup_close"])}"></label>
      <p class="pop-title">{escape(plan["h1"])}</p>
      <div class="pop-actions">
        <a class="cta-btn cta-login" {attrs}>{escape(words["cta_login"])}</a>
        <a class="cta-btn cta-reg" {attrs}>{escape(words["cta_register"])}</a>
      </div>
      <p class="pop-foot">&copy; {escape(brand["year"])}
         {escape(brand["site_name"])}</p>
    </div>
  </div>
""".strip()


def render_ratings(plan: dict, brand: dict) -> str:
    """
    Baris penilaian layanan.

    Angkanya berasal dari rencana konten, bukan dikarang di sini,
    supaya angka yang tampil di halaman sama persis dengan angka
    yang masuk ke structured data.
    """
    words = text_of(brand)
    ratings = plan.get("ratings", [])

    if not ratings:
        return ""

    parts: list[str] = []

    for item in ratings:
        try:
            shown = f"{float(item['value']):.1f}"
        except (TypeError, ValueError, KeyError):
            continue

        parts.append(
            '<div class="rate-card">'
            f'<div class="rate-name">{escape(item.get("label", ""))}</div>'
            f"{render_stars(item['value'], brand)}"
            f'<div class="rate-value">{escape(shown)} '
            f'{escape(words["out_of_5"])}</div>'
            "</div>"
        )

    if not parts:
        return ""

    cards = "\n      ".join(parts)

    return f"""
<section class="block ratings" aria-label="{escape(words["ratings_heading"])}">
    <div class="wrap">
      <h2>{escape(words["ratings_heading"])}</h2>
      <div class="rate-grid">
      {cards}
      </div>
    </div>
  </section>
""".strip()


def render_testimoni(plan: dict, brand: dict) -> str:
    """
    Kartu ulasan member.
    """
    words = text_of(brand)

    # Ulasan yang tidak lengkap dilewati, bukan dirender setengah
    # jadi. Jalur template menghasilkan ulasan berbentuk lain, dan
    # kartu tanpa nama atau tanpa isi tidak ada gunanya di halaman.
    reviews = [
        item
        for item in plan.get("reviews", [])
        if isinstance(item, dict) and item.get("name") and item.get("text")
    ]

    if not reviews:
        return ""

    heading = f'{words["testimoni_heading"]} {brand["site_name"]}'

    cards = "\n      ".join(
        f'<article class="rev-card">'
        f'<div class="rev-head">'
        f'<span class="rev-name">{escape(item["name"])}</span>'
        f'<span class="rev-date">{escape(item.get("date", ""))}</span>'
        f"{render_stars(item.get('rating', 5), brand)}"
        f"</div>"
        f'<p class="rev-text">{escape(item["text"])}</p>'
        f"</article>"
        for item in reviews
    )

    return f"""
<section class="block reviews" id="ulasan">
    <div class="wrap">
      <h2>{escape(heading)}</h2>
      <div class="rev-grid">
      {cards}
      </div>
    </div>
  </section>
""".strip()


def render_tags(plan: dict, brand: dict) -> str:
    """
    Deretan pil topik.

    Tiap pil menunjuk ke section di halaman ini, bukan ke luar.
    Tautan yang semuanya menunjuk ke satu alamat yang sama adalah
    pola yang gampang dikenali, dan tidak membantu pembaca sedikit
    pun.
    """
    words = text_of(brand)
    keywords = [word for word in plan.get("keywords", []) if word][:12]

    if not keywords:
        return ""

    links = section_links(plan, limit=12)

    if not links:
        return ""

    pills = "\n        ".join(
        f'<a class="pill" href="#{escape(links[index % len(links)][1])}">'
        f"{escape(word)}</a>"
        for index, word in enumerate(keywords)
    )

    return f"""
<section class="block tags">
    <div class="wrap">
      <h2>{escape(words["tags_heading"])}</h2>
      <nav class="pill-row" aria-label="{escape(words["tags_heading"])}">
        {pills}
      </nav>
    </div>
  </section>
""".strip()


def render_footer_sitemap(plan: dict, brand: dict) -> str:
    """
    Footer bertingkat berisi kolom tautan.
    """
    words = text_of(brand)
    links = section_links(plan, limit=6)
    keywords = [word for word in plan.get("keywords", []) if word][:6]

    page_column = "\n          ".join(
        f'<a href="#{escape(anchor)}">{escape(heading)}</a>'
        for heading, anchor in links
    )

    topic_column = "\n          ".join(
        f'<a href="#{escape(links[index % len(links)][1])}">{escape(word)}</a>'
        for index, word in enumerate(keywords)
    ) if links else ""

    disclaimer = brand.get("disclaimer", "")

    disclaimer_html = (
        f'<p class="disclaimer">{escape(disclaimer)}</p>'
        if disclaimer
        else ""
    )

    return f"""
<footer class="site-footer">
  <div class="wrap">
    <div class="foot-grid">
      <div class="foot-col foot-brand">
        <span class="brand">{escape(brand["site_name"])}</span>
        <a class="cta-btn cta-reg" {cta_attrs(brand)}>
          {escape(words["cta_register"])}</a>
      </div>
      <div class="foot-col">
        <h3>{escape(words["footer_page"])}</h3>
        <div class="foot-links">
          {page_column}
        </div>
      </div>
      <div class="foot-col">
        <h3>{escape(words["footer_topics"])}</h3>
        <div class="foot-links">
          {topic_column}
        </div>
      </div>
      <div class="foot-col">
        <h3>{escape(words["footer_explore"])}</h3>
        <div class="foot-links">
          <a href="/">{escape(words["home"])}</a>
          <a href="#faq">{escape(words["faq_nav"])}</a>
          <a href="#ulasan">{escape(words["reviews_heading"])}</a>
        </div>
      </div>
    </div>
    <p class="foot-legal">&copy; {escape(brand["year"])}
       {escape(brand["site_name"])}. {escape(words["rights_reserved"])}</p>
    {disclaimer_html}
  </div>
</footer>
""".strip()
