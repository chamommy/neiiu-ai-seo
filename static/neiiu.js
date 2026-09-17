/*
 * Halaman generator NEIIU.
 *
 * Pipeline butuh puluhan menit, jadi halaman ini tidak menunggu
 * request selesai. Job dibuat, lalu statusnya ditanyakan berkala
 * sampai selesai atau gagal.
 */

const TOTAL_STEPS = 8;
const POLL_MS = 3000;

const form = document.getElementById("jobForm");
const submitBtn = document.getElementById("submitBtn");
const formNotice = document.getElementById("formNotice");
const progressCard = document.getElementById("progressCard");
const stepDots = document.getElementById("stepDots");
const stepNow = document.getElementById("stepNow");
const stepCount = document.getElementById("stepCount");
const runPercent = document.getElementById("runPercent");
const runBar = document.getElementById("runBar");
const runSpinner = document.getElementById("runSpinner");
const jobLog = document.getElementById("jobLog");
const jobList = document.getElementById("jobList");
const tokenBalance = document.getElementById("tokenBalance");
const genStatus = document.getElementById("genStatus");

/*
 * Keadaan job dalam satu kata, di sebelah judul kartu.
 *
 * Bilah kemajuan menjawab "sudah sampai mana"; yang ini menjawab
 * "sedang apa". Halaman template tidak punya simpul ini, jadi
 * kehadirannya diperiksa dulu - aturan yang sama dengan bagian lain
 * di berkas ini yang dipakai bersama dua halaman.
 */
const STATUS_CHIP = {
    idle: "Siap",
    starting: "Menyiapkan",
    running: "Berjalan",
    success: "Selesai",
    error: "Gagal",
};

function setGenStatus(state) {
    if (!genStatus) {
        return;
    }

    genStatus.dataset.state = state;
    genStatus.textContent = STATUS_CHIP[state] || state;
}

let watchedJobId = null;
let pollTimer = null;

const STATUS_LABEL = {
    queued: "Menunggu giliran",
    running: "Berjalan",
    success: "Selesai",
    error: "Gagal",
    cancelled: "Dibatalkan",
};

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    })[char]);
}

function showNotice(message, kind) {
    if (!formNotice) {
        return;
    }

    formNotice.textContent = message;
    formNotice.className = "notice" + (kind ? " " + kind : "");
    formNotice.hidden = false;
}

function hideNotice() {
    if (formNotice) {
        formNotice.hidden = true;
    }
}

// ---------- Konfirmasi ----------

// confirm() bawaan browser muncul menempel di tepi atas jendela,
// jauh dari tombol yang baru ditekan, dan tampilannya tidak ikut
// tema halaman. Penggantinya memakai <dialog> supaya latar gelap,
// kunci fokus, dan tombol Esc tetap ditangani browser. Tampilannya
// meminjam kelas .popup-* dari halaman chat, jadi kedua halaman
// memakai bentuk konfirmasi yang sama.

const askDialog = document.getElementById("askDialog");
const askTitle = document.getElementById("askTitle");
const askText = document.getElementById("askText");
const askOk = document.getElementById("askOk");

function tanya({ judul, pesan, tombol = "Hapus", bahaya = true }) {
    // Browser lama tanpa showModal tetap dapat konfirmasi, meski
    // kembali ke bentuk bawaan. Lebih baik daripada tombol hapus
    // yang jalan tanpa bertanya sama sekali.
    if (!askDialog || typeof askDialog.showModal !== "function") {
        return Promise.resolve(window.confirm(pesan));
    }

    askTitle.textContent = judul;
    askText.textContent = pesan;
    askOk.textContent = tombol;
    askOk.classList.toggle("danger", bahaya);
    askOk.classList.toggle("primary", !bahaya);

    return new Promise((resolve) => {
        askDialog.addEventListener(
            "close",
            () => resolve(askDialog.returnValue === "ya"),
            { once: true }
        );

        // Dikosongkan dulu supaya nilai dari dialog sebelumnya tidak
        // terbawa kalau kali ini ditutup lewat Esc.
        askDialog.returnValue = "";
        askDialog.showModal();
    });
}

