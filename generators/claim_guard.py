"""
Membuang klaim yang tidak dipunyai pipeline dari teks yang sudah
ditulis model.

Aturan promptnya sudah ada dan sudah tegas - brand_confidence_rules
menyebutkan satu per satu apa yang tidak boleh: jumlah member, tahun
berdiri, nomor lisensi, angka RTP, winrate, lama proses dalam detik.
Model 4B mengikutinya kebanyakan waktu, dan "kebanyakan waktu" bukan
ukuran yang berguna untuk halaman yang terbit tanpa dibaca orang
lebih dulu.

Terukur 14 Agustus 2026, permintaan feature-boxes
dengan seluruh aturan itu terpasang di prompt: kotak kedua terbit
berbunyi "Transaksi terjadi dalam hitungan detik, tanpa perlu
menunggu konfirmasi tambahan." Lama proses dalam satuan waktu,
persis yang dilarang, di permintaan pertama.

Ini alasan yang sama dengan enforce_title_shape dan strip_figures:
aturan yang cuma ditulis di prompt diikuti model kadang-kadang saja,
dan yang harus benar setiap kali ditegakkan di Python.

Yang dibuang FRASANYA, bukan kalimatnya - kecuali untuk janji
kemenangan, yang tidak bisa diselamatkan dengan membuang sepotong
kata. "Transaksi diproses dalam hitungan detik" jadi "Transaksi
diproses", yang masih menyatakan hal yang sama tanpa mengarang
angkanya.
"""

import re

from utils.text import finish_clause

# Kata yang menandai kalimatnya sedang berbicara tentang PROSES
# layanan, bukan tentang hal lain yang kebetulan punya durasi.
#
# Pembatas ini yang memisahkan pembuangan dari perusakan. Tanpanya,
# halaman toko roti yang menulis "dipanggang 20 menit" ikut
# kehilangan durasinya - dan itu bukan klaim yang tidak dipunyai
# pipeline, melainkan keterangan resep yang memang benar.
PROCESS_WORDS_ID = (
    r"proses|diproses|memproses|transaksi|deposit|withdraw|wd|"
    r"penarikan|pencairan|cair|verifikasi|pendaftaran|mendaftar|"
    r"respon|balasan|dibalas|pengiriman|dikirim|masuk|selesai|"
    r"konfirmasi|dikonfirmasi|pembayaran|dibayar|"
    # Bentuk Indonesia dari "deposit", yang sudah ada di atas dalam
    # bentuk Inggrisnya. Ketiadaannya membuat kalimat yang sama
    # persis maknanya lolos hanya karena memakai kata Indonesia:
    # "Proses deposit hanya butuh 1 detik" tersapu, "Setor dana
    # hanya butuh 1 detik" tidak.
    r"setor|menyetor|setoran|penyetoran|top ?up|isi saldo|isi ulang"
)

PROCESS_WORDS_TH = (
    r"ฝาก|ถอน|โอน|ทำรายการ|สมัคร|ยืนยัน|ดำเนินการ|ตอบกลับ|จ่าย|"
    r"เข้าบัญชี|เสร็จ"
)

# Frasa durasi. Yang ditangkap seluruh frasanya termasuk kata
# pengantarnya, supaya yang tersisa sesudah dibuang tetap kalimat -
# membuang "2 detik" saja meninggalkan "diproses dalam".
# Kata pengantar durasi boleh berantai - "dalam waktu kurang dari 5
# menit" adalah tiga lapis pengantar sebelum angkanya. Dibiarkan
# berlapis di sini supaya yang tersisa sesudah dibuang bukan "dalam
# waktu" yang menggantung tanpa keterangan.
# Kata pengantar durasi, satu daftar yang boleh BERULANG.
#
# Dulu tiap lapis punya slotnya sendiri dan urutannya dipatok:
# pengantar, lalu "waktu", lalu "kurang dari", lalu "hitungan". Bentuk
# yang tidak mengikuti urutan itu lolos, dan yang tersisa sesudah
# angkanya dibuang adalah kalimat yang rusak. Terukur 14 Agustus 2026
# di teks template job 67:
#
#   "deposit QRIS instan hanya dalam 1 detik"
#     -> "deposit QRIS instan hanya."     ("dalam 1 detik" saja yang
#                                          kena, "hanya" ditinggal)
#   "diproses hanya dalam hitungan sekitar 1 detik"
#     -> tidak kena sama sekali           ("sekitar" berdiri SESUDAH
#                                          "hitungan")
#
# Satu daftar berulang menutup keduanya tanpa perlu menebak urutan.
# Kata yang mengantar sebuah durasi.
#
# Kata KEBUTUHAN ikut di sini - butuh, memerlukan, makan waktu -
# karena bentuk itu yang paling sering dipakai menjanjikan kecepatan
# tanpa menyebut prosesnya sama sekali. Terukur di halaman terbit 15
# Agustus 2026: "Setor dana lewat QRIS hanya butuh 1 detik setelah
# konfirmasi" lolos utuh, sementara "Proses deposit hanya butuh 1
# detik" tersapu - bedanya cuma kata "proses", dan janjinya sama
# persis. Rantai pengantarnya putus di "butuh", jadi polanya tidak
# pernah sampai ke angkanya.
DURATION_LEAD_ID = (
    r"(?:(?:dalam|hanya|cuma|sekitar|kira-kira|paling lama|maksimal|"
    r"kurang dari|tidak sampai|di bawah|tak sampai|waktu|hitungan|"
    r"butuh|membutuhkan|memerlukan|perlu|makan waktu|memakan waktu|"
    r"selesai dalam|tinggal)\s+)"
)

# Angka yang ditulis sebagai KATA, bukan sebagai digit.
#
# Ini lubang yang terbit di halaman jadi, dua kali di dua run berbeda.
# Bagian angka pola durasi hanya mengenali digit, jadi untuk "saldo
# masuk dalam dua detik" yang tercabut cuma kata "detik" - satuannya -
# dan yang tertinggal:
#
#     Setor QRIS pukul 16.30, saldo masuk dalam dua.
#
# Kalimat yang berhenti di tengah keterangan. Bentuk digitnya sudah
# benar sejak awal ("dalam 2 detik" tersapu utuh), jadi yang salah
# bukan mesinnya melainkan satu kelas masukan yang tidak pernah
# terpikir - dan model kecil memang lebih sering menulis angka kecil
# sebagai kata.
#
# Daftarnya berhenti di sepuluh plus beberapa kata jumlah yang samar.
# Angka di atas sepuluh hampir selalu ditulis sebagai digit, dan
# menambahkan "puluh", "ratus", "ribu" ke sini justru berisiko:
# ketiganya juga bagian dari harga barang.
NUMBER_WORD_ID = (
    r"(?:satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh|"
    r"sebelas|belasan|beberapa|sekejap|sepersekian|hitungan)"
)

