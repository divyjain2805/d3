const isLocalDevelopment = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const API_BASE = isLocalDevelopment ? "http://127.0.0.1:8001" : window.location.origin;

const form = document.querySelector("#chat-form");
const input = document.querySelector("#question-input");
const sendButton = document.querySelector("#send-button");
const conversation = document.querySelector("#conversation");
const suggestions = document.querySelector("#suggestions");
const connectionLabel = document.querySelector("#connection-label");
const connectionDot = document.querySelector("#connection-dot");
const topStatusText = document.querySelector("#top-status-text");
const topStatusDot = document.querySelector("#top-status-dot");
const accessDialog = document.querySelector("#access-dialog");
const accessForm = document.querySelector("#access-form");
const accessInput = document.querySelector("#access-token");
const accessError = document.querySelector("#access-error");
const requiresAccessToken = !isLocalDevelopment;
let accessToken = "";
let pendingQuestion = "";

if (requiresAccessToken) {
    accessDialog.showModal();
}

accessDialog.addEventListener("cancel", (event) => {
    if (requiresAccessToken) event.preventDefault();
});

accessForm.addEventListener("submit", (event) => {
    event.preventDefault();
    accessToken = accessInput.value.trim();
    accessInput.value = "";
    accessError.hidden = true;
    accessDialog.close();
    const question = pendingQuestion;
    pendingQuestion = "";
    if (question) sendQuestion(question, true);
});

function setConnectionState(isOnline) {
    const label = isOnline ? "Assistant connected" : "Assistant unavailable";
    connectionLabel.textContent = label;
    topStatusText.textContent = isOnline ? "Connected" : "Offline";
    connectionDot.classList.toggle("is-online", isOnline);
    connectionDot.classList.toggle("is-offline", !isOnline);
    topStatusDot.classList.toggle("is-online", isOnline);
    topStatusDot.classList.toggle("is-offline", !isOnline);
}

function addMessage({ text, role, error = false, typing = false }) {
    const message = document.createElement("div");
    message.className = `message ${role}-message${error ? " error-message" : ""}`;
    if (typing) message.id = "typing-message";

    if (role === "assistant") {
        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.textContent = error ? "!" : "d.";
        message.append(avatar);
    }

    const content = document.createElement("div");
    content.className = "message-content";

    if (role === "assistant") {
        const meta = document.createElement("div");
        meta.className = "message-meta";
        const name = document.createElement("strong");
        name.textContent = error ? "Connection issue" : "Candidate assistant";
        const time = document.createElement("span");
        time.textContent = typing ? "Writing an answer" : "Just now";
        meta.append(name, time);
        content.append(meta);
    }

    if (typing) {
        const indicator = document.createElement("div");
        indicator.className = "typing-indicator";
        indicator.setAttribute("aria-label", "Assistant is writing");
        for (let dot = 0; dot < 3; dot += 1) indicator.append(document.createElement("span"));
        content.append(indicator);
    } else {
        const paragraph = document.createElement("p");
        paragraph.textContent = text;
        content.append(paragraph);
    }

    message.append(content);
    conversation.append(message);
    message.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return message;
}

async function checkConnection() {
    try {
        const response = await fetch(`${API_BASE}/`);
        setConnectionState(response.ok);
    } catch {
        setConnectionState(false);
    }
}

async function sendQuestion(question, alreadyDisplayed = false) {
    const cleanQuestion = question.trim();
    if (!cleanQuestion || sendButton.disabled) return;

    if (requiresAccessToken && !accessToken) {
        pendingQuestion = cleanQuestion;
        if (!accessDialog.open) accessDialog.showModal();
        accessInput.focus();
        return;
    }

    suggestions.hidden = true;
    if (!alreadyDisplayed) addMessage({ text: cleanQuestion, role: "user" });
    input.value = "";
    input.style.height = "auto";
    sendButton.disabled = true;
    const typingMessage = addMessage({ role: "assistant", typing: true });

    try {
        const headers = { "Content-Type": "application/json" };
        if (requiresAccessToken) headers.Authorization = `Bearer ${accessToken}`;
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers,
            body: JSON.stringify({ question: cleanQuestion }),
        });

        if (response.status === 401 && requiresAccessToken) {
            accessToken = "";
            pendingQuestion = cleanQuestion;
            typingMessage.remove();
            accessError.textContent = "That token was not accepted. Try again.";
            accessError.hidden = false;
            window.setTimeout(() => {
                accessDialog.showModal();
                accessInput.focus();
            }, 0);
            return;
        }

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const detail = typeof payload.detail === "string" ? ` ${payload.detail}` : "";
            throw new Error(`The backend returned ${response.status}.${detail}`);
        }
        if (typeof payload.answer !== "string" || !payload.answer.trim()) {
            throw new Error("The backend response did not include an answer.");
        }

        typingMessage.remove();
        addMessage({ text: payload.answer, role: "assistant" });
        setConnectionState(true);
    } catch (error) {
        typingMessage.remove();
        const message = error instanceof TypeError
            ? "Could not reach the backend. Check that it is running and allows requests from this frontend."
            : error.message;
        addMessage({ text: message, role: "assistant", error: true });
        setConnectionState(false);
    } finally {
        sendButton.disabled = false;
        input.focus();
    }
}

form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendQuestion(input.value);
});

input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
});

input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
    }
});

suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-question]");
    if (button) sendQuestion(button.dataset.question);
});

checkConnection();