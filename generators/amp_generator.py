"""
Generator versi AMP.

Isi halaman sama persis dengan versi kanonik, hanya kerangkanya
yang mengikuti aturan AMP: boilerplate wajib, runtime v0.js, satu
blok <style amp-custom>, dan tanpa JavaScript sendiri.
"""

from generators.css_builder import build_css
from generators.html_utils import escape
from generators.page_body import render_body
from generators.schema_generator import build_schema_graph


AMP_BOILERPLATE = (
    "<style amp-boilerplate>"
    "body{-webkit-animation:-amp-start 8s steps(1,end) 0s 1 normal both;"
    "-moz-animation:-amp-start 8s steps(1,end) 0s 1 normal both;"
    "-ms-animation:-amp-start 8s steps(1,end) 0s 1 normal both;"
    "animation:-amp-start 8s steps(1,end) 0s 1 normal both}"
    "@-webkit-keyframes -amp-start{from{visibility:hidden}"
    "to{visibility:visible}}"
    "@-moz-keyframes -amp-start{from{visibility:hidden}"
    "to{visibility:visible}}"
    "@-ms-keyframes -amp-start{from{visibility:hidden}"
    "to{visibility:visible}}"
    "@-o-keyframes -amp-start{from{visibility:hidden}"
    "to{visibility:visible}}"
    "@keyframes -amp-start{from{visibility:hidden}"
    "to{visibility:visible}}"
    "</style>"
    "<noscript><style amp-boilerplate>"
    "body{-webkit-animation:none;-moz-animation:none;"
    "-ms-animation:none;animation:none}"
    "</style></noscript>"
)


def generate_amp_page(
    plan: dict,
    design: dict,
    brand: dict,
    page_url: str,
    amp_url: str,
) -> str:
    """
    Merender halaman AMP yang siap diunggah.

    canonical sengaja menunjuk ke halaman biasa, bukan ke dirinya
    sendiri, sesuai syarat AMP berpasangan.
    """
    css = build_css(design, amp=True)

    schema = build_schema_graph(
        plan=plan,
        brand=brand,
        page_url=page_url,
        include_article=True,
    )

    keywords = ", ".join(plan.get("keywords", [])[:10])

    return f"""<!doctype html>
<html amp lang="id">
<head>
  <meta charset="utf-8">
  <script async src="https://cdn.ampproject.org/v0.js"></script>
  <meta name="viewport" content="width=device-width,minimum-scale=1,initial-scale=1">

  <title>{escape(plan["title"])}</title>
  <meta name="description" content="{escape(plan["meta_description"])}">
  <meta name="keywords" content="{escape(keywords)}">
  <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
  <link rel="canonical" href="{escape(page_url)}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="{escape(brand["locale"])}">
  <meta property="og:site_name" content="{escape(brand["site_name"])}">
  <meta property="og:title" content="{escape(plan["title"])}">
  <meta property="og:description" content="{escape(plan["meta_description"])}">
  <meta property="og:url" content="{escape(amp_url)}">

  <script type="application/ld+json">
{schema}
  </script>

  {AMP_BOILERPLATE}

  <style amp-custom>
{css}
  </style>
</head>
<body>

  {render_body(plan, brand)}

</body>
</html>
"""
