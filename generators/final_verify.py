"""
Pemeriksa terakhir: yang dibaca HALAMAN JADI, bukan dict Python.

Seluruh penjaga yang berdiri sebelum ini bekerja pada isi yang
DIMINTA - kamus peran berisi teks yang dikembalikan model. Itu tempat
yang benar untuk memperbaiki tulisan, tapi tempat yang salah untuk
membuktikan halaman. Di antara kamus itu dan berkas yang terbit masih
ada satu lapis penuh: pemetaan slot, pemotongan lebar, penggantian
nama brand, penyisipan schema. Bug di lapis itu tidak terlihat sama
sekali dari kamusnya.

Terukur di halaman terbit 16 Agustus 2026: title landing dan title AMP
berbeda jauh - yang satu kalimat baru, yang satu kalimat pemilik
template dengan namanya saja yang tertukar. Kedua berkas berangkat
dari SATU isi yang sama, jadi tidak ada satu pun pemeriksaan tingkat
kamus yang bisa melihatnya.

Yang dikembalikan dua daftar:

  hard - halaman TIDAK BOLEH ditulis. Pemanggil menggagalkan run.
  soft - halaman boleh terbit, tapi cacatnya dicatat dan dilaporkan.

Pembagiannya mengikuti aturan yang diminta pengguna: yang membuat
halaman salah (brand salah ketik, placeholder, bahasa keliru, dua
berkas tidak sinkron, JSON rusak, template berubah) menahan terbit;
yang membuat halaman kurang enak dibaca (pengulangan, jumlah H1
lebih dari satu) dicatat saja.
"""

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache

from ai.schemas import META_MAX, META_MIN, TITLE_MAX, TITLE_MIN
from generators.claim_guard import fabricated_claims
from generators.leak_guard import garbage_tokens
from generators.template_guard import verify_untouched_regions
from utils.text import display_width


# Aksara Thai, untuk mengukur halaman zona th.
THAI_CHARS = re.compile(r"[฀-๿]")

