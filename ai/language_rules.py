"""
Aturan bunyi tulisan, dipisah per bahasa.

Sebelumnya cuma ada satu daftar aturan - VOICE_RULES di
ai/neiiu_prompts.py - dan daftar itu dikirim ke model apa pun zona
yang dipilih. Untuk zona Indonesia itu benar. Untuk zona Thailand
akibatnya terbaca, dan tiga di antaranya berlawanan langsung dengan
tugas yang sedang dikerjakan model:

  1. Daftar frasa terlarangnya seluruhnya bahasa Indonesia ("di era
     digital", "hal ini membuat"). Model yang sedang menulis Thai
     tidak pernah berpeluang melanggarnya, jadi seluruh daftar itu
     cuma memakan context tanpa menahan apa pun.
  2. Aturan "kata 'secara' hampir selalu bisa dibuang" adalah aturan
     tentang satu kata Indonesia. Di halaman Thai ia tidak menunjuk
     apa-apa.
  3. Yang paling merugikan: baris terakhirnya MENYURUH model memakai
     kata sehari-hari "nggak", "udah", "bikin". Itu perintah memakai
     bahasa gaul Indonesia, dikirim bersama perintah menulis dalam
     bahasa Thai. Dua perintah yang bertabrakan, dan yang satu
     menarik hasilnya persis ke arah yang dikeluhkan: kalimat Thai
     yang bentuknya bentuk kalimat Indonesia.

Aturan Indonesia di bawah ini disalin apa adanya dari VOICE_RULES
supaya zona Indonesia tidak berubah sehuruf pun. Yang baru cuma
pasangan Thai-nya.
"""

# Frasa brosur yang dilarang berdiri di halaman.
#
# Berdiri sebagai DAFTAR, bukan sebagai kalimat di dalam prompt, dan
# itu bukan kerapian. Daftar yang sama dipakai dua kali: sekali untuk
# menyusun aturannya di prompt, sekali lagi untuk menyaring contoh
# gaya milik pengguna sebelum diperlihatkan ke model.
#
# Sebabnya terukur. knowledge/gaya_artikel.txt memuat paragraf yang
# dibuka "Di era digital, kecepatan transaksi menjadi salah satu
# faktor utama ..." dan satu lagi yang berbunyi "[ BRAND ] bukan
# sekadar situs slot biasa" - dua bentuk yang persis dilarang daftar
# ini. Model 4B yang menerima aturan abstrak bersama contoh nyata
# mengikuti contohnya, jadi selama contohnya tidak ikut disaring,
# aturannya cuma memakan context.
BANNED_PHRASES_ID = (
    "di era digital",
    "hal ini membuat",
    "dirancang untuk",
    "salah satu faktor utama",
    "salah satu keunggulan utama",
    "teknologi yang digunakan",
    "memungkinkan pengguna",
    "memungkinkan kamu",
    "sehingga pengguna dapat",
    "aspek penting",
    "seluruh proses",
    "mengutamakan efisiensi",
    "tanpa perlu intervensi manusia",
    "data kinerja",
    "sistem pengolahan data",
    "secara transparan",
    "terukur dan",
    "berbasis data",
    "solusi cerdas",
    "pengalaman bermain yang optimal",
    "bukan sekadar",
    "tidak hanya menampilkan",
)


