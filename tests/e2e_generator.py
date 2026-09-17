"""
E2E generator: generate NYATA, lalu audit berkas yang benar-benar jadi.

Bukan bagian dari suite unittest, dan itu disengaja. Satu case
memakan belasan sampai puluhan menit karena modelnya benar-benar
menulis; suite yang dipanggil setiap kali kode berubah harus selesai
dalam hitungan detik.

Jalannya lewat pintu yang sama dengan pengguna:

    POST /api/neiiu/jobs -> submit_job -> services/neiiu_pipeline

Tidak ada stub, tidak ada mock, tidak ada pipeline khusus uji. Yang
diperiksa berkas HTML yang terbit, dibaca ulang dari endpoint
pratinjau.

Pakai:
    python -m tests.e2e_generator                 # CASE A-D
    python -m tests.e2e_generator A C             # sebagian
    python -m tests.e2e_generator --template 298  # template nyata
"""

import json
import re
import shutil
import sqlite3
import sys
import time

from fastapi.testclient import TestClient

import web_app
from config import BASE_DIR
from database.neiiu_templates_db import TEMPLATE_DIR, read_template_files
from generators.claim_guard import fabricated_claims
from generators.final_verify import (
    brand_typos,
    read_page,
    thai_share,
    verify_pages,
)
from generators.template_scanner import scan
from generators.template_slots import build_slot_map
from generators.leak_guard import garbage_tokens
from tests.fixtures import AMP, BEKU, LANDING, SISA_TEMPLATE


DB = BASE_DIR / "database" / "neiiu_ai.db"
NAMA_UJI = "zz_e2e_generator"

# brand, keyword, zona, dan nama brand LAMA yang sudah tertulis di
# dalam templatenya (kosong untuk template jebakan, yang memang tidak
# menyebut brand siapa pun).
CASES = {
    "A": ("WAYANGPLAY", "slot gacor", "id", ""),
    "B": ("SIAM123", "slot gacor", "id", ""),
    "C": ("WAYANGPLAY", "slot gacor", "th", ""),
    "D": ("X7GAMING88", "slot online", "id", ""),
    # Case untuk template NYATA: brand baru, keyword baru, dan brand
    # lama yang benar-benar ada di dalam berkasnya - 123 KB milik
    # OSB99, dengan iklan, skrip, dan tautan aslinya. Yang diuji di
    # sini bukan cuma isi, melainkan apakah penyapu nama brand
    # sanggup mengganti seluruh kemunculan nama lama di template
    # sebesar itu tanpa menyentuh satu byte pun di luar slot.
    "E": ("RAJAWALI77", "slot deposit qris", "id", "OSB99"),
}


class Tally:
    def __init__(self):
        self.lulus = 0
        self.gagal = 0
        self.catatan = []

    def cek(self, syarat, nama):
        if syarat:
            self.lulus += 1
            print(f"  LULUS  {nama}", flush=True)
        else:
            self.gagal += 1
            self.catatan.append(nama)
            print(f"  GAGAL  {nama}", flush=True)

        return bool(syarat)


def teks(bagian: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(bagian or "")).split())


def ambil(pola: str, html: str, semua: bool = False):
    ketemu = re.findall(pola, html, re.IGNORECASE | re.DOTALL)

    if semua:
        return [teks(x) for x in ketemu]

    return teks(ketemu[0]) if ketemu else ""


P_TITLE = r"<title[^>]*>([^<]*)</title>"
P_DESC = r'<meta name="description" content="([^"]*)"'
P_H1 = r"<h1[^>]*>(.*?)</h1>"
P_H2 = r"<h2[^>]*>(.*?)</h2>"
P_H3 = r"<h3[^>]*>(.*?)</h3>"
P_P = r"<p[^>]*>(.*?)</p>"
P_Q = r"<blockquote[^>]*>(.*?)</blockquote>"
P_LD = r'<script type="application/ld\+json">(.*?)</script>'


def json_sah(teks: str) -> bool:
    try:
        json.loads(teks)
    except ValueError:
        return False

    return True


def peran_slot(html: str, brand_lama: str, zona: str) -> set:
    """
    Peran yang benar-benar punya slot di sebuah template.
    """
    peta = build_slot_map(scan(html), brand_lama, zona)

    return {peran for peran, daftar in peta["roles"].items() if daftar}