# Satuan waktu yang diikuti angka atau bagian hari: itu penunjuk
# JAM, bukan lama proses.
#
# Terukur pada halaman yang terbit 30 Agustus 2026:
#
#   ditulis : Saya setor dari ponsel jam dua pagi dan saldo saya masuk
#   terbit  : Saya setor dari ponsel dua pagi dan saldo saya masuk
#
# "jam" tercabut karena ia satuan waktu yang berdiri dekat kata
# "setor", dan angka di pola ini dicari SEBELUM satuannya - sedangkan
# di penunjuk jam angkanya justru sesudah. Yang tersisa kalimat yang
# kehilangan kata depannya, dan pembaca melihat "setor dari ponsel dua
# pagi".
#
# Ditulis sebagai lookahead, bukan sebagai daftar pengecualian: yang
# membedakan bukan kata mana yang dipakai melainkan di sebelah mana
# angkanya berdiri.
CLOCK_AFTER = (
    r"(?!\s*(?:\d|" + NUMBER_WORD_ID + r"|pagi|siang|sore|malam|"
    r"wib|wita|wit)\b)"
)

DURATION_ID = re.compile(
    r"\s*" + DURATION_LEAD_ID + r"*"
    r"(?:(?:\d+[.,]?\d*|" + NUMBER_WORD_ID + r")\s*)?"
    r"(?:detik|menit|jam)\b" + CLOCK_AFTER,
    re.IGNORECASE,
)

DURATION_TH = re.compile(
    r"\s*(?:ภายใน|ไม่ถึง|ไม่เกิน|เพียง|แค่|ประมาณ)?\s*"
    r"(?:\d+[.,]?\d*\s*)?"
    r"(?:วินาที|นาที|ชั่วโมง)"
)

# Seberapa jauh ke belakang kata proses dicari dari frasa durasinya.
#
# Dihitung dalam karakter, di dalam kalimat yang sama. Delapan puluh
# kira-kira selebar satu klausa; lebih jauh dari itu yang tertangkap
# kata proses milik kalimat sebelahnya.
PROCESS_WINDOW = 80

PROCESS_NEAR_ID = re.compile(PROCESS_WORDS_ID, re.IGNORECASE)
PROCESS_NEAR_TH = re.compile(PROCESS_WORDS_TH)

# Kata kerja "kami menghubungi kamu", terpisah dari daftar proses di
# atas karena syarat durasinya lebih ketat - lihat di bawah.
#
# Terukur 14 Agustus 2026 pada job 65, halaman terbit dengan kalimat:
#
#   NAGAJITU akan menghubungi kamu dalam waktu 15 menit untuk
#   memverifikasi ulang proses deposit.
#
# Janji lama respons, persis jenis klaim yang dilarang, dan lolos
# karena "menghubungi" tidak ada di daftar proses. Kata "proses" di
# kalimat itu ada, tapi berdiri SESUDAH durasinya, sedangkan yang
# dicari cuma ke belakang.
RESPONSE_WORDS_ID = (
    r"menghubungi|hubungi|dihubungi|menghubungkan|"
    r"merespons|merespon|direspons|direspon|"
    r"menjawab|dijawab|membalas|balas"
)

RESPONSE_NEAR_ID = re.compile(RESPONSE_WORDS_ID, re.IGNORECASE)

# Durasi yang WAJIB punya kata pengantar, dipakai khusus bersama
# daftar respons di atas.
#
# Bedanya dengan DURATION_ID ada di kata pengantarnya yang tidak
# opsional, dan itu yang memisahkan dua kalimat yang bentuknya mirip:
#
#   janji     : dihubungi DALAM WAKTU 15 menit   -> dibuang
#   ketersediaan: bisa dihubungi 24 jam          -> dibiarkan
#
# Yang kedua bukan janji lama proses melainkan keterangan jam buka,
# dan membuangnya berarti menyapu kalimat yang benar. Halaman Thai
# yang sudah lulus uji memakai bentuk itu ("พร้อมรับการติดต่อตลอด 24
# ชั่วโมง"), jadi memperlebar aturannya justru merusak yang lulus.
DURATION_LEADIN_ID = re.compile(
    r"\s*" + DURATION_LEAD_ID + r"+"
    r"(?:(?:\d+[.,]?\d*|" + NUMBER_WORD_ID + r")\s*)?"
    r"(?:detik|menit|jam)\b" + CLOCK_AFTER,
    re.IGNORECASE,
)

# Angka yang berdiri SENDIRI, bukan ekor sebuah kata.
#
# Nama brand yang berakhir angka adalah bentuk paling umum di bidang
# ini - SIAM123, X7GAMING88, JUHI88 - dan tanpa penjaga ini angka di
# ujung namanya terbaca sebagai jumlah orang begitu kata sesudahnya
# kebetulan "pemain" atau "member". Terukur pada berkas AMP yang
# benar-benar terbit, output/siam123-slot-gacor-20260819_054058:
#
#   "SIAM123 Pemain baru bisa daftar..."
#     -> dilaporkan klaim "123 Pemain"
#     -> disapu jadi "SIAM baru bisa daftar..."
#
# Yang dirusak bukan cuma satu kalimat melainkan NAMA BRANDNYA, oleh
# penjaga yang tugasnya justru menjaga halaman. Penyapu klaim adalah
# lapis terakhir yang menyentuh teks, jadi tidak ada satu pun pemulih
# ejaan brand sesudahnya yang sempat mengembalikannya.
#
# Huruf DAN angka sama-sama menghalangi, karena angka yang didahului
# angka masih berada di tengah token yang sama - tanpa syarat itu
# "123" ditolak lalu "23" yang diambil, dan kalimatnya tetap rusak.
NOT_MID_TOKEN = r"(?<!\w)"