# Dua potongan di dalam aturan bunyi yang menyebut bidang tertentu.
#
# Sisa aturannya berlaku untuk halaman apa pun - subjek kalimat harus
# orang, frasa brosur dilarang, panjang kalimat berganti-ganti - tapi
# dua di antaranya memakai contoh dari dunia slot: satu bentuk kalimat
# terlarang, dan satu cara menyebut angka tanpa menyebut angkanya.
#
# Contoh yang salah bidang bukan cuma janggal. Aturan "jangan tulis
# begini" yang contohnya tentang slot, dikirim ke halaman kursus,
# menyodorkan kosakata slot ke model tepat pada saat ia diminta
# menulis tentang kursus - dan model kecil mengambil kosakata dari
# mana pun ia menemukannya, termasuk dari daftar larangan.
#
# Dipisah sebagai lubang, bukan digandakan sebagai dua versi utuh.
# Dua salinan aturan sepanjang ini akan berbeda isinya suatu saat,
# dan yang ketinggalan tidak akan ketahuan sampai ada yang
# membandingkan keduanya baris per baris.
VOICE_EXAMPLES = {
    "gambling": {
        "id": {
            "kalimat_terlarang": (
                '"Slot gacor bukan sekadar permainan yang sering '
                'menang, tapi ..."'
            ),
            "angka_samar": (
                'Sebut "RTP-nya lagi bagus" atau\n'
                '  "angkanya lagi tinggi"; angka persisnya biar '
                "berdiri di tabel."
            ),
        },
        "th": {
            "angka_samar": (
                'ให้เขียนว่า "ช่วงนี้กำลังดี"\n'
                '  หรือ "ตัวเลขกำลังขึ้น" ส่วนตัวเลขจริงปล่อยให้อยู่ในตาราง'
            ),
            "istilah": "สล็อต เว็บตรง ฝากถอน วอเลท",
            "kosakata": (
                '"แตกง่าย" "ถอนไว"\n'
                '  "สมัครง่าย" "เล่นได้จริง" "ทุนน้อยก็เล่นได้"'
            ),
        },
    },
    "generic": {
        "id": {
            "kalimat_terlarang": (
                '"Layanan ini bukan sekadar tempat memesan, tapi ..."'
            ),
            "angka_samar": (
                'Sebut "lagi banyak yang pakai" atau\n'
                '  "sedang ramai"; angka persisnya biar berdiri di '
                "tabel."
            ),
        },
        "th": {
            "angka_samar": (
                'ให้เขียนว่า "ช่วงนี้คนใช้เยอะ"\n'
                "  หรือ \"กำลังได้รับความนิยม\" ส่วนตัวเลขจริงปล่อยให้อยู่ในตาราง"
            ),
            "istilah": "ออนไลน์ โปรโมชั่น แพ็กเกจ",
            "kosakata": (
                '"ใช้ง่าย" "ตอบไว"\n'
                '  "สมัครง่าย" "ของถึงจริง" "เริ่มต้นไม่แพง"'
            ),
        },
    },
}