async function api(url, options) {
    // Berkas dan formulir multipart TIDAK boleh kebagian header
    // JSON. Batas antarbagian multipart ditulis browser sendiri ke
    // dalam Content-Type, dan menimpanya dengan "application/json"
    // membuat server menerima badan permintaan yang tidak bisa
    // diurai - jawabannya 400 untuk permintaan yang sebenarnya benar.
    const multipart = options && options.body instanceof FormData;

    const response = await fetch(url, {
        headers: multipart ? {} : { "Content-Type": "application/json" },
        ...options,
    });

    let payload = null;

    try {
        payload = await response.json();
    } catch (error) {
        payload = null;
    }

    if (!response.ok) {
        const detail =
            (payload && payload.detail) ||
            `Gagal (HTTP ${response.status})`;
        throw new Error(detail);
    }

    return payload;
}

function renderSteps(step, status) {
    let html = "";

    for (let index = 1; index <= TOTAL_STEPS; index += 1) {
        let cls = "step-dot";

        if (status === "success" || index < step) {
            cls += " done";
        } else if (index === step) {
            cls += status === "error" ? "" : " active";
        }

        html += `<div class="${cls}"></div>`;
    }

    stepDots.innerHTML = html;
}

function renderProgress(job) {
    progressCard.hidden = false;
    setGenStatus(job.status === "queued" ? "starting" : "running");

    renderSteps(job.step, job.status);

    const total = job.total_steps || TOTAL_STEPS;

    // Persen dihitung dari langkah yang SUDAH lewat, bukan dari
    // langkah yang sedang jalan. Langkah yang baru dimulai belum
    // menghasilkan apa-apa, dan menghitungnya sebagai selesai
    // membuat bar sampai di 100% sementara prosesnya masih menulis.
    let persen = Math.round(((job.step - 1) / total) * 100);

    if (job.status === "success") {
        persen = 100;
    } else if (job.status === "queued") {
        persen = 0;
    }

    persen = Math.max(0, Math.min(100, persen));

    runPercent.textContent = `${persen}%`;
    runBar.style.width = `${persen}%`;

    const diam = job.status === "queued" || job.status === "error";

    runSpinner.classList.toggle("idle", diam);

    if (job.status === "queued") {
        stepNow.textContent = "Menunggu giliran...";
        stepCount.textContent =
            "Job lain sedang berjalan. Job ini otomatis mulai setelahnya.";
    } else {
        stepNow.textContent = job.step_label || "Menyiapkan...";
        stepCount.textContent = `Langkah ${job.step} dari ${total} — ${
            STATUS_LABEL[job.status] || job.status
        }`;
    }

    const lines = job.log || [];

    jobLog.innerHTML = lines
        .map((item) => `<div>${escapeHtml(item.text)}</div>`)
        .join("");

    jobLog.scrollTop = jobLog.scrollHeight;
}

function statusBadge(status) {
    const cls =
        status === "success"
            ? "success"
            : status === "error"
            ? "error"
            : status === "running" || status === "queued"
            ? "running"
            : "";

    return `<span class="badge ${cls}">${
        STATUS_LABEL[status] || status
    }</span>`;
}

