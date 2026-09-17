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
| `SITE_BASE_URL` | **Tidak dipakai lagi oleh generator.** Sampai 30 Agustus 2026 ia jadi nilai cadangan kolom domain di `build_brand()`, dan bawaannya `https://example.com` — jadi selama kolomnya dikosongkan, alamat situs contoh itu yang dipakai. Sekarang kosong berarti kosong. Alamat halaman diisi lewat kolom opsional di formulir; yang dikosongkan berarti alamat di template dibiarkan apa adanya |
| `SITE_CTA_URL` | Tujuan semua tombol login, daftar, bilah mengambang, dan popup. Kosong berarti menunjuk beranda sendiri |
| `SITE_LICENSE` | Nama badan pengawas brand, mis. `PAGCOR`. Diisi berarti halaman menyebutnya dengan nama itu; kosong berarti halaman tetap bilang "resmi dan berlisensi" tanpa menyebut nama. Nomor lisensi tidak pernah ditulis |
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
python neiiu.py "slot gacor" --brand ABECE  --template landing.html
python neiiu.py "slot gacor" --brand DEFAFA --template landing.html
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

Kalau model lupa memasukkan brand ke title, bentuk judulnya
ditegakkan `enforce_title_shape()` di `generators/content_planner.py`:
nama situs di depan, satu tanda pisah, lalu janjinya.

```
ABECE | Slot Gacor dengan Pilihan Permainan yang Lengkap
```

Yang dilarang dikarang bukan seluruh klaim tentang brand, melainkan
ANGKA yang tidak dipunyai pipeline ini - jumlah member, RTP, tahun
berdiri, nomor lisensi - dan janji bahwa PEMBACANYA akan menang.
Brandnya sendiri boleh berbicara percaya diri tentang kesanggupannya;
lihat `brand_confidence_rules()` di `ai/neiiu_prompts.py`.

## Template Wajib

Halaman ditulis DI ATAS template, dan hanya di situ. Struktur,
iklan, skrip, tautan, gambar, kelas, dan ID template dipertahankan
byte demi byte; yang diganti cuma teksnya.

Karena itu `--template` (atau kolom Template di halaman web) wajib
diisi untuk membuat halaman. Yang bisa jalan tanpa template cuma
`--analyze-only`, dan mode itu memang tidak menerbitkan satu berkas
pun.

Sampai 19 Agustus 2026 template yang dikosongkan membuat pipeline
merakit halamannya sendiri dari pustaka blok - layout, warna,
tombol, popup, dan urutan bagiannya ditentukan program. Jalur itu
sudah dibuang seluruhnya beserta modulnya (`landing_generator.py`,
`theme.py`, `inspiration.py`), karena halaman yang keluar dari sana
tidak pernah bisa dijanjikan "strukturnya persis template pilihanmu"
- di situ tidak ada template sama sekali.

Berkas AMP tetap boleh dikosongkan. Kalau template AMP tidak
diunggah, versi AMP dibuat dari ISI YANG SAMA dengan landingnya,
jadi title, deskripsi, dan H1 kedua berkas tetap sama.

## Cara Pakai

```powershell
# paling dasar - template landing wajib
python neiiu.py "slot gacor" --template landing.html

# dengan brand sendiri dan template AMP-nya sekalian
python neiiu.py "slot gacor" `
  --brand ABECE --base-url https://abece.com `
  --template landing.html --template-amp amp.html

# template yang di dalamnya masih tertulis brand lama
python neiiu.py "slot gacor" `
  --brand ABECE --template landing.html --template-brand OSB99

# hanya analisis SERP, tanpa membuat halaman (tidak butuh template)
python neiiu.py "slot gacor" --analyze-only

# paksa ambil SERP baru, abaikan cache
python neiiu.py "slot online" --template landing.html --no-cache

# batasi jumlah halaman yang di-crawl biar cepat
python neiiu.py "slot gacor" --template landing.html --crawl 5

# brief kreatif: jenis halaman, nada, pembaca, keyword pendukung
python neiiu.py "slot gacor" `
  --brand ABECE --template landing.html `
  --page-purpose article --tone informatif `
  --audience "pemain baru yang belum pernah daftar" `
  --secondary-keyword "slot online" `
  --secondary-keyword "deposit qris"
```

---

## Alur Formulir Generate

Dirombak 30 Agustus 2026. Urutan kolomnya mengikuti urutan orang
memikirkan halamannya, dan yang jarang dipakai dilipat — bukan supaya
rapi, melainkan supaya enam kolom yang dipakai setiap hari tidak
sama sulitnya dicari dengan yang setahun sekali.

**Alur utama:**

| Kolom | Wajib | Keterangan |
|---|---|---|
| Brand | tidak | Nama situs baru. Kosong berarti `SITE_NAME` dari `.env` |
| **Niche** | **ya** | Topik halaman, ditulis seperti yang diketik orang di Google |
| Template | ya | Struktur halaman datang dari sini, dan hanya dari sini |
| Halaman yang dibuat | — | Keterangan mati: Landing Page + AMP. Bukan pilihan |
| Brand lama di template | tidak | Nama pemilik template sebelumnya, untuk dicari lalu diganti |
| Panjang artikel | tidak | Melebarkan jatah paragraf yang sudah ada; tidak menambah paragraf |

**Niche menggantikan kolom "Target Keyword".** Yang berganti namanya
di layar saja: nilainya tetap masuk kolom `keyword` yang dipakai
seluruh pipeline — riset SERP, title, H1, slug. `NeiiuJobRequest`
menerima `niche` maupun `keyword`, dan `niche` menang kalau keduanya
dikirim, supaya skrip lama tidak patah.

Jangan tertukar dengan `detect_niche()` di `ai/niche.py`. Itu hal
lain: ia menebak **bidang** halaman (`gambling` atau `generic`) dari
teks yang sama, dan tetap bekerja seperti sebelumnya.

### Domain, tautan, dan gambar — semuanya opsional

Blok terlipat berisi enam kolom. **Yang dikosongkan berarti alamat
yang sudah ada di template dipakai apa adanya**, dan itu satu-satunya
bawaannya — tidak ada nilai cadangan di jalur ini sama sekali.

| Kolom | Yang ditulisinya |
|---|---|
| Domain canonical | `<link rel="canonical">` di kedua berkas. Asal domainnya juga jadi pengenal situs di structured data. Berkas AMP menunjuk ke landing, bukan ke dirinya sendiri |
| Domain amphtml | `<link rel="amphtml">` di berkas **landing** saja |
| Tujuan tombol LOGIN & DAFTAR | `href` anchor yang tulisannya menyebut login, masuk, daftar, register, buat akun, atau padanan Thai-nya |
| Link logo | Gambar yang menamai dirinya logo, atau gambar pertama di `<header>`/`<nav>` |
| Link icon | Semua `rel="icon"`, `shortcut icon`, `apple-touch-icon`, `mask-icon` |
| Link gambar poster/banner | `og:image`, `twitter:image`, `poster` milik video, lalu sisa gambar isi |

Kalau template belum punya `rel="canonical"` atau `rel="amphtml"`,
satu baris ditambahkan tepat sebelum `</head>` — dan penambahan itu
didaftarkan ke pemeriksa struktur lewat `allow_added_tags`, bukan
diloloskan diam-diam.

**Yang tidak pernah disentuh** meski tulisannya cocok: tautan
dalam-halaman (`#daftar`), `javascript:`, `mailto:`, `tel:`, dan
seluruh isi blok iklan. Tombol yang tulisannya tidak umum bisa
ditandai sendiri di template dengan `data-neiiu="daftar"`.

Jalurnya `generators/page_links.py`: splice byte di rentang nilai
atribut lewat `scanned["assets"]`, sama seperti penukaran gambar —
bukan urai lalu serialisasi ulang. Sebelum ini, kolom "Tujuan tombol"
hanya berpengaruh pada berkas AMP yang **dirakit NEIIU sendiri**;
untuk template yang AMP-nya diunggah, kolomnya terisi tapi tidak satu
tombol pun berpindah.

---

## Brief Kreatif

Empat isian yang mengubah **cara isinya ditulis**, bukan bentuk
templatenya.

**Sekarang hanya di CLI.** Keempatnya dibuang dari formulir web pada
30 Agustus 2026 atas permintaan pengguna, bersama kolom "URL halaman
acuan". Dukungan sisi servernya sengaja TIDAK ikut dicabut: bidangnya
masih ada di `NeiiuJobRequest`, di database, dan di
`build_creative_brief()`, semuanya berbawaan kosong. Jadi CLI,
`/api/neiiu/compose`, dan skrip apa pun yang sudah memakainya tetap
berjalan persis seperti dulu.

| Isian | CLI | Isinya |
|---|---|---|
| Jenis halaman | `--page-purpose` | `landing-page`, `amp`, `homepage`, `article`, `seo-page`, `brand-page` |
| Nada tulisan | `--tone` | `natural`, `santai`, `profesional`, `persuasif`, `informatif` |
| Pembaca yang dituju | `--audience` | teks bebas |
| Keyword pendukung | `--secondary-keyword` | boleh diulang, paling banyak 8 |

**Semuanya opsional, dan yang dikosongkan tidak mengubah apa pun.**
Itu bukan basa-basi: job tanpa satu pun isian ini menghasilkan prompt
yang sama **byte per byte** dengan prompt sebelum brief ada, jadi
seluruh penyetelan yang sudah terukur tidak ikut bergeser. Aturannya
ada di `ai/brief.py`.

Dua hal yang perlu diketahui soal keyword pendukung:

- Tiap keyword dipakai **sekali saja** di seluruh halaman, bukan
  diulang-ulang. Model kecil membaca daftar keyword sebagai daftar
  yang harus dihabiskan, dan cara termurah menghabiskannya adalah
  menjejerkan semuanya di satu paragraf.
- Tidak dipakai di `title`. Title cuma punya 50-70 karakter dan itu
  sudah habis dibagi nama brand, tanda pisah, dan janjinya. Di
  `meta_description` boleh satu.

### Nada per bahasa

Aturan nada dan aturan bunyi tulisan ditulis **dalam bahasa
sasarannya**, bukan diterjemahkan saat dikirim
(`ai/language_rules.py`).

Sebelumnya satu daftar aturan berbahasa Indonesia dikirim ke semua
zona, termasuk zona Thailand — lengkap dengan barisnya yang menyuruh
model memakai kata "nggak", "udah", dan "bikin". Perintah memakai
bahasa gaul Indonesia dikirim bersama perintah menulis dalam bahasa
Thai, dan yang menang tarik-menarik itu adalah bentuk kalimat
Indonesia. Itu salah satu sebab halaman zona Thailand terbaca seperti
hasil terjemahan.

Karena alasan yang sama, contoh gaya di `knowledge/gaya_title.txt` dan
`gaya_title_deskripsi.txt` **tidak dikirim** untuk zona yang bahasanya
bukan bahasa berkas itu. Keduanya dikirim sebagai cetakan bentuk
("tiru susunan kalimatnya"), dan untuk halaman Thai perintah itu
berarti: susunlah kalimat Thai mengikuti susunan kalimat Indonesia.
Yang tetap bekerja untuk zona lain — bentuk title, rentang panjang,
dan bank kata dari SERP, yang isinya title Thai yang benar-benar
sedang ngerank.

---

## Mutu Title dan Meta Description

Dua teks ini ditangani terpisah dari isi halaman yang lain, dan
alasannya urutan prioritas yang diminta pengguna sendiri: **title,
description, H1, isi halaman, structured data, teknis crawl**. Bersama-
sama keduanya cuma sekitar 250 karakter, ditulis sekali per halaman,
dan merekalah satu-satunya bagian halaman yang dibaca orang **sebelum**
memutuskan mengklik.

### Kandidat diadu, bukan jawaban pertama dipakai

Judul tidak diterima apa adanya. `title` dan `meta_description`
diminta di giliran sendiri, dinilai `title_penalty` /
`description_penalty`, lalu diminta ulang sampai `TITLE_REPEAT_RETRIES`
habis — dan yang terbit kandidat dengan nilai terkecil, bukan yang
pertama datang. Dengan suhu di atas nol, permintaan yang sama
menghasilkan kalimat yang berbeda tiap kali, jadi percobaan tambahan
tidak pernah membuat hasilnya lebih buruk.

Kandidat yang kalah tidak pernah sampai ke halaman.

Mesinnya — `title` dan
`meta_description` memang diminta di giliran sendiri (`SINGLE_ROLES` di
`generators/content_batches.py`), dan jawaban yang buruk diminta ulang
lalu diadu. Yang berubah: ambangnya turun dari 1.0 ke
`HEAD_GOOD_ENOUGH` (0,7), jadi judul yang cuma "tidak melanggar" tetap
ditantang sekali. Dengan ambang 1.0, permintaan kedua hampir tidak
pernah berangkat, dan yang ada bukan pemilihan kandidat melainkan
penolakan yang kebetulan jarang kena.

