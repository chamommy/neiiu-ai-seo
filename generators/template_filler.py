"""
Mengisi template unggahan pengguna dengan konten baru.

Alurnya kebalikan dari generator biasa. Generator biasa menyusun
konten lalu membangun halaman di sekelilingnya. Di sini halamannya
sudah ada dan tidak boleh berubah, jadi templatelah yang menentukan
berapa banyak konten yang dibutuhkan: kalau template punya delapan
kartu FAQ, yang diminta ke AI juga tepat delapan.

Jumlah dari model tidak pernah dipercaya begitu saja. Schema
dinamis dipakai untuk mengarahkan, tapi dukungan minItems di
llama.cpp berbeda-beda antar versi, jadi hasilnya selalu
dicocokkan ulang secara deterministik sesudahnya.
"""

import re

from datetime import datetime, timedelta

from generators.schema_generator import json_for_html
from generators.brand_swap import (
    brand_edits,
    build_pattern,
    echo_edits,
    normalize,
)
from generators.jsonld_filler import has_reviews, jsonld_edits
from generators.script_text import script_edits
from generators.template_guard import verify
from generators.template_scanner import apply_edits, scan
from generators.template_slots import build_slot_map
from utils.region import format_date, get_region, iso_date
from utils.text import trim_to_width


def region_cities(region: str) -> list[str]:
    """
    Nama kota yang pantas ditulis di halaman zona itu.
    """
    return get_region(region)["city_names"]


# Nilai rating yang dipasang di schema. Ditetapkan di sini, bukan
# diminta ke AI, supaya angkanya tidak berubah tiap run dan tidak
# ada model yang mengarang 4.9 dari 12.483 ulasan.
REVIEW_RATING = 4.6


# Peran yang isinya berupa daftar. Sisanya tunggal.
LIST_ROLES = (
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "review_author",
    "caption",
    "nav_label",
    "list_item",
    "table_cell",
    "label",
)

# Peran yang jumlah isiannya dibatasi oleh pasangannya, DAN ARAHNYA
# hanya satu.
#
# Yang terbaca sebagai halaman rusak adalah pertanyaan baru yang
# berdiri di atas jawaban lama. Kebalikannya tidak: jawaban baru di
# bawah pertanyaan yang tidak dikenali sebagai slot tetap wajar,
# karena pertanyaan itu tertulis ulang lewat perannya sendiri.
#
# Dulu batas ini dipasang dua arah, dan itu merugikan dua kali.
# Template dengan 8 tempat pertanyaan tapi 17 tempat jawaban membuat
# 9 jawaban dibiarkan memakai kalimat asli template. Lebih parah,
# template yang menaruh nama pengulas di dalam kalimat ulasannya -
# jadi tidak punya slot review_author sama sekali - membuat SELURUH
# ulasannya tidak terisi, karena batasnya jadi nol.
CAPPED_BY_PAIR = {
    "faq_question": "faq_answer",
    "review_author": "review_text",
}

# Peran yang isinya dihitung sendiri di Python, tidak diminta ke AI.
# Tanggal yang dikarang model sering tidak masuk akal (bulan ke-13,
# tahun di masa depan) dan bentuk kalendernya tidak bisa dijamin.
GENERATED_ROLES = ("date", "review_date", "lang", "city", "brand")

# Peran yang teks barunya harus berarti sama dengan teks lamanya,
# bukan tulisan baru yang bebas. Menu, tombol, dan sel tabel menunjuk
# ke sesuatu yang nyata di situs itu; menggantinya dengan kata lain
# membuat tautannya menyesatkan meskipun alamatnya tidak berubah.
KEEP_MEANING_ROLES = ("nav_label", "table_cell", "label")