/*
    Kartu satu job di daftar riwayat.

    Job yang sudah selesai tidak lagi menampilkan rinciannya - skor
    SEO, jumlah kata, daftar masalah, daftar domain bajakan. Semua
    itu berguna SELAMA prosesnya berjalan, dan memang tetap tertulis
    di log serta di ANALISIS.md di dalam ZIP-nya. Sesudah halamannya
    jadi, yang dicari orang cuma halamannya.

    Job yang GAGAL tetap menampilkan sebab kegagalannya. Menyembunyikan
    itu bukan merapikan, melainkan membuat kegagalan jadi tidak bisa
    ditindaklanjuti.
*/
function renderJobCard(job) {
    const summary = job.summary || {};
    const isDone = job.status === "success";
    const analyzeOnly = summary.analyze_only || job.analyze_only;

    let actions = "";

    if (isDone && !analyzeOnly) {
        actions = `
            <a class="primary-link"
               href="/neiiu/jobs/${job.id}/preview/index.html"
               target="_blank">
                Lihat hasil
            </a>
            <a href="/neiiu/jobs/${job.id}/download-all">
                Unduh ZIP
            </a>
            <a href="/neiiu/jobs/${job.id}/download/index.html">
                Unduh landing page
            </a>
            <a href="/neiiu/jobs/${job.id}/download/amp.html">
                Unduh AMP
            </a>
        `;
    } else if (isDone && analyzeOnly) {
        // Job analisis tidak menghasilkan halaman, jadi tidak ada
        // yang bisa dilihat atau diunduh selain laporannya.
        actions = `
            <a class="primary-link" href="/neiiu/jobs/${job.id}/download-all">
                Unduh ZIP
            </a>
            <a href="/neiiu/jobs/${job.id}/download/analisis.md">
                Unduh analisis
            </a>
        `;
    }

    const canDelete =
        job.status !== "running" && job.status !== "queued";

    const brand = job.brand_name || summary.brand_name;

    const brandTag = brand
        ? `<span class="badge">${escapeHtml(brand)}</span>`
        : "";

    const errorBox = job.error
        ? `<div class="job-error">${escapeHtml(job.error)}</div>`
        : "";

    return `
        <div class="job">
            <div class="job-head">
                <span class="job-keyword">${escapeHtml(job.keyword)}</span>
                <span style="display:flex;gap:8px;flex-wrap:wrap">
                    ${brandTag}
                    ${statusBadge(job.status)}
                </span>
            </div>
            ${errorBox}
            <div class="job-actions">
                ${actions}
                ${
                    canDelete
                        ? `<button class="danger" data-delete="${job.id}">Hapus</button>`
                        : ""
                }
            </div>
        </div>
    `;
}

async function refreshJobs() {
    // Berkas ini dipakai dua halaman: generator dan pengelola
    // template. Yang kedua tidak punya daftar riwayat, jadi
    // ketiadaannya bukan kesalahan - cuma berarti tidak ada yang
    // perlu dimuat di sini.
    if (!jobList) {
        return;
    }

    let payload;

    try {
        payload = await api("/api/neiiu/jobs");
    } catch (error) {
        jobList.innerHTML = `<div class="empty">${escapeHtml(
            error.message
        )}</div>`;
        return;
    }

    const jobs = payload.jobs || [];

    if (!jobs.length) {
        jobList.innerHTML =
            '<div class="empty">Belum ada job. Buat yang pertama di atas.</div>';
        return;
    }

    jobList.innerHTML = jobs.map(renderJobCard).join("");

    // Kalau halaman baru dibuka saat ada job jalan, ikuti job itu.
    if (watchedJobId === null) {
        const live = jobs.find(
            (job) => job.status === "running" || job.status === "queued"
        );

        if (live) {
            watchJob(live.id);
        }
    }
}

async function pollJob() {
    if (watchedJobId === null) {
        return;
    }

    let payload;

    try {
        payload = await api(`/api/neiiu/jobs/${watchedJobId}`);
    } catch (error) {
        stopWatching();
        return;
    }

    const job = payload.job;

    renderProgress(job);

    if (job.status === "success" || job.status === "error") {
        stopWatching();

        // Panel proses ditutup begitu halamannya jadi. Langkah,
        // persen, dan log adalah kabar tentang pekerjaan yang
        // sedang berlangsung; sesudah selesai ia cuma menutupi
        // hasilnya. Log lengkapnya tetap tersimpan di ZIP.
        //
        // Job yang GAGAL sengaja dibiarkan terbuka: di situlah
        // satu-satunya tempat sebab kegagalannya terbaca baris per
        // baris.
        if (job.status === "success") {
            progressCard.hidden = true;
        }

        setGenStatus(job.status === "success" ? "success" : "error");

        showNotice(
            job.status === "success"
                ? `Job "${job.keyword}" selesai.`
                : `Job "${job.keyword}" gagal: ${job.error}`,
            job.status === "success" ? "ok" : "error"
        );

        await refreshJobs();
        return;
    }

    await refreshJobs();
}