### Apa yang membuat sebuah judul ditolak

Satu penilai untuk kedua jalur — `title_penalty` dan
`description_penalty` di `generators/content_planner.py`. Semua
alasannya dinyatakan sebagai **kelipatan ambangnya masing-masing**,
jadi 1.0 selalu berarti "tepat di batas" apa pun alasannya, dan
semuanya bisa diadu di satu tempat.

| Alasan | Judul | Deskripsi |
|---|---|---|
| Mengulang halaman yang sudah terbit (`title_echo_score` / `echo_score`) | ya | ya |
| Menyalin contoh gaya yang dilihatnya (`style_copy_score`) | ya | ya |
| Keyword hilang atau terbit rusak (`keyword_missing_score`) | ya | — |
| Ekornya menumpuk kata penyangat (`title_tail_pile`) | ya | — |
| Penyangat disebar rata (`filler_share_score`) | ya | — |
| Beberapa janji didempetkan koma (`clause_pile_score`) | ya | — |
| Berakhir menggantung (`incomplete_tail_score`) | ya | — |
| Gagasannya sama walau katanya beda (`concept_repeat_score`) | ya | — |
| Bentuk retorisnya sama (`shape_repeat_score`) | ya | — |
| Keyword ditulis berulang | maks 1× | maks 2× |
| Nama situs ditulis berulang | ditegakkan bentuknya | maks 1× |
| Membuka dengan kata yang sama (`opening_repeat_score`) | ya | ya |
| Menuliskan ulang judulnya sendiri | — | ya |
| Aksara asing bukan dari masukan (`script_leak_score`) | ya | ya |

Dua ukuran terakhir yang baru, dan keduanya menutup lubang yang
terukur. `filler_share_score` menangkap pola yang paling sering
dikeluhkan — `[BRAND] Situs Slot Gacor Terbaik dan Terpercaya` —
yang lolos `title_tail_pile` karena penyangatnya tidak menumpuk di
ekor melainkan disebar rata, jadi tidak ada ekor yang bisa dipotong.
Ambangnya `TITLE_FILLER_SHARE = 0.34`, diukur dari 120 contoh title
milik pengguna sendiri di `knowledge/gaya_title.txt`: judul miliknya
rata-rata 0,12 penyangat per kata isi dan yang tertinggi 0,29.

### Kenapa judul diukur di LUAR brand dan keyword

`echo_score` membandingkan kosakata dua teks, dan untuk judul itu
salah arah — karena dua hal di setiap judul memang **wajib** sama:
nama situs dan keyword. Terukur 16 Agustus 2026, tiga judul yang
gagasannya jelas berbeda:

```
WAYANGPLAY — Slot Gacor Online          echo 1,33  DITOLAK
WAYANGPLAY — Pilihan Slot Online Terbaru  echo 1,25  DITOLAK
WAYANGPLAY — Platform Slot Gacor Online   echo 1,25  DITOLAK
```

Ketiganya ditolak, dan angkanya bisa ditelusuri sampai habis: 3 token
bersama dari 8 = 0,375 ÷ `ECHO_COVERAGE` 0,6 ÷ `TITLE_REPEAT_LIMIT`
0,6 = 1,04. Yang dihukum bukan pengulangan melainkan kepatuhan pada
dua aturan yang ditegakkan sistem ini sendiri.

`bare_title()` mencabut nama situs (lewat `title_promise`), lalu frasa
keyword utuh, lalu tiap kata keyword satu per satu. `title_echo_score`
membandingkan sisanya. Yang tersisa dari ketiga judul di atas:
`Online`, `Pilihan Online Terbaru`, `Platform Online` — dan itu memang
tiga hal yang berbeda.

```
sesudah : 0,83   0,83   0,56   (tidak satu pun ditolak)
```

Pengulangan yang sungguhan tetap tertangkap: `… Slot Gacor Online`
diikuti `… Slot Gacor Online Terbaik` bernilai 2,00. Perbaikan yang
sama dipasang pada `style_copy_score` untuk riwayat, dengan alasan
yang persis sama.

`opening_repeat_score` menangkap dua teks yang **membuka** sama
meskipun sisanya berbeda. `echo_score` tidak bisa: ia membandingkan
pembuka sepanjang acuannya, dan untuk deskripsi 170 karakter itu
hampir seluruh kalimat. Terukur pada dua permintaan berturut-turut
sebelum ini dipasang:

```
desc 1 : Cari slot gacor di WAYANGPLAY. Mulai bermain sekarang ...
desc 2 : Cari slot gacor di WAYANGPLAY dengan pengalaman ...
```

`echo_score` menilainya 0,62 — di bawah ambang — padahal empat kata
pertamanya sama persis, dan itulah yang dibaca orang di hasil
pencarian.

Kata pembukanya dicari sesudah nama situs **dan tanda pisahnya**
dibuang (`opening_words` memakai `title_promise`). Itu bukan kerapian,
dan bugnya sempat membuat `shape_repeat_score` tidak berguna sama
sekali: dipakai `bare_style` saja, yang tersisa sesudah nama situs
dicabut adalah tanda pisahnya, jadi "kata isi pertama" setiap judul
adalah `#` — setiap judul berbentuk `(False, '#')`, dan setiap
pasangan judul dinilai berbentuk sama. Nilainya **selalu 1,00**,
apa pun judulnya.

Sesudah dibetulkan, lima judul yang benar-benar terbit berturut-turut:

```
bentuk : registrasi / waktu / hadiah / belajar / sandi
nilai  : 0,00  0,00  0,00  0,00  0,00
```

Dan dua judul yang memang mengulang bentuknya — sama-sama bertanya,
sama-sama dibuka `Cari` — tetap 1,00.

`clause_pile_score` menangkap judul yang isinya beberapa janji
didempetkan koma — keluhan "judulnya kaku dan terputus, tidak
tersusun dalam satu kalimat". Terukur pada judul yang benar-benar
terbit:

```
WAYANGPLAY # Akses Cepat Slot Gacor, Dana Aman, Langsung Dibayar
SIAM123 💰 Kamu Main slot online, lihat hasilnya, dapatkan pembayaran
```

Ambangnya `TITLE_CLAUSE_ALLOWED = 1`, dan angkanya dari 143 baris
contoh title milik pengguna sendiri, dihitung pada bagian **janji**-nya
saja (sesudah nama situs dan tanda pisahnya dibuang):

| Pemisah klausa di janji | Baris | Bagian |
|---|---|---|
| 0 | 111 | 78% |
| 1 | 26 | 18% |
| 2 | 3 | 2% |
| 3 | 3 | 2% |

Satu lazim, dua ke atas praktis tidak ada. Untuk aksara yang tidak
memakai koma seperti Thai, pemeriksaan ini praktis tidak pernah
berbunyi — disengaja, karena ambangnya diukur dari contoh berbahasa
Indonesia dan menebak ambang untuk bahasa tanpa pembanding berarti
menolak judul atas dasar dugaan.

### Jalur prompt terpisah untuk metadata

Permintaan ulang yang isinya **hanya** judul memakai
`build_title_only_prompt` — bukan prompt halaman penuh yang juga
mengatur paragraf, heading, FAQ, dan ulasan. Prompt halaman penuh
tidak diubah sedikit pun.

Sebabnya terukur:

| | Prompt bersama | Prompt metadata |
|---|---|---|
| Panjang | 5.363 token | **1.230 token** (23%) |
| System prompt | 332 token, menyebut "menyusun landing page" | 211 token, menyebut "penulis metadata SEO" |
| Blok terbesar | `Aturan Isi` 2.895 token | — |
| Letak perintah sudut | 13% awal, ditimbun 4.700 token | 11% awal, ditimbun ~1.000 |

Blok `Aturan Isi` mengatur paragraf, heading, FAQ, dan ajakan daftar —
tidak satu pun berlaku untuk permintaan yang tidak menulis satu
paragraf pun.

Repo ini sudah pernah menemukan sebab yang sama, dan catatannya masih
berdiri di `forbidden_claims_block`: *"yang dibaca terakhir yang paling
berpengaruh pada model kecil ... aturan yang berdiri di sepertiga awal
prompt selebar itu terbukti dilewati."* Blok larangan klaim dipindah ke
bawah karena itu; aturan judul tidak pernah ikut dipindah.

Akibatnya terbaca di lima generate berturut-turut 16 Agustus 2026 —
**dua dari lima judul tidak menyinggung sudutnya sama sekali, dan
kelimanya ditolak** meskipun sudah tiga permintaan × tiga kandidat.

### Sudut judul ditentukan model, bukan NEIIU

Dulu NEIIU memilihkan sudut judul dari daftar tetap dua belas butir,
mengirimkannya sebagai perintah berbagian (`SUDUT`, `YANG DICARI`,
`WAJIB TERASA`, `JANGAN JADI POKOK`), lalu memeriksa hasilnya dengan
`angle_coverage_score` dan `angle_violation_score`.

Seluruh mesin itu **dicabut** atas permintaan pengguna, dan alasannya
kelihatan di judul yang terbit karenanya:

```
WAYANGPLAY # RTP Slot Gacor Data, Sumber, dan Perbarui
```

Judul itu bukan buruk karena modelnya kurang pandai. Ia buruk karena
**patuh**: ia sedang mencentang daftar kata yang disodorkan padanya,
dan hasilnya terbaca persis seperti daftar kata yang dicentang.

Yang dikirim sekarang kebalikannya:

```
1. SUDUT JUDULNYA KAMU YANG MENENTUKAN. Orang yang mengetik
   "<keyword>" sedang mencari sesuatu; putuskan sendiri apa yang
   paling berguna dijanjikan kepadanya. Tidak ada daftar kata yang
   harus kamu centang di sini.
2. SATU gagasan, bukan tiga.
3. Jangan memaksakan kosakata apa pun. Angka, persen, "sumber data",
   "terbaru", "diperbarui", "RTP" - kalau sudut yang kamu pilih tidak
   benar-benar membutuhkannya, jangan ditulis.
```

**Yang tidak ikut dicabut** adalah seluruh ukuran MUTU: koma
menumpuk, ekor menggantung, kata penyangat, keyword dua kali, gagasan
yang mengulang halaman sebelumnya. Tidak satu pun dari ukuran itu
menuntut kosakata tertentu hadir — semuanya menilai apa yang ditulis,
bukan mencocokkannya ke daftar.

Bentuk judul juga tetap: nama situs, satu tanda pisah, lalu janji,
ditegakkan `enforce_title_shape`. Itu keputusan produk 10 Agustus
2026 dan tidak ikut berubah.

### Aksara asing di jawaban model

qwen3:4b sesekali memilih satu token beraksara Han di tengah kata
Indonesia. Terukur 16 Agustus 2026 di deskripsi yang benar-benar
terbit:

```
Sumber data RTP slot gac或 di WAYANGPLAY diambil dari penyedia resmi
```

`slot gac或` bukan salah pilih kata melainkan **token yang salah**, dan
tidak satu pun pemeriksa mutu bisa melihatnya: panjangnya pas, sudutnya
benar, tidak ada klaim, tidak mengulang apa pun.

`foreign_script_chars()` di `generators/content_planner.py` memakai
daftar aksara yang **dilarang**, bukan daftar yang diizinkan. Bedanya
disengaja: daftar izin harus menyebutkan setiap blok Unicode yang boleh
lewat — huruf beraksen, mata uang, tanda baca tipografis — dan setiap
yang lupa disebut jadi salah tuduh. Yang dilarang: Han, kana, Hangul,
Kiril, Ibrani, Arab, Devanagari, dan tanda baca lebar CJK.

Aksara Thai **tidak** ada di daftar itu, di kedua zona. Untuk halaman
Thai ia jelas sah; untuk halaman Indonesia, satu huruf Thai yang nyasar
belum pernah terukur sekali pun.

Huruf yang memang ada di keyword atau nama situs tidak pernah dihitung.
Nama situs beraksara CJK yang diminta pengguna sendiri lolos utuh.

Yang dikerjakan **deteksi → tolak → minta ulang**, bukan bersihkan.
Membuang hurufnya menyisakan `slot gac`, yang sama rusaknya tapi tidak
lagi terlihat rusak — dan tidak ada cara menebak kata apa yang
seharusnya ada di situ. Permintaan ulangnya menyebutkan hurufnya satu
per satu (`script_reason()`), karena model kecil tidak bisa mencari
sendiri huruf mana yang dimaksud di dalam kalimatnya.

Ini satu-satunya tambahan ke `description_penalty`, dan ia ada di situ
karena deskripsi tempat bugnya benar-benar terbit.

### Keyword wajib utuh di judul