# Klaim yang frasanya dibuang apa adanya, tanpa syarat kata di
# dekatnya. Semuanya angka yang tidak dipunyai siapa pun di pipeline
# ini.
FIGURE_CLAIMS = (
    # jumlah member, pemain, pengguna
    re.compile(
        r"\s*(?:lebih dari|di atas|hingga|sampai|sudah|telah)?\s*"
        + NOT_MID_TOKEN
        + r"\d[\d.,]*\s*(?:\+|juta|ribu|rb|k)?\s*"
        r"(?:member|anggota|pemain|pengguna|user|nasabah|pelanggan)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s*(?:ผู้เล่น|สมาชิก|ผู้ใช้|ลูกค้า)\s*"
        r"(?:กว่า|มากกว่า|ถึง)?\s*\d[\d.,]*\s*(?:คน|ราย)?"
    ),
    # Tahun berdiri.
    #
    # Bentuk terpanjang ditulis lebih dulu. Alternation regex memilih
    # yang PERTAMA cocok, bukan yang terpanjang, jadi "sejak" di
    # depan daftar akan menyisakan kata "berdiri" menggantung tanpa
    # keterangan waktunya.
    re.compile(
        r"\s*(?:sudah ada sejak|beroperasi sejak|hadir sejak|"
        r"berdiri sejak|berdiri (?:pada )?tahun|"
        r"didirikan (?:pada )?(?:tahun )?|sejak)\s*"
        r"(?:tahun\s*)?(?:19|20)\d{2}\b",
        re.IGNORECASE,
    ),
    re.compile(r"\s*(?:ตั้งแต่ปี|ก่อตั้งปี|เปิดให้บริการตั้งแต่ปี)\s*\d{4}"),
    # nomor lisensi
    re.compile(
        r"\s*(?:no\.?|nomor|nomer)?\s*lisensi\s*"
        r"(?:no\.?|nomor|#)?\s*[\w/-]*\d[\w/-]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s*lisensi\s*(?:no\.?|nomor|#)\s*[\w/-]+",
        re.IGNORECASE,
    ),
    re.compile(r"\s*ใบอนุญาต(?:เลขที่|หมายเลข)\s*[\w/-]+"),
    # RTP dan winrate berangka
    re.compile(
        r"\s*(?:rtp|win\s*rate|winrate)\s*"
        r"(?:sebesar|hingga|mencapai|di atas|rata-rata)?\s*"
        r"\d+[.,]?\d*\s*%?",
        re.IGNORECASE,
    ),
    # RTP yang angkanya TIDAK menempel ke katanya.
    #
    # Pola di atas menuntut angkanya berdiri langsung sesudah "RTP",
    # dengan paling banyak satu kata penghubung di antaranya. Dua kata
    # sudah cukup membuatnya lolos utuh, dan bentuk dua kata itulah
    # yang paling sering ditulis model: "RTP hari ini mencapai 98,7%"
    # terbit apa adanya, dengan laporan nol klaim dibuang.
    #
    # Menuntut tanda persen, tidak seperti pola di atas. Tanpa syarat
    # itu, jarak 32 karakter membuat "RTP" mencaplok angka apa pun
    # yang kebetulan lewat di kalimat yang sama - termasuk harga
    # barang dan jumlah permainan.
    re.compile(
        r"\s*(?:rtp|win\s*rate|winrate)\b[^.!?\n]{0,32}?\d+[.,]?\d*\s*%",
        re.IGNORECASE,
    ),
    # Persentase yang menerangkan HASIL, urutan mana pun.
    # "98% pemain menang", "menang hingga 95%".
    re.compile(
        r"\s*\d+[.,]?\d*\s*%[^.!?\n]{0,24}?"
        r"(?:menang|gacor|untung|cuan|jackpot|jp|profit|berhasil)"
        r"|\s*(?:menang|gacor|untung|cuan|jackpot|jp|profit)"
        r"[^.!?\n]{0,24}?\d+[.,]?\d*\s*%",
        re.IGNORECASE,
    ),
    # jumlah penghargaan
    re.compile(
        r"\s*" + NOT_MID_TOKEN + r"\d+\s*(?:penghargaan|award|piagam)\b",
        re.IGNORECASE,
    ),
    # Angka bersatuan teknis.
    #
    # Terbit 30 Agustus 2026, lolos utuh dengan laporan nol klaim:
    #
    #   "berjalan lancar bahkan saat jaringan stabil di bawah 50 kbps"
    #
    # Bentuknya sama persis dengan klaim berangka yang lain - sebuah
    # ukuran yang terdengar teliti, yang tidak bisa dibuktikan
    # pipeline, dan yang tidak ada di halaman kompetitor mana pun
    # sebagai fakta. Bedanya cuma satuannya bukan satuan waktu atau
    # orang, jadi tidak satu pun pola di atas melihatnya.
    #
    # Satuan mata uang sengaja TIDAK ikut. Harga barang memang boleh
    # berdiri di halaman ini dan sudah punya jalurnya sendiri - lihat
    # page_numbers - dan memasukkannya ke sini akan menyapu harga yang
    # benar.
    re.compile(
        r"\s*(?:di ?bawah|di ?atas|hingga|sampai|minimal|maksimal|"
        r"kurang dari|lebih dari|sekitar)?\s*"
        + NOT_MID_TOKEN
        + r"\d+[.,]?\d*\s*"
        r"(?:kbps|mbps|gbps|kb/s|mb/s|ms|milidetik|"
        r"kb|mb|gb|tb|fps|ping)\b",
        re.IGNORECASE,
    ),
)

# Janji hasil bagi pembacanya.
#
# Ditangani berbeda dari yang di atas: yang ini tidak bisa
# diselamatkan dengan membuang sepotong frasa, karena yang salah
# bukan angkanya melainkan seluruh pernyataannya. Kalimat yang
# memuatnya dibuang utuh.
#
# Yang dilarang janji bahwa PEMBACANYA menang atau untung. Pernyataan
# tentang kesanggupan brand - "yang menang dibayar" - tidak ikut, dan
# itu disengaja: pengguna sudah memutuskan brandnya boleh berbicara
# percaya diri tentang dirinya sendiri.
WIN_PROMISE = re.compile(
    r"(?:pasti|dijamin|jaminan|garansi|terjamin|niscaya)\s*"
    r"(?:akan\s*)?(?:menang|untung|cuan|profit|jackpot|jp|balik modal)"
    r"|(?:menang|untung|cuan)\s*(?:terus|setiap hari|tiap hari|pasti|"
    r"dijamin|100%)"
    r"|kemenangan\s*(?:pasti|terjamin|dijamin)"
    r"|(?:การันตี|รับรอง)\s*(?:ชนะ|กำไร|ได้เงิน)"
    r"|ชนะ\s*(?:แน่นอน|ทุกครั้ง|ชัวร์)"
    r"|(?:กำไร|ได้เงิน)\s*(?:แน่นอน|ทุกวัน|ชัวร์)",
    re.IGNORECASE,
)

