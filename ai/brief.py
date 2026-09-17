"""
Brief kreatif: pilihan pengguna yang mengubah BUNYI dan BENTUK isi
halaman, dipisah dari data yang dikumpulkan pipeline.

Sebelum berkas ini ada, satu-satunya hal yang bisa dipilih pengguna
untuk mempengaruhi tulisan adalah keyword, brand, dan zona. Semua
yang lain dipatok di dalam prompt: satu nada suara, satu jenis
halaman, satu bayangan tentang siapa pembacanya. Itu benar selama
NEIIU cuma dipakai untuk satu macam halaman, dan berhenti benar
begitu halaman yang sama harus terbit sebagai artikel, sebagai
beranda, dan sebagai halaman AMP - tiga hal yang tidak ditulis dengan
cara yang sama.

Aturan yang dipegang seluruh berkas ini: KOSONG BERARTI SEPERTI DULU.
Setiap kolom baru boleh tidak diisi, dan yang tidak diisi tidak
menyumbang satu baris pun ke prompt. Job yang dijalankan tanpa
menyentuh kolom-kolom ini menghasilkan prompt yang identik byte per
byte dengan prompt sebelum berkas ini ada - itu yang membuat seluruh
penyetelan yang sudah terukur tidak ikut bergeser.
"""

import re


# ==========================================================
# NADA TULISAN
# ==========================================================