Lubang yang paling memalukan, dan baru ketahuan setelah prompt
metadata dipasang — judul ini terbit dengan penalti **0,00**:

```
WAYANGPLAY # Slot gac Provinsi dari ponsel untuk Android dan browser
```

Sudutnya diikuti dengan benar, panjangnya pas, tidak menumpuk
penyangat, tidak mengulang apa pun — dan tidak memuat kata yang
seluruh halaman ini dibuat untuk memenanginya. Tidak satu pun
pemeriksa keberatan, karena tidak satu pun pernah menanyakannya.

`keyword_missing_score` memakai `keyword_covered` apa adanya,
termasuk kelonggarannya untuk tahun dan kata penunjuk waktu: judul
yang menulis "slot gacor" untuk keyword "slot gacor 2026" tetap
terhitung memuatnya.

### Batas yang harus diketahui: sinonim

`concept_repeat_score` mengakarkan kata lebih dulu (`word_root`), jadi
"kemenangan" dan "menang" terbaca satu hal. Ambangnya `0.34`, diukur
dari 7.140 pasangan di antara 120 judul milik pengguna (persentil 99 =
0,200) dibandingkan pasangan yang benar-benar mengulang (0,500).

**Ia buta terhadap sinonim.** `Cari slot gacor di X` dan `Temukan slot
gacor di X` mendapat 0,000 padahal keduanya gagasan yang sama.
Menutupnya butuh embedding. Yang menegakkan perbedaan gagasan di sini
bukan ukuran kemiripan melainkan **sudut yang ditugaskan lalu
diperiksa** — dua judul yang masing-masing wajib membawa sudut berbeda
tidak bisa jadi gagasan yang sama, berapa pun sinonim yang dipakainya.

### Judul yang berakhir menggantung

`incomplete_tail_score` menangkap `..., Kemenangan` — satu kata
sesudah koma yang tidak terikat ke apa pun. Yang diperiksa **panjang
dan letak**, bukan jenis kata: dari 120 judul milik pengguna, 11
memakai koma dan potongan terakhirnya tidak pernah kurang dari **tiga
kata** (3,4,4,4,4,5,5,5,6,6). Judul tanpa koma tidak pernah tersentuh,
jadi `WAYANGPLAY — Pilihan Slot Online Terbaru` yang juga berakhir di
kata benda sama sekali tidak kena — aturan "tidak boleh berakhir kata
benda" akan salah untuk hampir semua judul yang bagus.

### Kalau ditolak, alasannya dikatakan

Percobaan kedua dulu mengirim prompt yang sama persis, jadi yang
dikerjakannya cuma mengocok ulang dadu — dan terukur, jawaban kedua
mengulang lagi dengan kata yang digeser. `title_reasons` menyusun
alasannya jadi kalimat yang dibaca model:

```
# PERBAIKAN JAWABAN SEBELUMNYA

- title: kemarin beberapa janji yang didempetkan koma, bukan satu
  judul yang utuh. Pilih SATU janji dan buang sisanya ...
- meta_description: keyword "..." kemarin diulang terlalu sering.
```

Tiap alasan diperiksa sendiri-sendiri, bukan disimpulkan dari nilai
gabungannya: perbaikan yang menyuruh membetulkan hal yang tidak salah
membuat jawaban kedua lebih buruk daripada yang pertama.

Ambang yang memicu permintaan ulang `HEAD_GOOD_ENOUGH` (0,7), bukan
1,0 — judul yang cuma "tidak melanggar" tetap ditantang sekali, dan
itulah yang membuat pemilihan kandidat benar-benar terjadi. Murah
karena permintaan ulangnya mengirim satu peran saja, dengan awalan
prompt yang sudah di cache.

Ulangan hanya berangkat kalau jawabannya memang ditolak, jadi
permintaan yang jawabannya sudah bagus tetap selesai sekali kirim.

Percobaan **terakhir** berangkat dengan ruang yang dipersempit
(`HEAD_STRICT_NOTE`), bukan dengan keterangan yang lebih panjang:
wajib pernyataan, tanpa sapaan ke pembaca, tanpa koma, dibuka kata
benda. Terukur pada model 4B — penjelasan yang lebih panjang dibaca
sebagai bahan tulisan, larangan yang lebih sempit benar-benar mengubah
jawabannya.

### Aturan judul ditulis sebagai langkah bernomor

Untuk `qwen3:4b-instruct`, "tulis judul yang bervariasi dan tidak
terasa template" adalah kalimat yang tidak bisa dikerjakan siapa pun
langkah demi langkah, dan model kecil menjawabnya dengan kembali ke
pola yang paling dikenalnya. Blok aturan judul sekarang sepuluh
langkah bernomor yang masing-masing bisa dikerjakan: tentukan
sudutnya sendiri, satu gagasan saja, jangan memaksakan kosakata,
jangan buka dengan kata itu, jangan tempelkan kata di ujung.

Larangan pembuka disebut **terpisah** dari daftar judul lama, dan itu
bukan pengulangan: model 4B membaca "jangan tulis ulang judul ini"
sebagai "jangan salin kalimat ini" — lalu menulis kalimat lain yang
dibuka kata yang sama persis.

### Generate kedua harus berbeda

Halaman kedua untuk keyword yang sama harus berangkat dari gagasan
yang lain. Dulu itu ditegakkan dengan menggilir sudut dari daftar
tetap; sejak sudutnya diserahkan ke model, yang menegakkannya adalah
**riwayat apa yang benar-benar terbit** — ukuran atas hasil, bukan
daftar yang dibagikan di muka.

Dua hal, dan keduanya memakai judul yang sama:

1. **Judul lama disebut ke dalam prompt** (`title_history_block`),
   beserta daftar pembuka yang dilarang. Aturan "jangan mengulang"
   tanpa menyebut apa yang tidak boleh diulang adalah aturan yang
   tidak bisa diikuti: model tidak menyimpan ingatan antar permintaan.
2. **Jawaban yang tetap mengulang ditolak** — `concept_repeat_score`
   untuk gagasan yang sama meski katanya digeser,
   `opening_repeat_score` untuk pembuka yang sama, dan
   `shape_repeat_score` untuk bentuk retoris yang sama.

Riwayatnya lintas run dan tersimpan di database, jadi yang
dibandingkan judul halaman yang benar-benar sudah terbit.

### Model khusus kepala halaman

`AI_MODEL_HEAD` di `.env` memindahkan **giliran title + meta
description saja** ke model lain. Dikosongkan, ia sama dengan
`AI_MODEL` dan tidak ada satu pun perilaku yang berubah.

Alasannya sama dengan `AI_MODEL_INSIGHT`, dan angkanya berpihak lebih
jauh lagi: giliran ini jalan **sekali per run** atas jawaban 250
karakter, sedangkan isi halaman ratusan potong yang ditulis
berkali-kali. Model yang tiga kali lebih lambat di sini menambah
beberapa puluh detik pada run yang belasan menit.

Harganya yang perlu diketahui: Ollama memuat ulang model tiap kali
modelnya berganti, jadi mengisinya berarti dua kali muat per run. Untuk
mesin yang memorinya pas-pasan itu bisa lebih mahal daripada mutu yang
didapat. Pastikan modelnya sudah di-`ollama pull` sebelum diisi.

### Title landing dan title AMP wajib sama

Keduanya diisi dari isi yang sama, jadi dua teks yang berbeda berarti
salah satu slotnya tidak kebagian — dan yang terbit di tempatnya
kalimat pemilik template. Diperiksa `check_head_pair` di
`generators/seo_validator.py`, bersama satu pemeriksaan lagi: nama
situs harus ada di title.

Keduanya lahir dari halaman yang benar-benar terbit:

```
landing : Cara Akses Slot Gacor di HP dengan Link Resmi
AMP     : WAYANGPLAY – Solusi Deposit QRIS yang Cepat dan Praktis
```

Yang pertama 45 karakter dan tidak menyebut nama situs sama sekali;
yang kedua judul milik template dengan nama brandnya saja yang
tertukar, dan keywordnya tidak ada di situ. Dua halaman yang
seharusnya satu maksud terbit dengan dua judul yang tidak berhubungan,
dan tidak satu pun pemeriksaan yang berjalan waktu itu keberatan.

---

## Ragam Bahasa: Setengah Resmi

Diminta pengguna 21 Agustus 2026: "bahasa yang tidak kaku, formal tapi
tidak terlalu formal dan jangan menggunakan bahasa yang santai".

Yang terbit sebelumnya memang santai, dan sebabnya bukan model
melainkan **aturannya sendiri**. Dua baris di `VOICE_TEMPLATE_ID`
menariknya ke sana:

```
- Subjek kalimatnya ORANG ... Tulis "kamu bisa lihat angkanya di layar"
- Boleh memakai kata sehari-hari ... "nggak", "udah", "bikin" ...
```

Baris pertama mencontohkan "kamu"; baris kedua **menyuruh** memakai
bahasa gaul. Halaman BATARATOTO terbit dengan sembilan kalimat yang
dibuka "Kamu bisa ..." dan satu jawaban FAQ yang ditutup "sistem akan
membuat akun untukmu".

Tiga lapis menegakkannya sekarang:

1. **Aturan di prompt.** Sapaan dipatok "Anda"; daftar kata yang
   terlalu santai dan daftar kata yang terlalu kaku disebut
   berdampingan, supaya yang diminta terbaca sebagai rentang, bukan
   sebagai satu arah.
2. **Penyapu di Python** — `fix_content_register` di
   `utils/spelling.py`, dipanggil di titik yang sama dengan penyapu
   salah ketik, dan **hanya untuk zona Indonesia**. Aturan prompt
   untuk model 4B diikuti kadang-kadang saja; ini jaring pengamannya.
   Nama situs dilindungi lewat `protected_words`, sama seperti penyapu
   salah ketik — nama situs boleh saja berbunyi seperti kata gaul.
3. **Contoh gaya ikut disaring.** Ini yang paling menentukan, dan
   penjelasannya di bawah.

### Contoh gaya tidak boleh melanggar aturannya sendiri

`knowledge/gaya_artikel.txt` milik pengguna memuat dua register
sekaligus. Yang sampai ke model sebelum 21 Agustus 2026:

| contoh | masalahnya |
| --- | --- |
| "...withdraw **nggak** pernah **bikin** deg-degan" | kata yang dilarang aturan |
| "...pilihan terbaik **buat kamu** yang ingin main" | sapaan yang dilarang aturan |
| "[ BRAND ] **bukan sekadar** situs slot biasa." | bentuk yang dilarang aturan |

Model 4B yang menerima aturan abstrak bersama contoh nyata mengikuti
**contohnya**. Selama contohnya tidak ikut disaring, aturan di prompt
cuma memakan context.

Dua perbaikan:

- `ROBOT_FILTER` diperlebar: `bukan sekadar` tidak lagi menuntut
  "tapi" di belakangnya. Bentuk dua kalimat — "bukan sekadar X. Ini
  adalah Y." — dulu lolos.
- `CASUAL_FILTER` baru, dan ia **tegas**: tidak pernah dilepas walau
  menyisakan sedikit. Daftarnya diambil dari `CASUAL_WORDS`, daftar
  yang sama dengan penyapu ragam bahasa, jadi yang dilarang terbit dan
  yang dilarang jadi contoh selalu satu daftar.

`MIN_VOICE_POOL` turun 3 → 2 supaya kolam yang menyusut tidak membuat
`ROBOT_FILTER` dilepas seluruhnya. Yang tersisa dari berkas pengguna:
**2 contoh**, keduanya setengah resmi.

> **Yang paling menaikkan mutu artikel sekarang ada di tangan
> pengguna**, bukan di kode: menambah contoh paragraf setengah resmi
> ke `knowledge/gaya_artikel.txt`. Sebelas dari enam belas paragraf di
> berkas itu tersaring karena berbunyi brosur, tiga lagi karena
> berbahasa gaul.

Daftar frasa brosur sekarang berdiri sebagai `BANNED_PHRASES_ID` di
`ai/language_rules.py` dan dipakai **dua kali** — sekali menyusun
aturannya di prompt, sekali menyaring contohnya. Dua daftar yang
berdiri sendiri-sendiri akan bergeser tanpa yang lain tahu.

## Judul Harus Menyebut Sesuatu

Yang terbit 21 Agustus 2026:

```
BATARATOTO - Slot Online Pengalaman Bermain Terbaik
```

Di luar nama situs dan keyword "slot online", yang tersisa "Pengalaman
Bermain Terbaik": tiga kata yang tidak menunjuk satu hal pun yang bisa
dibuka, dibandingkan, atau dicari. Contoh milik pengguna sendiri
selalu menambah topik kedua — "& Bocoran Pola Slot Gacor", "& Login
Anti Blokir 24 Jam".

