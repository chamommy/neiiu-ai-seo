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
```

Tambahkan `-u` di depan (`python -u neiiu.py ...`) kalau outputnya
mau di-pipe ke file dan tetap ingin melihat progres.

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