# Nada ditulis dalam bahasa sasarannya masing-masing, bukan
# diterjemahkan saat dikirim.
#
# Alasannya sama dengan alasan VOICE_RULES dipisah per bahasa di
# ai/language_rules.py: perintah nada yang ditulis dalam bahasa
# Indonesia menyodorkan contoh bentuk kalimat Indonesia ke model yang
# sedang diminta menulis Thai. Untuk urusan nada, contoh bentuk itu
# justru bagian yang paling menular.
TONES: dict[str, dict] = {
    # Nada bawaan. Sengaja TIDAK menyumbang aturan apa pun: yang
    # berlaku aturan bunyi di ai/language_rules.py, yang sudah
    # disetel lewat keluhan-keluhan pengguna sendiri dan sudah
    # berbunyi seperti orang. Menambah blok nada di atasnya cuma
    # membuat dua aturan berebut satu hal yang sama.
    "natural": {
        "label": "Natural (bawaan NEIIU)",
        "rules": {"id": "", "th": ""},
    },
    "santai": {
        "label": "Santai — seperti ngobrol",
        "rules": {
            "id": (
                "- Nadanya SANTAI, seperti sedang menjawab teman yang\n"
                "  bertanya lewat chat. Sapa pembaca dengan \"kamu\".\n"
                "- Kalimatnya pendek-pendek. Boleh ada kalimat yang cuma\n"
                "  tiga kata kalau memang cukup segitu.\n"
                "- Boleh membuka dengan pertanyaan atau dengan kejadian,\n"
                "  bukan selalu dengan definisi."
            ),
            "th": (
                "- น้ำเสียงต้องสบาย ๆ เหมือนตอบเพื่อนที่ทักมาถามในแชท\n"
                "  เรียกผู้อ่านว่า \"คุณ\"\n"
                "- ประโยคสั้น ๆ ประโยคที่มีแค่สามคำก็ใช้ได้ถ้าพอแล้ว\n"
                "- เปิดด้วยคำถามหรือด้วยเหตุการณ์ได้ ไม่ต้องเปิดด้วย\n"
                "  คำนิยามทุกครั้ง"
            ),
        },
    },
    "profesional": {
        "label": "Profesional — rapi tapi tidak kaku",
        "rules": {
            "id": (
                "- Nadanya PROFESIONAL: rapi, tepat, dan tidak berbunga.\n"
                "  Tetap sapa pembaca dengan \"kamu\", bukan \"Anda\n"
                "  sekalian\" - yang diminta rapi, bukan berjarak.\n"
                "- Jangan memakai bahasa gaul dan singkatan chat.\n"
                "- Tiap klaim diikuti keterangan yang membuatnya bisa\n"
                "  diperiksa: caranya, syaratnya, atau kapan berlakunya."
            ),
            "th": (
                "- น้ำเสียงเป็นทางการแบบมืออาชีพ เรียบ ตรง ไม่ประดิษฐ์\n"
                "  ยังเรียกผู้อ่านว่า \"คุณ\" ได้ ที่ต้องการคือความเรียบร้อย\n"
                "  ไม่ใช่ระยะห่าง\n"
                "- ห้ามใช้คำแสลงและคำย่อแบบแชท\n"
                "- ทุกข้อที่กล่าวอ้างต้องตามด้วยรายละเอียดที่ตรวจสอบได้\n"
                "  เช่น วิธีทำ เงื่อนไข หรือช่วงเวลาที่ใช้ได้"
            ),
        },
    },
    "persuasif": {
        "label": "Persuasif — mendorong daftar",
        "rules": {
            "id": (
                "- Nadanya MENDORONG pembaca mengambil langkah, tapi\n"
                "  dorongannya lewat alasan, bukan lewat kata sifat.\n"
                "  \"Daftarnya cuma butuh nomor HP\" mendorong; \"buruan\n"
                "  daftar sekarang juga\" cuma berteriak.\n"
                "- Sebut hambatan yang hilang: apa yang TIDAK perlu\n"
                "  disiapkan pembaca, dan berapa langkah yang tersisa.\n"
                "- Tanda seru paling banyak satu di seluruh halaman.\n"
                "- Tetap tidak boleh menjanjikan pembacanya menang."
            ),
            "th": (
                "- น้ำเสียงต้องกระตุ้นให้ผู้อ่านลงมือ แต่กระตุ้นด้วยเหตุผล\n"
                "  ไม่ใช่ด้วยคำคุณศัพท์ \"สมัครใช้แค่เบอร์มือถือ\" คือการ\n"
                "  กระตุ้น ส่วน \"รีบสมัครเลยตอนนี้\" คือการตะโกนเฉย ๆ\n"
                "- บอกอุปสรรคที่หายไป ผู้อ่านไม่ต้องเตรียมอะไรบ้าง\n"
                "  และเหลืออีกกี่ขั้นตอน\n"
                "- เครื่องหมายอัศเจรีย์ใช้ได้มากที่สุดหนึ่งครั้งทั้งหน้า\n"
                "- ยังคงห้ามสัญญาว่าผู้อ่านจะชนะ"
            ),
        },
    },
    "informatif": {
        "label": "Informatif — menjelaskan lebih dulu",
        "rules": {
            "id": (
                "- Nadanya MENJELASKAN. Yang dikejar pembaca mengerti,\n"
                "  bukan pembaca terbujuk.\n"
                "- Tiap bagian menjawab satu pertanyaan yang benar-benar\n"
                "  ditanyakan orang, dan menjawabnya sampai selesai.\n"
                "- Kalau ada langkah, tulis urut. Kalau ada syarat,\n"
                "  sebutkan semuanya, termasuk yang tidak menguntungkan.\n"
                "- Ajakan mendaftar paling banyak di satu tempat."
            ),
            "th": (
                "- น้ำเสียงเน้นอธิบาย เป้าหมายคือให้ผู้อ่านเข้าใจ\n"
                "  ไม่ใช่ให้ผู้อ่านถูกโน้มน้าว\n"
                "- แต่ละส่วนตอบคำถามที่คนถามกันจริงหนึ่งข้อ และตอบจนจบ\n"
                "- ถ้ามีขั้นตอน ให้เรียงตามลำดับ ถ้ามีเงื่อนไข ให้บอก\n"
                "  ให้ครบ รวมถึงข้อที่ไม่ได้เป็นผลดีด้วย\n"
                "- คำชวนสมัครใส่ได้มากที่สุดหนึ่งจุด"
            ),
        },
    },
}

DEFAULT_TONE = "natural"


# ==========================================================
# TUJUAN HALAMAN
# ==========================================================

