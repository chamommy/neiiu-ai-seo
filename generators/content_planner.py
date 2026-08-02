"""
Lapisan AI pipeline NEIIU.

Dua tugas:
1. Menjelaskan kenapa halaman rank 1–10 bisa naik.
2. Menyusun isi landing page baru berdasarkan penjelasan itu.

Keduanya memakai structured output supaya hasilnya langsung bisa
dirender jadi HTML tanpa parsing teks bebas.
"""

import re

from ai.manager import AIManager
from ai.neiiu_prompts import (
    build_content_plan_prompt,
    build_serp_insight_prompt,
    build_template_content_prompt,
)
from generators.content_batches import (
    answer_chars,
    merge_batch_content,
    plan_batches,
)
from generators.template_filler import (
    balance_paired_roles,
    build_dynamic_schema,
    fit_content_to_spec,
    scale_spec,
)
from ai.schemas import CONTENT_PLAN_SCHEMA, SERP_INSIGHT_SCHEMA
from config import (
    AI_CONTEXT_LENGTH,
    AI_MAX_TOKENS_INSIGHT,
    AI_MAX_TOKENS_PLAN,
    AI_MODEL,
    AI_PROVIDER,
)
from utils.region import get_region, slug_for_url
from utils.text import (
    THAI_RANGE,
    count_words,
    estimate_tokens,
    thai_share,
)


# Ruang yang disisakan di luar prompt dan jawaban. Angkanya sama
# dengan kelonggaran yang dipasang ask_structured saat menghitung
# num_ctx, supaya batas yang dihitung di sini tidak melewati context
# yang nanti benar-benar diminta ke Ollama.
CONTEXT_MARGIN = 512

# Porsi ruang satu giliran yang disediakan untuk teks jawaban;
# sisanya untuk daftar permintaan di promptnya. Jawaban diberi porsi
# lebih besar karena itulah yang dipakai halaman, sementara daftar
# permintaan cuma pengantar. Porsi yang terbalik membuat giliran
# penuh keterangan tapi jawabannya terpotong.
ANSWER_SHARE = 0.65

# Sasaran panjang jawaban satu giliran. Bukan batas context - context
# masih sanggup lebih - melainkan ukuran yang membuat prosesnya
# terbaca maju. Di CPU 3,5 token per detik, angka ini kira-kira 17
# menit per giliran; giliran yang tiga kali lebih besar cuma
# memindahkan seluruh risiko ke satu permintaan yang kalau gagal
# menghanguskan sejam kerja.
BATCH_ANSWER_TOKENS = 3500