# Bagian dokumen yang isinya bukan teks yang dibaca orang. Dibuang
# lebih dulu supaya isi <script> dan <style> tidak ikut terhitung
# sebagai kalimat halaman - JSON-LD memuat seluruh teks halaman lagi,
# dan menghitungnya dua kali membuat setiap kalimat terlihat berulang.
NON_TEXT_BLOCKS = re.compile(
    r"<(script|style|template|noscript)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)

# Penanda isian yang belum diganti. Yang dicari bentuk yang tidak
# pernah pantas terbit di halaman untuk pembaca.
PLACEHOLDERS = (
    (r"\{\{[^{}]{0,80}\}\}", "penanda {{ }} belum diganti"),
    (r"\{%[^%]{0,80}%\}", "penanda {% %} belum diganti"),
    (r"\blorem ipsum\b", "teks lorem ipsum"),
    (r"\b(?:TODO|FIXME|TBD)\b", "penanda TODO"),
    (r"\[(?:brand|keyword|nama[ _]situs|site[ _]name)\]", "penanda [brand]"),
    (r"\bXXXX+\b", "penanda XXXX"),
    (r"%%[A-Z_]{2,}%%", "penanda %%NAMA%%"),
)

# Panjang kalimat terpendek yang ikut diadu antar peran. Sama dengan
# ambang di content_planner, dan ditulis ulang di sini dengan sengaja:
# pemeriksa terakhir harus bisa berdiri sendiri tanpa memuat lapisan
# AI, supaya ia tetap bisa dipakai memeriksa berkas yang sudah terbit.
CROSS_MIN_CHARS = 40

# Kemiripan huruf dua kalimat sebelum dianggap kalimat yang sama.
NEAR_RATIO = 0.86

# Berapa kata pembuka yang sama sebelum dua kalimat dihitung kembar.
SHARED_OPENING_WORDS = 7

# Ambang aksara Thai. Di zona th, teks di bawah ini dianggap bukan
# bahasa Thai; di zona lain, teks di atas AMBANG_BOCOR dianggap
# kebocoran aksara Thai ke halaman yang bukan Thai.
THAI_FLOOR = 0.5
THAI_LEAK = 0.2


def strip_tags(html: str) -> str:
    """
    Teks yang dibaca orang dari sepotong HTML.
    """
    tanpa_blok = NON_TEXT_BLOCKS.sub(" ", str(html or ""))
    tanpa_tag = re.sub(r"<[^>]+>", " ", tanpa_blok)

    # Entitas yang paling sering ada di teks halaman. Dibalik supaya
    # perbandingan kalimat tidak gagal cuma karena satu berkas menulis
    # "&amp;" dan yang lain menulis "&".
    for entitas, huruf in (
        ("&amp;", "&"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&apos;", "'"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
    ):
        tanpa_tag = tanpa_tag.replace(entitas, huruf)

    return " ".join(tanpa_tag.split())


def first(pattern: str, html: str) -> str:
    found = re.search(pattern, html, re.IGNORECASE | re.DOTALL)

    return " ".join(found.group(1).split()) if found else ""


def all_of(pattern: str, html: str) -> list[str]:
    return [
        " ".join(strip_tags(item).split())
        for item in re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
    ]


def read_page(html: str) -> dict:
    """
    Membaca halaman jadi seperti pembacanya, bukan seperti penulisnya.

    Sengaja dengan pola sederhana, bukan dengan pengurai HTML penuh.
    Yang diperiksa di sini adalah berkas yang SUDAH jadi, dan pengurai
    yang merapikan HTML rusak justru menyembunyikan kerusakan yang mau
    dicari.
    """
    title = first(r"<title[^>]*>(.*?)</title>", html)

    # Pola meta description SENGAJA dipatok di dalam satu tag.
    #
    # Bentuk sebelumnya memakai (.*?) untuk nilainya, dan dengan
    # DOTALL potongan itu bisa melompati tanda ">" - artinya melompati
    # tag. Terukur pada template nyata 123 KB yang atribut metanya
    # ditulis terbalik (content dulu, name belakangan): yang terbaca
    # sebagai meta description adalah nilai viewport dari tag di
    # atasnya, disambung sampai ke tag description yang jauh di
    # bawahnya.
    #
    # Akibatnya bukan laporan yang meleset melainkan generate yang
    # GAGAL: deskripsi landing terbaca berbeda dari AMP, gerbang akhir
    # menahan halaman, dan empat puluh menit kerja model dibuang untuk
    # cacat yang tidak pernah ada di halamannya.
    #
    # Dua urutan atribut sama-sama sah di HTML, jadi keduanya dicari.
    # Nilainya dibatasi [^"']* supaya tidak bisa keluar dari tanda
    # kutipnya sendiri.
    desc = first(
        r"<meta\b[^>]*\bname=[\"']description[\"'][^>]*"
        r"\bcontent=[\"']([^\"']*)[\"']",
        html,
    ) or first(
        r"<meta\b[^>]*\bcontent=[\"']([^\"']*)[\"'][^>]*"
        r"\bname=[\"']description[\"']",
        html,
    )

    return {
        "title": strip_tags(title),
        "meta_description": strip_tags(desc),
        "h1": all_of(r"<h1[^>]*>(.*?)</h1>", html),
        "heading": all_of(r"<h2[^>]*>(.*?)</h2>", html),
        "faq_question": all_of(r"<h3[^>]*>(.*?)</h3>", html),
        "paragraph": [
            teks
            for teks in all_of(r"<p[^>]*>(.*?)</p>", html)
            if len(teks) >= 40
        ],
        "review_text": all_of(r"<blockquote[^>]*>(.*?)</blockquote>", html),
        "jsonld": re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
            r"(.*?)</script>",
            html,
            re.IGNORECASE | re.DOTALL,
        ),
        "body_text": strip_tags(html),
    }


def sentences(teks: str) -> list[str]:
    bersih = " ".join(str(teks or "").split())

    if not bersih:
        return []

    potong = [
        bagian.strip()
        for bagian in re.split(r"(?<=[.!?])\s+", bersih)
        if bagian.strip()
    ]

    return potong or [bersih]


def same_sentence(satu: str, dua: str) -> bool:
    """
    Apakah dua kalimat akan terbaca sebagai kalimat yang sama.
    """
    if not satu or not dua:
        return False

    if satu == dua:
        return True

    pendek, panjang = sorted((satu, dua), key=len)

    if panjang.startswith(pendek):
        return True

    sama = 0

    for kiri, kanan in zip(satu.split(), dua.split()):
        if kiri != kanan:
            break

        sama += 1

    if sama >= SHARED_OPENING_WORDS:
        return True

    return SequenceMatcher(None, satu, dua).ratio() >= NEAR_RATIO


# Urutan peran waktu kalimatnya diadu. Yang lebih dulu berdiri
# menang, jadi title dan deskripsi tidak pernah dilaporkan sebagai
# pihak yang mengulang paragraf.
CROSS_ROLES = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "paragraph",
    "faq_question",
    "review_text",
)


