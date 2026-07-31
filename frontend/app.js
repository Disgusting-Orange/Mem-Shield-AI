/**
 * Mem-Shield-AI — ChatGPT Interface & Auto-Medical Classifier Logic
 */

document.addEventListener("DOMContentLoaded", () => {
    // Application State
    const state = {
        userId: "user_default",
        chats: [],
        activeChat: null,
        activeMessages: [],
        medicalMemories: [],
    };

    // DOM Elements
    const elements = {
        btnNewChat: document.getElementById("btn-new-chat"),
        chatHistoryList: document.getElementById("chat-history-list"),
        btnToggleMedicalDrawer: document.getElementById("btn-toggle-medical-drawer"),
        medicalVaultBadgeCount: document.getElementById("medical-vault-badge-count"),
        medicalDrawer: document.getElementById("medical-drawer"),
        btnCloseMedicalDrawer: document.getElementById("btn-close-medical-drawer"),
        drawerMedicalList: document.getElementById("drawer-medical-list"),

        // Canvas & Header
        currentChatTitle: document.getElementById("current-chat-title"),
        currentChatStatus: document.getElementById("current-chat-status"),
        btnLockChatHeader: document.getElementById("btn-lock-chat-header"),
        messagesContainer: document.getElementById("messages-container"),
        welcomeScreen: document.getElementById("welcome-screen"),
        streamList: document.getElementById("stream-list"),
        promptCards: document.querySelectorAll(".prompt-card"),

        // Input
        formChatInput: document.getElementById("form-chat-input"),
        inputChatText: document.getElementById("input-chat-text"),
        btnUploadFile: document.getElementById("btn-upload-file"),

        // Modals
        modalUnlockChat: document.getElementById("modal-unlock-chat"),
        formUnlockChat: document.getElementById("form-unlock-chat"),
        unlockChatId: document.getElementById("unlock-chat-id"),
        unlockPasswordInput: document.getElementById("unlock-password-input"),
        btnForgotPassword: document.getElementById("btn-forgot-password"),

        modalRecoveryDisplay: document.getElementById("modal-recovery-display"),
        displayRecoveryKey: document.getElementById("display-recovery-key"),

        modalResetPassword: document.getElementById("modal-reset-password"),
        formResetPassword: document.getElementById("form-reset-password"),
        resetChatId: document.getElementById("reset-chat-id"),
    };

    function init() {
        setupEventListeners();
        loadChats();
        loadMedicalMemories();
    }

    function setupEventListeners() {
        // New Chat Button
        elements.btnNewChat.addEventListener("click", () => createNewChat());

        // Starter Prompts
        elements.promptCards.forEach(card => {
            card.addEventListener("click", () => {
                const promptText = card.getAttribute("data-prompt");
                if (promptText) {
                    elements.inputChatText.value = promptText;
                    elements.formChatInput.dispatchEvent(new Event("submit"));
                }
            });
        });

        // Medical Drawer Toggle
        elements.btnToggleMedicalDrawer.addEventListener("click", () => {
            elements.medicalDrawer.classList.remove("hidden");
            loadMedicalMemories();
        });
        elements.btnCloseMedicalDrawer.addEventListener("click", () => {
            elements.medicalDrawer.classList.add("hidden");
        });

        // Upload Attachment Button
        elements.btnUploadFile.addEventListener("click", () => {
            const doc = prompt("Enter medical record details or test results to upload & firewall:");
            if (doc) {
                elements.inputChatText.value = doc;
                elements.formChatInput.dispatchEvent(new Event("submit"));
            }
        });

        // Send Message Handler
        elements.formChatInput.addEventListener("submit", async (e) => {
            e.preventDefault();
            const text = elements.inputChatText.value.trim();
            if (!text) return;

            // Ensure active chat session exists
            if (!state.activeChat) {
                await createNewChat("Chat " + new Date().toLocaleTimeString());
            }

            elements.inputChatText.value = "";
            elements.welcomeScreen.classList.add("hidden");
            elements.streamList.classList.remove("hidden");

            // Optimistically add user bubble
            addMessageRow("user", text);

            try {
                const res = await fetch("/vault/chat/message", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        chat_id: state.activeChat.chat_id,
                        sender: "user",
                        text: text
                    })
                });

                const data = await res.json();
                if (!res.ok) {
                    addMessageRow("ai", `🚨 **Blocked by Memory Firewall**\n\n${data.detail.message}`, "threat");
                } else {
                    const badgeType = data.is_medical ? "medical" : "safe";
                    addMessageRow("ai", data.ai_reply, badgeType);

                    if (data.auto_vaulted) {
                        loadMedicalMemories();
                    }
                }
            } catch (err) {
                addMessageRow("ai", "❌ Connection error reaching security proxy.", "threat");
            }
        });

        // Lock Chat Header Button
        elements.btnLockChatHeader.addEventListener("click", async () => {
            if (!state.activeChat) {
                alert("Please start a conversation session first!");
                return;
            }
            const pwd = prompt("Set a passcode to lock this chat session:");
            if (!pwd) return;

            try {
                const res = await fetch("/vault/chat/lock", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ chat_id: state.activeChat.chat_id, password: pwd })
                });

                const data = await res.json();
                if (data.recovery_key) {
                    elements.displayRecoveryKey.textContent = data.recovery_key;
                    openModal("modalRecoveryDisplay");
                }
                loadChats();
            } catch (err) {
                alert("Error locking chat session.");
            }
        });

        // Unlock Chat Form (PIN Modal)
        elements.formUnlockChat.addEventListener("submit", async (e) => {
            e.preventDefault();
            const chatId = elements.unlockChatId.value;
            const password = elements.unlockPasswordInput.value;

            try {
                const res = await fetch("/vault/chat/unlock", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ chat_id: chatId, password: password })
                });

                const data = await res.json();
                if (!res.ok) {
                    alert(`❌ ${data.detail.message || "Incorrect Passcode"}`);
                } else {
                    closeModal("modalUnlockChat");
                    state.activeMessages = data.messages || [];
                    renderActiveChatSession(chatId);
                }
            } catch (err) {
                alert("Error unlocking chat.");
            }
        });

        // Forgot Password Button
        elements.btnForgotPassword.addEventListener("click", () => {
            const chatId = elements.unlockChatId.value;
            closeModal("modalUnlockChat");
            elements.resetChatId.value = chatId;
            openModal("modalResetPassword");
        });

        // Reset Password Form
        elements.formResetPassword.addEventListener("submit", async (e) => {
            e.preventDefault();
            const chatId = elements.resetChatId.value;
            const recoveryKey = document.getElementById("reset-recovery-key").value;
            const newPassword = document.getElementById("reset-new-password").value;

            try {
                const res = await fetch("/vault/chat/reset-password", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        chat_id: chatId,
                        recovery_key: recoveryKey,
                        new_password: newPassword
                    })
                });

                const data = await res.json();
                if (!res.ok) {
                    alert(`❌ Reset Failed: ${data.detail.message}`);
                } else {
                    alert("🎉 Passcode Reset Successful! You can now unlock your chat.");
                    closeModal("modalResetPassword");
                    elements.formResetPassword.reset();
                }
            } catch (err) {
                alert("Error resetting passcode.");
            }
        });

        // Close Modals
        document.querySelectorAll(".btn-close-modal").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
            });
        });
    }

    async function createNewChat(customTitle) {
        const title = customTitle || "Chat " + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        try {
            const res = await fetch("/vault/chat/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: state.userId, title: title })
            });

            const data = await res.json();
            await loadChats();
            const newChat = state.chats.find(c => c.chat_id === data.chat.chat_id);
            if (newChat) selectChatSession(newChat);
        } catch (err) {
            console.error("Error creating chat", err);
        }
    }

    async function loadChats() {
        try {
            const res = await fetch(`/vault/chat/all?user_id=${state.userId}`);
            const data = await res.json();
            state.chats = data.chats || [];
            renderSidebarChats();
        } catch (err) {
            console.error("Error loading chat sessions", err);
        }
    }

    function renderSidebarChats() {
        const list = elements.chatHistoryList;
        if (!state.chats.length) {
            list.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); padding: 8px;">No chat history yet.</div>`;
            return;
        }

        list.innerHTML = state.chats.map(c => `
            <div class="chat-history-item ${state.activeChat && state.activeChat.chat_id === c.chat_id ? 'active' : ''}" data-id="${c.chat_id}">
                <div style="display: flex; align-items: center; gap: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    <i class="fa-solid ${c.is_locked ? 'fa-lock text-rose' : 'fa-message'}"></i>
                    <span>${escapeHtml(c.title)}</span>
                </div>
            </div>
        `).join("");

        list.querySelectorAll(".chat-history-item").forEach(item => {
            item.addEventListener("click", () => {
                const chatId = item.getAttribute("data-id");
                const chat = state.chats.find(c => c.chat_id === chatId);
                if (chat) selectChatSession(chat);
            });
        });
    }

    function selectChatSession(chat) {
        state.activeChat = chat;
        renderSidebarChats();

        if (chat.is_locked) {
            elements.unlockChatId.value = chat.chat_id;
            elements.unlockPasswordInput.value = "";
            openModal("modalUnlockChat");
        } else {
            fetchUnlockedMessages(chat.chat_id);
        }
    }

    async function fetchUnlockedMessages(chatId) {
        try {
            const res = await fetch("/vault/chat/unlock", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_id: chatId, password: "" })
            });

            const data = await res.json();
            state.activeMessages = data.messages || [];
            renderActiveChatSession(chatId);
        } catch (err) {
            console.error("Failed fetching unlocked messages", err);
        }
    }

    function renderActiveChatSession(chatId) {
        const chat = state.chats.find(c => c.chat_id === chatId);
        if (!chat) return;

        elements.currentChatTitle.textContent = chat.title;
        elements.currentChatStatus.innerHTML = chat.is_locked
            ? `<i class="fa-solid fa-lock text-rose"></i> Locked (Decrypted Session)`
            : `<i class="fa-solid fa-lock-open text-emerald"></i> Unlocked Session`;

        if (!state.activeMessages.length) {
            elements.welcomeScreen.classList.remove("hidden");
            elements.streamList.classList.add("hidden");
        } else {
            elements.welcomeScreen.classList.add("hidden");
            elements.streamList.classList.remove("hidden");
            elements.streamList.innerHTML = "";
            state.activeMessages.forEach(m => {
                addMessageRow(m.sender === "user" ? "user" : "ai", m.text);
            });
        }
    }

    function addMessageRow(sender, text, badgeType) {
        const list = elements.streamList;
        const row = document.createElement("div");
        row.className = "msg-row";

        let badgeHtml = "";
        if (badgeType === "medical") {
            badgeHtml = `<div class="msg-badge-tag medical"><i class="fa-solid fa-heart-pulse"></i> 🏥 Auto-Saved to Medical Vault</div>`;
        } else if (badgeType === "safe") {
            badgeHtml = `<div class="msg-badge-tag safe"><i class="fa-solid fa-shield-halved"></i> 🛡️ Verified Safe by Memory Firewall</div>`;
        } else if (badgeType === "threat") {
            badgeHtml = `<div class="msg-badge-tag threat"><i class="fa-solid fa-triangle-exclamation"></i> 🚨 Memory Firewall Blocked</div>`;
        }

        row.innerHTML = `
            <div class="msg-avatar ${sender}">
                <i class="fa-solid ${sender === 'user' ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="msg-content">
                ${badgeHtml}
                <div>${formatMessageText(text)}</div>
            </div>
        `;

        list.appendChild(row);
        elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
    }

    async function loadMedicalMemories() {
        try {
            const res = await fetch(`/vault/personal/list?user_id=${state.userId}&category=medical`);
            const data = await res.json();
            state.medicalMemories = data.memories || [];
            renderMedicalDrawerList();
            elements.medicalVaultBadgeCount.textContent = `${state.medicalMemories.length} Auto-Saved`;
        } catch (err) {
            console.error("Error loading medical vault", err);
        }
    }

    function renderMedicalDrawerList() {
        const list = elements.drawerMedicalList;
        if (!state.medicalMemories.length) {
            list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-box-open"></i><p>No medical records auto-vaulted yet. Mention symptoms or blood tests in chat!</p></div>`;
            return;
        }

        list.innerHTML = state.medicalMemories.map(m => `
            <div class="memory-item-card" style="margin-bottom: 8px;">
                <div class="memory-item-header">
                    <h4 style="font-size: 13px; color: var(--emerald);">${escapeHtml(m.title)}</h4>
                    <span class="badge badge-success">Score ${m.threat_score}</span>
                </div>
                <div class="memory-item-body">
                    <p style="font-size: 12px;">${escapeHtml(m.content)}</p>
                    <span style="font-size: 10px; color: var(--text-muted); display: block; margin-top: 4px;">${new Date(m.created_at * 1000).toLocaleString()}</span>
                </div>
            </div>
        `).join("");
    }

    function openModal(modalId) {
        const m = elements[modalId];
        if (m) m.classList.remove("hidden");
    }

    function closeModal(modalId) {
        const m = elements[modalId];
        if (m) m.classList.add("hidden");
    }

    function formatMessageText(str) {
        return (str || "").replace(/\n/g, "<br>");
    }

    function escapeHtml(str) {
        return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    init();
});