# Nominal yang didapat pembacanya - "saya langsung menang 1 juta".
#
# Dibuang seutuhnya seperti WIN_PROMISE, dan sebabnya sama: yang salah
# bukan angkanya melainkan seluruh pernyataannya. Membuang "1 juta"
# dari kalimat itu menyisakan "saya langsung menang", yang tetap
# mengarang hasil.
#
# Angkanya WAJIB berpasangan dengan kata kemenangan, dan syarat itu
# bukan kerapian melainkan yang menahan penyaring ini dari merusak
# halaman yang bukan judi. Harga barang ikut berpindah zona bersama
# mata uangnya - itu perilaku yang memang diminta - jadi pola yang
# membuang setiap "150 ribu" akan mencabut harga dari halaman toko.
# "Harga jaket ini 150 ribu" tidak memuat satu pun kata di daftar
# bawah, jadi ia lewat tanpa disentuh.
#
# "dapat" dituntut menempel langsung ke angkanya, tidak seperti kata
# lain di daftar. Ia kata paling umum dalam bahasa Indonesia dalam
# arti "bisa" - "dapat diakses", "dapat digunakan" - dan diberi jarak
# 40 karakter seperti yang lain, ia akan mencaplok kalimat yang tidak
# menjanjikan apa pun.
WIN_AMOUNT = re.compile(
    r"(?:menang(?:kan)?|kemenangan|untung|cuan|profit|jackpot|jp|hadiah)"
    r"[^.!?\n]{0,40}?(?:rp\.?\s*)?\d[\d.,]*\s*"
    r"(?:juta|jt|ribu|rb|miliar|milyar)\b"
    r"|(?:rp\.?\s*)?\d[\d.,]*\s*(?:juta|jt|ribu|rb|miliar|milyar)\b"
    r"[^.!?\n]{0,40}?"
    r"(?:menang(?:kan)?|kemenangan|untung|cuan|profit|jackpot|jp)"
    r"|(?:dapat|dapet|raih|meraih|bawa pulang)\s+(?:rp\.?\s*)?\d[\d.,]*\s*"
    r"(?:juta|jt|ribu|rb|miliar|milyar)\b"
    r"|(?:ชนะ|กำไร|รางวัล|ถอนได้)[^\n]{0,30}?\d[\d.,]*\s*(?:บาท|ล้าน|พัน)"
    r"|\d[\d.,]*\s*(?:บาท|ล้าน|พัน)[^\n]{0,30}?(?:ชนะ|กำไร|รางวัล)",
    re.IGNORECASE,
)

# Jadwal yang katanya pasti membawa hasil - "jam 3 sampai 5 sore pasti
# gacor", "jam gacor malam hari".
#
# Ini yang paling sering ditulis model waktu diminta menulis ulasan,
# dan ia klaim yang paling tidak bisa dipertanggungjawabkan siapa pun:
# tidak ada jam yang menentukan hasil permainan, jadi setiap kalimat
# yang menyebutnya sedang mengarang.
#
# Waktu saja tidak cukup untuk kena. "Layanan buka jam 9 pagi" adalah
# keterangan jam buka, dan ia lewat - yang dituntut waktu DAN kata
# hasil berdampingan.
LUCKY_SCHEDULE = re.compile(
    r"(?:jam|pukul)\s*\d{1,2}(?:[.:]\d{2})?\s*"
    r"(?:-|–|s/d|sampai|hingga)?\s*(?:\d{1,2}(?:[.:]\d{2})?)?\s*"
    r"(?:pagi|siang|sore|malam|wib|wita|wit)?"
    r"[^.!?\n]{0,30}?(?:gacor|menang|hoki|untung|jackpot|jp|cuan)"
    r"|(?:gacor|menang|hoki|untung|jackpot|jp|cuan)"
    r"[^.!?\n]{0,30}?(?:jam|pukul)\s*\d{1,2}"
    r"|jam[\s-]?(?:gacor|hoki|keberuntungan)"
    # Pola/bocoran/jadwal yang katanya berulang menurut waktu, dua
    # arah urutan. Dituntut kata POLA - bukan sekadar "gacor" -
    # dan syarat itu yang menahannya dari memakan keyword: halaman
    # ini memang berjudul "slot gacor", jadi "gacor" berdiri di
    # hampir setiap kalimat dan memakainya sebagai pemicu akan
    # membuang kalimat yang tidak menjanjikan apa pun.
    r"|(?:pola|bocoran|jadwal|jam)\s*(?:\w+\s+){0,3}?"
    r"(?:di|untuk)?\s*(?:slot\s+)?(?:gacor\s+)?"
    r"(?:diperbarui|diupdate|update|keluar|muncul|berubah)?\s*"
    r"(?:setiap|tiap)\s*(?:pagi|siang|sore|malam|hari|jam|minggu)"
    r"|(?:setiap|tiap)\s*(?:pagi|siang|sore|malam|hari|jam|minggu)"
    r"[^.!?\n]{0,30}?(?:pola|bocoran)\s*(?:slot\s*)?(?:gacor)?"
    r"|(?:setiap|tiap)\s*(?:pagi|siang|sore|malam|hari|minggu)"
    r"[^.!?\n]{0,24}?(?:gacor|hoki|pasti menang|selalu menang)"
    r"|(?:เวลา|ช่วง)\s*\d{1,2}[^\n]{0,24}?(?:แตกดี|ชนะ|กำไร)",
    re.IGNORECASE,
)

# Sumber data yang tidak dipunyai siapa pun di pipeline ini.
#
# "diperbarui setiap pagi berdasarkan data real-time dari pemain" -
# kalimat yang benar-benar terbit. Tidak ada data pemain di pipeline
# ini, tidak ada yang real-time, dan tidak ada yang diperbarui tiap
# pagi. Seluruh kalimatnya karangan, jadi seluruh kalimatnya dibuang.
#
# Yang dituntut kata SUMBER berdampingan dengan kata DATA. "Kamu bisa
# lihat angkanya di layar" tidak menyebut sumber apa pun dan lewat
# tanpa disentuh; begitu juga "data pribadi kamu aman", yang menyebut
# data tapi bukan sebagai sumber angka.
FAKE_SOURCE = re.compile(
    r"(?:berdasarkan|menurut|bersumber\s*dari|diambil\s*dari|dari)\s*"
    r"(?:data|statistik|catatan|rekaman|laporan)\s*"
    r"(?:real[\s-]?time|live|terbaru|aktual|resmi|langsung|server|sistem|"
    r"pemain|pengguna|member)"
    r"|data\s*(?:real[\s-]?time|live)\s*"
    r"(?:dari\s*)?(?:pemain|pengguna|member|server|sistem)?"
    r"|(?:ข้อมูล)\s*(?:เรียลไทม์|สด|ล่าสุด)",
    re.IGNORECASE,
)