def derive_spec(slot_map: dict) -> dict:
    """
    Menurunkan kebutuhan konten dari template.

    Yang keluar dari sini yang menentukan bentuk permintaan ke AI,
    bukan sebaliknya.
    """
    roles = slot_map["roles"]

    spec: dict[str, dict] = {}

    for role, slots in roles.items():
        if role in GENERATED_ROLES:
            continue

        # Semua slot ikut, tanpa dibatasi.
        #
        # Dulu ada batas per peran di sini, karena satu permintaan ke
        # model tidak muat menampung 658 teks sekaligus. Batas itu
        # menyelesaikan masalah yang salah: yang tidak muat bukan
        # templatenya, melainkan cara memintanya. Sejak permintaannya
        # dipecah beberapa giliran di content_batches, seluruh slot
        # kebagian dan tidak ada lagi kalimat asli template yang
        # tertinggal di halaman terbit.
        budgets = [slot["budget"] for slot in slots]

        spec[role] = {
            "count": len(slots),
            # Batas terkecil di kelompoknya. Hanya untuk dilaporkan;
            # BUKAN batas yang dikirim ke model. Memakai yang
            # terkecil untuk seluruh kelompok membuat satu slot
            # sempit mencekik semuanya: tombol "Daftar Sekarang" yang
            # sebenarnya punya ruang 20 kolom ikut dipotong jadi 8
            # cuma karena ada tautan "Promo" di menu yang sama.
            "max_length": min(budgets),
            # Batas yang dipakai sebagai plafon ke model. Tiap slot
            # tetap dirapikan ke jatahnya sendiri di build_edits.
            "max_length_any": max(budgets),
            # Jatah tiap slot, urut dokumen, supaya model bisa
            # menakar panjang per teks alih-alih menulis semuanya
            # sepanjang slot terlebar.
            "budgets": budgets,
        }

        if role in KEEP_MEANING_ROLES:
            # Teks lamanya ikut dikirim ke AI supaya artinya
            # dipertahankan. Tanpa ini, label ditulis sebagai daftar
            # bebas lalu dibagikan urut dokumen, dan tautan menuju
            # /syarat bisa berakhir bertuliskan "Kota" - menunya
            # jadi berbohong soal tujuannya sendiri.
            spec[role]["samples"] = [
                " ".join(slot["current"].split())[:80]
                for slot in slots
            ]

    return spec


def merge_specs(*specs: dict) -> dict:
    """
    Menggabungkan kebutuhan beberapa berkas template jadi satu.

    Landing page dan AMP hampir tidak pernah punya jumlah slot yang
    sama persis; versi AMP biasanya lebih ringkas. Kalau isi hanya
    dipesan sebanyak slot landing, slot AMP yang lebih banyak tidak
    kebagian dan kartu sisanya terbit dengan teks lama milik pemilik
    template - teks tentang keyword yang sama sekali berbeda.

    Jumlah diambil yang terbanyak supaya semua slot kebagian, dan
    panjang diambil yang paling sempit supaya teksnya tetap muat di
    berkas yang tata letaknya paling ketat.
    """
    merged: dict[str, dict] = {}

    for spec in specs:
        for role, rule in (spec or {}).items():
            if role not in merged:
                merged[role] = dict(rule)
                continue

            current = merged[role]

            current["count"] = max(current["count"], rule["count"])
            current["max_length"] = min(
                current["max_length"],
                rule["max_length"],
            )
            current["max_length_any"] = max(
                current["max_length_any"],
                rule["max_length_any"],
            )

            # Contoh teks lama dan jatah per slot diambil dari berkas
            # yang slotnya paling banyak, supaya jumlahnya selalu
            # cukup untuk dipasangkan dengan jumlah yang diminta.
            for kunci in ("samples", "budgets"):
                if len(rule.get(kunci, [])) > len(current.get(kunci, [])):
                    current[kunci] = rule[kunci]

    return merged


def scale_spec(spec: dict, chars_per_column: float) -> dict:
    """
    Mengubah jatah panjang dari kolom tampilan jadi jumlah karakter.

    Semua jatah dihitung dalam kolom, karena kolomlah yang
    menentukan apakah sebuah label masih muat di tata letaknya. Tapi
    yang bisa dihitung model dan dipaksakan JSON Schema adalah
    karakter, dan untuk aksara bertumpuk seperti Thai dua satuan itu
    berbeda jauh. Mengirim angka kolom apa adanya berarti menyuruh
    model menulis dalam separuh ruang yang sebenarnya tersedia.
    """
    if chars_per_column <= 1:
        return spec

    diperbesar: dict[str, dict] = {}

    for role, rule in spec.items():
        salinan = dict(rule)

        for kunci in ("max_length", "max_length_any"):
            if kunci in salinan:
                salinan[kunci] = int(salinan[kunci] * chars_per_column)

        if salinan.get("budgets"):
            salinan["budgets"] = [
                int(nilai * chars_per_column) for nilai in salinan["budgets"]
            ]

        diperbesar[role] = salinan

    return diperbesar


# Kelonggaran plafon schema terhadap batas yang diminta di prompt.
# Grammar harus jadi jaring pengaman, bukan yang pertama kena:
# potongannya mentah dan tidak bisa diperbaiki lagi.
SCHEMA_HEADROOM = 1.3