# Aturan zona Indonesia. Disalin PERSIS dari VOICE_RULES yang lama -
# setiap barisnya lahir dari keluhan pengguna yang bisa ditunjuk, dan
# tidak ada satu pun yang diubah waktu berkas ini dipisah. Dua
# lubangnya diisi VOICE_EXAMPLES, dan isian bidang "gambling"
# menghasilkan teks yang sama huruf per huruf dengan aslinya.
VOICE_TEMPLATE_ID = """Aturan bunyi tulisan — berlaku untuk SEMUA teks di atas:
- Tulis seperti orang yang mengurus situs ini sendiri dan sedang
  menjelaskannya ke calon pemakai. Bukan seperti brosur perusahaan,
  bukan seperti dokumen produk.
- Sapa pembaca dengan "Anda", bukan "kamu" dan bukan "-mu". Ini
  halaman yang dibaca orang yang belum kenal situs ini, dan "kamu"
  membuatnya terbaca seperti pesan singkat, bukan seperti keterangan
  resmi sebuah situs. Kalau kalimatnya tetap jelas tanpa menyapa
  siapa pun, tidak usah menyapa sama sekali.
- Subjek kalimatnya ORANG, bukan benda. Tulis "Anda bisa melihat
  angkanya di layar", bukan "sistem menampilkan angka kepada
  pengguna". Kalimat yang subjeknya "sistem", "teknologi", "proses",
  "layanan", atau "platform" berturut-turut adalah tanda paling jelas
  bahwa tulisannya dibuat mesin.
- Kalimat berikut DILARANG dipakai, termasuk bentuk miripnya:
  {frasa_terlarang}.
- DUA SUSUNAN KALIMAT INI DILARANG, dan keduanya diambil dari halaman
  yang dikeluhkan pengguna karena "terlihat AI banget":
    "Tidak hanya menampilkan angka, tapi juga menggambarkan pola ..."
    {kalimat_terlarang}
  Bentuk "bukan sekadar X, tapi Y" dan "tidak hanya X, tapi juga Y"
  adalah cara mesin membuat satu gagasan terdengar seperti dua. Orang
  menulis gagasannya langsung: "Yang ditampilkan bukan cuma angkanya.
  Polanya kelihatan juga." Kalau sebuah kalimat butuh dua sisi untuk
  berdiri, pecah jadi dua kalimat.
- Kata "secara" hampir selalu bisa dibuang. "Diperbarui secara
  otomatis" sama artinya dengan "diperbarui sendiri", dan yang kedua
  itu yang ditulis orang. Satu halaman paling banyak memakai "secara"
  dua kali.
- ANGKA PERSEN PALING BANYAK DISEBUT DUA KALI di seluruh halaman, dan
  tidak sekali pun di ulasan. Terukur pada halaman yang dikeluhkan
  pengguna: satu angka desimal yang sama muncul 18 kali di teks yang
  dibaca orang, termasuk di kelima ulasan sekaligus. Tidak ada lima
  orang yang menulis pengalamannya dan kelimanya menyebut angka
  desimal yang sama persis - itu satu-satunya tanda yang bisa dilihat
  pembaca tanpa membandingkan apa pun. {angka_samar}
- Panjang kalimatnya berganti-ganti. Kalimat pendek boleh berdiri
  sendiri. Paragraf yang semua kalimatnya sama panjang dan sama
  susunannya terbaca seperti daftar yang disamarkan.
- Bahasanya SETENGAH RESMI: tidak kaku, tapi juga tidak santai.
  Bayangkan keterangan yang ditulis pengelola situs untuk calon
  pemakainya - sopan, langsung ke pokoknya, tanpa basa-basi
  perusahaan dan tanpa gaya obrolan.
  Yang DILARANG karena terlalu santai: "nggak", "udah", "bikin",
  "banget", "gue", "lu", "yuk", "kok", "sih", "nih", "dong", "aja".
  Tulis bentuk bakunya: "tidak", "sudah", "membuat", "sekali", "saja".
  Yang DILARANG karena terlalu kaku: "adapun", "dengan demikian",
  "sehubungan dengan hal tersebut", "dalam rangka", "guna",
  "senantiasa", "merupakan suatu".
  Kata seperti "langsung", "tinggal", "cukup" tetap boleh - itu kata
  biasa, bukan bahasa gaul.
- YANG HARUS DILAKUKAN, bukan cuma yang dihindari.
  Semua aturan di atas melarang. Daftar larangan saja menghasilkan
  tulisan yang aman dan datar - tiap kalimatnya tidak melanggar apa
  pun, dan justru karena itu tidak ada orang yang menulisnya begitu.
  Empat hal berikut yang membuat sebuah halaman terbaca seperti
  ditulis orang:
  1. KALIMAT NYAMBUNG KE KALIMAT SEBELUMNYA. Satu paragraf itu satu
     pikiran yang dikembangkan, bukan tiga pernyataan yang kebetulan
     satu topik. Kalimat kedua menjawab, melanjutkan, atau membantah
     yang pertama. Ujinya begini: kalau urutan kalimat di satu
     paragraf bisa ditukar tanpa ada yang berubah artinya, itu daftar
     yang menyamar jadi paragraf - susun ulang sampai urutannya
     berarti.
  2. PEMBUKA PARAGRAF BERGANTI-GANTI. Jangan ada dua paragraf
     berturut-turut yang dibuka dengan cara yang sama. Yang satu
     boleh mulai dari keadaan pembaca, yang berikutnya dari hal yang
     dikerjakan, yang lain lagi dari satu kalimat pendek yang
     berdiri sendiri.
  3. SEBUT HAL YANG SPESIFIK. "Prosesnya cepat" adalah kalimat yang
     bisa ditulis siapa pun tentang apa pun tanpa tahu apa-apa.
     "Yang harus diisi cuma nomor rekening dan nominalnya" adalah
     keterangan yang cuma bisa ditulis orang yang pernah membukanya.
     Tiap paragraf sebaiknya memuat satu hal yang tidak bisa ditebak
     dari topiknya saja.
  4. TULIS SEPERTI SUDAH PERNAH MEMAKAINYA SENDIRI. Orang yang
     benar-benar memakai selalu menyebut hal kecil: letak tombolnya,
     apa yang muncul sesudah ditekan, bagian mana yang membingungkan
     waktu pertama kali. Hal kecil itu yang tidak dipunyai tulisan
     mesin, dan satu-dua saja sudah cukup mengubah bunyi seluruh
     paragraf.
- JANGAN MENYALIN KALIMAT DARI HALAMAN MANA PUN. Halaman pesaing
  yang diperlihatkan di atas ada untuk memberi tahu TOPIK apa yang
  perlu dibahas - bukan untuk ditiru bunyinya. Ambil topiknya, lalu
  tulis kalimatnya sendiri dari nol, dengan urutan dan contoh yang
  lain. Rangkaian EMPAT KATA berturut-turut yang sama persis dengan
  halaman contoh sudah terlalu banyak. Ini bukan soal sopan santun:
  halaman yang kalimatnya sama dengan halaman yang lebih dulu ada
  tidak punya satu alasan pun untuk ditaruh di atasnya."""