# Tujuan halaman mengubah dua hal sekaligus: seberapa padat tulisannya
# dan urutan apa yang didahulukan. Keduanya ditulis sebagai aturan,
# bukan sebagai angka, karena jumlah slot dan panjangnya sudah
# ditentukan template - yang bisa diubah cara mengisinya.
PURPOSES: dict[str, dict] = {
    "landing-page": {
        "label": "Landing page — mendorong daftar",
        "rules": {
            "id": (
                "- Halaman ini LANDING PAGE. Pembacanya datang dari iklan\n"
                "  atau hasil pencarian dan memutuskan dalam hitungan\n"
                "  detik, jadi janji halamannya harus sudah utuh di layar\n"
                "  pertama - di h1 dan paragraf pertama.\n"
                "- Tiap bagian menjawab satu keberatan yang membuat orang\n"
                "  ragu mendaftar, lalu berhenti. Jangan menjelaskan hal\n"
                "  yang tidak menghalangi siapa pun.\n"
                "- Tulis supaya bisa dibaca sambil di-scroll: kalimat\n"
                "  pembuka tiap paragraf sudah memuat isinya."
            ),
            "th": (
                "- หน้านี้คือแลนดิ้งเพจ ผู้อ่านมาจากโฆษณาหรือผลค้นหา\n"
                "  และตัดสินใจภายในไม่กี่วินาที คำสัญญาของหน้าจึงต้อง\n"
                "  ครบตั้งแต่หน้าจอแรก คือใน h1 และย่อหน้าแรก\n"
                "- แต่ละส่วนตอบข้อกังวลที่ทำให้คนลังเลจะสมัครหนึ่งข้อ\n"
                "  แล้วจบ อย่าอธิบายเรื่องที่ไม่ได้ขวางใคร\n"
                "- เขียนให้อ่านได้ระหว่างเลื่อนหน้าจอ ประโยคแรกของ\n"
                "  ทุกย่อหน้าต้องบอกใจความไว้แล้ว"
            ),
        },
    },
    "amp": {
        "label": "AMP — ringkas untuk ponsel",
        "rules": {
            "id": (
                "- Halaman ini versi AMP, dibuka di ponsel lewat jaringan\n"
                "  seluler. Tulis RINGKAS: tiap paragraf langsung ke\n"
                "  isinya di kalimat pertama, tanpa kalimat pengantar.\n"
                "- Kalimat panjang dipecah. Layar ponsel membuat kalimat\n"
                "  tiga baris terbaca seperti enam baris.\n"
                "- Tidak ada bagian yang cuma berfungsi sebagai jembatan.\n"
                "  Kalau satu paragraf bisa dibuang tanpa ada yang\n"
                "  hilang, isinya memang tidak perlu ditulis."
            ),
            "th": (
                "- หน้านี้คือเวอร์ชัน AMP เปิดบนมือถือผ่านเน็ตมือถือ\n"
                "  เขียนให้กระชับ ทุกย่อหน้าเข้าเนื้อหาตั้งแต่ประโยคแรก\n"
                "  ไม่ต้องมีประโยคเกริ่นนำ\n"
                "- ประโยคยาวให้ตัดเป็นท่อน หน้าจอมือถือทำให้ประโยค\n"
                "  สามบรรทัดกลายเป็นหกบรรทัด\n"
                "- ห้ามมีส่วนที่ทำหน้าที่เป็นแค่สะพานเชื่อม ถ้าย่อหน้าไหน\n"
                "  ตัดออกแล้วไม่มีอะไรหายไป ย่อหน้านั้นไม่ต้องเขียน"
            ),
        },
    },
    "homepage": {
        "label": "Beranda — memperkenalkan situs",
        "rules": {
            "id": (
                "- Halaman ini BERANDA. Pembacanya belum tentu tahu situs\n"
                "  ini apa, jadi paragraf pertama menjawab itu lebih dulu\n"
                "  sebelum menjelaskan bagian mana pun.\n"
                "- Cakupannya LEBAR tapi DANGKAL: sebut semua yang ada,\n"
                "  masing-masing satu-dua kalimat, tanpa menuntaskan satu\n"
                "  pun. Halaman lain yang menuntaskannya.\n"
                "- Tiap bagian menamai satu bagian situs dan mengatakan\n"
                "  untuk siapa bagian itu berguna."
            ),
            "th": (
                "- หน้านี้คือหน้าแรกของเว็บ ผู้อ่านอาจยังไม่รู้ว่าเว็บนี้\n"
                "  คืออะไร ย่อหน้าแรกจึงต้องตอบเรื่องนั้นก่อน แล้วค่อย\n"
                "  อธิบายส่วนอื่น\n"
                "- ขอบเขตให้กว้างแต่ตื้น พูดถึงทุกอย่างที่มี อย่างละ\n"
                "  หนึ่งถึงสองประโยค ไม่ต้องลงลึกจนจบสักเรื่อง\n"
                "  ให้หน้าอื่นเป็นคนลงลึก\n"
                "- แต่ละส่วนตั้งชื่อให้ส่วนหนึ่งของเว็บ และบอกว่า\n"
                "  ส่วนนั้นมีประโยชน์กับใคร"
            ),
        },
    },
    "article": {
        "label": "Artikel — menjelaskan topik",
        "rules": {
            "id": (
                "- Halaman ini ARTIKEL. Pembacanya datang untuk MENGERTI,\n"
                "  bukan untuk mendaftar, jadi penjelasannya yang\n"
                "  didahulukan dan ajakan mendaftar berdiri paling\n"
                "  belakang.\n"
                "- Cakupannya SEMPIT tapi DALAM: bahas sedikit hal sampai\n"
                "  tuntas, bukan banyak hal sekilas-sekilas.\n"
                "- Tiap heading adalah pertanyaan yang benar-benar\n"
                "  ditanyakan orang, dan paragraf di bawahnya menjawabnya\n"
                "  sampai selesai - termasuk syarat dan pengecualiannya.\n"
                "- Urutan bagiannya harus bisa dijelaskan: dari yang\n"
                "  paling mendasar ke yang paling khusus."
            ),
            "th": (
                "- หน้านี้คือบทความ ผู้อ่านมาเพื่อทำความเข้าใจ\n"
                "  ไม่ได้มาเพื่อสมัคร คำอธิบายจึงต้องมาก่อน\n"
                "  ส่วนคำชวนสมัครอยู่ท้ายสุด\n"
                "- ขอบเขตให้แคบแต่ลึก อธิบายไม่กี่เรื่องให้จบจริง\n"
                "  ดีกว่าพูดหลายเรื่องแบบผ่าน ๆ\n"
                "- ทุกหัวข้อคือคำถามที่คนถามกันจริง และย่อหน้าใต้หัวข้อ\n"
                "  ต้องตอบจนจบ รวมถึงเงื่อนไขและข้อยกเว้น\n"
                "- ลำดับของหัวข้อต้องอธิบายได้ ไล่จากเรื่องพื้นฐานที่สุด\n"
                "  ไปหาเรื่องเฉพาะที่สุด"
            ),
        },
    },
    "seo-page": {
        "label": "Halaman SEO — mengejar satu keyword",
        "rules": {
            "id": (
                "- Halaman ini dibuat untuk MENJAWAB SATU PENCARIAN\n"
                "  sampai tuntas. Yang menentukan isinya bukan struktur\n"
                "  situs, melainkan apa yang dicari orang yang mengetik\n"
                "  kata itu.\n"
                "- Jawaban atas pencariannya berdiri di paragraf pertama,\n"
                "  bukan disimpan sampai bagian tengah. Pembaca yang\n"
                "  harus menggali dulu akan kembali ke hasil pencarian.\n"
                "- Bagian sesudahnya menjawab pertanyaan lanjutan yang\n"
                "  wajar muncul setelah jawaban pertama dibaca."
            ),
            "th": (
                "- หน้านี้ทำขึ้นเพื่อตอบคำค้นหาเดียวให้จบ สิ่งที่กำหนด\n"
                "  เนื้อหาไม่ใช่โครงสร้างเว็บ แต่คือสิ่งที่คนพิมพ์คำนั้น\n"
                "  กำลังมองหา\n"
                "- คำตอบของคำค้นหาต้องอยู่ในย่อหน้าแรก ไม่ใช่เก็บไว้\n"
                "  กลางหน้า ผู้อ่านที่ต้องขุดหาก่อนจะกดกลับไปที่ผลค้นหา\n"
                "- ส่วนถัดไปตอบคำถามต่อเนื่องที่มักตามมาหลังอ่าน\n"
                "  คำตอบแรกจบ"
            ),
        },
    },
    "brand-page": {
        "label": "Halaman brand — memperkenalkan brand",
        "rules": {
            "id": (
                "- Halaman ini tentang BRANDNYA SENDIRI, bukan tentang\n"
                "  topiknya secara umum. Nama brand jadi subjek kalimat,\n"
                "  bukan cuma disebut sambil lalu.\n"
                "- Yang ditulis: apa yang brand ini kerjakan, untuk siapa,\n"
                "  dan apa yang membuatnya berbeda dari pilihan lain -\n"
                "  perbedaan yang bisa disebutkan, bukan kata sifat.\n"
                "- Kalimat yang tetap benar kalau nama brandnya ditukar\n"
                "  dengan nama lain berarti belum menulis tentang brand\n"
                "  ini. Tulis ulang sampai tidak bisa ditukar."
            ),
            "th": (
                "- หน้านี้พูดถึงตัวแบรนด์เอง ไม่ใช่พูดถึงหัวข้อโดยทั่วไป\n"
                "  ชื่อแบรนด์ต้องเป็นประธานของประโยค ไม่ใช่ถูกเอ่ยผ่าน ๆ\n"
                "- สิ่งที่ต้องเขียน คือแบรนด์นี้ทำอะไร ทำให้ใคร\n"
                "  และต่างจากตัวเลือกอื่นตรงไหน ความต่างที่ระบุได้\n"
                "  ไม่ใช่คำคุณศัพท์\n"
                "- ประโยคที่ยังเป็นจริงอยู่ถ้าสลับไปใช้ชื่อแบรนด์อื่น\n"
                "  แปลว่ายังไม่ได้เขียนถึงแบรนด์นี้ ให้เขียนใหม่จนสลับ\n"
                "  ไม่ได้"
            ),
        },
    },
}

