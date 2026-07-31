from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ai.chat_service import (
    generate_chat_response,
)


app = FastAPI(
    title="Neiiu AI Chat",
    version="1.0.0-mvp",
)


class ChatHistoryItem(BaseModel):
    role: Literal[
        "user",
        "assistant",
    ]

    content: str = Field(
        min_length=1,
        max_length=8000,
    )


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=12000,
    )

    mode: Literal[
        "normal",
        "seo",
    ] = "normal"

    history: list[ChatHistoryItem] = Field(
        default_factory=list,
        max_length=12,
    )


@app.get(
    "/",
    response_class=HTMLResponse,
)
def home() -> str:
    return HTML_PAGE


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "Neiiu AI Chat",
    }


@app.post("/api/chat")
def chat(
    request: ChatRequest,
) -> dict:
    try:
        history = [
            item.model_dump()
            for item in request.history
        ]

        return generate_chat_response(
            message=request.message,
            mode=request.mode,
            history=history,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


HTML_PAGE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>Neiiu AI</title>

    <style>
        :root {
            color-scheme: dark;
            --background: #070b14;
            --sidebar: #0b1120;
            --panel: #101827;
            --panel-soft: #131e30;
            --border: #263348;
            --text: #eef4ff;
            --muted: #91a0b8;
            --primary: #7c8cff;
            --primary-strong: #5b6cff;
            --user: #243251;
            --assistant: #111b2c;
            --danger: #ff9a9a;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            overflow: hidden;
            font-family:
                Inter,
                ui-sans-serif,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
            color: var(--text);
            background:
                radial-gradient(
                    circle at 50% -20%,
                    #172554,
                    var(--background) 45%
                );
        }

        button,
        textarea {
            font: inherit;
        }

        .app {
            display: grid;
            grid-template-columns: 270px 1fr;
            height: 100vh;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 22px;
            padding: 22px;
            border-right: 1px solid var(--border);
            background:
                rgba(11, 17, 32, 0.94);
            backdrop-filter: blur(20px);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-icon {
            display: grid;
            width: 42px;
            height: 42px;
            place-items: center;
            border-radius: 14px;
            font-size: 20px;
            font-weight: 900;
            background:
                linear-gradient(
                    135deg,
                    #38bdf8,
                    #6366f1
                );
            box-shadow:
                0 12px 30px
                rgba(99, 102, 241, 0.3);
        }

        .brand-title {
            font-size: 18px;
            font-weight: 850;
        }

        .brand-subtitle {
            margin-top: 2px;
            color: var(--muted);
            font-size: 12px;
        }

        .new-chat {
            width: 100%;
            min-height: 46px;
            border: 1px solid var(--border);
            border-radius: 14px;
            cursor: pointer;
            font-weight: 750;
            color: var(--text);
            background: var(--panel);
        }

        .new-chat:hover {
            border-color: var(--primary);
        }

        .mode-title {
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .mode-list {
            display: grid;
            gap: 8px;
        }

        .mode-button {
            display: flex;
            align-items: center;
            gap: 11px;
            width: 100%;
            padding: 13px;
            border: 1px solid transparent;
            border-radius: 13px;
            cursor: pointer;
            text-align: left;
            color: var(--muted);
            background: transparent;
        }

        .mode-button:hover {
            color: var(--text);
            background: var(--panel);
        }

        .mode-button.active {
            border-color:
                rgba(124, 140, 255, 0.5);
            color: white;
            background:
                rgba(91, 108, 255, 0.18);
        }

        .sidebar-footer {
            margin-top: auto;
            padding: 14px;
            border: 1px solid var(--border);
            border-radius: 14px;
            color: var(--muted);
            font-size: 12px;
            line-height: 1.6;
            background: var(--panel);
        }

        .main {
            display: grid;
            grid-template-rows: auto 1fr auto;
            min-width: 0;
            height: 100vh;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            min-height: 72px;
            padding: 14px 24px;
            border-bottom: 1px solid var(--border);
            background:
                rgba(7, 11, 20, 0.72);
            backdrop-filter: blur(18px);
        }

        .current-mode {
            font-size: 16px;
            font-weight: 800;
        }

        .mode-description {
            margin-top: 3px;
            color: var(--muted);
            font-size: 12px;
        }

        .model-badge {
            padding: 8px 11px;
            border: 1px solid var(--border);
            border-radius: 999px;
            color: var(--muted);
            font-size: 12px;
            background: var(--panel);
        }

        .chat-area {
            overflow-y: auto;
            scroll-behavior: smooth;
        }

        .messages {
            width: min(850px, 92%);
            margin: 0 auto;
            padding: 34px 0 160px;
        }

        .welcome {
            display: grid;
            min-height: 56vh;
            place-items: center;
            text-align: center;
        }

        .welcome-content {
            max-width: 620px;
        }

        .welcome-icon {
            font-size: 48px;
        }

        .welcome h1 {
            margin: 18px 0 10px;
            font-size: clamp(
                32px,
                5vw,
                54px
            );
        }

        .welcome p {
            color: var(--muted);
            line-height: 1.7;
        }

        .suggestions {
            display: grid;
            grid-template-columns:
                repeat(2, minmax(0, 1fr));
            gap: 10px;
            margin-top: 28px;
        }

        .suggestion {
            padding: 15px;
            border: 1px solid var(--border);
            border-radius: 15px;
            cursor: pointer;
            text-align: left;
            color: var(--text);
            background: var(--panel);
        }

        .suggestion:hover {
            border-color: var(--primary);
            transform: translateY(-1px);
        }

        .message-row {
            display: flex;
            margin-bottom: 22px;
        }

        .message-row.user {
            justify-content: flex-end;
        }

        .message-row.assistant {
            justify-content: flex-start;
        }

        .message {
            max-width: min(720px, 88%);
            padding: 15px 18px;
            border: 1px solid var(--border);
            border-radius: 18px;
            line-height: 1.7;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }

        .message-row.user .message {
            border-bottom-right-radius: 6px;
            background: var(--user);
        }

        .message-row.assistant .message {
            border-bottom-left-radius: 6px;
            background: var(--assistant);
        }

        .message-name {
            margin-bottom: 6px;
            color: var(--muted);
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        .typing {
            display: inline-flex;
            gap: 5px;
            align-items: center;
        }

        .typing span {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--muted);
            animation:
                pulse 1.2s infinite ease-in-out;
        }

        .typing span:nth-child(2) {
            animation-delay: 0.15s;
        }

        .typing span:nth-child(3) {
            animation-delay: 0.3s;
        }

        @keyframes pulse {
            0%,
            80%,
            100% {
                opacity: 0.35;
                transform: scale(0.8);
            }

            40% {
                opacity: 1;
                transform: scale(1);
            }
        }

        .composer-wrapper {
            position: fixed;
            right: 0;
            bottom: 0;
            left: 270px;
            padding:
                26px
                max(24px, calc((100vw - 1120px) / 2));
            background:
                linear-gradient(
                    to top,
                    var(--background) 58%,
                    transparent
                );
        }

        .composer {
            display: flex;
            align-items: flex-end;
            gap: 10px;
            width: min(850px, 100%);
            margin: 0 auto;
            padding: 10px 10px 10px 16px;
            border: 1px solid var(--border);
            border-radius: 20px;
            background: var(--panel);
            box-shadow:
                0 20px 60px
                rgba(0, 0, 0, 0.35);
        }

        textarea {
            flex: 1;
            min-height: 46px;
            max-height: 180px;
            resize: none;
            border: none;
            outline: none;
            padding: 12px 4px;
            color: var(--text);
            background: transparent;
        }

        textarea::placeholder {
            color: #65748b;
        }

        .send-button {
            display: grid;
            flex: 0 0 46px;
            width: 46px;
            height: 46px;
            place-items: center;
            border: none;
            border-radius: 14px;
            cursor: pointer;
            color: white;
            font-size: 20px;
            background:
                linear-gradient(
                    135deg,
                    #38bdf8,
                    var(--primary-strong)
                );
        }

        .send-button:disabled {
            cursor: wait;
            opacity: 0.5;
        }

        .composer-note {
            margin: 9px auto 0;
            color: #65748b;
            font-size: 11px;
            text-align: center;
        }

        .error-message {
            color: var(--danger);
        }

        @media (max-width: 760px) {
            .app {
                grid-template-columns: 1fr;
            }

            .sidebar {
                display: none;
            }

            .composer-wrapper {
                left: 0;
                padding-right: 14px;
                padding-left: 14px;
            }

            .suggestions {
                grid-template-columns: 1fr;
            }

            .model-badge {
                display: none;
            }
        }
    </style>
</head>

<body>
    <div class="app">
        <aside class="sidebar">
            <div class="brand">
                <div class="brand-icon">N</div>

                <div>
                    <div class="brand-title">
                        Neiiu AI
                    </div>

                    <div class="brand-subtitle">
                        Local intelligence
                    </div>
                </div>
            </div>

            <button
                id="newChatButton"
                class="new-chat"
                type="button"
            >
                ＋ New chat
            </button>

            <div>
                <div class="mode-title">
                    Select mode
                </div>

                <div class="mode-list">
                    <button
                        class="mode-button active"
                        data-mode="normal"
                        type="button"
                    >
                        <span>💬</span>
                        <span>Normal Mode</span>
                    </button>

                    <button
                        class="mode-button"
                        data-mode="seo"
                        type="button"
                    >
                        <span>📈</span>
                        <span>SEO Expert</span>
                    </button>
                </div>
            </div>

            <div class="sidebar-footer">
                Provider: Ollama<br>
                Model: qwen3:4b-instruct<br>
                Berjalan lokal di komputer.
            </div>
        </aside>

        <main class="main">
            <header class="topbar">
                <div>
                    <div
                        id="currentMode"
                        class="current-mode"
                    >
                        Normal Mode
                    </div>

                    <div
                        id="modeDescription"
                        class="mode-description"
                    >
                        Tanya apa saja kepada Neiiu AI.
                    </div>
                </div>

                <div class="model-badge">
                    Ollama · qwen3:4b-instruct
                </div>
            </header>

            <section
                id="chatArea"
                class="chat-area"
            >
                <div
                    id="messages"
                    class="messages"
                >
                    <div
                        id="welcome"
                        class="welcome"
                    >
                        <div class="welcome-content">
                            <div
                                id="welcomeIcon"
                                class="welcome-icon"
                            >
                                ✨
                            </div>

                            <h1 id="welcomeTitle">
                                Halo, gue Neiiu AI.
                            </h1>

                            <p id="welcomeText">
                                Tanya apa saja. Ganti ke
                                SEO Expert untuk pekerjaan
                                SEO yang lebih fokus.
                            </p>

                            <div
                                id="suggestions"
                                class="suggestions"
                            ></div>
                        </div>
                    </div>
                </div>
            </section>

            <div class="composer-wrapper">
                <form
                    id="chatForm"
                    class="composer"
                >
                    <textarea
                        id="messageInput"
                        rows="1"
                        placeholder="Ketik pesan..."
                        required
                    ></textarea>

                    <button
                        id="sendButton"
                        class="send-button"
                        type="submit"
                        aria-label="Kirim pesan"
                    >
                        ↑
                    </button>
                </form>

                <div class="composer-note">
                    Neiiu AI dapat membuat kesalahan.
                    Periksa kembali informasi penting.
                </div>
            </div>
        </main>
    </div>

    <script>
        const state = {
            mode: "normal",
            history: [],
            loading: false,
        };

        const modeContent = {
            normal: {
                title: "Normal Mode",
                description:
                    "Tanya apa saja kepada Neiiu AI.",
                icon: "✨",
                welcome:
                    "Halo, gue Neiiu AI.",
                text:
                    "Tanya apa saja. Ganti ke SEO Expert "
                    + "untuk pekerjaan SEO yang lebih fokus.",
                suggestions: [
                    "Jelaskan machine learning dengan sederhana",
                    "Bantu gue bikin rencana belajar Python",
                    "Rapikan ide bisnis ini",
                    "Jelaskan kode Python yang error",
                ],
            },

            seo: {
                title: "SEO Expert",
                description:
                    "Mode khusus strategi dan pekerjaan SEO.",
                icon: "📈",
                welcome:
                    "SEO mode aktif.",
                text:
                    "Tanya tentang technical SEO, content, "
                    + "keyword, indexing, landing page, "
                    + "atau strategi optimasi.",
                suggestions: [
                    "Buatkan title dan meta description",
                    "Jelaskan penyebab halaman tidak terindeks",
                    "Buat content brief untuk keyword tertentu",
                    "Audit struktur landing page SEO",
                ],
            },
        };

        const messagesElement =
            document.getElementById(
                "messages"
            );

        const chatArea =
            document.getElementById(
                "chatArea"
            );

        const form =
            document.getElementById(
                "chatForm"
            );

        const input =
            document.getElementById(
                "messageInput"
            );

        const sendButton =
            document.getElementById(
                "sendButton"
            );

        const newChatButton =
            document.getElementById(
                "newChatButton"
            );

        function updateModeUI() {
            const data =
                modeContent[state.mode];

            document.getElementById(
                "currentMode"
            ).textContent =
                data.title;

            document.getElementById(
                "modeDescription"
            ).textContent =
                data.description;

            document.getElementById(
                "welcomeIcon"
            ).textContent =
                data.icon;

            document.getElementById(
                "welcomeTitle"
            ).textContent =
                data.welcome;

            document.getElementById(
                "welcomeText"
            ).textContent =
                data.text;

            document.querySelectorAll(
                ".mode-button"
            ).forEach((button) => {
                button.classList.toggle(
                    "active",
                    button.dataset.mode
                        === state.mode
                );
            });

            renderSuggestions();
        }

        function renderSuggestions() {
            const container =
                document.getElementById(
                    "suggestions"
                );

            container.innerHTML = "";

            for (
                const text
                of modeContent[state.mode]
                    .suggestions
            ) {
                const button =
                    document.createElement(
                        "button"
                    );

                button.className =
                    "suggestion";

                button.type =
                    "button";

                button.textContent =
                    text;

                button.addEventListener(
                    "click",
                    () => {
                        input.value = text;
                        resizeTextarea();
                        input.focus();
                    }
                );

                container.appendChild(
                    button
                );
            }
        }

        function hideWelcome() {
            const welcome =
                document.getElementById(
                    "welcome"
                );

            if (welcome) {
                welcome.remove();
            }
        }

        function addMessage(
            role,
            content,
            isError = false
        ) {
            hideWelcome();

            const row =
                document.createElement(
                    "div"
                );

            row.className =
                `message-row ${role}`;

            const bubble =
                document.createElement(
                    "div"
                );

            bubble.className =
                "message";

            if (isError) {
                bubble.classList.add(
                    "error-message"
                );
            }

            const name =
                document.createElement(
                    "div"
                );

            name.className =
                "message-name";

            name.textContent =
                role === "user"
                    ? "Kanjeng ratu"
                    : (
                        state.mode === "seo"
                            ? "Neiiu AI SEO"
                            : "Neiiu AI"
                    );

            const text =
                document.createElement(
                    "div"
                );

            text.textContent =
                content;

            bubble.appendChild(name);
            bubble.appendChild(text);
            row.appendChild(bubble);
            messagesElement.appendChild(row);

            scrollToBottom();

            return row;
        }

        function addTyping() {
            hideWelcome();

            const row =
                document.createElement(
                    "div"
                );

            row.className =
                "message-row assistant";

            row.id =
                "typingRow";

            const bubble =
                document.createElement(
                    "div"
                );

            bubble.className =
                "message";

            const typing =
                document.createElement(
                    "div"
                );

            typing.className =
                "typing";

            typing.innerHTML =
                "<span></span>"
                + "<span></span>"
                + "<span></span>";

            bubble.appendChild(typing);
            row.appendChild(bubble);
            messagesElement.appendChild(row);

            scrollToBottom();
        }

        function removeTyping() {
            document.getElementById(
                "typingRow"
            )?.remove();
        }

        function scrollToBottom() {
            chatArea.scrollTop =
                chatArea.scrollHeight;
        }

        function resizeTextarea() {
            input.style.height = "auto";

            input.style.height =
                Math.min(
                    input.scrollHeight,
                    180
                ) + "px";
        }

        function resetChat() {
            state.history = [];

            messagesElement.innerHTML = `
                <div
                    id="welcome"
                    class="welcome"
                >
                    <div class="welcome-content">
                        <div
                            id="welcomeIcon"
                            class="welcome-icon"
                        ></div>

                        <h1 id="welcomeTitle"></h1>

                        <p id="welcomeText"></p>

                        <div
                            id="suggestions"
                            class="suggestions"
                        ></div>
                    </div>
                </div>
            `;

            updateModeUI();
            input.value = "";
            resizeTextarea();
            input.focus();
        }

        async function sendMessage(
            message
        ) {
            if (
                !message
                || state.loading
            ) {
                return;
            }

            const previousHistory =
                [...state.history];

            addMessage(
                "user",
                message
            );

            state.history.push({
                role: "user",
                content: message,
            });

            state.loading = true;
            sendButton.disabled = true;
            input.disabled = true;

            addTyping();

            try {
                const response =
                    await fetch(
                        "/api/chat",
                        {
                            method: "POST",
                            headers: {
                                "Content-Type":
                                    "application/json",
                            },
                            body: JSON.stringify({
                                message,
                                mode: state.mode,
                                history:
                                    previousHistory,
                            }),
                        }
                    );

                const data =
                    await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail
                        || "AI gagal menjawab."
                    );
                }

                removeTyping();

                addMessage(
                    "assistant",
                    data.answer
                );

                state.history.push({
                    role: "assistant",
                    content: data.answer,
                });

            } catch (error) {
                removeTyping();

                addMessage(
                    "assistant",
                    `ERROR: ${error.message}`,
                    true
                );

            } finally {
                state.loading = false;
                sendButton.disabled = false;
                input.disabled = false;
                input.focus();
            }
        }

        document.querySelectorAll(
            ".mode-button"
        ).forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    if (state.loading) {
                        return;
                    }

                    state.mode =
                        button.dataset.mode;

                    resetChat();
                }
            );
        });

        newChatButton.addEventListener(
            "click",
            () => {
                if (!state.loading) {
                    resetChat();
                }
            }
        );

        input.addEventListener(
            "input",
            resizeTextarea
        );

        input.addEventListener(
            "keydown",
            (event) => {
                if (
                    event.key === "Enter"
                    && !event.shiftKey
                ) {
                    event.preventDefault();
                    form.requestSubmit();
                }
            }
        );

        form.addEventListener(
            "submit",
            async (event) => {
                event.preventDefault();

                const message =
                    input.value.trim();

                if (!message) {
                    return;
                }

                input.value = "";
                resizeTextarea();

                await sendMessage(
                    message
                );
            }
        );

        updateModeUI();
        input.focus();
    </script>
</body>
</html>
"""