Penilai judul yang ada tidak bisa membedakan keduanya: judul datar itu
dan judul yang bagus **sama-sama bernilai 0,98**, tepat di bawah
ambang terima 1,0.

`vague_title_score` menutupnya. Ia memeriksa bagian judul di luar nama
situs dan di luar keyword, lalu menuntut **paling sedikit satu kata
topik**. Kosakatanya **dipanen dari berkas contoh milik pengguna**,
bukan ditulis tangan — 418 kata dari `gaya_title.txt` dan
`gaya_title_deskripsi.txt`, dikurangi kata rasa (`VAGUE_WORDS`) dan
kata tugas. Jadi daftarnya ikut berubah sendiri begitu pengguna
mengganti contohnya.

**Ini bukan mesin sudut judul yang dicabut 18 Agustus 2026.** Yang itu
menugaskan satu sudut lalu menuntut kata dari daftar sudut itu; yang
ini tidak menugaskan apa pun dan menerima topik mana saja. Sudutnya
tetap dipilih model — yang dituntut cuma judulnya menyebut sesuatu.

Alasannya ikut dikirim balik ke model lewat `title_reasons`, jadi
permintaan ulangnya tahu apa yang salah.

### Deskripsi dibuka nama situs

Keempat puluh contoh di `gaya_title_deskripsi.txt` dibuka dengan cara
yang sama persis: nama situs, lalu satu kata kerja yang menyatakan apa
yang disediakannya — "menjamin", "menawarkan", "menyediakan", "adalah",
"menyajikan". Tidak satu pun dibuka dengan menyapa pembaca.

Yang terbit dibuka "Kamu bisa mulai bermain slot online langsung dari
HP". `desc_opening_score` memeriksa **enam kata pertama** saja;
sisanya dibebaskan, karena di situlah contoh pengguna sendiri
berbeda-beda. Permintaan ulangnya membawa alasan yang menyebut bentuk
yang diminta, bukan kalimat tetap.

## Bidang Halaman

NEIIU tidak lagi menganggap setiap halaman halaman slot.
`ai/niche.py` mengenali bidangnya dari keyword dan nama brand, lalu
tiga hal mengikutinya:

| | `gambling` | bidang lain |
|---|---|---|
| Daftar kesanggupan brand | deposit, withdraw, yang menang dibayar | data aman, pesanan diurus sampai selesai |
| Isi FAQ | seputar slot | seputar topik halaman ini |
| Bank FAQ cadangan | 14 tanya-jawab slot | 6 tanya-jawab ber-lubang `{topik}` |
| Contoh di aturan bunyi | "Slot gacor bukan sekadar…" | "Layanan ini bukan sekadar…" |
| Contoh di daftar larangan | RTP, janji menang | persen kepuasan, janji hasil |
| Sudut judul (12 pilihan) | RTP live, deposit, link login | harga, cara mulai, bedanya |
| Emoji pemisah judul | 🎰 💰 🔥 ✨ ⚡ | ✨ ⭐ ✅ → • |
| Contoh gaya `knowledge/*.txt` | dikirim | tidak dikirim |

**Bidang `gambling` menghasilkan teks yang sama huruf per huruf
dengan sebelum pemisahan ini ada** — diuji terhadap `git HEAD`, bukan
diperkirakan. Yang berubah cuma halaman di bidang lain, yang
sebelumnya terbit dengan janji dan FAQ tentang bidang yang bukan
bidangnya.

Aturannya sendiri tidak ikut longgar: angka karangan dan janji hasil
tetap dilarang di bidang mana pun. Yang berbeda cuma contohnya —
dan itu penting, karena contoh judi di dalam daftar larangan
menyodorkan kosakata judi ke model tepat saat ia diminta menulis
tentang hal lain.

---

## Footer Dibiarkan, Termasuk Yang Dirakit Dari `<div>`

Pembekuan menu dan footer sudah ada sejak lama, dan yang dibacanya
**tag**: `<footer>`, `<header>`, `<nav>`, `<menu>`. Alasannya tertulis
di `in_frozen` — nama class bebas dipilih pembuat template, dan
"footer-cta" di tengah halaman bukan footer.

Yang tidak tertangkap: template yang footernya dirakit dari `<div>`
biasa. Template 488 tidak punya satu pun tag `<footer>`; kolomnya
ditandai `m-footer__trusted-text`, `m-footer-links`, dan
`m-foot__links-section`. Seluruh kolom footer toko ikut ditulis ulang,
dan judul kolomnya terbit begini:

| di template | yang terbit |
| --- | --- |
| Support | Pengalaman |
| About Us | Sistem Stabil |
| Explore | Pemain Aktif |
| Artists | Pilihan Banyak |
| Follow Us | Keamanan Tinggi |
| We Accept | Main Tanpa Batas |

Pengguna memintanya berhenti 21 Agustus 2026: "untuk bagian footer
jangan ubah bila tidak menyangkut brand jika footer adalah bagian
bawaan dari iklan template maka jangan ubah apapun."

`FOOTER_HINT` sekarang ikut membaca **nama class dan id**, di elemen
slot maupun seluruh leluhurnya. Dua hal yang perlu diketahui:

- **Kelebihan tangkap dipilih dengan sadar.** "footer-cta" di tengah
  halaman ikut beku. Harganya satu blok yang memakai kata-kata
  template; harga kebalikannya footer toko yang isinya diacak.
- **Pembekuan footer MUTLAK**, tanpa pengecualian salinan asing.
  Pengecualian itu ada supaya sisa teks demo berbahasa lain tetap
  tertulis ulang di mana pun ia berdiri, dan untuk badan halaman itu
  benar. Untuk footer justru itu yang membuka persis blok yang paling
  tidak boleh dibuka — kolom footer template buatan luar memang hampir
  seluruhnya berbahasa Inggris.

Yang **menyangkut brand tetap berganti**: nama brand lama di footer
diganti nama baru lewat `brand_edits`, seperti di bagian beku lainnya.

Terukur di template 488: slot `heading` turun dari 15 jadi 8,
`nav_label` dari 124 jadi 94, dan tidak ada satu pun slot badan
halaman yang ikut hilang. Diuji di `tests/test_footer_and_echo.py`.

## Judul Lama Diganti Di Mana Pun Ia Berdiri

Lapis gema menyamakan teks lama yang kembar dengan teks barunya —
itulah yang membuat 34 atribut `alt` berisi judul lama terbit dengan
judul baru. Sampai 21 Agustus 2026 ia cuma mengenali kembar **persis**.

Yang lolos: judul yang ditempeli keterangan pemilik gambar. Dari tujuh
kemunculan judul lama di halaman BATARATOTO, dua bertahan, keduanya
berbentuk

```html
alt='BATARATOTO : Situs Slot Eksklusif ... by Hey siriusly'
```

Judulnya sama persis; yang membuatnya lolos empat kata di belakangnya.
Pengguna memintanya ditutup: "setiap kalimat tersebut akan di ubah
oleh kalimat terbaru yang sudah di buat oleh AI".

`echo_edits` sekarang punya jalan kedua: kalau kembar persis tidak
ketemu, ia mencari teks lama sebagai **potongan di dalam** teks slot,
yang terpanjang lebih dulu, lalu menukar potongan itu saja.
Keterangan di sekitarnya — "by Hey siriusly" — tetap berdiri, karena
ia menyebut pemilik gambar dan bukan bagian dari judul.

Terukur di template 488: sisa judul lama 2 → **0**, sementara keempat
kredit pemilik gambar tetap utuh.

## Penyapu Klaim

`generators/claim_guard.py` membuang klaim yang tidak dipunyai
pipeline dari teks yang sudah ditulis model: lama proses dalam satuan
waktu, jumlah member, tahun berdiri, nomor lisensi, angka RTP dan
winrate, jumlah penghargaan, dan janji bahwa pembacanya akan menang.

Empat penyaring **membuang kalimat utuh**, bukan frasanya, karena yang
salah bukan satu kata melainkan seluruh pernyataannya:

| Penyaring | Contoh yang benar-benar terbit |
|---|---|
| `WIN_PROMISE` | "Jaminan menang untuk semua member baru." |
| `WIN_AMOUNT` | "Saya langsung menang 1 juta di situs ini." |
| `LUCKY_SCHEDULE` | "Pola slot gacor dilihat tiap pagi." |
| `FAKE_SOURCE` | "...diperbarui setiap pagi berdasarkan data real-time dari pemain." |

Tiga yang terakhir dipasang sesudah E2E memperlihatkan bahwa penyaring
lama melewatkan ketiganya. `fabricated_claims()` melaporkan apa yang
kena tanpa membuang apa pun, dan ia memakai daftar pola yang **sama
persis** — audit yang punya daftarnya sendiri akan bergeser dari
penyapunya tanpa ada yang tahu.

Jebakan yang ditutup satu per satu, dan semuanya diuji:

- **Harga barang tidak boleh ikut terbuang.** Mata uang dan harga
  memang berpindah zona bersama halamannya, jadi pola yang membuang
  setiap "150 ribu" akan mencabut harga dari halaman toko. `WIN_AMOUNT`
  menuntut kata kemenangan berdampingan dengan angkanya; "Harga jaket
  ini 150 ribu" tidak memuat satu pun, jadi lewat.
- **"gacor" TIDAK boleh jadi pemicu jadwal.** Keyword halaman ini
  memuat kata itu, jadi ia berdiri di hampir setiap kalimat.
  `LUCKY_SCHEDULE` menuntut kata **pola/bocoran/jadwal**, sehingga
  "Slot gacor bisa dicoba setiap hari" lewat sementara "Pola slot
  gacor dilihat tiap pagi" kena.
- **"data" saja bukan sumber.** "Data pribadi kamu disimpan aman"
  lewat; yang kena adalah data yang disebut sebagai **asal angka**.

## Jawaban Model Yang Salah Bahasa

Slot yang teks lamanya berbahasa lain memang sengaja **dibuka** untuk
ditulis ulang - itu gunanya tanda `fresh` di spec, dan tanpa itu sisa
teks demo milik template asing tidak pernah berganti.

Yang tidak diperhitungkan: model 4B yang diperlihatkan contoh
berbahasa Inggris kadang menjawab dalam bahasa Inggris juga. Terukur
pada halaman yang terbit 22 Agustus 2026, di slot keterangan milik
template toko:

```
Some users noted that the interface remains responsive even under
weak network conditions.
```

Kalimat itu **tidak ada di templatenya** — model yang menulisnya, jadi
tidak satu pun penjaga yang membandingkan hasil dengan template bisa
melihatnya.

`drop_foreign_content` memeriksa jawaban model dengan `foreign_copy`,
penilai yang sama yang dipakai menandai teks template. Yang salah
bahasa **dikosongkan, bukan dihapus**: pasangan tanya-jawab dan
pasangan judul-kartu dicocokkan lewat nomor urut, jadi menghapus satu
butir menggeser seluruh pasangan sesudahnya. Slot yang isinya kosong
jatuh ke penambal bahasa di `template_filler`, yang mengisinya dengan
teks seperan dari halaman yang sama.

Yang **tidak** ikut diperiksa: nama orang, nama kota, harga, dan label
pendek (lihat `LANGUAGE_ROLES`). Nama produk dan nama orang memang
sering berbahasa lain, dan mengosongkannya justru menghapus yang benar.
Diukur: "RTP Live Hari Ini" dan "Link Alternatif Resmi" — dua bentuk
yang diminta pengguna sendiri — tidak tertangkap sebagai bahasa asing.

Hanya berjalan untuk zona Indonesia. Zona lain punya penilai bahasanya
sendiri dan tidak boleh dinilai dengan alat yang bukan miliknya.

## Dua Janji Disambung "&", Bukan Koma

Yang terbit 22 Agustus 2026:

```
BATARATOTO - Slot Online Akses Cepat, Tidak Blokir
```

Koma di situ menjanjikan kelanjutan yang tidak pernah datang, dan
`incomplete_tail_score` menandainya sebagai kalimat menggantung —
nilainya tepat **1,00**, jadi judulnya ditolak di tiap percobaan lalu
tetap terbit sebagai "yang paling sedikit bermasalah".

Contoh milik pengguna memakai "&" untuk maksud yang sama, dan itu
bentuk yang dipakai mayoritas barisnya:

```
[ BRAND ] Withdraw Cepat & Instan | Jaminan Bayar 100%
[ BRAND ] RTP Live Hari Ini & Bocoran Pola Slot Gacor
[ BRAND ] Link Alternatif Resmi & Login Anti Blokir 24 Jam
```

`join_two_promises` menyambungnya di `enforce_title_shape`. Nilainya
turun 1,00 → **0,74**, dan bentuknya jadi sama dengan contoh pengguna.

