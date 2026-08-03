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


def star_width_rules() -> str:
    """
    Lebar isian bintang untuk tiap nilai penilaian.

    Lebarnya dipasang lewat kelas, bukan lewat atribut `style`,
    karena AMP melarang gaya sebaris. Rentangnya 3.0 sampai 5.0
    dengan langkah 0.1 — nilai di bawah itu tidak pernah dipakai
    untuk penilaian yang ditampilkan.
    """
    rules = []

    for tenth in range(30, 51):
        rules.append(
            f".stars.st-{tenth}:after {{ width: {tenth / 50 * 100:.1f}%; }}"
        )

    return "\n".join(rules)


def build_block_css(amp: bool, radius: int) -> str:
    """
    CSS untuk pustaka blok di generators/blocks.py.

    Dipisah dari CSS dasar supaya bagian yang tidak boleh ada di AMP
    benar-benar tidak ikut tertulis, bukan sekadar tidak terpakai.
    Validator AMP membaca isi <style amp-custom> apa adanya: satu
    aturan `position: fixed` di sana membuat halaman gagal validasi
    walau elemennya tidak pernah dipasang.
    """
    # Bintang digambar dari karakter yang ditulis sebagai escape CSS,
    # jadi berkas CSS-nya murni ASCII. Menempelkan karakter bintang
    # apa adanya membuat hasilnya bergantung pada encoding berkas,
    # dan salah encoding sekali saja mengubah seluruh bintang jadi
    # deretan tanda tanya.
    star = "\\2605\\2605\\2605\\2605\\2605"

    css = f"""
.nav-cta {{
  padding: 9px 18px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--brand), var(--brand-dark));
  color: var(--on-brand);
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.4px;
}}

.nav-cta:hover {{ text-decoration: none; filter: brightness(1.1); }}

.cta-duo {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 22px 0;
}}

.cta-btn {{
  flex: 1 1 200px;
  text-align: center;
  padding: 15px 24px;
  border-radius: {radius}px;
  border: 1px solid var(--border);
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--on-brand);
  background: linear-gradient(180deg, var(--brand), var(--brand-dark));
}}

.cta-btn:hover {{ text-decoration: none; filter: brightness(1.12); }}

.cta-reg {{
  background: linear-gradient(180deg, var(--brand-mid), var(--brand-dark));
}}

.floatbar {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
  padding: 12px 16px;
  background: var(--surface);
  border-top: 1px solid var(--border);
}}

.fb-item {{
  flex: 1 1 150px;
  text-align: center;
  padding: 11px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  color: var(--on-brand);
  background: linear-gradient(135deg, var(--brand), var(--brand-dark));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

.fb-item:hover {{ text-decoration: none; filter: brightness(1.12); }}

.stars {{
  position: relative;
  display: inline-block;
  font-size: 15px;
  line-height: 1;
  letter-spacing: 2px;
  white-space: nowrap;
}}

.stars:before {{
  content: "{star}";
  color: var(--border);
}}

.stars:after {{
  content: "{star}";
  color: var(--star);
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  overflow: hidden;
  white-space: nowrap;
}}

{star_width_rules()}

.rate-grid, .rev-grid {{
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}}

.rate-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: {radius}px;
  padding: 18px 20px;
  text-align: center;
}}

.rate-name {{
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 10px;
}}

.rate-value {{
  margin-top: 8px;
  color: var(--muted);
  font-size: 14px;
}}

.rev-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--brand);
  border-radius: {radius}px;
  padding: 16px 20px;
}}

.rev-head {{
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}}

.rev-name {{ font-weight: 700; }}
.rev-date {{ color: var(--muted); font-size: 13px; }}
.rev-head .stars {{ margin-left: auto; }}
.rev-text {{ margin: 0; color: var(--muted); font-size: 15px; }}

.pill-row {{ display: flex; flex-wrap: wrap; gap: 9px; }}

.pill {{
  display: inline-block;
  padding: 7px 15px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 14px;
}}

.pill:hover {{
  text-decoration: none;
  border-color: var(--brand);
  color: var(--brand);
}}

.foot-grid {{
  display: grid;
  gap: 22px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  margin-bottom: 22px;
}}

.foot-col h3 {{
  margin: 0 0 10px;
  font-size: 15px;
  color: var(--text);
}}

.foot-links {{ display: flex; flex-direction: column; gap: 7px; }}
.foot-links a {{ color: var(--muted); font-size: 14px; }}
.foot-links a:hover {{ color: var(--brand); }}
.foot-brand {{ display: flex; flex-direction: column; gap: 12px; }}
.foot-brand .cta-btn {{ flex: 0 0 auto; }}
.foot-legal {{ margin: 0 0 8px; }}
""".strip()

    if not amp:
        # Bilah mengambang dan popup hanya hidup di halaman kanonik.
        # AMP melarang `position: fixed` untuk elemen biasa, dan
        # melarang `<input>` di luar amp-form.
        css += f"""
body {{ padding-bottom: 84px; }}

.floatbar {{
  position: fixed;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  z-index: 40;
  width: calc(100% - 28px);
  max-width: var(--max-width);
  border: 1px solid var(--border);
  border-radius: {radius + 8}px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}}

.pop-switch {{ position: absolute; opacity: 0; pointer-events: none; }}

.pop-overlay {{
  display: none;
  position: fixed;
  inset: 0;
  z-index: 60;
  align-items: center;
  justify-content: center;
  padding: 18px;
  background: rgba(0, 0, 0, 0.6);
}}

.pop-switch:checked ~ .pop-overlay {{ display: flex; }}

.pop-card {{
  position: relative;
  width: 100%;
  max-width: 420px;
  border-radius: {radius + 8}px;
  border: 1px solid var(--border);
  padding: 30px 24px 22px;
  text-align: center;
  background: linear-gradient(160deg, var(--surface), var(--brand-dark));
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
}}

.pop-close {{
  position: absolute;
  top: 12px;
  right: 12px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
}}

.pop-close:before, .pop-close:after {{
  content: "";
  position: absolute;
  top: 14px;
  left: 7px;
  width: 15px;
  height: 2px;
  background: var(--text);
}}

.pop-close:before {{ transform: rotate(45deg); }}
.pop-close:after {{ transform: rotate(-45deg); }}

.pop-title {{
  margin: 0 0 18px;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.4;
}}

.pop-actions {{ display: flex; flex-direction: column; gap: 11px; }}

.pop-foot {{
  margin: 18px 0 0;
  font-size: 12px;
  color: var(--muted);
}}
"""

    css += """
@media (max-width: 720px) {
  .floatbar { gap: 7px; padding: 9px 10px; }
  .fb-item { flex: 1 1 100px; font-size: 12px; padding: 9px 8px; }
  .rev-head .stars { margin-left: 0; width: 100%; }
}
"""

    return css


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

    # Warna blok baru. Kalau paletnya berasal dari jalur lama yang
    # belum lewat theme.py, ketiganya jatuh balik ke aksen supaya
    # halaman tetap terbentuk, hanya tanpa gradasi.
    brand_color = palette.get("brand", accent)
    brand_mid = palette.get("brand_mid", accent_2)
    brand_dark = palette.get("brand_dark", accent_2)
    on_brand = palette.get("on_brand", accent_text)
    star = palette.get("star", accent)

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
  --brand: {brand_color};
  --brand-mid: {brand_mid};
  --brand-dark: {brand_dark};
  --on-brand: {on_brand};
  --star: {star};
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

    css += "\n" + build_block_css(amp, radius)

    if amp:
        # amp-img butuh latar supaya tidak berkedip saat layout.
        css += """
amp-img { background: var(--surface); border-radius: var(--radius); }
"""

    return minify_css(css)