function watchJob(jobId) {
    watchedJobId = jobId;
    submitBtn.disabled = true;
    progressCard.hidden = false;

    if (pollTimer) {
        clearInterval(pollTimer);
    }

    pollJob();
    pollTimer = setInterval(pollJob, POLL_MS);
}

function stopWatching() {
    watchedJobId = null;
    submitBtn.disabled = false;
    submitBtn.classList.remove("is-loading");

    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideNotice();

    const niche = document.getElementById("niche").value.trim();

    if (!niche) {
        showNotice("Niche tidak boleh kosong.", "error");
        return;
    }

    // Diperiksa di sini JUGA, bukan cuma di server.
    //
    // Server tetap yang memutuskan - lihat api_neiiu_create_job -
    // tapi menunggu jawaban 400 untuk kolom yang jelas-jelas belum
    // diisi berarti pengguna menekan tombol, menunggu, lalu membaca
    // pesan yang bisa muncul seketika.
    const templateDipilih = Number(
        document.getElementById("templateId").value
    ) || 0;

    if (!templateDipilih && !document.getElementById("analyzeOnly").checked) {
        showNotice(
            "Pilih template dulu. Halaman ditulis di atas template " +
                "yang kamu unggah, jadi tanpa template tidak ada " +
                "struktur yang bisa diisi.",
            "error"
        );
        return;
    }

    submitBtn.disabled = true;
    submitBtn.classList.add("is-loading");
    setGenStatus("starting");

    const body = {
        // Topik halaman. Server menerimanya sebagai "niche" dan
        // menyimpannya di kolom keyword - nama lama yang dipakai
        // seluruh pipeline. Yang berganti namanya cuma di layar.
        niche,
        brand_name: document.getElementById("brandName").value.trim(),
        provider: document.getElementById("provider").value,
        crawl: Number(document.getElementById("crawl").value) || 10,
        use_cache: document.getElementById("useCache").checked,
        analyze_only: document.getElementById("analyzeOnly").checked,
        region: document.getElementById("region").value,
        city: document.getElementById("city").value,
        template_id: Number(
            document.getElementById("templateId").value
        ) || 0,
        template_brand: document
            .getElementById("templateBrand")
            .value.trim(),
        // Alamat, semuanya opsional.
        //
        // Yang dikosongkan dikirim sebagai string kosong, dan string
        // kosong berarti alamat yang sudah ada di template dibiarkan
        // apa adanya. Tidak ada satu pun nilai cadangan di jalur ini -
        // lihat generators/page_links.py.
        canonical_url: document
            .getElementById("canonicalUrl")
            .value.trim(),
        amphtml_url: document.getElementById("amphtmlUrl").value.trim(),
        cta_url: document.getElementById("ctaUrl").value.trim(),
        logo_url: document.getElementById("logoUrl").value.trim(),
        favicon_url: document.getElementById("faviconUrl").value.trim(),
        poster_url: document.getElementById("posterUrl").value.trim(),
        // Kosong berarti 0, dan 0 berarti mengikuti panjang contoh
        // artikel apa adanya - bukan artikel sepanjang nol kata.
        article_words:
            Number(document.getElementById("articleWords").value) || 0,
    };

    try {
        const payload = await api("/api/neiiu/jobs", {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (tokenBalance && payload.remaining_tokens !== undefined) {
            tokenBalance.textContent = payload.remaining_tokens;
        }

        showNotice(
            payload.queued_behind
                ? "Job masuk antrian. Akan mulai setelah job yang sedang jalan selesai."
                : "Job dimulai.",
            "ok"
        );

        jobLog.innerHTML = "";
        watchJob(payload.job_id);
        await refreshJobs();
    } catch (error) {
        submitBtn.disabled = false;
        showNotice(error.message, "error");
    }
});

jobList?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete]");

    if (!button) {
        return;
    }

    const keyword = button
        .closest(".job")
        ?.querySelector(".job-keyword")
        ?.textContent?.trim();

    // Yang dihapus cuma barisnya di riwayat; berkas hasil di folder
    // output tidak ikut terhapus. Itu disebutkan supaya tidak terbaca
    // seolah halaman yang sudah jadi ikut hilang.
    const lanjut = await tanya({
        judul: "Hapus job ini?",
        pesan:
            (keyword ? `Job "${keyword}" ` : "Job ini ") +
            "akan hilang dari riwayat. Berkas landing page dan AMP " +
            "yang sudah jadi tetap ada di folder output.",
    });

    if (!lanjut) {
        return;
    }

    try {
        await api(`/api/neiiu/jobs/${button.dataset.delete}`, {
            method: "DELETE",
        });

        await refreshJobs();
    } catch (error) {
        showNotice(error.message, "error");
    }
});