def round_up(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step


def ask_structured(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    max_tokens: int,
    on_progress=None,
    context_length: int = 0,
) -> dict:
    """
    Mengirim prompt ke AI dan mengembalikan objek JSON hasilnya.

    context_length boleh dipatok dari luar. Itu penting untuk
    permintaan yang dikirim beberapa kali berturut-turut: mengubah
    num_ctx membuat Ollama memuat ulang model dan membuang cache
    prompt, sehingga awalan yang sengaja dibuat identik justru
    diproses ulang dari nol setiap giliran.
    """
    needed = (
        estimate_tokens(system_prompt)
        + estimate_tokens(user_prompt)
        + max_tokens
        + 512
    )

    # Context ditumbuhkan sesuai kebutuhan, bukan dipatok besar.
    # Membiarkannya kurang bikin Ollama memotong bagian awal prompt
    # tanpa error dan hasilnya jadi ngawur, tapi memasang context
    # jauh lebih besar dari yang dipakai cuma memperlambat inferensi
    # dan memakan memori.
    context_length = context_length or max(4096, round_up(needed, 2048))

    if context_length > AI_CONTEXT_LENGTH:
        print(
            f"  Catatan: prompt butuh context {context_length}, "
            f"melewati AI_CONTEXT_LENGTH ({AI_CONTEXT_LENGTH}). "
            "Proses bisa lambat atau kehabisan memori. "
            "Kurangi --crawl untuk memperpendek prompt."
        )

    ai = AIManager(
        provider=AI_PROVIDER,
        model=AI_MODEL,
        max_tokens=max_tokens,
        context_length=context_length,
    )

    result = ai.ask(
        prompt=user_prompt,
        system_prompt=system_prompt,
        response_schema=schema,
        on_progress=on_progress,
    )

    structured = result.get("structured_content")

    if not isinstance(structured, dict):
        raise ValueError(
            "AI tidak mengembalikan JSON terstruktur."
        )

    structured["_metadata"] = {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "prompt_tokens": result.get("prompt_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
    }

    return structured


def generate_serp_insight(
    analysis: dict,
    verbose: bool = True,
    on_progress=None,
) -> dict:
    """
    Menghasilkan penjelasan ranking halaman pertama.

    Kalau AI gagal, pipeline tetap jalan memakai insight fallback
    yang disusun dari data crawl.
    """
    system_prompt, user_prompt = build_serp_insight_prompt(analysis)

    try:
        if verbose:
            print("  Meminta analisis ranking ke AI...")

        insight = ask_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=SERP_INSIGHT_SCHEMA,
            max_tokens=AI_MAX_TOKENS_INSIGHT,
            on_progress=on_progress,
        )

        insight["status"] = "success"

        return insight

    except Exception as error:
        if verbose:
            print(f"  AI gagal ({type(error).__name__}), pakai fallback.")

        fallback = build_fallback_insight(analysis)
        fallback["status"] = "fallback"
        fallback["error"] = f"{type(error).__name__}: {error}"

        return fallback


def build_fallback_insight(analysis: dict) -> dict:
    """
    Insight sederhana dari data crawl, tanpa AI.

    Dipakai supaya generator tetap punya arahan walaupun model
    lokal sedang tidak jalan.
    """
    blueprint = analysis["blueprint"]
    target = blueprint["target"]
    adoption = blueprint["adoption"]

    ranking_analysis = []

    for page in analysis["pages"]:
        if page["status"] != "ok":
            ranking_analysis.append(
                {
                    "position": page["position"],
                    "domain": page["domain"],
                    "why_ranking": (
                        "Halaman tidak bisa di-crawl, "
                        "jadi tidak ada data untuk dinilai."
                    ),
                    "strengths": [],
                    "weaknesses": [],
                }
            )
            continue

        strengths = []
        weaknesses = []

        if page["word_count"] >= target["word_count_median"]:
            strengths.append(
                f"Konten {page['word_count']} kata, "
                "di atas median halaman pertama."
            )
        else:
            weaknesses.append(
                f"Konten {page['word_count']} kata, "
                "di bawah median halaman pertama."
            )

        if page["content"]["keyword_in_title"]:
            strengths.append("Keyword ada di title.")
        else:
            weaknesses.append("Keyword tidak ada di title.")

        if page["signals"]["faq"]["has_faq"]:
            strengths.append("Punya blok FAQ.")

        if page["signals"]["schema_types"]:
            strengths.append(
                "Memakai schema: "
                + ", ".join(page["signals"]["schema_types"][:3])
            )
        else:
            weaknesses.append("Tidak memakai structured data.")

        ranking_analysis.append(
            {
                "position": page["position"],
                "domain": page["domain"],
                "why_ranking": (
                    f"Skor SEO on-page {page['seo_score']}/100 "
                    f"dengan {page['headings']['h2_count']} H2 dan "
                    f"{page['links']['internal_count']} internal link."
                ),
                "strengths": strengths[:4],
                "weaknesses": weaknesses[:3],
            }
        )

    return {
        "serp_summary": (
            f"Halaman pertama untuk '{analysis['keyword']}' "
            f"rata-rata punya {target['word_count_median']} kata, "
            f"{target['h2_median']} H2, dan "
            f"{adoption['faq_percentage']}% di antaranya memakai FAQ."
        ),
        "search_intent": (
            "Belum dianalisis AI. Ditentukan dari pola SERP: "
            "mayoritas halaman bersifat informasional dan komersial."
        ),
        "ranking_analysis": ranking_analysis,
        "content_gaps": [
            f"Belum semua halaman punya FAQ "
            f"({adoption['faq_percentage']}% yang punya).",
            f"Hanya {adoption['amp_percentage']}% halaman "
            "yang menyediakan versi AMP.",
            f"Hanya {adoption['table_percentage']}% halaman "
            "yang memakai tabel perbandingan.",
        ],
        "winning_strategy": [
            f"Target minimal {int(target['word_count_top5_median'])} kata.",
            f"Susun minimal {int(target['h2_median'])} section H2.",
            "Pasang FAQ dengan schema FAQPage.",
            "Sediakan versi AMP yang valid.",
            f"Bangun minimal {int(target['internal_links_median'])} "
            "internal link.",
        ],
        "_metadata": {
            "provider": "fallback",
            "model": "-",
            "prompt_tokens": 0,
            "output_tokens": 0,
        },
    }


def generate_content_plan(
    analysis: dict,
    insight: dict,
    template: dict,
    brand: dict,
    verbose: bool = True,
    on_progress=None,
) -> dict:
    """
    Menghasilkan isi landing page baru dalam bentuk terstruktur.
    """
    system_prompt, user_prompt = build_content_plan_prompt(
        analysis=analysis,
        insight=insight,
        template=template,
        brand=brand,
    )

    if verbose:
        print("  Meminta rencana konten ke AI...")

    plan = ask_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=CONTENT_PLAN_SCHEMA,
        max_tokens=AI_MAX_TOKENS_PLAN,
        on_progress=on_progress,
    )

    return normalize_plan(
        plan,
        analysis["keyword"],
        brand.get("site_name", ""),
        brand.get("region", "id"),
    )