# Aturan zona Thailand.
#
# Ditulis DALAM bahasa Thai, bukan diterjemahkan dari daftar di atas.
# Bedanya bukan gaya: aturan bunyi yang ditulis dalam bahasa Indonesia
# menyodorkan bentuk kalimat Indonesia ke model tepat pada saat ia
# diminta menulis Thai, dan itu justru mesin yang memproduksi "Thai
# yang terasa hasil terjemahan".
#
# Yang dilarang di sini bukan salinan larangan Indonesia, melainkan
# penanda terjemahan yang khas bahasa Thai sendiri:
#
#   - "ในยุคดิจิทัล" adalah terjemahan harfiah "di era digital", dan
#     ia memang muncul di halaman Thai yang ditulis mesin. Ini satu-
#     satunya baris yang punya pasangan langsung di daftar Indonesia.
#   - "การ" dan "ความ" mengubah kata kerja jadi kata benda. Bahasa
#     Inggris dan Indonesia sering butuh itu; Thai tidak, dan
#     penumpukannya adalah tanda kalimat yang disusun mengikuti tata
#     bahasa bahasa lain.
#   - "ที่" berlebihan lahir dari klausa relatif "yang"/"which" yang
#     diterjemahkan satu per satu.
#   - Spasi. Thai tidak memberi spasi antar kata, hanya antar frasa.
#     Penulis mesin yang berangkat dari teks berspasi membawa
#     spasinya ikut, dan itu penanda paling kasatmata bahwa teksnya
#     bukan ditulis orang Thai.
#
# Baris terakhir daftar Indonesia - izin memakai "nggak/udah/bikin" -
# sengaja TIDAK punya salinan harfiah di sini. Padanannya kata yang
# memang dipakai orang Thai untuk topik ini.
VOICE_TEMPLATE_TH = """กฎน้ำเสียงการเขียน — ใช้กับข้อความทุกชิ้นด้านบน
(Aturan bunyi tulisan — berlaku untuk SEMUA teks di atas):
- เขียนเหมือนคนที่ดูแลเว็บนี้เอง กำลังอธิบายให้คนที่กำลังจะสมัครฟัง
  ไม่ใช่โบรชัวร์บริษัท ไม่ใช่เอกสารแนะนำสินค้า
- ประธานของประโยคต้องเป็น "คน" ไม่ใช่ "สิ่งของ" เขียนว่า
  "กดดูตัวเลขได้เลยบนหน้าจอ" ไม่ใช่ "ระบบจะแสดงตัวเลขให้แก่ผู้ใช้งาน"
  ประโยคที่ขึ้นต้นด้วย "ระบบ" "เทคโนโลยี" "แพลตฟอร์ม" "กระบวนการ"
  ติดกันหลายประโยค คือสัญญาณชัดที่สุดว่าเครื่องเป็นคนเขียน
- ห้ามใช้สำนวนต่อไปนี้ รวมถึงรูปที่ใกล้เคียงกัน:
  "ในยุคดิจิทัล", "ในโลกปัจจุบัน", "ถูกออกแบบมาเพื่อ",
  "หนึ่งในปัจจัยสำคัญ", "หนึ่งในจุดเด่นที่สำคัญ",
  "เทคโนโลยีที่ทันสมัย", "ช่วยให้ผู้ใช้สามารถ",
  "เพื่อให้ผู้ใช้สามารถ", "อย่างมีประสิทธิภาพ",
  "ตอบโจทย์ทุกความต้องการ", "ครบวงจร", "อย่างไร้รอยต่อ",
  "ประสบการณ์การเล่นที่ดีที่สุด", "สิ่งสำคัญอีกประการหนึ่ง"
  สำนวนพวกนี้คือร่องรอยของงานแปล ไม่ใช่ภาษาที่คนไทยพิมพ์เอง
- ห้ามใช้โครงประโยค "ไม่เพียงแต่ X แต่ยัง Y" และ "ไม่ใช่แค่ X แต่ยัง Y"
  นี่คือวิธีที่เครื่องทำให้ความคิดเดียวฟังดูเหมือนสองความคิด
  คนไทยเขียนความคิดนั้นตรง ๆ แล้วตัดเป็นสองประโยคสั้น
- "การ" และ "ความ" ที่เติมหน้าคำกริยา ใช้เท่าที่จำเป็นจริง ๆ
  "การทำรายการฝากเงินสามารถดำเนินการได้อย่างรวดเร็ว" คือประโยคแปล
  "ฝากเงินเข้าไว ทันก่อนปิดแอปธนาคาร" คือประโยคที่คนไทยเขียน
- "ที่" ที่ไม่จำเป็นให้ตัดทิ้ง ประโยคเดียวที่มี "ที่" สามครั้ง
  คือประโยคที่แปลมาจากภาษาอื่นทีละคำ
- เว้นวรรคแบบไทย ภาษาไทยไม่เว้นวรรคระหว่างคำ เว้นเฉพาะระหว่างวลี
  หรือจบประโยค การเว้นวรรคทีละคำคือหลักฐานว่าข้อความถูกแปลมา
- ห้ามแปลชื่อแบรนด์ ชื่อสินค้า ชื่อบริษัท และชื่อเฉพาะ เขียนทับศัพท์
  ตามที่คนไทยเรียกกันจริง เช่น {istilah}
- ตัวเลขเปอร์เซ็นต์พูดถึงได้มากที่สุดสองครั้งในทั้งหน้า และห้ามใช้
  ในรีวิวเลยแม้แต่ครั้งเดียว ไม่มีผู้เล่นห้าคนที่เขียนรีวิวแล้ว
  บอกตัวเลขทศนิยมเดียวกันเป๊ะทั้งห้าคน {angka_samar}
- ความยาวประโยคต้องสลับกันไป ประโยคสั้นยืนเดี่ยวได้
  ย่อหน้าที่ทุกประโยคยาวเท่ากันและเรียงเหมือนกัน อ่านเหมือนรายการ
  ที่ถูกอำพรางไว้
- ใช้คำที่คนไทยใช้จริงกับเรื่องนี้ได้ เช่น {kosakata} แต่อย่าใส่ถี่จนเฝือ
  ภาษาที่เรียบเกินไปกลับน่าสงสัยกว่า
- ห้ามลงท้าย "ครับ/ค่ะ" ใน title, heading และชื่อการ์ด
  ใส่ได้บ้างเฉพาะในรีวิวของผู้ใช้ เพราะรีวิวคือคนกำลังพูด
- สิ่งที่ "ต้องทำ" ไม่ใช่แค่สิ่งที่ห้าม
  ข้อข้างบนทั้งหมดเป็นข้อห้าม การมีแต่ข้อห้ามทำให้งานเขียนปลอดภัยแต่จืด
  ทุกประโยคไม่ผิดกฎอะไรเลย และเพราะอย่างนั้นเองจึงไม่มีคนเขียนแบบนั้น
  สี่ข้อนี้คือสิ่งที่ทำให้หน้าเว็บอ่านแล้วเหมือนคนเขียนจริง
  1. ประโยคต้องต่อกับประโยคก่อนหน้า หนึ่งย่อหน้าคือหนึ่งความคิดที่ขยายออก
     ไม่ใช่สามประโยคที่บังเอิญอยู่หัวข้อเดียวกัน ประโยคที่สองต้องตอบ
     ขยาย หรือแย้งประโยคแรก วิธีทดสอบคือ ถ้าสลับลำดับประโยคในย่อหน้าได้
     โดยความหมายไม่เปลี่ยน แปลว่านั่นคือรายการที่ปลอมตัวเป็นย่อหน้า
     ให้เรียบเรียงใหม่จนลำดับมีความหมาย
  2. คำขึ้นต้นย่อหน้าต้องสลับกันไป ห้ามมีสองย่อหน้าติดกันที่ขึ้นต้นแบบเดียวกัน
     ย่อหน้าหนึ่งเริ่มจากสถานการณ์ของคนอ่าน อีกย่อหน้าเริ่มจากสิ่งที่ต้องทำ
     อีกย่อหน้าเริ่มด้วยประโยคสั้น ๆ ที่ยืนเดี่ยวได้
  3. บอกสิ่งที่เจาะจง "ฝากถอนรวดเร็ว" คือประโยคที่ใครก็เขียนได้
     โดยไม่ต้องรู้อะไรเลย แต่ "กรอกแค่เลขบัญชีกับจำนวนเงิน"
     คือสิ่งที่เฉพาะคนที่เคยเปิดใช้จริงเท่านั้นที่เขียนได้
     แต่ละย่อหน้าควรมีอย่างน้อยหนึ่งอย่างที่เดาจากหัวข้อเฉย ๆ ไม่ได้
  4. เขียนเหมือนเคยใช้เองมาแล้ว คนที่ใช้จริงจะพูดถึงรายละเอียดเล็ก ๆ เสมอ
     ปุ่มอยู่ตรงไหน กดแล้วขึ้นอะไรต่อ ตรงไหนที่ครั้งแรกแล้วงง
     รายละเอียดเล็ก ๆ พวกนี้คือสิ่งที่งานเขียนของเครื่องไม่มี
     ใส่แค่หนึ่งถึงสองจุดก็เปลี่ยนน้ำเสียงทั้งย่อหน้าได้แล้ว
- ห้ามลอกประโยคจากหน้าเว็บใดก็ตาม หน้าคู่แข่งที่แสดงไว้ข้างบน
  มีไว้บอกว่า "ต้องพูดถึงหัวข้ออะไร" ไม่ได้มีไว้ให้ลอกสำนวน
  ให้เอาแต่หัวข้อ แล้วเขียนประโยคขึ้นใหม่เองทั้งหมด ด้วยลำดับและตัวอย่างที่ต่างออกไป
  คำติดกันสี่คำที่ตรงกับหน้าตัวอย่างเป๊ะ ๆ ก็ถือว่ามากเกินไปแล้ว
  นี่ไม่ใช่เรื่องมารยาท หน้าที่เขียนเหมือนหน้าที่มีอยู่ก่อนแล้ว
  ไม่มีเหตุผลสักข้อที่จะถูกจัดอันดับเหนือกว่า"""