def build_dynamic_schema(spec: dict) -> dict:
    """
    Menyusun JSON Schema yang jumlahnya persis mengikuti template.
    """
    properties: dict[str, dict] = {}
    required: list[str] = []

    def text_field(role: str) -> dict:
        # Plafon diambil dari slot TERLEBAR di kelompoknya, bukan
        # tersempit, lalu dilonggarkan lagi.
        #
        # maxLength di schema dipaksakan grammar llama.cpp dengan cara
        # memutus string begitu batasnya kena. Pemutusan itu tidak tahu
        # apa-apa soal kata maupun tanda yang menempel, jadi kalau
        # grammar yang lebih dulu kena, hasilnya potongan mentah yang
        # tidak bisa diperbaiki lagi di tahap mana pun. Batas yang
        # sungguhan ditegakkan belakangan per slot, di tempat yang
        # tahu cara memotong tanpa merusak huruf.
        return {
            "type": "string",
            "maxLength": int(spec[role]["max_length_any"] * SCHEMA_HEADROOM),
        }

    def list_field(role: str) -> dict:
        count = spec[role]["count"]

        return {
            "type": "array",
            "minItems": count,
            "maxItems": count,
            "items": text_field(role),
        }

    for role in ("title", "meta_description", "meta_keywords", "h1"):
        if role in spec:
            properties[role] = text_field(role)
            required.append(role)

    for role in LIST_ROLES:
        if role in spec and spec[role]["count"] > 0:
            properties[role] = list_field(role)
            required.append(role)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# Kelebihan lebar yang dibiarkan lewat kalau teksnya tidak punya
# batas kata untuk dipotong. Jatah tiap slot sudah memuat toleransi
# 35% terhadap teks aslinya, jadi tambahan ini hanya menyangkut teks
# yang sedikit melewati jatah itu - bukan jawaban yang kepanjangan.
OVERFLOW_TOLERANCE = 1.3


def clean_line(value, limit: int) -> str:
    """
    Merapikan satu teks dan memastikan panjangnya masuk akal.

    Pemotongannya diserahkan ke trim_to_width supaya potongan tidak
    pernah jatuh di tengah huruf. Memotong dengan iris biasa
    menyisakan tanda vokal tanpa huruf induknya, dan itu tampil
    sebagai karakter menggantung yang tidak terbaca.
    """
    return trim_to_width(value, limit, OVERFLOW_TOLERANCE)


def fit_content_to_spec(
    content: dict,
    spec: dict,
    fallbacks: dict | None = None,
) -> tuple[dict, list[str]]:
    """
    Mencocokkan jumlah isi dengan jumlah slot, apa pun jawaban model.

    Kelebihan dipotong. Kekurangan ditambal dari bahan yang sudah
    ada di blueprint. Kalau tetap kurang, slot sisanya dibiarkan
    memakai teks asli template: kartu yang isinya teks lama masih
    jauh lebih baik daripada kartu kosong.
    """
    filled: dict = {}
    warnings: list[str] = []
    spare = fallbacks or {}

    for role, rule in spec.items():
        # Plafon terlebar, bukan tersempit. Penyesuaian ke jatah tiap
        # slot dikerjakan belakangan di build_edits, di mana slot yang
        # dimaksud sudah diketahui - dan di situ pula setiap berkas
        # dirapikan menurut tata letaknya sendiri, bukan menurut
        # berkas paling sempit di antara landing dan AMP.
        limit = rule.get("max_length_any") or rule["max_length"]

        if role not in LIST_ROLES:
            nilai = content.get(role, "")

            # Peran tunggal yang dijawab sebagai daftar atau objek
            # akan tertulis di halaman sebagai repr Python kalau
            # dibiarkan, misalnya "['Judul']".
            if isinstance(nilai, (list, tuple)):
                nilai = nilai[0] if nilai else ""
            elif not isinstance(nilai, (str, int, float)):
                nilai = ""

            filled[role] = clean_line(nilai, limit)

            if not filled[role]:
                warnings.append(
                    f"AI tidak mengisi {role}, slotnya dilewati."
                )

            continue

        wanted = rule["count"]

        raw_items = content.get(role, [])

        # Model kadang mengembalikan satu string untuk peran yang
        # seharusnya daftar. Kalau string itu langsung diiterasi,
        # yang masuk ke slot adalah huruf per huruf: kartu FAQ
        # pertama berisi "J", kedua berisi "u". Halamannya terbit
        # dan tidak ada pemeriksa struktur yang bisa melihatnya,
        # karena strukturnya memang tidak rusak.
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        elif not isinstance(raw_items, (list, tuple)):
            raw_items = []

        items = [
            clean_line(item, limit)
            for item in raw_items
            if isinstance(item, (str, int, float))
            and clean_line(item, limit)
        ]

        if len(items) > wanted:
            warnings.append(
                f"AI menulis {len(items)} {role} padahal template "
                f"punya {wanted} slot, kelebihannya dibuang."
            )
            items = items[:wanted]

        if len(items) < wanted:
            for candidate in spare.get(role, []):
                if len(items) >= wanted:
                    break

                clean = clean_line(candidate, limit)

                if clean and clean not in items:
                    items.append(clean)

        if len(items) < wanted:
            warnings.append(
                f"Hanya {len(items)} dari {wanted} {role} yang terisi, "
                "sisanya memakai teks asli template."
            )

        filled[role] = items

    filled["_by_old"] = pair_by_old_text(spec, filled)

    return filled, warnings


