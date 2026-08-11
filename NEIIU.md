# NEIIU — Keyword ke Landing Page + AMP

Pipeline yang mengubah satu keyword jadi landing page dan versi AMP
yang siap diunggah, dibangun dari pola halaman yang sedang ngerank
di halaman pertama Google.

```
keyword
  -> cari di Google                        (serp/)
  -> crawl dan analisis rank 1-10          (analyzer/serp_analyzer.py)
  -> AI menjelaskan kenapa mereka naik     (generators/content_planner.py)
  -> ambil struktur + gaya halaman acuan   (generators/template_extractor.py)
  -> AI menyusun konten baru               (generators/content_planner.py)
  -> render landing page + AMP             (generators/landing_generator.py, amp_generator.py)
  -> validasi AMP dan SEO                  (generators/amp_validator.py, seo_validator.py)
  -> simpan ke output/
```

---

## Persiapan

### 1. Dependensi

```powershell
.venv\Scripts\pip install -r requirements.txt
```

Tidak ada dependensi baru di luar yang sudah terpasang
(`requests`, `beautifulsoup4`, `python-dotenv`).

### 2. Konfigurasi

```powershell
copy .env.example .env
```

Lalu isi `.env`. Yang paling penting:

| Variabel | Kegunaan |
| --- | --- |
| `SERP_PROVIDER` | `serper`, `google_cse`, atau `manual` |
| `SERPER_API_KEY` | Kalau memakai Serper.dev |
| `SITE_BASE_URL` | Domain asli. **Wajib diganti** sebelum halaman diunggah, karena dipakai untuk canonical, sitemap, dan structured data |
| `SITE_CTA_URL` | Tujuan semua tombol login, daftar, bilah mengambang, dan popup. Kosong berarti menunjuk beranda sendiri |
| `DESIGN_REFERENCES` | URL acuan gaya bawaan, dipisah koma. Bisa ditimpa per run lewat `--design-ref` |
| `AI_MODEL` | Model Ollama yang dipakai |
| `AI_CONTEXT_LENGTH` | Ukuran context. Jangan diturunkan di bawah 16384 kalau meng-crawl 10 kompetitor |

### 2b. Cek sumber SERP

Sebelum menjalankan pipeline penuh, pastikan API key-nya jalan:

```powershell
python check_serp.py
python check_serp.py "slot gacor" --provider serper
```

Kalau gagal, perintah ini langsung mencetak langkah perbaikannya.
Ini menghemat waktu: masalah API key ketahuan dalam hitungan
detik, bukan setelah menunggu puluhan menit.

### Memilih sumber SERP

| | Google CSE (resmi) | Serper.dev |
| --- | --- | --- |
| Sumber | Programmable Search Engine | SERP google.com asli |
| Akurasi peringkat | perkiraan | sesuai yang dilihat pengguna |
| Kuota gratis | 100 query/hari | ~2.500 kredit sekali |
| Setelah kuota | $5 per 1.000 query | jauh lebih murah |
| Targeting negara | terbatas | didukung penuh |

**Google Custom Search API tidak mengembalikan halaman google.com
yang dilihat orang.** Walau disetel "search the entire web",
urutannya bisa berbeda, sebagian hasil tidak muncul, dan tidak ada
personalisasi maupun lokasi.

Ini penting karena seluruh pipeline berdiri di atas asumsi bahwa
yang dianalisis benar-benar peringkat 1–10 di Google. Untuk keyword
Indonesia, Serper.dev jauh lebih mendekati kenyataan.

Google CSE tetap masuk akal kalau kamu butuh API resmi Google
dengan kuota gratis dan tidak masalah urutannya hanya perkiraan.

### 3. Ollama

```powershell
ollama serve
ollama pull qwen3:4b-instruct
```

---

## Keyword vs Brand

Dua hal ini terpisah dan tidak boleh tertukar:

| | Keyword | Brand |
| --- | --- | --- |
| Isinya | Topik yang dicari orang di Google | Nama situs yang menyajikan halaman |
| Contoh | `slot gacor` | `ABECE`, `DEFAFA` |
| Dipakai untuk | Riset SERP, target metrik, isi konten | Title, H1, footer, structured data, canonical |

Satu keyword yang sama bisa dipakai untuk berapa pun brand:

```powershell
python neiiu.py "slot gacor" --brand ABECE  --base-url https://abece.com
python neiiu.py "slot gacor" --brand DEFAFA --base-url https://defafa.id
```

Riset SERP-nya sama, tapi halaman yang keluar beda brand, beda
domain, beda folder output. Cache SERP membuat run kedua melewati
langkah pencarian, jadi lebih cepat dan tidak menghabiskan kuota API.

Kalau `--brand` dikosongkan, dipakai `SITE_NAME` dari `.env`.
Begitu juga `--base-url` dengan `SITE_BASE_URL`.

### Penempatan brand di halaman

Content planner diminta menyebut brand di paragraf pembuka dan di
penutup, total 3–5 kali sepanjang halaman. Menyebutnya di tiap
paragraf membuat halaman terbaca seperti iklan.

Kalau model lupa memasukkan brand atau keyword ke title dan H1,
`normalize_plan()` menambalnya jadi satu awalan gabungan:

```
ABECE Slot Gacor: Panduan Memilih Situs Terpercaya
```

Model juga dilarang mengarang klaim tentang brand — jumlah member,
lisensi, penghargaan, tahun berdiri — karena datanya memang tidak
ada di mana pun dalam pipeline ini.

## Cara Pakai

```powershell
# paling dasar
python neiiu.py "slot gacor"

# dengan brand sendiri
python neiiu.py "slot gacor" --brand ABECE --base-url https://abece.com

# hanya analisis SERP, tanpa membuat halaman
python neiiu.py "slot gacor" --analyze-only

# pilih sendiri halaman acuan templatenya
python neiiu.py "slot gacor" --reference https://contoh.com/halaman

# paksa ambil SERP baru, abaikan cache
python neiiu.py "slot online" --no-cache

# batasi jumlah halaman yang di-crawl biar cepat
python neiiu.py "slot gacor" --crawl 5

# halaman baru dengan gaya ditiru dari situs pilihan sendiri
python neiiu.py "slot gacor" `
  --brand WAYANGPLAY --base-url https://wayangplay.id `
  --design-ref https://situs-yang-saya-suka.com/ `
  --cta-url https://link-daftar.example/