VOICE_TEMPLATE_BY_LANGUAGE = {
    "id": VOICE_TEMPLATE_ID,
    "th": VOICE_TEMPLATE_TH,
}


def voice_rules(language_code: str = "id", niche: str = "gambling") -> str:
    """
    Aturan bunyi tulisan untuk satu bahasa dan satu bidang.

    Bahasa yang belum punya daftarnya sendiri jatuh ke Indonesia,
    sama seperti perilaku sebelum berkas ini ada.

    Bidang bawaannya "gambling", bukan "generic", dan itu disengaja.
    Setiap baris di daftar ini lahir dari halaman judi yang benar-
    benar dikeluhkan pengguna, dan angkanya diukur di halaman itu.
    Pemanggil yang lupa menyebutkan bidangnya mendapat teks yang
    sama persis seperti sebelum bidang ada - kalau bawaannya
    "generic", kelupaan yang sama diam-diam mengubah halaman yang
    selama ini benar.
    """
    bahasa = str(language_code or "").strip().lower()

    template = VOICE_TEMPLATE_BY_LANGUAGE.get(bahasa) or VOICE_TEMPLATE_ID

    bidang = VOICE_EXAMPLES.get(str(niche or "").strip().lower())

    if not bidang:
        bidang = VOICE_EXAMPLES["gambling"]

    contoh = bidang.get(bahasa) or bidang["id"]

    return template.format(
        **contoh,
        frasa_terlarang=", ".join(
            f'"{frasa}"' for frasa in BANNED_PHRASES_ID
        ),
    )


