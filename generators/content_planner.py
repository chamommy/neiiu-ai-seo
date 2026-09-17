"""
Lapisan AI pipeline NEIIU.

Dua tugas:
1. Menjelaskan kenapa halaman rank 1–10 bisa naik.
2. Menyusun isi landing page baru berdasarkan penjelasan itu.

Keduanya memakai structured output supaya hasilnya langsung bisa
dirender jadi HTML tanpa parsing teks bebas.
"""

import hashlib
import re
import time
from functools import lru_cache
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from ai.language_rules import style_examples_fit
from ai.manager import AIManager
from ai.neiiu_prompts import (
    build_serp_insight_prompt,
    build_template_content_prompt,
    build_meta_only_prompt,
    build_title_only_prompt,
    load_style_examples,
    pick_style_examples,
)
from generators.content_batches import (
    DISTINCT_ROLES,
    SINGLE_ROLES,
    answer_chars,
    merge_batch_content,
    plan_batches,
)
from generators.brand_swap import (
    normalize,
    restore_brand,
    restore_brand_content,
)
from generators.claim_guard import scrub_content
from generators.leak_guard import instruction_index, scrub_leaks
from generators.plagiarism_guard import scrub_copied, source_index
from generators.page_numbers import (
    build_number_set,
    enforce_content_numbers,
    strip_figures,
)
from generators.page_text import PAGE_TEXT
from generators.template_slots import foreign_copy
from generators.template_filler import (
    LIST_ROLES,
    balance_paired_roles,
    build_dynamic_schema,
    clean_line,
    fit_content_to_spec,
    sample_text,
    scale_spec,
    spare_headings,
)
from ai.schemas import (
    SERP_INSIGHT_SCHEMA,
)
from config import (
    AI_CONTEXT_LENGTH,
    AI_MAX_TOKENS_INSIGHT,
    AI_MODEL,
    AI_MODEL_HEAD,
    AI_MODEL_INSIGHT,
    AI_PROVIDER,
)
from utils.region import format_date, get_region, iso_date
from utils.spelling import (
    fix_content_register,
    fix_content_stiffness,
    fix_content_terms,
    fix_terms,
)
from utils.text import (
    CONTENT_STOPWORDS,
    THAI_RANGE,
    content_shingles,
    content_tokens,
    count_words,
    display_width,
    drop_dangling,
    finish_clause,
    drop_thai_tail,
    estimate_tokens,
    menggantung,
    thai_share,
    trim_to_width,
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

# Berapa kali sisa yang tidak dijawab diminta lagi sebelum menyerah.
#
# Model kecil rutin menutup daftar lebih awal dari jumlah yang
# diminta, dan minItems milik JSON Schema tidak selalu ditegakkan
# llama.cpp. Dua percobaan sudah menutup hampir semua kekurangan yang
# terukur di sini; lebih dari itu hanya menambah waktu untuk model
# yang memang tidak sanggup menyelesaikan daftarnya.
SHORT_ANSWER_RETRIES = 2

# Sependek apa sebuah jawaban baru dihitung sebagai lubang.
#
# Dihitung terhadap lantai slotnya, bukan terhadap plafon. Setengah
# lantai berarti slot berjatah 176 karakter - lantai 120 - baru
# diminta ulang kalau jawabannya di bawah 60 karakter. Yang di antara
# 60 dan 120 dibiarkan: pendek, tapi masih kalimat utuh, dan satu
# giliran ulang lebih mahal daripada selisihnya.
SHORT_TEXT_SHARE = 0.5


# Kegagalan yang PENYEBABNYA sambungan putus, bukan jawaban salah.
#
# Runner model Ollama sesekali mati di tengah permintaan panjang dan
# menutup soketnya. Yang sampai ke sini bentuknya RuntimeError berisi
# pesan jaringan, dan kalau dibiarkan lewat, satu permintaan gagal
# membatalkan seluruh run - terukur 12 Agustus: giliran 5 dari 5 mati
# di menit ke-21 dan dua puluh menit crawl serta penulisan sebelumnya
# ikut terbuang.
#
# Yang dicocokkan cuma pesan transportasi. Jawaban yang bukan JSON,
# schema yang tidak terpenuhi, atau prompt kosong TIDAK ikut diulang:
# mengirim permintaan yang sama untuk kesalahan yang sama cuma
# menghabiskan waktu.
TRANSPORT_ERROR = re.compile(
    r"forcibly closed|connection reset|connection aborted|"
    r"broken pipe|wsarecv|wsasend|eof occurred|"
    r"remote end closed|connection refused|"
    r"error was encountered while running the model",
    re.IGNORECASE,
)

# Berapa kali permintaan yang putus sambungannya dicoba lagi.
ASK_RETRIES = 2

# Jeda sebelum mencoba lagi. Runner yang barusan mati butuh waktu
# dimuat ulang; menembaknya seketika cuma menghasilkan kegagalan
# kedua yang sama.
ASK_RETRY_DELAY = 5.0


def round_up(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step


def ask_structured(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    max_tokens: int,
    on_progress=None,
    context_length: int = 0,
    model: str = "",
) -> dict:
    """
    Mengirim prompt ke AI dan mengembalikan objek JSON hasilnya.

    context_length boleh dipatok dari luar. Itu penting untuk
    permintaan yang dikirim beberapa kali berturut-turut: mengubah
    num_ctx membuat Ollama memuat ulang model dan membuang cache
    prompt, sehingga awalan yang sengaja dibuat identik justru
    diproses ulang dari nol setiap giliran.

    model dikosongkan berarti memakai AI_MODEL. Yang memakai jalur
    ini cuma tahap insight, dan alasannya ada di config.py.
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
        model=model or AI_MODEL,
        max_tokens=max_tokens,
        context_length=context_length,
    )

    result = None

    for percobaan in range(ASK_RETRIES + 1):
        try:
            result = ai.ask(
                prompt=user_prompt,
                system_prompt=system_prompt,
                response_schema=schema,
                on_progress=on_progress,
            )
            break

        except (RuntimeError, ConnectionError, OSError) as error:
            putus = TRANSPORT_ERROR.search(str(error))

            if not putus or percobaan >= ASK_RETRIES:
                raise

            catat(
                on_progress,
                f"sambungan ke model putus ({putus.group(0)}), "
                f"dicoba lagi {percobaan + 1}/{ASK_RETRIES} "
                f"setelah {int(ASK_RETRY_DELAY)} detik.",
            )

            time.sleep(ASK_RETRY_DELAY)

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
            catatan = (
                f" (model {AI_MODEL_INSIGHT})"
                if AI_MODEL_INSIGHT != AI_MODEL
                else ""
            )

            print(f"  Meminta analisis ranking ke AI{catatan}...")

        insight = ask_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=SERP_INSIGHT_SCHEMA,
            max_tokens=AI_MAX_TOKENS_INSIGHT,
            on_progress=on_progress,
            model=AI_MODEL_INSIGHT,
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

        # Sudut pembahasan diambil dari heading halamannya sendiri.
        # Ini fallback tanpa AI, jadi tidak ada yang menyimpulkan
        # apa pun di sini - yang bisa dilakukan cuma menunjukkan
        # kerangka aslinya dan membiarkannya bicara sendiri.
        outline = [
            item.get("heading", "")
            for item in (page.get("digest") or {}).get("outline", [])
            if item.get("heading")
        ]

        angle = (
            "Kerangka pembahasannya: " + "; ".join(outline[:5])
            if outline
            else "Belum dianalisis AI."
        )

        ranking_analysis.append(
            {
                "position": page["position"],
                "domain": page["domain"],
                "why_ranking": (
                    f"Skor SEO on-page {page['seo_score']}/100 "
                    f"dengan {page['headings']['h2_count']} H2 dan "
                    f"{page['links']['internal_count']} internal link."
                ),
                "angle": angle[:300],
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
        "intent_evidence": [
            f"{item['heading']} — dipakai {item['count']} domain"
            for item in blueprint.get("common_headings", [])[:4]
        ],
        # Tanpa AI, topik wajib diambil dari heading yang paling
        # sering berulang di halaman pertama. Itu bukan pemahaman,
        # tapi pengulangan lintas domain memang bukti yang sah:
        # kalau tujuh dari sepuluh halaman membahasnya, halaman baru
        # yang melewatinya berangkat dengan kekurangan.
        "must_cover": [
            {
                "topic": item["heading"],
                "reason": (
                    f"Dipakai {item['count']} domain di halaman pertama."
                ),
            }
            for item in blueprint.get("common_headings", [])[:8]
            if item.get("count", 0) >= 2
        ],
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


def generate_template_content(
    analysis: dict,
    insight: dict,
    spec: dict,
    brand: dict,
    fallbacks: dict | None = None,
    riwayat: dict | None = None,
    on_progress=None,
    old_brand: str = "",
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

    # Angka halaman dipilih SEBELUM giliran pertama berangkat, karena
    # daftarnya ikut masuk ke prompt tiap giliran. Benihnya tetap,
    # jadi seluruh giliran melihat daftar yang sama persis dan cache
    # prompt Ollama tidak batal di tengah jalan.
    angka_halaman = build_number_set(
        analysis["keyword"],
        brand.get("site_name", "").strip(),
        brand.get("variation", ""),
    )

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

    # Apa yang sudah tertulis di giliran sebelumnya, supaya giliran
    # berikutnya bisa menyambungnya. Yang dipakai sekarang cuma
    # pertanyaan FAQ, karena jawabannya hampir selalu jatuh di
    # giliran lain dan tanpa ini ditulis tanpa melihat pertanyaannya.
    terkumpul: dict[str, list[str]] = {}

    # Bentuk baku dari apa yang sudah tertulis, dipakai menolak
    # kalimat kembar lintas giliran. Disimpan terpisah dari
    # "terkumpul" karena yang itu dipakai prompt dan urutannya
    # penting, sedangkan yang ini cuma perlu cepat dicari.
    #
    # DIISI DULU dengan teks halaman-halaman sebelumnya. Ini yang
    # membuat halaman kedua benar-benar berbeda dari yang pertama,
    # bukan sekadar diminta berbeda: penolak kembar yang sudah ada
    # tinggal dipakai, dan tiap kalimat yang mengulang halaman lama
    # jadi lubang yang otomatis diminta ulang oleh mesin yang sama
    # yang menambal lubang di dalam satu run.
    # Contoh gaya yang DILIHAT model di giliran ini, disusun ulang
    # dengan benih yang sama supaya isinya persis sama dengan yang ada
    # di promptnya. Dipakai menolak jawaban yang menyalinnya.
    # Zona yang bahasanya bukan bahasa berkas contoh tidak menerima
    # contoh sama sekali, jadi di sini pun daftarnya kosong.
    #
    # Kalau dibiarkan terisi, penyaring akan mengadu jawaban Thai
    # dengan contoh Indonesia yang tidak pernah dilihat model. Skornya
    # memang selalu rendah - dua bahasa tidak berbagi kata - jadi
    # tidak ada yang tertolak salah; yang hilang cuma pekerjaan
    # membandingkan yang tidak menjawab apa pun. Yang penting kedua
    # sisi tetap membaca aturan yang sama, supaya tidak ada lagi
    # tempat yang harus diingat sendiri saat aturannya berubah.
    contoh_gaya = {
        # Argumennya harus PERSIS sama dengan yang dipakai
        # build_template_content_prompt - keyword mentah, nama brand
        # yang sudah di-strip, penanda run apa adanya - karena
        # ketiganya masuk ke benih pemilihnya. Beda satu spasi saja,
        # yang diperiksa di sini bukan contoh yang dilihat model.
        peran: (
            pick_style_examples(
                analysis["keyword"],
                brand.get("site_name", "").strip(),
                slot=peran,
                variation=brand.get("variation", ""),
            )
            if style_examples_fit(
                brand.get("region", "id"),
                brand.get("niche", "gambling"),
            )
            else []
        )
        for peran in ("title", "meta_description")
    }

    terpakai: dict[str, set[str]] = {
        peran: {
            normalize(str(teks))
            for teks in daftar
            if str(teks).strip()
        }
        for peran, daftar in (riwayat or {}).items()
    }

    def catat_terpakai(isi: dict) -> None:
        for peran, teks in isi.items():
            if peran.startswith("_") or not isinstance(teks, list):
                continue

            terpakai.setdefault(peran, set()).update(
                normalize(str(x)) for x in teks if str(x).strip()
            )

    def minta(
        bagian: dict,
        nomor: int,
        ulang: bool = False,
        sudah: dict | None = None,
        catatan: str = "",
    ) -> dict:
        """
        Satu permintaan ke model untuk satu potongan kebutuhan.

        "sudah" boleh ditimpa dari luar, dan itu yang dipakai giliran
        ulang. terkumpul baru diisi SESUDAH satu giliran tuntas, jadi
        permintaan susulan yang memakainya apa adanya berangkat tanpa
        tahu apa yang barusan ditulisnya sendiri.

        "catatan" ditempelkan di UJUNG prompt, sesudah seluruh aturan.
        Isinya alasan penolakan yang benar-benar berlaku untuk jawaban
        sebelumnya - lihat title_reasons. Kosong berarti permintaan ini
        berangkat dengan prompt yang sama persis seperti semula, dan
        itu yang benar: tidak ada perintah perbaikan untuk hal yang
        tidak salah.
        """
        # Nomor giliran nol dipakai penambalan sesudah penyapuan,
        # yang bukan bagian dari pembagian giliran. Menuliskannya
        # sebagai "Giliran 0" membaca seperti giliran yang hilang.
        label = f"Giliran {nomor}" if nomor else "Penambalan"

        gema = terkumpul if sudah is None else sudah

        # Giliran yang isinya HANYA judul memakai promptnya sendiri.
        #
        # plan_batches sudah menaruh title di giliran terpisah, tapi
        # giliran itu tetap berangkat dengan prompt seluruh halaman:
        # 15.423 token untuk satu judul 70 karakter, sebelas koma enam
        # kali prompt judul-saja untuk permintaan yang isinya sama.
        # Akibatnya terukur di job 93 dan 94 - dua-duanya gagal
        # menghasilkan judul sama sekali, lalu jatuh ke cadangan.
        #
        # Yang dipakai build_title_only_prompt, bukan prompt lengkap
        # yang ditambahi aturan judul. Sudut, kosakata sudut, dan
        # aturan judulnya diambil dari mesin yang sama dengan jalur
        # cepat, jadi tidak ada mesin sudut kedua yang bisa bergeser
        # sendiri - lihat keterangannya di build_title_only_prompt.
        #
        # SELURUH penilai sesudahnya tidak berubah: judulnya tetap
        # lewat title_penalty, tetap diminta ulang kalau ditolak, tetap
        # ditegakkan bentuknya, dan tetap punya cadangan kalau semua
        # percobaan habis.
        judul_saja = set(bagian) == {"title"}

        # Giliran yang isinya HANYA deskripsi punya jalur ramping
        # sendiri, dengan alasan yang sama persis seperti judul di
        # atas - dan dengan angka yang lebih tajam lagi.
        #
        # Terukur di run 30 Agustus 2026, pada permintaan yang cuma
        # minta satu judul dan satu deskripsi:
        #
        #     giliran title (jalur ramping)   :  22 detik
        #     giliran deskripsi (jalur penuh) : 472 detik
        #
        #     prompt giliran deskripsi : 11.811 token
        #     yang diminta             : satu kalimat 140-180 karakter
        #
        # Dua puluh satu kali lebih lama untuk teks yang panjangnya
        # dua kali lipat. Sebabnya cuma karena gerbang di atas
        # menyebut "title" dan tidak menyebut yang ini, jadi deskripsi
        # selalu berangkat membawa aturan paragraf, heading, FAQ,
        # daftar, CTA, bank kata SERP, dan pertanyaan kompetitor -
        # untuk giliran yang tidak menulis satu pun dari itu.
        #
        # Yang ikut ke jalur ramping tetap lengkap untuk deskripsi:
        # judul yang baru ditulis, larangan mengulanginya, kata khas
        # judul yang tidak boleh dipakai lagi, dan deskripsi yang
        # sudah terbit di halaman sebelumnya. SELURUH penilai
        # sesudahnya tidak berubah.
        meta_saja = set(bagian) == {"meta_description"}

        if judul_saja:
            system_prompt, user_prompt = build_title_only_prompt(
                analysis=analysis,
                brand=brand,
                spec=bagian,
                riwayat=riwayat,
            )
        elif meta_saja:
            system_prompt, user_prompt = build_meta_only_prompt(
                analysis=analysis,
                brand=brand,
                spec=bagian,
                sudah=gema,
                riwayat=riwayat,
            )
        else:
            system_prompt, user_prompt = build_template_content_prompt(
                analysis=analysis,
                insight=insight,
                spec=bagian,
                brand=brand,
                sudah=gema,
                riwayat=riwayat,
                angka=angka_halaman,
            )

        # Alasan penolakan berdiri PALING BAWAH, sesudah seluruh
        # aturan. Yang dibaca terakhir yang paling berpengaruh pada
        # model kecil - alasan yang sama dipakai forbidden_claims_block
        # dan repair_note.
        if catatan:
            user_prompt = f"{user_prompt}{catatan}"

        needed_chars = answer_chars(bagian)

        # Plafonnya sisa context, bukan angka di config. Jawaban yang
        # menabrak batas context tidak berhenti dengan rapi; ia putus
        # di tengah JSON, dan itu berarti seluruh giliran gagal.
        def sisa(sistem: str, pengguna: str) -> int:
            return (
                context_length
                - estimate_tokens(sistem)
                - estimate_tokens(pengguna)
                - CONTEXT_MARGIN
            )

        tersisa = sisa(system_prompt, user_prompt)
        perlu_awal = int(needed_chars / per_token) + 400

        # Kalau tidak muat, daftar gema DIBUANG - bukan cuma dikeluhkan.
        #
        # Dari semua bagian prompt, daftar "teks yang sudah terpakai"
        # yang paling murah dilepas: ia TIDAK menegakkan apa pun.
        # Penolak kalimat kembar dikerjakan Python lewat "terpakai" di
        # bawah, yang membandingkan teks utuh dan berjalan atas setiap
        # jawaban. Daftar di prompt cuma memberi tahu model lebih awal
        # supaya tidak membuang giliran.
        #
        # Ditukar dengan yang jauh lebih mahal kalau dibiarkan: prompt
        # yang melewati context membuat jawabannya putus di tengah JSON,
        # dan seluruh giliran itu terbuang. Terukur pada job 61 dan 62,
        # template LEGO: giliran ketiga berangkat dengan "sisa context
        # -721 token".
        # Prompt judul tidak punya daftar gema untuk dilepas, dan tidak
        # pernah membutuhkannya: seribuan token menyisakan ruang jawaban
        # berlipat-lipat dari yang diminta.
        if tersisa < perlu_awal and gema and not judul_saja:
            tanpa_gema, tanpa_gema_pengguna = build_template_content_prompt(
                analysis=analysis,
                insight=insight,
                spec=bagian,
                brand=brand,
                sudah=None,
                riwayat=riwayat,
                angka=angka_halaman,
            )

            lega = sisa(tanpa_gema, tanpa_gema_pengguna)

            if lega > tersisa:
                catat(
                    on_progress,
                    f"{label}: daftar teks terpakai dilepas "
                    f"untuk memberi ruang ({tersisa} -> {lega} token). "
                    "Penolak kalimat kembar tetap berjalan di Python.",
                )

                system_prompt = tanpa_gema
                user_prompt = tanpa_gema_pengguna
                tersisa = lega

        # Kekurangan ruang dikatakan, bukan didiamkan.
        #
        # Kalau sisa context lebih kecil daripada panjang jawaban yang
        # diminta, jawabannya PASTI terpotong - bukan mungkin. Dulu
        # keadaan ini lewat tanpa jejak dan yang terlihat pengguna cuma
        # "Jawaban AI bukan JSON yang valid" di menit ke-21 (job #52).
        # Sekarang potongannya masih diselamatkan di ollama_ai dan
        # sisanya diminta ulang, tapi sebabnya tetap perlu tercatat
        # supaya kelihatan bahwa templatenya yang kebesaran untuk
        # context yang dipasang.
        # Dihitung sekali di atas, dipakai lagi di sini: yang di atas
        # memutuskan apakah gema perlu dilepas, yang di sini
        # memutuskan apakah kekurangannya masih perlu dikatakan
        # sesudah gemanya dilepas.
        perlu = perlu_awal

        if tersisa < perlu:
            catat(
                on_progress,
                f"{label}: sisa context {tersisa} token, "
                f"sedangkan jawabannya butuh sekitar {perlu}. "
                "Jawaban akan terpotong dan sisanya diminta ulang. "
                "Naikkan AI_CONTEXT_LENGTH atau kurangi jumlah "
                "halaman yang di-crawl.",
            )

        return ask_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=build_dynamic_schema(bagian),
            max_tokens=max(
                600,
                min(int(needed_chars / per_token) + 400, tersisa),
            ),
            on_progress=batch_progress(
                on_progress,
                nomor,
                len(batches),
                ulang,
            ),
            context_length=context_length,
            model=head_model(bagian),
        )

    for nomor, bagian in enumerate(batches, start=1):
        raw = minta(bagian, nomor)

        # Ejaan nama situs dibetulkan di sini - SEBELUM satu pun
        # penilai melihat jawabannya.
        #
        # Nama brand adalah token atomik: pengguna mengetik SIAM123,
        # jadi setiap ukuran yang menyebut-nyebut nama situs harus
        # melihat SIAM123, bukan SIAM12S. Dulu pemulihannya dijalankan
        # di ujung, sesudah semua penilaian selesai, dan itu membuka
        # lubang yang tidak kelihatan dari mana pun kecuali dari
        # halaman yang terbit:
        #
        #   dinilai : "WAYANGPLAY menghadirkan ... WAYANGPLA
        #              menyediakan ..."   -> brand_repeat 0,0, LOLOS
        #   terbit  : "WAYANGPLAY menghadirkan ... WAYANGPLAY
        #              menyediakan ..."   -> nama situs dua kali
        #
        # Deskripsi itu lolos justru KARENA salah ketiknya: penilai
        # menghitung dua kata yang berbeda, lalu pemulih di ujung
        # menyamakan keduanya ketika tidak ada lagi yang memeriksa.
        #
        # Dijalankan di sini, yang dinilai sama dengan yang terbit.
        # Pemulih di ujung tetap berdiri sebagai jaring kedua untuk
        # teks yang tidak lewat sini - dijalankan dua kali tidak
        # mengubah apa pun, karena ejaan yang sudah benar dilewatinya.
        raw, brand_awal = restore_brand_content(
            raw,
            brand.get("site_name", ""),
            analysis["keyword"],
        )

        if brand_awal:
            warnings.append(
                f"{brand_awal} sebutan nama situs salah ketik di giliran "
                f"{nomor} dan sudah dikembalikan ke ejaan yang kamu "
                "masukkan."
            )

        isi, peringatan = fit_content_to_spec(
            raw,
            bagian,
            fallbacks or {},
            seen=terpakai,
        )
        metadata = raw.get("_metadata", metadata)

        # Sisa yang tidak dijawab diminta lagi, bukan dibiarkan.
        #
        # Daftar panjang rutin dijawab lebih pendek dari yang diminta:
        # model berhenti di tengah dan minItems milik JSON Schema
        # tidak selalu ditegakkan llama.cpp. Selama sisanya dibiarkan,
        # slot yang tidak kebagian terbit dengan teks pemilik template
        # - terukur di halaman jadi, 81 label diminta, 31 dijawab, dan
        # kartu "1. Deposit QRIS 1 Detik" milik brand lama tetap
        # berdiri di halaman yang seluruh isinya sudah berganti.
        for putaran in range(SHORT_ANSWER_RETRIES):
            kurang = short_roles(bagian, isi)

            if not kurang:
                break

            kembar = duplicate_slots(bagian, isi)

            catat(
                on_progress,
                f"Giliran {nomor}: "
                + ", ".join(
                    f"{peran} kurang {len(lubang)}"
                    + (
                        f" ({len(kembar[peran])} kembar)"
                        if kembar.get(peran)
                        else ""
                    )
                    for peran, lubang in kurang.items()
                )
                + ", diminta lagi.",
            )

            sisa_spec = gap_spec(bagian, kurang)

            if not sisa_spec:
                break

            # Apa yang sudah tertulis di giliran INI ikut dibawa,
            # bukan cuma yang dari giliran-giliran sebelumnya.
            #
            # Ini yang membuat permintaan susulan berguna. Tanpa itu
            # model diminta "dua pertanyaan lagi" tanpa diberi tahu
            # lima yang barusan ditulisnya, jadi yang keluar variasi
            # dari lima itu - lalu dibuang penyaring kembar, dan
            # slotnya tetap kosong sesudah dua kali diminta.
            sejauh_ini = {
                peran: list(terkumpul.get(peran) or [])
                + [
                    str(teks).strip()
                    for teks in (isi.get(peran) or [])
                    if str(teks).strip()
                ]
                for peran in bagian
                if isinstance(isi.get(peran), list)
            }

            tambahan = minta(
                sisa_spec,
                nomor,
                ulang=True,
                sudah={**terkumpul, **sejauh_ini},
            )
            metadata = tambahan.get("_metadata", metadata)

            lanjutan, _ = fit_content_to_spec(
                tambahan,
                sisa_spec,
                fallbacks or {},
                seen={
                    **terpakai,
                    **{
                        peran: set(terpakai.get(peran) or set())
                        | {
                            normalize(str(x))
                            for x in (isi.get(peran) or [])
                            if str(x).strip()
                        }
                        for peran in sisa_spec
                    },
                },
            )

            isi = extend_content(isi, lanjutan, bagian, sisa_spec)

        # Deskripsi yang cuma menuliskan ulang judulnya diminta lagi.
        #
        # Ini keluhan pengguna, dan aturan di prompt saja tidak cukup
        # menutupnya - terukur, deskripsi tetap terbit dibuka dengan
        # kalimat judul yang sama persis, cuma berhuruf kecil. Dua
        # teks itu berdiri berdampingan di hasil pencarian, jadi yang
        # terbuang bukan sekadar satu kalimat melainkan seluruh baris
        # yang seharusnya memberi alasan mengklik.
        #
        # Diminta sekali lagi, bukan dipaksa berkali-kali: dengan suhu
        # di atas nol, permintaan yang sama menghasilkan kalimat yang
        # berbeda, dan yang lebih baik di antara keduanya yang dipakai.
        # Judul yang mengulang judul halaman sebelumnya diminta lagi.
        #
        # Diadu, bukan diterima apa adanya - sama seperti deskripsi di
        # bawah. Dengan suhu di atas nol, permintaan yang sama
        # menghasilkan judul yang berbeda tiap kali, jadi percobaan
        # tambahan tidak pernah membuat hasilnya lebih buruk.
        judul_lama = [
            str(x) for x in (riwayat or {}).get("title", []) if str(x).strip()
        ]

        # Judul yang sudah ditolak di giliran ini ikut jadi pembanding
        # kandidat berikutnya, bukan cuma judul halaman lain.
        #
        # Tanpa itu, permintaan ulang rutin menjawab judul yang membuka
        # persis sama dengan yang barusan ditolak - model tidak diberi
        # tahu apa yang sudah dicobanya, jadi ia mendarat di tempat
        # yang sama dari brief yang sama.
        judul_ditolak: list[str] = []

        def judul_buruk(teks) -> float:
            """
            Alasan judul ditolak, semuanya dinyatakan dalam satu angka.

            Isinya pindah ke title_penalty supaya setiap pemanggil memakai
            daftar alasan yang sama persis - lihat keterangan di sana.
            Yang tinggal di sini cuma bahan yang khas giliran ini:
            judul halaman lain, judul yang sudah ditolak di giliran
            ini, dan contoh gaya yang benar-benar dilihat model.
            """
            return title_penalty(
                teks,
                analysis["keyword"],
                brand.get("site_name", ""),
                riwayat=judul_lama + judul_ditolak,
                contoh=contoh_gaya.get("title") or [],
            )

        if "title" in bagian and str(isi.get("title") or ""):
            terbaik = str(isi["title"])
            nilai_terbaik = judul_buruk(terbaik)


            for putaran in range(TITLE_REPEAT_RETRIES):
                # Ambangnya HEAD_GOOD_ENOUGH, bukan 1.0. Judul yang
                # cuma "tidak melanggar" tetap ditantang sekali, karena
                # itulah yang membuat pemilihan kandidat benar-benar
                # terjadi - lihat keterangan di HEAD_GOOD_ENOUGH.
                if nilai_terbaik < HEAD_GOOD_ENOUGH:
                    break

                # Alasan penolakan yang BENAR-BENAR berlaku, bukan satu
                # kalimat tetap.
                #
                # Terukur end-to-end 17 Agustus 2026, job 95: judul
                # ditolak 3 dari 3 percobaan karena clause_pile 1,50 dan
                # incomplete_tail 1,00 - dan kalimat tetap yang dikirim
                # ke model tidak menyebut satu pun dari keduanya. Model
                # diminta ulang tiga kali tanpa pernah tahu apa yang
                # salah, lalu yang terbit "yang paling sedikit
                # bermasalah".
                #
                # Penilainya tidak berubah sama sekali. Yang berubah
                # cuma apa yang DIKATAKAN tentang hasil penilaian itu.
                alasan = title_reasons(
                    terbaik,
                    analysis["keyword"],
                    brand.get("site_name", ""),
                    riwayat=judul_lama + judul_ditolak,
                )

                # Barisnya dipendekkan untuk log; yang dikirim ke model
                # tetap utuh.
                ringkas = "; ".join(
                    baris.split("\n")[0].removeprefix("- title: ").rstrip(".")
                    for baris in alasan
                ) or "nilainya masih di atas ambang"

                catat(
                    on_progress,
                    f"Giliran {nomor}: {ringkas}; diminta lagi "
                    f"({putaran + 1}/{TITLE_REPEAT_RETRIES}).",
                )

                # Yang sudah dicoba dicatat SEBELUM permintaan
                # berikutnya berangkat, jadi kandidat baru diadu dengan
                # kandidat lama - bukan cuma dengan halaman lain.
                if terbaik not in judul_ditolak:
                    judul_ditolak.append(terbaik)

                ulangan = minta(
                    {"title": bagian["title"]},
                    nomor,
                    ulang=True,
                    catatan=title_repair_note(alasan, judul_ditolak),
                )

                baru, _ = fit_content_to_spec(
                    ulangan,
                    {"title": bagian["title"]},
                    fallbacks or {},
                )

                calon = str(baru.get("title") or "")

                if not calon:
                    continue

                # Kandidat dinilai TANPA dirinya sendiri di daftar
                # pembanding. Ia baru saja ditulis, jadi ia belum
                # pernah ditolak.
                nilai = judul_buruk(calon)

                # Riwayat yang dicatat di sini sudah memuat kandidat
                # yang barusan ditolak - itu memang bahan yang dipakai
                # produksi menilai baris di atas, dan itu yang harus
                # terbaca di rekamannya.
    
                if nilai < nilai_terbaik:
                    terbaik = calon
                    nilai_terbaik = nilai

            isi["title"] = terbaik

            if nilai_terbaik >= 1.0:
                warnings.append(
                    "Judul masih mirip judul halaman sebelumnya, mirip "
                    "contoh gayanya, masih menumpuk kata penyangat, "
                    "atau mengulang keywordnya walau sudah diminta "
                    f"{TITLE_REPEAT_RETRIES + 1} kali; yang dipakai "
                    "yang paling sedikit bermasalah, dan tumpukan yang "
                    "tersisa dibuang."
                )

        # Judul giliran INI didahulukan atas judul giliran sebelumnya.
        #
        # Ini lubang yang membuat seluruh penolak "deskripsi mengulang
        # judul" tidak pernah bekerja di tempat yang paling
        # membutuhkannya. terkumpul baru diisi SESUDAH satu giliran
        # tuntas, sedangkan title dan meta_description dua-duanya
        # peran bertekstunggal - plan_batches menaruh keduanya di
        # giliran PERTAMA yang sama. Jadi waktu deskripsi giliran itu
        # diperiksa, terkumpul masih kosong, judul pembandingnya
        # string kosong, dan echo_score atas string kosong selalu nol.
        #
        # Akibatnya terbaca di halaman jadi: deskripsi yang membuka
        # dengan kalimat judulnya sendiri lolos tanpa satu pun
        # permintaan ulang, padahal mesin yang memintanya ulang sudah
        # terpasang sejak lama.
        judul = str(isi.get("title") or "").strip() or (
            terkumpul.get("title") or [""]
        )[0]

        # Yang dibandingkan bukan cuma judul halaman ini, tapi juga
        # deskripsi halaman-halaman sebelumnya. Dua alasan yang
        # berbeda, satu mesin yang sama: deskripsi yang mengulang
        # judulnya sendiri membuang baris yang seharusnya memberi
        # alasan mengklik, sedangkan deskripsi yang mengulang halaman
        # lain membuat dua halaman berebut kata kunci yang sama.
        desc_lama = [
            str(x)
            for x in (riwayat or {}).get("meta_description", [])
            if str(x).strip()
        ]

        # Deskripsi yang sudah ditolak di giliran ini ikut jadi
        # pembanding, dengan alasan yang sama seperti judul_ditolak.
        desc_ditolak: list[str] = []

        def gema_desc(teks) -> float:
            # Isinya pindah ke description_penalty supaya setiap pemanggil
            # memakai daftar alasan yang sama persis. Yang tinggal di
            # sini bahan yang khas giliran ini.
            return description_penalty(
                teks,
                analysis["keyword"],
                brand.get("site_name", ""),
                judul=judul,
                riwayat=desc_lama + desc_ditolak,
                contoh=contoh_gaya.get("meta_description") or [],
            )

        # Plafon slot deskripsi, dipakai mengenali teks yang berhenti
        # karena kehabisan jatah - lihat finish_cut_description.
        batas_desc = int(
            (bagian.get("meta_description") or {}).get("max_length_any")
            or (bagian.get("meta_description") or {}).get("max_length")
            or 0
        )

        # Dirapikan SEBELUM dinilai, bukan sesudah.
        #
        # Urutan itu mengikat. Dinilai lebih dulu, yang diadu teks
        # yang masih membawa potongan kalimatnya, dan kandidat yang
        # menang bisa saja menang karena potongannya kebetulan tidak
        # mengulang apa pun. Dirapikan lebih dulu, yang diadu kalimat
        # yang benar-benar akan terbit.
        if "meta_description" in bagian:
            isi["meta_description"] = finish_cut_description(
                isi.get("meta_description"), batas_desc
            )

        if "meta_description" in bagian and gema_desc(
            isi.get("meta_description")
        ) >= HEAD_GOOD_ENOUGH:
            # Diminta beberapa kali, lalu DIADU - bukan diminta sekali
            # lalu diterima apa adanya.
            #
            # Sekali ulang tidak cukup, dan itu terukur di job 35:
            # permintaan ulangnya jalan, jawabannya tetap mengulang
            # judul, dan halamannya terbit dengan deskripsi yang baris
            # pertamanya habis untuk menuliskan lagi judul yang
            # berdiri persis di atasnya - persis yang dilaporkan
            # pengguna sebagai "copy paste".
            #
            # Karena suhu model di atas nol, permintaan yang sama
            # menghasilkan kalimat yang berbeda tiap kali. Yang
            # dipakai yang paling sedikit mengulang di antara semua
            # percobaan, jadi giliran tambahan tidak pernah membuat
            # hasilnya lebih buruk.
            terbaik = str(isi.get("meta_description") or "")
            nilai_terbaik = gema_desc(terbaik)

            for putaran in range(DESC_ECHO_RETRIES):
                # Alasan yang BENAR-BENAR berlaku, bukan kalimat tetap.
                #
                # Sebabnya sama seperti title_reasons: kalimat tetap
                # yang menyebut empat kemungkinan sekaligus membuat log
                # tidak bisa dipakai mendiagnosis apa pun, dan salah
                # satu dari empat itu - bentuk pembuka - baru
                # ditegakkan 21 Agustus 2026, jadi kalimat lamanya
                # bahkan tidak menyebutnya.
                sebab = (
                    "tidak dibuka nama situs"
                    if desc_opening_score(
                        terbaik, brand.get("site_name", "")
                    )
                    else (
                        "mengulang judulnya sendiri, deskripsi halaman "
                        "lain, contoh gayanya, atau mengulang keyword "
                        "dan nama situs"
                    )
                )

                catat(
                    on_progress,
                    f"Giliran {nomor}: deskripsi {sebab}; diminta "
                    f"lagi ({putaran + 1}/{DESC_ECHO_RETRIES}).",
                )

                if terbaik not in desc_ditolak:
                    desc_ditolak.append(terbaik)

                # Pembuka yang salah bentuk dikatakan apa adanya.
                #
                # Sisa alasan penolakan deskripsi memang sudah
                # terwakili kalimat tetap di atas - semuanya soal
                # "mengulang sesuatu", dan model bisa menebaknya. Yang
                # satu ini tidak bisa ditebak: ia soal BENTUK, dan
                # bentuk yang diminta ada di berkas contoh yang model
                # memang tidak diberi seluruhnya.
                catatan_desc = ""

                if desc_opening_score(terbaik, brand.get("site_name", "")):
                    catatan_desc = (
                        "\n\nDESKRIPSI KEMARIN DITOLAK. Perbaiki yang "
                        "ini saja:\n"
                        "- meta_description: BUKA DENGAN NAMA SITUS. "
                        f"Tulis \"{brand.get('site_name', '')}\" "
                        "sebagai kata pertama, lalu satu kata kerja "
                        "yang menyatakan apa yang disediakannya - "
                        "menyediakan, menghadirkan, menyajikan, "
                        "menawarkan, atau adalah. Jangan dibuka "
                        "dengan menyapa pembaca."
                    )

                ulangan = minta(
                    {"meta_description": bagian["meta_description"]},
                    nomor,
                    ulang=True,
                    catatan=catatan_desc,
                )

                baru, _ = fit_content_to_spec(
                    ulangan,
                    {"meta_description": bagian["meta_description"]},
                    fallbacks or {},
                )

                calon = finish_cut_description(
                    str(baru.get("meta_description") or ""), batas_desc
                )

                if not calon:
                    continue

                nilai = gema_desc(calon)

                if nilai < nilai_terbaik:
                    terbaik = calon
                    nilai_terbaik = nilai

                if nilai_terbaik < HEAD_GOOD_ENOUGH:
                    break

            isi["meta_description"] = terbaik

            if nilai_terbaik >= 1.0:
                warnings.append(
                    "Deskripsi masih mengulang judulnya sendiri, "
                    "deskripsi halaman sebelumnya, contoh gayanya, atau "
                    "mengulang keyword dan nama situs walau sudah "
                    f"diminta {DESC_ECHO_RETRIES + 1} kali; yang "
                    "dipakai jawaban yang paling sedikit bermasalah."
                )

        # Peringatan disusun ulang dari hasil akhir, sesudah percobaan
        # ulang. Yang dari percobaan pertama menghitung kekurangan yang
        # mungkin sudah tertutup.
        _, peringatan = fit_content_to_spec(isi, bagian, fallbacks or {})

        catat_terpakai(isi)

        # Nama brand dan keyword ditambal di sini, bukan diharapkan
        # dari model.
        #
        # Jalur halaman biasa sudah punya pengaman ini lewat
        # normalize_plan(); jalur template tidak pernah memakainya,
        # dan akibatnya terbaca di halaman jadi - title "Slot Online
        # Aman dan Transparan" terbit tanpa satu pun sebutan nama
        # situsnya. Untuk halaman yang seluruh gunanya memperkenalkan
        # sebuah brand, itu kehilangan yang paling mahal, dan
        # ditambal di Python jauh lebih murah daripada diulang jadi
        # satu aturan lagi di prompt yang sudah panjang.
        isi = ensure_template_identity(
            isi,
            bagian,
            analysis["keyword"],
            brand.get("site_name", ""),
            brand.get("niche", "gambling"),
            brand.get("region", "id"),
        )

        # Heading di dalam halaman ikut dirapikan, dengan alasan yang
        # sama seperti H1 - dan dengan bukti yang sama.
        #
        # Terukur end-to-end: h1 DAN h2 pertama sama-sama terbit
        # sebagai "WAYANGPLAY # Slot Gacor". Model diminta keduanya di
        # giliran yang sama, melihat judul yang sudah ditulisnya, lalu
        # memakai teks itu dua kali. Tidak ada yang menolaknya:
        # DISTINCT_ROLES cuma membandingkan heading dengan heading
        # LAIN, tidak dengan H1.
        #
        # Yang dikerjakan cuma PEMBUANGAN, bukan penulisan: tanda pisah
        # gaya judul dibuang, dan kalau sesudah itu headingnya tidak
        # memuat apa pun di luar nama situs dan keyword, sebutan nama
        # situsnya ikut dibuang. Heading bagian tidak perlu menyebut
        # nama situs - judul halaman sudah menyebutnya - jadi yang
        # tertinggal frasa berbasis keyword, yang berbeda dari H1 dan
        # tetap menamai bagiannya.
        nama_situs = brand.get("site_name", "").strip()

        if isinstance(isi.get("heading"), list) and nama_situs:
            kata_kunci = analysis["keyword"]
            rapi = []

            for teks_kepala in isi["heading"]:
                satu_kepala = " ".join(str(teks_kepala or "").split())

                if not satu_kepala:
                    rapi.append(teks_kepala)
                    continue

                satu_kepala = " ".join(
                    LOOSE_MARK.sub(" ", satu_kepala).split()
                ).strip(EDGE_MARKS)

                if not bare_title(
                    satu_kepala, kata_kunci, nama_situs
                ).strip():
                    tanpa_nama = " ".join(
                        strip_brand_mentions(satu_kepala, nama_situs).split()
                    ).strip(EDGE_MARKS)

                    if tanpa_nama:
                        satu_kepala = tanpa_nama

                rapi.append(satu_kepala)

            isi["heading"] = rapi

            # Pembanding H1 TIDAK dikerjakan di sini.
            #
            # plan_batches menaruh h1 dan heading di giliran yang
            # berbeda, jadi di giliran mana pun cuma salah satunya
            # yang ada di tangan - dan versi pertama penegakan ini
            # dipasang di sini lalu diam-diam tidak pernah berjalan.
            # Yang tinggal di sini cuma PERAPIAN bentuk, yang memang
            # tidak butuh H1. Penegakan kembarnya berdiri sesudah
            # merge_batch_content, tempat keduanya pasti ada
            # bersamaan.

        for peran, teks in isi.items():
            if peran.startswith("_"):
                continue

            if isinstance(teks, list):
                terkumpul.setdefault(peran, []).extend(
                    str(x) for x in teks
                )
            elif str(teks).strip():
                # Peran bertekstunggal ikut dikumpulkan. Title, H1,
                # dan deskripsi ditulis di giliran pertama, dan
                # giliran sesudahnya memakainya sebagai patokan sudut
                # pandang - tanpa itu tiap giliran memilih nadanya
                # sendiri dan halamannya terbaca seperti tempelan
                # beberapa penulis yang tidak saling bicara.
                terkumpul.setdefault(peran, []).append(str(teks).strip())

        hasil.append(isi)
        warnings.extend(peringatan)

    content = merge_batch_content(hasil, spec)

    warnings.extend(balance_paired_roles(content))

    # Salah ketik istilah dibetulkan sesudah semua giliran disatukan.
    #
    # Satu titik untuk seluruh halaman, bukan per peran, karena salah
    # ketiknya tidak memilih peran: "deposit qrisk" bisa jatuh di
    # title, di kartu fitur, di jawaban FAQ, atau di ulasan, dan yang
    # dilaporkan pengguna kebetulan yang di keyword.
    #
    # Dua nama brand dilindungi, bukan satu. Nama brand LAMA ikut
    # karena sebagian sisanya masih berdiri di isi ini, dan nama brand
    # di ranah ini rutin berjarak satu huruf dari istilahnya sendiri -
    # "GACORR" jadi "gacor", "MAXWINS" jadi "maxwin". Membetulkan nama
    # situs orang adalah kerusakan yang jauh lebih sulit dilihat
    # daripada salah ketik yang diperbaikinya.
    content, salah_ketik = fix_content_terms(
        content,
        analysis["keyword"],
        " ".join(
            bagian
            for bagian in (brand.get("site_name", ""), old_brand)
            if str(bagian or "").strip()
        ),
    )

    if salah_ketik:
        warnings.append(
            f"{salah_ketik} teks memuat salah ketik istilah dan sudah "
            "dibetulkan ke ejaan bakunya."
        )

    # Jawaban yang ditulis dalam bahasa yang salah dikosongkan di
    # titik yang sama, dan SEBELUM ragam bahasa dinaikkan - tidak ada
    # gunanya membakukan sapaan di kalimat yang memang akan dibuang.
    content, salah_bahasa = drop_foreign_content(
        content,
        brand.get("region", "id"),
    )

    if salah_bahasa:
        warnings.append(
            f"{salah_bahasa} teks dijawab model dalam bahasa yang "
            "salah dan dikosongkan; slotnya ditambal teks seperan "
            "dari halaman yang sama."
        )

    # Ragam bahasa dinaikkan di titik yang sama, dan hanya untuk
    # halaman berbahasa Indonesia.
    #
    # Daftar kata gaulnya seluruhnya kata Indonesia, jadi menjalankan
    # penyapu ini di halaman Thai cuma memakan waktu tanpa menyentuh
    # apa pun - dan yang lebih buruk, "ga" dan "lu" bisa saja jadi
    # potongan sah di aksara lain suatu saat.
    #
    # Diminta pengguna 21 Agustus 2026 atas halaman yang benar-benar
    # terbit: sembilan kalimat dibuka "Kamu bisa ...". Aturannya sudah
    # ikut dipasang di prompt; ini jaring pengamannya, karena aturan
    # prompt untuk model 4B diikuti kadang-kadang saja.
    if str(brand.get("region", "id")).lower().startswith("id"):
        content, ragam = fix_content_register(
            content,
            analysis["keyword"],
            " ".join(
                bagian
                for bagian in (brand.get("site_name", ""), old_brand)
                if str(bagian or "").strip()
            ),
        )

        if ragam:
            warnings.append(
                f"{ragam} teks memakai sapaan atau kata sehari-hari "
                "yang terlalu santai dan sudah dinaikkan ke ragam "
                "setengah resmi."
            )

        # Sisi sebelahnya, di titik yang sama.
        #
        # Sampai 30 Agustus 2026 hanya ada satu arah di sini: yang
        # terlalu santai dinaikkan, yang terlalu kaku dibiarkan.
        # Aturan kata kaku sudah ada di prompt sejak awal, tapi untuk
        # model 4B aturan tanpa penyapu berarti aturan yang diikuti
        # kadang-kadang saja - dan yang terbit adalah keluhan yang
        # ditulis pengguna apa adanya: "bahasa yang digunakan terlalu
        # kaku".
        #
        # Dijalankan SESUDAH penyapu santai, bukan sebelum. Yang di
        # atas bisa menghasilkan bentuk baku yang kebetulan ada di
        # daftar kaku, dan urutan ini membuat hasilnya lewat kedua
        # saringan - bukan cuma yang pertama.
        content, kaku = fix_content_stiffness(
            content,
            analysis["keyword"],
            " ".join(
                bagian
                for bagian in (brand.get("site_name", ""), old_brand)
                if str(bagian or "").strip()
            ),
        )

        if kaku:
            warnings.append(
                f"{kaku} teks memakai bentuk surat dinas yang terlalu "
                "kaku dan sudah diturunkan ke ragam setengah resmi."
            )

    # Ejaan nama situs dipulihkan di titik yang sama, dan SESUDAH
    # fix_content_terms.
    #
    # Urutannya penting. fix_content_terms melindungi kata nama brand
    # supaya tidak dibetulkan jadi istilah - tapi perlindungan itu
    # bekerja atas nama yang ejaannya BENAR. Nama yang salah ketik
    # tidak dikenalinya sebagai nama, dan token berangka memang
    # dilewatinya sama sekali, jadi "SIAM12S" lolos utuh dari sana.
    #
    # Ini yang menutupnya. Terukur pada halaman yang benar-benar
    # terbit: pengguna mengetik SIAM123, yang terbit SIAM12S - satu
    # huruf, dan halamannya berdiri atas nama situs yang tidak ada.
    # Bukan lapisan pemotong yang merusaknya; ia memang ditulis
    # begitu oleh model.
    content, brand_pulih = restore_brand_content(
        content,
        brand.get("site_name", ""),
        analysis["keyword"],
    )

    if brand_pulih:
        warnings.append(
            f"{brand_pulih} sebutan nama situs salah ketik dan sudah "
            "dikembalikan ke ejaan yang kamu masukkan."
        )

    # Klaim yang tidak dipunyai pipeline dibuang di titik yang sama
    # dengan salah ketik: sekali, sesudah semua giliran selesai.
    #
    # Alasannya juga sama. Klaimnya tidak memilih peran - lama proses
    # dalam detik bisa jatuh di paragraf, di jawaban FAQ, di kartu
    # fitur, atau di ulasan - jadi menyapunya per peran berarti ada
    # peran yang terlewat setiap kali daftar perannya bertambah.
    #
    # Dijalankan SESUDAH fix_content_terms, karena penyapu ini
    # membandingkan kata dan kata yang masih salah ketik tidak
    # dikenalinya.
    content, klaim = scrub_content(content)

    if klaim:
        warnings.append(
            f"{klaim} klaim yang tidak bisa dibuktikan pipeline "
            "(lama proses, jumlah member, tahun berdiri, nomor "
            "lisensi, atau janji menang) dibuang dari isi halaman."
        )

    # Kalimat yang menyalin isi perintah dibuang di titik yang sama.
    #
    # Pembandingnya prompt yang benar-benar dikirim di run ini -
    # brief_contoh sudah disusun di atas untuk mengukur ruang context,
    # dan isinya hampir seluruh teks perintah yang dilihat model.
    # Memakai prompt yang sama berarti pendeteksinya ikut berubah
    # sendiri setiap kali aturannya diubah, tanpa ada daftar kedua
    # yang harus diingat.
    leak_index = instruction_index(sistem_contoh + "\n" + brief_contoh)

    content, bocor = scrub_leaks(content, leak_index)

    if bocor:
        warnings.append(
            f"{bocor} kalimat menyalin isi perintah ke dalam teks "
            "yang terbit dan sudah dibuang."
        )

    # Kalimat yang disalin dari halaman pesaing, di titik yang sama.
    #
    # Pembandingnya bacaan yang benar-benar dikirim ke model di run
    # ini - paragraf pembuka, paragraf kunci, dan jawaban FAQ milik
    # sepuluh halaman yang sedang menang. Bahan itu memang sengaja
    # diperlihatkan supaya model tahu TOPIK apa yang perlu dibahas,
    # dan justru karena diperlihatkan ia bisa disalin.
    #
    # Aturannya sudah ada di prompt sejak aturan bunyi tulisan
    # diperbarui; ini jaring pengamannya, dengan alasan yang sama
    # seperti seluruh penyapu di sekitarnya.
    jiplak_index = source_index(analysis)

    content, jiplak, contoh_jiplak = scrub_copied(content, jiplak_index)

    if jiplak:
        warnings.append(
            f"{jiplak} kalimat menyalin kata demi kata dari halaman "
            "pesaing dan sudah dibuang"
            + (
                f' (contoh: "{contoh_jiplak[0]}")'
                if contoh_jiplak
                else ""
            )
            + "."
        )

    # Slot yang jadi kependekan GARA-GARA ketiga penyapu di atas
    # diminta ulang, bukan dibiarkan.
    #
    # Ini lubang yang tersisa dari pemasangan sebelumnya. Mesin
    # penambal teks pendek berjalan PER GILIRAN, sedangkan kedua
    # ketiganya berjalan sesudah semua giliran selesai - jadi paragraf
    # yang kehilangan kalimatnya di sini tidak pernah bertemu lagi
    # dengan yang bisa memintanya ulang, dan terbit lebih pendek
    # daripada jatah slotnya.
    #
    # Yang diminta ulang HANYA slot yang berlubang, lewat gap_spec -
    # bukan seluruh halaman. Satu paragraf yang kependekan tidak
    # sebanding dengan mengulang seluruh giliran.
    if klaim or bocor or jiplak:
        content, ditambal, gagal = repair_short_slots(
            content=content,
            spec=spec,
            minta=minta,
            leak_index=leak_index,
            fallbacks=fallbacks or {},
            terkumpul=terkumpul,
            terpakai=terpakai,
            on_progress=on_progress,
        )

        if ditambal:
            warnings.append(
                f"{ditambal} slot yang jadi kependekan sesudah "
                "penyapuan sudah diisi ulang."
            )

        if gagal:
            warnings.append(
                f"{len(gagal)} slot tetap kependekan sesudah "
                f"{REPAIR_RETRIES} kali diminta ulang ("
                + ", ".join(gagal)
                + "). Yang terbit versi teraman yang tersedia."
            )

    # Angka disatukan SESUDAH semua giliran selesai, bukan per giliran.
    #
    # Tabrakan angka justru terjadi ANTAR giliran - ulasan ditulis di
    # giliran lima, paragrafnya di giliran tiga, dan keduanya tidak
    # pernah saling melihat. Merapikannya per giliran berarti tiap
    # giliran konsisten dengan dirinya sendiri dan tetap bertabrakan
    # dengan giliran lain, yaitu persis keadaan yang mau dibereskan.
    #
    # Dijalankan SEBELUM penolak bunyi kembar di bawah, bukan
    # sesudahnya. Penyeragaman angka bisa MEMBUAT kembar - dua judul
    # yang cuma berbeda angkanya jadi satu bunyi begitu angkanya
    # disamakan - dan yang terakhir jalan harus yang masih bisa
    # meminta teks pengganti ke model.
    sebelum = dict(content)
    content = enforce_content_numbers(content, angka_halaman)

    diperbaiki = sum(
        1
        for peran, nilai in content.items()
        if not peran.startswith("_")
        and nilai != sebelum.get(peran)
    )

    if diperbaiki:
        warnings.append(
            f"Angka di {diperbaiki} peran disamakan dengan angka "
            "yang dipakai halaman ini, supaya satu hal tidak disebut "
            "dengan dua angka berbeda."
        )

    # Slot yang bakal terbit berbunyi sama diminta ulang di sini,
    # SELAGI modelnya masih bisa dihubungi.
    #
    # Ini putaran terakhir sebelum isinya diserahkan ke perender, dan
    # ia harus ada karena dua putaran sebelumnya masing-masing punya
    # titik buta.
    #
    # Yang per giliran cuma melihat jawaban gilirannya sendiri: peran
    # yang slotnya terbelah ke dua giliran tidak pernah diadu
    # antargiliran, padahal keduanya terbit di satu halaman. Yang
    # sesudah penyapuan cuma jalan kalau ada klaim atau kebocoran yang
    # benar-benar dibuang - halaman bersih melewatinya sama sekali.
    #
    # Sesudah ini yang tersisa cuma pemasangan, dan di sana model
    # sudah tidak ada. Penjaga di build_edits masih berdiri, tapi yang
    # bisa dilakukannya cuma menukar dengan sisa antrean; kalau
    # antreannya habis, tidak ada lagi teks yang bisa dimintanya.
    # Terukur pada halaman Thai terbit: dua judul dengan teks asal
    # berbeda sama-sama terbit "NAGAJITU | <keyword>", dan catatan
    # yang tertinggal cuma "tidak ada teks lain yang tersisa untuk
    # membedakannya".
    #
    # Yang diminta HANYA posisi yang mengulang. Pengulangan yang
    # memang dikehendaki template - dua slot berteks asal sama -
    # tidak dihitung kembar oleh duplicate_slots, jadi tidak pernah
    # ikut diminta ulang.
    content, dibedakan, tetap_kembar = repair_short_slots(
        content=content,
        spec=spec,
        minta=minta,
        leak_index=leak_index,
        fallbacks=fallbacks or {},
        terkumpul=terkumpul,
        terpakai=terpakai,
        on_progress=on_progress,
        cari=all_duplicates,
        label="Membedakan slot yang bunyinya mengulang",
        # Teks pengganti lewat penyeragaman angka yang sama dengan
        # yang barusan dijalankan atas seluruh halaman. Tanpa ini,
        # satu-satunya teks yang tidak diseragamkan justru teks yang
        # ditulis paling akhir.
        angka=angka_halaman,
    )

    if dibedakan:
        warnings.append(
            f"{dibedakan} slot yang bakal terbit berbunyi sama dengan "
            "slot lain sudah diminta ulang dan sekarang berbeda."
        )

    if tetap_kembar:
        warnings.append(
            f"{len(tetap_kembar)} slot masih berbunyi sama dengan slot "
            f"lain sesudah {REPAIR_RETRIES} kali diminta ulang ("
            + ", ".join(tetap_kembar)
            + ")."
        )

    # Cukup atau tidaknya bunyi yang tersedia dikatakan, bukan
    # disimpulkan dari halaman jadi. Peran yang kekurangan bunyi PASTI
    # menerbitkan slot kembar berapa pun bagusnya pemasangan di
    # bawahnya, dan itu keterangan yang cuma ada di sini.
    for peran, (butuh, punya) in distinct_tally(spec, content).items():
        if punya < butuh:
            catat(
                on_progress,
                f"{peran}: {butuh} bunyi berbeda dibutuhkan, "
                f"{punya} tersedia.",
            )

    # Bentuk judul ditegakkan LAGI di sini, sesudah semua penyapuan dan
    # penambalan selesai.
    #
    # ensure_template_identity di atas jalan PER GILIRAN, sementara
    # penyapu klaim, penyapu kebocoran, dan kedua putaran
    # repair_short_slots semuanya jalan SESUDAH giliran terakhir. Jadi
    # judul yang disentuh salah satu dari empat langkah itu terbit tanpa
    # pernah bertemu lagi dengan penegak bentuknya - dan yang masuk
    # lewat penambalan adalah teks model yang mentah, dengan nama situs
    # masih di tengah kalimat atau tidak ada sama sekali.
    #
    # Terukur end-to-end 16 Agustus 2026, job 93, template 'timah33':
    #
    #   log     : Menambal sesudah penyapuan: title 1 slot (1/2), lalu (2/2)
    #   terbit  : "Cari Slot Gacor dengan Data Terbaru"
    #   panjang : 35 karakter (lantainya 50)
    #   nama situs: TIDAK ADA
    #
    # Bentuk judul itu keputusan pengguna 10 Agustus 2026 dan ditegakkan
    # di Python justru karena prompt tidak bisa diandalkan menegakkannya
    # - lalu satu-satunya jalur yang melewatinya adalah jalur yang
    # dipakai persis waktu judulnya paling bermasalah.
    #
    # HANYA title. H1 sengaja tidak ikut, alasannya sama seperti di
    # ensure_template_identity: nama situs berpemisah di dalam halaman
    # terbaca seperti label, bukan seperti kalimat pembuka.
    #
    # Aman dijalankan dua kali: enforce_title_shape idempoten - judul
    # yang sudah berbentuk "NAMA # janji" tidak berubah lagi kalau
    # dilewatkan sekali lagi.

    # Judul yang tetap KOSONG sesudah semua penambalan tidak boleh
    # diserahkan ke pemasang apa adanya.
    #
    # short_roles menandai title yang kosong dan repair_short_slots
    # memintanya ulang - tapi permintaannya boleh gagal, dan kalau
    # gagal, yang sampai ke fill_template adalah string kosong. Di
    # titik itu tidak ada satu pun lapisan yang keberatan, dan
    # akibatnya BERBEDA di dua berkas yang seharusnya kembar:
    #
    #   landing : slot title mewarisi teks lewat lapis gema, karena di
    #             template ini teks lama <h1> SAMA PERSIS dengan teks
    #             lama <title>. Yang terbit teks H1 - dan H1 sengaja
    #             tidak ditegakkan bentuknya, jadi judulnya terbit
    #             tanpa nama situs.
    #   AMP     : teks lama <h1> BERBEDA dari teks lama <title>, jadi
    #             tidak ada gema yang cocok dan slotnya terbit dengan
    #             kalimat pemilik template.
    #
    # Terukur end-to-end 16 Agustus 2026, job 93, lalu direproduksi
    # persis di luar model dengan content["title"] dikosongkan:
    #
    #   landing : "Cari Slot Gacor dengan Data Terbaru"   (teks H1)
    #   AMP     : "OSB99 - Solusi Deposit QRIS ..."       (teks template)
    #
    # Pemasangan slotnya sendiri TIDAK rusak: dengan title terisi,
    # ketiga slot landing dan kedua slot AMP sama-sama menerimanya.
    # Yang salah bukan pemetaan melainkan prasyaratnya - tidak pernah
    # ada nilai yang dipetakan.
    #
    # Cadangannya H1 halaman ini sendiri: teks yang ditulis untuk
    # halaman yang sama, sudah berbahasa benar, sudah dibatasi
    # panjangnya. Kalau H1 pun kosong, dipakai keywordnya - dan
    # enforce_title_shape di bawah yang menambahkan nama situs beserta
    # tanda pisahnya. Bentuk yang sama dipakai normalize_plan di jalur
    # non-template, jadi ini bukan aturan baru melainkan aturan yang
    # sama dibawa ke jalur yang belum punya.
    if "title" in spec and not str(content.get("title") or "").strip():
        cadangan = str(content.get("h1") or "").strip() or str(
            analysis["keyword"] or ""
        ).strip()

        if cadangan:
            content["title"] = cadangan

            warnings.append(
                "Judul tidak terisi sesudah semua permintaan ulang; "
                "dipakai "
                + ("H1 halaman ini" if content.get("h1") else "keywordnya")
                + " sebagai dasar, lalu bentuk judulnya ditegakkan. "
                "Tanpa ini berkas landing dan AMP terbit dengan judul "
                "yang berbeda."
            )

    # H1 yang cuma menyalin judul dilaporkan, bukan didiamkan.
    #
    # Terukur pada halaman yang benar-benar terbit: title
    # "WAYANGPLAY # Slot Gacor Paling Menarik, Mainkan Kemenangan yang
    # Nyata", lalu H1 "WAYANGPLAY # Slot Gacor" - pembuka title yang
    # sama persis, dipotong sepanjang jatah slotnya. Aturan promptnya
    # sudah ada sejak lama ("berbeda susunan kata dari title") dan
    # tidak ada satu pun yang memeriksanya, jadi tidak ada yang tahu
    # ketika model mengabaikannya.
    #
    # Dilaporkan sebagai peringatan, TIDAK ditulis ulang di sini.
    # Menulis ulang berarti mengarang kalimat yang tidak diminta
    # siapa pun; yang benar adalah memberi tahu pemiliknya bahwa
    # halaman ini punya dua judul yang sama supaya ia bisa
    # memutuskan sendiri. Pencegahannya di prompt - lihat aturan
    # nomor 4 di build_template_content_prompt.
    judul_kepala = str(content.get("title") or "").strip()
    kepala_h1 = str(content.get("h1") or "").strip()

    if judul_kepala and kepala_h1:
        nama_situs = brand.get("site_name", "")
        kata_kunci = analysis["keyword"]

        # Diukur di LUAR nama situs dan keyword, bukan atas teks
        # utuhnya. Keduanya WAJIB ada di title maupun di H1, jadi
        # keduanya selalu beririsan - terukur, H1 yang menyalin judul
        # dan H1 yang berdiri sendiri sama-sama mendapat 0,62 dari
        # echo_score, dan angka yang sama untuk dua hal yang berbeda
        # tidak memisahkan apa pun. Alasan yang sama sudah dipakai
        # title_echo_score dan style_copy_score.
        sisa_h1 = bare_title(kepala_h1, kata_kunci, nama_situs)
        sisa_judul = bare_title(judul_kepala, kata_kunci, nama_situs)

        if not sisa_h1.strip():
            warnings.append(
                "H1 halaman ini tidak memuat apa pun di luar nama situs "
                "dan keyword, jadi ia label - bukan kalimat pembuka. "
                "Pembaca yang sudah mengklik dari hasil pencarian "
                "membacanya lagi tanpa mendapat satu keterangan baru."
            )
        elif echo_score(sisa_h1, sisa_judul) >= 1.0:
            warnings.append(
                "H1 halaman ini mengulang judulnya. Keduanya dibaca di "
                "tempat yang berbeda - judul di hasil pencarian, H1 di "
                "dalam halaman - jadi teks yang sama dua kali membuang "
                "satu kesempatan menerangkan halaman ini."
            )

    # Judul yang jatuh di BAWAH lantainya sesudah dirapikan Python.
    #
    # Lantainya ditegakkan grammar llama.cpp atas jawaban MENTAH -
    # tanda kutip penutup ditahan sampai jatahnya terpenuhi - jadi
    # yang ditulis model memang selalu cukup panjang. Yang terjadi
    # sesudahnya tidak diperiksa siapa pun: enforce_title_shape
    # mencabut setiap sebutan nama situs dari badan judul, dan judul
    # yang menyebut namanya dua kali kehilangan belasan karakter di
    # situ. Terukur terbit 44 lebar untuk lantai 50.
    #
    # Dilaporkan, tidak ditambal. Tidak ada di Python ini yang sanggup
    # menyambung judul jadi lebih panjang tanpa mengarang - dan
    # menempelkan kata supaya angkanya cukup justru bentuk yang
    # dilarang di seluruh berkas ini.
    aturan_judul = spec.get("title") or {}
    lantai_judul = int(aturan_judul.get("min_length") or 0)

    if judul_kepala and lantai_judul:
        lebar_judul = display_width(judul_kepala)

        if lebar_judul < lantai_judul:
            warnings.append(
                f"Judul terbit {lebar_judul} lebar, di bawah lantai "
                f"{lantai_judul}. Model menulisnya cukup panjang; yang "
                "memendekkannya perapian di Python - biasanya karena "
                "nama situs disebut lebih dari sekali lalu dicabut."
            )

    kepala_lain = [
        str(x).strip()
        for x in (content.get("heading") or [])
        if str(x or "").strip()
    ]

    if kepala_h1 and any(
        echo_score(satu, kepala_h1) >= 1.0 for satu in kepala_lain
    ):
        warnings.append(
            "Ada heading di dalam halaman yang bunyinya sama dengan H1. "
            "Dua judul yang sama berturut-turut terbaca sebagai isi yang "
            "terduplikasi."
        )

    # Title DAN H1 ditegakkan lagi di sini, sesudah seluruh giliran
    # selesai - bukan cuma title.
    #
    # Penegakan per giliran tidak cukup, dan sebabnya bentuk giliran
    # itu sendiri: title dan H1 tidak selalu jatuh di giliran yang
    # sama. Kalau H1 ditulis di giliran yang tidak memuat title,
    # penegaknya tidak punya judul untuk diadu, jadi H1 yang isinya
    # persis judul lolos tanpa ada yang keberatan.
    #
    # Terukur pada halaman yang benar-benar terbit di atas template
    # nyata, output/rajawali77-slot-deposit-qris-20260820_044759:
    #
    #   title : RAJAWALI77 @ Slot Deposit QRIS untuk Pengguna Smartphone
    #   h1    : RAJAWALI77 Slot Deposit QRIS untuk Pengguna Smartphone
    #
    # Di sini judulnya sudah final, jadi H1 diadu dengan judul yang
    # benar-benar akan terbit. Zona ikut dikirim supaya bentuk
    # posisional penggantinya ditulis dalam bahasa halamannya.
    kepala = {
        peran: spec[peran]
        for peran in ("title", "h1")
        if peran in spec
    }

    if kepala:
        content = ensure_template_identity(
            content,
            kepala,
            analysis["keyword"],
            brand.get("site_name", ""),
            brand.get("niche", "gambling"),
            brand.get("region", "id"),
        )

    content["_metadata"] = metadata

    # Sudut dan cara bercerita judul dititipkan di dalam isi supaya ikut
    # tercatat sebagai "sudah dipakai" sesudah halamannya terbit.
    #
    # Penanda sudut/cara/susunan judul TIDAK lagi dicatat ke riwayat.
    #
    # Ketiganya dulu digilir di sini supaya halaman berikutnya bisa
    # menghindari yang sudah terpakai. Yang digilir itu daftar tetap
    # milik NEIIU, dan daftar itulah yang sekarang dicabut: sudut
    # halaman ditentukan model sendiri, jadi tidak ada lagi pilihan
    # NEIIU yang perlu diingat.
    #
    # Yang menjaga halaman kedua tetap berbeda dari halaman pertama
    # tidak ikut hilang - ia justru yang lebih dapat dipercaya, karena
    # mengukur apa yang BENAR-BENAR terbit: judul lama masuk ke prompt
    # lewat title_history_block, lalu concept_repeat_score,
    # opening_repeat_score, dan shape_repeat_score mengadu judul baru
    # dengan judul-judul itu di Python.
    #
    # MARK_ROLES di database/neiiu_history_db.py sengaja dibiarkan:
    # baris penanda dari run-run lama masih ada di basis data, dan
    # daftar itu yang menahannya supaya tidak ikut terbaca sebagai
    # teks halaman.

    # Pertanyaan FAQ halaman-halaman sebelumnya dibawa serta ke tahap
    # pengisian template. Kartu cadangan dipilih di sana, dan tanpa
    # daftar ini halaman kedua menambal lubangnya dengan pertanyaan yang
    # sama persis - bank pertanyaannya digilir dari nama brand, dan nama
    # brandnya memang tidak berubah antar halaman.
    content["_faq_lama"] = [
        str(teks)
        for teks in ((riwayat or {}).get("faq_question") or [])
        if str(teks).strip()
    ]

    # Heading yang bunyinya sama dengan H1 diganti DI TITIK PALING
    # AKHIR, sesudah setiap tahap lain selesai.
    #
    # Dua tempat sebelumnya sudah dicoba dan dua-duanya diam-diam
    # tidak berjalan. Per giliran: plan_batches menaruh h1 dan heading
    # di giliran yang BERBEDA, jadi di giliran mana pun cuma salah
    # satunya ada di tangan. Sesudah merge_batch_content: masih ada
    # tahap-tahap sesudahnya yang menyentuh kedua peran ini -
    # penambalan slot kosong, penyapu klaim, pemulih ejaan brand, dan
    # ensure_template_identity - dan cukup satu di antaranya yang
    # membuat keduanya bertemu lagi.
    #
    # Di sini tidak ada lagi yang berjalan sesudahnya. Yang dilihat
    # sama persis dengan yang dikirim ke fill_template.
    #
    # Bentuk kegagalannya perlu diingat: kode yang terpasang tapi
    # tidak menyala tidak meninggalkan jejak apa pun - tidak ada
    # galat, tidak ada peringatan, dan hasilnya sama seperti kalau
    # kodenya tidak ada. Karena itu peringatan di bawah dikeluarkan
    # juga ketika penggantinya HABIS: kalau tidak, satu-satunya kabar
    # yang tersisa adalah diam.
    kepala_h1 = str(content.get("h1") or "").strip()
    daftar_kepala = content.get("heading")

    if not kepala_h1 and isinstance(daftar_kepala, list) and daftar_kepala:
        # Kabar yang membedakan "berjalan dan bersih" dari "tidak
        # pernah berjalan". Tanpa ini, penegakan yang tidak menyala
        # tidak meninggalkan jejak apa pun - dan itu tiga kali membuat
        # cacat yang sama terbit dengan kode perbaikannya terpasang.
        warnings.append(
            "H1 kosong di akhir penyusunan isi, jadi heading tidak bisa "
            "diadu dengannya. Halaman bisa terbit dengan dua judul yang "
            "sama tanpa ada yang memeriksanya."
        )

    if kepala_h1 and isinstance(daftar_kepala, list):
        cadangan_kepala = [
            teks
            for teks in spare_headings(brand, analysis["keyword"])
            if not near_twins(teks, kepala_h1)
        ]

        # Dicocokkan dengan near_twins, bukan kesamaan persis.
        #
        # Terukur terbit: h1 "Slot Online di X7GAMING88" dan h2 "Main
        # Slot Online di X7GAMING88" - beda satu kata di depan, sama
        # persis sisanya. Kesamaan persis membiarkannya lewat, padahal
        # pembaca halaman membaca dua judul yang sama.
        #
        # near_twins sudah dipakai penolak kembar antar slot di peran
        # yang sama, jadi ambang dan wataknya sudah terukur - tidak
        # ada ukuran kedua yang bisa bergeser sendiri dari yang
        # pertama.
        terpakai_kepala = [kepala_h1]
        tukar_kepala: dict[str, str] = {}
        diganti_kepala = 0
        tersisa_kembar = 0

        for urut, satu_kepala in enumerate(daftar_kepala):
            bersih_kepala = " ".join(str(satu_kepala or "").split())

            if not bersih_kepala:
                continue

            if not any(
                near_twins(bersih_kepala, sudah)
                for sudah in terpakai_kepala
            ):
                terpakai_kepala.append(bersih_kepala)
                continue

            if not cadangan_kepala:
                tersisa_kembar += 1
                continue

            baru_kepala = cadangan_kepala.pop(0)
            daftar_kepala[urut] = baru_kepala
            terpakai_kepala.append(baru_kepala)
            tukar_kepala[bersih_kepala] = baru_kepala
            diganti_kepala += 1

        content["heading"] = daftar_kepala

        # Peta "teks lama -> teks baru" ikut diperbarui, dan tanpa ini
        # seluruh penggantian di atas TIDAK PERNAH SAMPAI ke halaman.
        #
        # Ini yang tiga kali membuat cacat yang sama terbit dengan
        # kode perbaikannya menyala dan melaporkan keberhasilannya.
        # build_edits tidak membagikan isi peran berdaftar urut
        # dokumen begitu saja: untuk peran yang artinya harus
        # dipertahankan, ia memakai content["_by_old"], peta yang
        # disusun jauh lebih awal di fit_content_to_spec. Mengubah
        # content["heading"] tanpa mengubah peta itu berarti mengubah
        # daftar yang tidak dibaca siapa pun - dan yang terpasang di
        # slotnya tetap nilai lama.
        #
        # Gejalanya paling menyesatkan yang mungkin: log melaporkan
        # "1 heading diganti", dan halaman terbit tanpa perubahan.
        if tukar_kepala:
            peta_lama = content.get("_by_old")

            if isinstance(peta_lama, dict):
                peta_kepala = peta_lama.get("heading")

                if isinstance(peta_kepala, dict):
                    for kunci, nilai in list(peta_kepala.items()):
                        pengganti = tukar_kepala.get(
                            " ".join(str(nilai or "").split())
                        )

                        if pengganti:
                            peta_kepala[kunci] = pengganti

        if diganti_kepala:
            warnings.append(
                f"{diganti_kepala} heading berbunyi sama dengan H1 atau "
                "dengan heading lain, dan diganti dari bank judul bagian "
                "NEIIU. Dua judul yang sama berturut-turut terbaca "
                "sebagai isi yang terduplikasi."
            )

        if tersisa_kembar:
            warnings.append(
                f"{tersisa_kembar} heading masih berbunyi sama dengan H1 "
                "dan bank judul bagian sudah habis. Halaman ini terbit "
                "dengan dua judul yang sama."
            )

    return content, warnings


# Berapa kali slot yang kependekan sesudah penyapuan diminta ulang.
#
# Dua. Tiap putaran satu permintaan penuh ke model - puluhan detik
# sampai beberapa menit di mesin ini - dan yang dikejar cuma
# mengembalikan panjang beberapa slot. Putaran ketiga membayar lebih
# mahal daripada yang diperbaikinya, dan slot yang gagal dua kali
# biasanya gagal karena topiknya memang sulit ditulis panjang, bukan
# karena modelnya kurang percobaan.
REPAIR_RETRIES = 2

# Sebanyak apa satu permintaan tambalan boleh meminta sekaligus.
#
# Model kecil menjawab daftar pendek jauh lebih tuntas daripada
# daftar panjang, dan bedanya bukan sedikit. Terukur pada halaman
# Thai terbit: diminta empat belas heading dalam satu permintaan,
# dijawab dua; sisanya jatuh ke jaring terakhir di template_filler
# dan terbit sebagai satu judul yang diulang delapan kali.
#
# Dipecah, tiap permintaan tetap membawa awalan prompt yang sama -
# jadi yang dibayar cuma jawabannya, karena Ollama memakai ulang
# hasil pemrosesan awalan yang tidak berubah.
REPAIR_CHUNK = 6


def chunk_spec(sisa: dict, besar: int = REPAIR_CHUNK) -> list[dict]:
    """
    Memecah satu permintaan tambalan jadi beberapa yang lebih kecil.

    Tiap potongan membawa "positions" miliknya sendiri, jadi
    jawabannya tetap kembali ke slot yang benar - pemecahan ini tidak
    pernah menggeser satu pun teks ke tempat lain.
    """
    potongan: list[dict] = []

    for role, rule in sisa.items():
        posisi = list(rule.get("positions") or range(int(rule["count"])))

        for mulai in range(0, len(posisi), besar):
            bagian = posisi[mulai : mulai + besar]

            satu = dict(rule)
            satu["count"] = len(bagian)
            satu["positions"] = bagian

            for kunci in (
                "samples",
                "budgets",
                "columns",
                "floors",
                "partners",
                "fresh",
            ):
                nilai = rule.get(kunci)

                if nilai:
                    satu[kunci] = list(nilai[mulai : mulai + besar])

            jatah = satu.get("budgets")

            if jatah:
                satu["max_length"] = min(jatah)
                satu["max_length_any"] = max(jatah)

            satu["offset"] = int(rule.get("offset", 0)) + mulai

            potongan.append({role: satu})

    return potongan


def repair_short_slots(
    content: dict,
    spec: dict,
    minta,
    leak_index: dict,
    fallbacks: dict,
    terkumpul: dict,
    terpakai: dict,
    on_progress=None,
    cari=None,
    label: str = "Menambal sesudah penyapuan",
    angka: dict | None = None,
) -> tuple[dict, int, list[str]]:
    """
    Meminta ulang slot yang jawabannya belum layak, HANYA slot itu.

    Dipakai dua kali di ujung penulisan, dengan pencari lubang yang
    berbeda. Yang pertama sesudah penyapu klaim dan penyapu
    kebocoran, mencari slot yang jadi kependekan gara-gara sapuan
    itu. Yang kedua selalu, mencari slot yang bakal terbit berbunyi
    sama dengan slot lain.

    "cari" itu yang memutuskan slot mana yang dianggap berlubang -
    short_roles kalau tidak diisi. Seluruh mesin di bawahnya sama
    persis untuk keduanya: gap_spec meminta posisi yang itu saja,
    chunk_spec memecahnya jadi permintaan kecil, dan extend_content
    mengembalikan jawabannya ke posisi asalnya. Halaman tidak pernah
    disusun ulang gara-gara beberapa slot.

    Yang dijaga di sini ada empat, dan keempatnya alasan mengapa
    fungsinya tidak sekadar "minta lagi":

    1. Klaim yang dibuang TIDAK BOLEH kembali. Jawaban baru lewat
       penyapu yang sama sebelum dipakai, jadi kalimat yang sama
       terlarangnya dibuang lagi - dan kalau slotnya tetap kependekan
       sesudah itu, ia dilaporkan, bukan diisi paksa.
    2. Kalimat lama TIDAK BOLEH digandakan. Penolak kembar yang sudah
       ada dipakai apa adanya lewat "seen", yang diisi teks yang
       sudah berdiri di halaman ini.
    3. Topik, bahasa, nada, jenis halaman, pembaca, brand, dan
       keyword ikut sendiri: promptnya disusun ulang lewat minta(),
       yang memakai brief dan brand yang sama dengan giliran biasa.
       Tidak ada satu pun aturan yang perlu disalin ke sini.
    4. Tidak ada putaran tanpa akhir. REPAIR_RETRIES membatasinya,
       dan putaran berhenti lebih awal begitu tidak ada lubang lagi
       atau begitu satu putaran tidak memperbaiki apa pun.

    Mengembalikan (isi, jumlah slot yang berhasil diisi, daftar slot
    yang menyerah).
    """
    ditambal = 0
    cari = cari or short_roles

    kurang = cari(spec, content)

    if not kurang:
        return content, 0, []

    for putaran in range(REPAIR_RETRIES):
        sisa_spec = gap_spec(spec, kurang)

        if not sisa_spec:
            break

        kembar = duplicate_slots(spec, content)

        catat(
            on_progress,
            f"{label}: "
            + ", ".join(
                f"{peran} {len(lubang)} slot"
                + (
                    f" ({len(kembar[peran])} kembar)"
                    if kembar.get(peran)
                    else ""
                )
                for peran, lubang in kurang.items()
            )
            + f" (percobaan {putaran + 1}/{REPAIR_RETRIES}).",
        )

        # Teks yang sudah berdiri di halaman ini ikut dikirim supaya
        # jawaban barunya menyambung, bukan mengulang.
        sejauh_ini = {
            peran: list(terkumpul.get(peran) or [])
            + [
                str(teks).strip()
                for teks in (content.get(peran) or [])
                if str(teks).strip()
            ]
            for peran in spec
            if isinstance(content.get(peran), list)
        }

        sebelum = cari(spec, content)
        putus = False

        # Diminta sepotong-sepotong, bukan sekaligus. Tiap potongan
        # melihat hasil potongan sebelumnya lewat "sudah", jadi yang
        # kedua tidak menulis ulang apa yang baru saja ditulis yang
        # pertama.
        for bagian_spec in chunk_spec(sisa_spec):
            berjalan = {
                peran: list(terkumpul.get(peran) or [])
                + [
                    str(teks).strip()
                    for teks in (content.get(peran) or [])
                    if str(teks).strip()
                ]
                for peran in spec
                if isinstance(content.get(peran), list)
            }

            try:
                tambahan = minta(
                    bagian_spec,
                    0,
                    ulang=True,
                    sudah={**terkumpul, **sejauh_ini, **berjalan},
                )
            except Exception as error:
                # Kegagalan menambal tidak boleh menggagalkan halaman.
                # Yang sudah ada tetap terbit; sebabnya dicatat.
                catat(
                    on_progress,
                    f"Penambalan gagal ({type(error).__name__}: {error}). "
                    "Isi yang sudah ada dipakai apa adanya.",
                )
                putus = True
                break

            tambahan.pop("_metadata", None)

            lanjutan, _ = fit_content_to_spec(
                tambahan,
                bagian_spec,
                fallbacks,
                seen={
                    **terpakai,
                    **{
                        peran: set(terpakai.get(peran) or set())
                        | {
                            normalize(str(x))
                            for x in (content.get(peran) or [])
                            if str(x).strip()
                        }
                        for peran in bagian_spec
                    },
                },
            )

            # Jawaban baru disapu SEBELUM dipasang. Tanpa ini,
            # penambalan jadi jalan masuk yang melewati kedua penjaga -
            # dan slot yang tadi dibersihkan justru terisi ulang dengan
            # klaim yang sama.
            lanjutan, _ = scrub_content(lanjutan)
            lanjutan, _ = scrub_leaks(lanjutan, leak_index)

            # Angkanya diseragamkan juga kalau daftarnya dikirim.
            # Teks yang masuk lewat jalur ini datang SESUDAH
            # penyeragaman yang berlaku untuk seluruh halaman, jadi
            # tanpa ini ia satu-satunya teks yang menyebut angkanya
            # sendiri.
            if angka:
                lanjutan = enforce_content_numbers(lanjutan, angka)

            content = extend_content(content, lanjutan, spec, bagian_spec)

        if putus:
            break

        kurang = cari(spec, content)

        terisi = sum(len(v) for v in sebelum.values()) - sum(
            len(v) for v in kurang.values()
        )

        if terisi > 0:
            ditambal += terisi

        if not kurang:
            break

        # Satu putaran yang tidak memperbaiki apa pun tidak akan
        # diperbaiki putaran berikutnya dengan permintaan yang sama.
        if terisi <= 0:
            break

    menyerah = [
        f"{peran} {len(lubang)} slot"
        for peran, lubang in (kurang or {}).items()
    ]

    return content, ditambal, menyerah


def batch_progress(on_progress, nomor: int, jumlah: int, ulang: bool = False):
    """
    Menyisipkan nomor giliran ke laporan kemajuan.

    Tanpa ini, pencacah token kembali ke nol tiap giliran dan
    prosesnya terbaca seperti mengulang dari awal, bukan maju.

    "batches" wajib tetap berupa ANGKA. Pembacanya di
    services/neiiu_pipeline.py membandingkannya dengan angka untuk
    memutuskan apakah nomor giliran perlu ditampilkan, dan mengirim
    teks ke sana menghentikan seluruh job di tengah langkah yang
    paling mahal. Penanda giliran ulang karena itu dikirim di kunci
    sendiri, bukan dengan menumpangi kunci ini.
    """
    if not on_progress:
        return None

    def report(info: dict) -> None:
        on_progress(
            {
                **info,
                "batch": nomor,
                # Nomor giliran nol berarti permintaan ini bukan bagian
                # dari pembagian giliran - penambalan sesudah
                # penyapuan, misalnya. Jumlahnya dilaporkan satu supaya
                # susun_kabar tidak menuliskan "bagian 0/8", yang
                # membaca seperti giliran yang hilang alih-alih
                # pekerjaan tambahan.
                "batches": jumlah if nomor else 1,
                "batch_retry": ulang,
            }
        )

    return report


def catat(on_progress, pesan: str) -> None:
    """
    Menulis satu baris ke log job kalau ada yang mendengarkan.
    """
    if on_progress:
        on_progress({"line": pesan})


# Slot yang wajib memuat nama brand sekaligus keyword, beserta
# berapa lebar yang tersedia untuk keduanya.
#
# meta_description tidak ikut: keyword di sana sudah dijaga
# ensure_keyword lewat jalurnya sendiri, dan memaksa nama brand ke
# depan deskripsi memakan ruang kalimat yang justru dibaca orang di
# hasil pencarian.
IDENTITY_SLOTS = ("title", "h1")


def ensure_template_identity(
    isi: dict,
    spec: dict,
    keyword: str,
    brand_name: str,
    niche: str = "gambling",
    region: str = "id",
) -> dict:
    """
    Menambal nama brand dan keyword ke title dan H1 hasil template.

    Batasnya diambil dari jatah slot yang sebenarnya, bukan angka
    tetap. Title di template pengguna dipatok 60 karakter, dan
    menambal tanpa melihat batas itu cuma memindahkan masalahnya:
    teksnya lolos pemeriksaan lalu dipotong mentah waktu dipasang.
    """
    if not keyword.strip() and not brand_name.strip():
        return isi

    hasil = dict(isi)

    for role in IDENTITY_SLOTS:
        if role not in spec:
            continue

        teks = hasil.get(role)

        if not isinstance(teks, str) or not teks.strip():
            continue

        batas = spec[role].get("max_length_any") or spec[role]["max_length"]

        # Angka dibuang sebelum penambalan, dengan alasan yang sama
        # seperti di normalize_plan: ensure_identity memotong judul
        # untuk memberi tempat pada nama brand, dan memotong sambil
        # menghitung angka yang kemudian dibuang berarti ekor judulnya
        # tercabut demi ruang yang tidak dipakai siapa pun.
        hasil[role] = ensure_identity(
            strip_title_pile(strip_figures(teks), keyword),
            keyword,
            brand_name,
            int(batas),
        )

        # Bentuknya ditegakkan sesudah penambalan, bukan sebelumnya.
        # ensure_identity menempelkan nama brand dan keyword dengan
        # pemisahnya sendiri, jadi menegakkan bentuk lebih dulu cuma
        # menghasilkan judul yang dirapikan lalu dicoret-coret lagi.
        #
        # H1 sengaja tidak ikut. H1 dibaca sebagai kalimat pembuka di
        # dalam halaman, bukan sebagai baris di hasil pencarian, dan
        # nama situs berpemisah di situ terbaca seperti label.
        if role == "title":
            hasil[role] = enforce_title_shape(
                hasil[role],
                keyword,
                brand_name,
                int(batas),
                niche,
            )
        elif role == "h1":
            # Judul dikirim supaya H1 bisa diadu dengannya. Urutan
            # IDENTITY_SLOTS menaruh title lebih dulu, jadi yang
            # dibaca di sini judul yang SUDAH ditegakkan bentuknya -
            # yang benar-benar akan terbit.
            hasil[role] = enforce_h1_shape(
                hasil[role],
                keyword,
                brand_name,
                int(batas),
                region,
                title=str(hasil.get("title") or ""),
            )

    return hasil


def enforce_h1_shape(
    h1: str,
    keyword: str,
    brand: str,
    limit: int,
    region: str = "id",
    title: str = "",
) -> str:
    """
    Menegakkan bahwa H1 adalah kalimat pembuka, bukan judul kedua.

    Niatnya sudah tertulis di ensure_template_identity sejak lama -
    "H1 dibaca sebagai kalimat pembuka di dalam halaman, bukan sebagai
    baris di hasil pencarian, dan nama situs berpemisah di situ
    terbaca seperti label" - tapi tidak ada satu pun yang
    memeriksanya. Yang terbit karenanya, terukur end-to-end:

        title : WAYANGPLAY # Slot Gacor Paling Menarik, Main Tanpa Ribet
        h1    : WAYANGPLAY # Slot Gacor
        h2    : WAYANGPLAY # Slot Gacor

    Model menyalin pembuka judulnya sendiri. Jatah H1 di template itu
    40 karakter dan yang dipakainya cuma 23, jadi sebabnya bukan
    kekurangan ruang - menyalin memang jawaban termurah, dan tidak ada
    yang menolaknya.

    Dua langkah:

      1. Tanda pisah gaya judul dibuang. "WAYANGPLAY # Slot Gacor"
         jadi "WAYANGPLAY Slot Gacor".

      2. Kalau sesudah itu H1 tidak memuat apa pun di luar nama situs
         dan keyword, ia disusun ulang sebagai frasa posisional dalam
         bahasa halaman: "Slot Gacor di WAYANGPLAY".

    Langkah kedua TIDAK mengarang apa pun. Dua token yang sama,
    disusun sebagai frasa yang wajar dibaca orang, bukan sebagai
    label bertanda pisah. Yang mengarang justru pilihan lain yang
    sempat dipertimbangkan - menuliskan keterangan yang tidak ada
    datanya - dan itu sebabnya tidak diambil.

    H1 yang memang sudah punya isi sendiri tidak disentuh sama sekali
    selain pembuangan tanda pisah.
    """
    bersih = " ".join(str(h1 or "").split())
    nama = str(brand or "").strip()

    if not bersih:
        return bersih

    # Tanda pisah gaya judul dibuang, tapi hanya yang berdiri LEPAS -
    # diapit spasi atau menempel di ujung kata. Tanda hubung di dalam
    # kata tidak ikut, alasannya sama seperti di LOOSE_MARK.
    #
    # Emoji ikut dibuang, dan itu bukan tambahan yang manis: emoji
    # ADALAH salah satu tanda pisah yang boleh terpilih untuk judul -
    # lihat TITLE_MARKS - jadi H1 yang menyalin judul membawanya
    # serta. Terukur terbit: "X7GAMING88 (petir) Slot Online
    # Pengalaman". LOOSE_MARK tidak memuatnya, jadi tanpa baris ini
    # separuh pembuangannya terlewat.
    bersih = " ".join(LOOSE_MARK.sub(" ", bersih).split())
    bersih = " ".join(
        EMOJI_MARK.sub(" ", bersih).split()
    ).strip(BRAND_EDGE_MARKS)

    if not nama or not str(keyword or "").strip():
        return bersih[:limit]

    # H1 yang isinya JUDUL ITU SENDIRI, cuma tanpa tanda pisahnya.
    #
    # Ini bentuk ketiga yang lolos dua langkah di atas: H1-nya punya
    # keterangan sendiri - jadi bukan label - tapi keterangan itu
    # persis keterangan judulnya. Terukur pada halaman yang
    # benar-benar terbit di atas template nyata,
    # output/rajawali77-slot-deposit-qris-20260820_041334:
    #
    #   title : RAJAWALI77 @ Slot Deposit QRIS untuk Pemain yang Ingin Cepat
    #   h1    : RAJAWALI77 Slot Deposit QRIS untuk Pemain yang Ingin Cepat
    #
    # Dua baris itu berdiri berurutan - satu di hasil pencarian, satu
    # di halaman - dan pembaca membaca kalimat yang sama dua kali.
    # Yang dibandingkan JANJI-nya, bukan teks utuhnya: nama situs
    # memang wajib ada di keduanya, jadi mengadu teks utuh berarti
    # mengadu bagian yang sudah pasti sama.
    judul = " ".join(str(title or "").split())

    menyalin_judul = bool(judul) and near_twins(
        title_promise(bersih, nama).casefold(),
        title_promise(judul, nama).casefold(),
    )

    if bare_title(bersih, keyword, nama).strip() and not menyalin_judul:
        return bersih[:limit]

    # Tidak ada apa pun di luar nama situs dan keyword - ia label -
    # atau isinya cuma salinan judul.
    bentuk = PAGE_TEXT.get(region, PAGE_TEXT["id"]).get(
        "h1_form", PAGE_TEXT["id"]["h1_form"]
    )

    susun = bentuk.format(
        keyword=" ".join(
            kata[:1].upper() + kata[1:] for kata in keyword.split()
        ),
        brand=nama,
    )

    # Kalau bentuk posisionalnya sendiri tidak muat, yang dipakai H1
    # apa adanya - dipotong. Label yang muat masih lebih berguna
    # daripada frasa yang terpenggal di tengah nama situs.
    return susun if len(susun) <= limit else bersih[:limit]


# Seberapa mirip pembuka satu teks dengan teks lain sebelum dihitung
# sebagai pengulangan.
#
# Dibandingkan per frasa tiga kata, bukan per kata. Alasannya sama
# dengan PHRASE_DUPLICATE_RATIO di generators/template_filler.py:
# irisan kata tidak bisa membedakan "kalimat yang sama ditulis ulang"
# dari "dua kalimat berbeda tentang topik yang sama", karena
# kosakatanya memang seharusnya sama.
ECHO_RATIO = 0.5

# Berapa bagian kata isi judul yang sudah habis terpakai di pembuka
# deskripsi sebelum dihitung sebagai pengulangan.
#
# Perbandingan frasa di atas tidak menangkapnya sendirian, dan itu
# terukur pada halaman yang dilaporkan pengguna:
#
#   title : TIMAH33 menghadirkan slot gacor dengan sistem spin modern
#   desc  : Akses slot gacor di TIMAH33 dengan sistem spin modern
#           yang lancar dan responsif...
#
# Irisan frasanya cuma 0,09 - satu kata sisipan sudah cukup menggeser
# seluruh frasa tiga kata - padahal enam dari tujuh kata isi judulnya
# terpakai lagi di baris pertama deskripsi. Dua teks itu berdiri
# berdampingan di hasil pencarian dan pembaca melihatnya sebagai satu
# kalimat yang ditulis dua kali.
#
# Angkanya diukur dari pasangan itu: yang mengulang 0,71, sedangkan
# deskripsi yang benar-benar membawa keterangan baru duduk di 0,14
# sampai 0,43. Ambangnya di ruang kosong di antaranya.
#
# Salah tuduh di sini murah: yang terjadi cuma satu permintaan
# tambahan, dan kalau jawabannya tidak lebih baik yang pertama tetap
# dipakai.
ECHO_COVERAGE = 0.6

# Berapa kali deskripsi diminta ulang kalau masih mengulang judulnya.
#
# Sempat satu, dan satu tidak cukup: di job 35 permintaan ulangnya
# jalan dan jawabannya tetap mengulang. Tiga percobaan tambahan masih
# murah - deskripsi cuma 200 karakter, dan awalan promptnya sudah ada
# di cache - sementara yang dibeli adalah baris paling banyak dibaca
# di seluruh hasil pencarian.
DESC_ECHO_RETRIES = 3

# Berapa kali judul diminta ulang kalau ia mengulang judul halaman
# yang sudah pernah terbit.
#
# Judul ditangani sendiri, terpisah dari penolak kembar yang lain,
# karena ia bukan salah satu dari sekian teks melainkan HULU seluruh
# halaman: bagian "Sudut Pandang Halaman Ini" menyuruh paragraf,
# heading, FAQ, dan ulasan melanjutkan sudut yang dipilih di judul.
# Dua halaman yang judulnya sama akan sama seluruhnya, berapa pun
# kalimat lain yang berhasil dibedakan.
TITLE_REPEAT_RETRIES = 2

# Ambang judul-mengulang-judul, dinyatakan sebagai kelipatan ambang
# echo_score biasa.
#
# Lebih ketat dari 1.0, dan angkanya diukur dari pasangan sungguhan:
#
#   lama  : TIMAH33 | Deposit QRIS Satu Detik Tanpa Potongan
#   calon : TIMAH33 | Setor QRIS Sedetik Tanpa Potongan Sama Sekali   0.83
#   calon : TIMAH33 | Riwayat Transaksi Yang Bisa Dibuka Kapan Saja   0.28
#
# Yang tengah itu judul yang sama dengan kata yang ditukar - persis
# yang dikeluhkan pengguna sebagai "sama saja" - dan ia lolos kalau
# ambangnya 1.0. Yang bawah benar-benar sudut lain. Jadi ambangnya
# ditaruh di ruang kosong di antara keduanya, bukan di tengah sebaran.
TITLE_REPEAT_LIMIT = 0.6

# Seberapa besar irisan frasa dengan contoh gaya sebelum dihitung
# sebagai menyalin.
#
# Berkas contoh gaya diperlihatkan ke model supaya ia tahu bentuk yang
# diminta, dan model kecil menjawab bentuk yang diperlihatkan dengan
# cara yang paling murah: menyalinnya. Terukur di job 41, judul yang
# terbit -
#
#   terbit : WAYANGPLAY # Slot Gacor dengan AI Predictor Maxwin & RTP
#            Tertinggi
#   contoh : [ BRAND ]: Situs Slot Gacor dengan AI Predictor Maxwin &
#            RTP Tertinggi        <- baris 114 knowledge/gaya_title.txt
#
# - baris contoh itu sendiri, dengan nama situs ditukar. Tidak ada
# satu pun penyaring yang keberatan: penyaring yang ada membandingkan
# jawaban dengan judul milik TEMPLATE, bukan dengan berkas contohnya.
#
# Angkanya dari jarak yang terukur pada pasangan itu: yang menyalin
# 0,857, sedangkan judul lain di berkas yang sama maupun judul yang
# ditulis baru semuanya 0,000. Ambangnya ditaruh jauh di bawah yang
# pertama supaya salinan separuh ikut tertangkap, dan masih jauh di
# atas yang kedua.
STYLE_COPY_LIMIT = 0.3

# Penanda nama situs di berkas contoh gaya.
BRAND_SLOT = re.compile(r"\[\s*BRAND\s*\]", re.I)


def bare_style(teks: str, brand: str) -> str:
    """
    Membuang nama situs dari satu teks sebelum dibandingkan.

    Perlu karena contoh gaya menulis "[ BRAND ]" sedangkan jawaban
    model menulis nama sungguhannya. Dibiarkan, keduanya terbaca
    sebagai kata yang berbeda dan salinan persis pun tampak agak
    berbeda.
    """
    bersih = BRAND_SLOT.sub(" ", str(teks or ""))
    nama = str(brand or "").strip()

    if nama:
        bersih = re.sub(re.escape(nama), " ", bersih, flags=re.I)

    return normalize(" ".join(bersih.split()))


# Seberapa besar irisan KATA dengan contoh gaya sebelum dihitung
# menyalin.
#
# Ukuran kedua, dan ia yang menutup lubang yang dikeluhkan pengguna:
# "title kata katanya udah pernah dipakai, jangan dipakai lagi biar
# ga samaan apalagi mirip mirip".
#
# Terukur pada judul yang terbit di job 55:
#
#   terbit : WAYANGPLAY # Slot Gacor Update Harian RTP 96,3% Terbaru
#   contoh : [ BRAND ] | Update Harian RTP Slot dengan Pola Gacor
#            Terbaik
#
#   irisan per frasa tiga kata : 0,11   <- lolos ambang 0,3
#   irisan per kata            : 0,62
#
# Keduanya jelas judul yang sama bagi pembaca - kata yang sama persis,
# cuma urutannya ditukar - dan justru penukaran urutan itu yang
# membuat perbandingan per frasa buta: satu kata bergeser, seluruh
# frasa tiga katanya ikut bergeser.
#
# Perbandingan per frasa TIDAK dibuang, karena ia yang menangkap
# salinan panjang yang kosakatanya tidak seberapa mirip. Yang dipakai
# nilai tertinggi di antara keduanya.
#
# Ambangnya lebih longgar daripada ambang frasa, dan memang harus:
# dua judul untuk topik yang sama wajar berbagi "slot", "gacor", dan
# nama brandnya. Yang tidak wajar adalah berbagi hampir seluruhnya.
STYLE_TOKEN_LIMIT = 0.5


def style_copy_score(teks, contoh: list[str], brand: str) -> float:
    """
    Seberapa jauh sebuah jawaban menyalin contoh gaya yang dilihatnya.

    Dinyatakan sebagai KELIPATAN AMBANG, sama seperti echo_score, jadi
    dua ukuran yang berbeda satuannya bisa diadu di satu tempat.

    Diukur dua cara sekaligus - per frasa tiga kata dan per kata -
    lalu yang paling memberatkan yang dipakai. Alasannya di
    STYLE_TOKEN_LIMIT.
    """
    bersih = bare_style(teks, brand)

    badan = content_shingles(bersih)
    kata = content_tokens(bersih)

    if not contoh or (not badan and not kata):
        return 0.0

    tertinggi = 0.0

    for satu in contoh:
        lawan = bare_style(satu, brand)

        lain = content_shingles(lawan)

        if badan and lain:
            tertinggi = max(
                tertinggi,
                len(badan & lain) / len(badan | lain) / STYLE_COPY_LIMIT,
            )

        lain_kata = content_tokens(lawan)

        if kata and lain_kata:
            tertinggi = max(
                tertinggi,
                len(kata & lain_kata)
                / len(kata | lain_kata)
                / STYLE_TOKEN_LIMIT,
            )

    return tertinggi


def echo_score(teks, acuan: str) -> float:
    """
    Seberapa jauh pembuka teks ini mengulang acuannya.

    Angkanya dinyatakan sebagai KELIPATAN AMBANG, bukan sebagai
    irisan mentah: 1.0 berarti tepat di ambang, di atas itu
    mengulang, di bawahnya tidak. Dua ukuran yang berbeda satuannya
    jadi bisa dibandingkan, dan dua jawaban jadi bisa diadu untuk
    dipilih yang paling sedikit mengulang.

    Yang dibandingkan hanya PEMBUKANYA, sepanjang acuannya sendiri.
    Deskripsi yang menyebut lagi nama brand dan keywordnya di tengah
    kalimat memang seharusnya begitu; yang salah adalah deskripsi
    yang seluruh baris pertamanya habis untuk menuliskan ulang judul
    yang berdiri persis di atasnya.

    Dua ukuran, karena satu pengulangan bisa disamarkan dua cara.
    Yang menyusun ulang katanya tertangkap perbandingan frasa; yang
    menyisipkan kata di antaranya - susunannya berubah, isinya sama
    persis - tertangkap cakupan kata isi.
    """
    badan = " ".join(str(teks or "").split())
    judul = " ".join(str(acuan or "").split())

    if not badan or not judul:
        return 0.0

    awal = " ".join(badan.split()[: len(judul.split())])

    nilai = 0.0

    a = content_shingles(awal)
    b = content_shingles(judul)

    if a and b:
        nilai = (len(a & b) / len(a | b)) / ECHO_RATIO

    kata_judul = content_tokens(judul)

    if kata_judul:
        nilai = max(
            nilai,
            (len(kata_judul & content_tokens(awal)) / len(kata_judul))
            / ECHO_COVERAGE,
        )

    return nilai


def echoes_text(teks, acuan: str) -> bool:
    """
    Apakah teks ini membuka dengan kalimat acuannya?
    """
    return echo_score(teks, acuan) >= 1.0


# ==========================================================
# MUTU TITLE DAN META DESCRIPTION
# ==========================================================
#
# Semua ukuran di bawah ini dinyatakan sebagai KELIPATAN AMBANGNYA
# masing-masing - 1.0 berarti tepat di batas, di atasnya ditolak -
# supaya bisa diadu di satu tempat dengan echo_score dan
# style_copy_score yang sudah memakai satuan itu lebih dulu.
#
# Yang ditambahkan di sini menutup keluhan yang tidak tertangkap
# ketiga penyaring lama. Terukur 16 Agustus 2026,
# dua permintaan berturut-turut untuk brand dan keyword yang sama:
#
#   judul 1 : WAYANGPLAY # Slot Gacor yang Diproses Langsung dan Aman
#   judul 2 : WAYANGPLAY # Slot Gacor Langsung, Withdraw Diproses
#             Langsung
#   desc  1 : Cari slot gacor di WAYANGPLAY. Mulai bermain sekarang...
#   desc  2 : Cari slot gacor di WAYANGPLAY dengan pengalaman...
#
# Tidak satu pun tertangkap penyaring lama: riwayatnya kosong (jalur
# cepat memang tidak mencatat), ekornya bukan tumpukan penyangat, dan
# tidak ada contoh gaya yang disalin. Yang mengulang justru hal yang
# paling dilihat pembaca - PEMBUKAAN kalimatnya - dan itu yang
# diukur opening_repeat_score.


# Berapa kali keyword utuh boleh berdiri di dalam satu judul.
#
# Sekali. Judul cuma 50-70 karakter, dan keyword yang ditulis dua kali
# di ruang sesempit itu adalah bentuk keyword stuffing yang paling
# gampang dilihat mesin pencari maupun pembaca.
TITLE_KEYWORD_LIMIT = 1

# Di deskripsi dua kali masih wajar: 140-180 karakter adalah dua
# sampai tiga kalimat, dan menyebut topiknya sekali di kalimat pembuka
# lalu sekali lagi waktu menerangkan cara pakainya bukan pengulangan.
DESC_KEYWORD_LIMIT = 2

# Nama situs di deskripsi. Sekali menyatakan halaman siapa ini; dua
# kali sudah terbaca seperti kalimat yang ditulis untuk mesin.
DESC_BRAND_LIMIT = 1

# Berapa bagian kata judul yang boleh berupa kata penyangat.
#
# title_tail_pile hanya melihat EKOR judul, dan itu memang tempat
# tumpukan paling sering berdiri. Tapi penyangat yang disebar rata -
# "Situs Slot Gacor Terbaik dan Terpercaya" - tidak punya ekor yang
# bisa dipotong, padahal ia justru pola yang dikeluhkan pengguna:
# "[BRAND] Situs Slot Gacor Terbaik / Terbaru / Online".
#
# Sepertiga, dan angkanya dari daftar contoh title milik pengguna
# sendiri (knowledge/gaya_title.txt): judul miliknya rata-rata 0,12
# penyangat per kata isi, dan yang tertinggi 0,29. Ambangnya ditaruh
# tepat di atas judulnya yang paling menyangat, bukan di tengah
# sebaran, supaya judul yang seperti miliknya tidak ikut tertolak.
TITLE_FILLER_SHARE = 0.34

# Pemisah klausa di dalam sebuah judul: koma, dan kata sambung yang
# memulai janji berikutnya.
#
# Titik dua dan garis tegak TIDAK ikut - keduanya justru tanda pisah
# yang dipasang enforce_title_shape antara nama situs dan janjinya,
# dan menghitungnya berarti menghukum bentuk judul yang diminta
# pengguna sendiri.
TITLE_CLAUSE_MARK = re.compile(r",|\s+(?:dan|atau|serta)\s+", re.IGNORECASE)

# Berapa pemisah klausa yang masih dimaafkan di dalam satu judul.
#
# Satu. Angkanya diukur dari 143 baris contoh title milik pengguna
# sendiri (knowledge/gaya_title.txt), dihitung pada bagian JANJI-nya
# saja - sesudah nama situs dan tanda pisahnya dibuang:
#
#   0 pemisah : 111 baris (78%)
#   1 pemisah :  26 baris (18%)
#   2 pemisah :   3 baris (2%)
#   3 pemisah :   3 baris (2%)
#
# Jadi dua ke atas praktis tidak ada di daftar miliknya, sementara
# satu lazim. Ambangnya ditaruh persis di situ.
#
# Yang ditangkapnya keluhan pengguna "judulnya kaku dan terputus,
# tidak tersusun dalam satu kalimat", dan judul yang terukur:
#
#   WAYANGPLAY # Akses Cepat Slot Gacor, Dana Aman, Langsung Dibayar
#   SIAM123 💰 Kamu Main slot online, lihat hasilnya, dapatkan pembayaran
#
# Keduanya tiga janji yang didempetkan, bukan satu janji yang utuh.
# Aturannya sudah ada di prompt ("SATU TARIKAN NAPAS: satu janji,
# bukan tiga janji yang ditumpuk") dan tetap dilanggar - jadi ia
# ditegakkan di Python, sama seperti bentuk judulnya.
#
# Untuk aksara yang tidak memakai koma seperti Thai, pemeriksaan ini
# praktis tidak pernah berbunyi. Itu disengaja: ambangnya diukur dari
# contoh berbahasa Indonesia, dan menebak ambang untuk bahasa yang
# tidak punya pembandingnya berarti menolak judul atas dasar dugaan.
TITLE_CLAUSE_ALLOWED = 1

# Berapa kata pembuka yang diadu untuk menilai dua teks membuka sama.
#
# Tiga kata isi. Dua terlalu pendek - "slot gacor" saja sudah dua kata
# dan dua judul untuk keyword yang sama memang harus menyebutnya -
# sedangkan empat sudah melewati bagian kalimat yang menentukan kesan
# pertama pembaca.
OPENING_WORDS = 3

# Berapa bagian kata pembuka yang boleh sama sebelum dihitung membuka
# dengan cara yang sama.
#
# Dua pertiga: dua dari tiga kata pembuka yang sama masih bisa
# kebetulan (keduanya memuat keyword), tiga dari tiga tidak pernah.
OPENING_LIMIT = 0.67


# Berapa kata paling sedikit yang boleh berdiri di potongan TERAKHIR
# sebuah judul berkoma.
#
# Tiga. Angkanya dari 120 judul milik pengguna sendiri: 11 di antaranya
# memakai koma, dan potongan terakhirnya TIDAK PERNAH lebih pendek dari
# tiga kata (sebarannya 3,4,4,4,4,5,5,5,6,6 kata). Satu kata di ujung
# sesudah koma tidak pernah terjadi sekali pun di daftar miliknya.
#
# Ini yang menangkap judul yang dikeluhkan:
#
#   WAYANGPLAY # Kamu Cari Slot Gacor? Bisa Dibuka dari HP, Kemenangan
#
# "Kemenangan" berdiri sendiri sesudah koma tanpa satu pun kata yang
# mengikatnya ke kalimat sebelumnya. Yang diperiksa PANJANG dan
# LETAKNYA, bukan jenis katanya - "WAYANGPLAY - Pilihan Slot Online
# Terbaru" juga berakhir di kata benda dan sama sekali tidak tersentuh,
# karena ia tidak punya koma sama sekali.
TAIL_MIN_WORDS = 3


# Awalan dan akhiran Indonesia yang paling sering membungkus satu akar.
#
# Dipakai membandingkan GAGASAN dua judul, bukan katanya: "kemenangan",
# "menang", dan "dimenangkan" adalah satu hal yang ditulis tiga cara,
# dan pembanding per kata melihatnya sebagai tiga kata berbeda.
#
# Sengaja kasar dan sengaja tidak lengkap. Ini bukan pengurai bahasa;
# ia cuma perlu cukup benar untuk mempertemukan bentuk-bentuk satu
# kata di dalam judul 70 karakter. Pemenggalan hanya dilakukan kalau
# sisanya masih empat huruf, supaya "pola" tidak jadi "la".
ROOT_PREFIX = (
    "menge", "meng", "meny", "mem", "men", "me",
    "peng", "peny", "pem", "pen", "per", "pe",
    "ber", "ter", "di", "ke", "se",
)

ROOT_SUFFIX = ("kannya", "annya", "inya", "kan", "nya", "an", "i")

# Sisa huruf paling sedikit sesudah dipenggal.
ROOT_MIN = 4


def word_root(kata: str) -> str:
    """
    Akar kasar sebuah kata Indonesia.

    Bukan stemmer sungguhan dan tidak berusaha jadi stemmer. Yang
    dibutuhkan cuma satu: "kemenangan" dan "menang" harus jatuh ke
    bentuk yang sama waktu dua judul dibandingkan gagasannya.

    Dipenggal BERULANG sampai bentuknya berhenti berubah, dan itu
    bukan kerapian melainkan syarat. Satu putaran menghasilkan
    "kemenangan" -> "menang" tapi "menang" -> "nang", jadi dua bentuk
    dari satu kata justru jatuh ke dua kunci yang berbeda - kebalikan
    dari gunanya. Terukur waktu pemeriksa ini pertama dipasang: judul
    yang menulis "Kemenangan" dan judul yang menulis "Menang" terbaca
    sebagai dua gagasan.

    Hasilnya kadang terpenggal lebih jauh daripada akar sungguhannya
    ("menang" jadi "nang"), dan itu tidak apa-apa: ini kunci
    pembanding, bukan kata yang ditampilkan. Yang penting kunci yang
    sama untuk kata yang sama.
    """
    hasil = str(kata or "").lower()

    # Dibatasi supaya tidak ada kata yang bisa memutar selamanya.
    for _ in range(4):
        sebelum = hasil

        for awalan in ROOT_PREFIX:
            if (
                hasil.startswith(awalan)
                and len(hasil) - len(awalan) >= ROOT_MIN
            ):
                hasil = hasil[len(awalan):]
                break

        for akhiran in ROOT_SUFFIX:
            if (
                hasil.endswith(akhiran)
                and len(hasil) - len(akhiran) >= ROOT_MIN
            ):
                hasil = hasil[: -len(akhiran)]
                break

        if hasil == sebelum:
            break

    return hasil


def concept_tokens(teks: str, keyword: str = "", brand: str = "") -> set:
    """
    Kata yang membawa GAGASAN sebuah judul.

    Yang dibuang tiga hal yang pasti sama di semua judul untuk satu
    halaman - nama situs, keyword, dan kata sambung - lalu sisanya
    diakarkan. Yang tertinggal adalah satu-satunya bagian judul yang
    membedakannya dari judul lain untuk topik yang sama.

    Kata penyangat ikut dibuang. "Terbaik" dan "terpercaya" tidak
    membawa gagasan apa pun, jadi dua judul yang cuma sama-sama
    memakainya bukan dua judul yang sama gagasannya.
    """
    milik: set[str] = set()

    for sumber in (keyword, brand):
        for satu in re.findall(r"\w+", str(sumber or "").lower()):
            milik.add(satu)
            milik.add(word_root(satu))

    return {
        akar
        for akar in (word_root(t) for t in content_tokens(teks))
        if akar
        and akar not in milik
        and akar not in TITLE_FILLER_TAIL
        and akar not in TITLE_INTENSIFIER
    }



# Tetapan di bawah ini sempat ikut terbawa waktu bobot sudut judul
# dibuang - keduanya bertetangga, tidak lebih. Dikembalikan apa
# adanya dari versi sebelumnya.
# Seberapa besar irisan GAGASAN dua judul sebelum dihitung mengulang.
#
# Diukur dari 7.140 pasangan di antara 120 judul milik pengguna - yang
# semuanya, menurut pemiliknya, gagasan yang berbeda-beda:
#
#   rata-rata      0,019
#   persentil 90   0,083
#   persentil 95   0,100
#   persentil 99   0,200
#
# Lalu dibandingkan dengan pasangan yang benar-benar terbit dan
# dikeluhkan:
#
#   "Slot Gacor yang Diproses Langsung dan Aman"
#   "Slot Gacor Langsung, Withdraw Diproses Langsung"   -> 0,500
#
# Ambangnya ditaruh di ruang kosong di antara persentil 99 milik
# pengguna dan pasangan yang mengulang itu.
#
# YANG TIDAK BISA DILAKUKANNYA harus dicatat sejelas kemampuannya.
# Ukuran ini buta terhadap sinonim: "Cari slot gacor di X" dan
# "Temukan slot gacor di X" mendapat 0,000 padahal keduanya gagasan
# yang sama - pengguna sendiri menyebut pasangan itu sebagai contoh
# yang harus tertangkap. Menutupnya butuh embedding, dan itu di luar
# yang diminta.
#
# Jadi ia berdiri sebagai PELENGKAP. Yang benar-benar menegakkan
# perbedaan gagasan adalah sudut yang ditugaskan lalu diperiksa -
# lihat concept_repeat_score. Dua judul yang masing-masing wajib
# membawa sudut yang berbeda tidak bisa jadi gagasan yang sama,
# berapa pun sinonim yang dipakainya.
CONCEPT_REPEAT_LIMIT = 0.34


def phrase_count(teks: str, frasa: str) -> int:
    """
    Berapa kali sebuah frasa berdiri di dalam teks, tanpa peduli huruf.

    Dibatasi batas kata di kedua ujungnya supaya "slot" di dalam
    "slotter" tidak ikut terhitung. Aksara yang tidak mengenal spasi -
    Thai, misalnya - tidak punya batas kata yang bisa dipakai, jadi
    untuk teks seperti itu yang dihitung kemunculan apa adanya.
    """
    isi = str(teks or "")
    cari = " ".join(str(frasa or "").split())

    if not isi or not cari:
        return 0

    if thai_share(cari) > 0.5:
        return isi.casefold().count(cari.casefold())

    return len(
        re.findall(
            r"(?<!\w){}(?!\w)".format(re.escape(cari)),
            isi,
            re.IGNORECASE,
        )
    )


def keyword_repeat_score(teks: str, keyword: str, batas: int) -> float:
    """
    Seberapa jauh sebuah teks mengulang keywordnya.

    Nol kali tidak dihitung masalah di sini. Keyword yang HILANG sudah
    diurus ensure_identity dan keyword_covered, dan menghitungnya dua
    kali berarti judul tanpa keyword ditolak karena dua alasan yang
    sebenarnya satu.
    """
    if not str(keyword or "").strip() or batas < 1:
        return 0.0

    jumlah = phrase_count(teks, keyword)

    if jumlah <= batas:
        return 0.0

    # Satu kelebihan sudah cukup untuk menolak, jadi kelipatannya
    # dihitung dari batas + 1 - bukan dari batasnya - supaya dua kali
    # untuk batas satu jatuh tepat di 1.0.
    return jumlah / (batas + 1)


def brand_repeat_score(teks: str, brand: str, batas: int) -> float:
    """
    Seberapa jauh sebuah teks mengulang nama situsnya.

    Untuk judul ini tidak dipakai: enforce_title_shape sudah mencabut
    setiap sebutan kedua sebelum namanya ditempelkan di kepala. Yang
    memerlukannya deskripsi, tempat tidak ada penegak bentuk sama
    sekali.
    """
    if not str(brand or "").strip() or batas < 1:
        return 0.0

    jumlah = phrase_count(teks, brand)

    if jumlah <= batas:
        return 0.0

    return jumlah / (batas + 1)


# Kata yang menyatakan RASA, bukan topik. Dipakai mengeluarkan kata
# semacam ini dari kosakata topik yang dipanen dari berkas contoh -
# berkas itu memang memuat "Terbaik" dan "Resmi" di beberapa barisnya,
# dan tanpa daftar ini keduanya ikut terhitung sebagai topik konkret.
VAGUE_WORDS = frozenset(
    """
    terbaik terpercaya terbaru terlengkap terpopuler nomor satu
    pengalaman bermain main nyaman mudah gampang seru asyik optimal
    memuaskan menyenangkan lengkap praktis modern canggih unggul
    berkualitas profesional pilihan favorit populer hebat luar biasa
    sempurna maksimal ideal tepat cocok bagus baik oke mantap
    """.split()
)


@lru_cache(maxsize=1)
def topic_vocabulary() -> frozenset:
    """
    Kosakata TOPIK, dipanen dari berkas contoh gaya milik pengguna.

    Bukan daftar tulisan tangan, dan itu disengaja. Yang menentukan
    "judul ini menyebut sesuatu yang nyata" adalah selera pengguna
    sendiri, dan seleranya sudah tertulis lengkap di
    knowledge/gaya_title.txt - 49 baris yang seluruhnya menyebut hal
    yang bisa ditunjuk: withdraw, bonus new member, link alternatif,
    login anti blokir, RTP live, bocoran pola, deposit QRIS, pulsa
    tanpa potongan, lisensi.

    Dipanen berarti daftar ini ikut berubah sendiri begitu pengguna
    menambah atau mengganti contohnya, tanpa ada daftar kedua di kode
    yang harus diingat orang.

    Kata rasa dibuang lewat VAGUE_WORDS, kata tugas lewat
    CONTENT_STOPWORDS. Sisanya yang dianggap topik.
    """
    kata: set[str] = set()

    for slot in ("title", "meta_description"):
        for contoh in load_style_examples(slot):
            bersih = contoh.replace("[ BRAND ]", " ")

            for potong in re.findall(r"[A-Za-zÀ-ɏ]{3,}", bersih):
                kecil = potong.casefold()

                if kecil in VAGUE_WORDS or kecil in CONTENT_STOPWORDS:
                    continue

                kata.add(kecil)

    return frozenset(kata)


def vague_title_score(teks: str, keyword: str, brand: str = "") -> float:
    """
    Seberapa jauh sebuah judul berhenti di rasa tanpa menyebut topik.

    Yang diperiksa bagian judul DI LUAR nama situs dan DI LUAR
    keywordnya. Keduanya wajib ada di setiap judul, jadi menghitungnya
    sebagai "topik" membuat setiap judul lulus tanpa pernah menambah
    satu keterangan pun - dan itu persis judul yang dikeluhkan
    pengguna 21 Agustus 2026:

        BATARATOTO - Slot Online Pengalaman Bermain Terbaik

    Di luar nama situs dan keyword "slot online", yang tersisa
    "Pengalaman Bermain Terbaik": tiga kata yang tidak menunjuk satu
    hal pun yang bisa dibuka, dibandingkan, atau dicari. Contoh milik
    pengguna sendiri selalu menambah topik kedua - "& Bocoran Pola
    Slot Gacor", "& Login Anti Blokir 24 Jam".

    Ini BUKAN mesin sudut judul yang dicabut 18 Agustus 2026. Yang itu
    menugaskan satu sudut lalu menuntut kata dari daftar sudut itu;
    yang ini tidak menugaskan apa pun dan menerima topik mana saja
    dari kosakata yang dipanen dari contoh pengguna. Sudutnya tetap
    dipilih model - yang dituntut cuma judulnya menyebut sesuatu.
    """
    sisa = bare_title(teks, keyword, brand)

    if not str(sisa).strip():
        # Judul yang isinya cuma nama situs dan keyword sudah diurus
        # ukuran lain; di sini ia tidak dihitung dua kali.
        return 0.0

    topik = topic_vocabulary()

    if not topik:
        return 0.0

    kata = {
        potong.casefold()
        for potong in re.findall(r"[A-Za-zÀ-ɏ]{3,}", str(sisa))
    }

    if kata & topik:
        return 0.0

    # Tepat di atas ambang terima, bukan jauh di atasnya. Judul yang
    # cuma kurang topik masih bisa kalah dari judul yang melanggar
    # hal lain lebih berat, dan itu urutan yang benar.
    return 1.05


def filler_share_score(teks: str, keyword: str, brand: str = "") -> float:
    """
    Berapa bagian judul yang habis untuk kata penyangat.

    Daftarnya TITLE_FILLER_TAIL dan TITLE_INTENSIFIER - daftar yang
    sama yang dipakai title_tail_pile - jadi tidak ada daftar kedua
    yang harus diingat waktu isinya berubah. Bedanya cuma tempat
    melihat: yang itu hanya ekor, yang ini seluruh judul.

    Kata milik keyword dan nama situs tidak ikut dihitung, dengan
    alasan yang sama seperti di title_tail_pile: "gacor" di dalam
    "slot gacor" adalah topik halamannya, bukan penyangat.
    """
    kata = [
        satu.strip(EDGE_MARKS).casefold()
        for satu in str(teks or "").split()
    ]

    milik = {
        potong.casefold()
        for potong in re.findall(
            r"\w+",
            f"{keyword or ''} {brand or ''}",
        )
    }

    isi = [
        satu
        for satu in kata
        if satu and satu not in milik and satu not in CONTENT_STOPWORDS
    ]

    if not isi:
        return 0.0

    penyangat = sum(
        1
        for satu in isi
        if satu in TITLE_FILLER_TAIL or satu in TITLE_INTENSIFIER
    )

    return (penyangat / len(isi)) / TITLE_FILLER_SHARE


def title_promise(teks: str, brand: str = "") -> str:
    """
    Bagian janji sebuah judul: yang tersisa sesudah nama situs dan
    tanda pisahnya dibuang.

    Dipakai pemeriksaan yang cuma berlaku untuk janjinya, bukan untuk
    judul utuh. Nama situs dan tanda pisah dipasang NEIIU sendiri,
    jadi menghitungnya berarti menghukum bentuk yang diminta pengguna.
    """
    bersih = re.sub(
        re.escape(str(brand or "").strip()),
        " ",
        str(teks or ""),
        flags=re.I,
    ) if str(brand or "").strip() else str(teks or "")

    return " ".join(bersih.split()).strip(BRAND_EDGE_MARKS)


def clause_pile_score(teks: str, brand: str = "") -> float:
    """
    Berapa janji yang didempetkan di dalam satu judul.

    Nol berarti satu kalimat utuh. Di atas 1.0 berarti judulnya
    beberapa potongan yang disambung koma - lihat TITLE_CLAUSE_ALLOWED
    untuk angkanya dan dari mana ia diukur.
    """
    janji = title_promise(teks, brand)

    if not janji:
        return 0.0

    jumlah = len(TITLE_CLAUSE_MARK.findall(janji))

    if jumlah <= TITLE_CLAUSE_ALLOWED:
        return 0.0

    return jumlah / (TITLE_CLAUSE_ALLOWED + 1)


def concept_repeat_score(teks: str, lain, keyword: str = "", brand: str = "") -> float:
    """
    Seberapa jauh gagasan judul ini mengulang gagasan judul lain.

    Batasnya dan apa yang TIDAK bisa ditangkapnya ada di
    CONCEPT_REPEAT_LIMIT. Ringkasnya: ia menangkap judul yang
    memakai kata yang sama untuk hal yang sama, tidak menangkap judul
    yang memakai sinonim.
    """
    milik = concept_tokens(teks, keyword, brand)

    if not milik:
        return 0.0

    tertinggi = 0.0

    for satu in lain or []:
        lawan = concept_tokens(satu, keyword, brand)

        if not lawan:
            continue

        tertinggi = max(
            tertinggi,
            (len(milik & lawan) / len(milik | lawan)) / CONCEPT_REPEAT_LIMIT,
        )

    return tertinggi


def incomplete_tail_score(teks: str, brand: str = "") -> float:
    """
    Apakah judul ini berakhir di potongan yang menggantung.

    Yang diperiksa potongan TERAKHIR sesudah koma, dan cuma kalau
    komanya memang ada. Judul tanpa koma tidak pernah tersentuh -
    itu penting, karena judul yang benar memang sering berakhir di
    kata benda ("... Pilihan Slot Online Terbaru") dan aturan
    "tidak boleh berakhir kata benda" akan salah untuk hampir semua
    judul yang bagus.

    Yang salah pada judul yang dikeluhkan bukan jenis kata di
    ujungnya melainkan bahwa ada koma yang menjanjikan kelanjutan,
    lalu kelanjutannya cuma satu kata yang tidak terikat ke apa pun.
    Lihat TAIL_MIN_WORDS untuk angkanya dan dari mana ia diukur.
    """
    janji = title_promise(teks, brand)

    if "," not in janji:
        return 0.0

    potong = [bagian.strip() for bagian in janji.split(",") if bagian.strip()]

    if len(potong) < 2:
        return 0.0

    ekor = potong[-1].split()

    if len(ekor) >= TAIL_MIN_WORDS:
        return 0.0

    # Makin pendek ekornya makin berat. Satu kata di ujung - yang
    # benar-benar terbit - mendapat nilai penuh.
    return TAIL_MIN_WORDS / max(len(ekor), 1) / TAIL_MIN_WORDS * 2


def opening_words(
    teks: str,
    brand: str = "",
    jumlah: int = OPENING_WORDS,
    keyword: str = "",
):
    """
    Kata isi pertama sebuah teks, sesudah nama situs dan keywordnya.

    Nama situs dibuang lebih dulu karena ia memang sama di setiap
    judul untuk brand yang sama - bentuknya sudah dipatok pengguna -
    jadi membandingkannya cuma menyatakan yang sudah pasti.

    TANDA PISAHNYA ikut dibuang, dan itu bukan kerapian. Dipakai
    bare_style saja, yang tersisa sesudah nama situs dicabut adalah
    tanda pisah yang dipasang enforce_title_shape - dan tanda itu sama
    untuk SETIAP judul brand ini, karena title_separator memilihnya
    dari benih yang tetap.

    Akibatnya terukur pada lima generate 16 Agustus 2026: kelima judul
    berkata-pertama "#", jadi title_shape kelimanya (False, "#") dan
    shape_repeat_score berbunyi 1,00 untuk semua pasangan - termasuk
    pasangan yang kata pertamanya benar-benar berbeda (Daftar,
    Bareng-bareng, Tampilkan, Grup, Lindungi). Penaltinya membengkak
    dan permintaan ulang berangkat tanpa satu pun alasan yang benar.
    """
    # Keyword ikut dicabut, dengan alasan yang persis sama seperti
    # nama situs di atas: ia WAJIB ada di setiap judul dan setiap
    # deskripsi, jadi membandingkannya cuma menyatakan yang sudah
    # pasti.
    #
    # Untuk deskripsi ini bukan penghalusan melainkan perbaikan
    # kesalahan, dan kesalahannya membuat penilainya bertengkar
    # dengan aturannya sendiri. meta_rules_block MEWAJIBKAN deskripsi
    # dibuka nama situs lalu satu kata kerja dari daftar tertutup -
    # menyediakan, menghadirkan, menyajikan, menawarkan - dan
    # keywordnya hampir selalu menyusul di kata berikutnya. Jadi tiga
    # kata isi pertama setiap deskripsi berbentuk
    # "<kata kerja> <keyword>", dan dua di antaranya dipatok aturan.
    #
    # Terukur pada dua deskripsi yang isinya benar-benar berbeda:
    #
    #   ABECE menghadirkan togel online yang mudah diakses ...
    #   ABECE menyajikan togel online yang cair ke rekening ...
    #
    #     sebelum : 1,00  (dua dari tiga kata sama - "togel online")
    #     sesudah : 0,00
    #
    # Nilai 1,00 itu berarti ditolak, dan yang ditolak bukan
    # pengulangan melainkan kepatuhan pada aturan di prompt. Model
    # menghabiskan seluruh jatah permintaan ulangnya di pemeriksaan
    # yang tidak bisa dimenangkan siapa pun, lalu yang terbit
    # "kandidat yang paling sedikit bermasalah" - dipilih oleh nilai
    # yang seluruhnya derau. Itu terbaca di setiap run sebagai
    # peringatan "deskripsi mengulang ... walau sudah diminta 3 kali".
    #
    # Judul ikut memakai jalur yang sama dan ikut membaik karena
    # alasan yang sama. Prinsipnya sudah lama berdiri di berkas ini -
    # title_echo_score dan bare_title dua-duanya mengukur DI LUAR
    # nama situs dan keyword - dan yang di sini cuma belum ikut.
    bersih = normalize(title_promise(teks, brand))

    if str(keyword or "").strip():
        bersih = normalize(bare_title(bersih, keyword, brand))

    kata = [
        satu
        for satu in bersih.split()
        if satu and satu not in CONTENT_STOPWORDS
    ]

    return tuple(kata[:jumlah])


def opening_repeat_score(
    teks: str,
    lain: list[str],
    brand: str = "",
    keyword: str = "",
) -> float:
    """
    Apakah teks ini membuka dengan kata-kata yang sama seperti yang lain.

    Ini penyaring yang menutup keluhan "generate kedua cuma ganti satu
    kata". echo_score sudah membandingkan pembuka, tapi ia mengukur
    pembuka SEPANJANG ACUANNYA - untuk deskripsi 170 karakter itu
    berarti hampir seluruh kalimat, dan dua deskripsi yang membuka
    sama lalu berbeda seluruhnya lolos dengan nilai rendah.

    Terukur: "Cari slot gacor di WAYANGPLAY. Mulai bermain sekarang
    ..." dan "Cari slot gacor di WAYANGPLAY dengan pengalaman ..."
    mendapat echo_score 0,62 - di bawah ambang - padahal tiga kata
    pertamanya sama persis dan itulah yang dibaca orang di hasil
    pencarian sebelum memutuskan mengklik.
    """
    milik = opening_words(teks, brand, keyword=keyword)

    if not milik:
        return 0.0

    tertinggi = 0.0

    for satu in lain or []:
        lawan = opening_words(satu, brand, keyword=keyword)

        if not lawan:
            continue

        sama = sum(1 for a, b in zip(milik, lawan) if a == b)

        tertinggi = max(
            tertinggi,
            (sama / max(len(milik), len(lawan))) / OPENING_LIMIT,
        )

    return tertinggi


def bare_title(teks: str, keyword: str = "", brand: str = "") -> str:
    """
    Judul tanpa nama situs dan tanpa keywordnya.

    Dipakai membandingkan dua judul untuk halaman yang sama. Keduanya
    WAJIB memuat nama situs dan keyword - itu bentuk yang diminta
    pengguna - jadi membandingkan judul mentah berarti menghitung
    kesamaan yang sudah dipastikan sebelum satu kata pun ditulis.
    """
    sisa = title_promise(teks, brand)

    kunci = " ".join(str(keyword or "").split())

    if kunci:
        sisa = re.sub(re.escape(kunci), " ", sisa, flags=re.I)

        # Kata keyword yang terpisah-pisah ikut dicabut. Judul rutin
        # menulis "Slot Gacor" di tengah kalimat lain, dan yang tersisa
        # sesudah frasa utuhnya dicabut masih memuat potongannya.
        for potong in re.findall(r"\w+", kunci):
            sisa = re.sub(
                r"(?<!\w){}(?!\w)".format(re.escape(potong)),
                " ",
                sisa,
                flags=re.I,
            )

    return " ".join(sisa.split())


def title_echo_score(teks: str, lain, keyword: str = "", brand: str = "") -> float:
    """
    Seberapa jauh judul ini mengulang judul lain, DI LUAR brand dan
    keywordnya.

    Ini perbaikan untuk cacat yang sudah berdiri sejak penolak judul
    kembar dipasang, dan yang baru terlihat waktu penaltinya dipecah
    per alasan 16 Agustus 2026: tiga judul yang benar-benar berbeda -

      WAYANGPLAY # Keamanan Akun Data Anda Dilindungi Saat Main Slot Gacor
      WAYANGPLAY # Hadiah Spesial dan Promo Slot Gacor untuk Pemain Baru
      WAYANGPLAY # Langkah Pertama Memulai Slot Gacor untuk Pemula

    - ketiganya mendapat nilai yang SAMA PERSIS, 1,04, dan ketiganya
    ditolak. Angkanya bisa diturunkan sampai ke sebabnya: tiga kata
    yang sama (nama situs, "slot", "gacor") dari delapan kata acuan =
    0,375; dibagi ECHO_COVERAGE 0,6 lalu dibagi TITLE_REPEAT_LIMIT 0,6
    = 1,04.

    Jadi yang diukur bukan pengulangan melainkan keharusan: setiap
    judul WAJIB memuat nama situs dan keyword, dan penaltinya
    menghukum mereka karena memenuhinya.

    Yang dibandingkan sekarang sisa judulnya - bagian yang memang
    pilihan penulisnya. Pengulangan yang sungguhan tetap tertangkap:
    dua judul yang sama-sama bicara "menang dibayar" tetap berbagi
    kata itu sesudah brand dan keywordnya dicabut.
    """
    milik = bare_title(teks, keyword, brand)

    if not milik:
        return 0.0

    return max(
        (
            echo_score(milik, bare_title(satu, keyword, brand))
            for satu in (lain or [])
            if bare_title(satu, keyword, brand)
        ),
        default=0.0,
    )


def keyword_missing_score(teks: str, keyword: str) -> float:
    """
    Apakah keywordnya benar-benar ada di judul ini.

    Lubang yang paling memalukan dari seluruh daftar, dan baru
    ketahuan 16 Agustus 2026 waktu judul ini terbit dengan penalti
    0,00:

      WAYANGPLAY # Slot gac Provinsi dari ponsel untuk Android

    "Slot gac" bukan "slot gacor". Judulnya mengikuti sudutnya dengan
    benar, panjangnya pas, tidak menumpuk penyangat, tidak mengulang
    apa pun - dan tidak memuat kata yang seluruh halaman ini dibuat
    untuk memenanginya. Tidak satu pun pemeriksa keberatan, karena
    tidak satu pun pernah menanyakannya.

    keyword_covered dipakai apa adanya, termasuk kelonggarannya untuk
    tahun dan kata penunjuk waktu - lihat OPTIONAL_KEYWORD_WORDS.
    Judul yang menulis "slot gacor" untuk keyword "slot gacor 2026"
    tetap terhitung memuatnya, dan itu memang benar.
    """
    if not str(keyword or "").strip() or not str(teks or "").strip():
        return 0.0

    return 0.0 if keyword_covered(teks, keyword) else 1.0


# Aksara yang tidak pernah sah di halaman Indonesia maupun Thai.
#
# Bukan daftar "aksara yang diizinkan", melainkan daftar yang DILARANG,
# dan bedanya disengaja. Daftar izin harus menyebutkan setiap blok
# Unicode yang boleh lewat - huruf beraksen, tanda mata uang, tanda
# baca tipografis - dan setiap yang lupa disebut jadi salah tuduh.
# Daftar larangan cuma perlu menyebutkan yang benar-benar salah.
#
# Aksara Thai TIDAK ada di sini, di kedua zona. Untuk halaman Thai ia
# jelas sah; untuk halaman Indonesia, satu huruf Thai yang nyasar belum
# pernah terukur sekali pun, dan menambahkannya berarti menaruh risiko
# salah tuduh di jalan yang tidak punya bukti membutuhkannya.
FOREIGN_SCRIPT = re.compile(
    "["
    "　-〿"   # tanda baca CJK
    "぀-ゟ"   # hiragana
    "゠-ヿ"   # katakana
    "㐀-䶿"   # CJK tambahan A
    "一-鿿"   # CJK
    "豈-﫿"   # CJK bentuk sepadan
    "＀-￯"   # bentuk lebar dan setengah lebar
    "ᄀ-ᇿ"   # jamo Hangul
    "가-힯"   # suku kata Hangul
    "Ѐ-ӿ"   # Kiril
    "֐-׿"   # Ibrani
    "؀-ۿ"   # Arab
    "ऀ-ॿ"   # Devanagari
    "]"
)


def foreign_script_chars(
    teks: str,
    keyword: str = "",
    brand: str = "",
) -> list[str]:
    """
    Huruf beraksara asing yang tidak berasal dari masukan pengguna.

    Ini bug model, bukan bug gaya, dan bentuknya khas: qwen3:4b sesekali
    memilih satu token beraksara Han di tengah kata Indonesia. Terukur
    16 Agustus 2026 di deskripsi yang benar-benar terbit:

      Sumber data RTP slot gac或 di WAYANGPLAY diambil dari penyedia

    "slot gac或" bukan salah pilih kata melainkan token yang salah, dan
    tidak satu pun pemeriksa mutu bisa melihatnya: panjangnya pas,
    sudutnya benar, tidak ada klaim, tidak mengulang apa pun.

    Yang dikembalikan hurufnya, bukan cuma "ada atau tidak", supaya
    permintaan ulang bisa menyebutkan yang salah - lihat head_reasons.

    Huruf yang memang ada di keyword atau nama situs TIDAK pernah
    dihitung. Pengguna berhak memberi nama situs beraksara apa pun, dan
    menolak jawaban karena memuat nama yang dimintanya sendiri adalah
    penolakan yang tidak akan pernah bisa dipenuhi.
    """
    isi = str(teks or "")

    if not isi:
        return []

    milik_pengguna = set(f"{keyword or ''} {brand or ''}")

    return [
        huruf
        for huruf in dict.fromkeys(FOREIGN_SCRIPT.findall(isi))
        if huruf not in milik_pengguna
    ]


def script_leak_score(
    teks: str,
    keyword: str = "",
    brand: str = "",
) -> float:
    """
    Apakah teks ini memuat huruf beraksara asing yang bukan dari masukan.

    Satu huruf sudah cukup untuk menolak, dan sengaja tidak dibuat
    bertingkat menurut jumlahnya: satu huruf Han di tengah kata
    Indonesia bukan "agak salah", ia kata yang rusak.

    Ditolak dan diminta ulang, BUKAN dibersihkan. Membuang hurufnya
    menyisakan "slot gac", yang lebih buruk daripada teks aslinya
    karena kerusakannya jadi tidak kelihatan - dan tidak ada cara
    menebak kata apa yang seharusnya ada di situ.
    """
    return 1.0 if foreign_script_chars(teks, keyword, brand) else 0.0


def opening_phrase(judul: str, brand: str = "", kata: int = 3) -> str:
    """
    Beberapa kata pertama JANJI sebuah judul, tanpa nama situs dan
    tanpa tanda pisahnya.

    Dipakai memberi tahu model apa yang tidak boleh dipakai membuka
    lagi. Diambil mentah dari judul utuh, yang terbawa justru tanda
    pisah yang dipasang NEIIU sendiri - terukur, larangan yang terbit
    berbunyi 'jangan membuka dengan "# Slot gacor"', dan tanda itu
    memang tidak pernah ditulis model.
    """
    janji = title_promise(judul, brand)

    return " ".join(janji.split()[:kata])


def script_reason(peran: str, huruf: list[str]) -> str:
    """
    Perintah menulis ulang satu peran yang kemasukan aksara asing.

    Hurufnya disebutkan satu per satu, bukan diringkas jadi "ada huruf
    asing". Model kecil tidak bisa mencari sendiri huruf mana yang
    dimaksud di dalam kalimatnya, dan perbaikan yang tidak menunjuk
    tempatnya biasanya kembali dengan kalimat baru yang cacatnya sama.

    Yang diminta MENGGANTI KATANYA, bukan membuang hurufnya. "slot
    gac或" tanpa hurufnya jadi "slot gac", yang sama rusaknya tapi
    tidak lagi terlihat rusak.
    """
    return (
        f"- {peran}: AKSARA ASING.\n"
        f"  Kemarin ada huruf yang bukan huruf Latin maupun Thai: "
        + " ".join(huruf)
        + ".\n  Tulis ulang KATA tempat huruf itu berada dengan kata "
        "yang utuh. Jangan cuma menghapus hurufnya - yang tersisa "
        "sesudahnya bukan kata."
    )


def title_reasons(
    judul: str,
    keyword: str,
    brand: str,
    riwayat: list[str] | None = None,
) -> list[str]:
    """
    Alasan sebuah judul ditolak, sebagai kalimat yang bisa dikerjakan.

    Pasangan title_penalty: yang itu menjawab "seberapa buruk", yang
    ini "buruknya di sebelah mana". Angka saja tidak bisa dikirim balik
    ke model - "nilaimu 1,5" bukan perintah yang bisa diikuti siapa
    pun.

    Tiap alasan diperiksa SENDIRI-SENDIRI, bukan disimpulkan dari nilai
    gabungannya. Yang dikembalikan cuma yang benar-benar dilanggar, dan
    itu bukan kerapian: model 4B yang dikirimi enam perintah perbaikan
    sekaligus mengerjakan satu dan mengabaikan sisanya, dan perbaikan
    yang menyuruh membetulkan hal yang tidak salah membuat jawaban
    kedua lebih buruk daripada yang pertama.

    Dipakai setiap pemanggil yang meminta judul ulang;
    jalur panjang memanggilnya di putaran permintaan ulang judul.

    Kenapa jalur panjang perlu ini, dengan angkanya. Terukur end-to-end
    17 Agustus 2026, job 95:

        yang terbit : WAYANGPLAY # RTP Slot Gacor Data, Sumber, dan Perbarui
        clause_pile     1,50   (dua koma; yang diperbolehkan satu)
        incomplete_tail 1,00   (ekor "dan Perbarui" cuma dua kata)
        ditolak 3 dari 3 percobaan

    dan yang dikatakan ke model di tiap permintaan ulang cuma satu
    kalimat tetap: "judulnya mengulang judul halaman sebelumnya,
    menyalin contoh gayanya, menumpuk kata penyangat, atau mengulang
    keywordnya" - tidak satu pun menyebut koma menumpuk maupun ekor
    menggantung, yang justru dua alasan sebenarnya. Model diminta
    ulang tiga kali tanpa pernah diberi tahu apa yang salah.
    """
    nama = str(brand or "").strip()
    lama = [str(x) for x in (riwayat or []) if str(x).strip()]

    baris: list[str] = []

    if not str(judul or "").strip():
        return baris

    if filler_share_score(judul, keyword, nama) >= 1.0:
        baris.append(
            "- title: kemarin terlalu banyak kata penyangat "
            "(\"terbaik\", \"terpercaya\", \"terbaru\", \"resmi\", "
            "\"aman\", \"cepat\"). Ganti dengan KETERANGAN yang "
            "benar-benar menerangkan sesuatu: untuk siapa, dipakai "
            "kapan, apa yang tidak perlu disiapkan, berapa lama."
        )

    if vague_title_score(judul, keyword, nama) >= 1.0:
        baris.append(
            "- title: TIDAK MENYEBUT SATU HAL PUN YANG NYATA.\n"
            "  Di luar nama situs dan keyword, judul kemarin cuma "
            "berisi kata rasa - \"pengalaman\", \"bermain\", "
            "\"terbaik\". Sebut satu hal yang benar-benar bisa "
            "dibuka atau dicari orang, misalnya RTP live, bocoran "
            "pola, link alternatif, login anti blokir, bonus new "
            "member, deposit QRIS, atau withdraw. Pilih sendiri yang "
            "paling pas dengan halaman ini - yang penting judulnya "
            "menunjuk sesuatu, bukan cuma memuji."
        )

    if clause_pile_score(judul, nama) >= 1.0:
        baris.append(
            "- title: kemarin beberapa janji yang didempetkan koma, "
            "bukan satu judul yang utuh. Pilih SATU janji dan "
            "buang sisanya - judul dibaca dalam satu tarikan napas, "
            "dan pembaca hasil pencarian berhenti di potongan "
            "pertama."
        )

    if keyword_missing_score(judul, keyword) >= 1.0:
        baris.append(
            "- title: KEYWORD HILANG ATAU RUSAK.\n"
            f"  Judul kemarin tidak memuat \"{keyword}\" utuh. "
            "Tulis keywordnya persis seperti itu, satu kali, tanpa "
            "dipenggal dan tanpa diganti kata lain."
        )

    if keyword_repeat_score(judul, keyword, TITLE_KEYWORD_LIMIT) >= 1.0:
        baris.append(
            f"- title: keyword \"{keyword}\" kemarin ditulis lebih "
            "dari sekali. Tulis sekali saja, lalu pakai sisa "
            "ruangnya untuk hal yang belum disebut."
        )

    if opening_repeat_score(judul, lama, nama) >= 1.0:
        awal = opening_phrase(judul, nama)

        dilarang = f" Jangan membuka dengan \"{awal}\"." if awal else ""

        baris.append(
            "- title: PEMBUKA BERULANG.\n"
            "  Judul kemarin membuka dengan kata yang sama seperti "
            "judul yang sudah keluar untuk topik ini."
            + dilarang
            + " Pakai susunan kalimat yang lain."
        )

    if incomplete_tail_score(judul, nama) >= 1.0:
        ekor = [
            bagian.strip()
            for bagian in title_promise(judul, nama).split(",")
            if bagian.strip()
        ]

        contoh = (
            f" Jangan berakhir dengan potongan seperti \"{ekor[-1]}\"."
            if len(ekor) > 1
            else ""
        )

        baris.append(
            "- title: KALIMAT BELUM SELESAI.\n"
            "  Judul kemarin berakhir dengan potongan yang "
            "menggantung - kata di ujung sesudah koma, tanpa apa "
            "pun yang mengikatnya ke kalimat sebelumnya."
            + contoh
            + " Tulis judul yang kalimatnya SELESAI. Kalau kehabisan "
            "bahan, berhenti lebih pendek; jangan menempelkan kata di "
            "ujungnya."
        )

    # Sudut halaman tidak lagi diperiksa maupun dikirim balik.
    #
    # Blok yang berdiri di sini dulu berbunyi "SALAH SUDUT - judul kali
    # ini WAJIB memuat salah satu dari: link, login, masuk". Ia dicabut
    # bersama kedua ukuran sudut di title_penalty; menyuruh model
    # membetulkan sesuatu yang sudah tidak dinilai lagi cuma memakan
    # jatah perbaikan yang benar-benar berlaku - dan model 4B memang
    # mengerjakan satu perintah lalu mengabaikan sisanya.

    if concept_repeat_score(judul, lama, keyword, nama) >= 1.0:
        baris.append(
            "- title: GAGASAN BERULANG.\n"
            "  Judul kemarin mengatakan hal yang sama dengan judul "
            "yang sudah keluar, cuma kata-katanya digeser. Pakai "
            "gagasan yang lain - bukan sinonim dari gagasan yang "
            "sama - sambil tetap memakai keyword dan nama situs "
            "yang sama."
        )

    if shape_repeat_score(judul, lama, nama) >= 1.0:
        baris.append(
            "- title: kemarin bentuknya sama persis dengan judul "
            "sebelumnya - sama-sama bertanya dan dibuka kata yang "
            "sama. Ganti bentuknya, bukan cuma kata-katanya."
        )

    nyasar = foreign_script_chars(judul, keyword, nama)

    if nyasar:
        baris.append(script_reason("title", nyasar))

    return baris


def title_repair_note(alasan: list[str], ditolak: list[str]) -> str:
    """
    Alasan penolakan sebagai blok yang ditempelkan ke prompt judul.

    Kosong kalau tidak ada yang dilanggar, dan itu yang membuat
    permintaan ulang untuk judul yang sudah layak berangkat dengan
    prompt yang sama persis seperti semula - tidak ada perintah
    perbaikan untuk hal yang tidak salah.

    Judul yang barusan ditolak ikut disebutkan supaya kandidat
    berikutnya tidak mendarat di kalimat yang sama. Tanpa itu, model
    memperbaiki cacat yang disebutkan lalu mengembalikan susunan yang
    sama dengan satu kata digeser.
    """
    if not alasan:
        return ""

    blok = "\n\nJUDUL KEMARIN DITOLAK. Perbaiki yang ini saja:\n"
    blok += "\n".join(alasan)

    bekas = [str(x).strip() for x in (ditolak or []) if str(x).strip()]

    if bekas:
        blok += "\n\nJudul yang SUDAH ditolak di permintaan ini:\n"
        blok += "\n".join(f"- {teks}" for teks in bekas)
        blok += (
            "\nJangan menulis ulang salah satunya dengan kata yang "
            "digeser. Yang diminta judul yang susunannya lain."
        )

    return blok


def title_shape(teks: str, brand: str = "") -> tuple:
    """
    Bentuk retoris sebuah judul, sebagai penanda yang bisa dibandingkan.

    Dua hal: apakah ia bertanya, dan kata isi pertamanya. Keduanya yang
    paling menentukan kesan "judul ini sama seperti yang tadi" -
    pembaca hasil pencarian membaca beberapa kata pertama, dan tanda
    tanya mengubah seluruh nadanya.

    Bertanya sengaja ikut. Dari 120 judul milik pengguna cuma 2 (2%)
    memakai tanda tanya, jadi dua judul bertanya berturut-turut untuk
    topik yang sama bukan kebetulan melainkan model yang tersangkut di
    satu cetakan.
    """
    janji = title_promise(teks, brand)

    pembuka = opening_words(teks, brand, 1)

    return ("?" in janji, pembuka[0] if pembuka else "")


def shape_repeat_score(teks: str, lain, brand: str = "") -> float:
    """
    Apakah judul ini memakai bentuk retoris yang sama seperti judul lain.

    Nilai penuh hanya kalau KEDUANYA sama - bertanya sama-sama dan
    kata pertamanya sama. Salah satu saja tidak cukup: banyak judul
    yang benar kebetulan mulai dengan kata yang sama, dan judul
    bertanya yang isinya lain sama sekali tetap judul yang lain.

    Terukur pada dua judul yang benar-benar terbit berturut-turut:

      WAYANGPLAY # Kamu yang Cari Slot Gacor?, Hasil Menang Dibayar
      WAYANGPLAY # Kamu Cari Slot Gacor? Bisa Dibuka dari HP, Kemenangan

    Dua-duanya bertanya, dua-duanya dibuka kata "cari". Pembanding per
    kata melihat keduanya cukup berbeda (irisan gagasannya 0,143);
    pembacanya melihat satu judul yang ditulis dua kali.
    """
    milik = title_shape(teks, brand)

    if not milik[0] and not milik[1]:
        return 0.0

    for satu in lain or []:
        lawan = title_shape(satu, brand)

        if milik == lawan:
            return 1.0

    return 0.0


def title_penalty(
    teks: str,
    keyword: str,
    brand: str,
    riwayat: list[str] | None = None,
    contoh: list[str] | None = None,
) -> float:
    """
    Alasan sebuah judul ditolak, semuanya dinyatakan dalam satu angka.

    Satu tempat untuk setiap pemanggil -
    dengan alasan yang sama seperti enforce_title_shape dipakai
    bersama: dua daftar alasan yang berdiri sendiri-sendiri akan
    bergeser tanpa yang lain tahu, dan gejalanya judul yang lolos di
    satu jalur lalu ditolak di jalur lain dari perintah yang sama.

    Nilai di bawah 1.0 berarti judulnya boleh terbit. Di atasnya
    berarti diminta ulang, dan kalau permintaan ulangnya habis, yang
    dipakai kandidat dengan nilai terkecil.
    """
    lama = [str(x) for x in (riwayat or []) if str(x).strip()]

    return max(
        # Mengulang judul halaman yang sudah pernah terbit - diukur di
        # LUAR nama situs dan keyword, yang wajib ada di dua-duanya.
        # Lihat title_echo_score.
        title_echo_score(teks, lama, keyword, brand) / TITLE_REPEAT_LIMIT,
        # Ekornya menumpuk kata penyangat.
        len(title_tail_pile(teks, keyword)) / (TITLE_TAIL_ALLOWED + 1),
        # Penyangatnya disebar rata, jadi tidak punya ekor yang bisa
        # dipotong - "Situs Slot Gacor Terbaik dan Terpercaya".
        filler_share_score(teks, keyword, brand),
        # Beberapa janji yang didempetkan koma, bukan satu janji utuh.
        clause_pile_score(teks, brand),
        # Berhenti di rasa tanpa menyebut satu topik pun yang bisa
        # ditunjuk - lihat vague_title_score.
        vague_title_score(teks, keyword, brand),
        # Berakhir di potongan menggantung sesudah koma.
        incomplete_tail_score(teks, brand),
        # Sudut halaman TIDAK diperiksa di sini, dan itu disengaja.
        #
        # Dulu ada dua ukuran lagi di daftar ini: satu menuntut judul
        # memuat kata dari daftar "wajib terasa" milik sudut yang
        # ditugaskan padanya, satu lagi menolaknya penuh kalau memuat
        # kata dari daftar "jangan jadi pokok". Keduanya dicabut atas
        # permintaan pengguna, dan alasannya kelihatan di judul yang
        # terbit karenanya:
        #
        #   WAYANGPLAY # RTP Slot Gacor Data, Sumber, dan Perbarui
        #
        # Judul itu bukan judul yang buruk karena modelnya kurang
        # pandai. Ia buruk karena PATUH: ia sedang mencentang daftar
        # kata yang disodorkan padanya, dan hasilnya terbaca persis
        # seperti daftar kata yang dicentang.
        #
        # Yang tinggal di daftar ini semuanya mengukur MUTU dan
        # PENGULANGAN - koma menumpuk, ekor menggantung, kata
        # penyangat, keyword dua kali, gagasan yang sama seperti
        # halaman sebelumnya. Tidak satu pun menuntut kosakata
        # tertentu hadir. Sudutnya diserahkan ke model, dan yang
        # menjaga halaman kedua tidak menyerupai halaman pertama
        # adalah concept_repeat_score beserta riwayat yang benar-benar
        # terbit - ukuran atas hasil, bukan daftar yang dibagikan di
        # muka.
        # Gagasannya mengulang judul sebelumnya, meskipun katanya
        # digeser.
        concept_repeat_score(teks, lama, keyword, brand),
        # Bentuk retorisnya sama: sama-sama bertanya, dibuka kata yang
        # sama.
        shape_repeat_score(teks, lama, brand),
        # Keywordnya ditulis lebih dari sekali di ruang 70 karakter.
        keyword_repeat_score(teks, keyword, TITLE_KEYWORD_LIMIT),
        # Keywordnya tidak ada sama sekali, atau terbit rusak.
        keyword_missing_score(teks, keyword),
        # Memuat huruf beraksara asing yang bukan dari masukan pengguna
        # - token yang salah, bukan kata yang salah pilih.
        script_leak_score(teks, keyword, brand),
        # Membuka dengan kata yang sama seperti judul sebelumnya,
        # meskipun sisanya berbeda.
        opening_repeat_score(teks, lama, brand, keyword),
        # Menyalin judul halaman sebelumnya, kosakatanya saja - diukur
        # di luar brand dan keyword, dengan alasan yang sama seperti
        # title_echo_score. bare_style sendirian cuma mencabut nama
        # situs, jadi "slot" dan "gacor" tetap ikut dihitung sebagai
        # kosakata yang disalin padahal keduanya wajib ada.
        style_copy_score(
            bare_title(teks, keyword, brand),
            [bare_title(satu, keyword, brand) for satu in lama],
            brand,
        ),
        # Menyalin contoh gaya yang diperlihatkan kepadanya.
        style_copy_score(teks, list(contoh or []), brand),
    )


def desc_opening_score(teks: str, brand: str) -> float:
    """
    Apakah deskripsi dibuka nama situsnya, seperti contoh pengguna.

    Keempat puluh contoh di knowledge/gaya_title_deskripsi.txt dibuka
    dengan cara yang sama persis: nama situs, lalu satu kata kerja
    yang menyatakan apa yang disediakannya - "menjamin", "menawarkan",
    "menyediakan", "adalah", "menyajikan". Tidak satu pun dibuka
    dengan menyapa pembaca.

    Yang terbit 21 Agustus 2026 dibuka "Kamu bisa mulai bermain slot
    online langsung dari HP", dan pengguna menyebutnya belum sesuai
    contoh. Bentuk pembuka inilah bedanya yang paling kasatmata, dan
    ia bisa diperiksa tanpa menebak-nebak selera.

    Cuma pembukanya yang diperiksa - enam kata pertama. Sisanya
    dibebaskan, karena di situlah contoh pengguna sendiri
    berbeda-beda.
    """
    nama = str(brand or "").strip()
    kalimat = " ".join(str(teks or "").split())

    if not nama or not kalimat:
        return 0.0

    pembuka = " ".join(kalimat.split()[:6])

    if normalize(nama) in normalize(pembuka):
        return 0.0

    return 1.05


# Sedekat apa ke plafon sebuah deskripsi terhitung "mentok jatah".
#
# Grammar llama.cpp menegakkan maxLength dengan menahan lalu memaksa
# tanda kutip penutup, jadi deskripsi yang kepanjangan tidak berhenti
# di tempat yang dipilih model - ia berhenti di karakter ke-180,
# di mana pun kalimatnya sedang berada. Terukur pada run 30 Agustus
# 2026, tepat 180 dari 180:
#
#     ... Tidak perlu persiapan khusus, cocok untuk pemain yang ingin.
#
# Dua karakter, bukan lebih. Jaraknya harus sempit supaya deskripsi
# yang kebetulan panjang dan utuh tidak ikut dirapikan; yang dicari
# cuma yang benar-benar menyentuh plafonnya.
DESC_CUT_SLACK = 2

# Sependek apa deskripsi masih boleh dipakai sesudah ekornya dibuang.
#
# Di bawah ini yang tersisa bukan deskripsi yang lebih pendek
# melainkan potongan, dan yang terlalu pendek ditambal repair_short_slots -
# jalur yang memang untuk itu. Kalau perapian di sini menghasilkan
# sisa sependek itu, teks aslinya dikembalikan apa adanya dan
# keputusannya diserahkan ke tahap yang punya bahan untuk menambal.
DESC_MIN_KEEP = 60


def finish_cut_description(teks, batas: int) -> str:
    """
    Merapikan deskripsi yang berhenti karena kehabisan jatah, bukan
    karena kalimatnya selesai.

    Ini bukan penilai dan tidak meminta ulang apa pun; ia membereskan
    kerusakan yang sudah pasti terjadi. Syaratnya satu dan diperiksa
    sebelum apa pun disentuh: panjangnya menyentuh plafon slot. Di
    luar itu teksnya dikembalikan utuh, huruf per huruf.

    Syarat itu yang membuat finish_clause boleh dipanggil dengan
    dipotong=True di sini. Parameter itu artinya "teks ini memang baru
    dipotong", dan ia membuka perapian yang jauh lebih berani -
    membuang seluruh anak kalimat terakhir, bukan cuma kata sambung di
    ujungnya. Dipakai atas teks yang TIDAK dipotong, keberanian itu
    salah: diuji atas deskripsi sehat "... saat situs utama diblokir,
    deposit QRIS tanpa potongan", ia memangkasnya jadi "... deposit
    QRIS" dan membuang keterangan yang benar. Di sini pemotongannya
    sudah dipastikan lebih dulu, jadi yang dibuang memang sisa
    potongan.
    """
    isi = " ".join(str(teks or "").split())

    if not isi or int(batas or 0) <= 0:
        return isi

    if len(isi) < int(batas) - DESC_CUT_SLACK:
        return isi

    rapi = finish_clause(isi, dipotong=True).rstrip(" ,;:-\u2013\u2014")

    if len(rapi) < DESC_MIN_KEEP or rapi == isi:
        return isi

    if rapi[-1:] not in ".!?":
        rapi += "."

    return rapi


# Frasa brosur: susunan yang panjang tapi tidak menyebut apa pun.
#
# Ini daftar yang berbeda dari VAGUE_WORDS dan dari STIFF_PHRASES,
# dan perbedaannya yang membuatnya perlu. VAGUE_WORDS berisi kata
# RASA satuan ("terbaik", "nyaman") dan dipakai memilah kosakata
# topik. STIFF_PHRASES berisi ragam bahasa resmi yang diturunkan jadi
# sehari-hari ("dengan demikian" jadi "jadi") dan ia penyapu - ia
# MENGGANTI teks. Yang di sini tidak diganti apa pun, karena tidak
# ada gantinya: frasa-frasa ini bukan cara yang kaku untuk mengatakan
# sesuatu, ia cara untuk tidak mengatakan apa-apa.
#
# Isinya diambil dari deskripsi yang benar-benar terbit, bukan
# dikarang. Dua run berturut-turut, dua-duanya memuat DUA frasa dari
# daftar ini:
#
#   run 1 : "Tidak perlu persiapan khusus, cocok untuk pemain yang ingin."
#   run 2 : "... dirancang khusus untuk pemain yang menginginkan keamanan"
#
# Ambangnya karena itu dua, bukan satu: satu frasa masih bisa berdiri
# di kalimat yang selebihnya menyebut sesuatu, dua sudah jadi
# kalimatnya sendiri.
BROCHURE_PHRASES = (
    "dirancang khusus",
    "dirancang agar",
    "dirancang untuk memberikan",
    "cocok untuk pemain yang",
    "cocok bagi pemain yang",
    "bagi pemain yang menginginkan",
    "untuk pemain yang menginginkan",
    "yang menginginkan kenyamanan",
    "pengalaman bermain yang",
    "kenyamanan bermain",
    "salah satu aspek",
    "menjadi salah satu",
    "turut memberikan",
    "memberikan kemudahan",
    "menghadirkan kenyamanan",
    "solusi tepat",
    "pilihan tepat bagi",
    "tanpa perlu persiapan khusus",
    "tidak perlu persiapan khusus",
    "dengan sistem yang dirancang",
    "demi kenyamanan",
    "guna memberikan",
)

BROCHURE_PATTERN = re.compile(
    r"(?<!\w)("
    + "|".join(re.escape(frasa) for frasa in BROCHURE_PHRASES)
    + r")(?!\w)",
    re.IGNORECASE,
)

# Berapa frasa brosur yang masih ditoleransi. Lihat BROCHURE_PHRASES
# untuk dari mana angka ini diukur.
BROCHURE_ALLOWED = 1


def brochure_score(teks) -> float:
    """
    Seberapa jauh sebuah deskripsi habis untuk frasa yang tidak
    menyebut apa pun.

    Kembaran filler_share_score, tapi untuk deskripsi dan dengan
    daftar sendiri - daftar milik judul isinya kata khas judul
    ("gacor", "maxwin", "jam") yang di dalam deskripsi justru
    keterangan yang benar, dan memakainya di sini akan menolak
    kalimat yang tidak salah apa-apa.

    Nilainya di atas 1.0 berarti deskripsinya diminta ulang. Ia tidak
    pernah membuang teks: yang terjadi model diminta menulis lagi, dan
    yang dipakai kandidat dengan nilai terkecil di antara semuanya -
    jadi permintaan tambahan tidak pernah membuat hasilnya lebih
    buruk daripada tanpa ukuran ini.
    """
    isi = str(teks or "")

    if not isi.strip():
        return 0.0

    jumlah = len(BROCHURE_PATTERN.findall(isi))

    if jumlah <= BROCHURE_ALLOWED:
        return 0.0

    return jumlah / (BROCHURE_ALLOWED + 1)


def description_penalty(
    teks: str,
    keyword: str,
    brand: str,
    judul: str = "",
    riwayat: list[str] | None = None,
    contoh: list[str] | None = None,
) -> float:
    """
    Alasan sebuah meta description ditolak, dalam satu angka.

    Susunannya sengaja mirip title_penalty, tapi ambang-ambangnya
    berbeda dan bedanya disengaja: deskripsi tiga kali lebih panjang
    daripada judul, jadi menyebut topiknya dua kali di situ wajar
    sementara di judul tidak.
    """
    lama = [str(x) for x in (riwayat or []) if str(x).strip()]

    acuan = ([judul] if str(judul or "").strip() else []) + lama

    return max(
        # Menuliskan ulang judulnya sendiri, atau deskripsi halaman
        # sebelumnya. Keduanya diukur dengan mesin yang sama.
        max((echo_score(teks, satu) for satu in acuan), default=0.0),
        # Keyword yang diulang-ulang sepanjang kalimat.
        keyword_repeat_score(teks, keyword, DESC_KEYWORD_LIMIT),
        # Nama situs yang disebut berkali-kali.
        brand_repeat_score(teks, brand, DESC_BRAND_LIMIT),
        # Membuka dengan kata yang sama seperti deskripsi sebelumnya.
        opening_repeat_score(teks, lama, brand, keyword),
        # Memuat huruf beraksara asing yang bukan dari masukan pengguna.
        # Ini SATU-SATUNYA tambahan ke penilai deskripsi, dan ia ada di
        # sini karena deskripsi tempat bugnya benar-benar terbit -
        # lihat foreign_script_chars.
        script_leak_score(teks, keyword, brand),
        # Menyalin contoh gaya yang diperlihatkan kepadanya.
        style_copy_score(teks, list(contoh or []), brand),
        # Tidak dibuka nama situsnya - lihat desc_opening_score.
        desc_opening_score(teks, brand),
        # Habis untuk frasa yang tidak menyebut apa pun.
        #
        # Judul sudah lama punya vague_title_score untuk ini;
        # deskripsi tidak punya apa-apa, dan itu terlihat di dua run
        # berturut-turut yang keduanya terbit tanpa satu permintaan
        # ulang pun atas alasan ini. Ukurannya BUKAN vague_title_score
        # yang dipakai ulang: yang itu menuntut satu kata dari
        # topic_vocabulary(), dan diuji atas kedua deskripsi tadi ia
        # meloloskan keduanya - "keamanan", "sistem", "pemain", dan
        # "proses" semuanya ada di dalam kosakata itu. Yang memisahkan
        # bukan ada-tidaknya kata topik melainkan frasa brosurnya.
        brochure_score(teks),
    )


def head_model(bagian: dict) -> str:
    """
    Model yang dipakai satu giliran: khusus kepala halaman, atau biasa.

    Giliran yang isinya HANYA peran bertekstunggal adalah giliran
    title dan meta_description - plan_batches memang memisahkannya
    supaya keduanya selesai sebelum satu paragraf pun ditulis, dan
    pemisahan itu yang membuat model khusus di sini murah: ia jalan
    sekali per run, atas jawaban 250 karakter.

    Permintaan ulang judul dan deskripsi ikut lewat sini, karena
    keduanya juga dikirim sebagai giliran berperan tunggal.

    AI_MODEL_HEAD yang dikosongkan mengembalikan AI_MODEL, jadi tanpa
    pengaturan tambahan tidak ada satu pun giliran yang berpindah
    model - lihat keterangannya di config.py.
    """
    if not bagian:
        return AI_MODEL

    if all(peran in SINGLE_ROLES for peran in bagian):
        return AI_MODEL_HEAD

    return AI_MODEL


# Nilai penalti yang sudah dianggap cukup baik untuk berhenti mencari.
#
# Lebih ketat daripada 1.0, dan itu yang membuat pemilihan kandidat
# benar-benar terjadi. Dengan ambang 1.0, judul pertama yang "tidak
# melanggar apa pun" langsung dipakai dan permintaan kedua tidak
# pernah berangkat - jadi yang ada bukan pemilihan kandidat melainkan
# penolakan yang kebetulan jarang kena.
#
# 0,7 menyisakan ruang untuk judul yang memang bersih (yang terukur
# duduk di 0,2-0,5) sambil tetap menantang judul yang menempel di
# batas. Harganya satu permintaan pendek tambahan, dan judul adalah
# hal pertama di urutan prioritas yang diminta pengguna.
HEAD_GOOD_ENOUGH = 0.7


# Peran bertekstunggal yang kekosongannya diminta ulang.
#
# Cuma dua, dan keduanya karena teks lamanya ikut dikirim sebagai
# cetakan bentuk. Peran tunggal lain tidak punya contoh yang bisa
# disalin, jadi kosongnya berarti model memang tidak menjawab - dan
# itu sudah tercatat sebagai peringatan tersendiri.
SINGLE_RETRY_ROLES = ("title", "meta_description")


# Sependek apa dua teks masih pantas diadu kemiripannya.
#
# Label dua huruf terlalu pendek untuk dinilai mirip - "ID" dan "TH"
# beririsan setengahnya tanpa berarti apa-apa - jadi yang sependek
# itu cuma diadu persamaan persis.
DISTINCT_MIN_CHARS = 4

# Seberapa mirip dua label sebelum dihitung kembar.
NEAR_RATIO = 0.86


def render_form(teks: str, jatah: int = 0, role: str = "") -> str:
    """
    Bentuk sebuah teks sebagaimana ia akan terbaca di slotnya.

    Dibandingkan mentah-mentah, dua label bisa terlihat berbeda
    padahal yang terbit sama. Terukur pada halaman Thai terbit: empat
    belas tautan footer berbunyi "ทุกการฝากถอนที่ไม่ต้องรอ",
    "ทุกการฝากถอนที่ไม่ต้อ", dan "ทุกการฝากถอนที่ไม่ต้องกรอก" -
    tiga bunyi berbeda di data, satu kalimat yang sama di layar,
    karena masing-masing dipotong di jatah slotnya sendiri.

    Karena itu yang diadu bentuk POTONGANNYA, bukan teks utuhnya.

    Yang memotong di sini clean_line - pemotong yang SAMA dengan yang
    dipakai build_edits waktu teksnya benar-benar dipasang, bukan
    tiruannya. Iris karakter biasa sempat dipakai di sini, dan
    bedanya bukan teoretis: jatah 40 kolom diiris di 46 karakter,
    sehingga dua judul yang berpisah baru di ekor yang dibuang lolos
    sebagai dua bunyi berbeda lalu terbit sebagai satu bunyi yang
    sama. Menyalin logika potongnya ke sini berarti dua tempat yang
    harus diingat setiap kali aturan memotong berubah; memanggilnya
    berarti keduanya tidak akan pernah berselisih lagi.

    "jatah" bersatuan KOLOM, bukan karakter - sama seperti
    slot["budget"]. Untuk spec yang sudah dilebarkan scale_spec,
    yang dikirim ke sini harus "columns", bukan "budgets".
    """
    bersih = " ".join(str(teks or "").split())

    if not bersih:
        return ""

    if jatah and jatah > 0:
        # Pertanyaan yang tidak muat dikembalikan kosong oleh
        # clean_line, dan kosong tidak bisa diadu dengan apa pun.
        # Untuk keperluan DI SINI yang dicari cuma bentuk terbacanya,
        # jadi teks utuhnya yang dipakai kalau pemotongnya menyerah.
        bersih = clean_line(bersih, int(jatah), role) or bersih

    return " ".join(bersih.split()).casefold()


def slot_widths(rule: dict) -> list[int]:
    """
    Jatah tiap slot dalam kolom tampilan.

    "columns" dipasang scale_spec untuk zona beraksara bertumpuk, di
    mana "budgets" sudah dilebarkan jadi karakter supaya model dan
    JSON Schema bisa menghitungnya. Zona lain tidak dilebarkan sama
    sekali, jadi di sana keduanya memang angka yang sama.
    """
    return list(rule.get("columns") or rule.get("budgets") or [])


# Berapa kata pembuka yang sama sebelum dua teks dihitung kembar.
#
# Tujuh, dan angkanya diukur dari yang benar-benar terbit: dua
# paragraf yang berbagi "X7GAMING88 menyediakan akses langsung ke slot
# online" - tujuh kata - lalu berpisah di ujungnya. Ditaruh lebih
# rendah, paragraf yang dibuka nama situs plus satu kata kerja ikut
# terbuang, dan pengulangan sependek itu memang wajar.
SHARED_OPENING_WORDS = 7


def near_twins(satu: str, dua: str) -> bool:
    """
    Apakah dua teks ini akan terbaca sebagai label yang sama.

    Tiga ukuran, dari yang paling murah. Sama persis; yang satu
    pembuka yang lain - inilah bentuk yang paling sering terjadi,
    karena dua jawaban model yang berangkat dari kalimat yang sama
    berpisah baru di ujungnya; dan sisanya diadu kemiripan huruf.
    """
    if not satu or not dua:
        return False

    if satu == dua:
        return True

    pendek, panjang = sorted((satu, dua), key=len)

    if len(pendek) >= DISTINCT_MIN_CHARS and panjang.startswith(pendek):
        return True

    if len(pendek) < DISTINCT_MIN_CHARS * 2:
        return False

    # Pembuka yang sama panjangnya, meskipun ujungnya berpisah.
    #
    # Ini bentuk yang lolos dari ketiga ukuran di atas dan terbit di
    # halaman jadi - dua paragraf berdampingan:
    #
    #   X7GAMING88 menyediakan akses langsung ke slot online tanpa
    #   perlu verifikasi tambahan. ...
    #   X7GAMING88 menyediakan akses langsung ke slot online setelah
    #   proses daftar. ...
    #
    # Tujuh kata pertamanya sama persis. Yang satu bukan pembuka yang
    # lain karena keduanya diteruskan berbeda, dan kemiripan hurufnya
    # secara keseluruhan tidak sampai ke ambang - tapi pembaca
    # halaman membaca dua paragraf yang mengatakan hal yang sama.
    #
    # Dituntut TUJUH kata, bukan tiga atau empat: paragraf yang
    # dibuka nama situs plus satu kata kerja ("X7GAMING88
    # menyediakan") memang wajar berulang, dan membuang yang kedua
    # karena itu akan membuang tulisan yang benar.
    kata_satu = satu.split()
    kata_dua = dua.split()

    sama = 0

    for kiri, kanan in zip(kata_satu, kata_dua):
        if kiri != kanan:
            break

        sama += 1

    if sama >= SHARED_OPENING_WORDS:
        return True

    return SequenceMatcher(None, satu, dua).ratio() >= NEAR_RATIO


def duplicate_slots(spec: dict, isi: dict) -> dict[str, list[int]]:
    """
    Posisi mana saja yang mengulang bunyi posisi lain, per peran.

    Dipisahkan dari lubang kosong supaya bisa dihitung dan dilaporkan
    sendiri, tapi keduanya bermuara ke tempat yang sama: gap_spec
    meminta ULANG persis posisi ini saja, bukan seluruh halaman.

    Yang pertama muncul dibiarkan, yang sesudahnya dihitung kembar.
    Dengan begitu jawaban yang sudah bagus tidak pernah dibuang untuk
    diganti jawaban yang belum tentu lebih baik.

    Pengulangan yang MEMANG dikehendaki template tidak dihitung.
    Kalau dua slot berangkat dari teks asal yang sama, template itu
    sendiri yang menuliskan bunyi yang sama di dua tempat - dan teks
    barunya pantas sama juga. Peran biasa sudah digabung per bunyi di
    derive_spec, jadi syarat ini yang menjaga peran berpasangan, yang
    tidak digabung.
    """
    kembar: dict[str, list[int]] = {}

    for role, rule in spec.items():
        if role not in DISTINCT_ROLES or role not in LIST_ROLES:
            continue

        ada = isi.get(role) or []
        jatah = slot_widths(rule)
        contoh = list(rule.get("samples") or [])

        dipakai: list[tuple[str, str]] = []
        ulang: list[int] = []

        for index in range(int(rule.get("count") or 0)):
            teks = str(ada[index]).strip() if index < len(ada) else ""

            if not teks:
                continue

            bentuk = render_form(
                teks, jatah[index] if index < len(jatah) else 0, role
            )
            asal = contoh[index] if index < len(contoh) else ""

            cocok = False

            for bentuk_lain, asal_lain in dipakai:
                if not near_twins(bentuk, bentuk_lain):
                    continue

                if (
                    asal
                    and asal_lain
                    and normalize(asal) == normalize(asal_lain)
                ):
                    continue

                cocok = True
                break

            if cocok:
                ulang.append(index)
                continue

            dipakai.append((bentuk, asal))

        if ulang:
            kembar[role] = ulang

    return kembar


# Urutan peran waktu diadu SATU SAMA LAIN.
#
# Yang lebih dulu berdiri di daftar ini menang: kalimatnya dianggap
# yang sah, dan peran sesudahnya yang mengulangnya diminta ulang.
# Urutannya bukan selera - judul, deskripsi, dan H1 adalah tiga teks
# yang paling tidak boleh diganggu (keduanya terikat kontrak panjang
# dan bentuk), lalu isi badan dari yang paling menentukan alur.
CROSS_ROLE_ORDER = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "caption",
    "card_title",
)

# Kalimat yang lebih pendek dari ini tidak pernah diadu lintas peran.
#
# Diukur dalam karakter sesudah dirapikan. Kalimat pendek memang
# wajar berulang di halaman mana pun - "Daftar sekarang", "Gratis" -
# dan mengadukannya cuma membuang giliran model untuk perbaikan yang
# tidak pernah dikeluhkan siapa pun. Empat puluh kira-kira sepanjang
# satu klausa yang benar-benar membawa pernyataan.
CROSS_MIN_CHARS = 40

# Selisih panjang terjauh sebelum dua kalimat berhenti diadu.
#
# Penjaga ongkos, bukan aturan bahasa: kalimat yang panjangnya beda
# lebih dari ini tidak akan pernah lolos ambang kemiripan mana pun,
# jadi menghitung kemiripannya cuma menghabiskan waktu. Halaman
# dengan 45 caption dan 17 jawaban FAQ menghasilkan ribuan pasangan,
# dan seluruhnya dihitung tiap kali putaran perbaikan berjalan.
CROSS_LENGTH_SPREAD = 1.6


def split_sentences(teks: str) -> list[str]:
    """
    Memecah satu teks jadi kalimat, untuk diadu dengan kalimat lain.

    Dipisah di titik, tanda tanya, tanda seru, dan baris baru. Aksara
    Thai tidak memakai titik sebagai pengakhir kalimat, jadi teks Thai
    biasanya kembali utuh sebagai satu potongan - dan itu benar:
    yang diadu memang seluruh pernyataannya.
    """
    bersih = " ".join(str(teks or "").split())

    if not bersih:
        return []

    potong = [
        bagian.strip()
        for bagian in re.split(r"(?<=[.!?])\s+", bersih)
        if bagian.strip()
    ]

    return potong or [bersih]


def cross_role_conflict(teks: str, role: str, isi: dict) -> bool:
    """
    Apakah teks ini mengulang kalimat milik peran LAIN di halaman ini.

    Dipakai waktu menimbang jawaban susulan: slot yang diminta ulang
    karena mengulang peran lain hanya boleh diganti oleh teks yang
    benar-benar berbeda, dan tanpa ukuran ini satu-satunya syarat
    yang berlaku adalah "yang lebih panjang menang" - syarat yang
    dibuat untuk lubang kependekan, bukan untuk lubang kembar.
    """
    kalimat = [
        satu
        for satu in split_sentences(teks)
        if len(satu) >= CROSS_MIN_CHARS
    ]

    if not kalimat:
        return False

    for peran_lain, nilai in (isi or {}).items():
        if peran_lain == role or peran_lain.startswith("_"):
            continue

        if peran_lain not in CROSS_ROLE_ORDER:
            continue

        daftar = nilai if isinstance(nilai, list) else [nilai]

        for lain in daftar:
            for lawan in split_sentences(str(lain or "")):
                if len(lawan) < CROSS_MIN_CHARS:
                    continue

                bentuk_lawan = " ".join(lawan.split()).casefold()

                for satu in kalimat:
                    bentuk = " ".join(satu.split()).casefold()

                    panjang = max(len(bentuk), len(bentuk_lawan))
                    pendek = min(len(bentuk), len(bentuk_lawan))

                    if pendek * CROSS_LENGTH_SPREAD < panjang:
                        continue

                    if near_twins(bentuk, bentuk_lawan):
                        return True

    return False


# Peran yang tiap butirnya harus DIBUKA berbeda, bukan cuma berbunyi
# berbeda.
#
# Cuma ulasan. Tiga ulasan yang sama-sama dibuka "Saya" terbaca
# sebagai tiga ulasan yang ditulis satu orang - dan memang begitu
# adanya. Peran lain tidak ikut: label menu dan judul kartu memang
# wajar berbagi kata pertama, dan menuntutnya berbeda cuma
# menghasilkan bahasa yang dipaksakan.
OPENING_DISTINCT_ROLES = ("review_text",)


def opening_word(teks: str) -> str:
    """
    Kata pembuka sebuah teks, tanpa tanda baca.
    """
    kata = str(teks or "").split()

    if not kata:
        return ""

    return kata[0].strip(EDGE_MARKS).casefold()


def same_opening_slots(spec: dict, isi: dict) -> dict[str, list[int]]:
    """
    Posisi yang dibuka kata yang sama dengan posisi sebelumnya.

    Aturannya sudah lama ada di prompt - "setiap ulasan memakai gaya
    bicara yang berbeda" - dan diikuti model kadang-kadang saja.
    Terukur pada halaman yang benar-benar terbit,
    output/wayangplay-slot-gacor-20260820_055457: ketiga ulasannya
    dibuka "Saya".

    Yang pertama dibiarkan, yang sesudahnya diminta ulang - sama
    seperti seluruh penolak kembar yang lain, jadi seluruh mesin
    perbaikan yang sudah ada langsung berlaku tanpa jalur baru.
    """
    kembar: dict[str, list[int]] = {}

    for role in OPENING_DISTINCT_ROLES:
        if role not in spec:
            continue

        ada = isi.get(role) or []

        if not isinstance(ada, list) or len(ada) < 2:
            continue

        dipakai: set[str] = set()
        ulang: list[int] = []

        for index in range(int(spec[role].get("count") or 0)):
            teks = str(ada[index]).strip() if index < len(ada) else ""
            pembuka = opening_word(teks)

            if not pembuka:
                continue

            if pembuka in dipakai:
                ulang.append(index)
            else:
                dipakai.add(pembuka)

        if ulang:
            kembar[role] = ulang

    return kembar


def all_duplicates(spec: dict, isi: dict) -> dict[str, list[int]]:
    """
    Kembar SEPERAN dan kembar LINTAS PERAN, dalam satu daftar.

    Dipakai putaran terakhir sebelum isinya diserahkan ke perender.
    Sebelum ini putaran itu memanggil duplicate_slots langsung, jadi
    ia buta terhadap bentuk yang justru paling sering dikeluhkan -
    dan buta di tempat yang paling menentukan, karena sesudahnya
    model sudah tidak dihubungi lagi.

    Terukur pada halaman yang benar-benar terbit,
    output/x7gaming88-slot-online-20260820_014659: dua kalimat
    deskripsi berdiri lagi sebagai paragraf pertama, utuh. Putaran
    gap di awal memang memeriksanya, tapi teks itu baru bertabrakan
    SESUDAH penyapu klaim dan penyeragaman angka mengubah keduanya.
    """
    hasil = {role: list(ulang) for role, ulang in duplicate_slots(spec, isi).items()}

    for peta in (cross_role_duplicates(spec, isi), same_opening_slots(spec, isi)):
        for role, ulang in peta.items():
            hasil[role] = sorted(set(hasil.get(role, [])) | set(ulang))

    return hasil


def cross_role_duplicates(spec: dict, isi: dict) -> dict[str, list[int]]:
    """
    Posisi mana saja yang mengulang KALIMAT milik peran lain.

    duplicate_slots hanya mengadu satu peran dengan dirinya sendiri:
    paragraf dengan paragraf, ulasan dengan ulasan. Itu menutup dua
    slot bersebelahan yang berbunyi sama, tapi tidak menutup bentuk
    yang paling sering dikeluhkan pembaca halaman - satu kalimat yang
    sama berdiri di tiga tempat berbeda, dan justru karena tempatnya
    berbeda tidak ada satu pun pemeriksaan yang keberatan.

    Terukur pada halaman yang benar-benar terbit 19 Agustus 2026,
    berkas output/siam123-slot-gacor-20260819_054058/index.html:

      meta description : "Pemain baru bisa daftar dengan QRIS
                          langsung, tanpa perlu verifikasi tambahan.
                          Setelah login, tampilan slot gacor sudah
                          update sebelum pagi hari."
      paragraf pertama : kalimat yang sama, dua-duanya, dengan satu
                         kata bertukar tempat.
      paragraf keempat : "Setelah login, tampilan slot gacor di
                          SIAM123 sudah update sebelum pagi hari."

    Yang diadu KALIMATNYA, bukan slotnya. Slot yang mengulang satu
    kalimat lalu meneruskan dengan tiga kalimat baru tidak pernah
    tertangkap ukuran kemiripan atas teks utuh - kemiripannya terlalu
    kecil - padahal kalimat yang diulang itu yang dibaca dua kali.

    Yang pertama berdiri dibiarkan; yang sesudahnya dihitung kembar.
    Urutannya CROSS_ROLE_ORDER, jadi title dan deskripsi tidak pernah
    dikorbankan untuk paragraf yang menyalinnya.

    Mengembalikan nomor posisi per peran, bentuk yang sama dengan
    duplicate_slots supaya keduanya bermuara ke gap_spec yang sama.
    """
    kembar: dict[str, list[int]] = {}

    # Kalimat yang sudah berdiri, beserta peran pemiliknya. Peran
    # ikut disimpan supaya slot tidak pernah dihitung kembar oleh
    # kalimatnya sendiri - dua slot sepeeran sudah diurus
    # duplicate_slots, dengan pengecualian template yang memang
    # menghendakinya.
    berdiri: list[tuple[str, str]] = []

    urutan = [
        role
        for role in CROSS_ROLE_ORDER
        if role in spec or role in isi
    ]

    for role in urutan:
        nilai = isi.get(role)

        if isinstance(nilai, list):
            butir = [(index, str(teks or "")) for index, teks in enumerate(nilai)]
        else:
            butir = [(0, str(nilai or ""))]

        ulang: list[int] = []
        milik_role: list[str] = []

        for index, teks in butir:
            kalimat = [
                satu
                for satu in split_sentences(teks)
                if len(satu) >= CROSS_MIN_CHARS
            ]

            if not kalimat:
                continue

            bentrok = False

            for satu in kalimat:
                bentuk = " ".join(satu.split()).casefold()

                for peran_lain, lawan in berdiri:
                    if peran_lain == role:
                        continue

                    panjang = max(len(bentuk), len(lawan))
                    pendek = min(len(bentuk), len(lawan))

                    if pendek * CROSS_LENGTH_SPREAD < panjang:
                        continue

                    if near_twins(bentuk, lawan):
                        bentrok = True
                        break

                if bentrok:
                    break

            # Syarat "role in spec" bukan kerapian. Nomor posisi yang
            # dikembalikan fungsi ini bermuara ke gap_spec, yang
            # membaca spec[role] langsung - peran yang ada di isi tapi
            # tidak diminta di spec akan menjatuhkan seluruh run
            # dengan KeyError, di tengah langkah yang paling mahal.
            if bentrok and role in LIST_ROLES and role in spec:
                # Peran bertekstunggal tidak ikut diminta ulang.
                # Judul, deskripsi, dan H1 berdiri paling depan di
                # urutan, jadi yang mengulang selalu peran sesudahnya
                # - dan kalau toh salah satunya yang mengulang, yang
                # dikorbankan tidak boleh teks yang kontrak panjang
                # dan bentuknya paling ketat.
                ulang.append(index)
                continue

            milik_role.extend(
                " ".join(satu.split()).casefold() for satu in kalimat
            )

        berdiri.extend((role, satu) for satu in milik_role)

        if ulang:
            kembar[role] = sorted(set(ulang))

    return kembar


def distinct_tally(spec: dict, isi: dict) -> dict[str, tuple[int, int]]:
    """
    Berapa bunyi berbeda yang DIBUTUHKAN tiap peran, dan berapa yang
    benar-benar tersedia.

    Yang dibutuhkan dihitung dari templatenya, bukan dari jumlah
    slotnya: slot yang teks asalnya sama boleh - dan memang pantas -
    berbunyi sama, jadi yang harus berbeda cuma sebanyak teks asal
    yang berbeda. Untuk peran yang teks lamanya tidak dikirim,
    seluruh slotnya harus berbeda.

    Yang tersedia dihitung dari bentuk TERBACANYA, bukan dari teks
    mentahnya, dengan alasan yang sama seperti di duplicate_slots.
    """
    hitung: dict[str, tuple[int, int]] = {}

    for role, rule in spec.items():
        if role not in DISTINCT_ROLES or role not in LIST_ROLES:
            continue

        jumlah = int(rule.get("count") or 0)

        if jumlah < 2:
            continue

        ada = isi.get(role) or []
        jatah = slot_widths(rule)
        contoh = list(rule.get("samples") or [])

        butuh = (
            len({normalize(str(teks)) for teks in contoh if str(teks).strip()})
            if contoh
            else jumlah
        )

        punya = {
            render_form(
                str(ada[index]),
                jatah[index] if index < len(jatah) else 0,
                role,
            )
            for index in range(min(jumlah, len(ada)))
            if str(ada[index]).strip()
        }

        hitung[role] = (butuh, len(punya))

    return hitung


def short_roles(spec: dict, isi: dict) -> dict[str, list[int]]:
    """
    Posisi mana saja yang belum terjawab, per peran.

    Yang dikembalikan nomor urutnya, bukan sekadar berapa banyak.
    Lubang tidak selalu di ekor: model bisa menjawab slot ke-1 dan
    ke-5 lalu melewatkan yang di antaranya, dan yang paling sering
    terjadi, menyalin balik contoh di posisi mana pun. Meminta
    "sisanya" sebanyak N akan mengambil N slot terakhir - bukan slot
    yang benar-benar kosong - sehingga yang terisi ditimpa dan yang
    kosong tetap kosong.
    """
    kurang: dict[str, list[int]] = {}

    for role, rule in spec.items():
        if role not in LIST_ROLES:
            # Peran bertekstunggal ikut dihitung sejak judul dan
            # deskripsi lama milik template dikirim sebagai cetakan
            # bentuk. Jawaban yang menyalin balik cetakannya
            # dikosongkan di fit_content_to_spec, dan tanpa baris ini
            # kekosongan itu tidak pernah diminta ulang - slotnya
            # terbit dengan kalimat pemilik template, yang justru
            # keadaan yang mau dihindari sejak awal.
            if role not in SINGLE_RETRY_ROLES:
                continue

            teks_tunggal = str(isi.get(role) or "").strip()

            if not teks_tunggal:
                kurang[role] = [0]
                continue

            # Judul dan deskripsi yang JATUH DI BAWAH LANTAINYA ikut
            # diminta ulang, tidak seperti peran lain yang baru
            # dihitung lubang di setengah lantai.
            #
            # Rentangnya keputusan pengguna - title 50-70, deskripsi
            # 140-180 - dan yang membuatnya jatuh biasanya bukan model
            # melainkan penyapu klaim, yang bekerja SESUDAH panjangnya
            # ditegakkan grammar. Terukur pada halaman terbit
            # output/wayangplay-slot-gacor-20260819_232939: satu
            # kalimat dibuang penyapu, deskripsinya tinggal 93
            # karakter dari lantai 140, dan tidak ada satu pun tahap
            # yang keberatan karena kolomnya toh tidak kosong.
            lantai_tunggal = list(rule.get("floors") or [])
            batas_tunggal = lantai_tunggal[0] if lantai_tunggal else 0

            if batas_tunggal and len(teks_tunggal) < batas_tunggal:
                kurang[role] = [0]

            continue

        ada = isi.get(role) or []
        lantai = list(rule.get("floors") or [])

        lubang: list[int] = []

        for index in range(rule["count"]):
            teks = str(ada[index]).strip() if index < len(ada) else ""

            if not teks:
                lubang.append(index)
                continue

            # Teks yang jauh lebih pendek dari jatahnya dihitung sebagai
            # lubang juga, bukan sebagai jawaban yang sah.
            #
            # Ini keluhan pengguna tentang ulasan: "terlalu pendek".
            # Slot ulasan berjatah 176 karakter dijawab satu kalimat 40
            # karakter, dan sebelumnya tidak ada satu pun tahap yang
            # keberatan - jumlahnya pas, isinya ada, jadi lolos. Yang
            # membedakan lubang panjang dari lubang kosong cuma bahwa
            # yang ini kelihatan penuh dari jauh.
            #
            # Ambangnya SETENGAH lantai, bukan lantainya sendiri.
            # Meminta ulang tiap teks yang meleset sedikit menghabiskan
            # giliran untuk perbaikan yang tidak akan terlihat siapa
            # pun; yang diincar di sini jawaban yang panjangnya
            # sepertiga dari yang diminta.
            batas = lantai[index] if index < len(lantai) else 0

            if batas and len(teks) < batas * SHORT_TEXT_SHARE:
                lubang.append(index)

        if lubang:
            kurang[role] = lubang

    # Bunyi yang mengulang diperlakukan sama seperti slot kosong.
    #
    # Keduanya sama-sama "posisi ini belum punya jawaban yang layak",
    # dan menyatukannya di sini berarti seluruh mesin perbaikan yang
    # sudah ada - gap_spec, forbid_samples, daftar "sudah", batas
    # percobaan - langsung berlaku untuk kembar juga, tanpa satu pun
    # jalur baru yang perlu dijaga sendiri.
    #
    # Yang diminta ulang HANYA posisi kembarnya. Halaman tidak pernah
    # disusun ulang gara-gara dua label bertabrakan.
    for role, ulang in duplicate_slots(spec, isi).items():
        gabung = sorted(set(kurang.get(role, [])) | set(ulang))

        if gabung:
            kurang[role] = gabung

    # Kembar LINTAS PERAN lewat pintu yang sama.
    #
    # Dipanggil sesudah kembar sepeeran, bukan sebagai gantinya:
    # keduanya menangkap bentuk yang berbeda dan tidak saling
    # menutupi. Yang satu menjaga dua ulasan bersebelahan tidak
    # berbunyi sama; yang ini menjaga kalimat ulasan tidak
    # mengulang kalimat yang sudah dibaca di paragraf dan di
    # deskripsi.
    for role, ulang in cross_role_duplicates(spec, isi).items():
        gabung = sorted(set(kurang.get(role, [])) | set(ulang))

        if gabung:
            kurang[role] = gabung

    return kurang


def gap_spec(spec: dict, kurang: dict[str, list[int]]) -> dict:
    """
    Menyusun permintaan khusus untuk posisi yang masih kosong.

    Contoh teks lama dan jatah panjang ikut dipetik dari posisi yang
    sama, jadi yang dikirim ke model benar-benar milik slot yang
    hendak diisi. Nomor posisinya disimpan di "positions" supaya
    jawabannya bisa dikembalikan ke tempat asalnya.
    """
    sisa: dict[str, dict] = {}

    for role, lubang in kurang.items():
        rule = spec[role]

        potongan = dict(rule)
        potongan["count"] = len(lubang)
        potongan["positions"] = list(lubang)

        # Posisi ini kosong karena jawabannya dibuang, dan sebab
        # paling sering adalah model menyalin balik teks lamanya.
        # Contohnya tetap dikirim - bentuk dan fungsinya masih perlu
        # diketahui - tapi sebagai larangan, bukan sebagai cetakan.
        potongan["forbid_samples"] = True

        for kunci in (
            "samples",
            "budgets",
            "columns",
            "floors",
            "partners",
            "fresh",
        ):
            nilai = rule.get(kunci)

            if nilai:
                potongan[kunci] = [
                    nilai[index] for index in lubang if index < len(nilai)
                ]

        jatah = potongan.get("budgets")

        if jatah:
            potongan["max_length"] = min(jatah)
            potongan["max_length_any"] = max(jatah)

        # offset dipakai memasangkan faq_answer dengan pertanyaannya.
        # Untuk lubang yang berserak, yang paling masuk akal adalah
        # posisi pertamanya.
        potongan["offset"] = int(rule.get("offset", 0)) + lubang[0]

        sisa[role] = potongan

    return sisa


def extend_content(isi: dict, lanjutan: dict, spec: dict, sisa: dict) -> dict:
    """
    Mengembalikan jawaban susulan ke posisi yang tadinya kosong.

    Peta teks lama ke teks baru ikut disambung, karena peta itulah
    yang memasangkan tiap label ke slot yang memakainya.
    """
    hasil = dict(isi)

    for role, tambahan in lanjutan.items():
        if role == "_by_old":
            # Petanya TIDAK disalin dari jawaban model. Disusun ulang
            # di bawah, dari daftar yang benar-benar diterima.
            continue

        if role.startswith("_") or role not in sisa:
            continue

        if not isinstance(tambahan, list):
            # Peran bertekstunggal: jawabannya satu string.
            #
            # Dulu apa pun yang datang langsung dipakai, dan itu benar
            # selama yang diminta ulang cuma slot yang KOSONG. Sejak
            # judul dan deskripsi yang jatuh di bawah lantainya ikut
            # diminta ulang, syaratnya tidak berlaku lagi: jawaban
            # susulan yang lebih pendek lagi akan menukar teks pendek
            # dengan teks yang lebih pendek.
            #
            # Aturannya sama dengan yang dipakai peran berdaftar di
            # bawah: yang kosong menerima apa saja, yang kependekan
            # hanya menerima yang lebih panjang.
            if role in SINGLE_RETRY_ROLES and str(tambahan or "").strip():
                lama_tunggal = str(hasil.get(role) or "").strip()
                baru_tunggal = str(tambahan).strip()

                if not lama_tunggal or len(baru_tunggal) > len(lama_tunggal):
                    hasil[role] = baru_tunggal

            continue

        daftar = list(hasil.get(role) or [])
        daftar += [""] * (spec[role]["count"] - len(daftar))

        for urutan, posisi in enumerate(sisa[role].get("positions", [])):
            if urutan >= len(tambahan):
                break

            teks = str(tambahan[urutan]).strip()

            if not teks or posisi >= len(daftar):
                continue

            lama = str(daftar[posisi]).strip()
            jatah = slot_widths(spec[role])
            contoh = list(spec[role].get("samples") or [])

            def bentuk(nilai: str, urut: int) -> str:
                return render_form(
                    nilai, jatah[urut] if urut < len(jatah) else 0, role
                )

            def asal(urut: int) -> str:
                return (
                    normalize(str(contoh[urut]))
                    if urut < len(contoh)
                    else ""
                )

            def bertabrakan(nilai: str) -> bool:
                # Pengulangan yang MEMANG dikehendaki template
                # dikecualikan, dengan syarat yang sama persis seperti
                # di duplicate_slots: dua slot yang teks asalnya sama
                # pantas berbunyi sama. Tanpa pengecualian ini, slot
                # yang kebetulan berpasangan dengan kembarannya yang
                # sah tidak akan pernah bisa diperbaiki - jawaban
                # barunya selalu terbaca "masih kembar".
                sendiri = asal(posisi)

                sepearan = any(
                    near_twins(bentuk(nilai, posisi), bentuk(str(lain), urut))
                    for urut, lain in enumerate(daftar)
                    if urut != posisi
                    and str(lain).strip()
                    and not (sendiri and sendiri == asal(urut))
                )

                # Kembar LINTAS PERAN ikut dihitung tabrakan.
                #
                # Kalau tidak, slot yang diminta ulang karena
                # mengulang deskripsi cuma tunduk pada aturan "yang
                # lebih panjang menang" - aturan yang dibuat untuk
                # lubang kependekan - dan jawaban yang benar-benar
                # berbeda tapi lebih pendek ditolak, sementara
                # kalimat yang mengulang tetap terbit.
                # Pembuka yang sama dengan ulasan lain ikut dihitung
                # tabrakan, dengan alasan yang sama seperti kembar
                # lintas peran: yang dicari di situ bukaan yang
                # BERBEDA, dan jawaban yang lebih pendek tapi dibuka
                # lain justru yang diminta.
                pembuka_sama = role in OPENING_DISTINCT_ROLES and any(
                    opening_word(nilai) == opening_word(str(lain))
                    and opening_word(nilai)
                    for urut, lain in enumerate(daftar)
                    if urut != posisi and str(lain).strip()
                )

                return (
                    sepearan
                    or pembuka_sama
                    or cross_role_conflict(nilai, role, hasil)
                )

            # Lubang di sini ada tiga macam, dan aturannya beda-beda.
            #
            # Yang benar-benar kosong: apa pun jawabannya menang.
            #
            # Yang terisi tapi jauh lebih pendek dari jatahnya: yang
            # lebih panjang yang dipakai, karena giliran ulang yang
            # kebetulan menjawab lebih pendek lagi cuma menukar teks
            # pendek dengan teks yang lebih pendek.
            #
            # Yang isinya MENGULANG posisi lain: panjang tidak lagi
            # jadi ukuran. Yang dicari di situ bunyi yang berbeda, dan
            # jawaban yang lebih pendek tapi berbeda justru yang
            # diminta - kalau aturan panjang tetap dipakai, label
            # kembar yang panjang tidak akan pernah bisa diganti.
            if bertabrakan(lama):
                if bertabrakan(teks):
                    # Masih kembar juga: tidak ada yang diperbaiki,
                    # jadi yang lama dibiarkan dan putaran berikutnya
                    # berhenti sendiri karena tidak ada kemajuan.
                    continue
            elif len(teks) <= len(lama):
                continue

            daftar[posisi] = tambahan[urutan]

        hasil[role] = daftar

    # Peta teks lama -> teks baru disusun ulang dari daftar yang SUDAH
    # diterima, bukan disalin dari jawaban model.
    #
    # Peta inilah yang dibaca build_edits, jadi peta yang tidak
    # sepakat dengan daftarnya berarti yang terbit justru jawaban yang
    # barusan DITOLAK di atas - entah karena masih kembar, entah
    # karena lebih pendek daripada yang sudah ada. Disalin mentah,
    # penolakan di atas cuma merapikan daftar yang tidak pernah
    # dibaca siapa pun.
    peta = dict(hasil.get("_by_old") or {})

    for role, aturan in (sisa or {}).items():
        contoh = list((spec.get(role) or {}).get("samples") or [])
        daftar = hasil.get(role)

        if not contoh or not isinstance(daftar, list):
            continue

        pasangan = dict(peta.get(role) or {})

        for posisi in aturan.get("positions", []):
            if posisi >= len(contoh) or posisi >= len(daftar):
                continue

            kunci = normalize(sample_text(contoh[posisi]))

            if kunci and str(daftar[posisi]).strip():
                pasangan[kunci] = daftar[posisi]

        if pasangan:
            peta[role] = pasangan

    if peta:
        hasil["_by_old"] = peta

    return hasil


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


# Tanda pisah yang boleh berdiri antara nama situs dan janji di
# belakangnya.
#
# Isi dan takarannya diambil dari 120 contoh title milik pengguna
# sendiri di knowledge/gaya_title.txt: titik dua 33 kali, garis tegak
# 27 kali, sisanya tersebar tipis. Emoji ikut karena banyak barisnya
# memang memakai emoji sebagai pemisah - bytenya hilang waktu berkas
# itu ditempel ke chat, bukan karena pengguna tidak memakainya.
#
# Yang TIDAK ada di sini: koma, titik, dan tanda hubung tanpa spasi.
# Ketiganya menyatu dengan kalimat, dan yang diminta justru
# kebalikannya - nama situs berdiri sendiri, terpisah bersih dari
# janji di belakangnya.
TITLE_MARKS = (
    ":", ":", ":", ":", ":", ":",
    "|", "|", "|", "|", "|",
    "-", ">", "~", "@", "#", "$",
    "🔥", "⚡", "🎰", "💰", "✨",
)

# Tanda pisah untuk bidang di luar judi.
#
# Tiga emoji di daftar atas menamai bidangnya sendiri: 🎰 mesin slot,
# 💰 uang, 🔥 "lagi panas". Untuk halaman judi itu memang selera
# pengguna, dan daftar aslinya diambil dari 120 contoh title
# miliknya.
#
# Untuk halaman lain, emoji itu bukan hiasan yang salah tempat
# melainkan pernyataan yang salah: terukur di uji 14 Agustus 2026,
# judul halaman kursus bahasa terbit sebagai
# "LINGUAKU 🎰 Kursus bahasa inggris online" - mesin slot berdiri di
# hasil pencarian sebuah kursus.
#
# Perbandingan tanda baca dan emojinya dijaga sama dengan daftar
# aslinya, jadi bentuk judulnya tidak ikut berubah watak - yang
# berganti cuma emoji mana yang mungkin terpilih.
TITLE_MARKS_GENERIC = (
    ":", ":", ":", ":", ":", ":",
    "|", "|", "|", "|", "|",
    "-", ">", "~", "@", "#", "$",
    "✨", "⭐", "✅", "→", "•",
)

TITLE_MARKS_BY_NICHE = {
    "gambling": TITLE_MARKS,
    "generic": TITLE_MARKS_GENERIC,
}

# Tanda pisah yang berdiri lepas di tengah judul, yaitu yang diapit
# spasi atau menempel di ujung kata. Tanda hubung hanya dihitung
# kalau diapit spasi, supaya "anti-rungkad" tidak ikut terbelah.
LOOSE_MARK = re.compile(r"\s+[|:>~@#$•·–—]\s*|\s*[|:>~@#$•·–—]\s+|\s+-\s+")

# Emoji yang dipakai sebagai tanda pisah judul, sebagai pola yang
# bisa dicabut dari tengah teks.
#
# Dibutuhkan karena LOOSE_MARK hanya memuat tanda baca ASCII,
# sedangkan daftar tanda pisah judul memuat emoji juga - dan H1 yang
# menyalin judul membawa emoji itu ke dalam halaman.
EMOJI_MARK = re.compile(
    r"\s*[🌀-🫿☀-➿⬀-⯿]+\s*"
)

# Karakter yang tidak boleh menempel di awal atau akhir sisa judul.
EDGE_MARKS = " |:>~@#$•·–—-,.;!"

# Sama seperti di atas, ditambah setiap emoji yang bisa terpilih jadi
# tanda pisah.
#
# Dipakai waktu nama situs dicabut dari DEPAN judul. Yang tertinggal
# di situ bukan cuma spasi melainkan tanda pisah yang tadinya menempel
# ke nama itu, dan emoji tidak ada di EDGE_MARKS - terukur, judul yang
# ditulis model "PALAPAX 💰 Slot Gacor ..." terbit sebagai
# "PALAPAX 💰 💰 Slot Gacor ...".
BRAND_EDGE_MARKS = EDGE_MARKS + "".join(
    set(TITLE_MARKS) | set(TITLE_MARKS_GENERIC)
)

# Tanda baca yang menggantung sesudah satu kata dicabut dari TENGAH
# kalimat: " ," dan ", ,". Keduanya tidak pernah muncul dari tulisan
# model, cuma dari pencabutan.
ORPHAN_MARK = re.compile(r"\s+([,;.!?])")
DOUBLE_MARK = re.compile(r"([,;])(?:\s*[,;])+")

# Tanda yang menempel ke nama situs tanpa spasi di depannya. Titik dua
# yang didahului spasi terbaca sebagai salah ketik, sedangkan garis
# tegak dan emoji justru butuh ruang di kedua sisinya.
TIGHT_MARKS = {":"}


def title_separator(
    brand: str,
    keyword: str,
    niche: str = "gambling",
) -> str:
    """
    Memilih satu tanda pisah untuk judul halaman ini.

    Dipilih dari nama brand dan keywordnya, bukan diacak: dua halaman
    untuk brand yang sama memakai tanda yang sama, dan menjalankan
    ulang keyword yang sama tidak menghasilkan judul berbeda bentuk.

    Daftar tandanya mengikuti bidang - lihat TITLE_MARKS_GENERIC.
    Bawaannya "gambling" supaya pemanggil yang belum menyebutkan
    bidangnya mendapat tanda yang sama seperti sebelum bidang ada.
    """
    benih = hashlib.sha1(
        f"{brand.strip().casefold()}|{keyword.strip().casefold()}".encode(
            "utf-8"
        )
    ).hexdigest()

    daftar = TITLE_MARKS_BY_NICHE.get(
        str(niche or "").strip().lower(),
        TITLE_MARKS,
    )

    return daftar[int(benih[:8], 16) % len(daftar)]


# Kata yang boleh berdiri di dalam judul tapi tidak menambah satu
# keterangan pun kalau ditumpuk di ekornya.
#
# Ini keluhan pengguna, dan contohnya judul yang benar-benar terbit:
#
#   DINAR33 | Update Pola Slot Gacor Tiap Pagi 2026 Akurat 24 Jam Hari
#
# Enam kata pertama sudah judul yang utuh. "Akurat 24 Jam Hari" bukan
# kelanjutannya melainkan empat kata yang didempetkan di belakangnya,
# dan susunan itu tidak berbunyi seperti bahasa Indonesia sama sekali -
# tidak ada kata sambung, tidak ada yang diterangkan, dan "24 Jam"
# berdiri tanpa menyebut apa yang berlangsung 24 jam.
#
# Sebabnya bukan model kehabisan ide melainkan lantai panjang.
# TITLE_MIN 50 karakter ditegakkan grammar llama.cpp, yang menahan
# tanda kutip penutup sampai jatahnya terpenuhi. "DINAR33 | Update
# Pola Slot Gacor Tiap Pagi" cuma 41 karakter, jadi model dipaksa
# meneruskan - dan yang paling murah diteruskan adalah kata sifat.
#
# Lantainya tidak diturunkan: 50-70 sudah diputuskan pengguna, dan
# judul sependek 41 karakter memang membuang separuh baris yang
# diberikan Google. Yang diperbaiki caranya diisi - brief memesan
# manfaat, bukan kata sifat (lihat ai/neiiu_prompts.py), dan
# tumpukan yang tetap lolos disapu di sini.
TITLE_FILLER_TAIL = frozenset(
    {
        # penyangat mutu
        "akurat", "terakurat", "terbaik", "terpercaya", "terjamin",
        "dijamin", "resmi", "asli", "official", "original", "valid",
        "terverifikasi", "terlengkap", "lengkap", "mantap", "wajib",
        "pasti", "jitu", "ampuh", "parah", "banget", "aman", "nyaman",
        "cepat", "mudah", "gampang", "lancar", "stabil",
        # penyangat waktu. "harian", "setiap", dan "tiap" sengaja
        # TIDAK ikut: ketiganya menerangkan kata di sebelahnya dengan
        # sungguhan - "Pola Slot Gacor Harian" bukan tumpukan - dan
        # membuangnya membuang keterangan, bukan pengisi ruang.
        "terbaru", "terkini", "terupdate", "update", "hari", "ini",
        "sekarang", "juga", "nonstop",
        "jam", "menit", "detik", "realtime", "live",
        # penyangat khas halaman slot
        "gacor", "maxwin", "jackpot", "rungkad", "boncos", "anti",
        "no", "nomor", "satu",
    }
)

# Angka yang lazim ikut tumpukan sebagai satuan waktu, bukan sebagai
# keterangan. Tahun sengaja tidak masuk - "2026" hampir selalu bagian
# keywordnya, dan membuangnya berarti membuang kata yang dicari orang.
TITLE_FILLER_NUMBER = re.compile(r"^\d{1,3}$")

# Kata penyangat yang menuntut kata SIFAT sesudahnya.
#
# Dipisah dari kata sambung biasa karena nasibnya berkebalikan. Kata
# sambung menuntut kata benda, jadi yang di belakangnya keterangan
# sungguhan dan tumpukannya batal. Penyangat menuntut kata sifat, jadi
# yang di belakangnya penyangat lagi - "Paling Akurat" adalah dua kata
# yang sama-sama tidak menerangkan apa pun, dan keduanya bagian dari
# tumpukan yang sama.
TITLE_INTENSIFIER = frozenset(
    {
        "paling", "makin", "semakin", "kian", "sangat", "amat",
        "terlalu", "agak", "serba", "lebih",
    }
)

# Penyangat yang terdiri dari DUA kata, dan karena itu harus dihitung
# satu.
#
# Isinya sudah ada di TITLE_FILLER_TAIL sebagai kata-kata terpisah -
# "hari", "ini", "nomor", "satu" - dan pemisahan itu yang jadi
# soalnya. Penelusuran ekor berjalan kata per kata, jadi "Hari Ini"
# terhitung DUA tumpukan, lewat dari jatah satu, dan judul yang
# berakhir begitu ditolak:
#
#   WAYANGPLAY: Daftar Slot Gacor yang Bisa Dicoba Hari Ini
#
# Judul itu tidak menumpuk apa pun. "Hari ini" satu keterangan waktu,
# ditulis dengan dua kata karena memang begitu bentuknya dalam bahasa
# Indonesia - dan daftar larangan di prompt pun menuliskannya sebagai
# satu butir, berdampingan dengan "24 jam" dan "nomor satu".
#
# Angka diwakili "#", dan itu yang menangkap "24 Jam" maupun
# "3 Menit" tanpa menuliskan setiap angka yang mungkin.
TITLE_FILLER_PAIRS = frozenset(
    {
        "hari ini", "nomor satu", "no satu", "nomer satu",
        "# jam", "# menit", "# detik",
    }
)


def merge_filler_pairs(tumpukan: list[str]) -> list[str]:
    """
    Menggabungkan penyangat dua kata jadi satu butir.

    Dipakai SETELAH ekornya ditelusuri, bukan selama - penelusuran
    berjalan dari kanan ke kiri dan berhenti di kata pertama yang
    bukan penyangat, sedangkan pasangan hanya bisa dikenali dari kiri
    ke kanan atas daftar yang sudah lengkap.
    """
    hasil: list[str] = []
    lewat = False

    for nomor, satu in enumerate(tumpukan):
        if lewat:
            lewat = False
            continue

        if nomor + 1 < len(tumpukan):
            kiri = satu.strip(EDGE_MARKS).casefold()
            kanan = tumpukan[nomor + 1].strip(EDGE_MARKS).casefold()

            if kiri.isdigit():
                kiri = "#"

            if f"{kiri} {kanan}" in TITLE_FILLER_PAIRS:
                hasil.append(f"{satu} {tumpukan[nomor + 1]}")
                lewat = True
                continue

        hasil.append(satu)

    return hasil


# Berapa kata tumpukan yang masih dimaafkan di ekor judul.
#
# Satu kata sifat di ujung adalah cara menutup judul yang wajar -
# "... Tanpa Potongan Sekarang" masih terbaca sebagai kalimat. Dua ke
# atas tidak pernah: begitu dua penyangat berdiri berdampingan tanpa
# kata sambung di antaranya, keduanya berhenti menerangkan apa pun dan
# tinggal mengisi ruang.
TITLE_TAIL_ALLOWED = 1

# Berapa kata yang harus tersisa sesudah tumpukannya dibuang.
#
# Judul yang seluruh isinya penyangat tidak punya bagian utuh untuk
# diselamatkan, dan memotongnya cuma meninggalkan nama brand berdiri
# sendiri. Yang seperti itu dibiarkan apa adanya, lalu ditandai
# pemeriksa SEO sebagai judul yang perlu ditulis ulang.
TITLE_TAIL_KEEP = 4


def title_tail_pile(text: str, keyword: str = "") -> list[str]:
    """
    Kata tumpukan yang berdiri di ekor judul, dari kiri ke kanan.

    Kata yang ada di keyword tidak pernah dihitung tumpukan, berapa
    pun mirip bentuknya. "Slot Gacor" adalah topik halamannya, dan
    "gacor" yang kebetulan berdiri di ujung judul bukan penyangat yang
    bisa dibuang - membuangnya membuang keywordnya sendiri.

    Begitu juga kata yang berdiri sesudah kata sambung. Yang
    membedakan tumpukan dari keterangan sungguhan bukan kata-katanya
    melainkan ada tidaknya yang mengikatnya ke kalimat:

      DINAR33 Deposit QRIS Cair Dalam 3 Menit     <- "3 Menit"
      DINAR33 Pola Slot Gacor Tiap Pagi 2026 Akurat 24 Jam Hari

    Dua kata terakhir di baris pertama ada di daftar penyangat, tapi
    keduanya justru yang diterangkan "Dalam" - dibuang, judulnya
    berhenti sebelum mengatakan dalam berapa lama. Di baris kedua
    tidak ada satu pun kata yang mengikat "Akurat 24 Jam Hari" ke
    kalimat sebelumnya, dan itulah yang membuatnya tumpukan.
    """
    kata = str(text or "").split()

    if not kata:
        return []

    milik_keyword = {
        potong.casefold()
        for potong in re.findall(r"\w+", str(keyword or ""))
    }

    tumpukan: list[str] = []

    for satu in reversed(kata):
        bersih = satu.strip(EDGE_MARKS).casefold()

        if not bersih or bersih in milik_keyword:
            break

        if (
            bersih in TITLE_FILLER_TAIL
            or bersih in TITLE_INTENSIFIER
            or TITLE_FILLER_NUMBER.match(bersih)
        ):
            tumpukan.insert(0, satu)
            continue

        # Kata yang menghentikan penelusuran sekaligus menentukan
        # nasib tumpukannya. Kalau ia menuntut kelanjutan - "dalam",
        # "tanpa", "setiap" - maka yang di belakangnya bukan tumpukan
        # melainkan kelanjutan yang dituntutnya.
        if menggantung(satu, True):
            return []

        break

    return merge_filler_pairs(tumpukan)


def strip_title_pile(text: str, keyword: str = "") -> str:
    """
    Membuang tumpukan penyangat yang menempel di ekor judul.

    Yang di depan tumpukan tidak disentuh sama sekali. Judulnya sudah
    utuh sebelum tumpukan itu ditempelkan - itu justru yang membuat
    tumpukannya kelihatan - jadi tidak ada yang perlu disusun ulang.
    """
    bersih = " ".join(str(text or "").split())
    tumpukan = title_tail_pile(bersih, keyword)

    if len(tumpukan) <= TITLE_TAIL_ALLOWED:
        return bersih

    # Yang dipotong dihitung dalam KATA, bukan butir.
    #
    # Sejak penyangat dua kata digabung jadi satu butir - "Hari Ini",
    # "24 Jam" - jumlah butir tidak lagi sama dengan jumlah kata, dan
    # memotong sebanyak butir meninggalkan separuh frasa berdiri
    # sendiri: "... Slot Gacor Akurat 24". Persis ekor menggantung
    # yang justru sedang dicegah fungsi ini.
    kata_tumpukan = sum(len(satu.split()) for satu in tumpukan)

    sisa = bersih.split()[:-kata_tumpukan]

    if len(sisa) < TITLE_TAIL_KEEP:
        return bersih

    dipangkas = " ".join(sisa).strip(EDGE_MARKS)

    # Keywordnya diperiksa lagi sesudah dipangkas. Tumpukan yang
    # kebetulan memuat kata terakhir keywordnya tidak boleh dibuang
    # meskipun sisanya masih panjang; yang tersisa akan lolos semua
    # pemeriksaan panjang lalu terbit tanpa kata yang dicari orang.
    if keyword.strip() and not keyword_covered(dipangkas, keyword):
        return bersih

    return dipangkas or bersih


def strip_brand_mentions(text: str, brand: str) -> str:
    """
    Mencabut SETIAP sebutan nama situs dari bagian janji judul.

    Bentuk judul yang diminta pengguna menaruh nama situs satu kali,
    di kepala. Nama itu ditempelkan enforce_title_shape, jadi setiap
    sebutan yang tertinggal di badan judul adalah sebutan KEDUA.

    Dulu yang dicabut cuma sebutan pertama, dan model memang menulis
    namanya lebih dari sekali. Terukur 14 Agustus 2026, halaman
    landing terbit dengan judul:

        PALAPAX 💰 Slot Gacor Hari Ini di PALAPAX, Gacor dan Dibayar

    Enam puluh delapan karakter, dan dua puluh satu di antaranya
    dipakai untuk menulis nama yang sama dua kali - di jatah yang
    cuma tujuh puluh. Di hasil pencarian itu terbaca sebagai judul
    yang digenerate mesin, persis kesan yang dihindari.

    Kembalinya teks apa adanya kalau namanya memang tidak ada, supaya
    judul yang tidak menyebut nama situs sama sekali tidak tersentuh
    perapian tanda baca di bawah.
    """
    nama = str(brand or "").strip()
    hasil = str(text or "")

    if not nama:
        return hasil

    pola = re.compile(re.escape(nama), re.I)

    if not pola.search(hasil):
        return hasil

    # Satu sebutan dibuang tiap putaran, jadi putarannya pasti habis.
    while True:
        cocok = pola.search(hasil)

        if not cocok:
            break

        # dipotong=False sama seperti sebelumnya - lihat alasannya di
        # enforce_title_shape: potongan ini bukan sisa pemotongan
        # panjang, jadi angka di ujungnya tidak boleh ikut dibuang.
        depan = drop_dangling(hasil[:cocok.start()].strip())

        # Kata sambung Thai menempel ke kata di depannya tanpa spasi,
        # jadi drop_dangling yang bekerja per token tidak melihatnya.
        # Dijalankan di sini saja, di tempat pencabutan benar-benar
        # terjadi - lihat drop_thai_tail.
        depan = drop_thai_tail(depan, True)

        belakang = hasil[cocok.end():].strip()

        hasil = f"{depan} {belakang}".strip()

    hasil = DOUBLE_MARK.sub(r"\1", ORPHAN_MARK.sub(r"\1", hasil))

    return " ".join(hasil.split()).strip(BRAND_EDGE_MARKS)


def join_two_promises(janji: str) -> str:
    """
    Dua janji pendek yang didempetkan koma disambung dengan "&".

    Bentuk yang dipakai pengguna di berkas contohnya sendiri, dan ia
    dipakai di mayoritas barisnya:

        [ BRAND ] Withdraw Cepat & Instan | Jaminan Bayar 100%
        [ BRAND ] RTP Live Hari Ini & Bocoran Pola Slot Gacor
        [ BRAND ] Link Alternatif Resmi & Login Anti Blokir 24 Jam

    Yang terbit 22 Agustus 2026 memakai koma untuk maksud yang sama:
    "BATARATOTO - Slot Online Akses Cepat, Tidak Blokir". Koma di
    situ membuat penilai judul menandainya sebagai kalimat yang
    berhenti menggantung - dan penilai itu benar, karena koma memang
    menjanjikan kelanjutan yang tidak pernah datang. "&" tidak
    menjanjikan apa-apa; ia cuma menyandingkan.

    Yang disambung HANYA yang benar-benar dua janji pendek: satu koma
    saja, dan potongan sesudahnya paling banyak empat kata. Judul
    dengan dua koma adalah tumpukan, dan itu urusan clause_pile_score
    - bukan sesuatu yang boleh disembunyikan dengan mengganti
    tandanya.
    """
    teks = " ".join(str(janji or "").split())

    if teks.count(",") != 1:
        return teks

    kiri, _, kanan = teks.partition(",")
    kiri, kanan = kiri.strip(), kanan.strip()

    if not kiri or not kanan:
        return teks

    if len(kanan.split()) > 4 or len(kiri.split()) > 8:
        return teks

    # Potongan yang sudah dibuka kata sambung tidak perlu tanda lagi.
    if kanan.split()[0].casefold() in {"dan", "atau", "serta", "tapi"}:
        return teks

    return f"{kiri} & {kanan}"


def enforce_title_shape(
    title: str,
    keyword: str,
    brand: str,
    limit: int,
    niche: str = "gambling",
) -> str:
    """
    Menegakkan bentuk judul: nama situs, satu tanda pisah, lalu janji.

    Ini permintaan pengguna, dan alasannya kelihatan begitu judul
    hasil generate dijajarkan dengan contoh miliknya:

      punya pengguna : [ BRAND ] | Update Harian RTP Slot dengan Pola
                       Gacor Terbaik
      yang terbit    : TIMAH33 menghadirkan slot gacor dengan sistem
                       spin modern

    Yang kedua bukan judul yang lebih jelek - ia bentuk yang lain
    sama sekali. Nama situs melebur jadi subjek kalimat, jadi tidak
    ada satu titik pun di mana mata pembaca bisa berhenti dan tahu
    situs apa ini. Di hasil pencarian, tempat judul dibaca dalam
    sepersekian detik sambil lalu, itu yang menentukan diklik atau
    tidak.

    Ditegakkan di Python, bukan diserahkan ke prompt. Aturan bentuk
    di prompt sudah dicoba dan hasilnya diikuti kadang-kadang saja,
    sedangkan bentuk yang cuma benar sebagian sama saja dengan tidak
    punya bentuk.

    Angka persen dibuang lebih dulu, SEBELUM panjangnya dihitung.
    Urutannya penting: dibuang belakangan, judulnya sudah terlanjur
    dipotong untuk memberi tempat pada angka yang kemudian hilang,
    dan yang terbit adalah judul pendek yang ekornya tetap tercabut.
    """
    clean = strip_title_pile(
        strip_figures(" ".join(str(title or "").split())),
        keyword,
    )

    nama = str(brand or "").strip()

    if not clean or not nama:
        return clean

    # Ejaan nama situs dibetulkan SEBELUM sebutannya dicabut, dan
    # urutan itu yang jadi soalnya.
    #
    # strip_brand_mentions mencari nama yang ejaannya PERSIS. Nama
    # yang salah ketik satu huruf tidak dikenalinya, jadi ia
    # tertinggal di badan judul - lalu kepala judul ditempeli nama
    # yang benar, dan yang terbit menyebut situsnya dua kali:
    #
    #   mentah : WAYANGPLA menghadirkan slot gacor
    #   terbit : WAYANGPLAY # WAYANGPLA menghadirkan slot gacor
    #
    # Bentuk sebaliknya lebih buruk lagi. "WAYANGPLAYY" memuat
    # "WAYANGPLAY" di dalamnya, jadi yang tercabut sepuluh huruf
    # pertamanya dan yang tertinggal satu huruf "Y" berdiri sendiri
    # di tengah kalimat:
    #
    #   terbit : WAYANGPLAY # Cara Masuk Slot Gacor Y Tanpa Blokir
    #
    # Dibetulkan di sini, keduanya hilang sekaligus: yang dicabut
    # sebutan yang sudah benar ejaannya, dan tidak ada puing yang
    # tertinggal. restore_brand juga dijalankan atas seluruh isi
    # halaman di tahap akhir - dijalankan dua kali tidak mengubah
    # apa pun, karena yang ejaannya sudah benar dilewatinya.
    clean = restore_brand(clean, nama, keyword)[0]

    # Kata sambung yang tadinya menempel ke nama situs ikut dibuang.
    # Tanpa itu, "Rahasia Spin di TIMAH33 yang Membuka Peluang"
    # berpindah jadi "TIMAH33 | Rahasia Spin di yang Membuka Peluang".
    #
    # Setiap sebutan dicabut, bukan cuma yang pertama - alasannya di
    # strip_brand_mentions.
    sisa = strip_brand_mentions(clean, nama)

    sisa = " ".join(LOOSE_MARK.sub(" ", sisa).split()).strip(EDGE_MARKS)

    # Kata sambung yang menggantung di ujung dibuang SEBELUM panjangnya
    # diperiksa, bukan cuma waktu judulnya kepanjangan. Judul yang
    # sampai ke sini sering sudah dipotong sekali oleh ensure_identity,
    # dan potongan itu meninggalkan ekor seperti "... Setiap Hari
    # Tanpa" yang muat di jatah - jadi tidak pernah kena pemotongan
    # kedua, dan terbit apa adanya.
    sisa = drop_dangling(sisa)

    if not sisa:
        return clean[:limit]

    # Huruf pertama janji dibesarkan. Tanpa itu terbit "TIMAH33 |
    # menghadirkan slot gacor", yang terbaca seperti kalimat yang
    # kepalanya dipenggal - bukan seperti judul.
    if sisa[:1].islower():
        sisa = sisa[0].upper() + sisa[1:]

    sisa = join_two_promises(sisa)

    tanda = title_separator(nama, keyword, niche)

    kepala = (
        f"{nama}{tanda} " if tanda in TIGHT_MARKS else f"{nama} {tanda} "
    )

    ruang = limit - display_width(kepala)

    if ruang < 12:
        # Nama situsnya sendiri sudah hampir menghabiskan jatah.
        # Memaksakan bentuknya di sini menyisakan janji sepotong dua
        # kata, dan judul apa adanya lebih berguna daripada itu.
        return clean

    if display_width(sisa) > ruang:
        sisa = drop_dangling(trim_to_width(sisa, ruang), True)

    return f"{kepala}{sisa}".strip(EDGE_MARKS)


# Kata di keyword yang tidak wajib tertulis supaya keywordnya
# terhitung sudah ada di judul.
#
# Isinya tahun dan kata penunjuk waktu, dan keduanya memang yang paling
# sering ditinggalkan model waktu menulis judul: "slot gacor 2026"
# ditulisnya "slot gacor". Diperiksa apa adanya, judul itu terhitung
# TIDAK memuat keywordnya, dan seluruh keyword ditempelkan lagi di
# depan - sehingga yang terbit "WAYANGPLAY: Slot Gacor 2026 Link Login
# Slot Gacor Anti Blokir", dengan "slot gacor" dua kali dan ekornya
# terpotong untuk memberi tempat pada pengulangan itu.
#
# Inilah salah satu sebab keluhan "judulnya kaku dan terputus, tidak
# tersusun dalam satu kalimat".
OPTIONAL_KEYWORD_WORDS = re.compile(
    r"^(?:\d{4}|hari|ini|terbaru|terkini|sekarang|latest|today)$",
    re.IGNORECASE,
)


def keyword_covered(text: str, keyword: str) -> bool:
    """
    Apakah judul ini sudah memuat keywordnya, dengan toleransi.

    Yang diperiksa kata-kata isinya, bukan frasa persisnya. Judul yang
    sudah berbunyi "Link Login Slot Gacor Anti Blokir" memang sudah
    tentang "slot gacor 2026"; menempelkan keyword utuh di depannya
    tidak menambah satu pun kata baru, ia cuma menulis dua kali kata
    yang sudah ada dan memakan ruang ekor judulnya.
    """
    isi = str(text or "").lower()

    if keyword.strip().lower() in isi:
        return True

    wajib = [
        kata
        for kata in re.findall(r"\w+", keyword.lower())
        if not OPTIONAL_KEYWORD_WORDS.match(kata)
    ]

    if not wajib:
        return False

    return all(re.search(rf"\b{re.escape(kata)}", isi) for kata in wajib)


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

    # Ejaan nama situs dibetulkan lebih dulu, SEBELUM ditanya apakah
    # namanya sudah ada di teks ini.
    #
    # Pertanyaan itu dijawab dengan pencocokan persis, jadi nama yang
    # salah ketik satu huruf terbaca "tidak ada" - lalu nama yang
    # benar ditempelkan di depan, dan yang salah ketik tetap berdiri
    # di belakangnya. Pemulih ejaan di tahap akhir kemudian
    # membetulkan yang di belakang, dan yang terbit menyebut situsnya
    # dua kali:
    #
    #   mentah : WAYANGPLA menghadirkan slot gacor
    #   H1     : WAYANGPLAY: WAYANGPLAY menghadirkan slot gacor
    #
    # Title tidak memperlihatkannya karena enforce_title_shape
    # mencabut setiap sebutan lalu memasang satu di kepala. H1 tidak
    # lewat sana - dan H1 yang menyebut nama situs dua kali berturut-
    # turut adalah kalimat yang tidak ditulis siapa pun.
    #
    # Dibetulkan di sini, keduanya tertutup sekaligus: yang ditanya
    # keberadaan nama yang ejaannya sudah benar.
    clean = restore_brand(clean, clean_brand, keyword)[0]

    missing: list[str] = []

    if clean_brand and clean_brand.lower() not in clean.lower():
        missing.append(clean_brand)

    if keyword.strip() and not keyword_covered(clean, keyword):
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


def normalize_reviews(
    raw_reviews,
    region: str = "id",
    limit: int = 6,
) -> list[dict]:
    """
    Merapikan ulasan dari AI dan menanggalinya sendiri.

    Tanggalnya tidak pernah diminta ke model. Model kecil rutin
    menulis tanggal yang tidak ada di kalender, salah tahun, atau
    ada di masa depan, dan tanggal semacam itu langsung membuat
    structured data-nya ditolak. Di sini tanggal dipasang mundur
    dari hari ini, satu ulasan tiap beberapa hari, lalu dituliskan
    dalam dua bentuk: bentuk baca yang mengikuti kalender zona, dan
    bentuk ISO masehi untuk mesin.
    """
    now = datetime.now()
    result: list[dict] = []

    for index, raw in enumerate(raw_reviews or []):
        if not isinstance(raw, dict):
            continue

        # Nama pengulas tidak ikut dibetulkan. Nama orang tidak punya
        # ejaan baku, dan "Qrisna" yang diluruskan jadi "QRIS" adalah
        # kerusakan yang jauh lebih kelihatan daripada yang diperbaiki.
        name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()[:40]
        text = fix_terms(
            re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()[:600]
        )

        if not name or not text:
            continue

        try:
            rating = float(raw.get("rating", 5))
        except (TypeError, ValueError):
            rating = 5.0

        # Dijepit di 4.0-5.0. Ulasan bintang satu di halaman yang
        # dipasang sendiri oleh pemilik situs tidak masuk akal, dan
        # nilai di luar 1-5 membuat schema-nya tidak valid.
        rating = round(max(4.0, min(5.0, rating)), 1)

        moment = now - timedelta(days=3 + index * 4)

        result.append(
            {
                "name": name,
                "rating": rating,
                "text": text,
                "date": format_date(moment, region),
                "date_iso": iso_date(moment),
            }
        )

        if len(result) >= limit:
            break

    return result


def normalize_ratings(raw_ratings, limit: int = 3) -> list[dict]:
    """
    Merapikan penilaian layanan yang tampil di blok rating.
    """
    result: list[dict] = []

    for raw in raw_ratings or []:
        if not isinstance(raw, dict):
            continue

        label = re.sub(r"\s+", " ", str(raw.get("label") or "")).strip()[:40]

        if not label:
            continue

        try:
            value = float(raw.get("value", 5))
        except (TypeError, ValueError):
            value = 5.0

        result.append(
            {
                "label": label,
                "value": round(max(4.0, min(5.0, value)), 1),
            }
        )

        if len(result) >= limit:
            break

    return result


# Kata yang boleh berdiri di remah navigasi halaman situs slot.
#
# Diminta pengguna 21 Agustus 2026, atas remah yang benar-benar
# terbit: "Beranda > Slot Online > Pengalaman Bermain > Slot Gacor".
# Kalimatnya: "pada bagian breadcrumble jangan melenceng dari
# pembahasan situs slot; contohnya 'lihat hasil, verifikasi akun,
# tutup sesi, main tanpa batas' saya tidak suka".
#
# Remah bukan tempat menulis manfaat atau ajakan. Ia menyatakan LETAK
# halaman, jadi kosakatanya memang sempit - dan sempit itu yang
# membuatnya terbaca sebagai jalur, bukan sebagai slogan.
BREADCRUMB_WORDS = frozenset(
    """
    situs slot online rtp link login alternatif agen gacor resmi
    daftar terbaru live casino judi game games provider bocoran pola
    jackpot maxwin deposit withdraw main bermain terpercaya
    """.split()
)


# Bentuk remah yang dipakai menambal tingkat yang ditolak.
#
# Urutannya dari umum ke khusus, karena itu arah yang benar bagi
# sebuah jalur. {brand} diisi nama situs baru; bentuk tanpa {brand}
# dipakai lebih dulu supaya jalurnya tidak dibuka nama situs.
BREADCRUMB_SHAPES = (
    "Situs Slot",
    "Slot Online",
    "RTP Slot",
    "Agen Slot",
    "Link Login",
    "Alternatif Slot",
    "Situs {brand}",
    "RTP {brand}",
    "{brand} Login",
    "Link {brand}",
    "Alternatif {brand}",
)


def breadcrumb_allowed(teks: str, keyword: str, brand_name: str) -> bool:
    """
    Apakah satu tingkat remah memakai kosakata yang pantas.

    Yang diperiksa SELURUH katanya, bukan sebagiannya. Satu kata di
    luar daftar sudah cukup menolak, dan itu memang maksudnya:
    "Pengalaman Bermain" lolos kalau cuma sebagian katanya diperiksa,
    padahal justru "Pengalaman" yang membuatnya bukan jalur.
    """
    kata = {k.casefold() for k in re.findall(r"\w+", teks)}

    if not kata:
        return False

    boleh = set(BREADCRUMB_WORDS)
    boleh |= {k.casefold() for k in re.findall(r"\w+", keyword or "")}
    boleh |= {k.casefold() for k in re.findall(r"\w+", brand_name or "")}

    return kata <= boleh


def breadcrumb_fillers(
    keyword: str,
    brand_name: str,
    sudah: list[str],
) -> list[str]:
    """
    Bentuk remah cadangan yang belum dipakai di jalur ini.
    """
    dipakai = {normalize(teks) for teks in sudah}

    hasil: list[str] = []

    for bentuk in BREADCRUMB_SHAPES:
        if "{brand}" in bentuk and not brand_name:
            continue

        teks = bentuk.format(brand=brand_name)

        if normalize(teks) in dipakai:
            continue

        dipakai.add(normalize(teks))
        hasil.append(teks)

    return hasil


def normalize_breadcrumb(
    raw,
    keyword: str,
    h1: str,
    brand_name: str = "",
    region: str = "id",
    niche: str = "generic",
    levels: int = 4,
) -> list[str]:
    """
    Merapikan jalur breadcrumb hasil AI.

    Tiga hal ditegakkan di sini. Tingkat pertama selalu beranda
    dalam bahasa halaman, karena model kadang mengisinya dengan
    nama brand. Nama brand dibuang dari seluruh tingkat, sebab
    breadcrumb menyatakan letak topik, bukan siapa pemiliknya -
    dan brand sudah berdiri di title. Tingkat terakhir dipastikan
    ada, karena remah yang berhenti di kategori tidak memberi tahu
    pembaca hasil pencarian halaman apa yang akan dibukanya.
    """
    beranda = PAGE_TEXT.get(region, PAGE_TEXT["id"])["home"]

    bersih: list[str] = []

    for item in raw if isinstance(raw, list) else []:
        teks = re.sub(r"\s+", " ", str(item or "")).strip(" .,-–—>/|")

        if not teks:
            continue

        # Nama situs dicabut DARI DALAM tingkatnya, bukan cuma
        # dibandingkan sama dengan seluruh tingkatnya.
        #
        # Aturan promptnya sudah ada sejak lama - "Jangan memuat nama
        # brand di tingkat mana pun" - dan yang memeriksanya di sini
        # cuma menyamakan seluruh teks tingkat dengan nama brandnya.
        # Tingkat yang MEMUAT nama itu lewat, dan itu yang terbit:
        #
        #     Beranda > Slot Gacor > SIAM123 Slot
        #
        # Remah menyatakan LETAK topiknya, bukan siapa pemiliknya, dan
        # nama situs sudah berdiri di judul halaman.
        # Nama situs dicabut - KECUALI di halaman situs slot.
        #
        # Pengguna membalik aturan ini 21 Agustus 2026 dengan
        # menyebutkan sendiri bentuk yang dia mau: "brand/brand
        # login/rtp brand/situs slot/situs brand/brand link/link
        # brand". Enam dari tiga belas bentuk itu memuat nama situs,
        # jadi mencabutnya di sini menghapus separuh daftar yang baru
        # saja diminta.
        if brand_name and niche != "gambling":
            teks = " ".join(
                strip_brand_mentions(teks, brand_name).split()
            ).strip(" .,-\u2013\u2014>/|")

            if not teks:
                continue

        teks = teks[:60]

        # Dibandingkan tanpa huruf besar-kecil supaya "Beranda" dan
        # "beranda" tidak berdiri dua kali.
        if any(normalize(teks) == normalize(ada) for ada in bersih):
            continue

        if len(teks) < 4:
            continue

        bersih.append(teks)

    # Tingkat yang kosakatanya termuat seluruhnya di tingkat LAIN
    # dibuang, mana pun urutannya.
    #
    # "SIAM123 Slot" menyisakan "Slot" sesudah nama situs dicabut, dan
    # "Slot" berdiri berdampingan dengan "Slot Gacor" adalah jalur
    # yang bergerak mundur - tingkat yang lebih dalam justru lebih
    # umum daripada tetangganya. Diperiksa sesudah semuanya terkumpul,
    # bukan sambil jalan, karena tingkat yang lebih khusus bisa datang
    # BELAKANGAN: diperiksa sambil jalan, "Slot" lolos waktu daftarnya
    # baru berisi "Beranda".
    def kata_dari(teks_remah):
        return {k.casefold() for k in re.findall(r"\w+", teks_remah)}

    saring: list[str] = []

    for nomor, satu in enumerate(bersih):
        milik = kata_dari(satu)

        # Yang dibuang hanya tingkat yang termuat di tingkat SEBELUM
        # dirinya. Termuat di tingkat SESUDAHNYA justru bentuk jalur
        # yang benar - "Slot" lalu "Slot Gacor" lalu "Main Slot
        # Gacor" bergerak dari umum ke khusus, persis seperti
        # seharusnya. Yang salah kebalikannya: "Slot Gacor" lalu
        # "Slot", yang bergerak mundur.
        if milik and any(
            milik < kata_dari(lain)
            for urut, lain in enumerate(bersih)
            if urut < nomor
        ):
            continue

        saring.append(satu)

    bersih = saring

    # Tingkat terakhir: halaman ini. Diambil dari h1 kalau model
    # tidak menyediakannya, dipotong pendek supaya tetap terbaca
    # sebagai remah, bukan sebagai judul kedua.
    # Kata sambung yang menggantung di ujung dibuang. Lima kata
    # pertama H1 sering berhenti tepat sesudah "di", "untuk", atau
    # "dengan" - dan remah yang berbunyi "Cara Main Slot Gacor di"
    # berhenti di tengah keterangan.
    daun = (
        drop_dangling(" ".join(h1.split()[:5]))[:60]
        if h1
        else keyword.title()[:60]
    )

    if not bersih:
        bersih = [keyword.title()[:60], daun]

    if normalize(bersih[0]) != normalize(beranda):
        bersih.insert(0, beranda)

    if len(bersih) < 2:
        bersih.append(daun)

    # Tingkat terakhir harus menyatakan HALAMAN INI, bukan kategorinya.
    #
    # Ini yang tertulis di keterangan fungsi ini sejak awal - "remah
    # yang berhenti di kategori tidak memberi tahu pembaca hasil
    # pencarian halaman apa yang akan dibukanya" - tapi yang
    # menegakkannya cuma hitungan "kurang dari dua tingkat". Begitu
    # tingkat terakhir dibuang karena memuat nama situs, remahnya
    # berhenti di kategori dengan dua tingkat utuh, dan hitungan itu
    # tidak keberatan.
    #
    # Yang disebut kategori: tingkat yang kosakatanya tidak menambah
    # apa pun di luar keyword halaman ini.
    kata_keyword = {k.casefold() for k in re.findall(r"\w+", keyword or "")}
    kata_akhir = {k.casefold() for k in re.findall(r"\w+", bersih[-1])}

    if (
        daun
        and kata_keyword
        and kata_akhir
        and kata_akhir <= kata_keyword
        and normalize(daun) not in {normalize(x) for x in bersih}
    ):
        bersih.append(daun)

    # Panjang jalur mengikuti KEDALAMAN REMAH DI TEMPLATE, bukan
    # angka tetap.
    #
    # Dulu dipatok empat. Kalau template punya lima tingkat, tingkat
    # kelima kebagian nama tingkat keempat - rewrite_breadcrumb
    # mengulang tingkat terakhir untuk sisa yang tidak kebagian - dan
    # yang terbit "... > RTP Slot > RTP Slot". Terukur di halaman
    # BATARATOTO 21 Agustus 2026.
    jumlah = max(2, int(levels or 4))

    bersih = bersih[:jumlah]

    # Tingkat yang kosakatanya keluar dari pembahasan situs slot
    # ditukar bentuk remah yang pantas.
    #
    # Ditegakkan di Python, bukan diserahkan ke prompt. Aturan remah
    # sudah disebutkan di prompt sejak lama dan yang terbit tetap
    # "Pengalaman Bermain" - model 4B menulis remah seperti menulis
    # judul bagian, karena keduanya sama-sama frasa pendek dan cuma
    # satu di antaranya yang punya aturan bentuk.
    #
    # Beranda tidak ikut diperiksa: ia memang bukan kosakata slot, dan
    # ia tingkat yang wajib ada di setiap jalur.
    if niche == "gambling":
        cadangan = breadcrumb_fillers(keyword, brand_name, bersih)
        hasil: list[str] = []

        for nomor, teks in enumerate(bersih):
            if nomor == 0 and normalize(teks) == normalize(beranda):
                hasil.append(teks)
                continue

            if breadcrumb_allowed(teks, keyword, brand_name):
                hasil.append(teks)
                continue

            if cadangan:
                hasil.append(cadangan.pop(0))

        # Jalur yang seluruh tingkatnya tertolak tetap harus punya
        # tingkat sesudah beranda.
        if len(hasil) < 2 and cadangan:
            hasil.append(cadangan.pop(0))

        bersih = hasil

    # Jalur yang lebih pendek daripada tingkat yang tersedia di
    # template ditambah dari daftar bentuk, bukan dibiarkan pendek.
    #
    # Yang membiarkannya pendek berarti menyerahkan sisanya ke
    # rewrite_breadcrumb, dan ia mengulang tingkat terakhir untuk
    # setiap tingkat yang tidak kebagian - "... > RTP Slot > RTP
    # Slot". Disisipkan SEBELUM tingkat terakhir supaya daun jalurnya
    # tetap berdiri di ujung.
    if niche == "gambling" and len(bersih) < jumlah:
        tambahan = breadcrumb_fillers(keyword, brand_name, bersih)

        while len(bersih) < jumlah and tambahan:
            bersih.insert(max(1, len(bersih) - 1), tambahan.pop(0))

    return bersih[:jumlah]


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


# Peran yang isinya kalimat, jadi salah bahasa di situ terbaca
# langsung oleh pembaca.
#
# Nama orang, nama kota, harga, dan label pendek sengaja TIDAK ikut:
# nama produk dan nama orang memang sering berbahasa lain, dan
# mengosongkannya justru menghapus yang benar.
LANGUAGE_ROLES = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "card_title",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
)


def drop_foreign_content(content: dict, region: str = "id") -> tuple[dict, int]:
    """
    Mengosongkan jawaban model yang ditulis dalam bahasa yang salah.

    Slot yang teks lamanya berbahasa lain memang sengaja dibuka untuk
    ditulis ulang - itu gunanya tanda "fresh" di spec. Yang tidak
    diperhitungkan: model 4B yang diperlihatkan contoh berbahasa
    Inggris kadang menjawab dalam bahasa Inggris juga. Terukur pada
    halaman yang benar-benar terbit 22 Agustus 2026, di slot
    keterangan milik template toko:

        Some users noted that the interface remains responsive even
        under weak network conditions.

    Kalimat itu tidak ada di templatenya - model yang menulisnya.

    Dikosongkan, BUKAN dihapus dari daftar. Pasangan tanya-jawab dan
    pasangan judul-kartu dicocokkan lewat nomor urut, jadi menghapus
    satu butir menggeser seluruh pasangan sesudahnya. Slot yang
    isinya kosong jatuh ke penambal bahasa di template_filler, yang
    mengisinya dengan teks seperan dari halaman yang sama.

    Mengembalikan (isi, jumlah yang dikosongkan).
    """
    bahasa = str(region or "id").strip().lower()

    if not bahasa.startswith("id"):
        # Penilai bahasa di sini dibangun untuk halaman Indonesia.
        # Zona lain punya aturannya sendiri dan tidak boleh dinilai
        # dengan alat yang bukan miliknya.
        return content, 0

    hasil = dict(content)
    jumlah = 0

    for peran in LANGUAGE_ROLES:
        nilai = content.get(peran)

        if isinstance(nilai, str):
            if nilai.strip() and foreign_copy(nilai, bahasa, None, None):
                hasil[peran] = ""
                jumlah += 1

        elif isinstance(nilai, list):
            baru = []

            for butir in nilai:
                if (
                    isinstance(butir, str)
                    and butir.strip()
                    and foreign_copy(butir, bahasa, None, None)
                ):
                    baru.append("")
                    jumlah += 1
                else:
                    baru.append(butir)

            if jumlah:
                hasil[peran] = baru

    return hasil, jumlah