def generate_template_content(
    analysis: dict,
    insight: dict,
    spec: dict,
    brand: dict,
    fallbacks: dict | None = None,
    on_progress=None,
) -> tuple[dict, list[str]]:
    """
    Menghasilkan potongan teks sebanyak slot di template pengguna.

    Dikerjakan beberapa giliran, bukan sekali kirim. Template
    sungguhan punya jauh lebih banyak teks daripada yang muat dalam
    satu context: halaman 720 KB yang dipakai menguji punya 658
    potongan teks. Selama semuanya diminta sekaligus, satu-satunya
    jalan adalah memotong daftar permintaan, dan slot yang terpotong
    terbit dengan kalimat asli milik template.

    Schema tiap giliran dibentuk dari template, bukan konstanta,
    supaya jumlah yang diminta sama persis dengan jumlah tempat yang
    tersedia. Hasilnya tetap dicocokkan ulang sesudahnya, karena
    dukungan minItems di llama.cpp berbeda antar versi.
    """
    # Jatah panjang di spec bersatuan kolom tampilan, karena itu yang
    # menentukan apakah teksnya masih muat di tata letak template.
    # Model dan JSON Schema menghitung karakter, dan untuk aksara
    # bertumpuk seperti Thai satu kolom butuh lebih dari satu
    # karakter. Tanpa penyetaraan ini, batas yang diterima model
    # kira-kira dua pertiga dari ruang yang sebenarnya ada, dan
    # grammar memutus kata di tengah begitu batasnya kena.
    zona = get_region(brand.get("region", "id"))

    spec = scale_spec(spec, zona.get("chars_per_column", 1.0))

    # Berapa karakter yang muat dalam satu token sangat berbeda antar
    # aksara. Tokenizer byte-level memecah aksara Thai hampir satu
    # token per karakter, sedangkan teks Latin sekitar dua.
    per_token = 1.0 if zona["word_mode"] == "unspaced" else 2.0

    # Brief-nya diukur dengan permintaan kosong, karena bagian itulah
    # yang sama di setiap giliran. Sisanya yang bisa dipakai memuat
    # daftar permintaan sekaligus jawabannya.
    sistem_contoh, brief_contoh = build_template_content_prompt(
        analysis=analysis,
        insight=insight,
        spec={},
        brand=brand,
    )

    tetap = estimate_tokens(sistem_contoh) + estimate_tokens(brief_contoh)
    ruang = AI_CONTEXT_LENGTH - tetap - CONTEXT_MARGIN

    # Ruangnya dibagi dua: daftar permintaan di sisi prompt, dan teks
    # jawaban di sisi keluaran. Porsi jawaban dibuat lebih besar
    # karena itu yang dipakai, sementara daftar permintaannya cuma
    # pengantar.
    batches = plan_batches(
        spec,
        answer_budget=max(
            400,
            int(
                min(ruang * ANSWER_SHARE, BATCH_ANSWER_TOKENS) * per_token
            ),
        ),
        prompt_budget=max(400, int(ruang * (1 - ANSWER_SHARE) * per_token)),
    )

    # num_ctx dipatok satu nilai untuk semua giliran. Mengubahnya di
    # tengah membuat Ollama memuat ulang model dan membuang cache
    # prompt, sehingga awalan yang sengaja dibuat identik justru
    # diproses ulang dari nol - persis yang mau dihindari.
    context_length = max(4096, round_up(AI_CONTEXT_LENGTH, 2048))

    hasil: list[dict] = []
    warnings: list[str] = []
    metadata: dict = {}

    if len(batches) > 1:
        warnings.append(
            f"Isi halaman ditulis dalam {len(batches)} giliran karena "
            "teksnya tidak muat diminta sekaligus."
        )

    for nomor, bagian in enumerate(batches, start=1):
        system_prompt, user_prompt = build_template_content_prompt(
            analysis=analysis,
            insight=insight,
            spec=bagian,
            brand=brand,
        )

        needed_chars = answer_chars(bagian)

        # Plafonnya sisa context, bukan angka di config. Jawaban yang
        # menabrak batas context tidak berhenti dengan rapi; ia putus
        # di tengah JSON, dan itu berarti seluruh giliran gagal.
        tersisa = (
            context_length
            - estimate_tokens(system_prompt)
            - estimate_tokens(user_prompt)
            - CONTEXT_MARGIN
        )

        max_tokens = max(
            600,
            min(int(needed_chars / per_token) + 400, tersisa),
        )

        raw = ask_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=build_dynamic_schema(bagian),
            max_tokens=max_tokens,
            on_progress=batch_progress(on_progress, nomor, len(batches)),
            context_length=context_length,
        )

        isi, peringatan = fit_content_to_spec(raw, bagian, fallbacks or {})

        hasil.append(isi)
        warnings.extend(peringatan)
        metadata = raw.get("_metadata", metadata)

    content = merge_batch_content(hasil, spec)

    warnings.extend(balance_paired_roles(content))

    content["_metadata"] = metadata

    return content, warnings