# Ketiganya dibuang per kalimat utuh, bukan per frasa. Dikumpulkan
# dalam satu tuple supaya scrub_text dan fabricated_claims memakai
# daftar yang sama persis - dua daftar yang berdiri sendiri-sendiri
# akan bergeser tanpa yang lain tahu.
WHOLE_SENTENCE_CLAIMS = (
    ("janji kemenangan", WIN_PROMISE),
    ("nominal kemenangan", WIN_AMOUNT),
    ("jadwal keberuntungan", LUCKY_SCHEDULE),
    ("sumber data karangan", FAKE_SOURCE),
)


# Pemisah kalimat. Titik, tanda tanya, tanda seru, dan baris baru.
# Aksara Thai tidak memakai titik untuk mengakhiri kalimat, jadi
# baris baru ikut dihitung batas.
#
# Dua syarat tambahan, keduanya dipasang sesudah pemisah polos
# memotong di tempat yang salah:
#
#   1. Sesudah titik harus ada HURUF. Tanpa syarat ini "Lisensi No.
#      8048/JAZ" terpotong jadi dua kalimat tepat di tengah nomornya,
#      dan tidak satu pun potongan cocok dengan pola nomor lisensi -
#      klaimnya lolos utuh justru karena dipotong.
#   2. Titik milik singkatan "No." tidak memisahkan apa pun, bahkan
#      kalau sesudahnya memang huruf.
SENTENCE_SPLIT = re.compile(
    r"(?<!\bNo\.)(?<=[.!?])\s+(?=[^\W\d_])|\n+",
    re.IGNORECASE,
)

# Kalimat yang tersisa lebih pendek dari ini sesudah frasanya dibuang
# dianggap rusak dan ikut dibuang. Diukur setelah spasi dirapikan.
MIN_SENTENCE = 15

# Sisa tanda baca yang tertinggal sesudah frasa di tengah dibuang.
TIDY = (
    (re.compile(r"\s+([,.!?;:])"), r"\1"),
    (re.compile(r"([,;:])\s*([,.;:])"), r"\1"),
    (re.compile(r"\(\s*\)"), ""),
    (re.compile(r"\s{2,}"), " "),
    (re.compile(r"\s+$", re.M), ""),
    # Kalimat yang kehilangan ekornya sering menyisakan kata sambung
    # menggantung di ujung. Yang dibuang cuma di ujung kalimat, bukan
    # di tengah.
    (
        re.compile(
            r"\s+(?:dalam|dengan|dan|atau|yang|untuk|pada|dari|ke)"
            r"\s*([.!?]|$)",
            re.IGNORECASE,
        ),
        r"\1",
    ),
)


def tidy_text(text: str) -> str:
    """
    Merapikan sisa tanda baca sesudah frasa dibuang dari tengah.
    """
    hasil = text

    for pola, ganti in TIDY:
        hasil = pola.sub(ganti, hasil)

    return hasil.strip()


def strip_durations(text: str, konteks: str = "") -> tuple[str, int]:
    """
    Membuang lama proses dalam satuan waktu.

    Cuma yang berdiri dekat kata proses. Durasi lain dibiarkan -
    lihat keterangan PROCESS_WORDS_ID.

    konteks diisi kalimat sebelumnya kalau ada. Ia hanya DIBACA untuk
    mencari kata proses; tidak satu karakter pun darinya ikut
    terpotong.
    """
    dibuang = 0

    # Ekor kalimat sebelumnya ikut jadi jendela pencarian.
    #
    # Kata prosesnya tidak selalu berdiri di kalimat yang sama dengan
    # durasinya. Terukur 14 Agustus 2026 di teks template job 67,
    # yang titiknya memang salah tempat:
    #
    #   "... sehingga saldo dapat diproses."
    #   "hanya dalam hitungan sekitar 1 detik pada kondisi normal."
    #
    # Dibaca orang itu satu kalimat; dibaca pemecah kalimat itu dua,
    # dan yang kedua tidak memuat satu pun kata proses - sehingga
    # janji satu detik lolos justru karena kalimatnya rusak.
    depan = str(konteks or "")
    sela = " " if depan else ""

    for pola, dekat in (
        (DURATION_ID, PROCESS_NEAR_ID),
        (DURATION_TH, PROCESS_NEAR_TH),
        # Pasangan ketiga sengaja paling sempit: kata kerja respons
        # hanya berpasangan dengan durasi yang berkata pengantar.
        (DURATION_LEADIN_ID, RESPONSE_NEAR_ID),
    ):
        while True:
            cocok = None

            for kandidat in pola.finditer(text):
                # Jendela dihitung di atas gabungan konteks + teks,
                # supaya kata proses di ujung kalimat sebelumnya
                # tetap terlihat, tapi yang DIPOTONG tetap teksnya
                # sendiri - konteksnya cuma dibaca.
                titik = len(depan) + len(sela) + kandidat.start()
                awal = max(0, titik - PROCESS_WINDOW)
                jendela = (depan + sela + text)[awal:titik]

                if dekat.search(jendela):
                    cocok = kandidat
                    break

            if cocok is None:
                break

            text = text[:cocok.start()] + text[cocok.end():]
            dibuang += 1

    return text, dibuang