def repeated_across_roles(page: dict) -> list[str]:
    """
    Kalimat yang berdiri di dua peran berbeda di halaman yang terbit.

    Ini pemeriksaan yang sama dengan cross_role_duplicates di lapis
    isi, dijalankan sekali lagi di ujung. Bukan karena yang pertama
    tidak dipercaya, melainkan karena keduanya menjawab pertanyaan
    yang berbeda: yang di sana "apakah yang diminta ke model sudah
    layak", yang di sini "apakah yang benar-benar terbaca orang di
    halaman ini masih mengulang".
    """
    berdiri: list[tuple[str, str]] = []
    temuan: list[str] = []

    for role in CROSS_ROLES:
        nilai = page.get(role)
        daftar = nilai if isinstance(nilai, list) else [nilai]

        milik: list[str] = []

        for teks in daftar:
            for kalimat in sentences(teks):
                if len(kalimat) < CROSS_MIN_CHARS:
                    continue

                bentuk = kalimat.casefold()
                kena = ""

                for peran_lain, lawan in berdiri:
                    if peran_lain == role:
                        continue

                    if same_sentence(bentuk, lawan):
                        kena = peran_lain
                        break

                if kena:
                    temuan.append(
                        f"kalimat yang sama berdiri di {kena} dan {role}: "
                        f'"{kalimat[:80]}"'
                    )
                else:
                    milik.append(bentuk)

        berdiri.extend((role, satu) for satu in milik)

    return temuan


def thai_share(teks: str, brand: str = "", keyword: str = "") -> float:
    """
    Bagian aksara Thai, DI LUAR nama brand dan keyword.

    Keduanya dicabut lebih dulu karena keduanya memang boleh tetap
    berbentuk aslinya di halaman berbahasa apa pun - itu yang diminta
    pengguna. Dihitung apa adanya, judul Thai yang benar seperti
    "WAYANGPLAY slot gacor" terbaca seperti bahasa yang salah justru
    karena memuat dua hal yang memang diminta.
    """
    isi = str(teks or "")

    for buang in (str(brand or ""), str(keyword or "")):
        if buang.strip():
            isi = re.sub(re.escape(buang), " ", isi, flags=re.IGNORECASE)

            for kata in buang.split():
                isi = re.sub(
                    r"\b%s\b" % re.escape(kata),
                    " ",
                    isi,
                    flags=re.IGNORECASE,
                )

    huruf = [satu for satu in isi if satu.isalpha()]

    if not huruf:
        return 0.0

    return sum(1 for satu in huruf if THAI_CHARS.match(satu)) / len(huruf)


def brand_typos(teks: str, brand: str) -> list[str]:
    """
    Kata yang jelas-jelas salah ketik dari nama brand.

    Yang dicari kata yang MIRIP nama brand tapi tidak sama - bukan
    kata biasa yang kebetulan berbagi beberapa huruf. Tiga syarat
    harus terpenuhi sekaligus: empat huruf pertamanya sama, panjangnya
    beda paling banyak dua huruf, dan kemiripannya di atas ambang.

    Syarat itu yang menahannya dari merusak halaman: brand
    "WAYANGPLAY" tidak boleh membuat kata "wayang" di kalimat "wayang
    kulit" dilaporkan sebagai salah ketik, dan tidak dilaporkan -
    panjangnya beda empat huruf.
    """
    nama = str(brand or "").strip()

    if len(nama) < 4:
        return []

    temuan: list[str] = []

    for kata in re.findall(r"[^\W_]+", str(teks or "")):
        if kata == nama or kata.casefold() == nama.casefold():
            continue

        if kata.upper()[:4] != nama.upper()[:4]:
            continue

        if abs(len(kata) - len(nama)) > 2:
            continue

        if SequenceMatcher(None, kata.upper(), nama.upper()).ratio() < 0.75:
            continue

        temuan.append(kata)

    return sorted(set(temuan))