def batch_progress(on_progress, nomor: int, jumlah: int):
    """
    Menyisipkan nomor giliran ke laporan kemajuan.

    Tanpa ini, pencacah token kembali ke nol tiap giliran dan
    prosesnya terbaca seperti mengulang dari awal, bukan maju.
    """
    if not on_progress:
        return None

    def report(info: dict) -> None:
        on_progress({**info, "batch": nomor, "batches": jumlah})

    return report


def check_language(plan: dict, region: str) -> str:
    """
    Memeriksa apakah AI benar-benar menulis dalam bahasa yang diminta.

    Model kecil sering ikut bahasa promptnya, bukan bahasa yang
    diperintahkan. Kalau itu terjadi, halamannya terbit dengan
    lang="th" tapi isinya bahasa Indonesia, dan tidak ada satu pun
    validasi lain yang bisa melihatnya. Lebih baik diberitahukan
    apa adanya daripada lolos diam-diam.
    """
    spec = get_region(region)

    if spec["word_mode"] != "unspaced":
        return ""

    sample = " ".join(
        [plan.get("title", ""), plan.get("h1", "")]
        + list(plan.get("intro", []))
        + [
            section.get("heading", "")
            for section in plan.get("sections", [])
        ]
    )

    share = thai_share(sample)

    if share >= 0.4:
        return ""

    return (
        f"AI hanya menulis {round(share * 100)}% aksara Thai padahal "
        f"zona {spec['label']} dipilih. Halaman kemungkinan tertulis "
        "dalam bahasa yang salah. Coba pakai model yang lebih besar, "
        "atau jalankan ulang."
    )