```

---

## Halaman Baru Tanpa Template

Kalau `--template` tidak dipakai, NEIIU tidak lagi menghasilkan
halaman artikel polos. Ia merakit halaman sendiri dari pustaka blok
di `generators/blocks.py`:

| Blok | Isinya |
| --- | --- |
| `navbar` | Nama brand, menu ke tiap section, tombol daftar |
| `popup` | Popup pembuka berisi tombol login dan daftar |
| `cta_duo` | Sepasang tombol besar di bawah hero |
| `ratings` | Tiga aspek layanan beserta bintangnya |
| `testimoni` | Kartu ulasan member |
| `tags` | Deretan pil topik |
| `footer_sitemap` | Footer bertingkat berisi kolom tautan |
| `floatbar` | Bilah mengambang di bawah layar |

Susunannya tetap. Yang berganti tiap halaman adalah **warna dan
teksnya** — itu keputusan yang disengaja, karena susunan yang
berubah-ubah membuat hasilnya sulit diperiksa dan sulit diperbaiki
kalau ada yang salah.

### Dari mana gayanya

`--design-ref` menerima URL halaman yang gayanya mau ditiru, dan
boleh diulang beberapa kali. Yang dibaca dari halaman itu hanya:

- palet warna, nama font, dan besar radius, dari CSS-nya
- komponen apa saja yang dipakai, dari markupnya

Teks, HTML, dan CSS halaman acuan **tidak pernah ikut tersalin**.
Halaman baru selalu dirakit ulang dari pustaka blok sendiri.

Kalau `--design-ref` dikosongkan, urutan cadangannya: `--reference`,
lalu halaman acuan yang dipilih dari SERP, lalu palet bawaan.
Halaman acuan yang mati atau menolak request cukup dicatat lalu
dilewati — satu acuan yang gagal tidak menggagalkan seluruh run.

### Warna

Titik berangkatnya warna aksen halaman acuan, lalu ronanya diputar
sejauh salah satu dari sembilan jarak tetap. Memutar rona menjaga
kekontrasan tetap utuh, sehingga teksnya selalu terbaca — hal yang
tidak dijamin kalau ketiga kanal RGB diacak bebas.

Nomor variasinya diambil dari nama folder hasil, dan nama itu memuat
waktu run. Dua halaman dengan brand dan keyword yang sama karena itu
tetap keluar dengan warna berbeda. Pakai `--color N` kalau ingin
memilih sendiri.

### Pilihan lain

| Perintah | Gunanya |
| --- | --- |
| `--cta-url` | Tujuan semua tombol login, daftar, bilah, dan popup |
| `--color N` | Kunci varian warna ke nomor tertentu |
| `--kit-from-ref` | Pasang hanya blok yang terdeteksi di acuan |
| `--plain` | Kembali ke halaman artikel polos seperti dulu |

Bawaannya seluruh blok dipasang, dan acuan hanya menentukan warna
serta font. Alasannya: halaman acuan yang kebetulan tidak punya
popup akan menghasilkan halaman baru tanpa popup, padahal yang
diminta dari acuan itu gayanya, bukan daftar komponennya.

### Ulasan dan penilaian

Blok testimoni dan rating diisi dari rencana konten, dan angka yang
sama itu juga yang masuk ke `Product` + `AggregateRating` + `Review`
di JSON-LD. `reviewCount` dan `ratingValue` dihitung dari ulasan
yang benar-benar terbit di halaman, bukan diisi angka besar:
structured data yang melaporkan ribuan ulasan sementara halamannya
menampilkan empat adalah pelanggaran pedoman Google yang bisa
membuat seluruh rich result situs dicabut.

Tanggal ulasan tidak pernah diminta ke model, karena model kecil
rutin menulis tanggal yang tidak ada di kalender atau jatuh di masa
depan. NEIIU memasangnya sendiri, mundur dari hari ini, dalam dua
bentuk: bentuk baca yang mengikuti kalender zona (tahun Buddha untuk
zona Thailand) dan bentuk ISO masehi untuk mesin.

### Versi AMP

Dua blok berbeda di AMP, dan bedanya bukan kosmetik:

- **Popup tidak dipasang.** Ia memakai kotak centang tersembunyi
  supaya bisa ditutup tanpa JavaScript, dan AMP melarang `<input>`
  di luar amp-form.
- **Bilah mengambang duduk di akhir halaman.** AMP hanya
  mengizinkan `position: fixed` untuk segelintir elemen bawaannya,
  jadi aturan itu tidak ikut ditulis sama sekali ke
  `<style amp-custom>` — bukan sekadar tidak terpakai.

Besar bintang penilaian ditentukan kelas `st-NN`, bukan atribut
`style`, karena gaya sebaris melanggar AMP. CSS akhirnya sekitar
7–8KB, jauh di bawah batas 75KB.

Tambahkan `-u` di depan (`python -u neiiu.py ...`) kalau outputnya
mau di-pipe ke file dan tetap ingin melihat progres.

### Apa yang diubah di template unggahan

Template yang diunggah adalah milik pengguna, jadi yang ditulis
ulang dibatasi pada isi yang memang membicarakan brand-nya:

| ditulis ulang | dibiarkan apa adanya |
| --- | --- |
| title, meta description, meta keywords | menu, tombol, label formulir |
| h1 dan seluruh heading | keterangan gambar |
| pertanyaan dan jawaban FAQ | sel tabel |
| isi ulasan, nama pengulas, kota | butir daftar di luar blok brand |
| paragraf **di dalam blok brand lama** | paragraf milik pemilik template |
| blok artikel yang dirakit NEIIU | |

Batas "blok brand lama" ditentukan struktur judul, bukan ambang
jarak: satu bagian dianggap milik brand lama kalau judul `h2`–`h6`
yang mengepalainya menyebut namanya. `h1` sengaja tidak ikut
membatasi — ia menamai seluruh halaman, bukan satu bagian, dan
memakainya membuat isi milik pemilik template ikut terhitung. Nama
brand lamanya boleh dikosongkan; kalau begitu ia ditebak dari
potongan judul sebelum tanda pisah pertama.

Dua lapis tetap menyapu SELURUH halaman, termasuk bagian yang
dibiarkan:

- **Nama brand lama diganti nama baru**, di mana pun ia tertulis.
- **Teks yang bunyinya sama persis dengan judul lama memakai judul
  baru.** Ini yang mengurus atribut `alt` gambar: template uji punya
  34 gambar yang seluruh `alt`-nya berisi judul lama, dan ketiga
  puluh empatnya terbit dengan judul baru — bukan dengan kalimat
  karangan yang berbeda-beda di tiap gambar. Kalau `<title>`,
  `<meta>`, dan `<h1>` kebetulan berbunyi sama, yang menang **title**.

Nama pengulas dikenali dari letaknya, bukan dari penandanya: baris
teks pendek yang berdiri tepat sebelum sebuah isi ulasan. Template
uji menulisnya sebagai `<strong>` polos tanpa class, dan bentuk
aslinya — `Nama — Kota • ★★★★★` — ikut dikirim ke model supaya nama
dan kotanya berganti tanpa kehilangan tanda pisah dan bintangnya.

### Panjang artikel di template unggahan

Halaman ini **sudah punya tempat artikel**, dan tempat itulah yang
dipakai: blok artikel milik template diisi lewat jalur slot biasa,
paragraf demi paragraf, di tempatnya masing-masing.

Kolom **Panjang artikel (kata)** di web app — atau `--article-words N`
di CLI — tidak pernah menambah satu paragraf pun. Yang dinaikkan
**jatah karakter tiap slot paragraf yang sudah berdiri di template**,
dan model menulis lebih panjang di tempat yang sama. Jumlah paragraf
di halaman terbit persis sama dengan jumlah paragraf di template
unggahan, berapa pun targetnya.

Pelebarannya **sebanding**, bukan rata. Paragraf pembuka berjatah 542
karakter dan keterangan berjatah 298 punya peran berbeda di halaman;
menyamakan keduanya jadi 400 menghapus irama yang sudah ada di
templatenya. Dikali faktor yang sama, selisihnya tetap.

Diukur di template uji, yang punya tujuh slot paragraf cukup lebar:

| target | slot dilebarkan | jatah tiga slot terlebar | tercapai |
| --- | --- | --- | --- |
| kosong | 0 | 542, 473, 298 | — |
| 600 | 7 | 1008, 880, 554 | 600 kata |
| 900 | 7 | 1512, 1320, 831 | 900 kata |
| 1.500 | 7 | 1626, 1419, 894 | **966 kata** |

Tiga batas yang menjelaskan baris terakhir:

- **Satu paragraf paling banyak melar tiga kali lipat.** Tanpa batas
  ini, target 3.000 kata di template yang muat 322 membuat tiap
  paragraf diminta sembilan kali lipat — dan paragraf 4.000 karakter
  bukan paragraf lagi, melainkan satu blok teks yang tidak dibaca
  siapa pun. Target yang tidak tercapai **dikatakan apa adanya** di
  log job, bukan didiamkan.
- **Satu slot paling panjang 1.200 karakter** (`MAX_SLOT_BUDGET`,
  disamakan dengan `MAX_LENGTH_BUDGET`). Batas perbandingan saja
  tidak cukup: slot berjatah 542 melar jadi 1.626 kalau cuma dibatasi
  tiga kali lipat.
- **Slot yang jatahnya di bawah 200 karakter tidak ikut dilebarkan.**
  Delapan dari lima belas slot `paragraph` di template uji berjatah
  79–172 karakter; itu keterangan kartu fitur yang berdiri di kolom
  sempit, dan kartu berisi 79 karakter yang dipaksa memuat 300 akan
  mendorong kartu di sebelahnya keluar dari barisnya.

### Batas grammar Ollama

Batas kedua di atas bukan cuma soal selera. `maxLength` di JSON Schema
diubah llama.cpp jadi aturan pengulangan karakter, dan di atas sekitar
dua ribu ia menyerah — permintaannya ditolak sebelum satu token pun
ditulis:

```
400 Bad Request
Failed to initialize samplers: failed to parse grammar
```

Dibisect di mesin ini: **1998 lolos, 2012 gagal**. Jumlah item di
dalam array tidak berpengaruh — 1 item dan 15 item sama-sama lolos di
1600 — jadi yang dibatasi memang panjang satu teks.

Ini pernah membatalkan satu run di giliran 2 dari 4. Dua jalan
menabraknya, dan dua-duanya nyata:

1. Jatah paragraf yang dilebarkan kolom Panjang artikel — terukur
   1.626 karakter, dikali kelonggaran grammar 1,3 jadi 2.113.
2. Zona beraksara bertumpuk: `scale_spec` menggandakan seluruh jatah
   untuk Thai, jadi slot 1.200 karakter jadi 2.400 **bahkan tanpa
   target panjang sama sekali**.

Karena itu ada dua pengaman, bukan satu: `MAX_SLOT_BUDGET` menahan
jatahnya sejak awal, dan `SCHEMA_MAX_LENGTH = 1800` di
`build_dynamic_schema()` memotong plafon grammar apa pun yang lolos ke
sana. Angkanya dipasang jauh di bawah ambang terukur, karena ambang
itu milik satu versi llama.cpp di satu mesin.

Diuji ke Ollama sungguhan sesudahnya — target 1.000, target 5.000, dan
zona Thailand tanpa target — keempat giliran diterima di ketiganya.

Terukur dengan model sungguhan pada tiga slot yang sama:

| | jatah | panjang yang ditulis |
| --- | --- | --- |
| sebelum dilebarkan | 542, 473, 298 | 530, 495, 476 |
| target 900 | 1512, 1320, 831 | 997, 930, 859 |

**Dua bentuk sebelumnya ditolak pengguna**, dicatat supaya tidak
diulang orang ketiga:

1. Satu `<section>` utuh ditempel sebelum `</main>`, lengkap dengan
   judul dan gayanya sendiri. Halaman terbit dengan dua artikel
   berjejer — *"artikelnya 1 aja, di tempat biasa itu."*
2. Lanjutan berupa `<h2>` dan `<p>` polos disisipkan ke dalam blok
   artikel yang sama, sebelum judul FAQ. Tetap salah, karena tetap
   menambah paragraf — *"bukan menambah paragraf baru tetapi
   memperpanjang isi paragraf yang sudah ada."*

Yang berlaku sekarang cara ketiga, dan `fill_template` tidak
menyisipkan satu byte pun untuk artikel.

### Kenapa jawaban FAQ diminta di giliran terpisah

Cacat yang paling kelihatan di halaman jadi: **ditanya A dijawab B**.
Terukur pada halaman terbit — pertanyaan *"Bagaimana proses deposit di
TIMAH33?"* dijawab *"Proses login di TIMAH33 dilakukan secara otomatis
melalui browser"*, sementara kalimat yang menjawabnya justru terpasang
di kartu lain.

Sebabnya bukan model yang bodoh, melainkan cara memintanya. Selama
`faq_question` dan `faq_answer` muat di satu giliran, keduanya diminta
dalam **satu objek JSON**: model menulis tujuh pertanyaan
berturut-turut, lalu tujuh jawaban berturut-turut, dan harus mengingat
sendiri jawaban keempat itu milik pertanyaan yang mana. Model 4B tidak
sanggup, dan urutannya melenceng di tengah daftar.

`AFTER_ROLES` di `generators/content_batches.py` memaksa keduanya
jatuh di giliran yang berbeda:

```
giliran 1: title, meta_description, meta_keywords, h1
giliran 2: heading, paragraph
giliran 3: paragraph, faq_question
giliran 4: faq_answer, review_text, review_author
```

Giliran 4 menerima daftar bernomor lewat bagian *"Pertanyaan Yang
Harus Dijawab Berurutan"*, jadi jawaban ke-N ditulis sambil melihat
pertanyaan ke-N. Aturannya ikut disebut: pertanyaan **CARA** dijawab
dengan langkahnya, **APAKAH** dijawab mulai dengan ya atau tidak,
**BERAPA LAMA** dijawab dengan menyebut waktunya.

Harganya satu giliran tambahan. Awalan promptnya sama persis dengan
giliran sebelumnya, jadi yang dibayar cuma jawabannya sendiri.

Diuji dengan model sungguhan pada tujuh pertanyaan template: **tujuh
dari tujuh** jawabannya cocok dengan pertanyaannya, dan ketiga aturan
bentuk di atas diikuti.

Satu jebakan yang ikut ditutup: giliran susulan — yang mengisi jawaban
yang tadi dilewati model — punya posisi yang **berserak**, bukan
berurutan. Memakai potongan berurutan di situ menampilkan pertanyaan
ke-3 dan ke-4 untuk lubang yang sebenarnya ada di posisi ke-3 dan
ke-6. `gap_spec` mencatat posisinya di `positions`, dan bagian prompt
itu membacanya.

### Kenapa pertanyaan FAQ terbit kosong

Gejalanya satu — "5 dari 7 faq_question terisi" — tapi sebabnya tiga,
dan ketiganya berdiri sendiri-sendiri.

**1. Jatah slot yang mencekik.** Jatah diturunkan dari lebar teks
lama, dan satu slot di template uji berisi *"Apakah proses deposit
QRIS aman?"* — 32 kolom, jadi jatahnya 43 karakter. Pertanyaan tidak
pernah dipotong (memotong pertanyaan menghasilkan pertanyaan yang
rusak, bukan yang lebih pendek), jadi jawaban model yang 58 karakter
dibuang bulat-bulat. Nama brand baru saja sudah memakan selisihnya.
`MIN_ROLE_BUDGET` sekarang memberi lantai 90 karakter untuk
`faq_question`, 160 untuk `faq_answer`, 140 untuk `review_text` —
ketiganya teks yang mengalir dan membungkus sendiri, jadi yang dijaga
bukan lebar kotaknya.

**2. Giliran ulang yang buta.** Model menutup daftarnya lebih awal,
sisanya diminta lagi — tapi `terkumpul` baru diisi **sesudah** satu
giliran tuntas, jadi permintaan susulan berangkat tanpa tahu lima
pertanyaan yang barusan ditulisnya sendiri. Yang keluar variasi dari
lima itu, penyaring kembar membuangnya, dan slotnya tetap kosong
sesudah dua kali diminta. Sekarang `minta()` menerima `sudah` dari
luar, dan giliran ulang membawa isi giliran berjalan.

**3. Penyaring kembar yang memakan pertanyaan yang benar.** Tujuh
pertanyaan tentang satu topik sempit terpaksa berbagi hampir seluruh
kosakatanya. Terukur pada tujuh pertanyaan yang **semuanya berbeda**:

| pasangan | irisan kata |
| --- | --- |
| tertinggi antar tujuh pertanyaan berbeda | 0.50 |
| "Apakah transaksi QRIS bisa gagal?" vs "Bagaimana jika QRIS gagal saat transaksi?" | **1.00** |

Ambang 0,5 tidak menyisakan ruang sama sekali, dan dua pertanyaan yang
sama sekali berbeda bisa terbaca identik karena `content_tokens`
menyaring kata pendek — yang tersisa dari keduanya cuma
`{transaksi, qris, gagal, juhi88}`.

Yang memisahkan dengan bersih **kata tanyanya**. Dua pertanyaan yang
dibuka kata tanya berbeda tidak pernah dihitung mengulang, berapa pun
irisan kosakatanya — yang menentukan bukan kata-katanya melainkan apa
yang diminta. Sesudahnya: tujuh pertanyaan berbeda lolos semuanya,
sementara *"Apakah deposit QRIS aman?"* / *"Apakah deposit QRIS aman
dan terpercaya?"* tetap dibatalkan.

### Pasangan yang cuma terisi sebelah

Penutup terakhir, dan yang paling menentukan buat pembaca.
`balance_paired_roles()` dulu cuma menyamakan **jumlah**; kalau tujuh
pertanyaan dan tujuh jawaban sama banyaknya, ia tidak melihat apa-apa
— padahal yang ke-4 di salah satu sisi kosong. Slot itu lalu terbit
dengan pertanyaan **lama** milik brand lama, sementara jawaban barunya
sudah terpasang di bawahnya.

`drop_broken_pairs()` mengosongkan keduanya. Satu kartu yang memakai
teks asli template seutuhnya — pertanyaan lama dengan jawaban lama,
nyambung meski bukan tentang brand baru — jauh lebih baik daripada
pasangan yang saling tidak kenal. Pasangan kosong juga tidak ikut ke
`plan["faq"]`, jadi tidak pernah terbit sebagai `<Question>` bernama
string kosong di structured data maupun di halaman AMP.

### Pertanyaan FAQ yang topiknya sama sekali lain

Keluhan pengguna: halaman "slot gacor" terbit dengan kartu FAQ
**"Seberapa Pancasila Dirimu?"**. Dugaan pertama — model kecil
mengarang — keliru. Model tidak pernah menulis kalimat itu. Ia
disalin ke halaman oleh Python, dan asalnya bisa ditelusuri sampai
ke domainnya.

**Rantai kejadiannya.** Keyword "slot gacor" waktu itu memunculkan
halaman pertama yang isinya enam situs pemerintah dan kampus yang
dibajak: `aceh.lan.go.id`, `bpsdm.kemenkum.go.id`,
`jurnal.poltekkesmamuju.ac.id`, dan seterusnya. Isi judinya cloaking
— cuma dilayani ke Googlebot — jadi yang terbaca crawler ini justru
isi asli situsnya: pelatihan ASN, kebijakan publik, Pancasila.

`check_usability()` menangkap keenamnya dengan benar dan log run itu
mencatatnya satu per satu sebagai "tidak terbaca". Yang membocorkan
adalah dua baris di tempat lain:

1. **`build_blueprint()` jatuh balik ke halaman kotor.** Begitu tidak
   ada halaman bersih tersisa, `ok_pages` diisi ulang dengan
   **seluruh** halaman. Fallback itu ada supaya angka target tetap
   bisa dihitung, dan untuk angka alasannya masih benar. Tapi
   `ok_pages` yang sama dipakai lagi untuk memanen entity, tema
   heading, dan pertanyaan FAQ kompetitor. Satu-satunya pertanyaan
   yang terpanen hari itu adalah milik situs LAN RI.
2. **`fit_content_to_spec()` menempelkannya ke slot kosong.** Model
   menulis 6 pertanyaan yang benar dan membiarkan slot ke-7 kosong.
   Lubang itu ditambal dari `people_also_ask + competitor_questions`
   — apa adanya, tanpa lewat model. Jawabannya baru ditulis
   belakangan di giliran terpisah, dan giliran itu memang
   diperlihatkan pertanyaan yang sudah terpasang, jadi model dengan
   patuh menjawab *"Seberapa pancasila diriku, saya menjawab
   bahwa sistem di WAYANGPLAY…"*.

**Perbaikannya.** `build_blueprint()` sekarang memegang dua daftar.
`ok_pages` boleh jatuh balik dan dipakai untuk **angka** saja.
`clean_pages` tidak pernah jatuh balik dan itulah satu-satunya sumber
**kata**: `common_entities`, `competitor_questions`, `heading_topics`,
`common_headings`. Kalau tidak ada halaman bersih, keempatnya terbit
kosong — dan kosong memang jawaban yang benar.

Terukur pada SERP yang sama:

| | sebelum | sesudah |
| --- | --- | --- |
| `competitor_questions` | 1 | 0 |
| `common_headings` | 25 | 0 |
| `heading_topics` | 20 | 0 |
| `target` (semua median) | ada | **sama persis** |

Pada keyword yang halaman pertamanya bersih (`belajar python`,
`hijack_fallback` False) seluruh isi blueprint **identik** dengan
sebelum perbaikan — `clean_pages` memang salinan `ok_pages` selama
fallbacknya tidak jalan.

Efek sampingnya di halaman: slot FAQ ke-7 sekarang terbit kosong,
bukan terisi teks asing. Kosong berarti giliran susulan memintanya
lagi ke model, dan kalau tetap kosong slotnya memakai teks asli
template — pertanyaan lama yang tidak nyambung, tapi masih tentang
sesuatu yang ditawarkan situs judi, bukan tentang ideologi negara.

**Dua hal yang sekarang kelihatan di log.** Saat fallback jalan,
step 2 menambahkan satu baris bahwa kosakata kompetitor tidak dipakai
sama sekali, supaya FAQ dan heading yang lebih tipis tidak terbaca
seperti kesalahan lain. Dan tiap slot yang ditambal dari bahan
kompetitor sekarang dihitung tersendiri — dulu ia ikut terhitung
"terisi" dan tidak meninggalkan jejak apa pun, dan justru itu yang
membuat kejadian ini lama dikira model yang mengarang.

Lihat juga [Deteksi Domain Bajakan](#deteksi-domain-bajakan).

### Title dan meta description tidak boleh kembar

Keluhan pengguna: keduanya berbunyi hal yang sama. Terukur — judul
*"JUHI88 Slot Gacor Terpercaya dengan Deposit QRIS Cepat dan Aman"*,
deskripsi dibuka *"JUHI88 slot gacor terpercaya dengan deposit QRIS
cepat dan aman."* Kalimat yang sama, huruf kecil, lalu disambung.

Tiga lapis, karena satu tidak cukup:

1. **Giliran terpisah.** `AFTER_ROLES` memaksa `meta_description`
   jatuh sesudah `title`, sama seperti FAQ. Selama keduanya diminta
   dalam satu objek JSON, yang paling mungkin ditulis sesudah sebuah
   kalimat adalah kalimat itu lagi, sedikit lebih panjang.
2. **Larangan tertulis.** Bagian "Sudut Pandang Halaman Ini" menyuruh
   melanjutkan sudut judulnya — dan cara paling malas melanjutkan
   sebuah kalimat adalah menuliskannya lagi. Untuk giliran yang
   menulis deskripsi, bagian itu sekarang membawa larangan tegas
   beserta alasannya: judulnya sudah terbaca sendiri tepat di atas
   deskripsi, jadi mengulangnya membuang seluruh baris pertama.
3. **Diminta lagi kalau tetap mengulang.** `echoes_text()`
   membandingkan **pembuka** deskripsi sepanjang judulnya sendiri,
   per frasa tiga kata, ambang 0,5. Kalau kena, deskripsinya diminta
   sekali lagi — dengan suhu di atas nol permintaan yang sama
   menghasilkan kalimat yang berbeda — dan yang lebih baik yang
   dipakai.

Yang dibandingkan hanya pembukanya. Deskripsi yang menyebut lagi nama
brand dan keywordnya di tengah kalimat memang seharusnya begitu.

### Lantai panjang untuk teks di badan halaman

Keluhan pengguna: ulasannya terlalu pendek. Terukur — lima slot ulasan
di template uji berjatah 162, 176, 172, 148, dan 164 karakter, cukup
untuk dua kalimat, dan yang terbit rutin satu kalimat pujian.

Sebabnya sama dengan title: promptnya cuma menyebut **plafon**.
Berhenti lebih awal tidak melanggar apa pun yang tertulis di situ.

`BODY_FLOOR` di `generators/template_slots.py` memberi lantai ke tiga
peran — `review_text` 120, `paragraph` 150, `faq_answer` 110 — dan
lantai sesungguhnya diambil yang lebih besar antara angka itu dan
**55% jatah slotnya sendiri**. Jadi slot berjatah 542 karakter
berlantai 298, sementara slot berjatah 124 tidak diberi lantai sama
sekali: yang seperti itu bukan paragraf artikel melainkan keterangan
pendek yang kebetulan berperan sama.

Lantai itu sampai ke model sebagai **rentang**, bukan plafon:

```
- paragraph: tepat 15 teks, panjang per teks:
  ke-1 298-542, ke-2 260-473, ke-3 150-157, ...