def buat_pengguna():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username = ?", (NAMA_UJI,))
    con.commit()

    uid = int(
        con.execute(
            "INSERT INTO users (username, password_hash, role, "
            "token_balance, is_active, created_at) "
            "VALUES (?, 'x', 'user', 99, 1, '2026-08-19T00:00:00+00:00')",
            (NAMA_UJI,),
        ).lastrowid
    )

    con.commit()
    con.close()

    return uid


def bersihkan(uid: int):
    shutil.rmtree(TEMPLATE_DIR / str(uid), ignore_errors=True)

    con = sqlite3.connect(DB)

    for tabel in ("neiiu_templates", "neiiu_jobs", "neiiu_used_text"):
        try:
            con.execute(f"DELETE FROM {tabel} WHERE user_id = ?", (uid,))
        except sqlite3.Error:
            pass

    con.execute("DELETE FROM users WHERE id = ?", (uid,))
    con.commit()
    con.close()


# Pola yang menunjuk bagian template yang tidak boleh berubah.
#
# Diturunkan dari templatenya sendiri, bukan ditulis tangan, supaya
# pemeriksaan yang sama berlaku untuk template mana pun - termasuk
# template nyata milik pengguna yang isinya tidak diketahui uji ini.
PENANDA_BEKU = (
    (r'<script[^>]+src="[^"]+"', "skrip luar"),
    (r'\son[a-z]+="[^"]*"', "handler kejadian"),
    (r'<iframe[^>]+src="[^"]+"', "iframe"),
    (r'<img[^>]+src="[^"]+"', "gambar"),
    (r'href="https?://[^"]+"', "tautan keluar"),
    (r'class="[^"]*"', "kelas CSS"),
    (r'\bid="[^"]*"', "id elemen"),
)


def penanda_hilang(
    template: str,
    jadi: str,
    brand: str = "",
    brand_lama: str = "",
) -> list[str]:
    """
    Penanda beku yang jumlahnya berkurang di berkas jadi.

    Dihitung dengan jumlahnya, bukan dengan himpunan. Template yang
    punya tiga blok iklan identik dan kehilangan dua di antaranya
    tetap terlihat utuh kalau yang dibandingkan cuma nilai uniknya.

    Yang BERTAMBAH tidak dilaporkan di sini: blok schema ulasan
    memang ditambahkan, dan itu satu-satunya penambahan yang
    disengaja - lihat build_review_block.
    """
    hilang = []

    # Nama brand disamakan lebih dulu.
    #
    # Penggantian nama memang menyentuh atribut yang dibaca orang -
    # alt gambar, judul tautan - dan itu perilaku yang diminta.
    # Dibandingkan apa adanya, seluruh gambar yang alt-nya menyebut
    # nama lama terhitung "hilang": terukur 13 gambar sekaligus di
    # template nyata, padahal tidak satu pun yang dibuang.
    if brand and brand_lama:
        jadi = re.sub(re.escape(brand), brand_lama, jadi, flags=re.IGNORECASE)

    for pola, label in PENANDA_BEKU:
        asal = re.findall(pola, template, re.IGNORECASE)
        akhir = re.findall(pola, jadi, re.IGNORECASE)

        sisa = list(akhir)
        kurang = []

        for satu in asal:
            if satu in sisa:
                sisa.remove(satu)
            else:
                kurang.append(satu)

        if kurang:
            hilang.append(f"{label}: {len(kurang)} hilang, mis. {kurang[0][:60]}")

    return hilang