// ---------- Template milik pengguna ----------

// Bagian ini berdiri di DUA halaman, dan masing-masing cuma memakai
// separuhnya. Halaman generator punya pemilih template tapi tidak
// punya formulir unggah; halaman pengelola template kebalikannya.
// Karena itu tiap simpul diperiksa dulu sebelum dipakai - yang
// tidak ada bukan kesalahan, cuma bagian yang tidak dipakai halaman
// ini. Satu berkas untuk keduanya supaya cara memanggil
// /api/neiiu/templates tidak ditulis dua kali lalu berbeda suatu
// saat.

const templateForm = document.getElementById("templateForm");
const templateNotice = document.getElementById("templateNotice");
const templateList = document.getElementById("templateList");
const templateSelect = document.getElementById("templateId");
const uploadBtn = document.getElementById("uploadBtn");

function showTemplateNotice(message, kind) {
    if (!templateNotice) {
        return;
    }

    templateNotice.textContent = message;
    templateNotice.className = "notice" + (kind ? " " + kind : "");
    templateNotice.hidden = false;
}

/**
 * Waktu simpan yang bisa dibaca sekilas.
 *
 * Yang disimpan database ISO UTC. Ditampilkan apa adanya, kolomnya
 * jadi deretan angka dan huruf T yang tidak terbaca sebagai tanggal
 * oleh siapa pun yang cuma ingin tahu mana template yang paling
 * baru.
 */