Yang disambung **hanya** yang benar-benar dua janji pendek: satu koma
saja, potongan sesudahnya paling banyak empat kata, dan tidak dibuka
kata sambung. Judul dengan dua koma adalah tumpukan, dan itu urusan
`clause_pile_score` — bukan sesuatu yang boleh disembunyikan dengan
mengganti tandanya.

## Penjaga Token Sampah

`garbage_tokens()` di `generators/leak_guard.py` menangkap potongan
yang tidak pernah datang dari orang yang menulis halaman: kerangka
obrolan model (`<|im_start|>`, `[INST]`), penanda template yang belum
terisi (`{{TITLE}}`, `lorem ipsum`, `TODO`), dan nama pustaka Python
yang tersesat ke dalam kalimat (`tqdm`, `numpy`, `print(`).

Bedanya dari penjaga kebocoran perintah di bawah: yang itu mengenali
kalimat MASUK AKAL yang isinya perintah, jadi ia harus dibandingkan ke
prompt aslinya. Yang ini token yang tidak masuk akal di mana pun, jadi
ia bisa dipakai memeriksa halaman yang **sudah** terbit — yang
promptnya tidak ikut tersimpan.

Daftarnya sengaja pendek. Daftar hitam yang panjang akan memuat kata
yang kebetulan juga kata biasa lalu membuang kalimat yang tidak salah
apa pun. Diuji tidak tersangkut: "Impor data lama tidak diperlukan",
"Definisi RTP dijelaskan di bagian berikutnya".

## Nama Situs Yang Dipenggal Model

Terukur pada halaman yang benar-benar terbit 21 Agustus 2026:

```
BATARATOTO - Slot Online di BATARAT-TO-TO Akses Cepat, Tidak Blokir
```

Satu judul, dua sebutan nama situs, dan yang kedua bukan nama siapa
pun. Pemulih ejaan yang sudah ada tidak pernah melihatnya, dan
sebabnya di **tokenisasi**: `BRAND_CANDIDATE` memotong per deretan
huruf-angka, jadi `BATARAT-TO-TO` masuk sebagai TIGA kata —
`BATARAT`, `TO`, `TO` — dan tidak satu pun berjarak dua sunting dari
`BATARATOTO`.

Akibatnya berlipat, bukan satu:

1. Halaman berdiri atas nama situs yang tidak ada.
2. Bentuk yang rusak tidak dikenali `strip_brand_mentions`, jadi ia
   lolos dari penyapu sebutan kedua — judulnya menyebut nama situs
   **dua kali**, sekali benar sekali rusak.
3. Lapis gema menyalinnya ke seluruh halaman. Di halaman itu ke lima
   tempat sekaligus, termasuk `og:title` dan `alt` gambar.

`restore_split_brand` menutupnya, dan ia berjalan **sebelum** kedua
tingkat pemulihan ejaan yang lama, supaya hasil sambungannya ikut
dinilai seperti sebutan biasa. Dua jalan:

| jalan | menangkap | contoh |
| --- | --- | --- |
| huruf sama persis, pemisah opsional di tiap sela | penggalan murni | `BATARA TOTO`, `WAYANG-PLAY`, `B.A.T.A.R.A.T.O.T.O` |
| deretan bertanda hubung/titik/garis bawah, diadu dengan jarak sunting | penggalan **sekaligus** salah ketik | `BATARAT-TO-TO` (sebelas huruf, satu lebih banyak) |

Dua penjaga yang menahannya dari memakan kalimat biasa:

- **Nama yang dipisah SPASI dituntut sama persis huruf besar-kecilnya.**
  Spasi adalah pemisah kata yang sah, jadi tanpa syarat ini brand
  `SITUSSLOT` mengubah "situs slot gacor hari ini" jadi "SITUSSLOT
  gacor hari ini" — kalimat pembaca dimakan nama situs. Tanda hubung,
  titik, dan garis bawah tidak dituntut begitu; ketiganya jarang
  memisahkan dua kata biasa.
- **Nama pendek tidak dilayani**, ambangnya sama dengan pemulihan
  ejaan (`FUZZY_MIN_LETTERS`).

Dijalankan hanya atas isi yang ditulis model, tidak pernah atas HTML
template — jadi atribut seperti `data-ad-client` tidak pernah lewat
sini. Diuji di `tests/test_brand_split.py`.

## Teks Di Dalam `<script>` Bukan Gema

`script_edits` menyamakan teks yang tertanam di dalam `<script>`
dengan isi baru, dan itu ada sebabnya: blok konfigurasi seperti
`window.SEO_GEO_CONFIG = { META_TITLE: "..." }` menimpakan judulnya ke
`document.title` begitu halaman dibuka, jadi halaman yang `<title>`-nya
sudah berganti tetap kembali ke judul lama di layar pengunjung.

Yang **dicabut** 21 Agustus 2026: pemakaian peta gema di dalam skrip.
Di badan halaman, teks lama yang kembar memang harus ikut memakai
kalimat barunya. Di dalam skrip, "teks yang kebetulan sama" bukan gema
melainkan **data** — dan menimpanya mengubah perilaku halaman, bukan
isinya. Terukur di dua blok `<script>` milik template toko:

```
"Hey siriusly"   ->  "BATARATOTO"      (nama penjual di data produk)
"Adult Apparel"  ->  "Tidak ada"       (nama kategori di data produk)
```

Yang kedua bahkan menerbitkan kalimat yang artinya kebalikan dari yang
tertulis semula. Keduanya bukan tulisan yang dibaca siapa pun sebagai
isi halaman.

Yang tetap dikerjakan di dalam skrip cuma dua, dan keduanya sempit:
nilai di bawah kunci konfigurasi yang namanya sudah menyatakan isinya
(`CONFIG_KEYS`), dan nama brand lama di mana pun ia tertulis. Sisanya
dibiarkan apa adanya.

## Nama Situs Sebagai Token Atomik

Pengguna mengetik `SIAM123`, jadi seluruh halaman harus berbunyi
`SIAM123`. Model kecil rutin meleset satu huruf — terukur, yang
benar-benar terbit `SIAM12S` — dan satu huruf itu menerbitkan halaman
atas nama situs yang tidak ada.

`restore_brand()` di `generators/brand_swap.py` mengembalikannya, dan
ia dijalankan **di hulu**: begitu jawaban model masuk, sebelum satu
pun penilai melihatnya. Urutan itu bukan kerapian. Dijalankan di
ujung, ada lubang yang tidak kelihatan dari mana pun kecuali dari
halaman yang terbit:

```
dinilai : "WAYANGPLAY menghadirkan ... WAYANGPLA menyediakan ..."
          -> brand_repeat 0,0, LOLOS
terbit  : "WAYANGPLAY menghadirkan ... WAYANGPLAY menyediakan ..."
          -> nama situs dua kali
```

Deskripsi itu lolos justru **karena** salah ketiknya.

Dua tingkat, dan pemisahannya yang menahan mesin ini dari merusak kata
biasa:

1. Ejaannya benar, huruf besar-kecilnya salah (`Siam123`) — selalu
   dipulihkan, berapa pun panjang namanya.
2. Ejaannya sendiri meleset (`SIAM12S`, `SIAM1234`) — hanya kalau
   namanya cukup khas: memuat angka, atau paling sedikit enam huruf.

Diuji tidak tersentuh: "Wayang kulit" di halaman WAYANGPLAY, "Siam"
sebagai nama lama sebuah negara di halaman SIAM123, "megawatt" di
halaman MEGA, "play game" di halaman WAYANGPLAY, dan setiap kata yang
merupakan bagian dari keyword.

**Batas yang diketahui:** nama situs yang kebetulan juga kata biasa
akan membuat kata itu ikut berhuruf besar — brand `MEJA` mengubah
"Meja makan" jadi "MEJA makan". Itu akibat langsung dari aturan token
atomik, dan pilihannya memang begitu.

Ini lapis kedua, bukan satu-satunya. Lapis pertama daftar larangan di
prompt (`forbidden_claims_block`), yang sengaja berdiri **paling
bawah** karena yang dibaca terakhir paling berpengaruh pada model
kecil. Lapis kedua ada karena lapis pertama terbukti tidak cukup:
dengan seluruh aturan terpasang, permintaan pertama tetap terbit
dengan "Transaksi terjadi dalam hitungan detik".

Tiga hal yang perlu diketahui kalau bagian ini disentuh:

1. **Durasi cuma dibuang kalau berdiri dekat kata proses.** Tanpa
   pembatas itu, halaman toko roti kehilangan "dipanggang 20 menit" —
   keterangan yang benar, bukan klaim karangan. Diuji: resep,
   durasi kursus, dan jam mulai kelas semuanya dibiarkan.
2. **Yang dibuang frasanya, kalimatnya cuma kalau jadi puing.**
   Kelayakan kalimat sisa diperiksa dari tanda kerusakan yang bisa
   diukur — dua kata tugas berdampingan, huruf awal jadi kecil,
   terlalu pendek. Rasio penyusutan sempat dicoba dan dibuang: ia
   tidak memisahkan kalimat yang benar dari yang janggal.
3. **Jangan hitung kata dengan `split()` untuk aksara Thai.** Thai
   memberi spasi antar frasa, bukan antar kata; jebakan yang sama
   sudah pernah menjatuhkan seluruh kartu FAQ cadangan zona Thailand.

Slot yang jadi kependekan **gara-gara** penyapuan tidak dibiarkan:
lubangnya dikumpulkan sesudah semua penyapu selesai, lalu ditambal
lewat satu permintaan tambahan — lihat "Menambal Slot Yang Kependekan
Sesudah Penyapuan".

---

## Slot Yang Tidak Terjawab Model

Ini cacat yang paling sering terlihat waktu hasil generate dibaca, dan
yang paling mudah salah dikira "template tidak diganti": slot yang
tidak kebagian isi terbit dengan **teks pemilik template**. Terukur dua
kali di satu run E2E:

```
CASE B : <h2> "Bagian Pertama Milik Template", ulasan ke-3 milik pemilik
CASE D : ulasan ke-2 DAN ke-3 milik pemilik
```

Mesin pendeteksinya sudah benar dan tidak diubah: `short_roles`
menemukan posisi mana yang kosong, `gap_spec` menyusun permintaan
susulan untuk posisi ITU saja, dan permintaan itu dikirim sampai
`SHORT_ANSWER_RETRIES` habis. Yang tidak ada adalah **jaring
terakhir**.

FAQ sudah punya jaring itu sejak lama lewat `FAQ_BANK`, dan jalannya
lewat `spare` di `fit_content_to_spec`. Yang ditambahkan sekarang cuma
bahan untuk dua peran lain yang belum punya:

| Bank | Untuk | Isinya |
|---|---|---|
| `REVIEW_BANK` | `review_text` | tampilan, navigasi, kecepatan buka, keterbacaan |
| `HEADING_BANK` | `heading` | judul bagian netral, berlubang `{topik}` |

Keduanya per zona, digilir dari nama brand supaya dua halaman yang
lubangnya sama tidak menambalnya dengan kalimat yang sama.

**Batas isinya diambil dari aturan pengguna sendiri.** Ulasan boleh
membahas tampilan, navigasi, kemudahan menemukan permainan,
responsivitas, dan kemudahan akses — dan TIDAK boleh menyebut nominal,
persentase, jadwal, atau hasil. Tidak satu kalimat pun di bank
menyebut salah satunya, dan seluruhnya tetap lewat penyapu klaim di
ujung seperti teks yang ditulis model.

Peringatannya dibedakan menurut sumbernya, dan itu bukan kerapian:
bahan dari hasil crawl adalah salinan mentah milik situs lain dan
**harus** dibaca ulang, sedangkan bahan dari bank sudah ditulis untuk
keperluan ini. Menyebut keduanya "salinan dari kompetitor" membuat
peringatan yang benar terbaca seperti alarm palsu — dan peringatan
yang dianggap alarm palsu berhenti dibaca.

## H1 Bukan Judul Kedua

Niatnya sudah tertulis di `ensure_template_identity` sejak lama —
*"H1 dibaca sebagai kalimat pembuka di dalam halaman, bukan sebagai
baris di hasil pencarian, dan nama situs berpemisah di situ terbaca
seperti label"* — tapi tidak ada satu pun yang memeriksanya. Yang
terbit karenanya:

```
title : WAYANGPLAY # Slot Gacor Paling Menarik, Main Tanpa Ribet
h1    : WAYANGPLAY # Slot Gacor
h2    : WAYANGPLAY # Slot Gacor
```

Jatah H1 di template itu 40 karakter dan yang dipakainya cuma 23, jadi
sebabnya bukan kekurangan ruang — menyalin memang jawaban termurah,
dan tidak ada yang menolaknya.

`enforce_h1_shape` mengerjakan dua langkah:

1. Tanda pisah gaya judul dibuang, **emoji termasuk** — emoji memang
   salah satu tanda pisah yang boleh terpilih untuk judul, jadi H1
   yang menyalin judul membawanya serta.
2. Kalau sesudah itu H1 tidak memuat apa pun di luar nama situs dan
   keyword, ia disusun ulang jadi frasa posisional dalam bahasa
   halaman: `Slot Gacor di WAYANGPLAY`.

Langkah kedua **tidak mengarang apa pun** — dua token yang sama,
disusun sebagai frasa yang wajar dibaca, bukan sebagai label. H1 yang
memang punya isi sendiri tidak disentuh selain pembuangan tanda pisah.

Heading di dalam halaman ikut dirapikan dengan cara yang sama, tapi
yang dikerjakan hanya **pembuangan**: tanda pisah dibuang, dan kalau
headingnya tidak memuat apa pun di luar nama situs dan keyword,
sebutan nama situsnya ikut dibuang. Judul bagian tidak perlu menyebut
nama situs — judul halaman sudah menyebutnya.

## Kosakata Remah Navigasi

> **Dibalik 21 Agustus 2026 untuk halaman situs slot.** Bagian
> berikutnya — "Nama Situs Tidak Masuk Remah Navigasi" — masih
> berlaku penuh untuk bidang `generic`, tapi **tidak lagi** untuk
> bidang `gambling`. Jangan menyatukan keduanya lagi.

Remah yang terbit di halaman BATARATOTO:

```
Beranda > Slot Online > Pengalaman Bermain > Slot Gacor > Slot Gacor
```

Pengguna menolaknya, dan yang ditolak bukan cuma tingkat kembarnya:
"pada bagian breadcrumble jangan melenceng dari pembahasan situs slot;
contohnya *lihat hasil, verifikasi akun, tutup sesi, main tanpa batas*
saya tidak suka". Bentuk yang dia mau disebutkan sendiri:

```
brand            situs slot        rtp slot        slot online
brand login      situs brand       agen slot       link login
rtp brand        brand link        link brand      alternatif brand
                                                   alternatif slot
```

Enam dari tiga belas bentuk itu **memuat nama situs**, jadi aturan
lama yang mencabut nama dari tiap tingkat menghapus separuh daftar
yang baru saja diminta. Karena itu pencabutan nama sekarang dilewati
untuk bidang `gambling`.

Yang menggantikannya: **daftar kata yang boleh berdiri di remah**
(`BREADCRUMB_WORDS`). Satu tingkat lolos hanya kalau **seluruh**
katanya ada di daftar itu, di keyword, atau di nama brand. Satu kata
di luar daftar sudah cukup menolak — dan itu memang maksudnya, karena
justru "Pengalaman" yang membuat "Pengalaman Bermain" bukan jalur.

Tingkat yang tertolak **ditukar**, bukan dibuang, dari
`BREADCRUMB_SHAPES` yang urut dari umum ke khusus. Jadi remah tidak
pernah menyusut jadi "Beranda" saja:

| yang ditulis model | yang terbit |
| --- | --- |
| Beranda > Slot Online > Pengalaman Bermain > Slot Gacor | Beranda > Slot Online > Situs Slot > Slot Gacor |
| Beranda > Lihat Hasil > Verifikasi Akun > Tutup Sesi | Beranda > Situs Slot > Slot Online > RTP Slot |
| Beranda > Main Tanpa Batas | Beranda > Situs Slot |
| Beranda > Situs Slot > RTP BATARATOTO | tidak berubah |

Ditegakkan di Python, bukan di prompt. Aturan remah sudah disebutkan
di prompt sejak lama dan yang terbit tetap "Pengalaman Bermain": model
4B menulis remah seperti menulis judul bagian, karena keduanya
sama-sama frasa pendek dan cuma satu di antaranya yang punya aturan
bentuk. Diuji di `tests/test_breadcrumb_vocab.py`.

## Nama Situs Tidak Masuk Remah Navigasi

> Berlaku untuk bidang `generic`. Untuk halaman situs slot, lihat
> bagian di atas.

Aturan promptnya sudah ada sejak lama, dan yang memeriksanya cuma
menyamakan seluruh teks tingkat dengan nama brandnya. Tingkat yang
**memuat** nama itu lewat:

```
Beranda > Slot Gacor > SIAM123 Slot
```

Tiga hal ditegakkan sekarang, semuanya di `normalize_breadcrumb`:

1. Nama situs dicabut dari **dalam** tiap tingkat, bukan dibandingkan
   dengan seluruhnya.
2. Tingkat yang kosakatanya termuat di tingkat **sebelum** dirinya
   dibuang — jalur yang bergerak mundur. Termuat di tingkat
   *sesudahnya* justru bentuk yang benar: "Slot" → "Slot Gacor" →
   "Main Slot Gacor" bergerak dari umum ke khusus.
3. Tingkat terakhir dipastikan menyatakan **halaman ini**, bukan
   kategorinya — kalau kosakatanya tidak menambah apa pun di luar
   keyword, daun dari H1 ditambahkan.

## Bahan Cadangan Harus Setopik

Slot FAQ yang tidak dijawab model ditambal dari pertanyaan yang
dipanen dari halaman pertama Google. Selama bahan itu tidak disaring,
yang tertambal bisa pertanyaan milik situs yang sama sekali lain -
terukur, halaman slot terbit dengan:

```
Seberapa Pancasila Dirimu?
```

Pertanyaan milik situs lembaga negara, di halaman judi.

Aturannya **sudah** ada di prompt sejak lama — *"Pertanyaan yang tidak
nyambung dengan topik halaman ini lebih baik tidak ditulis sama
sekali"* — dan itu justru yang membuat kejadiannya membingungkan.
Aturan prompt cuma mengikat MODEL. Yang menaruh kalimat ini ke halaman
bukan model melainkan **penambal di Python**, yang tidak pernah membaca
aturan itu.

`on_topic_questions()` menyaringnya sebelum bahan itu dipakai.
Syaratnya sengaja seringan mungkin: cukup satu kata isi yang sama
dengan keyword. Yang dicari bukan pertanyaan yang bagus melainkan
pertanyaan yang setidaknya membicarakan hal yang sama — sisanya sudah
diurus penambal kartu FAQ, yang punya bank tanya-jawab berpasangan.

Kalau tidak ada satu pun yang lolos, yang dikembalikan daftar kosong,
dan itu jawaban yang benar: slot kosong ditambal bank berpasangan;
slot yang ditambal pertanyaan asing terbit apa adanya.

## Dua Paragraf Yang Membuka Sama

`near_twins` punya tiga ukuran — sama persis, yang satu pembuka yang
lain, dan kemiripan huruf secara keseluruhan. Ada satu bentuk yang
lolos dari ketiganya, dan ia terbit berdampingan di satu halaman:

```
X7GAMING88 menyediakan akses langsung ke slot online tanpa perlu
verifikasi tambahan. ...
X7GAMING88 menyediakan akses langsung ke slot online setelah proses
daftar. ...
```

Tujuh kata pertamanya sama persis. Yang satu bukan pembuka yang lain
karena keduanya diteruskan berbeda, dan kemiripan hurufnya secara
keseluruhan tidak sampai ke ambang 0,86 — tapi pembaca halaman membaca
dua paragraf yang mengatakan hal yang sama.

`SHARED_OPENING_WORDS = 7` menutupnya. Angkanya diukur dari yang
benar-benar terbit; ditaruh lebih rendah, paragraf yang dibuka nama
situs plus satu kata kerja ("X7GAMING88 menyediakan") ikut terbuang,
dan pengulangan sependek itu memang wajar.

Gejala yang dilaporkan pertama kali bukan "paragraf kembar" melainkan
**densitas keyword terlalu tinggi** — dua paragraf yang sama
menyebutkan keyword dua kali untuk satu gagasan. Ukurannya benar; yang
ditunjuknya bukan penyebabnya.

## Jebakan `_by_old`: Mengubah Isi Tanpa Mengubah Peta

Ini jebakan paling mahal yang ditemukan sesi 19 Agustus 2026, dan
bentuknya perlu diingat karena ia **melapor berhasil sambil tidak
mengerjakan apa pun**.

`build_edits` tidak membagikan isi peran berdaftar urut dokumen begitu
saja. Untuk peran yang artinya harus dipertahankan, ia memakai
`content["_by_old"]` — peta *teks lama → teks baru* yang disusun jauh
lebih awal di `fit_content_to_spec`. Peta itu yang menentukan apa yang
benar-benar terpasang di slot.

Akibatnya, kode yang mengubah `content["heading"]` **sesudah** peta itu
tersusun mengubah daftar yang tidak dibaca siapa pun:

```
log     : "1 heading berbunyi sama dengan H1 dan diganti dari bank"
halaman : <h1>WAYANGPLAY Temukan Slot Gacor Terbaik</h1>
          <h2>WAYANGPLAY Temukan Slot Gacor Terbaik</h2>
```

Tiga kali berturut-turut cacat yang sama terbit dengan kode
perbaikannya menyala. Diperiksa di `content`, semuanya benar; yang
salah cuma kelihatan dari halamannya.

**Kalau menyentuh isi peran berdaftar sesudah `fit_content_to_spec`,
perbarui `content["_by_old"][role]` juga.** Dan ujinya harus sampai
HTML — uji yang berhenti di dict akan lulus untuk halaman yang salah.

Dua penjaga dipasang supaya bentuk kegagalan ini tidak terulang:

1. Uji `F6` di suite menjalankan `generate_template_content` penuh
   dengan model diganti stub, lalu meneruskan hasilnya ke
   `fill_template` dan memeriksa **HTML**-nya. Deterministik, dan
   selesai dalam sepersekian detik — bukan dua puluh menit.
2. Harness E2E memeriksa modul yang BENAR-BENAR dimuat prosesnya
   sebelum satu job pun berangkat. Kalau penegakan yang diharapkan
   tidak ada di sumber yang dimuat, run berhenti. Sebelumnya tidak ada
   apa pun yang membedakan "kode terpasang" dari "proses memuat versi
   lama", dan dua puluh menit per percobaan habis untuk menebak.

## Penyapu Kebocoran Perintah

`generators/leak_guard.py` menangkap kalimat yang menyalin ISI
PERINTAH ke dalam teks yang terbit. Terukur pada halaman yang terbit:

    "... Tidak ada penundaan, tidak ada kata 'mungkin'."

Kalimat kedua bukan tentang brandnya melainkan tentang aturan yang
baru dibaca model — `brand_confidence_rules` melarang kata "mungkin",
dan model menuliskan larangannya alih-alih mematuhinya.

**Pembandingnya prompt yang benar-benar dikirim, bukan daftar hitam.**
Daftar hitam cuma menangkap contoh yang sudah pernah terjadi;
kebocoran berikutnya berbunyi lain. `instruction_index(prompt)`
menyusun bahan pembanding dari blok perintah di prompt itu sendiri,
jadi pendeteksinya ikut berubah setiap kali aturannya diubah — tanpa
daftar kedua yang harus diingat.

Empat sinyal:

| | Sinyal | Contoh yang tertangkap |
|---|---|---|
| A | mengutip istilah yang dikutip perintah | `... kata 'mungkin'` |
| B | metabahasa — bicara *tentang* kata | `tanpa frasa "konon"` |
| C | menyalin ≥55% tiga-kata dari baris perintah | `Tulis seperti orang yang mengurus situs ini sendiri...` |
| D | berbentuk perintah | `JANGAN ...`, `salah :`, `maksimal 70 karakter` |

Tiga hal yang menjaganya dari salah tangkap, semuanya lahir dari
kalimat wajar yang sempat dibuang saat kalibrasi:

1. **Metabahasa saja tidak cukup** — istilahnya harus berasal dari
   perintah. Tanpa syarat ini, *"Istilah 'gacor' dipakai pemain untuk
   menyebut game yang lagi ramai"* — kalimat yang justru berguna —
   ikut dibuang.
2. **`JANGAN` harus berhuruf besar.** Prompt menulisnya kapital;
   *"Jangan ragu hubungi tim kami"* adalah idiom, bukan kebocoran.
3. **Baris sambungan prompt ikut dibaca.** Kata terlarang berdiri di
   baris kedua sebuah butir, dan tanpa menyambungnya tidak satu pun
   masuk ke daftar kutipan — sinyal terkuat jadi mati.

Kata tunggal seperti "mungkin", "aturan", "SEO", "keyword", dan
"format" **tidak pernah** memicu apa pun sendirian; diuji dengan 22
kalimat jualan wajar yang memuatnya.

---

## Menambal Slot Yang Kependekan Sesudah Penyapuan

