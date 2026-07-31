const state = {
    mode: "normal",
    chatId: null,
    loading: false,
};

const messages = document.getElementById("messages");
const input = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const form = document.getElementById("chatForm");
const tokenLabel = document.getElementById("tokenLabel");
const modeTitle = document.getElementById("modeTitle");
const modeSubtitle = document.getElementById("modeSubtitle");
const history = document.getElementById("history");

function showPopup({
    title,
    message,
    confirmText = "OK",
    cancelText = null,
    danger = false,
}) {
    return new Promise((resolve) => {
        const backdrop = document.createElement("div");
        backdrop.className = "popup-backdrop";

        const dialog = document.createElement("div");
        dialog.className = "popup-dialog";
        dialog.setAttribute("role", "dialog");
        dialog.setAttribute("aria-modal", "true");

        const heading = document.createElement("h2");
        heading.textContent = title;

        const body = document.createElement("p");
        body.textContent = message;

        const actions = document.createElement("div");
        actions.className = "popup-actions";

        function close(value) {
            backdrop.remove();
            resolve(value);
        }

        if (cancelText) {
            const cancelButton = document.createElement("button");
            cancelButton.type = "button";
            cancelButton.className = "popup-button secondary";
            cancelButton.textContent = cancelText;
            cancelButton.addEventListener("click", () => close(false));
            actions.appendChild(cancelButton);
        }

        const confirmButton = document.createElement("button");
        confirmButton.type = "button";
        confirmButton.className = danger
            ? "popup-button danger"
            : "popup-button primary";
        confirmButton.textContent = confirmText;
        confirmButton.addEventListener("click", () => close(true));
        actions.appendChild(confirmButton);

        backdrop.addEventListener("click", (event) => {
            if (event.target === backdrop) {
                close(false);
            }
        });

        dialog.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                close(false);
            }
        });

        dialog.appendChild(heading);
        dialog.appendChild(body);
        dialog.appendChild(actions);
        backdrop.appendChild(dialog);
        document.body.appendChild(backdrop);
        confirmButton.focus();
    });
}

function escapeText(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}

function removeWelcome() {
    document.getElementById("welcome")?.remove();
}

function removeMessageNames() {
    document.querySelectorAll(".message-name").forEach((item) => item.remove());
}

function addMessage(role, content) {
    removeWelcome();
    removeMessageNames();

    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const body = document.createElement("div");
    body.textContent = content;

    bubble.appendChild(body);
    row.appendChild(bubble);
    messages.appendChild(row);

    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: "smooth",
    });

    return row;
}

function addTyping() {
    const row = addMessage("assistant", "Sedang berpikir...");
    row.id = "typing";
    row.querySelector(".message-bubble").classList.add("typing");
}

function removeTyping() {
    document.getElementById("typing")?.remove();
}

function resetChat() {
    state.chatId = null;
    messages.innerHTML = `
        <div id="welcome" class="welcome">
            <div>
                <img
                    src="https://ik.imagekit.io/haim3/neiiuai%20logo.jpg"
                    alt="NEIIU AI"
                >
                <h1 class="brand-green">NEIIU AI</h1>
                <p>Apa yang bisa gue bantu hari ini?</p>
            </div>
        </div>
    `;

    document
        .querySelectorAll(".history-item")
        .forEach((item) => item.classList.remove("active"));

    input.focus();
}

async function togglePin(
    chatId,
    isPinned
) {
    const response = await fetch(
        `/api/chats/${chatId}/pin`,
        {
            method: "PATCH",
            headers: {
                "Content-Type":
                    "application/json",
            },
            body: JSON.stringify({
                is_pinned: isPinned,
            }),
        }
    );

    const data = await response.json();

    if (!response.ok) {
        alert(
            data.detail
            || "Gagal mengubah pin chat."
        );
        return;
    }

    await refreshHistory();
}


async function deleteHistoryChat(
    chatId
) {
    const confirmed = await showPopup({
        title: "Hapus chat?",
        message: "History dan semua isi chat ini akan dihapus permanen.",
        confirmText: "Hapus",
        cancelText: "Batal",
        danger: true,
    });

    if (!confirmed) {
        return;
    }

    const response = await fetch(
        `/api/chats/${chatId}`,
        {
            method: "DELETE",
        }
    );

    const data = await response.json();

    if (!response.ok) {
        await showPopup({
            title: "Gagal menghapus",
            message: data.detail || "Gagal menghapus chat.",
        });
        return;
    }

    if (
        Number(state.chatId)
        === Number(chatId)
    ) {
        resetChat();
    }

    await refreshHistory();

    await showPopup({
        title: "Chat dihapus",
        message: "History chat berhasil dihapus.",
    });
}