def ensure_keyword(
    text: str,
    keyword: str,
    limit: int,
) -> str:
    """
    Memastikan keyword utama benar-benar ada di title atau meta.

    Model kecil sering menulis parafrase yang enak dibaca tapi
    kehilangan keywordnya, misalnya menulis "Pelajari Python"
    untuk keyword "belajar python". Kalau itu terjadi, keyword
    dipasang di depan dan teksnya dipotong di batas kata supaya
    tetap muat.
    """
    clean = text.strip()

    if keyword.lower() in clean.lower():
        return clean

    # Setiap kata dikapitalisasi manual, bukan lewat str.title(),
    # supaya bentuk seperti "python's" tidak jadi "Python'S".
    prefix = " ".join(
        word[:1].upper() + word[1:]
        for word in keyword.split()
    )

    combined = f"{prefix}: {clean}" if clean else prefix

    if len(combined) <= limit:
        return combined

    trimmed = combined[:limit]
    cut = trimmed.rfind(" ")

    if cut > limit * 0.6:
        trimmed = trimmed[:cut]

    return trimmed.rstrip(" ,.;:-")


def ensure_brand(
    text: str,
    brand: str,
    limit: int,
) -> str:
    """
    Memastikan nama brand muncul di title atau H1.

    Model kecil sering hanya menuliskan keywordnya dan melupakan
    brandnya. Kalau itu terjadi, brand dipasang di depan mengikuti
    pola yang lazim: "BRAND: Judul Halaman".
    """
    clean = text.strip()
    clean_brand = brand.strip()

    if not clean_brand:
        return clean

    if clean_brand.lower() in clean.lower():
        return clean

    combined = f"{clean_brand}: {clean}" if clean else clean_brand

    if len(combined) <= limit:
        return combined

    # Brand diprioritaskan tetap utuh, judulnya yang dipotong.
    room = limit - len(clean_brand) - 2

    if room < 12:
        return clean_brand[:limit]

    trimmed = clean[:room]
    cut = trimmed.rfind(" ")

    if cut > room * 0.5:
        trimmed = trimmed[:cut]

    return f"{clean_brand}: {trimmed.rstrip(' ,.;:-')}"


def ensure_identity(
    text: str,
    keyword: str,
    brand: str,
    limit: int,
) -> str:
    """
    Memastikan title atau H1 memuat brand sekaligus keyword.

    Kalau dua pengaman dijalankan berurutan, hasilnya jadi
    "ABECE: Slot Gacor: Judul" dengan titik dua dobel. Di sini
    keduanya digabung jadi satu awalan: "ABECE Slot Gacor: Judul",
    yang juga pola lazim di halaman seperti ini.
    """
    clean = text.strip()
    clean_brand = brand.strip()

    missing: list[str] = []

    if clean_brand and clean_brand.lower() not in clean.lower():
        missing.append(clean_brand)

    if keyword.strip() and keyword.lower() not in clean.lower():
        missing.append(
            " ".join(
                word[:1].upper() + word[1:]
                for word in keyword.split()
            )
        )

    if not missing:
        return clean

    prefix = " ".join(missing)

    if not clean:
        return prefix[:limit]

    # Judul dari model sering sudah memakai titik dua sendiri.
    # Menambahkan satu lagi menghasilkan "ABECE: Judul: Anak Judul"
    # yang terbaca berantakan di hasil pencarian, jadi pemisahnya
    # diganti tanda hubung.
    separator = " - " if ":" in clean else ": "

    combined = f"{prefix}{separator}{clean}"

    if len(combined) <= limit:
        return combined

    # Awalan dipertahankan utuh, judulnya yang dipotong, karena
    # brand dan keyword yang menentukan halaman ini dikenali.
    room = limit - len(prefix) - len(separator)

    if room < 12:
        return prefix[:limit]

    trimmed = clean[:room]
    cut = trimmed.rfind(" ")

    if cut > room * 0.5:
        trimmed = trimmed[:cut]

    return f"{prefix}{separator}{trimmed.rstrip(' ,.;:-')}"