Penyapu klaim dan penyapu kebocoran membuang KALIMAT, dan keduanya
berjalan sesudah semua giliran selesai — sedangkan mesin penambal
teks pendek berjalan **per giliran**. Akibatnya paragraf yang
kehilangan kalimatnya di sini tidak pernah bertemu lagi dengan yang
bisa memintanya ulang, dan terbit lebih pendek daripada jatah
slotnya.

`repair_short_slots()` di `generators/content_planner.py` menutup
lubang itu. Yang diminta ulang **hanya slot yang berlubang**, lewat
`gap_spec` — bukan seluruh halaman.

- Klaim yang dibuang **tidak bisa kembali**: jawaban tambalan lewat
  kedua penyapu lagi sebelum dipasang.
- Kalimat lama **tidak digandakan**: penolak kembar yang sudah ada
  dipakai lewat `seen`.
- Topik, bahasa, nada, jenis halaman, pembaca, brand, dan keyword
  ikut sendiri karena promptnya disusun ulang lewat `minta()`.
- `REPAIR_RETRIES = 2`, dan putaran berhenti lebih awal begitu tidak
  ada lubang lagi atau begitu satu putaran tidak memperbaiki apa pun.
- Model yang mati saat menambal tidak menggagalkan halaman; sebabnya
  dicatat ke log job.
- Slot yang tetap kependekan dilaporkan apa adanya di log, bukan
  diisi paksa.

### Panjang teks yang ditegakkan

Plafon di JSON Schema sengaja dilonggarkan 30% supaya grammar tidak
memenggal kata di tengah, jadi jawaban model boleh melewati batas
yang diminta — dan yang memotongnya kembali harus ada. Tiga lapis,
urut:

1. `enforce_title_shape` merapikan bentuk judul (bisa memendekkan).
2. `potong()` memotong ke plafon **di batas kalimat**, dengan lantai
   ikut dioper. Tanpa lantai, mundur ke kalimat utuh jatuh jauh di
   bawah jatahnya — terukur: deskripsi 181 karakter mundur ke 133
   untuk plafon 180 dan lantai 140, memperbaiki kelebihan satu
   karakter dengan kekurangan tujuh.
3. `length_problems()` memeriksa lantai **sesudah** semua penyapu,
   dan yang masih kurang memicu satu permintaan ulang.

Permintaan ulangnya **menyebut apa yang salah**. Dulu percobaan kedua
mengirim prompt yang sama persis dengan yang pertama, jadi yang
dikerjakannya cuma mengocok ulang dadu — cukup untuk kesalahan yang
kebetulan, tidak untuk kekurangan yang sistematis. Terukur 14 Agustus
2026: model menulis judul 43 karakter untuk lantai 50, diminta ulang
tanpa diberi tahu apa yang salah, dan menjawab pendek lagi.

Blok pendek ditempelkan di ujung permintaan kedua:

```
# PERBAIKAN JAWABAN SEBELUMNYA

- title: kemarin 43 karakter, kurang 7. Tulis ulang sepanjang 50-70
  karakter. Tambah keterangan yang benar-benar berisi, jangan
  menambal dengan mengulang kata yang sudah ada.
```

Kekurangannya disebut dalam **karakter yang kurang**, bukan cuma
rentang yang diminta: rentangnya sudah tertulis di prompt pertama dan
tetap dilanggar, jadi yang belum pernah dikatakan adalah seberapa
jauh melesetnya. Isinya disusun dari hasil pemeriksaan, bukan ditulis
tangan per jenis isi, jadi jenis isi yang ditambahkan nanti ikut
terlayani tanpa disentuh. Blok ini ikut masuk `instruction_index()`,
karena baris perintah yang paling segar di ingatan model justru yang
paling mungkin disalin balik ke jawaban.

---

## Jalur Tanpa Template Sudah Dibuang

Sampai 19 Agustus 2026, `--template` yang dikosongkan membuat NEIIU
merakit halamannya sendiri dari pustaka blok: navbar, popup, sepasang
tombol besar, kartu rating, testimoni, pil topik, footer bertingkat,
dan bilah mengambang. Warna, font, dan sudut lengkungnya ditiru dari
halaman acuan lewat `--design-ref`.

Seluruh jalur itu dihapus, beserta modulnya:
`generators/landing_generator.py`, `generators/theme.py`, dan
`generators/inspiration.py`, ditambah `generate_content_plan()`,
`normalize_plan()`, dan `build_content_plan_prompt()`. Opsi
`--design-ref`, `--color`, `--plain`, dan `--kit-from-ref` ikut
hilang, begitu juga kolom "URL acuan gaya" di halaman web.

Alasannya satu: itu generator kedua yang hidup di dalam yang pertama.
Selama ia ada, "halaman ini strukturnya persis template yang kamu
pilih" cuma benar untuk separuh jalur, dan separuh yang lain
menerbitkan halaman yang layoutnya ditentukan program - persis yang
tidak boleh dilakukan.

Yang tersisa satu jalur: template pengguna diisi di tempatnya. Lihat
"Template Wajib" di atas.


### Ulasan dan penilaian

Slot ulasan di template diisi teks baru, dan teks yang sama itu juga
yang masuk ke `Product` + `AggregateRating` + `Review` di JSON-LD. `reviewCount` dan `ratingValue` dihitung dari ulasan
yang benar-benar terbit di halaman, bukan diisi angka besar:
structured data yang melaporkan ribuan ulasan sementara halamannya
menampilkan empat adalah pelanggaran pedoman Google yang bisa
membuat seluruh rich result situs dicabut.

Tanggal ulasan tidak pernah diminta ke model, karena model kecil
rutin menulis tanggal yang tidak ada di kalender atau jatuh di masa
depan. NEIIU memasangnya sendiri, mundur dari hari ini, dalam dua
bentuk: bentuk baca yang mengikuti kalender zona (tahun Buddha untuk
zona Thailand) dan bentuk ISO masehi untuk mesin.

### Versi AMP kalau template AMP tidak diunggah

Template AMP boleh dikosongkan. Kalau dikosongkan, berkas AMP-nya
dirakit dari ISI YANG SAMA dengan landingnya - bukan dari permintaan
kedua ke model - sehingga title, deskripsi, dan H1 kedua berkas
tetap sama persis. Canonical-nya mengikuti canonical template
landing; kalau template tidak punya canonical, dipakai alamat
relatif supaya tidak ada satu domain pun yang dikarang.

Dua blok berbeda di berkas AMP rakitan ini, dan bedanya bukan
kosmetik:

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
| paragraf **di bagian yang judulnya ikut diganti** | paragraf di bagian yang judulnya dibiarkan |
| blok artikel yang dirakit NEIIU | |

Batas sebuah bagian ditentukan struktur judul, bukan ambang jarak.
Isi sebuah bagian ikut ditulis ulang kalau **salah satu** dari dua
hal berlaku pada judul `h2`–`h6` yang mengepalainya:

1. **Judulnya menyebut nama brand lama.**
2. **Judulnya sendiri ikut diganti NEIIU**, yaitu judul itu jadi slot
   `heading`.

`h1` sengaja tidak ikut membatasi — ia menamai seluruh halaman, bukan
satu bagian, dan memakainya membuat isi milik pemilik template ikut
terhitung. Nama brand lamanya boleh dikosongkan; kalau begitu ia
ditebak dari potongan judul sebelum tanda pisah pertama.

Syarat kedua ditambahkan 21 Agustus 2026, dan yang ditutupnya halaman
yang isinya bertengkar dengan judulnya sendiri. Di template 298 milik
pengguna, judul kartu "Transparansi informasi" berganti teks baru
sementara paragraf tepat di bawahnya bertahan apa adanya, karena judul
itu tidak menyebut "OSB99". Delapan paragraf bernasib sama di berkas
itu, dan **lima di antaranya masih bercerita tentang deposit QRIS** —
keyword pemilik template sebelumnya — di halaman yang seluruh judulnya
sudah membicarakan keyword yang lain sama sekali.

Yang dijaga syarat kedua sama dengan yang dijaga syarat pertama:
tulisan milik pemilik template. Bagian yang judulnya **dibiarkan** —
ditandai `data-neiiu-skip`, atau memang tidak dikenali jadi slot —
tetap membawa isinya sendiri. Diukur di template 275, yang memuat 12
paragraf salinan produk toko: jumlah slot yang terisi tidak berubah
satu pun sesudah syarat kedua dipasang (156 sebelum, 156 sesudah),
sementara template 298 naik dari 99 ke 107.

Diuji di `tests/test_block_scope.py`, dua arah sekaligus.

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

Judul kartu keunggulan dikenali dengan cara yang sama — teks pendek
yang berdiri tepat sebelum sebuah paragraf, sekedalaman dengannya —
dan justru karena itu ia punya satu pengecualian yang harus disebut:
**kata yang berdiri DI DALAM sebuah judul tidak pernah jadi judul
kartu**, walau tagnya sendiri bukan tag judul. Berkas AMP template 298
menulis judul besarnya begini:

```html
<h1 class="hero-title">OSB99 <em>Login</em></h1>
<p class="lead">OSB99 memberikan kemudahan deposit QRIS ...</p>
```

"Login" memenuhi ketiga syarat judul kartu, lalu diisi satu kalimat
judul kartu utuh — dan judul besar halaman terbit berbunyi `NEWBRAND
<em>kalimat sepanjang satu baris</em>`. Karena H1 berkas AMP jadi
berbeda dari H1 landing, pemeriksa akhir menahan **seluruh run**, jadi
template itu tidak bisa dipakai sama sekali sampai pengecualiannya
dipasang. Kata di dalam judul adalah bagian dari judul itu: ia tetap
kebagian penggantian nama brand dan penyamaan teks kembar, seperti
bagian judul lainnya. Diuji di `tests/test_card_title.py`.

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

### Tiap jawaban FAQ dipasangkan ke pertanyaan yang berdiri di atasnya

Giliran terpisah di bawah menyelesaikan separuh masalahnya: jawaban
ke-N ditulis sambil melihat pertanyaan ke-N. Yang tersisa separuh
lagi, dan ia terbit lagi 21 Agustus 2026 di halaman BATARATOTO:

```
Q: Mengapa BATARATOTO Menjadi Situs Slot Pilihan Banyak Pemain?
A: Setelah kamu masuk ke akun, kamu bisa memilih jenis slot ...
```

Pemasangan lewat NOMOR benar hanya selama kedua daftarnya sama panjang
dan sejajar. Di template 488 keduanya tidak sejajar sama sekali, dan
sebabnya dua hal yang berdiri sendiri-sendiri:

1. **Judul bagian toko terbaca sebagai pertanyaan.** Seluruh blok
   keterangan produk berdiri di dalam
   `<div class="m-design-product-info-and-faqs">`, jadi penanda FAQ
   mengenainya semua — termasuk `<h4>Product Quality</h4>`, yang tidak
   bertanya apa pun.
2. **Pertanyaan yang sungguhan tidak pernah jadi slot.** Keduanya
   ditulis sebagai akordeon di dalam `<button>`, jadi ia teks template
   yang dibiarkan — sementara jawaban di bawahnya ditulis ulang penuh.

Hasilnya satu "pertanyaan" palsu dan tiga "jawaban". Model diberi
daftar berisi satu pertanyaan lalu diminta tiga jawaban.

`pair_faq_cards` di `generators/template_slots.py` menutup keduanya.
Untuk tiap jawaban, urut dokumen:

| langkah | yang dikerjakan |
| --- | --- |
| 1 | Cari teks berbentuk pertanyaan di atasnya — paling jauh 4 simpul teks dan 1.400 byte, dan berhenti kalau menabrak judul yang bukan pertanyaan |
| 2 | Teks itu **diangkat** jadi `faq_question` kalau belum berperan, jadi tanya dan jawabnya ditulis ulang berpasangan |
| 3 | Bunyi pertanyaannya dicatat di `asks`, dibawa sampai ke prompt lewat `spec["faq_answer"]["asks"]` |
| 4 | Jawaban yang **tidak punya** pertanyaan di atasnya diturunkan jadi paragraf biasa |

Batas jarak di langkah 1 bukan hiasan. Pasangan sungguhan di template
488 berjarak 528 dan 485 byte; tanpa batas, paragraf mutu produk
menyeberang 2.192 byte ke atas dan menempel ke pesan pencarian kosong
"Not what you're looking for?" — satu-satunya teks berbentuk
pertanyaan di sekitarnya.

Teks di dalam `<button>` boleh diangkat, dan itu bukan kelonggaran
melainkan bentuk yang lazim: akordeon FAQ menulis pertanyaannya
sebagai tombol yang membuka jawabannya. Yang membedakannya dari label
tombol biasa bunyi teksnya sendiri — label tombol tidak bertanya
apa-apa.

Terukur di template 488: dari 1 pertanyaan + 3 jawaban jadi **2
pertanyaan + 2 jawaban yang berpasangan benar**, dan satu paragraf
toko dikembalikan jadi paragraf. Diuji di `tests/test_faq_pairing.py`.

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
| meta description | 140–180 karakter | 160–200 |

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