DEFAULT_PURPOSE = "landing-page"


# Berapa keyword pendukung yang ikut ke prompt.
#
# Delapan. Di atas itu daftar keyword berubah fungsi: bukan lagi
# penunjuk topik yang harus disinggung, melainkan daftar yang dikira
# model harus dimasukkan semuanya - dan yang terbit paragraf berisi
# keyword berjejer. Batasnya di sini, bukan di UI, supaya jalur API
# ikut terjaga.
MAX_SECONDARY_KEYWORDS = 8

# Panjang satu keyword pendukung. Yang lebih panjang dari ini bukan
# keyword melainkan kalimat, dan kalimat yang dipaksa muncul utuh di
# dalam paragraf selalu terbaca janggal.
MAX_KEYWORD_LENGTH = 60

# Pemisah keyword: koma, titik koma, baris baru, atau garis lurus.
KEYWORD_SPLIT = re.compile(r"[,;\n|]+")

MAX_AUDIENCE_LENGTH = 300


def parse_keywords(raw) -> list[str]:
    """
    Membaca keyword pendukung dari teks atau daftar.

    Menerima dua bentuk karena dua jalur masuk memang mengirim bentuk
    yang berbeda: formulir web mengirim satu teks berisi beberapa
    baris, sedangkan pemanggil API mengirim daftar.
    """
    if not raw:
        return []

    if isinstance(raw, str):
        potongan = KEYWORD_SPLIT.split(raw)
    else:
        potongan: list[str] = []

        for item in raw:
            potongan.extend(KEYWORD_SPLIT.split(str(item)))

    bersih: list[str] = []
    terlihat: set[str] = set()

    for item in potongan:
        kata = " ".join(str(item).split())

        if not kata or len(kata) > MAX_KEYWORD_LENGTH:
            continue

        # Dibandingkan tanpa memperhatikan huruf besar-kecil. Daftar
        # yang memuat "slot online" dan "Slot Online" menyuruh model
        # menyinggung satu hal dua kali, dan model kecil menurutinya.
        kunci = kata.casefold()

        if kunci in terlihat:
            continue

        terlihat.add(kunci)
        bersih.append(kata)

        if len(bersih) >= MAX_SECONDARY_KEYWORDS:
            break

    return bersih