function tanggalPendek(value) {
    if (!value) {
        return "-";
    }

    const waktu = new Date(value);

    if (Number.isNaN(waktu.getTime())) {
        return String(value).slice(0, 10);
    }

    return waktu.toLocaleDateString("id-ID", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

function formatBytes(value) {
    if (value >= 1024 * 1024) {
        return (value / (1024 * 1024)).toFixed(1) + " MB";
    }

    return Math.max(Math.round(value / 1024), 1) + " KB";
}

function renderTemplates(items) {
    // Pilihan yang sedang aktif dipertahankan, supaya daftar yang
    // dimuat ulang setelah unggahan tidak diam-diam mengganti
    // template yang sudah dipilih pengguna.
    const chosen = templateSelect ? templateSelect.value : "0";

    if (templateSelect) {
        // Pilihan pertama BUKAN "tanpa template" lagi, melainkan
        // ajakan memilih yang tidak sah dikirim.
        //
        // Halaman ini ditulis di atas template dan hanya di atas
        // template; tidak ada lagi jalur yang merakit struktur
        // sendiri. Menyisakan pilihan lamanya berarti menjanjikan
        // sesuatu yang akan ditolak server sesudah tombolnya
        // ditekan.
        templateSelect.innerHTML =
            '<option value="0">' +
            "-- pilih template --</option>";
    }

    if (!templateList) {
        // Halaman generator: yang perlu diisi cuma pemilihnya.
        isiPemilihTemplate(items, chosen);
        return;
    }

    if (!items.length) {
        templateList.innerHTML =
            '<div class="empty">Belum ada template yang diunggah. ' +
            '<a href="/neiiu/template">Unggah satu</a> untuk mulai.</div>';
        isiPemilihTemplate(items, chosen);
        return;
    }

    templateList.innerHTML = items
        .map((item) => {
            const slots = Object.entries(item.slot_summary || {})
                .map(([role, count]) => role + " " + count)
                .join(", ");

            return `
                <div class="job-card">
                    <div class="job-head">
                        <strong>${escapeHtml(item.name)}</strong>
                        <span>
                            <button class="link-btn" data-ganti-nama="${item.id}">
                                Ganti nama
                            </button>
                            <button class="link-btn" data-hapus-template="${item.id}">
                                Hapus
                            </button>
                        </span>
                    </div>
                    <div class="job-meta">
                        landing ${formatBytes(item.landing_bytes)}
                        ${
                            item.amp_bytes
                                ? "&middot; AMP " + formatBytes(item.amp_bytes)
                                : "&middot; tanpa AMP"
                        }
                    </div>
                    <div class="job-meta">
                        dibuat ${escapeHtml(tanggalPendek(item.created_at))}
                        ${
                            item.updated_at &&
                            item.updated_at !== item.created_at
                                ? "&middot; diubah " +
                                  escapeHtml(tanggalPendek(item.updated_at))
                                : ""
                        }
                    </div>
                    <div class="job-meta">Bagian yang akan diisi: ${
                        escapeHtml(slots) || "-"
                    }</div>
                    ${
                        item.notes
                            ? `<div class="job-meta">${escapeHtml(item.notes)}</div>`
                            : ""
                    }
                </div>
            `;
        })
        .join("");

    isiPemilihTemplate(items, chosen);
}

/**
 * Mengisi pemilih template di formulir generator.
 *
 * Dipisah supaya halaman yang cuma punya pemilihnya - tanpa daftar
 * kartu dan tanpa formulir unggah - tetap kebagian isi yang sama
 * dari satu tempat.
 */
function isiPemilihTemplate(items, chosen) {
    if (!templateSelect) {
        return;
    }

    for (const item of items) {
        const option = document.createElement("option");
        option.value = String(item.id);
        option.textContent = item.name;
        templateSelect.appendChild(option);
    }

    templateSelect.value = items.some((item) => String(item.id) === chosen)
        ? chosen
        : "0";
}

async function refreshTemplates() {
    if (!templateSelect && !templateList) {
        return;
    }

    try {
        const payload = await api("/api/neiiu/templates");
        renderTemplates(payload.templates || []);
    } catch (error) {
        if (templateList) {
            templateList.innerHTML =
                '<div class="empty">Gagal memuat template: ' +
                escapeHtml(error.message) +
                "</div>";
        }
    }
}

templateForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    templateNotice.hidden = true;

    const landing = document.getElementById("landingFile").files[0];

    if (!landing) {
        showTemplateNotice("Pilih berkas landing page dulu.", "error");
        return;
    }

    const data = new FormData();
    data.append("name", document.getElementById("templateName").value.trim());
    data.append("landing", landing);

    const amp = document.getElementById("ampFile").files[0];

    if (amp) {
        data.append("amp", amp);
    }

    uploadBtn.disabled = true;

    try {
        // Sengaja tidak lewat api(): FormData harus dikirim tanpa
        // Content-Type buatan sendiri, supaya batas multipart-nya
        // ditentukan browser.
        const response = await fetch("/api/neiiu/templates", {
            method: "POST",
            body: data,
        });

        const payload = await response.json();

        if (!response.ok) {
            throw new Error(payload.detail || "Gagal mengunggah template.");
        }

        const ringkas = Object.entries(payload.slots || {})
            .map(([role, count]) => role + " " + count)
            .join(", ");

        showTemplateNotice(
            `Template tersimpan. ${payload.total_slots} bagian dikenali` +
                (ringkas ? ` (${ringkas}).` : ".") +
                (payload.notes && payload.notes.length
                    ? " " + payload.notes.join(" ")
                    : ""),
            "ok"
        );

        templateForm.reset();
        await refreshTemplates();

        if (templateSelect) {
            templateSelect.value = String(payload.template_id);
        }
    } catch (error) {
        showTemplateNotice(error.message, "error");
    } finally {
        uploadBtn.disabled = false;
    }
});

