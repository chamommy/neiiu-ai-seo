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
from datetime import datetime, timedelta

from ai.manager import AIManager
from ai.neiiu_prompts import (
    build_content_plan_prompt,
    build_serp_insight_prompt,
    build_template_content_prompt,
    pick_style_examples,
)
from generators.content_batches import (
    answer_chars,
    merge_batch_content,
    plan_batches,
)
from generators.brand_swap import normalize
from generators.template_filler import (
    LIST_ROLES,
    balance_paired_roles,
    build_dynamic_schema,
    fit_content_to_spec,
    scale_spec,
)
from ai.schemas import (
    CONTENT_PLAN_SCHEMA,
    META_MAX,
    SERP_INSIGHT_SCHEMA,
    TITLE_MAX,
)
from config import (
    AI_CONTEXT_LENGTH,
    AI_MAX_TOKENS_INSIGHT,
    AI_MAX_TOKENS_PLAN,
    AI_MODEL,
    AI_PROVIDER,
)
from utils.region import format_date, get_region, iso_date, slug_for_url
from utils.text import (
    THAI_RANGE,
    content_shingles,
    content_tokens,
    count_words,
    display_width,
    drop_dangling,
    estimate_tokens,
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
    riwayat: dict | None = None,
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
    contoh_gaya = {
        # Argumennya harus PERSIS sama dengan yang dipakai
        # build_template_content_prompt - keyword mentah, nama brand
        # yang sudah di-strip, penanda run apa adanya - karena
        # ketiganya masuk ke benih pemilihnya. Beda satu spasi saja,
        # yang diperiksa di sini bukan contoh yang dilihat model.
        peran: pick_style_examples(
            analysis["keyword"],
            brand.get("site_name", "").strip(),
            slot=peran,
            variation=brand.get("variation", ""),
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
    ) -> dict:
        """
        Satu permintaan ke model untuk satu potongan kebutuhan.

        "sudah" boleh ditimpa dari luar, dan itu yang dipakai giliran
        ulang. terkumpul baru diisi SESUDAH satu giliran tuntas, jadi
        permintaan susulan yang memakainya apa adanya berangkat tanpa
        tahu apa yang barusan ditulisnya sendiri.
        """
        system_prompt, user_prompt = build_template_content_prompt(
            analysis=analysis,
            insight=insight,
            spec=bagian,
            brand=brand,
            sudah=terkumpul if sudah is None else sudah,
            riwayat=riwayat,
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
        )

    for nomor, bagian in enumerate(batches, start=1):
        raw = minta(bagian, nomor)

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

            catat(
                on_progress,
                f"Giliran {nomor}: "
                + ", ".join(
                    f"{peran} kurang {len(lubang)}"
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

        def judul_buruk(teks) -> float:
            """
            Dua alasan judul ditolak, dinyatakan dalam satu angka.

            Keduanya kelipatan ambangnya masing-masing, jadi 1.0
            berarti "tepat di batas" untuk alasan apa pun dan satu
            putaran ulang menutup dua-duanya sekaligus. Sebelumnya
            keduanya butuh putaran sendiri-sendiri, dan itu berarti
            judul yang kena dua-duanya membayar dua kali giliran
            model untuk satu baris teks.
            """
            mengulang = max(
                (echo_score(teks, lama) for lama in judul_lama),
                default=0.0,
            )

            return max(
                mengulang / TITLE_REPEAT_LIMIT,
                style_copy_score(
                    teks,
                    contoh_gaya.get("title") or [],
                    brand.get("site_name", ""),
                ),
            )

        if "title" in bagian and str(isi.get("title") or ""):
            terbaik = str(isi["title"])
            nilai_terbaik = judul_buruk(terbaik)

            for putaran in range(TITLE_REPEAT_RETRIES):
                if nilai_terbaik < 1.0:
                    break

                catat(
                    on_progress,
                    f"Giliran {nomor}: judulnya mengulang judul halaman "
                    "sebelumnya atau menyalin contoh gayanya; diminta "
                    f"lagi ({putaran + 1}/{TITLE_REPEAT_RETRIES}).",
                )

                ulangan = minta({"title": bagian["title"]}, nomor, ulang=True)

                baru, _ = fit_content_to_spec(
                    ulangan,
                    {"title": bagian["title"]},
                    fallbacks or {},
                )

                calon = str(baru.get("title") or "")

                if not calon:
                    continue

                nilai = judul_buruk(calon)

                if nilai < nilai_terbaik:
                    terbaik = calon
                    nilai_terbaik = nilai

            isi["title"] = terbaik

            if nilai_terbaik >= 1.0:
                warnings.append(
                    "Judul masih mirip judul halaman sebelumnya atau "
                    "contoh gayanya walau sudah diminta "
                    f"{TITLE_REPEAT_RETRIES + 1} kali; yang dipakai "
                    "yang paling sedikit mengulang."
                )

        judul = (terkumpul.get("title") or [""])[0]

        # Yang dibandingkan bukan cuma judul halaman ini, tapi juga
        # deskripsi halaman-halaman sebelumnya. Dua alasan yang
        # berbeda, satu mesin yang sama: deskripsi yang mengulang
        # judulnya sendiri membuang baris yang seharusnya memberi
        # alasan mengklik, sedangkan deskripsi yang mengulang halaman
        # lain membuat dua halaman berebut kata kunci yang sama.
        acuan_desc = [judul] if judul else []

        acuan_desc += [
            str(x)
            for x in (riwayat or {}).get("meta_description", [])
            if str(x).strip()
        ]

        def gema_desc(teks) -> float:
            # Dua alasan, satu angka. Keduanya sudah dinyatakan sebagai
            # kelipatan ambangnya masing-masing, jadi bisa diadu di
            # satu tempat dan satu putaran ulang menutup dua-duanya.
            return max(
                max(
                    (echo_score(teks, acuan) for acuan in acuan_desc),
                    default=0.0,
                ),
                style_copy_score(
                    teks,
                    contoh_gaya.get("meta_description") or [],
                    brand.get("site_name", ""),
                ),
            )

        if "meta_description" in bagian and gema_desc(
            isi.get("meta_description")
        ) >= 1.0:
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
                catat(
                    on_progress,
                    f"Giliran {nomor}: deskripsi mengulang judulnya "
                    "sendiri, deskripsi halaman lain, atau contoh "
                    f"gayanya; diminta lagi "
                    f"({putaran + 1}/{DESC_ECHO_RETRIES}).",
                )

                ulangan = minta(
                    {"meta_description": bagian["meta_description"]},
                    nomor,
                    ulang=True,
                )

                baru, _ = fit_content_to_spec(
                    ulangan,
                    {"meta_description": bagian["meta_description"]},
                    fallbacks or {},
                )

                calon = str(baru.get("meta_description") or "")

                if not calon:
                    continue

                nilai = gema_desc(calon)

                if nilai < nilai_terbaik:
                    terbaik = calon
                    nilai_terbaik = nilai

                if nilai_terbaik < 1.0:
                    break

            isi["meta_description"] = terbaik

            if nilai_terbaik >= 1.0:
                warnings.append(
                    "Deskripsi masih mengulang judulnya sendiri, "
                    "deskripsi halaman sebelumnya, atau contoh gayanya "
                    f"walau sudah diminta {DESC_ECHO_RETRIES + 1} kali; "
                    "yang dipakai jawaban yang paling sedikit mengulang."
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
        )

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

    content["_metadata"] = metadata

    return content, warnings


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
                "batches": jumlah,
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

        hasil[role] = ensure_identity(
            teks,
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
            )

    return hasil


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


def style_copy_score(teks, contoh: list[str], brand: str) -> float:
    """
    Seberapa jauh sebuah jawaban menyalin contoh gaya yang dilihatnya.

    Dinyatakan sebagai KELIPATAN AMBANG, sama seperti echo_score, jadi
    dua ukuran yang berbeda satuannya bisa diadu di satu tempat.
    """
    badan = content_shingles(bare_style(teks, brand))

    if not badan or not contoh:
        return 0.0

    tertinggi = 0.0

    for satu in contoh:
        lain = content_shingles(bare_style(satu, brand))

        if not lain:
            continue

        tertinggi = max(tertinggi, len(badan & lain) / len(badan | lain))

    return tertinggi / STYLE_COPY_LIMIT


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


# Peran bertekstunggal yang kekosongannya diminta ulang.
#
# Cuma dua, dan keduanya karena teks lamanya ikut dikirim sebagai
# cetakan bentuk. Peran tunggal lain tidak punya contoh yang bisa
# disalin, jadi kosongnya berarti model memang tidak menjawab - dan
# itu sudah tercatat sebagai peringatan tersendiri.
SINGLE_RETRY_ROLES = ("title", "meta_description")


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
            if role in SINGLE_RETRY_ROLES and not str(
                isi.get(role) or ""
            ).strip():
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

        for kunci in ("samples", "budgets", "floors", "partners"):
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
            peta = dict(hasil.get("_by_old") or {})

            for peran, pasangan in (tambahan or {}).items():
                peta[peran] = {**peta.get(peran, {}), **pasangan}

            hasil["_by_old"] = peta
            continue

        if role.startswith("_") or role not in sisa:
            continue

        if not isinstance(tambahan, list):
            # Peran bertekstunggal: jawabannya satu string, dan yang
            # diminta ulang cuma yang tadinya kosong - jadi apa pun
            # yang datang sekarang lebih baik daripada yang ada.
            if role in SINGLE_RETRY_ROLES and str(tambahan or "").strip():
                hasil[role] = tambahan

            continue

        daftar = list(hasil.get(role) or [])
        daftar += [""] * (spec[role]["count"] - len(daftar))

        for urutan, posisi in enumerate(sisa[role].get("positions", [])):
            if urutan >= len(tambahan):
                break

            teks = str(tambahan[urutan]).strip()

            if not teks or posisi >= len(daftar):
                continue

            # Yang lebih panjang yang dipakai.
            #
            # Lubang di sini ada dua macam: slot yang benar-benar
            # kosong, dan slot yang terisi tapi jauh lebih pendek dari
            # jatahnya. Untuk yang pertama apa pun jawabannya menang,
            # karena yang lama memang kosong. Untuk yang kedua, giliran
            # ulang yang kebetulan menjawab lebih pendek lagi akan
            # menukar teks pendek dengan teks yang lebih pendek - satu
            # permintaan ke model yang membuat halamannya lebih buruk.
            if len(teks) <= len(str(daftar[posisi]).strip()):
                continue

            daftar[posisi] = tambahan[urutan]

        hasil[role] = daftar

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

# Tanda pisah yang berdiri lepas di tengah judul, yaitu yang diapit
# spasi atau menempel di ujung kata. Tanda hubung hanya dihitung
# kalau diapit spasi, supaya "anti-rungkad" tidak ikut terbelah.
LOOSE_MARK = re.compile(r"\s+[|:>~@#$•·–—]\s*|\s*[|:>~@#$•·–—]\s+|\s+-\s+")

# Karakter yang tidak boleh menempel di awal atau akhir sisa judul.
EDGE_MARKS = " |:>~@#$•·–—-,.;!"

# Tanda yang menempel ke nama situs tanpa spasi di depannya. Titik dua
# yang didahului spasi terbaca sebagai salah ketik, sedangkan garis
# tegak dan emoji justru butuh ruang di kedua sisinya.
TIGHT_MARKS = {":"}


def title_separator(brand: str, keyword: str) -> str:
    """
    Memilih satu tanda pisah untuk judul halaman ini.

    Dipilih dari nama brand dan keywordnya, bukan diacak: dua halaman
    untuk brand yang sama memakai tanda yang sama, dan menjalankan
    ulang keyword yang sama tidak menghasilkan judul berbeda bentuk.
    """
    benih = hashlib.sha1(
        f"{brand.strip().casefold()}|{keyword.strip().casefold()}".encode(
            "utf-8"
        )
    ).hexdigest()

    return TITLE_MARKS[int(benih[:8], 16) % len(TITLE_MARKS)]


def enforce_title_shape(
    title: str,
    keyword: str,
    brand: str,
    limit: int,
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
    """
    clean = " ".join(str(title or "").split())
    nama = str(brand or "").strip()

    if not clean or not nama:
        return clean

    cocok = re.search(re.escape(nama), clean, re.I)

    if cocok:
        # Kata sambung yang tadinya menempel ke nama situs ikut
        # dibuang. Tanpa itu, "Rahasia Spin di TIMAH33 yang Membuka
        # Peluang" berpindah jadi "TIMAH33 | Rahasia Spin di yang
        # Membuka Peluang".
        depan = drop_dangling(clean[:cocok.start()].strip(), True)
        sisa = f"{depan} {clean[cocok.end():].strip()}"
    else:
        sisa = clean

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

    tanda = title_separator(nama, keyword)

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

        name = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()[:40]
        text = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()[:600]

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

    # Plafonnya satu angka dari awal sampai akhir.
    #
    # Dulu ada tiga angka berbeda di lima baris ini: title dipangkas ke
    # 70, lalu ke 62 waktu nama brand ditambal, sementara deskripsi
    # dipangkas ke 165 lalu ke 160. Angka terkecil yang menang, dan
    # yang terbit adalah title 62 karakter - di bawah lantai yang
    # diminta, dipotong oleh baris yang tugasnya bukan memotong.
    title = clean_text(plan.get("title"), TITLE_MAX) or (
        f"{keyword.title()} — Panduan Lengkap"
    )

    title = ensure_identity(title, keyword, brand_name, TITLE_MAX)
    title = enforce_title_shape(title, keyword, brand_name, TITLE_MAX)

    h1 = clean_text(plan.get("h1"), 90) or title
    h1 = ensure_identity(h1, keyword, brand_name, 90)

    meta = ensure_keyword(
        clean_text(plan.get("meta_description"), META_MAX),
        keyword,
        META_MAX,
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
        "reviews": normalize_reviews(plan.get("reviews"), region),
        "ratings": normalize_ratings(plan.get("ratings")),
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
