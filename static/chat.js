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
    const confirmed = confirm(
        "Hapus chat ini secara permanen?"
    );

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
        alert(
            data.detail
            || "Gagal menghapus chat."
        );
        return;
    }

    if (
        Number(state.chatId)
        === Number(chatId)
    ) {
        resetChat();
    }

    await refreshHistory();
}

async function refreshHistory() {
    const response =
        await fetch("/api/chats");

    const data =
        await response.json();

    const container =
        document.getElementById(
            "history"
        );

    container.innerHTML = "";

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

        openButton.dataset.chatId =
            chat.id;

        const title =
            document.createElement(
                "span"
            );

        title.className =
            "history-title";

        title.textContent =
            `${chat.is_pinned ? "📌 " : ""}${chat.title}`;

        openButton.appendChild(title);

        openButton.addEventListener(
            "click",
            () => {
                loadChat(chat.id);
            }
        );

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

        pinButton.textContent =
            chat.is_pinned
                ? "Unpin"
                : "Pin";

        pinButton.addEventListener(
            "click",
            async (event) => {
                event.stopPropagation();

                await togglePin(
                    chat.id,
                    !Boolean(
                        chat.is_pinned
                    )
                );
            }
        );

        const deleteButton =
            document.createElement(
                "button"
            );

        deleteButton.className =
            "danger";

        deleteButton.textContent =
            "Delete";

        deleteButton.addEventListener(
            "click",
            async (event) => {
                event.stopPropagation();

                await deleteHistoryChat(
                    chat.id
                );
            }
        );

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

        container.appendChild(row);
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

document.querySelectorAll(".history-item").forEach((button) => {
    button.addEventListener("click", () => {
        loadChat(Number(button.dataset.chatId));
    });
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