def balance_paired_roles(content: dict) -> list[str]:
    """
    Menyamakan jumlah pertanyaan dengan jumlah jawaban yang tersedia.

    Dijalankan SESUDAH semua giliran disatukan, bukan di dalam tiap
    giliran. Pertanyaan dan jawabannya sering jatuh di giliran yang
    berbeda, dan menyeimbangkan per giliran berarti memangkas satu
    sisi hanya karena pasangannya belum dikerjakan - giliran yang
    isinya pertanyaan saja akan dipotong habis jadi nol.

    Arahnya satu, sama seperti CAPPED_BY_PAIR: yang dipangkas
    pertanyaannya, bukan jawabannya. Pertanyaan baru di atas jawaban
    lama terbaca sebagai halaman rusak; jawaban yang lebih banyak
    dari pertanyaannya tidak.
    """
    catatan: list[str] = []

    for dibatasi, pembatas in CAPPED_BY_PAIR.items():
        a = content.get(dibatasi)
        b = content.get(pembatas)

        if not a or b is None or len(a) <= len(b):
            continue

        catatan.append(
            f"{len(a)} {dibatasi} dan {len(b)} {pembatas} tidak sejajar; "
            f"dipakai {len(b)} supaya tidak ada pertanyaan baru yang "
            "berdiri di atas jawaban lama."
        )

        content[dibatasi] = a[: len(b)]

    return catatan


def pair_by_old_text(spec: dict, filled: dict) -> dict:
    """
    Memetakan teks lama ke penggantinya untuk peran yang berarti.

    Label menu dibagikan urut dokumen, dan itu benar selama slotnya
    berasal dari berkas yang sama dengan contoh yang dikirim ke AI.
    Landing page dan AMP tidak begitu: AMP biasanya cuma punya satu
    tautan di footer, sementara contohnya diambil dari landing yang
    punya enam. Slot pertama AMP lalu kebagian teks pertama landing,
    sehingga tautan menuju /syarat terbit bertuliskan "Promo" -
    alamatnya benar, tulisannya berbohong.

    Dengan peta ini pencocokannya lewat teks lamanya sendiri, jadi
    setiap berkas mendapat padanan yang memang untuk teks itu, tidak
    peduli urutan atau jumlah slotnya.
    """
    peta: dict[str, dict[str, str]] = {}

    for role, rule in spec.items():
        contoh = rule.get("samples") or []
        baru = filled.get(role) or []

        if not contoh or not baru:
            continue

        pasangan = {
            normalize(lama): teks
            for lama, teks in zip(contoh, baru)
            if normalize(lama) and teks
        }

        if pasangan:
            peta[role] = pasangan

    return peta


def generated_dates(count: int, brand: dict) -> list[dict]:
    """
    Membuat tanggal yang menurun dari hari ini.

    Tanggal yang tampil memakai kalender zona, sedangkan nilai untuk
    atribut datetime tetap masehi ISO. Menuliskan tahun Buddha di
    atribut mesin akan membuat tanggalnya terbaca 543 tahun di masa
    depan oleh mesin pencari.
    """
    region = brand.get("region", "id")
    today = datetime.now()

    return [
        {
            "text": format_date(today - timedelta(days=index * 3), region),
            "iso": iso_date(today - timedelta(days=index * 3)),
        }
        for index in range(count)
    ]