def audit(nama, brand, keyword, lang, landing, amp, tpl_landing, tpl_amp, t,
          fixture: bool = True, brand_lama: str = ""):
    """
    Membaca berkas jadi seperti pembacanya, lalu mengadu dengan
    seluruh janji yang dipegang generator ini.
    """
    # Dibaca lewat read_page, PEMBACA YANG SAMA dengan yang dipakai
    # gerbang akhir. Pola sendiri di sini sempat dipakai dan hasilnya
    # laporan palsu di atas template nyata: metanya ditulis dengan
    # urutan atribut terbalik, jadi deskripsi yang sebenarnya terisi
    # terbaca kosong dan dilaporkan sebagai cacat.
    halaman_landing = read_page(landing)
    halaman_amp = read_page(amp) if amp else {}

    title = halaman_landing["title"]
    desc = halaman_landing["meta_description"]
    h1 = halaman_landing["h1"][0] if halaman_landing["h1"] else ""
    h2s = ambil(P_H2, landing, True)
    faq = ambil(P_H3, landing, True)
    para = [x for x in ambil(P_P, landing, True) if len(x) > 40]
    ulasan = ambil(P_Q, landing, True)

    print()
    print(f"   TITLE       : {title}  ({len(title)})")
    print(f"   DESCRIPTION : {desc}  ({len(desc)})")
    print(f"   H1          : {h1}")

    for satu in h2s[:4]:
        print(f"   H2          : {satu}")

    for satu in faq[:4]:
        print(f"   FAQ         : {satu}")

    for satu in para[:3]:
        print(f"   PARAGRAF    : {satu[:150]}")

    for satu in ulasan[:3]:
        print(f"   ULASAN      : {satu[:130]}")

    print(flush=True)

    semua = [title, desc, h1] + h2s + faq + para + ulasan
    gabung = " ".join(semua)

    # --- 1. terbit dan utuh ---
    t.cek(bool(landing.strip()), f"{nama}: landing terbit")
    t.cek(bool(amp.strip()), f"{nama}: AMP terbit")

    for label, html in (("landing", landing), ("AMP", amp)):
        t.cek(
            html.count("<html") == 1 and html.count("</html>") == 1,
            f"{nama}: struktur HTML {label} utuh",
        )

    # --- 2. wilayah beku ---
    #
    # Dua lapis. Yang pertama berlaku untuk template apa pun: seluruh
    # skrip, handler, iframe, gambar, tautan keluar, kelas, dan id
    # milik template harus tetap ada di berkas jadi, sebanyak
    # aslinya. Yang kedua khusus fixture jebakan, yang isinya memang
    # disusun untuk diuji satu per satu.
    for label, template, jadi in (
        ("landing", tpl_landing, landing),
        ("AMP", tpl_amp or tpl_landing, amp),
    ):
        if not template:
            continue

        hilang = penanda_hilang(template, jadi, brand, brand_lama)

        t.cek(
            not hilang,
            f"{nama}: penanda beku {label} utuh {hilang[:2]}",
        )

    if fixture:
        for label, potongan in BEKU:
            t.cek(
                potongan in landing and potongan in amp,
                f"{nama}: bagian beku utuh di landing dan AMP - {label}",
            )

        # --- 3. teks pemilik template tersapu ---
        sisa = [x for x in SISA_TEMPLATE if x in landing]
        t.cek(not sisa, f"{nama}: teks pemilik template tersapu {sisa[:3]}")

    # --- 4. jumlah bagian mengikuti template, bukan ditambah ---
    #
    # Diadu dengan templatenya sendiri supaya berlaku untuk template
    # apa pun: yang tidak punya blockquote tidak dituntut punya
    # ulasan, dan yang punya dua puluh heading dituntut tetap punya
    # dua puluh.
    for tag in ("h1", "h2", "h3", "p", "blockquote"):
        pola = f"<{tag}[ >]"
        asal = len(re.findall(pola, tpl_landing, re.IGNORECASE))
        jadi = len(re.findall(pola, landing, re.IGNORECASE))

        t.cek(
            asal == jadi,
            f"{nama}: jumlah <{tag}> sama dengan template "
            f"({asal} -> {jadi})",
        )

    # --- 4b. slot utama benar-benar terisi ---
    t.cek(len(title) >= 30, f"{nama}: title terisi ({len(title)})")
    t.cek(len(desc) >= 100, f"{nama}: description terisi ({len(desc)})")
    t.cek(bool(h1), f"{nama}: H1 terisi")

    if re.search(r"<h3[ >]", tpl_landing, re.IGNORECASE):
        t.cek(len(faq) >= 1, f"{nama}: FAQ terisi ({len(faq)})")

    t.cek(len(para) >= 2, f"{nama}: paragraf terisi ({len(para)})")

    if re.search(r"<blockquote[ >]", tpl_landing, re.IGNORECASE):
        t.cek(len(ulasan) >= 1, f"{nama}: ulasan terisi ({len(ulasan)})")

    # --- 5. pemeriksa akhir dijalankan lagi di luar pipeline ---
    hasil = verify_pages(
        landing_html=landing,
        amp_html=amp,
        template_landing=tpl_landing,
        template_amp=tpl_amp,
        brand=brand,
        old_brand=brand_lama,
        keyword=keyword,
        region=lang,
        # Peran yang benar-benar punya slot di template AMP, dihitung
        # dari templatenya sendiri. Tanpa ini, template AMP yang H1-nya
        # terbelah tag di dalamnya dilaporkan "tidak sinkron" untuk
        # sesuatu yang tidak ada isian yang bisa menyamakannya.
        amp_roles=peran_slot(tpl_amp, brand_lama, lang) if tpl_amp else None,
    )

    t.cek(
        not hasil["hard"],
        f"{nama}: pemeriksa akhir nol penahan {hasil['hard'][:2]}",
    )

    # Pengulangan lintas peran dilaporkan sebagai catatan di pipeline,
    # tapi DI SINI dihitung gagal. Bedanya disengaja: pipeline tidak
    # boleh membatalkan halaman karena satu kalimat yang berulang,
    # sedangkan pemeriksaan mutu memang ada untuk menemukannya.
    ulang = [x for x in hasil["soft"] if "kalimat yang sama" in x]
    t.cek(not ulang, f"{nama}: nol kalimat berulang antar peran {ulang[:2]}")

    # Panjang title dan deskripsi dicatat sebagai peringatan lunak di
    # pipeline - halaman yang isinya benar tidak pantas dibatalkan
    # karena judulnya meleset lima karakter. Di sini keduanya
    # dihitung GAGAL, karena rentangnya keputusan pengguna dan
    # pemeriksaan mutu memang ada untuk menemukan yang meleset.
    panjang = [x for x in hasil["soft"] if "di luar rentang" in x]
    t.cek(not panjang, f"{nama}: panjang title dan deskripsi sesuai {panjang}")

    mirip = [x for x in hasil["soft"] if "hampir sama dengan title" in x]
    t.cek(not mirip, f"{nama}: deskripsi bukan salinan title")

    # Judul yang menumpuk dua janji dipisah koma. Satu koma masih
    # wajar; dua sudah daftar atribut, bukan judul.
    t.cek(
        title.count(",") <= 1,
        f"{nama}: title paling banyak satu koma ({title.count(',')})",
    )

    # Kalimat yang berakhir di klausa daftar pendek.
    #
    # DICATAT, bukan dihitung gagal. Bentuknya sama persis dengan
    # bentuk yang ditinggalkan pemotongan slot - ", dan hasil
    # kemenangan." - tapi juga sama persis dengan kalimat yang
    # memang ditulis begitu dan utuh: "Putaran pertama langsung
    # muncul, dan tampilan jernih." Dari teks jadi saja keduanya
    # tidak bisa dibedakan; yang membedakan adalah apakah teks
    # aslinya masih berlanjut sesudah titik potong, dan itu cuma
    # terlihat di tempat pemotongannya - lihat drop_cut_tail
    # beserta ujinya di tests/test_text_trim.py.
    gantung = [
        potongan[:70]
        for potongan in [desc] + para + ulasan
        if re.search(
            r",\s+(?:dan|atau|serta|maupun)\s+\S+(?:\s+\S+)?\.$",
            potongan or "",
        )
    ]

    for satu in gantung[:3]:
        print(f"   CATATAN     : kalimat berakhir di klausa daftar "
              f"pendek - {satu}", flush=True)

    # --- 6. brand ---
    t.cek(brand in landing, f"{nama}: ejaan brand persis ada di halaman")

    if brand_lama:
        # Nama pemilik template sebelumnya tidak boleh tersisa di
        # teks yang dibaca orang. Yang di dalam blok iklan memang
        # tidak pernah disentuh, jadi yang dihitung teks badannya.
        from generators.final_verify import read_page as _baca

        sisa_lama = _baca(landing)["body_text"].count(brand_lama)

        t.cek(
            sisa_lama == 0,
            f"{nama}: nama brand lama '{brand_lama}' tersapu dari teks "
            f"halaman ({sisa_lama} tersisa)",
        )
    salah = brand_typos(gabung, brand)
    t.cek(not salah, f"{nama}: nol ejaan brand yang salah {salah[:3]}")

    # --- 7. token sampah dan klaim ---
    sampah = garbage_tokens(gabung)
    t.cek(not sampah, f"{nama}: nol token sampah {sampah[:3]}")

    karangan = fabricated_claims(gabung)
    t.cek(not karangan, f"{nama}: nol klaim karangan {karangan[:3]}")

    # --- 8. landing == AMP ---
    for kunci, label in (
        ("title", "title"),
        ("meta_description", "description"),
    ):
        kiri = halaman_landing[kunci]
        kanan = halaman_amp.get(kunci, "")

        t.cek(
            kiri == kanan and bool(kiri),
            f"{nama}: landing dan AMP sama - {label}",
        )

    # H1 hanya diadu kalau template AMP-nya memang punya slot H1.
    # Kalau tidak, tidak ada isian yang bisa menyamakannya - lihat
    # keterangan di verify_pages.
    amp_punya_h1 = bool(tpl_amp) and "h1" in peran_slot(
        tpl_amp, brand_lama, lang
    )

    if amp_punya_h1:
        amp_h1 = (halaman_amp.get("h1") or [""])[0]

        t.cek(h1 == amp_h1, f"{nama}: landing dan AMP sama - H1")

    # --- 9. bahasa ---
    if lang == "th":
        for label, satu in (("title", title), ("desc", desc), ("h1", h1)):
            t.cek(
                thai_share(satu, brand, keyword) > 0.5,
                f"{nama}: {label} berbahasa Thai",
            )

        meleset = [x for x in para if thai_share(x, brand, keyword) <= 0.5]
        t.cek(not meleset, f"{nama}: seluruh paragraf berbahasa Thai")
    else:
        bocor = [x for x in semua if thai_share(x, brand, keyword) > 0.2]
        t.cek(not bocor, f"{nama}: nol bocoran aksara Thai")

    # --- 10. keyword tidak dijejalkan ---
    berlebih = [
        (potongan[:50], jumlah)
        for potongan in semua
        if potongan
        and (
            jumlah := len(
                re.findall(re.escape(keyword.casefold()), potongan.casefold())
            )
        )
        > 1
    ]

    t.cek(
        not berlebih,
        f"{nama}: tidak ada slot yang menyebut keyword lebih dari sekali "
        f"{berlebih[:2]}",
    )

    # --- 11. FAQ dan ulasan benar-benar berbeda ---
    t.cek(
        len({x.casefold() for x in faq}) == len(faq),
        f"{nama}: tidak ada pertanyaan FAQ yang kembar",
    )
    t.cek(
        len({x.casefold() for x in ulasan}) == len(ulasan),
        f"{nama}: tidak ada ulasan yang kembar",
    )

    pembuka = [x.split()[0].casefold() for x in ulasan if x.split()]
    t.cek(
        len(set(pembuka)) == len(pembuka) or len(pembuka) <= 1,
        f"{nama}: tiap ulasan dibuka kata yang berbeda {pembuka}",
    )

    # --- 12. JSON-LD ---
    for label, html, template in (
        ("landing", landing, tpl_landing),
        ("AMP", amp, tpl_amp),
    ):
        blok = read_page(html)["jsonld"]
        sah = all(json_sah(satu) for satu in blok)

        # Blok data terstruktur hanya dituntut ada kalau templatenya
        # memang punya - atau kalau halamannya menampilkan ulasan,
        # yang membuat NEIIU menambahkan blok Review sendiri. Template
        # AMP yang memang tidak membawa JSON-LD tidak sedang cacat.
        wajib = bool(template) and bool(read_page(template)["jsonld"])

        t.cek(
            sah and (bool(blok) or not wajib),
            f"{nama}: JSON-LD {label} sah ({len(blok)} blok)",
        )

    return {"title": title, "desc": desc, "h1": h1}