```

Dan lantainya ikut melar waktu jatahnya dilebarkan. Kalau tidak,
seluruh gunanya menaikkan target hilang di kalimat terakhir prompt:
slot yang jatahnya naik 542 jadi 1626 tetap membawa lantai 298, dan
model memilih ujung bawahnya — persis panjang yang sama dengan
sebelum targetnya dinaikkan.

Yang jawabannya tetap **di bawah setengah lantai** dihitung sebagai
lubang dan diminta lagi, sama seperti slot yang benar-benar kosong.
Yang di antaranya dibiarkan: pendek, tapi masih kalimat utuh, dan satu
giliran ulang lebih mahal daripada selisihnya. Giliran ulang memakai
yang **lebih panjang** di antara jawaban lama dan baru, supaya
permintaan ulang tidak pernah menukar teks pendek dengan teks yang
lebih pendek lagi.

Terukur dengan model sungguhan, ulasan sesudah perbaikan ini:

> *"Saya setor lewat QRIS pukul 02.15 pagi dari bank BCA, saldo
> langsung masuk ke akun TIMAH33 sebelum saya tutup aplikasi bank."*
> (124 karakter)

Isi ulasannya juga diikat ke title: yang diceritakan harus hal yang
disebut di judul halaman. Halaman yang judulnya tentang deposit QRIS
satu detik tapi ulasannya membicarakan grafis permainan sedang memuji
hal yang bukan janjinya sendiri.

### Kenapa batas kalimat dicari di teks asli

Bug yang sempat terbit, ketemu waktu menguji jawaban FAQ.
`trim_to_width` menggeser potongannya ke batas kata, dan geseran itu
membuang tanda titik yang kebetulan berdiri **persis di ujung jatah**.
Jawaban berjatah 244 karakter yang kalimat keduanya berakhir tepat di
karakter ke-244 karena itu kehilangan kata terakhirnya lebih dulu,
lalu dicarikan titik di sisa yang sudah tidak punya titik:

| | hasil |
| --- | --- |
| sebelum | `...prosesnya selesai dalam waktu kurang dari satu.` |
| sesudah | `...prosesnya selesai dalam waktu kurang dari satu detik.` |

Sekarang batas kalimat dicari di teks aslinya, bukan di hasil potongan
lebar. Lantai panjang sengaja **tidak** ikut ke tahap pemotongan:
kalimat utuh yang pendek selalu lebih baik daripada potongan panjang
yang berhenti di tengah pikiran.

### Kenapa paragraf dibandingkan per frasa, bukan per kata

Teks yang mengulang isi teks lain dibatalkan sebelum ditulis. Untuk
teks pendek — pertanyaan FAQ, label — yang dibandingkan irisan
katanya, dengan ambang 0,5 yang diukur dari pertanyaan yang memang
mengulang.

Untuk paragraf artikel aturan itu tidak bisa dipakai sama sekali.
Terukur pada tiga kumpulan teks:

| kumpulan | irisan kata | frasa 3 kata |
| --- | --- | --- |
| tulisan asli pengguna, 16 paragraf | 0,396 | 0,101 |
| kerangka kalimat sama, 20 paragraf | 1,000 | 0,829 |
| beragam tapi sekosakata, 42 paragraf | 0,880 | 0,500 |

Baris kedua harus dibatalkan dan baris ketiga harus lolos — dan
dengan irisan kata tidak ada satu pun ambang yang bisa memisahkan
0,880 dari 1,000, karena paragraf yang membahas satu topik memang
memakai kata yang itu-itu juga. Akibatnya terukur: artikel 42
paragraf terbit tinggal 26.

Yang membedakan paragraf yang mengulang dari paragraf yang cuma
setopik adalah apakah URUTAN katanya ikut sama. Paragraf karena itu
dibandingkan per potongan tiga kata berurutan, dengan ambang 0,65 —
duduk di ruang kosong antara 0,500 dan 0,829.

Dua hal yang berbeda di berkas AMP:

- **Tidak kebagian `<style>`.** AMP hanya mengizinkan satu
  `<style amp-custom>` di seluruh dokumen; yang kedua membuat
  halamannya gugur dari hasil pencarian AMP. Bloknya masuk tanpa
  gaya dan mewarisi tampilan template apa adanya.
- Kalau berkas AMP tidak diunggah sama sekali, versi AMP dibuat
  generator biasa dari rencana konten — dan blok artikel ikut ke
  sana lewat `article_plan_sections`, jadi halaman AMP tidak pernah
  terbit tanpa isi utamanya.

### Lewat web app

```powershell
python serve.py
```

Buka <http://127.0.0.1:8000/neiiu> (atau lewat menu **Tools →
Generator Landing Page** di sidebar chat).

### Membuka dari PC atau HP lain

`serve.py` sudah membuka server ke seluruh jaringan lokal dan
mencetak alamat yang harus dibuka dari perangkat lain:

```
Buka dari PC atau HP lain di jaringan yang sama:
  http://192.168.10.163:8000/neiiu