def normalize_tone(tone: str = "") -> str:
    """
    Kode nada yang dikenal, atau bawaan kalau tidak dikenal.
    """
    kode = str(tone or "").strip().lower()

    return kode if kode in TONES else DEFAULT_TONE


def normalize_purpose(purpose: str = "") -> str:
    """
    Kode tujuan halaman yang dikenal.

    Kosong TIDAK dijatuhkan ke bawaan di sini, melainkan dikembalikan
    apa adanya sebagai string kosong. Bedanya penting: kosong berarti
    "pengguna tidak memilih apa pun, jangan tambahkan aturan tujuan ke
    prompt", sedangkan "landing-page" berarti pengguna memilihnya dan
    aturannya ikut. Menjatuhkan kosong ke bawaan akan menambah blok
    aturan ke setiap job lama yang tidak pernah memilih apa pun.
    """
    kode = str(purpose or "").strip().lower().replace("_", "-")

    return kode if kode in PURPOSES else ""


def build_creative_brief(
    tone: str = "",
    page_purpose: str = "",
    target_audience: str = "",
    secondary_keywords=None,
    language: str = "id",
) -> dict:
    """
    Menyusun brief kreatif satu run dari pilihan pengguna.

    Hasilnya dititipkan di dalam dict brand, sama seperti zona dan
    penanda variasi, karena dict itu sudah sampai ke setiap penyusun
    prompt tanpa satu pun parameter tambahan.
    """
    return {
        "tone": normalize_tone(tone),
        # Disimpan apa adanya supaya bisa dibedakan dari "tidak
        # memilih". Lihat keterangan di normalize_purpose.
        "purpose": normalize_purpose(page_purpose),
        "audience": " ".join(
            str(target_audience or "").split()
        )[:MAX_AUDIENCE_LENGTH],
        "secondary_keywords": parse_keywords(secondary_keywords),
        "language": str(language or "id").strip().lower(),
    }


