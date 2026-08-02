"""
Generator landing page versi biasa (HTML kanonik).

Halaman ini yang jadi canonical target. Versi AMP menunjuk balik
ke sini lewat rel=canonical, dan halaman ini menunjuk ke AMP lewat
rel=amphtml.
"""

from generators.css_builder import build_css
from generators.html_utils import escape
from generators.page_body import render_body
from generators.schema_generator import build_schema_graph


def build_meta_tags(
    plan: dict,
    brand: dict,
    page_url: str,
    amp_url: str,
) -> str:
    keywords = ", ".join(plan.get("keywords", [])[:10])

    return f"""
<title>{escape(plan["title"])}</title>
  <meta name="description" content="{escape(plan["meta_description"])}">
  <meta name="keywords" content="{escape(keywords)}">
  <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
  <link rel="canonical" href="{escape(page_url)}">
  <link rel="amphtml" href="{escape(amp_url)}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="{escape(brand["locale"])}">
  <meta property="og:site_name" content="{escape(brand["site_name"])}">
  <meta property="og:title" content="{escape(plan["title"])}">
  <meta property="og:description" content="{escape(plan["meta_description"])}">
  <meta property="og:url" content="{escape(page_url)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(plan["title"])}">
  <meta name="twitter:description" content="{escape(plan["meta_description"])}">
""".strip()


def generate_landing_page(
    plan: dict,
    design: dict,
    brand: dict,
    page_url: str,
    amp_url: str,
) -> str:
    """
    Merender halaman HTML lengkap yang siap diunggah.
    """
    css = build_css(design, amp=False)

    schema = build_schema_graph(
        plan=plan,
        brand=brand,
        page_url=page_url,
        include_article=True,
    )

    return f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  {build_meta_tags(plan, brand, page_url, amp_url)}

  <script type="application/ld+json">
{schema}
  </script>

  <style>
{css}
  </style>
</head>
<body>

  {render_body(plan, brand)}

</body>
</html>
"""
