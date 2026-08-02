"""
Pembuat CSS halaman hasil generate.

CSS ditulis ulang dari design token kompetitor (warna, font,
radius), bukan disalin dari stylesheet mereka. Selain soal hak
cipta, CSS bundle situs besar hampir selalu jauh melewati batas
75KB milik AMP, jadi menyalinnya akan langsung membuat halaman
AMP invalid.

Aturan yang dijaga supaya lolos AMP:
- tanpa !important
- tanpa @import dan font eksternal
- tanpa -moz-binding atau behavior
- ukuran akhir jauh di bawah 75KB
"""

from generators.html_utils import minify_css


from utils.region import DEFAULT_REGION, font_stack

SYSTEM_FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)


def build_font_stack(
    fonts: list[str],
    region: str = DEFAULT_REGION,
) -> str:
    """
    Menyusun font stack dari font kompetitor.

    Font tetap dipanggil lewat nama saja tanpa @font-face, jadi
    tidak ada request eksternal dan halaman tetap cepat.

    Cadangan milik zona selalu ikut di belakang. Font Latin yang
    ditiru dari kompetitor Indonesia tidak punya aksara Thai sama
    sekali, dan halaman Thai yang memakainya tampil sebagai deretan
    kotak kosong di sebagian perangkat.
    """
    clean = [font for font in fonts[:2] if font]

    return font_stack(clean, region)


def build_css(
    design: dict,
    amp: bool = False,
    region: str = DEFAULT_REGION,
) -> str:
    """
    Menghasilkan CSS lengkap untuk satu halaman.
    """
    palette = design.get("palette", {})
    fonts = design.get("fonts", [])
    radius = int(design.get("radius", 12))

    background = palette.get("background", "#0b0f19")
    surface = palette.get("surface", "#151b2b")
    text = palette.get("text", "#e8ecf5")
    muted = palette.get("muted", "#9aa4bd")
    border = palette.get("border", "#252d42")
    accent = palette.get("accent", "#f5b301")
    accent_2 = palette.get("accent_2", accent)
    accent_text = palette.get("accent_text", "#0b0f19")

    fonts_css = build_font_stack(fonts, region)

    css = f"""
:root {{
  --bg: {background};
  --surface: {surface};
  --text: {text};
  --muted: {muted};
  --border: {border};
  --accent: {accent};
  --accent-2: {accent_2};
  --accent-text: {accent_text};
  --radius: {radius}px;
  --max-width: 1080px;
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: {fonts_css};
  font-size: 17px;
  line-height: 1.75;
  -webkit-text-size-adjust: 100%;
}}

.wrap {{
  width: 100%;
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 0 20px;
}}

a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

.site-header {{
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  padding: 14px 0;
}}

.site-header .wrap {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}}

.brand {{
  font-weight: 700;
  font-size: 20px;
  color: var(--text);
  letter-spacing: 0.3px;
}}

.site-nav a {{
  color: var(--muted);
  margin-left: 18px;
  font-size: 15px;
}}

.hero {{
  padding: 56px 0 40px;
  background: linear-gradient(180deg, var(--surface), var(--bg));
  border-bottom: 1px solid var(--border);
}}

.hero h1 {{
  margin: 0 0 16px;
  font-size: 34px;
  line-height: 1.25;
  letter-spacing: -0.5px;
}}

.hero p {{
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 18px;
  max-width: 780px;
}}

.btn {{
  display: inline-block;
  margin-top: 12px;
  padding: 13px 26px;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-text);
  font-weight: 700;
  font-size: 16px;
}}

.btn:hover {{ background: var(--accent-2); text-decoration: none; }}

main {{ padding: 12px 0 40px; }}

section.block {{
  padding: 34px 0;
  border-bottom: 1px solid var(--border);
}}

section.block:last-of-type {{ border-bottom: 0; }}

h2 {{
  font-size: 26px;
  line-height: 1.3;
  margin: 0 0 14px;
  letter-spacing: -0.3px;
}}

h3 {{
  font-size: 19px;
  margin: 22px 0 8px;
}}

p {{ margin: 0 0 14px; }}

.toc {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 22px;
  margin: 26px 0;
}}

.toc strong {{ display: block; margin-bottom: 8px; font-size: 16px; }}
.toc ol {{ margin: 0; padding-left: 20px; }}
.toc li {{ margin-bottom: 5px; }}

ul.check {{ list-style: none; margin: 0 0 14px; padding: 0; }}

ul.check li {{
  position: relative;
  padding: 10px 0 10px 30px;
  border-bottom: 1px solid var(--border);
}}

ul.check li:before {{
  content: "\\2713";
  position: absolute;
  left: 4px;
  top: 10px;
  color: var(--accent);
  font-weight: 700;
}}

ol.steps {{ margin: 0 0 14px; padding-left: 22px; }}
ol.steps li {{ margin-bottom: 10px; }}

.table-wrap {{ overflow-x: auto; margin: 0 0 14px; }}

table {{
  width: 100%;
  border-collapse: collapse;
  min-width: 420px;
  font-size: 16px;
}}

th, td {{
  text-align: left;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}}

th {{
  background: var(--surface);
  color: var(--text);
  font-weight: 700;
}}

td:first-child {{ color: var(--accent); font-weight: 600; width: 64px; }}

.cta-box {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: var(--radius);
  padding: 22px 24px;
}}

.faq-item {{
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  margin-bottom: 12px;
  padding: 4px 20px;
}}

.faq-item h3 {{ margin: 16px 0 8px; font-size: 17px; }}
.faq-item p {{ color: var(--muted); }}

.site-footer {{
  border-top: 1px solid var(--border);
  background: var(--surface);
  padding: 30px 0;
  color: var(--muted);
  font-size: 14px;
}}

.site-footer p {{ margin: 0 0 8px; }}
.disclaimer {{ font-size: 13px; line-height: 1.6; }}

.meta-line {{
  color: var(--muted);
  font-size: 14px;
  margin-bottom: 18px;
}}

@media (max-width: 720px) {{
  body {{ font-size: 16px; }}
  .hero {{ padding: 36px 0 28px; }}
  .hero h1 {{ font-size: 26px; }}
  .hero p {{ font-size: 16px; }}
  h2 {{ font-size: 22px; }}
  .site-nav a {{ margin-left: 12px; font-size: 14px; }}
}}
""".strip()

    if amp:
        # amp-img butuh latar supaya tidak berkedip saat layout.
        css += """
amp-img { background: var(--surface); border-radius: var(--radius); }
"""

    return minify_css(css)