def claim_edits(slot_map: dict, sudah: dict) -> tuple[list[dict], int]:
    """
    Membuang klaim dari teks yang terbit TANPA lewat model.

    Penyapu klaim yang lain bekerja atas jawaban model. Slot yang
    tidak kebagian jawaban terbit apa adanya - dan teks template pun
    bisa memuat klaim, karena template itu dulu halaman milik orang
    lain yang menjanjikan hal-hal miliknya sendiri.

    Terukur 14 Agustus 2026 pada job 67: heading milik template
    "Deposit QRIS Instan 1 Detik" terbit utuh di halaman NAGAJITU,
    lengkap dengan janji satu detik yang tidak dipunyai siapa pun di
    pipeline ini. Halamannya lolos semua pemeriksaan, karena tidak
    satu pun penyapu pernah melihat teks yang tidak diganti.

    Dijalankan PALING AKHIR, sesudah nama brand dan harga ditukar,
    supaya yang diperiksa teks yang benar-benar akan terbit. Slot
    yang sudah punya edit diperbaiki di tempat, bukan ditambahi edit
    kedua - dua penggantian di rentang byte yang sama membuat seluruh
    pengisian gagal.

    Yang dibuang cuma frasa klaimnya, bukan seluruh slotnya, dan slot
    yang jadi kosong dibiarkan memakai teksnya semula: heading kosong
    lebih buruk daripada heading yang terlalu berjanji.
    """
    baru: list[dict] = []
    jumlah = 0

    def periksa(slot: dict) -> None:
        nonlocal jumlah

        kunci = (slot["start"], slot["end"])
        ada = sudah.get(kunci)

        teks = str((ada["text"] if ada else slot.get("current")) or "")

        if not teks.strip():
            return

        bersih, dibuang = scrub_text(teks)

        if not dibuang:
            return

        bersih = " ".join(bersih.split()).strip(" ,;:-–—")

        if not bersih:
            return

        jumlah += 1

        if ada:
            ada["text"] = bersih
        else:
            baru.append({**slot, "text": bersih})

    for slots in slot_map["roles"].values():
        for slot in slots:
            periksa(slot)

    for slot in slot_map["skipped"]:
        # Syarat yang sama dengan brand_edits: blok iklan dan atribut
        # tanpa kutip tetap tidak disentuh.
        #
        # Klaim milik pengiklan tidak disapu di sini, dan itu bukan
        # kelonggaran. Penyapu ini ada untuk klaim yang TERBIT ATAS
        # NAMA halaman - janji satu detik milik pemilik template yang
        # ikut terbawa ke halaman brand lain. Kalimat di dalam kreatif
        # pihak ketiga bukan janji halaman ini; ia janji pemasangnya,
        # tertulis atas namanya sendiri, dan mengubahnya berarti
        # memalsukan iklan orang. Klaim yang ditulis model untuk
        # halaman sendiri tetap disapu seperti biasa.
        if slot.get("in_ad") or slot.get("protected_ad"):
            continue

        if slot["kind"] == "attribute" and not slot.get("quote"):
            continue

        periksa(slot)

    return baru, jumlah


def strip_figure_claims(text: str) -> tuple[str, int]:
    """
    Membuang angka yang tidak dipunyai pipeline.
    """
    dibuang = 0

    for pola in FIGURE_CLAIMS:
        text, jumlah = pola.subn("", text)
        dibuang += jumlah

    return text, dibuang


def drop_win_promises(text: str) -> tuple[str, int]:
    """
    Membuang kalimat yang menjanjikan pembacanya menang.

    Kalimatnya dibuang utuh. Membuang frasanya saja menyisakan
    kalimat yang tetap berbunyi seperti janji, cuma tanpa kata
    kuncinya.
    """
    if not WIN_PROMISE.search(text):
        return text, 0

    kalimat = SENTENCE_SPLIT.split(text)

    sisa = [
        bagian
        for bagian in kalimat
        if bagian.strip() and not WIN_PROMISE.search(bagian)
    ]

    dibuang = len([b for b in kalimat if b.strip()]) - len(sisa)

    return " ".join(sisa), dibuang


# Dua kata tugas berdampingan adalah bekas frasa yang dicabut dari
# tengah kalimat. "Situs ini berdiri sejak 2015 dan terus berkembang"
# menyisakan "Situs ini dan terus berkembang", dan yang menandainya
# rusak justru "ini dan" - pasangan yang tidak pernah ditulis orang.
DANGLING = re.compile(
    r"\b(?:ini|itu|yang|dan|atau|dengan|dalam|untuk|pada|dari|ke|"
    r"adalah|akan|bisa|dapat)\s+"
    r"(?:dan|atau|dengan|dalam|untuk|pada|dari|ke|adalah)\b",
    re.IGNORECASE,
)

MIN_WORDS = 4

# Aksara Thai. Dipakai memutuskan apakah menghitung kata itu berarti.
#
# Thai memberi spasi antar FRASA, bukan antar kata, jadi kalimat Thai
# yang wajar bisa terhitung dua "kata" dan tertolak oleh pemeriksaan
# yang benar untuk teks Latin. Jebakan yang sama sudah pernah
# menjatuhkan seluruh kartu FAQ cadangan zona Thailand, dan itu
# tercatat - jangan hitung kata dengan split() untuk aksara ini.
THAI_CHARS = re.compile(r"[฀-๿]")


def drop_dangling_clause(text: str) -> str:
    """
    Membuang klausa satu kata yang menggantung di ujung kalimat.

    Sesudah frasa durasi dicabut, kadang yang tertinggal di belakang
    koma cuma subjeknya. Terukur pada ulasan yang benar-benar terbit:

        ditulis : Daftar dari HP, prosesnya selesai dalam dua detik.
        tersisa : Daftar dari HP, prosesnya.

    "prosesnya" berdiri sendiri tanpa apa pun yang diterangkannya -
    ia bukan kalimat yang lebih pendek melainkan kalimat yang
    kepalanya dipenggal.

    Ambangnya SATU kata, bukan dua, dan itu disengaja. "saldo masuk"
    juga dua kata di belakang koma, tapi ia klausa yang utuh -
    subjek dan predikat - dan membuangnya membuang keterangan yang
    benar. Yang dicari cuma sisa yang mustahil berdiri sendiri.
    """
    isi = str(text or "").strip()

    if "," not in isi:
        return isi

    ekor_tanda = ""

    if isi[-1:] in ".!?":
        ekor_tanda, isi = isi[-1], isi[:-1]

    bagian = [potong.strip() for potong in isi.split(",")]

    if len(bagian) < 2:
        return text

    if len(bagian[-1].split()) <= 1:
        sisa = ", ".join(bagian[:-1]).strip().rstrip(",")

        return (sisa + ekor_tanda) if sisa else text

    # Ekor yang lebih dari satu kata, tapi bendanya yang tercabut.
    #
    # Ambang satu kata di atas menutup "prosesnya", dan tidak menutup
    # bentuk yang benar-benar terbit 30 Agustus 2026:
    #
    #     ditulis : ... saat bermain, dengan sistem sejak tahun 2015.
    #     tersisa : ... saat bermain, dengan sistem.
    #
    # "dengan sistem" dua kata, jadi ia lolos, lalu titiknya dipasang
    # balik dan kalimat penggal terbit terlihat utuh di hasil
    # pencarian. Sekelasnya "dengan sistem yang sudah dipakai" dan
    # "dengan sistem berlisensi resmi" - semuanya kata depan yang
    # membuka keterangan, lalu keterangannya hilang bersama klaimnya.
    #
    # Yang TIDAK dilakukan: menambah kata ke daftar kata menggantung.
    # Alasannya sudah tertulis di finish_clause, dan sama di sini -
    # daftar itu akan tumbuh satu kata setiap kali muncul bentuk baru.
    # Yang dipakai fungsi itu sendiri, karena soalnya memang soal yang
    # sama: teks yang BARU dipotong dan menyisakan anak kalimat yang
    # kepalanya dipenggal. Di titik ini pemotongan itu sudah pasti
    # terjadi - scrub_text cuma sampai sini kalau ada klaim yang
    # benar-benar dicabut.
    rapi = finish_clause(isi, dipotong=True)

    if rapi and rapi != isi and len(rapi.split()) >= MIN_WORDS:
        return rapi.rstrip(" ,;:-") + ekor_tanda

    return text