@lru_cache(maxsize=8)
def template_forms(template: str) -> tuple[str, str]:
    """
    Dua bentuk template untuk dicari: apa adanya, dan teksnya saja.

    Keduanya perlu. Penanda isian bisa berdiri di dalam atribut atau
    skrip, jadi harus dicari di berkas mentahnya; kalimat yang dibaca
    orang sering terbelah tag di dalamnya - "Jam <b>OSB99</b>
    beroperasi setiap hari" - dan di berkas mentah kalimat itu tidak
    pernah ketemu utuh.

    Di-cache karena template bisa ratusan kilobyte dan fungsi ini
    dipanggil sekali untuk setiap temuan.
    """
    mentah = " ".join(str(template or "").split()).casefold()
    teks = strip_tags(template).casefold()

    return mentah, teks


def from_template(
    potongan: str,
    template: str,
    brand: str = "",
    old_brand: str = "",
) -> bool:
    """
    Apakah temuan ini memang sudah ada di templatenya sendiri.

    Yang berasal dari template bukan karangan generator ini, dan
    menahan terbit karenanya berarti menolak halaman untuk kalimat
    yang ditulis pemilik templatenya sendiri - bagian yang tidak
    pernah disentuh dan memang tidak boleh disentuh.

    Nama brand ikut diperhitungkan. Slot yang tidak kebagian teks baru
    tetap kebagian penggantian NAMA, jadi kalimat pemilik template
    terbit dengan nama yang baru - dan dicari apa adanya, kalimat itu
    tidak akan pernah ketemu di templatenya sendiri. Terukur pada
    template nyata: "Jam OSB99 beroperasi setiap hari" terbit sebagai
    "Jam RAJAWALI77 beroperasi setiap hari", dan tanpa penyetaraan ini
    seluruh halaman ditahan karena kalimat yang ditulis pemiliknya.
    """
    jarum = " ".join(str(potongan or "").split())

    if not jarum:
        return False

    mentah, teks = template_forms(template)

    calon = [jarum.casefold()]

    nama_baru = str(brand or "").strip()
    nama_lama = str(old_brand or "").strip()

    if nama_baru and nama_lama:
        calon.append(
            re.sub(
                re.escape(nama_baru),
                nama_lama,
                jarum,
                flags=re.IGNORECASE,
            ).casefold()
        )

    return any(satu in mentah or satu in teks for satu in calon)