def build_edits(
    slot_map: dict,
    content: dict,
    brand: dict,
) -> tuple[list[dict], list[str]]:
    """
    Memasangkan isi baru ke slot yang sesuai.
    """
    edits: list[dict] = []
    notes: list[str] = []

    roles = slot_map["roles"]

    for role, slots in roles.items():
        if role == "lang":
            for slot in slots:
                edits.append(
                    {**slot, "text": brand.get("html_lang", "id")}
                )

            continue

        if role == "brand":
            # Tulisan logo dan nama situs: diisi nama brand baru apa
            # adanya, tidak diminta ke AI dan tidak dipotong batas
            # panjang. Nama brand yang terpotong lebih buruk daripada
            # header yang sedikit lebih lebar.
            nama = str(brand.get("site_name", "")).strip()

            if nama:
                for slot in slots:
                    edits.append({**slot, "text": nama})

            continue

        if role == "city":
            # Nama kota diambil dari daftar zona, bukan dari AI.
            # Model kecil rutin mengarang kota yang tidak ada, dan
            # kota palsu di halaman yang menargetkan satu negara
            # justru merusak sinyal lokalnya.
            kota = region_cities(brand.get("region", "id"))

            for index, slot in enumerate(slots):
                edits.append(
                    {**slot, "text": kota[index % len(kota)]}
                )

            continue

        if role in GENERATED_ROLES:
            # Dikelompokkan per elemen, bukan per urutan slot. Satu
            # <time> punya dua slot sekaligus: nilai atribut datetime
            # dan teks yang terbaca di layar. Kalau dibagikan
            # berurutan, keduanya dapat tanggal berbeda, sehingga
            # mesin pencari dan pembaca melihat hari yang tidak sama
            # untuk ulasan yang sama.
            groups: dict[int, list[dict]] = {}

            for slot in slots:
                groups.setdefault(slot.get("element_index", -1), []).append(
                    slot
                )

            dates = generated_dates(len(groups), brand)

            for moment, members in zip(dates, groups.values()):
                for slot in members:
                    edits.append(
                        {
                            **slot,
                            "text": (
                                moment["iso"]
                                if slot["kind"] == "attribute"
                                else moment["text"]
                            ),
                        }
                    )

            continue

        if role in LIST_ROLES:
            items = list(content.get(role, []))

            # Peran berpasangan dipotong sampai sejumlah slot
            # pasangannya. Kalau template punya 4 tempat pertanyaan
            # tapi cuma 3 tempat jawaban, mengisi keempatnya membuat
            # kartu terakhir terbit dengan pertanyaan baru di atas
            # jawaban lama - persis kesalahan yang paling sulit
            # dilihat, karena strukturnya sama sekali tidak rusak.
            pasangan = CAPPED_BY_PAIR.get(role)
            slot_pasangan = roles.get(pasangan, []) if pasangan else []

            # Batas hanya berlaku kalau pasangannya memang ada di
            # template ini. Template yang tidak punya slot pasangan
            # sama sekali bukan template yang setengah berganti; ia
            # cuma menaruh keterangan itu di tempat lain.
            if pasangan and slot_pasangan:
                muat = min(len(slots), len(slot_pasangan))

                if muat < len(slots):
                    notes.append(
                        f"Template punya {len(slots)} tempat {role} tapi "
                        f"{len(slot_pasangan)} tempat {pasangan}; diisi "
                        f"{muat} supaya tidak ada pertanyaan baru yang "
                        "berdiri di atas jawaban lama."
                    )

                slots = slots[:muat]

            # Peran yang artinya harus dipertahankan dicocokkan lewat
            # teks lamanya sendiri. Sisanya - dan slot yang teks
            # lamanya tidak ada di peta - tetap dibagikan urut
            # dokumen seperti biasa.
            peta = (content.get("_by_old") or {}).get(role, {})
            terpakai = set(peta.values())
            antre = [teks for teks in items if teks not in terpakai]

            for slot in slots:
                text = peta.get(normalize(slot["current"]))

                if text is None:
                    if not antre:
                        continue

                    text = antre.pop(0)

                edits.append(
                    {**slot, "text": clean_line(text, slot["budget"])}
                )

            continue

        text = content.get(role, "")

        if not text:
            continue

        for slot in slots:
            edits.append(
                {**slot, "text": clean_line(text, slot["budget"])}
            )

    used = len(edits)
    total = sum(len(items) for items in roles.values())

    if used < total:
        notes.append(
            f"{total - used} slot dibiarkan memakai teks asli template."
        )

    return edits, notes


def brand_left_in_ads(scanned: dict, html: str, old_brand: str) -> int:
    """
    Berapa kali nama brand lama muncul di dalam blok iklan.

    Yang di dalam alamat tidak dihitung, karena di situ namanya
    bagian dari URL dan memang harus tetap - mengubahnya mematikan
    tautan iklannya.
    """
    nama = str(old_brand or "").strip()

    if not nama:
        return 0

    pola = build_pattern(nama)
    jumlah = 0

    for awal, akhir in scanned.get("ads", []):
        badan = re.sub(
            r'(?i)(href|src|srcset|content|action)\s*=\s*'
            r'(["\'])[^"\']*\2',
            "",
            html[awal:akhir],
        )

        jumlah += len(pola.findall(badan))

    return jumlah


