/**
 * Mem-Shield-AI — Frontend Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
    // Current State
    const state = {
        userId: "user_default",
        activeTab: "tab-dashboard",
        memories: [],
        chats: [],
        activeChat: null,
        activeChatUnlockedMessages: null,
        auditLogs: [],
    };

    // DOM Elements
    const elements = {
        navButtons: document.querySelectorAll(".nav-menu .nav-item"),
        tabPages: document.querySelectorAll(".tab-page"),
        pageTitle: document.getElementById("page-title"),
        pageDesc: document.getElementById("page-desc"),
        btnRefresh: document.getElementById("btn-refresh-data"),
        
        // Dashboard
        metricLoops: document.getElementById("metric-loops"),
        metricFailures: document.getElementById("metric-failures"),
        metricCost: document.getElementById("metric-cost"),
        dashboardAuditFeed: document.getElementById("dashboard-audit-feed"),
        statMemoriesCount: document.getElementById("stat-memories-count"),
        statChatsCount: document.getElementById("stat-chats-count"),

        // Personal Memories
        formUploadMemory: document.getElementById("form-upload-memory"),
        personalMemoryList: document.getElementById("personal-memory-list"),
        memoryFilters: document.querySelectorAll("#memory-category-filters .pill"),

        // Private Chats
        chatSessionsList: document.getElementById("chat-sessions-list"),
        btnOpenCreateChat: document.getElementById("btn-open-create-chat"),
        chatViewPlaceholder: document.getElementById("chat-view-placeholder"),
        chatActiveBox: document.getElementById("chat-active-box"),
        activeChatTitle: document.getElementById("active-chat-title"),
        activeChatStatus: document.getElementById("active-chat-status"),
        btnLockCurrentChat: document.getElementById("btn-lock-current-chat"),
        chatMessagesScroll: document.getElementById("chat-messages-scroll"),
        formSendMessage: document.getElementById("form-send-message"),
        inputChatMessage: document.getElementById("input-chat-message"),

        // Modals
        modalCreateChat: document.getElementById("modal-create-chat"),
        formCreateChat: document.getElementById("form-create-chat"),
        modalUnlockChat: document.getElementById("modal-unlock-chat"),
        formUnlockChat: document.getElementById("form-unlock-chat"),
        unlockPasswordInput: document.getElementById("unlock-password-input"),
        unlockChatId: document.getElementById("unlock-chat-id"),
        btnForgotPassword: document.getElementById("btn-forgot-password"),
        modalRecoveryDisplay: document.getElementById("modal-recovery-display"),
        displayRecoveryKey: document.getElementById("display-recovery-key"),
        modalResetPassword: document.getElementById("modal-reset-password"),
        formResetPassword: document.getElementById("form-reset-password"),
        resetChatId: document.getElementById("reset-chat-id"),

        // Sandbox Forms
        formSandboxFirewall: document.getElementById("form-sandbox-firewall"),
        sbFwResult: document.getElementById("sb-fw-result"),
        formSandboxGuardian: document.getElementById("form-sandbox-guardian"),
        sbGdResult: document.getElementById("sb-gd-result"),
    };

    // Tab Navigation Configuration
    const tabHeaders = {
        "tab-dashboard": { title: "Security Dashboard", desc: "Real-time threat monitoring, graph loops, and agent inspection" },
        "tab-medical": { title: "Medical & Personal Memory Vault", desc: "Firewall-inspected safe storage for clinical notes & user context" },
        "tab-chats": { title: "Private Locked Chats", desc: "PBKDF2 encrypted chat threads backed by isolated private_vault.db" },
        "tab-sandbox": { title: "Firewall Security Sandbox", desc: "Test prompt injections, memory poisoning, and reasoning loops" },
    };

    function init() {
        setupEventListeners();
        loadAllData();
    }

    function setupEventListeners() {
        // Navigation Tabs
        elements.navButtons.forEach(btn => {
            btn.addEventListener("click", () => {
                const targetTab = btn.getAttribute("data-tab");
                switchTab(targetTab);
            });
        });

        // Refresh Button
        elements.btnRefresh.addEventListener("click", () => loadAllData());

        // Category Filter Pills
        elements.memoryFilters.forEach(pill => {
            pill.addEventListener("click", () => {
                elements.memoryFilters.forEach(p => p.classList.remove("active"));
                pill.classList.add("active");
                const filter = pill.getAttribute("data-filter");
                renderPersonalMemories(filter);
            });
        });

        // Upload Personal Memory Form
        elements.formUploadMemory.addEventListener("submit", async (e) => {
            e.preventDefault();
            const category = document.getElementById("mem-category").value;
            const title = document.getElementById("mem-title").value;
            const content = document.getElementById("mem-content").value;

            const btnSave = document.getElementById("btn-save-memory");
            btnSave.disabled = true;
            btnSave.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scanning with Firewall...`;

            try {
                const res = await fetch("/vault/personal/write", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        user_id: state.userId,
                        category: category,
                        title: title,
                        content: content
                    })
                });

                const data = await res.json();
                if (!res.ok) {
                    alert(`❌ REJECTED BY FIREWALL (Score: ${data.detail.score}/100)\n\nReasons:\n${data.detail.reasons.join('\n')}`);
                    addAuditLog(`Memory write REJECTED for '${title}'`, "danger", data.detail.score);
                } else {
                    alert(`✅ ACCEPTED BY FIREWALL (Score: ${data.memory.threat_score}/100)\nRecord saved safely to vault!`);
                    addAuditLog(`Memory write ACCEPTED for '${title}'`, "success", data.memory.threat_score);
                    elements.formUploadMemory.reset();
                    loadPersonalMemories();
                }
            } catch (err) {
                alert("Error connecting to server.");
            } finally {
                btnSave.disabled = false;
                btnSave.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> Scan & Save to Safe Vault`;
            }
        });

        // Create Chat Modal
        elements.btnOpenCreateChat.addEventListener("click", () => openModal("modalCreateChat"));
        
        elements.formCreateChat.addEventListener("submit", async (e) => {
            e.preventDefault();
            const title = document.getElementById("create-chat-title").value;
            const password = document.getElementById("create-chat-pwd").value || null;

            try {
                const res = await fetch("/vault/chat/create", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        user_id: state.userId,
                        title: title,
                        password: password
                    })
                });

                const data = await res.json();
                closeModal("modalCreateChat");
                elements.formCreateChat.reset();

                if (data.recovery_key) {
                    elements.displayRecoveryKey.textContent = data.recovery_key;
                    openModal("modalRecoveryDisplay");
                }

                loadChats();
            } catch (err) {
                alert("Error creating chat session.");
            }
        });

        // Unlock Chat Form (PIN Pad Modal)
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
                    alert(`❌ Unlock Failed: ${data.detail.message || "Invalid password"}`);
                } else {
                    closeModal("modalUnlockChat");
                    state.activeChatUnlockedMessages = data.messages;
                    renderActiveChat(chatId, true);
                }
            } catch (err) {
                alert("Error unlocking chat.");
            }
        });

        // Forgot Password Button inside Unlock Modal
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
                    alert("🎉 Password Reset Successful! You can now unlock your chat with your new password.");
                    closeModal("modalResetPassword");
                    elements.formResetPassword.reset();
                }
            } catch (err) {
                alert("Error resetting password.");
            }
        });

        // Lock Current Chat Button
        elements.btnLockCurrentChat.addEventListener("click", async () => {
            if (!state.activeChat) return;
            const pwd = prompt("Enter a password to lock this chat session:");
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
                state.activeChat = null;
                elements.chatActiveBox.classList.add("hidden");
                elements.chatViewPlaceholder.classList.remove("hidden");
            } catch (err) {
                alert("Error locking chat.");
            }
        });

        // Send Message Form
        elements.formSendMessage.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!state.activeChat) return;

            const text = elements.inputChatMessage.value;
            elements.inputChatMessage.value = "";

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
                    alert(`⚠️ ${data.detail.message}`);
                } else {
                    // Update active view
                    state.activeChatUnlockedMessages.push({ sender: "user", text: text, timestamp: Date.now()/1000 });
                    renderChatMessages(state.activeChatUnlockedMessages);
                }
            } catch (err) {
                alert("Failed to send message.");
            }
        });

        // Close Modal Handlers
        document.querySelectorAll(".btn-close-modal").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".modal-overlay").forEach(m => m.classList.add("hidden"));
            });
        });

        // Sandbox Forms
        elements.formSandboxFirewall.addEventListener("submit", async (e) => {
            e.preventDefault();
            const key = document.getElementById("sb-fw-key").value;
            const val = document.getElementById("sb-fw-val").value;

            try {
                const res = await fetch("/memory/write", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ agent_id: "sandbox-agent", key: key, value: val })
                });

                const data = await res.json();
                elements.sbFwResult.classList.remove("hidden");
                if (res.ok) {
                    elements.sbFwResult.innerHTML = `<div class="security-banner" style="border-color: var(--emerald)"><i class="fa-solid fa-circle-check text-emerald"></i><div><strong>ACCEPTED (Score: ${data.score}/100)</strong><p>${data.reasons.join('; ')}</p></div></div>`;
                } else {
                    elements.sbFwResult.innerHTML = `<div class="security-banner" style="border-color: var(--rose)"><i class="fa-solid fa-triangle-exclamation text-rose"></i><div><strong>REJECTED (Score: ${data.detail.score}/100)</strong><p>${data.detail.reasons.join('; ')}</p></div></div>`;
                }
            } catch (err) {
                alert("Sandbox evaluation error.");
            }
        });

        elements.formSandboxGuardian.addEventListener("submit", async (e) => {
            e.preventDefault();
            const action = document.getElementById("sb-gd-action").value;
            const payload = document.getElementById("sb-gd-payload").value;

            try {
                const res = await fetch("/agent/step", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        agent_id: "sandbox-agent",
                        step_id: `step-${Date.now().toString().slice(-4)}`,
                        action: action,
                        status: "success",
                        result_payload: payload,
                        cost_estimate: 0.001
                    })
                });

                const data = await res.json();
                elements.sbGdResult.classList.remove("hidden");
                elements.sbGdResult.innerHTML = `<pre style="background: rgba(0,0,0,0.6); padding: 12px; border-radius: 8px; font-size: 12px; color: var(--sky);">${JSON.stringify(data, null, 2)}</pre>`;
                
                // Update metrics
                if (data.loops.length) elements.metricLoops.textContent = `${data.loops.length} Cycles`;
                if (data.silent_failures.length) elements.metricFailures.textContent = `${data.silent_failures.length} Flagged`;
                if (data.estimated_cost_leak) elements.metricCost.textContent = `$${data.estimated_cost_leak.toFixed(4)}`;
            } catch (err) {
                alert("Guardian step error.");
            }
        });
    }

    function switchTab(tabId) {
        state.activeTab = tabId;
        elements.navButtons.forEach(btn => {
            btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
        });
        elements.tabPages.forEach(page => {
            page.classList.toggle("active", page.id === tabId);
        });

        if (tabHeaders[tabId]) {
            elements.pageTitle.textContent = tabHeaders[tabId].title;
            elements.pageDesc.textContent = tabHeaders[tabId].desc;
        }
    }

    async function loadAllData() {
        await Promise.all([loadPersonalMemories(), loadChats()]);
    }

    async function loadPersonalMemories() {
        try {
            const res = await fetch(`/vault/personal/list?user_id=${state.userId}`);
            const data = await res.json();
            state.memories = data.memories || [];
            renderPersonalMemories("all");
            elements.statMemoriesCount.textContent = `${state.memories.length} Stored Records`;
        } catch (err) {
            console.error("Error loading memories:", err);
        }
    }

    function renderPersonalMemories(filter) {
        const list = elements.personalMemoryList;
        const filtered = filter === "all" ? state.memories : state.memories.filter(m => m.category === filter);

        if (!filtered.length) {
            list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-box-open"></i><p>No records found in category '${filter}'.</p></div>`;
            return;
        }

        list.innerHTML = filtered.map(m => `
            <div class="memory-item-card">
                <div class="memory-item-header">
                    <h4>${escapeHtml(m.title)}</h4>
                    <span class="badge badge-success"><i class="fa-solid fa-shield"></i> Score ${m.threat_score}</span>
                </div>
                <div class="memory-item-body">
                    <p>${escapeHtml(m.content)}</p>
                    <span style="font-size: 11px; color: var(--text-dim); margin-top: 6px; display: block;">Category: ${m.category.toUpperCase()} • ${new Date(m.created_at * 1000).toLocaleTimeString()}</span>
                </div>
            </div>
        `).join("");
    }

    async function loadChats() {
        try {
            const res = await fetch(`/vault/chat/all?user_id=${state.userId}`);
            const data = await res.json();
            state.chats = data.chats || [];
            renderChatsList();
            elements.statChatsCount.textContent = `${state.chats.filter(c => c.is_locked).length} Locked Chats`;
        } catch (err) {
            console.error("Error loading chats:", err);
        }
    }

    function renderChatsList() {
        const list = elements.chatSessionsList;
        if (!state.chats.length) {
            list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-comments"></i><p>No chat sessions found.</p></div>`;
            return;
        }

        list.innerHTML = state.chats.map(c => `
            <div class="chat-session-item" data-id="${c.chat_id}">
                <div class="memory-item-header">
                    <h4>${escapeHtml(c.title)}</h4>
                    <span class="badge ${c.is_locked ? 'badge-danger' : 'badge-info'}">
                        <i class="fa-solid ${c.is_locked ? 'fa-lock' : 'fa-unlock'}"></i>
                        ${c.is_locked ? 'LOCKED' : 'PUBLIC'}
                    </span>
                </div>
            </div>
        `).join("");

        // Attach click listeners to list items
        list.querySelectorAll(".chat-session-item").forEach(item => {
            item.addEventListener("click", () => {
                const chatId = item.getAttribute("data-id");
                const chat = state.chats.find(c => c.chat_id === chatId);
                if (chat) selectChat(chat);
            });
        });
    }

    function selectChat(chat) {
        state.activeChat = chat;
        if (chat.is_locked) {
            elements.unlockChatId.value = chat.chat_id;
            elements.unlockPasswordInput.value = "";
            openModal("modalUnlockChat");
        } else {
            // Unlocked chat — fetch directly
            fetchUnlockedChatMessages(chat.chat_id);
        }
    }

    async function fetchUnlockedChatMessages(chatId) {
        try {
            const res = await fetch("/vault/chat/unlock", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ chat_id: chatId, password: "" })
            });

            const data = await res.json();
            state.activeChatUnlockedMessages = data.messages || [];
            renderActiveChat(chatId, false);
        } catch (err) {
            console.error("Failed to fetch unlocked chat", err);
        }
    }

    function renderActiveChat(chatId, isLocked) {
        elements.chatViewPlaceholder.classList.add("hidden");
        elements.chatActiveBox.classList.remove("hidden");

        const chat = state.chats.find(c => c.chat_id === chatId);
        if (chat) {
            elements.activeChatTitle.textContent = chat.title;
            elements.activeChatStatus.innerHTML = isLocked
                ? `<i class="fa-solid fa-lock text-rose"></i> Decrypted Session`
                : `<i class="fa-solid fa-unlock text-emerald"></i> Public Session`;
        }

        renderChatMessages(state.activeChatUnlockedMessages || []);
    }

    function renderChatMessages(messages) {
        const scroll = elements.chatMessagesScroll;
        if (!messages.length) {
            scroll.innerHTML = `<div class="empty-state"><i class="fa-solid fa-message"></i><p>No messages in this chat session yet. Type below!</p></div>`;
            return;
        }

        scroll.innerHTML = messages.map(m => `
            <div class="chat-msg ${m.sender === 'user' ? 'user' : 'system'}">
                ${escapeHtml(m.text)}
            </div>
        `).join("");

        scroll.scrollTop = scroll.scrollHeight;
    }

    function openModal(modalId) {
        const m = elements[modalId];
        if (m) m.classList.remove("hidden");
    }

    function closeModal(modalId) {
        const m = elements[modalId];
        if (m) m.classList.add("hidden");
    }

    function addAuditLog(text, type, score) {
        const feed = elements.dashboardAuditFeed;
        if (feed.querySelector(".empty-state")) feed.innerHTML = "";

        const div = document.createElement("div");
        div.className = "security-banner";
        div.style.marginBottom = "8px";
        div.style.borderColor = type === "danger" ? "var(--rose)" : "var(--emerald)";
        div.innerHTML = `<i class="fa-solid ${type === 'danger' ? 'fa-triangle-exclamation text-rose' : 'fa-circle-check text-emerald'}"></i><div><strong>${text}</strong><p>Score: ${score}/100 • ${new Date().toLocaleTimeString()}</p></div>`;

        feed.prepend(div);
    }

    function escapeHtml(str) {
        return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    init();
});