def jalankan(pilihan, template_id=0):
    uid = buat_pengguna()

    pengguna = {
        "id": uid,
        "username": NAMA_UJI,
        "role": "user",
        "token_balance": 99,
        "is_active": 1,
    }

    session_asli, require_asli = web_app.session_user, web_app.require_user
    web_app.session_user = lambda request: pengguna
    web_app.require_user = lambda request: pengguna

    client = TestClient(web_app.app)
    t = Tally()
    ringkas = {}
    job_ids = []
    tid = 0

    try:
        if template_id:
            # Template nyata milik pengguna sungguhan, disalin ke
            # pengguna uji supaya pemeriksaan kepemilikan tetap
            # berjalan apa adanya.
            asli = read_template_files(int(template_id), 1)
            tpl_landing = asli["landing"]
            tpl_amp = asli.get("amp") or ""
            berkas = {"landing": ("landing.html", tpl_landing, "text/html")}

            if tpl_amp:
                berkas["amp"] = ("amp.html", tpl_amp, "text/html")

            jawab = client.post(
                "/api/neiiu/templates",
                data={"name": f"E2E salinan {template_id}"},
                files=berkas,
            )
        else:
            tpl_landing, tpl_amp = LANDING, AMP
            jawab = client.post(
                "/api/neiiu/templates",
                data={"name": "E2E fixture jebakan"},
                files={
                    "landing": ("landing.html", LANDING, "text/html"),
                    "amp": ("amp.html", AMP, "text/html"),
                },
            )

        if jawab.status_code != 200:
            raise SystemExit(f"unggah template gagal: {jawab.text}")

        tid = jawab.json()["template_id"]

        print(f"pengguna uji {uid}, template {tid}\n", flush=True)

        for nama in pilihan:
            brand, keyword, lang, brand_lama = CASES[nama]

            print("=" * 74)
            print(
                f"{nama}  brand={brand}  keyword={keyword}  language={lang}"
            )
            print("=" * 74, flush=True)

            mulai = time.monotonic()

            jawab = client.post(
                "/api/neiiu/jobs",
                json={
                    "keyword": keyword,
                    "brand_name": brand,
                    "region": lang,
                    "template_id": tid,
                    "template_brand": brand_lama,
                    "use_cache": True,
                    "analyze_only": False,
                    "history_scope": "qa",
                },
            )

            if not t.cek(
                jawab.status_code == 200,
                f"{nama}: POST /api/neiiu/jobs -> 200 ({jawab.status_code} "
                f"{jawab.text[:120]})",
            ):
                continue

            job_id = jawab.json()["job_id"]
            job_ids.append(job_id)
            job = {}

            while True:
                time.sleep(10)
                job = client.get(f"/api/neiiu/jobs/{job_id}").json()["job"]

                if job.get("status") in ("success", "error", "cancelled"):
                    break

                print(
                    f"   .[{job.get('step')}/{job.get('total_steps')}] "
                    f"{str(job.get('step_label'))[:70]}",
                    flush=True,
                )

            menit = (time.monotonic() - mulai) / 60

            if job.get("status") != "success":
                t.cek(False, f"{nama} GAGAL: {str(job.get('error'))[:250]}")
                continue

            for baris in job.get("log") or []:
                isi = str(
                    baris.get("text") if isinstance(baris, dict) else baris
                )

                if any(
                    kata in isi.lower()
                    for kata in (
                        "catatan:",
                        "tolak:",
                        "dibiarkan",
                        "kependekan",
                        "tidak terisi",
                        "dibuang",
                        "peringatan",
                    )
                ):
                    print(f"   LOG> {isi[:160]}")

            landing = client.get(
                f"/neiiu/jobs/{job_id}/preview/index.html"
            ).text
            amp = client.get(f"/neiiu/jobs/{job_id}/preview/amp.html").text

            print(f"\n   waktu       : {menit:.1f} menit")
            print(
                f"   skor SEO    : "
                f"{(job.get('summary') or {}).get('seo_score')}"
            )

            ringkas[nama] = audit(
                nama,
                brand,
                keyword,
                lang,
                landing,
                amp,
                tpl_landing,
                tpl_amp,
                t,
                fixture=not template_id,
                brand_lama=brand_lama,
            )
            ringkas[nama]["menit"] = menit
            print(flush=True)

    finally:
        for job_id in job_ids:
            try:
                client.request("DELETE", f"/api/neiiu/jobs/{job_id}")
            except Exception:
                pass

        if tid:
            try:
                client.delete(f"/api/neiiu/templates/{tid}")
            except Exception:
                pass

        web_app.session_user, web_app.require_user = session_asli, require_asli
        bersihkan(uid)
        print(f"\ndata uji dibersihkan (pengguna {uid})")

    print("\n" + "=" * 74)

    for nama, isi in ringkas.items():
        print(
            f"{nama}  {isi['menit']:.1f} menit  {isi['title'][:60]}"
        )

    print("-" * 74)
    print(f"LULUS: {t.lulus}   GAGAL: {t.gagal}")

    for satu in t.catatan:
        print(f"   ! {satu}")

    print("=" * 74, flush=True)

    return 1 if t.gagal else 0


def main(argv):
    template_id = 0
    pilihan = []

    sisa = list(argv)

    while sisa:
        satu = sisa.pop(0)

        if satu == "--template":
            template_id = int(sisa.pop(0))
        elif satu.upper() in CASES:
            pilihan.append(satu.upper())

    return jalankan(pilihan or list(CASES), template_id)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    raise SystemExit(main(sys.argv[1:]))