async function refreshHistory() {
    const response =
        await fetch("/api/chats");

    const data =
        await response.json();

    history.innerHTML = "";

    for (const chat of data.chats) {
        const row =
            document.createElement(
                "div"
            );

        row.className =
            "history-row";

        if (chat.is_pinned) {
            row.classList.add(
                "pinned"
            );
        }

        const openButton =
            document.createElement(
                "button"
            );

        openButton.className =
            "history-item";
        openButton.type = "button";

        openButton.dataset.chatId =
            chat.id;

        if (
            Number(state.chatId)
            === Number(chat.id)
        ) {
            openButton.classList.add("active");
        }

        const title =
            document.createElement(
                "span"
            );

        title.className =
            "history-title";

        title.textContent =
            `${chat.is_pinned ? "📌 " : ""}${chat.title}`;

        openButton.appendChild(title);

        const menuWrapper =
            document.createElement(
                "div"
            );

        menuWrapper.className =
            "history-menu-wrapper";

        const menuButton =
            document.createElement(
                "button"
            );

        menuButton.className =
            "history-menu-button";

        menuButton.textContent =
            "⋯";

        const menu =
            document.createElement(
                "div"
            );

        menu.className =
            "history-menu";

        const pinButton =
            document.createElement(
                "button"
            );

        pinButton.className =
            "history-pin";
        pinButton.type = "button";
        pinButton.dataset.chatId =
            chat.id;
        pinButton.dataset.pinned =
            chat.is_pinned ? "1" : "0";

        pinButton.textContent =
            chat.is_pinned
                ? "Unpin"
                : "Pin";

        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.className =
            "history-delete danger";
        deleteButton.type = "button";
        deleteButton.dataset.chatId =
            chat.id;

        deleteButton.textContent =
            "Delete";

        menu.appendChild(pinButton);
        menu.appendChild(
            deleteButton
        );

        menuWrapper.appendChild(
            menuButton
        );

        menuWrapper.appendChild(menu);

        row.appendChild(openButton);
        row.appendChild(menuWrapper);

        history.appendChild(row);
    }
}

async function loadChat(chatId) {
    if (state.loading) {
        return;
    }

    const response = await fetch(`/api/chats/${chatId}`);
    const data = await response.json();

    if (!response.ok) {
        alert(data.detail || "Chat gagal dibuka.");
        return;
    }

    state.chatId = chatId;
    state.mode = data.chat.mode;

    updateModeUI();
    messages.innerHTML = "";

    for (const item of data.messages) {
        addMessage(item.role, item.content);
    }

    document
        .querySelectorAll(".history-item")
        .forEach((item) => {
            item.classList.toggle(
                "active",
                Number(item.dataset.chatId) === Number(chatId)
            );
        });
}

function updateModeUI() {
    document.querySelectorAll(".mode").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.mode === state.mode
        );
    });

    if (state.mode === "seo") {
        modeTitle.textContent = "SEO Expert";
        modeSubtitle.textContent =
            "Mode khusus pekerjaan dan strategi SEO.";
    } else {
        modeTitle.textContent = "Normal Mode";
        modeSubtitle.textContent =
            "Tanya apa saja kepada NEIIU AI.";
    }
}

async function sendMessage(message) {
    if (!message || state.loading) {
        return;
    }

    addMessage("user", message);

    state.loading = true;
    sendButton.disabled = true;
    input.disabled = true;

    addTyping();

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                mode: state.mode,
                chat_id: state.chatId,
            }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "AI gagal menjawab."
            );
        }

        removeTyping();

        state.chatId = data.chat_id;

        addMessage("assistant", data.answer);

        tokenLabel.textContent =
            `${data.remaining_tokens} token`;

        await refreshHistory();

    } catch (error) {
        removeTyping();
        addMessage("assistant", `ERROR: ${error.message}`);

    } finally {
        state.loading = false;
        sendButton.disabled = false;
        input.disabled = false;
        input.focus();
    }
}

document.querySelectorAll(".mode").forEach((button) => {
    button.addEventListener("click", () => {
        if (state.loading) {
            return;
        }

        state.mode = button.dataset.mode;
        resetChat();
        updateModeUI();
    });
});

document.getElementById("newChat").addEventListener("click", () => {
    if (!state.loading) {
        resetChat();
    }
});

history.addEventListener("click", async (event) => {
    const pinButton = event.target.closest(".history-pin");
    if (pinButton) {
        event.preventDefault();
        event.stopPropagation();

        const isPinned =
            pinButton.dataset.pinned === "True"
            || pinButton.dataset.pinned === "true"
            || pinButton.dataset.pinned === "1";

        await togglePin(
            Number(pinButton.dataset.chatId),
            !isPinned
        );
        return;
    }

    const deleteButton = event.target.closest(".history-delete");
    if (deleteButton) {
        event.preventDefault();
        event.stopPropagation();

        await deleteHistoryChat(
            Number(deleteButton.dataset.chatId)
        );
        return;
    }

    const menuButton = event.target.closest(".history-menu-button");
    if (menuButton) {
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    const historyItem = event.target.closest(".history-item");
    if (historyItem) {
        await loadChat(Number(historyItem.dataset.chatId));
    }
});

input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height =
        `${Math.min(input.scrollHeight, 180)}px`;
});

input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
    }
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();

    if (!message) {
        return;
    }

    input.value = "";
    input.style.height = "auto";

    await sendMessage(message);
});

updateModeUI();
input.focus();