templateList?.addEventListener("click", async (event) => {
    const rename = event.target.closest("[data-ganti-nama]");

    if (rename) {
        const kartu = rename.closest(".job-card");
        const lama = kartu?.querySelector("strong")?.textContent?.trim() || "";

        // Kotak isian bawaan browser, bukan dialog sendiri. Yang
        // diubah cuma satu baris teks, dan membuat dialog khusus
        // untuk itu menambah tiga bagian antarmuka yang harus dijaga
        // demi satu kolom.
        const baru = window.prompt("Nama baru untuk template ini:", lama);

        if (baru === null || !baru.trim() || baru.trim() === lama) {
            return;
        }

        try {
            const data = new FormData();
            data.append("name", baru.trim());

            // Nomor templatenya TIDAK berganti - itu yang mengikat
            // landing dan AMP jadi satu pasangan, dan job yang sudah
            // menunjuknya tetap menunjuk yang benar.
            await api("/api/neiiu/templates/" + rename.dataset.gantiNama, {
                method: "PUT",
                body: data,
            });

            await refreshTemplates();
        } catch (error) {
            showTemplateNotice(error.message, "error");
        }

        return;
    }

    const button = event.target.closest("[data-hapus-template]");

    if (!button) {
        return;
    }

    const nama = button
        .closest(".job-card")
        ?.querySelector("strong")
        ?.textContent?.trim();

    // Berbeda dengan job: delete_template() ikut menghapus folder
    // berkasnya, jadi HTML yang diunggah benar-benar hilang.
    const lanjut = await tanya({
        judul: "Hapus template ini?",
        pesan:
            (nama ? `Template "${nama}" ` : "Template ini ") +
            "beserta berkas HTML yang diunggah akan dihapus permanen. " +
            "Job yang sudah terlanjur memakainya tidak terpengaruh.",
    });

    if (!lanjut) {
        return;
    }

    try {
        await api("/api/neiiu/templates/" + button.dataset.hapusTemplate, {
            method: "DELETE",
        });

        await refreshTemplates();
    } catch (error) {
        showTemplateNotice(error.message, "error");
    }
});

// ---------- Pemilih kota ----------

// Daftar kota per zona dikirim bersama halamannya, bukan diambil
// lewat permintaan terpisah. Isinya kecil dan tidak pernah berubah
// saat halaman terbuka, jadi menaruhnya di sini membuat pemilih kota
// langsung terisi begitu zonanya diganti.
const REGION_CITIES = (() => {
    const holder = document.getElementById("regionData");

    if (!holder) {
        return {};
    }

    try {
        const rows = JSON.parse(holder.textContent) || [];
        const map = {};

        rows.forEach((row) => {
            map[row.code] = row.cities || [];
        });

        return map;
    } catch (error) {
        return {};
    }
})();

function refreshCities() {
    const regionSelect = document.getElementById("region");
    const citySelect = document.getElementById("city");

    if (!regionSelect || !citySelect) {
        return;
    }

    const cities = REGION_CITIES[regionSelect.value] || [];

    citySelect.innerHTML =
        '<option value="">Seluruh negara</option>' +
        cities
            .map(
                (city) =>
                    `<option value="${escapeHtml(city.value)}">` +
                    `${escapeHtml(city.label)}</option>`
            )
            .join("");
}

const regionSelect = document.getElementById("region");

if (regionSelect) {
    // Kota zona lain ditolak server, jadi daftarnya harus ikut
    // berganti begitu zonanya berganti - bukan menunggu job gagal.
    regionSelect.addEventListener("change", refreshCities);
}

refreshCities();
refreshJobs();
refreshTemplates();