```

`127.0.0.1` tidak bisa dipakai dari perangkat lain, karena di
perangkat itu alamat tersebut menunjuk ke dirinya sendiri.

Yang perlu diperhatikan:

- Perangkatnya harus tersambung ke Wi-Fi atau jaringan yang sama.
- Windows Firewall menanyakan izin saat pertama kali dijalankan.
  Pilih **Allow** untuk jaringan **Private**.
- Sambungannya HTTP biasa, **bukan** HTTPS. Password yang diketik
  dari perangkat lain lewat dalam bentuk terbaca di jaringan lokal.
  Pakai hanya di jaringan yang kamu percaya, jangan di Wi-Fi publik.
- Pakai `python serve.py --local-only` untuk kembali ke perilaku
  lama yang hanya bisa dibuka dari komputer itu sendiri.

**Kunci sesi.** Nilai bawaannya dulu berupa teks tetap di dalam
`web_app.py`, dan file itu ter-commit. Selama server hanya
mendengarkan di `127.0.0.1` hal itu tidak berbahaya, tapi begitu
dibuka ke jaringan, siapa pun yang bisa membaca kode ini dapat
menandatangani cookie sesi sendiri dan masuk sebagai admin tanpa
password. `serve.py` sekarang membuatkan kunci acak dan
menyimpannya di `.env` pada run pertama. Kalau `web_app` dijalankan
langsung tanpa kunci itu, kuncinya dibuat acak per proses — aman,
tapi semua sesi login berakhir tiap kali server dimatikan.

### Membatasi akses per alamat IP

Setelah server dibuka ke jaringan, **semua perangkat di jaringan
yang sama bisa sampai ke halaman login**. Untuk membatasinya, buka
**Admin → Akses per alamat IP**.

Di sana ada:

- Alamat perangkat yang sedang kamu pakai, sudah terisi di kolom
  tambah supaya tinggal klik
- Daftar IP yang diizinkan, bisa ditambah dan dihapus
- Tombol menyalakan dan mematikan penyaringan

Formatnya menerima alamat tunggal (`192.168.1.20`) maupun rentang
CIDR (`192.168.1.0/24`). Rentang berguna karena alamat perangkat
bisa berganti sendiri setiap tersambung ulang ke Wi-Fi.

Dua hal yang menjaga supaya kamu tidak terkunci sendiri:

1. **`127.0.0.1` selalu diizinkan dan tidak bisa dihapus.**
   Komputer yang menjalankan server selalu punya jalan masuk untuk
   membetulkan daftar yang salah atur.
2. **Penyaringan tidak bisa dinyalakan saat daftarnya masih
   kosong.** Kalau bisa, semua perangkat selain komputer server
   akan langsung tertolak, termasuk laptop yang sedang dipakai
   mengaturnya.

Penyaringan berjalan sebelum halaman login, jadi perangkat asing
bahkan tidak melihat formulir loginnya.

**Alamat dibaca dari sambungan langsung, bukan dari header
`X-Forwarded-For`.** Header itu diisi oleh pengirim request dan
bisa dikarang siapa saja; memakainya akan membuat penyaringan bisa
dilewati hanya dengan menambahkan satu baris header. Konsekuensinya,
kalau nanti aplikasi ini ditaruh di belakang reverse proxy, semua
request akan terlihat berasal dari proxy dan penyaringan ini perlu
disesuaikan lebih dulu.

### Mengunduh hasil

Setiap kartu job punya tombol **Unduh semua (ZIP)** berisi
`index.html`, `amp/index.html`, `sitemap.xml`, `ANALISIS.md`, dan
`report.json`. File masuk ke folder unduhan **perangkat yang
membukanya**, bukan komputer yang menjalankan server — jadi setiap
PC mengunduh hasilnya sendiri-sendiri.

Di sana ada form keyword, pilihan provider, jumlah halaman yang
di-crawl, dan URL acuan opsional. Setelah dijalankan, kemajuan
langkah 1–8 tampil langsung beserta lognya, dan hasilnya bisa
dipratinjau atau diunduh dari daftar riwayat.

Beberapa hal yang perlu diketahui soal mode web:

- **Satu job jalan pada satu waktu.** Job berikutnya masuk antrian.
  Menjalankan dua pipeline sekaligus di satu mesin justru membuat
  keduanya berebut CPU dan lebih lambat daripada berurutan.
- **Satu job memotong 1 token**, sama seperti satu pesan chat.
  Kalau jobnya gagal, tokennya dikembalikan otomatis.
- **Job runner hidup di dalam proses server.** Kalau server
  dimatikan di tengah run, job itu ditandai gagal saat server
  dinyalakan lagi — ia tidak dilanjutkan sendiri.
- Halaman bisa ditutup kapan saja; job tetap jalan. Saat halaman
  dibuka lagi, ia otomatis menempel ke job yang sedang berjalan.

### Konfirmasi hapus

Tombol **Hapus** pada kartu job dan kartu template dulu memakai
`confirm()` bawaan browser. Di Chrome kotak itu muncul menempel di
tepi atas jendela, jauh dari tombol yang baru ditekan, dan
tampilannya tidak ikut tema gelap halaman.

Sekarang keduanya memakai `<dialog>` yang muncul di tengah layar,
dengan bentuk yang sama persis seperti popup di halaman chat —
markup-nya memakai kelas `.popup-dialog`, `.popup-actions`, dan
`.popup-button` dari `style.css`, bukan gaya baru sendiri, supaya
kedua halaman tidak berbeda tampilan.

`<dialog>` dipilih daripada menyusun div sendiri karena latar
gelap, kunci fokus, dan tombol Esc datang dari browser.
`method="dialog"` pada form di dalamnya membuat kedua tombol
menutup sendiri dan mengisi `returnValue`, jadi tidak perlu
pemasangan listener per tombol. **Batal** sengaja ditaruh lebih
dulu di markup: itu membuatnya jadi tombol yang menerima fokus
dan yang terpicu saat Enter ditekan — pilihan yang aman untuk
tindakan yang menghapus.

Isi pesannya menyebut akibat yang sebenarnya, dan keduanya
berbeda:

| Yang dihapus | Berkasnya |
| --- | --- |
| Job | tetap ada — `delete_job()` hanya menghapus baris di database, folder outputnya tidak disentuh |
| Template | ikut terhapus — `delete_template()` memanggil `shutil.rmtree()` pada folder templatenya |

Nama job atau template yang dimaksud dibaca dari kartunya dan
disebut di dalam pesan, supaya jelas kartu mana yang akan hilang
kalau ada beberapa yang mirip.

Browser tanpa `showModal` jatuh kembali ke `confirm()` biasa.
Tampilannya kembali seperti dulu, tapi itu lebih baik daripada
tombol hapus yang jalan tanpa bertanya sama sekali.

Di halaman chat masih ada dua `alert()` yang lolos saat popupnya
dibuat — pesan gagal pin chat dan gagal membuka chat. Keduanya
sekarang ikut memakai `showPopup()`.

### Tanpa API key: mode manual

Kalau belum punya API key SERP, salin sendiri URL hasil pencarian
Google ke `database/serp_manual.json`:

```json
{
  "slot gacor": [
    "https://situs-a.com/halaman",
    "https://situs-b.com/halaman"
  ]
}
```

Lalu:

```powershell
python neiiu.py "slot gacor" --provider manual
```

---

## Hasil

Setiap run membuat folder `output/<slug>-<timestamp>/`:

| File | Isi |
| --- | --- |
| `index.html` | Landing page kanonik, CSS sudah inline |
| `amp/index.html` | Versi AMP, canonical menunjuk ke `index.html` |
| `sitemap.xml` | Sitemap untuk kedua URL |
| `ANALISIS.md` | Penjelasan kenapa rank 1-10 bisa naik, plus target metrik |
| `report.json` | Seluruh data mentah: SERP, hasil crawl per halaman, blueprint, insight, template, rencana konten, hasil validasi |

Exit code: `0` sukses, `2` halaman jadi tapi AMP belum valid,
`1` gagal.

---

## Apa Yang Diambil dari Kompetitor

Yang diambil hanya **struktur dan gaya visual**:

- urutan dan tipe section (hero, list, tabel, langkah, FAQ, CTA)
- palet warna, font, dan radius, dibaca dari CSS mereka
- tipe schema yang mereka pakai
- pola panjang title dan meta
- tema heading yang berulang di banyak domain

Yang **tidak** diambil: teks, HTML, dan CSS mereka. Seluruh isi
halaman baru ditulis ulang oleh content planner.

Selain soal hak cipta, ini juga keharusan teknis: CSS bundle situs
besar hampir selalu jauh melewati batas 75KB milik AMP, jadi
menyalinnya akan langsung membuat halaman AMP invalid. CSS di sini
digenerate ulang dari design token dan hasilnya sekitar 3.5KB.

### Analisis SERP sebagai bahan kata title dan deskripsi

Inilah gunanya seluruh crawl di awal run. Hasilnya tidak berhenti
sebagai laporan: sebelum satu huruf pun ditulis, brief menerima satu
bagian bernama **Bahan Kata Untuk Title Dan Deskripsi**, berisi

| isinya | dari mana |
| --- | --- |
| title halaman yang sedang ngerank | `pages[].title`, 6 teratas |
| deskripsi yang mereka pasang | `pages[].meta_description`, 4 terpanjang |
| yang juga dicari orang | `blueprint.related_searches` |
| kata yang muncul di banyak halaman | `blueprint.common_entities` |

Halaman yang gagal di-crawl, yang isinya tidak terbaca, dan yang
berdiri di domain bajakan **tidak** ikut. Ketiganya ngerank karena hal
yang tidak ada hubungannya dengan pilihan katanya — domain curian,
cloaking, atau kebetulan — jadi menirunya berarti meniru sesuatu yang
bukan penyebabnya.

Yang diambil kata dan frasanya, bukan kalimatnya; aturan di brief
menyebut perbedaan itu dengan tegas, dan aturan lama tentang "jangan
menyalin data SERP" diperjelas jadi *kosakatanya dipakai, kalimatnya
tidak*.

Angka median panjang title kompetitor ikut dikirim, tapi sebagai
**peluang**, bukan patokan. Menuliskannya apa adanya — "panjang yang
lazim: 54 karakter" — membuat satu-satunya angka konkret di bagian itu
justru membantah jatah yang diminta, dan model memilih angka yang
dilihatnya.

### Panjang title dan meta description

| slot | rentang | dulu |
| --- | --- | --- |
| title | 50–70 karakter | maksimal 60, tanpa lantai |
| meta description | 160–200 karakter | 140–160 |

Rentang title sempat 65–80, lalu diturunkan atas permintaan pengguna
supaya judulnya tidak kepanjangan. Yang penting bukan angkanya
melainkan bahwa **ada lantainya** — tanpa itu model selalu memilih
yang aman. Rentang yang sekarang juga duduk di sekitar titik potong
tampilan Google (~580 piksel, kira-kira 60 karakter), jadi sebagian
besar judul terbaca utuh di layar.

Efek sampingnya bagus: 85 dari 116 contoh title milik pengguna di
`knowledge/gaya_title.txt` masuk rentang 50–70, jadi contohnya
sekarang disaring panjangnya seperti contoh deskripsi. Sebelumnya
tidak bisa — lantai 65 sementara contoh terpanjang 61 karakter berarti
menyaringnya mengirim daftar kosong, sehingga keterangan di atas
contoh terpaksa berbunyi "panjangnya JANGAN ditiru". Sekarang
contohnya mengajarkan nada dan panjang sekaligus.

Angkanya ada di satu tempat, `HEAD_FLOOR` dan `HEAD_BUDGET` di
`generators/template_slots.py`, lalu dipakai ulang lewat `ai/schemas.py`
oleh jalur template maupun jalur halaman-dari-nol. Sebelumnya tiap
jalur punya angkanya sendiri dan angkanya tidak sama: title dipatok 70
di satu tempat, 60 di tempat lain, lalu dipotong lagi jadi 62 waktu
nama brand ditambal.

**Lantainya ditegakkan grammar, bukan prompt.** Diminta lewat kalimat
saja, model lokal selalu memilih yang aman — terukur di mesin ini,
prompt yang cuma bilang "maksimal karakter sekian" dijawab dengan 52
karakter. Dengan `minLength` di JSON Schema, jawaban yang sama jadi 67
karakter: grammar menahan tanda kutip penutup sampai jatahnya
terpenuhi, dan model meneruskan kalimatnya alih-alih berhenti.

Ini kebalikan dari cara plafon ditegakkan. Teks yang kepanjangan masih
bisa diperbaiki belakangan — dipotong di batas kalimat, di tempat yang
tahu di mana kata berakhir — jadi plafon di grammar sengaja
dilonggarkan 30% supaya bukan dia yang pertama kena. Teks yang
kependekan tidak bisa diperbaiki oleh siapa pun. Tidak ada di Python
ini yang sanggup menyambung title 41 karakter jadi 68 karakter yang
masih berbunyi seperti kalimat manusia.

Kelonggaran plafon itu sempat dicabut untuk peran yang punya lantai,
dengan alasan yang kedengaran masuk akal: kalau lantai dan plafon
dua-duanya dipatok, model menulis di dalam rentangnya dan tidak ada
yang perlu dipotong. Yang terjadi justru sebaliknya, dan terbaca di
halaman jadi — title terbit sebagai

> TIMAH33 menyediakan slot gacor dengan RTP live dan deposit QRIS
> instan untuk **sel**

Grammar menutup stringnya persis di karakter ke-80, di tengah kata
"seluruh", dan tidak ada satu tahap pun sesudahnya yang bisa
mengembalikan huruf yang hilang. **Lantai membuat model menulis sampai
penuh, dan menulis sampai penuh membuat tabrakan dengan plafon jadi
keadaan biasa, bukan kekecualian** — jadi kelonggarannya justru lebih
dibutuhkan di peran yang punya lantai, bukan kurang.

Konsekuensinya diketahui dan diterima: Google memotong **tampilan**
title di sekitar 580 piksel (kira-kira 60 karakter) dan deskripsi di
sekitar 155 karakter di layar ponsel. Yang lewat batas itu tetap
terbaca mesin pencari dan tetap dihitung relevansinya — yang hilang
cuma ekornya di layar. Karena itu brief mewajibkan bagian terpenting
ditulis di depan.

Dua hal ikut menyesuaikan supaya tidak saling membantah:

- `knowledge/gaya_title_deskripsi.txt` disaring ke rentang 160–200
  sebelum dikirim sebagai contoh. Dari 120 baris, 22 di bawah lantai
  dan 32 di atas plafon; 66 yang tersisa masih delapan kali lebih
  banyak daripada yang dikirim per run.
- `knowledge/gaya_title.txt` **tidak** disaring, karena seluruh 116
  contohnya di bawah lantai baru (median 52, terpanjang 61). Contohnya
  tetap dikirim untuk nadanya, dan keterangan di atasnya sekarang
  menyebutkan bahwa panjangnya justru yang tidak ditiru.
- Meta description masuk `SENTENCE_ROLES`, dan `trim_to_sentence`
  menerima lantai. Di 160 karakter sebuah deskripsi muat satu kalimat
  dan potongan di batas kata praktis tidak kelihatan; di 200 ia muat
  dua sampai tiga, dan mundur ke titik terakhir bisa jatuh ke 151 —
  rapi, tapi di bawah lantai yang jadi alasan teks itu ditulis
  sepanjang itu.

---

## Deteksi Domain Bajakan

Di keyword yang dikuasai spam, halaman pertama Google sering diisi
domain institusi yang dibobol — kampus, kementerian, jurnal,
yayasan. Halaman itu melakukan **cloaking**: pengunjung biasa
dilayani halaman asli milik institusinya, sedangkan Googlebot
dilayani halaman spam yang kemudian diindeks dan ngerank.

Tanpa penanganan, ini merusak pipeline dari dua arah:

1. Crawler dengan User-Agent biasa membaca halaman institusinya,
   bukan halaman yang benar-benar ngerank.
2. Halaman itu ngerank lewat otoritas domain curian, bukan lewat
   struktur halamannya. Menirunya tidak ada gunanya.

`analyzer/cloak_detector.py` mengambil setiap halaman **dua kali**,
sebagai Chrome dan sebagai Googlebot, lalu membandingkannya.

Sinyal yang dijumlahkan jadi skor keyakinan 0–100:

| Sinyal | Bobot |
| --- | --- |
| Isi berbeda antara pengunjung dan Googlebot | +50 |
| Keyword hanya muncul di versi Googlebot | +25 |
| Domain institusi (`.go.id`, `.ac.id`, `.edu`, `.gov`) | +35 |
| Subdomain memuat keyword, induknya tidak menyebutnya | +45 |
| Seluruh domain induk ikut dipenuhi keyword | +45 |
| Domain institusi dengan density ≥ 2.5% | +25 |
| Density > 6% | +15 |

Di atas `HIJACK_MIN_CONFIDENCE` (default 60), halaman dikeluarkan
dari perhitungan target dan tidak pernah dipilih jadi acuan template.

**Sinyal domain saja tidak pernah cukup untuk memvonis.** Tanpa
bukti dari isi halamannya, skor ditahan di bawah ambang. Situs
kampus atau pemerintah yang memang membahas topiknya tidak akan
tervonis hanya karena alamat domainnya.

Untuk memisahkan subdomain parasit dari yang sah, halaman depan
domain induknya ikut diperiksa. `slot.gasrestaurant.com` dan
`slot.pragmaticplay.com` polanya identik kalau dilihat dari
namanya saja; bedanya baru kelihatan di domain induknya.

### Batasnya

Menyamar sebagai Googlebot hanya menembus cloaking yang memeriksa
User-Agent saja. Cloaking yang canggih ikut memverifikasi rentang
IP Google, dan terhadap halaman seperti itu crawler ini tetap
dilayani halaman kosong atau halaman aslinya.

Karena itu ada saringan kedua: halaman yang terbaca di bawah 150
kata, atau yang tidak memuat satu pun kata dari keywordnya, ditandai
**tidak terbaca** dan ikut dikeluarkan. Tanpa saringan ini, halaman
peringkat satu yang terbaca dua kata akan ikut menghitung median
dan menghasilkan target yang tidak masuk akal.

Kalau tidak ada satu pun halaman yang layak, NEIIU tetap
menghasilkan angka tapi menandainya dengan peringatan keras. Pada
kondisi itu, tentukan acuan sendiri lewat `--reference` atau isi
daftar kompetitor asli lewat provider manual.

Deteksi bisa dimatikan lewat `CLOAK_CHECK=false` di `.env`. Itu
memangkas jumlah request jadi separuh, tapi blueprintnya kembali
rawan tersusun dari konten yang salah.

## Target Metrik

Halaman baru tidak dinilai dengan patokan umum, tapi dengan
blueprint yang diambil dari SERP keyword itu sendiri:

- jumlah kata mengejar **median top 5**, bukan rata-rata semua
- jumlah H2 mengikuti median halaman pertama
- FAQ dipasang kalau kompetitor memakainya
- schema mengikuti tipe yang paling banyak dipakai

Alasannya, standar "cukup panjang" untuk satu keyword bisa jauh
berbeda dari keyword lain.

---

## Validasi

`generators/amp_validator.py` memeriksa aturan AMP yang fatal:

- doctype, atribut `amp`, urutan `<meta charset>`
- runtime `v0.js`, viewport, canonical, boilerplate
- satu `<style amp-custom>`, ukuran di bawah 75KB
- tanpa `!important`, `@import`, `-moz-binding`, `behavior`
- tanpa `<img>`, `<iframe>`, `<video>`, `<form>` mentah
- tanpa script kustom, style inline, dan handler `onclick`

Ini menangkap semua kesalahan yang bisa muncul dari generator
sendiri, tapi **bukan pengganti validator resmi**. Sebelum
benar-benar diunggah, cek sekali di
<https://validator.ampproject.org>.

### Pengaman otomatis

Model kecil sering menulis parafrase yang enak dibaca tapi
kehilangan keywordnya — misalnya menulis "Pelajari Python" untuk
keyword "belajar python". `normalize_plan()` menambalnya sendiri:
kalau keyword tidak ada di title, H1, atau meta, keyword dipasang
di depan dan teksnya dipotong di batas kata supaya tetap muat.
Fungsi ini idempoten, jadi aman dijalankan berulang.

Yang **tidak** bisa ditambal otomatis adalah panjang konten. Kalau
model menulis lebih pendek dari target, itu dilaporkan apa adanya
oleh validator dan perlu ditangani manual (lihat bagian Catatan
Performa).

Panjang title dan meta description juga dilaporkan, bukan ditambal.
Lantainya sudah ditegakkan grammar waktu jawabannya ditulis, jadi
sampai ke tahap ini hampir selalu terpenuhi; kalau ternyata tidak,
yang tercatat di log job berbunyi `title cuma 41 karakter, di bawah
lantai 50`. Menambalnya di Python berarti mengarang kalimat.

`generators/seo_validator.py` menilai halaman terhadap blueprint:
panjang title dan meta, posisi keyword, jumlah H1 dan H2, panjang
konten, keyword density, canonical, `rel=amphtml`, dan structured
data.

---

## Kalau AI Mati

Langkah analisis ranking punya fallback: kalau Ollama tidak bisa
dihubungi, insight disusun langsung dari data crawl dan pipeline
tetap jalan. Yang ditandai `status: fallback` di `report.json`.

Langkah penyusunan konten tidak punya fallback, karena menulis
prosa memang butuh model. Kalau gagal di sini, analisis SERP tetap
tersimpan dan `ANALISIS.md` tetap ditulis.

---

## Batas Waktu AI

Jawaban AI diambil secara **streaming**, dan `AI_STALL_TIMEOUT_SECONDS`
(default 180 detik) adalah **jeda maksimal antar token**, bukan
batas waktu total.

Ini penting. Sebelumnya batasnya berupa total 900 detik, dan
langkah penyusunan konten yang meminta 5000 token di CPU dengan
kecepatan ~3 token/detik butuh sekitar 28 menit. Hasilnya selalu:

```
HTTPConnectionPool(host='localhost', port=11434):
Read timed out. (read timeout=900)
```

Batas total berapa pun akan salah untuk sebagian mesin. Yang
benar-benar menandakan masalah adalah token yang berhenti mengalir,
dan itu yang sekarang diukur. Efek sampingnya, jumlah token yang
sudah ditulis ikut dilaporkan ke log job, jadi proses yang berjalan
puluhan menit tidak lagi terlihat menggantung.

## Membuat Ulang Halaman Dari Template Yang Sama

Dua run dengan keyword, brand, dan template yang sama dulu
menghasilkan halaman yang **sama huruf per huruf**. Terukur — dua
panggilan berturut-turut dengan prompt identik mengembalikan ulasan
yang persis sama dan judul yang cuma beda tanda hubung. Membuat ulang
halaman jadi tidak ada gunanya.

Sebabnya `temperature: 0`: model selalu mengambil kata yang paling
mungkin, jadi prompt yang sama pasti menghasilkan teks yang sama. Dua
hal diubah, dan keduanya perlu:

| | apa | kenapa perlu keduanya |
| --- | --- | --- |
| `AI_TEMPERATURE` | 0.6 (bisa diatur di `.env`) | mengubah pilihan katanya |
| `brand["variation"]` | penanda waktu per run | mengubah **contoh gaya** yang dikirim ke model |

Yang kedua penting karena `pick_style_examples()` memilih delapan
contoh dari `knowledge/gaya_title.txt` dan
`knowledge/gaya_title_deskripsi.txt` dengan benih yang diturunkan,
bukan diacak. Tanpa penanda run, setiap run membaca delapan contoh
yang sama persis — dan model yang membaca contoh yang sama cenderung
kembali ke kalimat yang sama, berapa pun suhunya.

Penandanya dititipkan di dict `brand` karena dict itu sudah sampai ke
setiap generator tanpa satu pun parameter tambahan, dan karena ia
dibuat **sekali per run**. Dua sifat itu yang dibutuhkan: beda antar
run, dan sama sepanjang satu run — kalau berubah di tengah, awalan
prompt ikut berubah, cache prompt Ollama batal, dan tiap giliran
membayar prefill dari nol.

Diukur pada dua run berurutan lewat jalur sungguhan, dihitung per
frasa tiga kata:

| | perbedaan |
| --- | --- |
| title | 0.73 |
| ulasan | 0.98 |

Suhu 0.9 sempat diuji juga dan tidak menambah perbedaan yang berarti
(0.69 dan 0.92) tapi menambah peluang model melantur. Bentuk JSON-nya
tidak ikut terancam berapa pun angkanya — yang menjaga strukturnya
grammar dari JSON Schema, bukan suhu.

### Contoh gaya disalin bulat-bulat

Berkas `knowledge/gaya_title.txt` dan `gaya_title_deskripsi.txt`
diperlihatkan ke model supaya ia tahu bentuk yang diminta — dan model
kecil menjawab bentuk yang diperlihatkan dengan cara yang paling
murah: menyalinnya. Terukur di job 41:

```
terbit : WAYANGPLAY # Slot Gacor dengan AI Predictor Maxwin & RTP Tertinggi
contoh : [ BRAND ]: Situs Slot Gacor dengan AI Predictor Maxwin & RTP Tertinggi
                                            ^ baris 114 knowledge/gaya_title.txt
