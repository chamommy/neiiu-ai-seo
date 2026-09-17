"""
Template jebakan yang dipakai seluruh pemeriksaan.

Berdiri di satu berkas supaya tiap uji memakai template yang sama
persis. Dua daftar di bawahnya - BEKU dan SISA_TEMPLATE - adalah
kontraknya: yang di BEKU harus terbawa apa adanya sampai ke berkas
jadi, yang di SISA_TEMPLATE tidak boleh tersisa satu pun.
"""

# Template landing dengan seluruh jebakan yang diminta pengguna:
# blok iklan, onclick pelacak, tautan sponsor, gambar banner, iframe
# iklan, CSS inline, JS inline, dan skrip vendor.
LANDING = """<!doctype html>
<html lang="id"><head>
<meta charset="utf-8">
<title>Judul Template Lama Milik Pemilik</title>
<meta name="description" content="Deskripsi lama milik pemilik template
yang panjangnya cukup untuk dikenali sebagai meta description halaman.">
<style>.ad{display:block;border:1px solid #333}.hero{padding:20px}</style>
<script>window.trackAd=function(id){return id;};</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebPage",
 "name":"Judul Template Lama Milik Pemilik",
 "description":"Deskripsi lama milik pemilik template.",
 "breadcrumb":{"@type":"BreadcrumbList","itemListElement":[
   {"@type":"ListItem","position":1,"name":"Home"},
   {"@type":"ListItem","position":2,"name":"Kategori Lama"},
   {"@type":"ListItem","position":3,"name":"Halaman Lama"}]}}
</script>
</head><body>
<div class="ad" data-slot="top" onclick="trackAd('top')">
  <a href="https://sponsor.invalid/promo?ref=abc"><img
     src="/assets/banner-top.png" alt="Promo" width="728" height="90"></a>
</div>
<nav class="crumbs"><a href="/">Home</a> &gt; <a href="/k">Kategori Lama</a>
 &gt; <span>Halaman Lama</span></nav>
<h1>Heading Besar Lama Template</h1>
<h2>Bagian Pertama Milik Template</h2>
<p>Paragraf pertama milik pemilik template yang isinya membahas topik
lamanya dan panjangnya cukup untuk dikenali sebagai slot isi halaman.</p>
<h2>Bagian Kedua Milik Template</h2>
<p>Paragraf kedua milik pemilik template yang juga cukup panjang untuk
ikut terhitung sebagai slot isi yang bisa diganti nanti oleh mesin.</p>
<div class="faq">
  <h3>Pertanyaan lama pertama tentang halaman ini apa?</h3>
  <p>Jawaban lama pertama yang panjangnya memadai untuk dikenali mesin.</p>
  <h3>Pertanyaan lama kedua tentang halaman ini apa?</h3>
  <p>Jawaban lama kedua yang panjangnya juga memadai untuk dikenali.</p>
</div>
<div class="reviews">
  <blockquote>Ulasan lama pertama dari pemain yang cukup panjang isinya.</blockquote>
  <blockquote>Ulasan lama kedua dari pemain yang juga cukup panjang isinya.</blockquote>
  <blockquote>Ulasan lama ketiga dari pemain yang panjangnya juga memadai.</blockquote>
</div>
<div class="ad" data-slot="bottom"><iframe
   src="https://ads.invalid/frame.html" width="300" height="250"></iframe></div>
<script src="/assets/vendor-tracker.js" async></script>
</body></html>"""


# Versi AMP-nya sengaja TIDAK sama persis: judulnya lain dan satu
# heading dibuang. Template AMP sungguhan hampir selalu punya jumlah
# slot yang berbeda dari landingnya, dan itu keadaan yang harus
# ditangani - bukan keadaan yang boleh dihindari di uji.
AMP = (
    LANDING.replace("Judul Template Lama Milik Pemilik", "Judul AMP Lama")
    .replace("<h2>Bagian Kedua Milik Template</h2>", "")
)


# Potongan yang HARUS terbawa apa adanya, byte demi byte.
BEKU = [
    ("div iklan atas", '<div class="ad" data-slot="top"'),
    ("onclick pelacak", "onclick=\"trackAd('top')\""),
    ("tautan sponsor", 'href="https://sponsor.invalid/promo?ref=abc"'),
    ("gambar banner", 'src="/assets/banner-top.png"'),
    ("atribut ukuran", 'width="728" height="90"'),
    ("iframe iklan", 'src="https://ads.invalid/frame.html"'),
    ("CSS inline", ".ad{display:block;border:1px solid #333}"),
    ("JS inline", "window.trackAd=function(id)"),
    ("skrip vendor", 'src="/assets/vendor-tracker.js"'),
]


# Teks milik pemilik template yang tidak boleh tersisa di halaman jadi.
SISA_TEMPLATE = [
    "Judul Template Lama",
    "Judul AMP Lama",
    "Heading Besar Lama",
    "Bagian Pertama Milik Template",
    "Bagian Kedua Milik Template",
    "Paragraf pertama milik pemilik",
    "Paragraf kedua milik pemilik",
    "Pertanyaan lama pertama",
    "Pertanyaan lama kedua",
    "Jawaban lama pertama",
    "Jawaban lama kedua",
    "Ulasan lama pertama",
    "Ulasan lama kedua",
    "Ulasan lama ketiga",
    "Kategori Lama",
    "Halaman Lama",
    "Deskripsi lama milik pemilik",
]