# Kata penghubung yang MENJANJIKAN sebuah pernyataan sesudahnya.
#
# Bedanya dengan DANGLING: yang itu mencari dua kata tugas berturut-
# turut di mana pun, yang ini mencari satu kata penghubung yang
# berdiri di UJUNG kalimat dengan cuma beberapa kata di belakangnya.
#
# Terbit 30 Agustus 2026 di badan artikel:
#
#   ditulis : ... mencatat bahwa proses verifikasi hanya butuh 30 detik.
#   terbit  : ... mencatat bahwa proses verifikasi.
#
# "bahwa" menjanjikan sebuah pernyataan, dan pernyataannya persis yang
# dicabut. Yang tersisa bukan kalimat yang lebih pendek melainkan
# kalimat yang isinya hilang - dan ia lolos setiap pemeriksaan yang
# ada karena panjangnya cukup, kata terakhirnya kata benda, dan tidak
# ada dua kata tugas yang berdempetan di dalamnya.
OPEN_COMPLEMENT = re.compile(
    r"\b(?:bahwa|karena|sehingga|agar|supaya|yakni|yaitu)\b"
    r"(?:\s+\S+){0,3}\s*$",
    re.IGNORECASE,
)

# Sesedikit apa kata boleh tersisa di klausa PERTAMA sebuah kalimat
# berkoma sebelum klausa itu terhitung kehilangan predikatnya.
#
# Terbit di run yang sama, di jawaban FAQ:
#
#   ditulis : Proses verifikasi hanya 2 menit, tanpa perlu mengunggah ...
#   terbit  : Proses verifikasi, tanpa perlu mengunggah ...
#
# "Proses verifikasi" bukan kalimat, ia nama sebuah hal. Yang
# menjadikannya kalimat justru bagian yang dicabut. drop_dangling_clause
# menjaga ujung; ini menjaga kepala, dan keduanya dibutuhkan karena
# klaim bisa berdiri di mana saja.
HEAD_MIN_WORDS = 2


def head_clause(teks: str) -> str:
    """
    Klausa pertama sebuah kalimat, sebelum koma pertamanya.
    """
    isi = " ".join(str(teks or "").split())

    return isi.split(",")[0].strip() if "," in isi else isi


def cut_at_end(asli: str, sisa: str) -> bool:
    """
    Apakah yang dicabut berdiri di UJUNG kalimatnya.

    Dijawab dengan membandingkan bentuknya, bukan dengan menyimpan
    posisi potongan: kalau yang tersisa adalah awalan persis dari
    kalimat aslinya, berarti tidak ada satu kata pun dari asli yang
    berdiri di belakang titik potongnya.

    Tanda baca penutup dilepas lebih dulu karena ia memang ikut
    pindah ke belakang waktu bagian tengahnya dicabut.
    """
    kiri = " ".join(str(asli or "").split())
    kanan = " ".join(str(sisa or "").split()).rstrip(".!?")

    return bool(kanan) and kiri.startswith(kanan)


def sentence_survives(asli: str, sisa: str) -> bool:
    """
    Apakah kalimat yang sudah dipangkas masih layak berdiri.

    Tiga tanda kerusakan, semuanya terukur dari teksnya sendiri tanpa
    perlu tahu tata bahasanya.

    Rasio penyusutan sengaja TIDAK dipakai, meski sempat dicoba.
    Diukur pada kalimat sungguhan, ia tidak memisahkan apa pun:
    "Penarikan dana diproses dalam waktu kurang dari 5 menit setiap
    hari" menyusut 47% dan hasilnya kalimat yang benar, sedangkan
    "Sudah dipercaya lebih dari 10.000 member aktif setiap harinya"
    menyusut 40% dan hasilnya kalimat yang janggal. Ambang mana pun
    di antara keduanya salah untuk salah satunya, dan yang salah ke
    arah "dibuang" jauh lebih mahal - kalimat janggal cuma kurang
    enak dibaca, kalimat yang hilang membuat slot terbit dengan teks
    lama milik template.
    """
    bersih = sisa.strip()

    if len(bersih) < MIN_SENTENCE:
        return False

    if DANGLING.search(bersih):
        return False

    # Kalimat yang tadinya diawali huruf besar lalu jadi diawali huruf
    # kecil berarti subjeknya yang tercabut, bukan keterangannya.
    awal_asli = asli.strip()[:1]
    awal_sisa = bersih[:1]

    if awal_asli.isupper() and awal_sisa.islower():
        return False

    if not THAI_CHARS.search(asli) and len(bersih.split()) < MIN_WORDS:
        return False

    # Aksara Thai tidak ikut dua pemeriksaan di bawah. Keduanya
    # menghitung kata dengan split(), dan Thai memberi spasi antar
    # FRASA - jebakan yang sudah pernah menjatuhkan seluruh kartu FAQ
    # cadangan zona Thailand.
    if THAI_CHARS.search(asli):
        return True

    # Ekornya yang tercabut, dan yang dicabut adalah pernyataan yang
    # dijanjikan kata penghubung di ujung - lihat OPEN_COMPLEMENT.
    if cut_at_end(asli, bersih) and OPEN_COMPLEMENT.search(bersih):
        return False

    # Kepalanya yang tercabut - lihat HEAD_MIN_WORDS.
    kepala_asli = head_clause(asli)
    kepala_sisa = head_clause(bersih)

    if (
        "," in " ".join(str(asli).split())
        and len(kepala_sisa.split()) <= HEAD_MIN_WORDS
        and len(kepala_sisa.split()) < len(kepala_asli.split())
    ):
        return False

    return True


