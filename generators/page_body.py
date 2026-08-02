"""
Perakit isi halaman.

Body HTML dipakai bersama oleh versi biasa dan versi AMP supaya
kedua halaman benar-benar menyajikan konten yang sama. Google
memperlakukan versi AMP yang isinya berbeda dari halaman
kanoniknya sebagai pelanggaran, jadi keduanya wajib dirender dari
sumber yang satu ini.
"""

from generators.html_utils import escape, heading_id


def render_header(brand: dict) -> str:
    return f"""
<header class="site-header">
  <div class="wrap">
    <a class="brand" href="/">{escape(brand["site_name"])}</a>
    <nav class="site-nav">
      <a href="/">Beranda</a>
      <a href="#faq">FAQ</a>
    </nav>
  </div>
</header>
""".strip()


def render_hero(plan: dict) -> str:
    intro_html = "\n      ".join(
        f"<p>{escape(paragraph)}</p>"
        for paragraph in plan.get("intro", [])
    )

    return f"""
<div class="hero">
    <div class="wrap">
      <h1>{escape(plan["h1"])}</h1>
      {intro_html}
    </div>
  </div>
""".strip()


def render_toc(plan: dict) -> str:
    """
    Daftar isi dengan anchor ke tiap section.

    Selain membantu pembaca, anchor ini juga memberi Google
    kandidat jump-to link di hasil pencarian.
    """
    sections = plan.get("sections", [])

    if len(sections) < 3:
        return ""

    items = "\n        ".join(
        f'<li><a href="#{heading_id(section["heading"])}">'
        f'{escape(section["heading"])}</a></li>'
        for section in sections
    )

    return f"""
<nav class="toc" aria-label="Daftar isi">
        <strong>Daftar Isi</strong>
        <ol>
        {items}
        </ol>
      </nav>
""".strip()


def render_list_items(items: list[str]) -> str:
    return "\n        ".join(
        f"<li>{escape(item)}</li>" for item in items
    )


def render_table(items: list[str]) -> str:
    """
    Merender daftar poin jadi tabel bernomor.

    Format "Judul: penjelasan" dipecah jadi dua kolom supaya
    tabelnya informatif, bukan cuma daftar yang dikotak-kotakkan.
    """
    rows = []

    for index, item in enumerate(items, start=1):
        if ":" in item:
            left, right = item.split(":", 1)
        else:
            left, right = item, ""

        rows.append(
            f"<tr><td>{index}</td>"
            f"<td><strong>{escape(left.strip())}</strong></td>"
            f"<td>{escape(right.strip())}</td></tr>"
        )

    body = "\n          ".join(rows)

    return f"""
<div class="table-wrap">
        <table>
          <thead>
            <tr><th>#</th><th>Poin</th><th>Keterangan</th></tr>
          </thead>
          <tbody>
          {body}
          </tbody>
        </table>
      </div>
""".strip()


def render_section(section: dict) -> str:
    heading = section["heading"]
    anchor = heading_id(heading)

    paragraphs = "\n      ".join(
        f"<p>{escape(paragraph)}</p>"
        for paragraph in section["paragraphs"]
    )

    items = section.get("items", [])
    extra = ""

    if section["type"] == "list" and items:
        extra = (
            '<ul class="check">\n        '
            + render_list_items(items)
            + "\n      </ul>"
        )

    elif section["type"] == "steps" and items:
        extra = (
            '<ol class="steps">\n        '
            + render_list_items(items)
            + "\n      </ol>"
        )

    elif section["type"] == "table" and items:
        extra = render_table(items)

    elif section["type"] == "cta":
        extra = ""

    body = f"""
<h2 id="{anchor}">{escape(heading)}</h2>
      {paragraphs}
      {extra}
""".strip()

    if section["type"] == "cta":
        return f"""
<section class="block">
    <div class="wrap">
      <div class="cta-box">
        {body}
      </div>
    </div>
  </section>
""".strip()

    return f"""
<section class="block">
    <div class="wrap">
      {body}
    </div>
  </section>
""".strip()


def render_faq(faq: list[dict]) -> str:
    if not faq:
        return ""

    items = "\n      ".join(
        f'<div class="faq-item">'
        f'<h3>{escape(item["question"])}</h3>'
        f'<p>{escape(item["answer"])}</p>'
        f"</div>"
        for item in faq
    )

    return f"""
<section class="block" id="faq">
    <div class="wrap">
      <h2>Pertanyaan Yang Sering Diajukan</h2>
      {items}
    </div>
  </section>
""".strip()


def render_footer(
    brand: dict,
    plan: dict,
) -> str:
    disclaimer = brand.get("disclaimer", "")

    disclaimer_html = (
        f'<p class="disclaimer">{escape(disclaimer)}</p>'
        if disclaimer
        else ""
    )

    keywords = ", ".join(plan.get("keywords", [])[:8])

    keywords_html = (
        f"<p>Topik terkait: {escape(keywords)}</p>"
        if keywords
        else ""
    )

    return f"""
<footer class="site-footer">
  <div class="wrap">
    {keywords_html}
    <p>&copy; {escape(brand["year"])} {escape(brand["site_name"])}.
       Seluruh hak cipta dilindungi.</p>
    {disclaimer_html}
  </div>
</footer>
""".strip()


def render_body(
    plan: dict,
    brand: dict,
) -> str:
    """
    Merakit seluruh isi halaman jadi satu blok HTML.
    """
    sections_html = "\n\n  ".join(
        render_section(section)
        for section in plan.get("sections", [])
    )

    toc = render_toc(plan)

    toc_block = (
        f'<section class="block">\n    <div class="wrap">\n      '
        f"{toc}\n    </div>\n  </section>"
        if toc
        else ""
    )

    return f"""
{render_header(brand)}

  {render_hero(plan)}

  <main>
  {toc_block}

  {sections_html}

  {render_faq(plan.get("faq", []))}
  </main>

  {render_footer(brand, plan)}
""".strip()