def empty_brief(language: str = "id") -> dict:
    """
    Brief tanpa satu pilihan pun - perilaku NEIIU sebelum brief ada.
    """
    return build_creative_brief(language=language)


def brief_identity_lines(brief: dict | None) -> str:
    """
    Baris keterangan yang berdiri bersama keyword dan nama brand.

    Ditaruh di kepala brief, bukan di blok aturan, karena isinya
    KETERANGAN tentang halaman ini - sejenis dengan "Keyword utama"
    dan "Bahasa isi halaman" yang sudah ada di situ. Aturan yang
    menyuruh model melakukan sesuatu berdiri di blok terpisah.
    """
    if not brief:
        return ""

    baris: list[str] = []

    kunci_dua = brief.get("secondary_keywords") or []

    if kunci_dua:
        baris.append("Keyword pendukung: " + ", ".join(kunci_dua))

    if brief.get("audience"):
        baris.append(f"Pembaca yang dituju: {brief['audience']}")

    if brief.get("purpose"):
        baris.append(
            "Jenis halaman: "
            + PURPOSES[brief["purpose"]]["label"]
        )

    if not baris:
        return ""

    return "\n".join(baris) + "\n"


def brief_rule_blocks(brief: dict | None, language_code: str = "id") -> str:
    """
    Blok aturan yang lahir dari brief kreatif.

    Dikembalikan sebagai satu teks siap tempel, dan KOSONG kalau
    pengguna tidak memilih apa pun. Teks kosong itu yang menjaga
    prompt job lama tetap sama persis.
    """
    if not brief:
        return ""

    bahasa = str(
        language_code or brief.get("language") or "id"
    ).strip().lower()

    bagian: list[str] = []

    tujuan = brief.get("purpose")

    if tujuan and tujuan in PURPOSES:
        aturan = PURPOSES[tujuan]["rules"].get(bahasa)

        # Bahasa yang belum punya terjemahan aturannya dilewati, bukan
        # dikirim dalam bahasa lain. Aturan berbahasa Indonesia di
        # tengah tugas menulis Thai adalah persoalan yang justru
        # sedang diperbaiki di ai/language_rules.py.
        if aturan:
            bagian.append(
                "\n## Jenis Halaman Yang Sedang Ditulis\n" + aturan
            )

    nada = brief.get("tone")

    if nada and nada in TONES:
        aturan = TONES[nada]["rules"].get(bahasa)

        if aturan:
            bagian.append("\n## Nada Tulisan\n" + aturan)

    pembaca = brief.get("audience")

    if pembaca:
        bagian.append(
            "\n## Siapa Yang Membaca Halaman Ini\n"
            + audience_rules(pembaca, bahasa)
        )

    kunci_dua = brief.get("secondary_keywords") or []

    if kunci_dua:
        bagian.append(
            "\n## Keyword Pendukung\n"
            + secondary_keyword_rules(kunci_dua, bahasa)
        )

    if not bagian:
        return ""

    return "\n".join(bagian) + "\n"