def verify_pages(
    landing_html: str,
    amp_html: str = "",
    template_landing: str = "",
    template_amp: str = "",
    landing_ranges: list[dict] | None = None,
    amp_ranges: list[dict] | None = None,
    brand: str = "",
    old_brand: str = "",
    keyword: str = "",
    region: str = "id",
    amp_roles: set | None = None,
) -> dict:
    """
    Memeriksa berkas yang akan terbit dan memutuskan boleh atau tidak.

    template_* dan *_ranges boleh dikosongkan; yang dikosongkan cuma
    membuat pemeriksaan yang membutuhkannya dilewati, bukan membuat
    seluruhnya gagal. Itu disengaja supaya fungsi ini juga bisa
    dipakai memeriksa berkas yang sudah terbit, di luar pipeline.

    amp_roles berisi peran yang BENAR-BENAR punya slot di template
    AMP. Dipakai membedakan dua hal yang terlihat sama dari berkas
    jadi: slot yang gagal kebagian teks baru - kesalahan yang harus
    menahan terbit - dan bagian yang memang tidak pernah bisa diisi
    karena template AMP-nya tidak menyediakan slot untuk itu.

    Contohnya terukur pada template nyata: H1 berkas AMP-nya ditulis
    "OSB99 <em>Login</em>" - teksnya terbelah tag di dalamnya, jadi
    mengisinya berarti menyentuh markup yang justru dijanjikan tidak
    disentuh. Tidak ada isian yang bisa membuat H1 kedua berkas sama,
    dan menahan terbit karenanya berarti template itu tidak akan
    pernah bisa dipakai sama sekali.
    """
    hard: list[str] = []
    soft: list[str] = []

    # Dipakai bersama seluruh pemeriksaan isi: temuan yang teksnya
    # memang berasal dari template - termasuk yang namanya sudah
    # ditukar - tidak pernah menahan terbit.
    nama_brand = str(brand or "").strip()
    lama_brand = str(old_brand or "").strip()

    if not str(landing_html or "").strip():
        return {"hard": ["Berkas landing kosong."], "soft": [], "facts": {}}

    landing = read_page(landing_html)
    amp = read_page(amp_html) if amp_html else None

    berkas = [("landing", landing_html, landing, template_landing)]

    if amp is not None:
        berkas.append(("AMP", amp_html, amp, template_amp))

    # --- 1. Struktur dokumen -------------------------------------
    for label, html, halaman, _template in berkas:
        if html.count("<html") != 1 or html.count("</html>") != 1:
            hard.append(
                f"Struktur {label} rusak: {html.count('<html')} tag "
                f"<html> dan {html.count('</html>')} penutupnya."
            )

        if not halaman["title"]:
            hard.append(f"{label} terbit tanpa isi <title>.")

        if not halaman["meta_description"]:
            hard.append(f"{label} terbit tanpa meta description.")

        if len(halaman["h1"]) != 1:
            soft.append(
                f"{label} punya {len(halaman['h1'])} H1, yang paling "
                "aman satu."
            )

    # --- 2. Slot wajib benar-benar terisi -------------------------
    #
    # Diadu dengan TEMPLATENYA, bukan dengan anggapan bahwa setiap
    # halaman pasti memakai <p>. Ada template yang menaruh seluruh
    # teks badannya di dalam <div>, dan menolak halaman seperti itu
    # berarti menggagalkan generate untuk template yang sama sekali
    # tidak bermasalah - kegagalan yang paling mahal, karena baru
    # muncul sesudah seluruh isi selesai ditulis model.
    #
    # Tanpa template pembanding, syaratnya dilonggarkan ke "ada teks
    # badan": yang benar-benar salah adalah halaman kosong.
    if template_landing:
        punya_paragraf = bool(
            re.search(r"<p\b", template_landing, re.IGNORECASE)
        )
    else:
        punya_paragraf = False

    if punya_paragraf and not landing["paragraph"]:
        hard.append(
            "Template punya paragraf, tapi halaman jadi tidak memuat "
            "satu pun paragraf isi."
        )

    if not landing["paragraph"] and len(landing["body_text"]) < 200:
        hard.append(
            "Halaman terbit hampir tanpa teks badan "
            f"({len(landing['body_text'])} karakter)."
        )

    # --- 3. Landing dan AMP sinkron -------------------------------
    if amp is not None:

        def bisa_diisi(peran: str) -> bool:
            """
            Apakah template AMP memang menyediakan slot untuk peran ini.

            Tanpa daftarnya, semua dianggap bisa diisi - itu perilaku
            lama, dan pemanggil di luar pipeline memang tidak punya
            peta slotnya.
            """
            return amp_roles is None or peran in amp_roles

        for kunci, label in (
            ("title", "Title"),
            ("meta_description", "Meta description"),
            ("h1", "H1"),
        ):
            kiri = landing[kunci]
            kanan = amp[kunci]

            if kunci == "h1":
                kiri = kiri[0] if kiri else ""
                kanan = kanan[0] if kanan else ""

                # H1 yang tidak ada di salah satu berkas bukan
                # ketidaksamaan - template AMP memang boleh tidak
                # punya H1 sama sekali.
                if not kiri or not kanan:
                    continue

            if kiri == kanan:
                continue

            pesan = (
                f"{label} landing dan AMP berbeda, padahal keduanya "
                f'diisi dari satu isi yang sama. Landing: "{kiri[:70]}". '
                f'AMP: "{kanan[:70]}".'
            )

            if bisa_diisi(kunci):
                hard.append(pesan)
            else:
                # Template AMP tidak punya slot untuk peran ini, jadi
                # tidak ada isian yang bisa membuat keduanya sama.
                # Dicatat supaya pemiliknya tahu, bukan ditahan.
                soft.append(
                    pesan
                    + f" Template AMP tidak punya slot {kunci} yang bisa "
                    "diisi - teksnya terbelah tag di dalamnya, atau "
                    "memang tidak ada di berkas itu - jadi tidak ada "
                    "isian yang bisa menyamakannya tanpa menyentuh "
                    "markup template."
                )

    # --- 4. JSON-LD sah -------------------------------------------
    for label, _html, halaman, _template in berkas:
        for blok in halaman["jsonld"]:
            try:
                json.loads(blok)
            except ValueError as error:
                hard.append(
                    f"JSON-LD di {label} bukan JSON yang sah: {error}."
                )

    # --- 5. Penanda isian yang belum diganti ----------------------
    for label, html, _halaman, template in berkas:
        for pola, sebutan in PLACEHOLDERS:
            for kena in re.findall(pola, html, re.IGNORECASE)[:3]:
                potongan = kena if isinstance(kena, str) else kena[0]

                if from_template(potongan, template, nama_brand, lama_brand):
                    continue

                hard.append(
                    f"{label} memuat {sebutan}: {potongan[:60]!r}."
                )

    # --- 6. Nama brand --------------------------------------------
    nama = str(brand or "").strip()

    if nama:
        for label, html, halaman, template in berkas:
            if nama not in html:
                hard.append(
                    f"Nama brand '{nama}' tidak ada satu pun di {label}."
                )

            salah = [
                kata
                for kata in brand_typos(halaman["body_text"], nama)
                if not from_template(kata, template, nama, lama_brand)
            ]

            if salah:
                hard.append(
                    f"{label} memuat ejaan brand yang salah: "
                    + ", ".join(salah[:5])
                    + f" (yang benar '{nama}')."
                )

    lama = str(old_brand or "").strip()

    if lama and lama.casefold() != nama.casefold():
        for label, _html, halaman, _template in berkas:
            if re.search(
                r"\b%s\b" % re.escape(lama), halaman["body_text"], re.I
            ):
                soft.append(
                    f"Nama brand lama '{lama}' masih terbaca di teks "
                    f"{label}. Kalau itu di dalam blok iklan, memang "
                    "tidak pernah disentuh."
                )

    # --- 7. Token sampah dan klaim karangan -----------------------
    for label, _html, halaman, template in berkas:
        teks = halaman["body_text"]

        sampah = [
            token
            for token in garbage_tokens(teks)
            if not from_template(
                str(token), template, nama_brand, lama_brand
            )
        ]

        if sampah:
            hard.append(
                f"{label} memuat token sampah: "
                + ", ".join(str(satu)[:30] for satu in sampah[:5])
            )

        karangan = [
            (jenis, potongan)
            for jenis, potongan in fabricated_claims(teks)
            if not from_template(
                str(potongan), template, nama_brand, lama_brand
            )
        ]

        if karangan:
            hard.append(
                f"{label} memuat klaim karangan: "
                + "; ".join(
                    f"{jenis} ({str(potongan)[:40]})"
                    for jenis, potongan in karangan[:3]
                )
            )

    # --- 8. Bahasa -------------------------------------------------
    if str(region or "").lower() == "th":
        for kunci, label in (
            ("title", "Title"),
            ("meta_description", "Meta description"),
        ):
            bagian = thai_share(landing[kunci], nama, keyword)

            if bagian <= THAI_FLOOR:
                hard.append(
                    f"{label} halaman zona Thailand tidak berbahasa "
                    f"Thai (hanya {bagian:.0%} aksara Thai di luar "
                    "nama brand dan keyword)."
                )

        bukan_thai = [
            teks
            for teks in landing["paragraph"]
            if thai_share(teks, nama, keyword) <= THAI_FLOOR
        ]

        if bukan_thai:
            hard.append(
                f"{len(bukan_thai)} paragraf halaman zona Thailand "
                "tidak berbahasa Thai: "
                f'"{bukan_thai[0][:60]}".'
            )
    else:
        bocor = [
            teks
            for teks in [landing["title"], landing["meta_description"]]
            + landing["paragraph"]
            if thai_share(teks, nama, keyword) > THAI_LEAK
        ]

        if bocor:
            hard.append(
                f"{len(bocor)} teks memuat aksara Thai padahal zona "
                f'halaman ini bukan Thailand: "{bocor[0][:60]}".'
            )

    # --- 9. Template tidak berubah di luar slot -------------------
    #
    # Pembuktian byte demi byte, memakai rentang yang benar-benar
    # ditulis pengisi. Lapis ini sudah berjalan di dalam fill_template
    # dan dijalankan LAGI di sini dengan sengaja: yang diperiksa
    # sekarang adalah teks yang persis akan ditulis ke disk, sesudah
    # setiap lapis sesudah pengisian selesai bekerja.
    for label, html, template, rentang in (
        ("landing", landing_html, template_landing, landing_ranges),
        ("AMP", amp_html, template_amp, amp_ranges),
    ):
        if not template or not rentang or not html:
            continue

        rusak = verify_untouched_regions(template, html, rentang)

        if rusak:
            hard.append(
                f"Bagian template {label} di luar slot isi berubah: "
                + "; ".join(rusak[:2])
            )

    # --- 10. Panjang title dan deskripsi (catatan) ----------------
    #
    # Angkanya diambil dari sumber yang sama dengan yang diminta ke
    # model - HEAD_FLOOR dan HEAD_BUDGET lewat ai/schemas.py - bukan
    # ditulis ulang di sini. Dua daftar angka yang berdiri
    # sendiri-sendiri akan berselisih suatu saat, dan yang di sini
    # yang akan ketinggalan.
    #
    # Dicatat, bukan ditahan. Judul yang meleset lima karakter tetap
    # judul yang benar; yang salah cuma panjangnya, dan menahan
    # halaman karenanya berarti membuang seluruh isi yang sudah benar.
    for kunci, label, lantai, atap in (
        ("title", "Title", TITLE_MIN, TITLE_MAX),
        ("meta_description", "Meta description", META_MIN, META_MAX),
    ):
        # Diukur dalam KOLOM TAMPILAN, bukan dalam karakter.
        #
        # Keduanya angka yang sama untuk teks Latin, dan sangat
        # berbeda untuk aksara Thai: tanda vokal dan nada ditumpuk di
        # atas atau di bawah huruf induknya, jadi tidak menambah lebar
        # sedikit pun. Terukur pada halaman zona th yang benar-benar
        # terbit, output/wayangplay-slot-gacor-20260820_005421:
        # deskripsinya 213 karakter tapi 171 kolom - di dalam rentang
        # yang diminta, dan dilaporkan melanggar hanya karena diukur
        # dengan penggaris yang salah.
        #
        # Jatah slotnya sendiri sudah dihitung dalam kolom sejak awal
        # (lihat scale_spec), jadi mengukur di sini dengan len()
        # berarti pemeriksa memakai satuan yang lain dari yang dipakai
        # waktu teksnya dipesan.
        panjang = display_width(landing[kunci])

        if panjang and not lantai <= panjang <= atap:
            soft.append(
                f"{label} {panjang} kolom, di luar rentang "
                f"{lantai}-{atap}."
            )

    if (
        landing["title"]
        and landing["meta_description"]
        and SequenceMatcher(
            None,
            landing["title"].casefold(),
            landing["meta_description"].casefold(),
        ).ratio()
        >= NEAR_RATIO
    ):
        soft.append(
            "Meta description hampir sama dengan title, jadi baris "
            "kedua di hasil pencarian mengulang baris pertama."
        )

    # --- 11. Pengulangan antar peran (catatan) --------------------
    for label, _html, halaman, _template in berkas:
        for catatan in repeated_across_roles(halaman)[:5]:
            soft.append(f"{label}: {catatan}")

    return {
        "hard": hard,
        "soft": soft,
        "facts": {
            "title": landing["title"],
            "meta_description": landing["meta_description"],
            "h1": landing["h1"][0] if landing["h1"] else "",
            "paragraphs": len(landing["paragraph"]),
            "faq": len(landing["faq_question"]),
            "reviews": len(landing["review_text"]),
            "jsonld_blocks": len(landing["jsonld"]),
        },
    }