```

Baris contoh itu sendiri, dengan nama situs ditukar. Tidak ada satu
pun penyaring yang keberatan — penyaring yang ada (`copies_sample`)
membandingkan jawaban dengan judul milik **template**, bukan dengan
berkas contohnya.

`style_copy_score()` menutup lubang itu. Ia menyusun ulang contoh yang
**dilihat model di run ini** — benihnya deterministik, jadi
argumennya harus persis sama dengan yang dipakai
`build_template_content_prompt`: keyword mentah, nama brand yang sudah
di-`strip()`, penanda run apa adanya — lalu membandingkan lewat irisan
frasa tiga kata, dengan nama situs dibuang dari kedua sisi (contoh
menulis `[ BRAND ]`, jawaban menulis nama sungguhannya).

| jawaban | skor | |
| --- | --- | --- |
| `WAYANGPLAY # Slot Gacor dengan AI Predictor Maxwin & RTP Tertinggi` | 2.86 | salinan penuh |
| `WAYANGPLAY \| Slot Gacor dengan AI Predictor Maxwin Terbaru` | 1.67 | salinan separuh |
| `WAYANGPLAY \| Putaran Malam Yang Saldonya Masuk Sebelum Bank Tutup` | 0.00 | ditulis baru |
| `WAYANGPLAY: Panduan Memilih Putaran Untuk Pemain Yang Baru Mulai` | 0.00 | ditulis baru |