- `knowledge/gaya_title_deskripsi.txt` disaring ke rentang 140–180
  sebelum dikirim sebagai contoh. Diukur 13 Agustus 2026 sesudah
  rentangnya turun dan sesudah `PERCENT_FILTER` dipasang: dari 102
  baris yang lolos saringan, 4 di bawah lantai dan 58 di atas plafon;
  40 yang tersisa masih lima kali lebih banyak daripada yang dikirim
  per run.
- `knowledge/gaya_title.txt` ikut disaring ke 50–70, dan dari 116
  baris yang lolos saringan, 49 masuk rentang. Yang di luar rentang
  masih bisa ikut lewat jalan mundur di `pick_style_examples`, yang
  menambah contoh terdekat supaya daftarnya tidak pernah kosong.
- Meta description masuk `SENTENCE_ROLES`, dan `trim_to_sentence`
  menerima lantai. Di 140 karakter sebuah deskripsi muat satu kalimat
  dan potongan di batas kata praktis tidak kelihatan; di 180 ia muat
  dua, dan mundur ke titik terakhir bisa jatuh di bawah lantai yang
  jadi alasan teks itu ditulis sepanjang itu.

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

### Gerbang terakhir: `generators/final_verify.py`

Sebelum satu berkas pun ditulis ke disk, kedua berkas yang akan
terbit diperiksa sekali lagi — dan yang diperiksa **berkasnya**,
bukan kamus isi milik Python. Bedanya bukan teori: pemetaan slot,
pemotongan lebar, penukaran nama brand, dan penyisipan schema
semuanya berdiri di antara kamus itu dan berkas yang jadi.

Yang **menahan terbit** (halaman tidak ditulis, job gagal, token
dikembalikan):

| Temuan | Kenapa fatal |
| --- | --- |
| Bagian di luar slot berubah | Template itu milik pengguna |
| Landing dan AMP beda title/deskripsi/H1 | Keduanya dari satu isi |
| Nama brand salah ketik, atau hilang sama sekali | |
| Penanda isian belum diganti (`{{ }}`, lorem ipsum, TODO) | |
| Klaim karangan atau token sampah | |
| Bahasa halaman tidak sesuai zonanya | |
| JSON-LD bukan JSON yang sah | |
| Title, deskripsi, atau paragraf kosong | |
| `<html>` lebih dari satu, atau tidak ditutup | |

Yang **cuma dicatat** (halaman tetap terbit, cacatnya masuk log):
panjang title atau deskripsi di luar rentang, deskripsi yang hampir
menyalin title, jumlah H1 bukan satu, dan kalimat yang sama berdiri
di dua peran berbeda.

Temuan yang teksnya memang **sudah ada di template** tidak pernah
menahan terbit. Itu bukan karangan generator ini, dan bagian itu
tidak pernah disentuh.

Pemeriksaan wilayah beku dijalankan DUA KALI: sekali di dalam
`fill_template()` atas hasil pengisian, sekali lagi di sini atas
teks yang persis akan mendarat di disk. Rentang isian dikembalikan
`fill_template()` lewat kunci `ranges`.

### Pengaman otomatis

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
4. **Setiap** sebutan nama situs dicabut dari bagian janji, bukan
   cuma yang pertama (`strip_brand_mentions()`). Nama situs sudah
   ditempelkan di kepala, jadi sebutan yang tertinggal di badan judul
   adalah sebutan kedua. Terukur 14 Agustus 2026, yang terbit:

   ```
   PALAPAX 💰 Slot Gacor Hari Ini di PALAPAX, Gacor dan Dibayar
   ```

   Enam puluh delapan karakter, dua puluh satu di antaranya dipakai
   menulis nama yang sama dua kali — di jatah yang cuma tujuh puluh.
   Ikut dibereskan di situ: tanda pisah yang tertinggal waktu nama di
   depannya dicabut (dulu terbit `PALAPAX 💰 💰 Slot ...`, karena
   emoji tidak ada di `EDGE_MARKS`), dan koma yang menggantung
   berspasi (`Hari Ini , Gacor`).

Khusus teks Thai ada satu langkah lagi, `drop_thai_tail()` di
`utils/text.py`. Bahasa Thai tidak memberi spasi antar kata, jadi
`ร้านกาแฟออนไลน์จาก` satu token buat Python padahal tiga kata buat
yang membacanya — dan waktu nama situs sesudahnya dicabut, yang
menggantung cuma suku terakhirnya. Seluruh aturan `DANGLING_WORDS`
bekerja per token, jadi tidak satu pun menyentuhnya, dan judul terbit
sebagai `LINGUAKU > ร้านกาแฟออนไลน์จาก ใช้งานง่าย`: "dari" yang tidak
pernah mengatakan dari apa.

Daftar kata sambungnya sengaja pendek, dan dijalankan **hanya** di
tempat pencabutan benar-benar terjadi. `ตาม` dan `ด้วย` sengaja TIDAK
masuk: keduanya hidup di dalam kata yang sah (`ติดตาม`, `พร้อมด้วย`),
dan memangkasnya berarti merusak teks yang benar.

`ที่` punya perlakuan sendiri, dan alasannya diukur 16 Agustus 2026.
Judul zona Thailand yang terbit:

```
SIAM123: เปิดบัญชีใหม่ที่ เพื่อเข้าร่วมการเล่นสล็อตออนไลน์
```

Yang ditulis model `เปิดบัญชีใหม่ที่ SIAM123 เพื่อ…` — "buka akun baru
**di** SIAM123 untuk…". Namanya dipindahkan ke kepala, dan `ที่` yang
tadinya menerangkan nama itu tertinggal tanpa apa-apa di belakangnya.

`ที่` tetap tidak boleh masuk daftar umum, karena di ujung teks yang
kebetulan terpotong ia hampir selalu bagian dari kata lain (`ทุกที่`
= di mana saja, `สถานที่` = tempat). Yang membedakan **titik
pencabutan**: kata yang berdiri persis sebelum nama situs dan
berakhiran `ที่` adalah kata depan yang menerangkan nama itu —
`เล่นได้ทุกที่ SIAM123` bukan kalimat Thai yang wajar.

Jadi `drop_thai_tail()` punya parameter `di_pencabutan`, bawaannya
`False`. `finish_clause()` memanggilnya seperti dulu dan perilakunya
tidak bergeser sedikit pun; `strip_brand_mentions()` memanggilnya
dengan `True`, dan cuma di situ `THAI_DANGLING_AT_CUT` berlaku —
dijaga `THAI_DANGLING_SAFE` yang isinya kata sah yang bisa berdiri
persis sebelum nama situs.

Diukur pada tujuh kasus: brand di awal, di tengah, di akhir, diikuti
partikel, dan tiga kontrol (`ทุกที่`, `สถานที่`, `ติดตาม`). Tidak satu
pun kontrol tersentuh, dan `drop_thai_tail()` sendiri terbukti **tidak**
terlalu agresif — yang kurang cuma satu partikel di satu tempat
panggil.

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

### Kenapa bentuknya ditegakkan DUA kali

`ensure_template_identity()` jalan **per giliran**, di dalam putaran
yang menulis isi. Empat langkah jalan **sesudah giliran terakhir**:

1. `scrub_content()` — membuang klaim yang tidak bisa dibuktikan
2. `scrub_leaks()` — membuang kalimat yang menyalin isi perintah
3. `repair_short_slots()` — menambal slot yang jadi kependekan
4. `repair_short_slots()` lagi — membedakan slot yang bunyinya kembar

Tidak satu pun dari keempatnya menegakkan bentuk judul, dan yang masuk
lewat penambalan adalah teks model yang **mentah** — nama situs masih
di tengah kalimat, atau tidak ada sama sekali.

Terukur end-to-end 16 Agustus 2026, job 93, template `timah33`:

```
log     : Menambal sesudah penyapuan: title 1 slot (percobaan 1/2)
          Menambal sesudah penyapuan: title 1 slot (percobaan 2/2)
terbit  : "Cari Slot Gacor dengan Data Terbaru"
panjang : 35 karakter (lantainya 50)
nama situs: TIDAK ADA
```

Bentuk judul itu keputusan pengguna 10 Agustus 2026, dan ditegakkan di
Python justru karena prompt tidak bisa diandalkan menegakkannya — lalu
satu-satunya jalur yang melewatinya adalah jalur yang dipakai persis
waktu judulnya paling bermasalah. Cacat ini **tidak bisa** terlihat
dari uji per-fungsi: tiap fungsinya benar sendiri-sendiri, yang salah
urutan pemanggilannya.

Jadi `ensure_template_identity()` dipanggil sekali lagi di ujung, atas
isi akhir, **hanya untuk `title`**. Aman dijalankan dua kali karena
`enforce_title_shape()` idempoten — diuji tiga kali berturut-turut atas
lima bentuk judul yang berbeda, hasilnya tidak bergeser sesudah
panggilan pertama. Peran lain tidak ikut dilewatkan sama sekali.

Yang menangkapnya `check_head_pair()` di `generators/seo_validator.py`,
dan itu memang gunanya: ia satu-satunya pemeriksa yang membaca halaman
**jadi**, bukan isi sebelum dipasang.

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

## Menjalankan Uji

Dua tingkat, dan keduanya perlu.

### 1. Suite cepat (tanpa AI, tanpa jaringan)

```powershell
python -m unittest discover -s tests -t .
```

Selesai dalam hitungan detik. Isinya:

| Berkas | Yang dijaga |
| --- | --- |
| `tests/test_template_integrity.py` | Wilayah beku byte-identik, teks pemilik template tersapu, jumlah bagian tidak berubah |
| `tests/test_final_verify.py` | Gerbang akhir menahan yang salah dan hanya yang salah |
| `tests/test_repetition.py` | Kalimat yang sama tidak berdiri di dua peran; judul dan deskripsi yang jatuh di bawah lantainya diminta ulang |
| `tests/test_claim_guard.py` | Angka di ujung nama brand bukan klaim; klaim sungguhan tetap ditangkap |
| `tests/test_text_trim.py` | Teks yang dipotong tetap kalimat, bukan kalimat yang dipenggal |
| `tests/test_amp_pairing.py` | Landing dan AMP dari satu isi, termasuk saat template AMP tidak diunggah |
| `tests/test_h1_shape.py` | H1 kalimat pembuka halaman, bukan salinan judul |
| `tests/test_template_contract.py` | Template wajib, pustaka template, penolakan yang bisa dibaca |

Template jebakannya ada di `tests/fixtures/__init__.py`: blok iklan,
handler `onclick`, tautan sponsor, gambar banner, iframe iklan, CSS
sebaris, JS sebaris, dan skrip vendor - semuanya harus terbawa apa
adanya ke berkas jadi.

### 2. Generate nyata (model sungguhan, ~20-40 menit per case)

```powershell
python -m tests.e2e_generator A B C D
python -m tests.e2e_generator E --template 298
```

Berjalan lewat endpoint yang sama dengan yang dipakai antarmuka -
`POST /api/neiiu/jobs` - jadi yang diuji benar-benar pipeline
produksi, bukan tiruannya. Datanya terisolasi: pengguna sendiri,
template sendiri, ruang ingatan `qa`, dan semuanya dihapus di akhir.
Berkas hasilnya sengaja TIDAK dihapus, karena itulah barang bukti
yang diaudit sesudahnya.

Case bawaan A-D memakai template jebakan; `--template <id>` memakai
template nyata milik pengguna 1, dan di situ pemeriksaan wilayah
bekunya diturunkan dari templatenya sendiri (skrip, handler, iframe,
gambar, tautan keluar, kelas, id) - bukan dari daftar yang ditulis
tangan.


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

1. Ganti domainnya:
   - **Halaman dari template.** Alamat di berkas hasil adalah alamat
     yang tertulis di template — `canonical`, `href`, `@id`, `url`,
     dan alamat di BreadcrumbList. NEIIU tidak menyentuh satu pun,
     jadi tidak ada domain karangan yang perlu diburu. Cari-ganti
     domain lama ke domain sendiri, sekali, di kedua berkas.
   - **Halaman yang dirakit dari nol.** Ganti `SITE_BASE_URL` di
     `.env` ke domain asli lalu jalankan ulang; canonical, sitemap,
     dan JSON-LD ikut memakai nilai itu.
2. Cek `amp/index.html` di validator resmi AMP.
3. Baca ulang isi halamannya. Konten hasil model tetap perlu
   diperiksa manusia sebelum terbit — cek klaim yang salah,
   pengulangan, dan hal yang tidak sesuai aturan platform atau
   aturan yang berlaku di tempat halaman itu diterbitkan.
4. Daftarkan `sitemap.xml` di Google Search Console.
