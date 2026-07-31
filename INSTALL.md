# NEIIU AI v1 Patch

Patch ini menambahkan:

- Tema hitam + aksen hijau
- Logo NEIIU AI
- Login wajib
- Admin membuat user
- Saldo token per user
- Biaya 1 token per pesan
- New chat
- History chat per user
- Normal Mode dan SEO Expert
- Provider/model disembunyikan dari tampilan user

## 1. Copy file

Extract isi ZIP ke root project `C:\Users\USER\AI`.

Saat diminta mengganti `web_app.py`, pilih **Replace**.

Folder lama `database/reports` tidak dihapus.

## 2. Install dependensi

Aktifkan `.venv`, lalu:

```bash
pip install -r requirements-neiiu-v1.txt
pip freeze > requirements.txt
```

## 3. Buat session secret

Di CMD sebelum menjalankan server:

```cmd
set NEIIU_SESSION_SECRET=ganti-dengan-random-string-yang-panjang
```

Untuk development lokal, aplikasi tetap dapat berjalan tanpa command ini,
tetapi secret default tidak aman untuk deployment publik.

## 4. Buat admin pertama

```bash
python init_admin.py
```

Masukkan username dan password admin.

## 5. Jalankan

```bash
python -m uvicorn web_app:app --reload
```

Buka:

```text
http://127.0.0.1:8000
```

## 6. Buat user

Login sebagai admin, buka menu **Admin**, lalu:

- Masukkan username
- Password
- Role
- Jumlah token
- Klik Create user

## Token

Sistem memakai aturan:

```text
1 pesan user = 1 token
```

Jika AI gagal menjawab, token otomatis dikembalikan.

## Catatan

Patch menggunakan SQLite:

```text
database/neiiu_ai.db
```

Password disimpan sebagai hash PBKDF2, bukan plaintext.

Ollama dan nama model tidak ditampilkan di UI, tetapi backend tetap memakai
`ai/chat_service.py` milik project lu.