Pemisahannya sangat lebar — salinan di 0,857 irisan mentah, yang
ditulis baru semuanya 0,000 — jadi `STYLE_COPY_LIMIT = 0.3` menangkap
salinan separuh tanpa mendekati jawaban yang jujur.

Judul sekarang punya **satu** putaran ulang untuk dua alasan
sekaligus: mengulang halaman sebelumnya, dan menyalin contoh gaya.
Keduanya dinyatakan sebagai kelipatan ambangnya masing-masing, jadi
1.0 berarti "tepat di batas" untuk alasan apa pun. Sebelum digabung,
judul yang kena dua-duanya membayar dua kali giliran model untuk satu
baris teks.

### Halaman kedua tidak boleh sama dengan yang pertama

Suhu 0.6 dan penanda run di atas membuat dua halaman **berbeda
kalimatnya**, tapi tidak membuatnya berbeda **isinya**. Keduanya
berangkat dari titik yang persis sama — keyword yang sama, kompetitor
yang sama, template yang sama — jadi sudut yang dipilih model
cenderung sudut yang sama, cuma dengan kata yang ditukar.

NEIIU sebenarnya sudah punya penolak kalimat kembar yang bagus, tapi
seluruhnya hidup di dalam **satu** run: begitu prosesnya selesai,
semua yang pernah ditulis hilang. Jadi yang ditambahkan bukan mesin
baru, melainkan **ingatannya**.