def repair_fragment(text: str) -> str:
    """
    Menambal kalimat yang tersisa sesudah frasa dicabut dari tengah.

    Dipakai HANYA untuk kalimat cadangan - yang sudah gagal
    pemeriksaan kelayakan tapi tetap harus dipakai karena tidak ada
    kalimat lain yang tersisa. Dua tambalan, keduanya aman karena
    tidak menambahkan satu kata pun yang tidak ada di kalimat asli:

      "Situs ini dan terus berkembang"  -> "Situs ini terus berkembang"
      "membuat permainan ini dicari"    -> "Membuat permainan ini dicari"
    """
    hasil = DANGLING.sub(
        lambda cocok: cocok.group(0).split()[0],
        text,
    )

    hasil = tidy_text(hasil)

    if hasil[:1].islower():
        hasil = hasil[:1].upper() + hasil[1:]

    return hasil


def scrub_text(text: str) -> tuple[str, int]:
    """
    Membersihkan satu potong teks dari klaim yang tidak dipunyai.

    Dikerjakan per kalimat, bukan atas seluruh teks sekaligus. Yang
    membuat perbedaan bukan kerapiannya melainkan hasilnya: membuang
    frasa dari tengah kalimat kadang menyisakan kalimat utuh
    ("Deposit diproses dalam 2 detik dan langsung masuk" jadi
    "Deposit diproses dan langsung masuk") dan kadang menyisakan
    puing ("Situs ini dan terus berkembang"). Bedanya cuma bisa
    dinilai per kalimat, dan yang jadi puing dibuang seluruhnya.

    Mengembalikan (teks, jumlah klaim yang dibuang).
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0

    asli = text
    total = 0
    simpan: list[str] = []

    # Kalimat yang dipangkas tapi gagal pemeriksaan kelayakan.
    # Disimpan terpisah sebagai cadangan, bukan dibuang begitu saja -
    # lihat alasannya di bawah.
    cadangan: list[str] = []

    # Kalimat sebelumnya disimpan sebagai konteks pencarian kata
    # proses - lihat strip_durations.
    sebelumnya = ""

    for kalimat in SENTENCE_SPLIT.split(text):
        if not kalimat.strip():
            continue

        konteks = sebelumnya
        sebelumnya = kalimat

        # Janji kemenangan, nominal yang didapat, dan jadwal yang
        # katanya pasti membawa hasil tidak bisa diselamatkan dengan
        # membuang sepotong kata - yang salah seluruh pernyataannya.
        if any(pola.search(kalimat) for _, pola in WHOLE_SENTENCE_CLAIMS):
            total += 1
            continue

        sisa, a = strip_durations(kalimat, konteks)
        sisa, b = strip_figure_claims(sisa)

        if not (a + b):
            simpan.append(kalimat.strip())
            cadangan.append(kalimat.strip())
            continue

        total += a + b
        sisa = drop_dangling_clause(tidy_text(sisa))

        if sentence_survives(kalimat, sisa):
            simpan.append(sisa)

        if sisa.strip():
            cadangan.append(sisa.strip())

    if not total:
        return asli, 0

    hasil = " ".join(bagian for bagian in simpan if bagian).strip()

    # Kalau seluruh kalimatnya gugur, yang dipakai versi terpangkasnya
    # - BUKAN teks aslinya.
    #
    # Versi pertama fungsi ini mengembalikan teks asli di titik ini,
    # dan itu diam-diam menerbitkan persis klaim yang sedang dicegah:
    # teks berkalimat tunggal yang seluruh isinya klaim keluar utuh
    # dengan laporan "0 klaim dibuang". Kalimat janggal tanpa klaim
    # masih lebih baik daripada kalimat rapi yang mengarang angka,
    # dan jumlah yang dikembalikan tetap memberitahu pemanggilnya
    # bahwa ada yang dipotong.
    if not hasil:
        hasil = " ".join(
            repair_fragment(bagian) for bagian in cadangan if bagian
        ).strip()

    return hasil, total


def fabricated_claims(text: str) -> list[tuple[str, str]]:
    """
    Klaim karangan yang masih berdiri di sebuah teks, beserta jenisnya.

    Pasangan scrub_text: yang itu MEMBUANG, yang ini MELAPORKAN. Dua
    pekerjaan yang berbeda, dan yang kedua dibutuhkan karena penyapuan
    saja tidak bisa membuktikan dirinya sendiri - halaman yang terbit
    tetap harus diperiksa, dan pemeriksaan itu harus memakai daftar
    yang sama persis dengan yang menyapunya.

    Karena itu tidak ada satu pun pola baru di sini: WHOLE_SENTENCE_CLAIMS
    dan FIGURE_CLAIMS dipakai apa adanya. Daftar kedua yang ditulis
    sendiri akan bergeser dari yang pertama tanpa yang lain tahu, dan
    gejalanya audit yang melaporkan bersih atas halaman yang tidak.

    Mengembalikan daftar (jenis, potongan yang kena). Kosong berarti
    tidak ada yang karangan.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    kena: list[tuple[str, str]] = []

    for jenis, pola in WHOLE_SENTENCE_CLAIMS:
        for cocok in pola.finditer(text):
            kena.append((jenis, cocok.group(0).strip()))

    for pola in FIGURE_CLAIMS:
        for cocok in pola.finditer(text):
            potongan = cocok.group(0).strip()

            if potongan:
                kena.append(("angka karangan", potongan))

    return kena


def scrub_content(content, ) -> tuple[object, int]:
    """
    Membersihkan seluruh isi halaman sekaligus, seberapa pun dalam.

    Menerima dict, list, atau string, dan menelusuri isinya. Peran
    berawalan garis bawah dilewati: isinya penanda untuk riwayat,
    bukan teks yang terbit - aturan yang sama dengan
    fix_content_terms di utils/spelling.py.
    """
    if isinstance(content, str):
        return scrub_text(content)

    if isinstance(content, list):
        hasil = []
        total = 0

        for item in content:
            bersih, jumlah = scrub_content(item)
            hasil.append(bersih)
            total += jumlah

        return hasil, total

    if isinstance(content, dict):
        hasil = {}
        total = 0

        for kunci, nilai in content.items():
            if isinstance(kunci, str) and kunci.startswith("_"):
                hasil[kunci] = nilai
                continue

            bersih, jumlah = scrub_content(nilai)
            hasil[kunci] = bersih
            total += jumlah

        return hasil, total

    return content, 0
