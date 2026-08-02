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

from datetime import datetime, timedelta

from generators.schema_generator import json_for_html
from generators.template_guard import verify
from generators.template_scanner import apply_edits, scan
from generators.template_slots import build_slot_map
from utils.region import format_date, iso_date


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
)

# Peran yang isi satu slotnya hanya masuk akal kalau slot pasangannya
# ikut terisi. Pertanyaan tanpa jawaban barunya, atau ulasan tanpa nama
# pengulas barunya, terbaca lebih janggal daripada kartu yang seluruhnya
# masih memakai teks lama template.
PAIRED_ROLES = {
    "faq_question": "faq_answer",
    "faq_answer": "faq_question",
    "review_text": "review_author",
    "review_author": "review_text",
}

# Peran yang isinya dihitung sendiri di Python, tidak diminta ke AI.
# Tanggal yang dikarang model sering tidak masuk akal (bulan ke-13,
# tahun di masa depan) dan bentuk kalendernya tidak bisa dijamin.
GENERATED_ROLES = ("date", "review_date", "lang")


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

        budgets = [slot["budget"] for slot in slots]

        spec[role] = {
            "count": len(slots),
            # Batas terkecil yang dipakai, supaya satu teks tidak
            # kepanjangan untuk slot tersempit di kelompoknya.
            "max_length": min(budgets),
            "max_length_any": max(budgets),
        }

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

    return merged


def build_dynamic_schema(spec: dict) -> dict:
    """
    Menyusun JSON Schema yang jumlahnya persis mengikuti template.
    """
    properties: dict[str, dict] = {}
    required: list[str] = []

    def text_field(role: str) -> dict:
        return {
            "type": "string",
            "maxLength": spec[role]["max_length"],
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


def clean_line(value, limit: int) -> str:
    text = " ".join(str(value or "").split())

    if len(text) <= limit:
        return text

    trimmed = text[:limit]
    cut = trimmed.rfind(" ")

    if cut > limit * 0.6:
        trimmed = trimmed[:cut]

    return trimmed.rstrip(" ,.;:-")


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
        limit = rule["max_length"]

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

    # Penyeimbangan pasangan dilakukan PALING AKHIR, sesudah
    # penambalan, bukan sebelumnya.
    #
    # Penambalan hanya punya bahan cadangan untuk satu sisi:
    # pertanyaan bisa diambil dari "People also ask", jawabannya
    # tidak ada. Jadi kalau model kurang menulis, pertanyaan bisa
    # penuh 8 sementara jawaban tetap 3. Slot ke-4 sampai ke-8
    # lalu terbit dengan pertanyaan baru tentang keyword baru di
    # atas jawaban lama milik pemilik template.
    #
    # Dipotong sampai sejajar berarti kartu sisanya memakai
    # pertanyaan lama DAN jawaban lama, yang setidaknya masih
    # nyambung satu sama lain.
    for kiri, kanan in (
        ("faq_question", "faq_answer"),
        ("review_text", "review_author"),
    ):
        if kiri not in filled or kanan not in filled:
            continue

        a, b = filled[kiri], filled[kanan]

        if len(a) == len(b):
            continue

        cukup = min(len(a), len(b))

        warnings.append(
            f"{len(a)} {kiri} dan {len(b)} {kanan} tidak sejajar; "
            f"dipakai {cukup} pasang supaya tidak ada pertanyaan baru "
            "yang berdiri di atas jawaban lama."
        )

        filled[kiri] = a[:cukup]
        filled[kanan] = b[:cukup]

    return filled, warnings


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
            items = content.get(role, [])

            # Peran berpasangan dipotong sampai sejumlah slot
            # pasangannya. Kalau template punya 4 tempat pertanyaan
            # tapi cuma 3 tempat jawaban, mengisi keempatnya membuat
            # kartu terakhir terbit dengan pertanyaan baru di atas
            # jawaban lama - persis kesalahan yang paling sulit
            # dilihat, karena strukturnya sama sekali tidak rusak.
            pasangan = PAIRED_ROLES.get(role)

            if pasangan:
                muat = min(len(slots), len(roles.get(pasangan, [])))

                if muat < len(slots):
                    notes.append(
                        f"Template punya {len(slots)} tempat {role} tapi "
                        f"{muat} tempat {pasangan}; diisi {muat} pasang "
                        "supaya tidak ada yang setengah berganti."
                    )

                slots = slots[:muat]

            for slot, text in zip(slots, items):
                edits.append({**slot, "text": text})

            continue

        text = content.get(role, "")

        if not text:
            continue

        for slot in slots:
            edits.append({**slot, "text": text})

    used = len(edits)
    total = sum(len(items) for items in roles.values())

    if used < total:
        notes.append(
            f"{total - used} slot dibiarkan memakai teks asli template."
        )

    return edits, notes


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
) -> dict:
    """
    Mengisi satu berkas template dan membuktikan strukturnya utuh.

    Melempar ValueError kalau hasilnya melanggar struktur. Template
    itu milik pengguna; menerbitkan versi yang rusak jauh lebih
    merugikan daripada gagal dengan pesan yang jelas.
    """
    scanned = scan(html)
    slot_map = build_slot_map(scanned)

    edits, notes = build_edits(slot_map, content, brand)

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

    if add_review_schema and content.get("review_text"):
        block = build_review_block(
            content,
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
                f"{len(content['review_text'])} ulasan."
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