def normalize_plan(
    plan: dict,
    keyword: str,
    brand_name: str = "",
    region: str = "id",
) -> dict:
    """
    Membersihkan hasil AI supaya aman dirender jadi HTML.

    Model kadang mengembalikan field kosong atau tipe section yang
    tidak cocok dengan isinya. Di sini semuanya dirapikan sebelum
    masuk ke generator.
    """
    def clean_text(value, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()

        return text[:limit]

    title = clean_text(plan.get("title"), 70) or (
        f"{keyword.title()} — Panduan Lengkap"
    )

    title = ensure_identity(title, keyword, brand_name, 62)

    h1 = clean_text(plan.get("h1"), 90) or title
    h1 = ensure_identity(h1, keyword, brand_name, 90)

    meta = ensure_keyword(
        clean_text(plan.get("meta_description"), 165),
        keyword,
        160,
    )

    # Slug URL boleh memuat aksara Thai. Membuangnya membuat setiap
    # halaman zona Thailand memakai URL yang sama, sehingga
    # canonical, rel=amphtml, dan sitemap semuanya saling menimpa.
    slug = slug_for_url(
        clean_text(plan.get("slug"), 80) or keyword,
        region,
    )

    sections = []

    for raw in plan.get("sections", []):
        if not isinstance(raw, dict):
            continue

        heading = clean_text(raw.get("heading"), 110)

        if not heading:
            continue

        paragraphs = [
            clean_text(item, 1000)
            for item in raw.get("paragraphs", [])
            if clean_text(item, 1000)
        ]

        items = [
            clean_text(item, 260)
            for item in raw.get("items", [])
            if clean_text(item, 260)
        ]

        section_type = str(raw.get("type", "paragraph")).lower()

        if section_type not in {
            "paragraph",
            "list",
            "table",
            "steps",
            "cta",
        }:
            section_type = "paragraph"

        # Tipe diturunkan kalau isinya tidak mendukung.
        if section_type in {"list", "steps", "table"} and not items:
            section_type = "paragraph"

        if not paragraphs and not items:
            continue

        sections.append(
            {
                "heading": heading,
                "type": section_type,
                "paragraphs": paragraphs,
                "items": items,
            }
        )

    faq = []

    for raw in plan.get("faq", []):
        if not isinstance(raw, dict):
            continue

        question = clean_text(raw.get("question"), 160)
        answer = clean_text(raw.get("answer"), 700)

        if question and answer:
            faq.append(
                {
                    "question": question,
                    "answer": answer,
                }
            )

    keywords = [
        clean_text(item, 60)
        for item in plan.get("keywords", [])
        if clean_text(item, 60)
    ]

    if keyword not in keywords:
        keywords.insert(0, keyword)

    intro_raw = str(plan.get("intro", "")).strip()

    intro_paragraphs = [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n{2,}|\r\n\r\n", intro_raw)
        if re.sub(r"\s+", " ", part).strip()
    ]

    if not intro_paragraphs and intro_raw:
        intro_paragraphs = [re.sub(r"\s+", " ", intro_raw).strip()]

    return {
        "title": title,
        "meta_description": meta,
        "slug": slug,
        "h1": h1,
        "intro": intro_paragraphs,
        "sections": sections,
        "faq": faq,
        "keywords": keywords[:12],
        "_metadata": plan.get("_metadata", {}),
    }


def count_plan_words(plan: dict) -> int:
    """
    Menghitung jumlah kata rencana konten.
    """
    parts: list[str] = list(plan.get("intro", []))

    for section in plan.get("sections", []):
        parts.append(section["heading"])
        parts.extend(section["paragraphs"])
        parts.extend(section["items"])

    for item in plan.get("faq", []):
        parts.append(item["question"])
        parts.append(item["answer"])

    # Dihitung sadar aksara: memecah spasi membuat halaman Thai
    # dilaporkan sekitar seperlima panjang aslinya, dan angka itu
    # yang dipakai membandingkan dengan target kompetitor.
    return sum(count_words(part) for part in parts)
