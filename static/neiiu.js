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
const jobLog = document.getElementById("jobLog");
const jobList = document.getElementById("jobList");
const tokenBalance = document.getElementById("tokenBalance");

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
    formNotice.textContent = message;
    formNotice.className = "notice" + (kind ? " " + kind : "");
    formNotice.hidden = false;
}

function hideNotice() {
    formNotice.hidden = true;
}

async function api(url, options) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
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

    renderSteps(job.step, job.status);

    if (job.status === "queued") {
        stepNow.textContent = "Menunggu giliran...";
        stepCount.textContent =
            "Job lain sedang berjalan. Job ini otomatis mulai setelahnya.";
    } else {
        stepNow.textContent = job.step_label || "Menyiapkan...";
        stepCount.textContent = `Langkah ${job.step} dari ${job.total_steps} — ${
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

function renderJobCard(job) {
    const summary = job.summary || {};
    const isDone = job.status === "success";
    const analyzeOnly = summary.analyze_only || job.analyze_only;

    let stats = "";
    let problems = "";
    let actions = "";

    if (isDone && !analyzeOnly) {
        stats = `
            <div class="job-stats">
                <span>Skor SEO: <b>${summary.seo_score}/100</b></span>
                <span>AMP: <b>${
                    summary.amp_valid ? "valid" : "invalid"
                }</b></span>
                <span>Kata: <b>${summary.word_count}</b>
                    <span class="muted">/ target ${summary.word_target}</span>
                </span>
                <span>Section: <b>${summary.sections}</b></span>
                <span>FAQ: <b>${summary.faq}</b></span>
            </div>
        `;

        const list = (summary.problems || []).concat(
            summary.amp_valid ? [] : summary.amp_errors || []
        );

        if (list.length) {
            problems = `<ul class="job-problems">${list
                .map((item) => `<li>${escapeHtml(item)}</li>`)
                .join("")}</ul>`;
        }

        actions = `
            <a href="/neiiu/jobs/${job.id}/preview/index.html" target="_blank">
                Lihat landing page
            </a>
            <a href="/neiiu/jobs/${job.id}/preview/amp.html" target="_blank">
                Lihat AMP
            </a>
            <a class="primary-link" href="/neiiu/jobs/${job.id}/download-all">
                Unduh semua (ZIP)
            </a>
            <a href="/neiiu/jobs/${job.id}/download/index.html">
                index.html
            </a>
            <a href="/neiiu/jobs/${job.id}/download/amp.html">
                amp.html
            </a>
            <a href="/neiiu/jobs/${job.id}/download/sitemap.xml">
                sitemap.xml
            </a>
            <a href="/neiiu/jobs/${job.id}/download/analisis.md">
                ANALISIS.md
            </a>
            <a href="/neiiu/jobs/${job.id}/download/report.json">
                report.json
            </a>
        `;
    } else if (isDone && analyzeOnly) {
        stats = `
            <div class="job-stats">
                <span>Halaman dianalisis: <b>${summary.analyzed_pages}</b></span>
                <span>Gagal: <b>${summary.failed_pages}</b></span>
            </div>
        `;

        actions = `
            <a class="primary-link" href="/neiiu/jobs/${job.id}/download-all">
                Unduh semua (ZIP)
            </a>
            <a href="/neiiu/jobs/${job.id}/download/analisis.md">
                ANALISIS.md
            </a>
            <a href="/neiiu/jobs/${job.id}/download/analysis.json">
                analysis.json
            </a>
        `;
    }

    let hijackBox = "";
    const excluded = [];

    (summary.hijacked_pages || []).forEach((item) => {
        excluded.push(
            `<li>#${item.position} ${escapeHtml(item.domain)} — domain bajakan ${
                item.confidence
            }%${item.cloaking ? ", cloaking" : ""}</li>`
        );
    });

    (summary.unreadable_pages || []).forEach((item) => {
        excluded.push(
            `<li>#${item.position} ${escapeHtml(item.domain)} — isi tidak terbaca (${
                item.word_count
            } kata)</li>`
        );
    });

    if (excluded.length) {
        const counts = [];

        if (summary.hijacked_count) {
            counts.push(`${summary.hijacked_count} domain bajakan`);
        }

        if (summary.unreadable_count) {
            counts.push(`${summary.unreadable_count} isi tidak terbaca`);
        }

        hijackBox = `
            <div class="notice" style="margin-top:12px">
                <b>${counts.join(" dan ")}</b>
                dikeluarkan dari perhitungan target.
                ${
                    summary.hijack_fallback
                        ? "<br><b style='color:var(--danger)'>Tidak ada halaman pertama yang layak jadi acuan. Target metrik tidak bisa dipercaya — tentukan halaman acuan sendiri lewat kolom URL acuan.</b>"
                        : ""
                }
                <ul class="job-problems">${excluded.join("")}</ul>
            </div>
        `;
    }

    const meta = [];

    if (summary.title) {
        meta.push(`Title: ${escapeHtml(summary.title)}`);
    }

    if (summary.reference_domain) {
        meta.push(`Acuan: ${escapeHtml(summary.reference_domain)}`);
    }

    meta.push(`Provider: ${escapeHtml(job.provider)}`);

    if (job.error) {
        meta.push(`<span style="color:var(--danger)">${escapeHtml(
            job.error
        )}</span>`);
    }

    const canDelete =
        job.status !== "running" && job.status !== "queued";

    const brand = job.brand_name || summary.brand_name;

    const brandTag = brand
        ? `<span class="badge">${escapeHtml(brand)}</span>`
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
            <div class="job-meta">${meta.join(" &middot; ")}</div>
            ${stats}
            ${hijackBox}
            ${problems}
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

    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideNotice();

    const keyword = document.getElementById("keyword").value.trim();

    if (!keyword) {
        showNotice("Keyword tidak boleh kosong.", "error");
        return;
    }

    submitBtn.disabled = true;

    const body = {
        keyword,
        brand_name: document.getElementById("brandName").value.trim(),
        base_url: document.getElementById("baseUrl").value.trim(),
        provider: document.getElementById("provider").value,
        crawl: Number(document.getElementById("crawl").value) || 10,
        reference: document.getElementById("reference").value.trim(),
        use_cache: document.getElementById("useCache").checked,
        analyze_only: document.getElementById("analyzeOnly").checked,
        region: document.getElementById("region").value,
        template_id: Number(
            document.getElementById("templateId").value
        ) || 0,
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

jobList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete]");

    if (!button) {
        return;
    }

    if (!confirm("Hapus job ini dari riwayat?")) {
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

const templateForm = document.getElementById("templateForm");
const templateNotice = document.getElementById("templateNotice");
const templateList = document.getElementById("templateList");
const templateSelect = document.getElementById("templateId");
const uploadBtn = document.getElementById("uploadBtn");

function showTemplateNotice(message, kind) {
    templateNotice.textContent = message;
    templateNotice.className = "notice" + (kind ? " " + kind : "");
    templateNotice.hidden = false;
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
    const chosen = templateSelect.value;

    templateSelect.innerHTML =
        '<option value="0">Tanpa template (tiru struktur kompetitor)</option>';

    if (!items.length) {
        templateList.innerHTML =
            '<div class="empty">Belum ada template yang diunggah.</div>';
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
                        <button class="link-btn" data-hapus-template="${item.id}">
                            Hapus
                        </button>
                    </div>
                    <div class="job-meta">
                        landing ${formatBytes(item.landing_bytes)}
                        ${
                            item.amp_bytes
                                ? "&middot; AMP " + formatBytes(item.amp_bytes)
                                : "&middot; tanpa AMP"
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
    try {
        const payload = await api("/api/neiiu/templates");
        renderTemplates(payload.templates || []);
    } catch (error) {
        templateList.innerHTML =
            '<div class="empty">Gagal memuat template: ' +
            escapeHtml(error.message) +
            "</div>";
    }
}

templateForm.addEventListener("submit", async (event) => {
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
        templateSelect.value = String(payload.template_id);
    } catch (error) {
        showTemplateNotice(error.message, "error");
    } finally {
        uploadBtn.disabled = false;
    }
});

templateList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-hapus-template]");

    if (!button) {
        return;
    }

    if (!confirm("Hapus template ini?")) {
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

refreshJobs();
refreshTemplates();