def published_content(edits: list[dict], content: dict) -> dict:
    """
    Isi seperti yang BENAR-BENAR terbit, bukan seperti yang diminta.

    Teks dari AI dipotong menyesuaikan lebar slotnya, jadi kalimat
    yang tampak di halaman bisa lebih pendek daripada kalimat yang
    dikirim. Data terstruktur harus memakai versi yang tampak itu.

    Terukur pada halaman jadi: JSON-LD memuat jawaban FAQ "...tidak
    memerlukan verifikasi tambahan untuk dimainkan." sementara yang
    terbaca di halaman berhenti di "...verifikasi tambahan". Google
    mensyaratkan teks FAQ di schema sama persis dengan teks di
    halaman; yang tidak sama diabaikan, atau lebih buruk, dianggap
    schema yang menjanjikan sesuatu yang tidak ada.

    Urutan dokumen dipakai apa adanya. Untuk peran berdaftar itu
    sama dengan urutan isi aslinya, karena slot dibagikan berurutan
    dari antrean yang sama.
    """
    urut = sorted(
        (
            item
            for item in edits
            if item.get("role") and str(item.get("text", "")).strip()
        ),
        key=lambda item: item["start"],
    )

    per_peran: dict[str, list[str]] = {}

    for item in urut:
        per_peran.setdefault(item["role"], []).append(str(item["text"]))

    hasil = dict(content)

    for peran, daftar in per_peran.items():
        if peran in LIST_ROLES:
            hasil[peran] = daftar
        else:
            # Satu kalimat bisa terbit di beberapa tempat dengan
            # lebar berbeda - judul di <title> utuh, di og:title
            # terpotong. Yang terpanjang tetap ada di halaman, jadi
            # itu yang paling aman dipakai.
            hasil[peran] = max(daftar, key=len)

    return hasil


def build_review_block(
    content: dict,
    brand: dict,
    dates: list[dict],
) -> str:
    """
    Menyusun JSON-LD Review dan AggregateRating dari isi ulasan.

    Rating tidak diminta ke AI melainkan ditetapkan di sini, supaya
    angka yang muncul di schema selalu sama dengan yang bisa
    dipertanggungjawabkan dan tidak berubah-ubah tiap run.
    """
    texts = content.get("review_text", [])
    authors = content.get("review_author", [])

    if not texts:
        return ""

    reviews = []

    for index, text in enumerate(texts):
        author = (
            authors[index]
            if index < len(authors)
            else brand.get("site_name", "")
        )

        moment = dates[index] if index < len(dates) else dates[-1]

        reviews.append(
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": author},
                "datePublished": moment["iso"],
                "reviewBody": text,
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": REVIEW_RATING,
                    "bestRating": 5,
                    "worstRating": 1,
                },
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": content.get("h1") or brand.get("site_name", ""),
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": REVIEW_RATING,
            "reviewCount": len(reviews),
            "bestRating": 5,
            "worstRating": 1,
        },
        "review": reviews,
    }

    return (
        '<script type="application/ld+json">'
        + json_for_html(payload)
        + "</script>"
    )


def review_insert_point(html: str, scanned: dict | None = None) -> int:
    """
    Mencari tempat menyisipkan blok schema.

    Ditaruh tepat sebelum </head> karena di situlah blok JSON-LD
    lazim berada, dan penyisipan di satu titik tetap membuat
    perbandingan struktur mudah dibuktikan.

    Letaknya diambil dari hasil pengurai, bukan dari mencari teks
    "</head>" di dalam dokumen. Deretan huruf itu bisa muncul di
    dalam komentar atau di dalam string milik <script> - pola yang
    justru lazim di skrip penulis widget - dan menyisipkan di situ
    menaruh JSON-LD di tempat yang tidak pernah dibaca mesin pencari
    sekaligus merusak skrip yang tidak ada hubungannya.
    """
    for marker in ("head", "body"):
        for item in (scanned or {}).get("end_tags", []):
            if item["tag"] == marker:
                return item["start"]

    return len(html)