`database/neiiu_history_db.py` menyimpan teks yang sudah terbit,
lalu run berikutnya membacanya dan memakainya di tiga tempat:

| tempat | yang terjadi |
| --- | --- |
| `terpakai` di `generate_template_content()` | diisi duluan dengan teks halaman lama, jadi penolak kembar yang sudah ada langsung menolaknya — lubangnya ditambal mesin retry yang sama |
| judul | diadu dengan judul halaman lama, diminta ulang sampai `TITLE_REPEAT_RETRIES` kali |
| deskripsi | pembanding lamanya bertambah: judulnya sendiri **dan** deskripsi halaman lama |

Judul ditangani sendiri karena ia bukan salah satu dari sekian teks
melainkan **hulu** seluruh halaman — bagian "Sudut Pandang Halaman
Ini" menyuruh paragraf, heading, FAQ, dan ulasan melanjutkan sudut
yang dipilih di judul. Dua halaman yang judulnya sama akan sama
seluruhnya, berapa pun kalimat lain yang berhasil dibedakan.

Ambangnya lebih ketat dari ambang gema biasa, dan angkanya diukur
dari pasangan sungguhan:

| calon judul halaman ke-2 | skor | |
| --- | --- | --- |
| `Deposit QRIS Satu Detik Tanpa Potongan` | 2.00 | sama persis |
| `Setor QRIS Sedetik Tanpa Potongan Sama Sekali` | 0.83 | judul yang sama, kata ditukar |
| `Riwayat Transaksi Yang Bisa Dibuka Kapan Saja` | 0.28 | sudut lain |

Yang tengah persis yang dikeluhkan pengguna sebagai "sama saja", dan
ia lolos kalau ambangnya 1.0. Jadi `TITLE_REPEAT_LIMIT = 0.6` duduk
di ruang kosong antara 0.28 dan 0.83.

**Yang diingat** dibatasi 5 halaman terakhir dan 600 baris, dan cuma
peran yang memang harus berbeda — `nav_label` dan `label` tidak ikut,
karena "Beranda" memang harus sama di setiap halaman.

**Cakupannya** halaman dengan keyword yang sama **atau** template yang
sama, milik pengguna yang sama. Dua-duanya perlu: orang membuat
halaman kedua untuk keyword yang sama dengan brand berbeda, dan juga
memakai satu template untuk beberapa keyword.

Daftarnya juga dikirim ke model, di dalam `brief` — bukan di blok
permintaan. Isinya tetap sepanjang satu run, jadi cache prompt Ollama
tidak batal. Menghapus job ikut menghapus ingatannya, supaya halaman
yang sudah dibuang tidak diam-diam membatasi halaman berikutnya.

### Ekor menggantung di judul yang dipotong

Efek samping yang muncul begitu title punya lantai: model menulis
sampai penuh, melewati plafonnya, lalu dipotong di batas kata — dan
yang tersisa berakhir menggantung.

| | hasil |
| --- | --- |
| sebelum | `...Mainan Cepat Tanpa Ribet di Era` |
| | `...Game Berkualitas Tinggi dan Transaksi` |
| sesudah | `...Mainan Cepat Tanpa Ribet` |
| | `...Game Berkualitas Tinggi` |

`drop_dangling()` dulu hanya membuang kata sambung yang berdiri
sendirian di ujung. Sekarang ia juga membuang pasangan *kata depan +
satu kata* — tapi **hanya kalau teksnya memang baru dipotong**, dan
syarat itu yang membuat aturannya aman. Judul yang ditulis utuh dan
kebetulan berakhir `...Deposit Cepat dan Praktis` sama sekali tidak
disentuh, karena tidak ada yang dipotong darinya.

### Bentuk title: nama situs, satu tanda pisah, lalu janjinya

Permintaan pengguna, dan alasannya kelihatan begitu hasil generate
dijajarkan dengan contoh miliknya sendiri:

| | judul |
| --- | --- |
| punya pengguna | `[ BRAND ] \| Update Harian RTP Slot dengan Pola Gacor Terbaik` |
| yang terbit | `TIMAH33 menghadirkan slot gacor dengan sistem spin modern` |

Yang kedua bukan judul yang lebih jelek — ia bentuk yang lain sama
sekali. Nama situs melebur jadi subjek kalimat, jadi tidak ada satu
titik pun di mana mata pembaca bisa berhenti dan tahu ini situs apa.
Di hasil pencarian, tempat judul dibaca sambil lalu, itu yang
menentukan diklik atau tidak.

`enforce_title_shape()` di `generators/content_planner.py` menegakkan
tiga hal:

1. Nama situs dipindahkan ke depan. Kata sambung yang tadinya
   menempel padanya ikut dibuang — tanpa itu, *Rahasia Spin di
   TIMAH33 yang Membuka Peluang* berpindah jadi `TIMAH33 | Rahasia
   Spin di yang Membuka Peluang`.
2. Tanda pisah lepas di sisa judul dihapus, jadi cuma ada **satu**
   tanda pisah di seluruh title. Tanda hubung hanya dihitung kalau
   diapit spasi, supaya `anti-rungkad` tidak ikut terbelah.
3. Kata sambung yang menggantung di ujung dibuang **sebelum**
   panjangnya diperiksa, bukan cuma waktu judulnya kepanjangan.
   Judul yang sampai ke sini sering sudah dipotong sekali oleh
   `ensure_identity()`, dan potongan itu meninggalkan ekor seperti
   `... Setiap Hari Tanpa` yang muat di jatah — jadi tidak pernah
   kena pemotongan kedua.

Tanda pisahnya dipilih `title_separator()` dari nama brand dan
keyword, bukan diacak: dua halaman untuk brand yang sama memakai
tanda yang sama, dan mengulang keyword yang sama tidak menghasilkan
judul berbeda bentuk. Isi dan takaran daftarnya diambil dari 120
contoh title milik pengguna di `knowledge/gaya_title.txt` — titik dua
33 kali, garis tegak 27 kali, sisanya tersebar tipis — ditambah emoji,
yang di berkas aslinya dipakai tapi bytenya hilang waktu ditempel ke
chat.

Ditegakkan di Python, bukan diserahkan ke prompt. Aturan bentuk di
prompt sudah dicoba dan hasilnya diikuti kadang-kadang saja; bentuk
yang cuma benar sebagian sama saja dengan tidak punya bentuk.
Aturannya tetap ditulis juga di prompt, tapi tugasnya cuma satu:
menyuruh model **tidak** menulis tanda pisah sendiri, supaya yang
dipasang Python tidak berdiri di sebelah tanda pisah karangan model.

H1 sengaja tidak ikut. H1 dibaca sebagai kalimat pembuka di dalam
halaman, bukan sebagai baris di hasil pencarian, dan nama situs
berpemisah di situ terbaca seperti label.

## Mengganti Logo, Favicon, dan Poster

Alamat gambar diisi di formulir, dan NEIIU menukarnya di template.
Ketiganya opsional; yang dikosongkan berarti gambar template dipakai
apa adanya.

| isian | yang diganti |
| --- | --- |
| logo | gambar yang `class`, `id`, `alt`, atau nama berkasnya menyebut *logo*; kalau tidak ada satu pun, gambar pertama di dalam `<header>` atau `<nav>` |
| favicon | `<link rel="icon">`, `shortcut icon`, `apple-touch-icon`, `mask-icon`, dan `<meta name="msapplication-TileImage">` |
| poster | `og:image`, `twitter:image`, atribut `poster` milik `<video>`, lalu **seluruh gambar isi yang tersisa** |

Penanda `data-neiiu="logo"`, `data-neiiu="favicon"`, dan
`data-neiiu="poster"` menang atas semua tebakan di bawah, untuk
template yang menamai gambarnya dengan cara yang tidak bisa ditebak
siapa pun.

### Kenapa poster memakai "semua kecuali", bukan daftar kata

Tebakan berdasarkan penamaan sudah dicoba dan gagal. Terukur di job
39, pada template sungguhan milik pengguna:

| | hasil |
| --- | --- |
| terganti | 74 thumbnail menu 250 piksel, karena class Tailwind `object-cover` menempel di semuanya |
| lolos | seluruh foto utama selebar 2000 piksel, yang tidak punya satu class pun |

Persis kebalikan dari yang diminta. Sebabnya template modern menamai
gambarnya dengan **ukuran**, bukan dengan fungsi — `absolute inset-0
object-cover`, `w-full h-12` — dan tidak ada kata *poster*, *hero*,
atau *banner* di mana pun.

Jadi aturannya dibalik: semua gambar isi diganti, **kecuali** yang
punya alasan untuk tidak.

| alasan tidak diganti | contoh |
| --- | --- |
| sudah kebagian peran lain | logo, favicon |
| berukuran ikon | `width`/`height` ≤ 64, atau class `w-6`, `h-12`, `size-5` (skala Tailwind, 16 = 64px) |
| berkas SVG | ikon panah, bendera bahasa |
| namanya menyebut ikon | `nav-menu-icons_1.jpg`, `payment-*`, `avatar-*` |
| bertanda `data-neiiu-skip` | termasuk kalau penandanya di elemen induk |
| di dalam blok iklan sungguhan | lihat di bawah |

Setelah dibalik, template yang sama: **114** gambar terganti di
landing (dari 74), dan berkas AMP-nya naik dari 1 jadi 2.

`<video src>` dan `<source>` di dalam `<video>` sengaja tidak pernah
ikut — isinya berkas video, dan menulisi alamat JPG ke situ
mematikan videonya. `<source>` hanya diganti kalau induknya
`<picture>`.

`Organization.logo` dan `image` di JSON-LD ikut berganti. Tanpa itu,
rich result di Google menampilkan logo pemilik template sebelumnya
meskipun logo di header sudah ditukar — karena yang dibaca Google di
situ JSON-LD, bukan `<img>` di badan halaman.

### Kenapa jalurnya dipisah dari pengisi teks

Nilai `src` dan `href` adalah **struktur**, bukan isi.
`template_guard` menolak hasil isian yang mengubahnya, dan penolakan
itu yang selama ini menjaga gambar template tidak hilang gara-gara
satu pemetaan slot yang keliru. Jadi:

- Pemindai mencatat alamat gambar di daftar **terpisah**
  (`scanned["assets"]`), tidak pernah di `slots`. Apa pun yang masuk
  `slots` melewati `classify()` lalu bisa kebagian kalimat dari AI,
  dan kalimat yang ditulis ke dalam `src` berarti gambarnya hilang.
- Setiap penukaran didaftarkan sebagai izin bernama ke
  `verify(..., asset_swaps=[...])`: elemen ke berapa, atribut apa,
  jadi nilai apa. Izinnya diterapkan ke sidik template **asli**, jadi
  yang dibandingkan tetap sidik yang seharusnya terbit — bukan
  pemeriksaan yang dilonggarkan. `src` yang hilang karena bug tetap
  ketahuan.
- Gambar diganti **sebelum** lapis gema dan lapis nama brand. Alamat
  gambar sering memuat nama brand lama (`assets/img/logo-osb99.png`),
  dan lapis nama brand menyentuh setiap slot yang belum kebagian isi.
  Kalau urutannya dibalik, dua lapis menulis ke rentang yang sama dan
  seluruh pengisian dibatalkan karena bertumpang tindih.

### Yang sengaja tidak disentuh

- **Isi blok iklan sungguhan** — `adsbygoogle`, `googlesyndication`,
  `data-ad-`, `adslot`, `sponsor`, `propeller`, `adsterra`, dan tag
  `<ins>`/`<amp-ad>`. Janji itu lebih tua daripada fitur ini; yang
  bisa dilakukan cuma menghitungnya dan menyebutkannya di log.

  Kata **`banner`** sendirian tidak lagi menghalangi. Ia ada di
  `AD_MARKERS` karena blok iklan sungguhan memang sering menamai
  dirinya begitu, tapi template sama seringnya memakainya untuk
  gambar sampulnya sendiri — dan akibatnya terukur di job 39:
  `<amp-img class="banner-amp">`, satu-satunya gambar besar di berkas
  AMP, tidak pernah ikut berganti. Pemindai sekarang menyimpan
  **alasan** tiap blok dihitung iklan (`ad_reasons`), dan
  `SOFT_AD_MARKERS` di `template_assets.py` memaafkan yang alasannya
  cuma kata itu. Kelonggarannya berlaku **hanya untuk alamat
  gambar** — teks di dalam blok yang sama tetap tidak disentuh sama
  sekali.
- **Elemen bertanda `data-neiiu-skip`,** termasuk kalau penandanya
  ada di elemen induknya. Bentuk yang lazim adalah daftar logo mitra:
  logo bank di situ bukan logo situsnya.
- **Atribut yang ditulis tanpa tanda kutip.** Alamat yang memuat
  spasi akan terbaca sebagai atribut tambahan dan mengubah struktur
  tagnya.

Alamat yang boleh dipasang cuma `https://`, `http://`, atau alamat di
dalam situs sendiri yang diawali `/`. Diperiksa dua kali — di lapisan
web supaya salah ketik ketahuan selagi formulirnya masih terbuka, dan
di pipeline supaya tidak ada jalur lain yang bisa melewatinya.

## Catatan Performa

Model 4B di CPU butuh beberapa menit per langkah AI. Kalau terlalu
lama:

- turunkan `--crawl` (misal `--crawl 5`) supaya prompt lebih pendek
- turunkan `AI_MAX_TOKENS_INSIGHT` dan `AI_MAX_TOKENS_PLAN`
- pakai model yang lebih besar di GPU kalau tersedia

Jangan menurunkan `AI_CONTEXT_LENGTH` untuk mengejar kecepatan.
Kalau prompt tidak muat, Ollama memotong bagian awalnya tanpa
error apa pun, dan hasil analisisnya jadi ngawur tanpa ketahuan.

---

## Sebelum Mengunggah

1. Ganti `SITE_BASE_URL` di `.env` ke domain asli, lalu jalankan
   ulang. Canonical, sitemap, dan JSON-LD ikut memakai nilai ini.
2. Cek `amp/index.html` di validator resmi AMP.
3. Baca ulang isi halamannya. Konten hasil model tetap perlu
   diperiksa manusia sebelum terbit — cek klaim yang salah,
   pengulangan, dan hal yang tidak sesuai aturan platform atau
   aturan yang berlaku di tempat halaman itu diterbitkan.
4. Daftarkan `sitemap.xml` di Google Search Console.