def audience_rules(audience: str, language_code: str = "id") -> str:
    """
    Aturan menulis untuk pembaca yang disebutkan pengguna.

    Keterangan pembacanya sendiri dikutip apa adanya, karena ia
    ditulis pengguna dan bisa dalam bahasa apa pun. Yang diterjemahkan
    perintah di sekitarnya.
    """
    if language_code == "th":
        return (
            f"- ผู้อ่านหน้านี้คือ: {audience}\n"
            "- เขียนถึงคนกลุ่มนี้โดยตรง ใช้คำที่เขาใช้เรียกสิ่งต่าง ๆ เอง\n"
            "  ไม่ใช่คำที่คนในวงการใช้กันเอง\n"
            "- สิ่งที่คนกลุ่มนี้รู้อยู่แล้ว ไม่ต้องอธิบายซ้ำ\n"
            "  ส่วนสิ่งที่เขายังไม่รู้ ต้องอธิบายให้จบ ไม่ใช่เอ่ยผ่าน\n"
            "- ถ้าประโยคไหนใช้ได้กับผู้อ่านกลุ่มไหนก็ได้ แปลว่าประโยคนั้น\n"
            "  ยังไม่ได้เขียนถึงคนกลุ่มนี้"
        )

    return (
        f"- Yang membaca halaman ini: {audience}\n"
        "- Tulis langsung untuk mereka. Pakai kata yang mereka pakai\n"
        "  sendiri untuk menyebut sesuatu, bukan istilah orang dalam.\n"
        "- Yang sudah mereka ketahui tidak perlu dijelaskan lagi. Yang\n"
        "  belum mereka ketahui dijelaskan sampai selesai, bukan\n"
        "  disinggung sambil lalu.\n"
        "- Kalimat yang sama cocoknya untuk pembaca mana pun berarti\n"
        "  belum ditulis untuk mereka."
    )