# Nama lama, dipertahankan karena masih dipakai di luar berkas ini.
# Isinya aturan Indonesia untuk bidang yang sama dengan bawaan
# voice_rules, jadi maknanya tidak berubah.
VOICE_RULES_ID = voice_rules("id")
VOICE_RULES_TH = voice_rules("th")

VOICE_RULES_BY_LANGUAGE = {
    "id": VOICE_RULES_ID,
    "th": VOICE_RULES_TH,
}


# Apakah contoh gaya berbahasa Indonesia boleh ikut ke prompt.
#
# knowledge/gaya_title.txt dan gaya_title_deskripsi.txt seluruhnya
# bahasa Indonesia, dan keduanya dikirim sebagai CETAKAN BENTUK -
# "tiru susunan kalimatnya". Untuk halaman Thai itu berarti model
# diminta menyusun kalimat Thai mengikuti susunan kalimat Indonesia,
# yang persis definisi hasil terjemahan.
#
# Jadi untuk zona yang bahasanya bukan bahasa berkas contoh, contohnya
# tidak dikirim sebagai cetakan. Yang tetap bekerja: aturan bentuk
# title (enforce_title_shape), rentang panjang, dan bank kata dari
# SERP - dan bank kata SERP zona Thailand isinya title Thai yang
# benar-benar sedang ngerank, jadi contohnya justru lebih tepat
# daripada berkas Indonesia.
STYLE_EXAMPLE_LANGUAGE = "id"