def fill_template(
    html: str,
    content: dict,
    brand: dict,
    add_review_schema: bool = True,
    old_brand: str = "",
) -> dict:
    """
    Mengisi satu berkas template dan membuktikan strukturnya utuh.

    Melempar ValueError kalau hasilnya melanggar struktur. Template
    itu milik pengguna; menerbitkan versi yang rusak jauh lebih
    merugikan daripada gagal dengan pesan yang jelas.

    Tiga lapis, berurutan:
      1. Slot diisi teks baru dari AI.
      2. Slot yang tertinggal dibersihkan dari nama brand lama.
      3. Teks lama yang kembar disamakan dengan teks barunya.

    Lapis 2 dan 3 tidak pernah menyentuh slot yang sudah terisi di
    lapis sebelumnya, jadi tidak ada rentang yang ditulis dua kali.
    """
    scanned = scan(html)
    slot_map = build_slot_map(scanned, old_brand)

    edits, notes = build_edits(slot_map, content, brand)

    # Disalin sebelum lapis berikutnya menambah apa pun. Edit gema
    # dan edit nama brand ikut membawa "role" karena disusun dari
    # slot yang sama, dan kalau ikut terhitung, satu kalimat yang
    # kebetulan muncul dua kali di halaman akan tercatat dua kali -
    # menggeser pasangan tanya-jawab di data terstruktur satu langkah.
    edits_isi = list(edits)

    # Slot yang sudah kebagian teks baru, dikenali dari letaknya.
    sudah = {(item["start"], item["end"]): item for item in edits}

    diganti = {
        normalize(item["current"]): str(item["text"])
        for item in edits
        if item.get("kind") != "attribute" and str(item.get("text", "")).strip()
    }

    # Teks kembar didahulukan atas penggantian nama. Kalimat lama
    # yang muncul dua kali - judul yang diulang di footer, misalnya -
    # harus memakai KALIMAT BARU yang sama, bukan sekadar kalimat
    # lama dengan nama brand yang ditukar. Kalau urutannya dibalik,
    # footer terbit berbunyi "DEEFGE Situs Slot Terpercaya" padahal
    # judul barunya "DEEFGE Situs Slot Resmi".
    gema, jumlah_gema = echo_edits(slot_map, sudah, diganti)

    if gema:
        edits.extend(gema)
        sudah.update({(x["start"], x["end"]): x for x in gema})

        notes.append(
            f"{jumlah_gema} teks lama yang kembar disamakan dengan "
            "teks barunya."
        )

    tambahan, jumlah_brand = brand_edits(
        slot_map,
        sudah,
        old_brand,
        brand.get("site_name", ""),
    )

    if tambahan:
        edits.extend(tambahan)
        sudah.update({(x["start"], x["end"]): x for x in tambahan})

        notes.append(
            f"Nama brand lama '{old_brand}' diganti di "
            f"{jumlah_brand} tempat yang tidak kebagian teks baru."
        )

    # Data terstruktur ditulis ulang dari isi yang sama dengan yang
    # terbit di halaman. Tanpa ini, rich result di Google menampilkan
    # pertanyaan, ulasan, dan nama brand milik template lama meskipun
    # seluruh teks yang tampak sudah berganti.
    tanggal = generated_dates(
        max(len(content.get("review_text", [])), 8),
        brand,
    )

    terbit = published_content(edits_isi, content)

    schema, jumlah_schema = jsonld_edits(
        scanned,
        html,
        terbit,
        brand,
        tanggal,
        old_brand,
    )

    if schema:
        edits.extend(schema)
        sudah.update({(x["start"], x["end"]): x for x in schema})

        notes.append(
            f"Data terstruktur diperbarui: {jumlah_schema} nilai di "
            "JSON-LD ikut memakai isi baru."
        )

    # Teks yang tertanam di dalam skrip. Blok konfigurasi milik
    # template menimpakan judulnya sendiri ke halaman saat dibuka,
    # jadi judul yang sudah diganti akan kembali ke judul lama di
    # layar pengunjung kalau blok itu dibiarkan.
    tertanam, jumlah_tertanam = script_edits(
        scanned,
        html,
        diganti,
        old_brand,
        brand.get("site_name", ""),
        content,
    )

    if tertanam:
        edits.extend(tertanam)
        sudah.update({(x["start"], x["end"]): x for x in tertanam})

        notes.append(
            f"{jumlah_tertanam} teks yang tertanam di dalam skrip ikut "
            "diperbarui, termasuk judul yang ditimpakan saat halaman "
            "dibuka."
        )

    # Nama brand lama yang tertinggal di dalam blok iklan. Isi iklan
    # sengaja tidak pernah disentuh, jadi ini bukan sesuatu yang bisa
    # diperbaiki sendiri - tapi mendiamkannya membuat halaman terbit
    # dengan alt="Banner OSB99" di tengah halaman yang seluruhnya
    # sudah bernama lain, tanpa ada yang tahu.
    sisa_iklan = brand_left_in_ads(scanned, html, old_brand)

    if sisa_iklan:
        notes.append(
            f"Nama '{old_brand}' masih ada di {sisa_iklan} tempat di "
            "dalam blok iklan. Isi iklan tidak pernah diubah, jadi "
            "kalau itu bukan iklan pihak lain, gantilah sendiri di "
            "templatenya."
        )

    if slot_map["unquoted"]:
        notes.append(
            f"{len(slot_map['unquoted'])} atribut ditulis tanpa tanda "
            "kutip di template, jadi dibiarkan apa adanya: "
            + ", ".join(sorted(set(slot_map["unquoted"]))[:5])
        )

    if not edits:
        # Dua sebab yang sangat berbeda, dan menyebut sebab yang
        # salah membuat pengguna memperbaiki template yang sebenarnya
        # tidak ada masalahnya.
        if not slot_map["roles"]:
            raise ValueError(
                "Tidak ada satu pun slot isi yang dikenali di template "
                "ini. Pastikan templatenya memuat judul, heading, dan "
                "paragraf, atau tandai bagian yang mau diisi dengan "
                "data-neiiu."
            )

        raise ValueError(
            f"Template ini punya {sum(len(v) for v in slot_map['roles'].values())} "
            "slot yang bisa diisi, tapi AI tidak menghasilkan teks satu "
            "pun untuk mengisinya. Templatenya tidak bermasalah. "
            "Periksa apakah Ollama masih berjalan dan modelnya sanggup "
            "menjawab dalam bahasa yang diminta, lalu ulangi."
        )

    allowance: dict[str, int] = {}

    # Blok ulasan sendiri hanya ditambahkan kalau template belum punya.
    # Template yang sudah membawa Product beserta aggregateRating akan
    # berakhir dengan DUA klaim rating yang berbeda di satu halaman,
    # dan mesin pencari melihatnya sebagai data yang bertentangan -
    # lebih buruk daripada tidak menambahkan apa pun. Yang sudah ada
    # tetap terisi ulasan baru lewat jsonld_edits di atas.
    sudah_punya = has_reviews(scanned, html)

    if sudah_punya:
        notes.append(
            "Template sudah punya data ulasan sendiri, jadi isinya "
            "diperbarui di tempat - bukan ditambah blok kedua."
        )

    # Ulasan hanya boleh diklaim di schema kalau ulasannya memang
    # terbaca di halaman. Terukur pada AMP milik pengguna: berkasnya
    # tidak punya satu pun tempat ulasan - tidak ada kata "ulasan",
    # "review", atau "testimoni" di seluruh teksnya - tapi tetap
    # kebagian blok schema berisi lima ulasan. Itu persis yang
    # dilarang Google: rich result bintang untuk ulasan yang tidak
    # ada di halaman, dan hukumannya tindakan manual untuk seluruh
    # situs, bukan cuma halaman itu.
    tampil_ulasan = bool(slot_map["roles"].get("review_text"))

    boleh_tambah = (
        add_review_schema
        and bool(content.get("review_text"))
        and not sudah_punya
    )

    if boleh_tambah and not tampil_ulasan:
        notes.append(
            "Blok schema Review tidak ditambahkan: halaman ini tidak "
            "menampilkan ulasan, dan schema ulasan untuk teks yang "
            "tidak terlihat melanggar aturan Google."
        )

    if boleh_tambah and tampil_ulasan:
        block = build_review_block(
            terbit,
            brand,
            generated_dates(len(content["review_text"]), brand),
        )

        if block:
            position = review_insert_point(html, scanned)

            # Rentang kosong: tidak ada teks lama yang dibuang,
            # hanya disisipkan di satu titik.
            edits.append(
                {
                    "kind": "raw",
                    "start": position,
                    "end": position,
                    "text": block,
                }
            )

            allowance["script"] = 1
            notes.append(
                f"Blok schema Review ditambahkan untuk "
                f"{len(terbit.get('review_text', []))} ulasan yang "
                "terbaca di halaman."
            )

    filled = apply_edits(html, edits)

    check = verify(html, filled, edits, allowance)

    if not check["ok"]:
        raise ValueError(
            "Hasil pengisian mengubah struktur template: "
            + "; ".join(check["violations"][:3])
        )

    return {
        "html": filled,
        "edits": len(edits),
        "slot_counts": slot_map["counts"],
        "skipped": len(slot_map["skipped"]),
        "notes": notes,
        "stats": check["stats"],
    }