def secondary_keyword_rules(
    keywords: list[str],
    language_code: str = "id",
) -> str:
    """
    Aturan pemakaian keyword pendukung.

    Yang ditegaskan justru batasnya, bukan kewajibannya. Daftar
    keyword yang dikirim tanpa batas dibaca model kecil sebagai daftar
    yang harus dihabiskan, dan cara termurah menghabiskannya adalah
    menjejerkan semuanya di satu paragraf - persis bentuk yang dikenali
    mesin pencari sebagai penumpukan keyword.

    Yang dilarang cuma TITLE, bukan meta description.

    Versi pertama melarang keduanya, dan model melanggarnya di
    percobaan pertama - meta description yang terbit berbunyi
    "Mainkan game online thailand dengan cepat, deposit dan withdraw
    langsung", dengan keyword pendukung berdiri di tengah kalimat yang
    tetap wajar dibaca. Larangannya yang salah, bukan jawabannya:
    deskripsi punya 140-180 karakter dan satu keyword pendukung di
    dalamnya tidak mendesak apa pun. Title punya 50-70 karakter yang
    sudah dibagi nama brand, tanda pisah, dan janjinya - di situ satu
    keyword tambahan memang mengambil tempat yang bukan miliknya.

    Aturan yang dilanggar dan didiamkan lebih buruk daripada aturan
    yang tidak ada: ia mengajari model bahwa daftar larangan di
    sekitarnya juga boleh ditawar.
    """
    daftar = "\n".join(f"  - {kata}" for kata in keywords)

    if language_code == "th":
        return (
            "คำค้นหารองของหน้านี้:\n"
            f"{daftar}\n"
            "- แต่ละคำใช้ได้มากที่สุดหนึ่งครั้งในทั้งหน้า และต้องอยู่ใน\n"
            "  ประโยคที่ต่อให้ไม่มีคำนั้นก็ยังอ่านรู้เรื่อง\n"
            "- ไม่จำเป็นต้องใช้ให้ครบทุกคำ คำที่ยัดเข้าไปแบบฝืน ๆ\n"
            "  เสียหายมากกว่าคำที่ไม่ได้ใช้\n"
            "- ห้ามเอาหลายคำมาเรียงต่อกันในประโยคเดียว\n"
            "- ห้ามใส่ใน title เด็ดขาด title มีที่แค่ 50-70 ตัวอักษร\n"
            "  ซึ่งแบ่งให้ชื่อแบรนด์ เครื่องหมายคั่น และคำสัญญาไปหมดแล้ว\n"
            "  ส่วนใน meta description ใส่ได้หนึ่งคำถ้ามันเข้ากับประโยค\n"
            "- คำเหล่านี้คือหัวข้อที่ควรแตะถึง ไม่ใช่ข้อความที่ต้องคัดลอก\n"
            "  รูปคำที่เปลี่ยนไปตามประโยคถือว่าใช้แล้ว"
        )

    return (
        "Keyword pendukung halaman ini:\n"
        f"{daftar}\n"
        "- Tiap keyword paling banyak dipakai SATU KALI di seluruh\n"
        "  halaman, dan harus berdiri di kalimat yang tetap masuk akal\n"
        "  seandainya keyword itu tidak ada.\n"
        "- Tidak wajib dipakai semuanya. Keyword yang dipaksa masuk\n"
        "  lebih merugikan daripada keyword yang tidak terpakai.\n"
        "- Jangan menjejerkan dua keyword dalam satu kalimat.\n"
        "- JANGAN dipakai di title. Title cuma punya 50-70 karakter\n"
        "  dan itu sudah habis dibagi nama brand, tanda pisah, dan\n"
        "  janjinya - keyword tambahan di situ mengambil tempat milik\n"
        "  keyword utama. Di meta description boleh satu, kalau\n"
        "  memang jatuh wajar di dalam kalimatnya.\n"
        "- Ini penunjuk TOPIK yang perlu disinggung, bukan teks yang\n"
        "  harus disalin. Bentuk katanya boleh berubah mengikuti\n"
        "  kalimatnya, dan itu tetap dihitung terpakai."
    )


def tone_options() -> list[dict]:
    """
    Daftar nada untuk formulir. Urutannya urutan yang ditampilkan.
    """
    return [
        {"code": kode, "label": isi["label"]}
        for kode, isi in TONES.items()
    ]


def purpose_options() -> list[dict]:
    """
    Daftar tujuan halaman untuk formulir.
    """
    return [
        {"code": kode, "label": isi["label"]}
        for kode, isi in PURPOSES.items()
    ]