# Bidang isi berkas contoh gaya.
#
# Ketiga berkas di knowledge/ berisi title, deskripsi, dan artikel
# tentang situs slot - itu memang bidang pengguna, dan untuk halaman
# slot berkas itu bahan terbaik yang ada.
#
# Untuk halaman di bidang lain, ia justru bahan terburuk. Berkasnya
# dikirim sebagai CETAKAN BENTUK dengan perintah "tiru susunannya",
# dan delapan contoh berbunyi "Situs Resmi Slot Gacor No.1" yang
# berdiri di prompt halaman kursus mengajari model dua hal sekaligus:
# susunan kalimatnya, dan kosakatanya. Yang kedua tidak diminta
# siapa pun, dan model kecil tidak memisahkan keduanya.
STYLE_EXAMPLE_NICHE = "gambling"


def style_examples_fit(
    language_code: str = "id",
    niche: str = STYLE_EXAMPLE_NICHE,
) -> bool:
    """
    Apakah berkas contoh gaya cocok dengan halaman yang ditulis.

    Cocok berarti dua hal sekaligus: sebahasa, dan sebidang. Yang
    tidak cocok tidak dikirim sama sekali - lihat keterangan di
    format_style_examples untuk apa yang tetap bekerja tanpanya.

    Bidang bawaannya sama dengan bidang berkasnya, jadi pemanggil
    lama yang cuma menyebut bahasa mendapat perilaku yang sama
    seperti sebelum bidang ikut diperiksa.
    """
    bahasa_cocok = (
        str(language_code or "").strip().lower() == STYLE_EXAMPLE_LANGUAGE
    )

    bidang_cocok = (
        str(niche or "").strip().lower() == STYLE_EXAMPLE_NICHE
    )

    return bahasa_cocok and bidang_cocok
