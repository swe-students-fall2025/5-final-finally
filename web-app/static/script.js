let currentConversationId = null;
let mediaRecorder = null;
let audioChunks = [];
let currentDiaryId = null;

// Voice input for preferences
let voiceInputRecorder = null;
let voiceInputChunks = [];

// Diary preferences
let diaryPreferences = {
    theme: null,
    style: null,
    custom_instructions: null
};

function setConversationStatus(text) {
    const el = document.getElementById("conversation-status");
    if (el) el.textContent = text;
}

function appendMessage(role, text) {
    const box = document.getElementById("conversation");
    if (!box) return;
    const row = document.createElement("div");
    row.className = "msg " + role;
    row.textContent = text;
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
}

function setRecordingButtons(options) {
    const startBtn = document.getElementById("start-recording-btn");
    const stopBtn = document.getElementById("stop-recording-btn");
    const finishBtn = document.getElementById("finish-conversation-btn");
    const prefsBtn = document.getElementById("open-preferences-btn");

    if (startBtn) startBtn.disabled = !options.canRecord;
    if (stopBtn) stopBtn.disabled = !options.canStop;
    if (finishBtn) finishBtn.disabled = !options.canComplete;
    if (prefsBtn) prefsBtn.disabled = !options.canComplete;
}

function moodToEmoji(mood) {
    if (mood === "positive") return "😄 Positive";
    if (mood === "negative") return "😔 Negative";
    return "😐 Neutral";
}

// ----------------- Preferences Modal -----------------

function openPreferencesModal() {
    const modal = document.getElementById("preferences-modal");
    if (modal) {
        modal.classList.remove("hidden");
        document.getElementById("diary-theme").value = diaryPreferences.theme || "";
        document.getElementById("diary-style").value = diaryPreferences.style || "";
        document.getElementById("custom-instructions").value = diaryPreferences.custom_instructions || "";
    }
}

function closePreferencesModal() {
    const modal = document.getElementById("preferences-modal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

function savePreferences() {
    const theme = document.getElementById("diary-theme").value;
    const style = document.getElementById("diary-style").value;
    const customInstructions = document.getElementById("custom-instructions").value.trim();

    diaryPreferences = {
        theme: theme || null,
        style: style || null,
        custom_instructions: customInstructions || null
    };

    closePreferencesModal();
    
    const hasPrefs = theme || style || customInstructions;
    if (hasPrefs) {
        setConversationStatus("Diary settings saved. Ready to generate.");
    } else {
        setConversationStatus("Using default settings. Ready to generate.");
    }
}

function resetPreferences() {
    document.getElementById("diary-theme").value = "";
    document.getElementById("diary-style").value = "";
    document.getElementById("custom-instructions").value = "";
    diaryPreferences = {
        theme: null,
        style: null,
        custom_instructions: null
    };
}

function applyTemplate(template) {
    const textarea = document.getElementById("custom-instructions");
    if (textarea) {
        const currentText = textarea.value.trim();
        if (currentText) {
            textarea.value = currentText + "\n" + template;
        } else {
            textarea.value = template;
        }
    }
}

// ----------------- Voice Input for Preferences -----------------

async function startVoiceInput() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        document.getElementById("voice-input-status").textContent = "Not supported";
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        voiceInputRecorder = new MediaRecorder(stream);
        voiceInputChunks = [];

        voiceInputRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                voiceInputChunks.push(e.data);
            }
        };

        voiceInputRecorder.onstop = async () => {
            const blob = new Blob(voiceInputChunks, { type: "audio/webm" });
            await transcribeVoiceInput(blob);
        };

        voiceInputRecorder.start();
        
        document.getElementById("start-voice-input-btn").classList.add("hidden");
        document.getElementById("stop-voice-input-btn").classList.remove("hidden");
        document.getElementById("voice-input-status").textContent = "Recording...";
    } catch (err) {
        console.error(err);
        document.getElementById("voice-input-status").textContent = "Failed to start";
    }
}

function stopVoiceInput() {
    if (voiceInputRecorder && voiceInputRecorder.state === "recording") {
        voiceInputRecorder.stop();
        document.getElementById("start-voice-input-btn").classList.remove("hidden");
        document.getElementById("stop-voice-input-btn").classList.add("hidden");
        document.getElementById("voice-input-status").textContent = "Processing...";
    }
}

async function transcribeVoiceInput(blob) {
    try {
        const fd = new FormData();
        fd.append("audio", blob, "voice-input.webm");

        const res = await fetch("/api/transcribe", {
            method: "POST",
            body: fd,
        });

        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }

        if (res.ok) {
            const data = await res.json();
            const text = data.text || "";
            
            if (text) {
                const textarea = document.getElementById("custom-instructions");
                const currentText = textarea.value.trim();
                if (currentText) {
                    textarea.value = currentText + " " + text;
                } else {
                    textarea.value = text;
                }
                document.getElementById("voice-input-status").textContent = "Added!";
            } else {
                document.getElementById("voice-input-status").textContent = "No speech detected";
            }
        } else {
            document.getElementById("voice-input-status").textContent = "Transcription failed";
        }
    } catch (err) {
        console.error(err);
        document.getElementById("voice-input-status").textContent = "Error";
    }

    setTimeout(() => {
        document.getElementById("voice-input-status").textContent = "";
    }, 2000);
}

// ----------------- Chat / conversation -----------------

async function startConversation() {
    setConversationStatus("Starting conversation...");
    const box = document.getElementById("conversation");
    if (box) box.innerHTML = "";
    // Reset preferences for new conversation
    resetPreferences();

    const rightCard = document.querySelector('.chat-right');
    if (rightCard) {
        rightCard.classList.add('hidden');
    }

    const leftCard = document.querySelector('.chat-left');
    if (leftCard) {
        leftCard.classList.remove('normal-width');
        leftCard.classList.add('full-width');
    }

    const titleEl = document.getElementById("diary-title-chat");
    const dateEl = document.getElementById("diary-date-chat");
    const moodEl = document.getElementById("diary-mood-chat");
    const contentEl = document.getElementById("diary-content-chat");
    
    if (titleEl) titleEl.textContent = "";
    if (dateEl) dateEl.textContent = "";
    if (moodEl) moodEl.textContent = "";
    if (contentEl) contentEl.textContent = "";


    try {
        const res = await fetch("/api/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });

        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }

        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        currentConversationId = data.conversation_id || null;

        if (data.first_message) {
            appendMessage("ai", data.first_message);
        }

        setConversationStatus("Conversation started. Tap 🎙 to record.");
        setRecordingButtons({
            canRecord: true,
            canStop: false,
            canComplete: false,
        });
    } catch (err) {
        console.error(err);
        setConversationStatus("Failed to start conversation.");
    }
}


async function sendAudioMessage(blob) {
    if (!currentConversationId) {
        setConversationStatus("No active conversation.");
        return;
    }
    setConversationStatus("Sending audio...");

    try {
        const fd = new FormData();
        fd.append("audio", blob, "audio.webm");

        const res = await fetch(
            `/api/conversations/${currentConversationId}/audio`,
            {
                method: "POST",
                body: fd,
            }
        );

        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }

        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        if (data.user_message) {
            appendMessage("user", data.user_message);
        }
        if (data.ai_response) {
            appendMessage("ai", data.ai_response);
        }

        setConversationStatus("Message sent. You can record again or finish.");
        setRecordingButtons({
            canRecord: true,
            canStop: false,
            canComplete: true,
        });
    } catch (err) {
        console.error(err);
        setConversationStatus("Failed to send audio.");
    }
}

// ----------------- Audio recording -----------------

async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setConversationStatus("Recording is not supported.");
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                audioChunks.push(e.data);
            }
        };

        mediaRecorder.onstop = async () => {
            const blob = new Blob(audioChunks, { type: "audio/webm" });
            await sendAudioMessage(blob);
        };

        mediaRecorder.start();
        setConversationStatus("Recording...");
        setRecordingButtons({
            canRecord: false,
            canStop: true,
            canComplete: false,
        });
    } catch (err) {
        console.error(err);
        setConversationStatus("Failed to start recording.");
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        setConversationStatus("Processing audio...");
        setRecordingButtons({
            canRecord: false,
            canStop: false,
            canComplete: false,
        });
    }
}

async function completeConversation() {
    if (!currentConversationId) {
        setConversationStatus("No active conversation.");
        return;
    }

    setConversationStatus("Finishing conversation...");

    try {
        const body = {};
        
        if (diaryPreferences.theme || diaryPreferences.style || diaryPreferences.custom_instructions) {
            body.preferences = {};
            if (diaryPreferences.theme) body.preferences.theme = diaryPreferences.theme;
            if (diaryPreferences.style) body.preferences.style = diaryPreferences.style;
            if (diaryPreferences.custom_instructions) body.preferences.custom_instructions = diaryPreferences.custom_instructions;
        }

        const res = await fetch(
            `/api/conversations/${currentConversationId}/complete`,
            { 
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            }
        );

        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();

        const rightCard = document.querySelector('.chat-right');
        if (rightCard) {
            rightCard.classList.remove('hidden');
        }

        const leftCard = document.querySelector('.chat-left');
        if (leftCard) {
            leftCard.classList.remove('full-width');
            leftCard.classList.add('normal-width');
        }

        const titleEl = document.getElementById("diary-title-chat");
        const dateEl = document.getElementById("diary-date-chat");
        const moodEl = document.getElementById("diary-mood-chat");
        const contentEl = document.getElementById("diary-content-chat");

        if (titleEl) titleEl.textContent = data.title || "";
        if (dateEl) dateEl.textContent = data.date || "";
        if (moodEl) moodEl.textContent = moodToEmoji(data.mood);
        if (contentEl) contentEl.textContent = data.content || "";

        setConversationStatus("Diary generated ✔");
        setRecordingButtons({
            canRecord: false,
            canStop: false,
            canComplete: false,
        });

        currentConversationId = null;
        resetPreferences();

        await loadDiaries();
    } catch (err) {
        console.error(err);
        setConversationStatus("Failed to finish conversation.");
    }
}

// ----------------- Diaries list / detail / search / edit / delete -----------------

async function loadDiaries() {
    if (!currentUserId) return;

    const listEl = document.getElementById("diary-list");
    if (!listEl) return;
    listEl.innerHTML = "";

    try {
        const res = await fetch(
            `/api/users/${currentUserId}/diaries?page=1&limit=50`
        );
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        let lastDate = null;

        data.diaries.forEach((d) => {
            // === Date header ===
            if (d.date !== lastDate) {
                const header = document.createElement("li");
                header.className = "diary-date-header";
                header.textContent = d.date || "";
                listEl.appendChild(header);
                lastDate = d.date;
            }

            // === Diary item ===
            const li = document.createElement("li");
            li.className = "diary-item";

            const timeText = d.time || "";
            const moodLabel = d.mood ? ` (${d.mood})` : "";

            li.textContent = `${timeText}  ${d.title || ""}${moodLabel}`;
            li.dataset.diaryId = d.diary_id;

            li.addEventListener("click", () => {
                loadDiaryDetail(d.diary_id);
            });

            listEl.appendChild(li);
        });
    } catch (err) {
        console.error("loadDiaries error:", err);
    }
}

async function loadDiaryDetail(diaryId) {
    const titleEl = document.getElementById("diary-title");
    const contentEl = document.getElementById("diary-content");
    const dateEl = document.getElementById("diary-date");
    const timeEl = document.getElementById("diary-time");
    const moodEl = document.getElementById("diary-mood");
    try {
        const res = await fetch(`/api/diaries/${diaryId}`);
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        if (titleEl) titleEl.textContent = data.title || "";
        if (contentEl) contentEl.textContent = data.content || "";
        if (dateEl) dateEl.textContent = data.date || "";
        if (timeEl) timeEl.textContent = data.time || "";
        if (moodEl) moodEl.textContent = moodToEmoji(data.mood);

        currentDiaryId = diaryId;

        const actions = document.querySelector(".diary-actions");
        if (actions) actions.classList.remove("hidden");

    } catch (err) {
        console.error("loadDiaryDetail error:", err);
    }
}

async function searchDiaries() {
    const input = document.getElementById("diary-search-input");
    const q = (input?.value || "").trim();
    if (!q) {
        await loadDiaries();
        return;
    }

    const listEl = document.getElementById("diary-list");
    if (!listEl) return;
    listEl.innerHTML = "";

    try {
        const res = await fetch(
            `/api/users/${currentUserId}/diaries/search?q=${encodeURIComponent(
                q
            )}`
        );
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        data.diaries.forEach((d) => {
            const li = document.createElement("li");
            const moodLabel = d.mood ? ` (${d.mood})` : "";
            li.textContent = `${d.date || ""}  ${d.title || ""}${moodLabel}`;
            li.dataset.diaryId = d.diary_id;
            li.addEventListener("click", () => {
                loadDiaryDetail(d.diary_id);
            });
            listEl.appendChild(li);
        });
    } catch (err) {
        console.error("searchDiaries error:", err);
    }
}

async function editCurrentDiary() {
    if (!currentDiaryId) {
        alert("Please select a diary first.");
        return;
    }

    const contentEl = document.getElementById("diary-content");
    const oldContent = contentEl?.textContent || "";
    const newContent = window.prompt("Edit diary content:", oldContent);
    if (newContent === null) return;

    try {
        const res = await fetch(`/api/diaries/${currentDiaryId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: newContent }),
        });
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        if (contentEl) contentEl.textContent = data.content || "";
        await loadDiaries();
        // alert("Diary updated.");
    } catch (err) {
        console.error("editCurrentDiary error:", err);
        alert("Failed to update diary.");
    }
}

async function deleteCurrentDiary() {
    if (!currentDiaryId) {
        alert("Please select a diary first.");
        return;
    }

    if (!window.confirm("Delete this diary? This cannot be undone.")) {
        return;
    }

    try {
        const res = await fetch(`/api/diaries/${currentDiaryId}`, {
            method: "DELETE",
        });
        if (res.status === 401) {
            window.location.href = "/login";
            return;
        }
        if (!res.ok) {
            throw new Error("HTTP " + res.status);
        }

        currentDiaryId = null;

        const titleEl = document.getElementById("diary-title");
        const contentEl = document.getElementById("diary-content");
        const dateEl = document.getElementById("diary-date");
        const timeEl = document.getElementById("diary-time");
        const moodEl = document.getElementById("diary-mood");

        if (titleEl) titleEl.textContent = "";
        if (contentEl) contentEl.textContent = "";
        if (dateEl) dateEl.textContent = "";
        if (timeEl) timeEl.textContent = "";
        if (moodEl) moodEl.textContent = "";

        const actions = document.querySelector(".diary-actions");
        if (actions) actions.classList.add("hidden");
        await loadDiaries();
        
    } catch (err) {
        console.error("deleteCurrentDiary error:", err);
        alert("Failed to delete diary.");
    }
}


// ----------------- Nav + logout -----------------

function logout() {
    window.location.href = "/logout";
}

function setupNav() {
    const buttons = document.querySelectorAll(".bottom-nav .nav-btn");
    const sections = document.querySelectorAll(".page-section");

    buttons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.target;

            buttons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            sections.forEach((sec) => {
                if (sec.id === targetId) {
                    sec.classList.remove("hidden");
                } else {
                    sec.classList.add("hidden");
                }
            });

            if (targetId === "section-diaries") {
                loadDiaries();
            }
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const startConvBtn = document.getElementById("start-conversation-btn");
    const startRecBtn = document.getElementById("start-recording-btn");
    const stopRecBtn = document.getElementById("stop-recording-btn");
    const finishBtn = document.getElementById("finish-conversation-btn");
    const loadDiariesBtn = document.getElementById("load-diaries-btn");
    const searchBtn = document.getElementById("diary-search-btn");
    const searchClearBtn = document.getElementById("diary-search-clear-btn");
    const editBtn = document.getElementById("diary-edit-btn");
    const deleteBtn = document.getElementById("diary-delete-btn");
    // Preferences modal buttons
    const openPrefsBtn = document.getElementById("open-preferences-btn");
    const closePrefsBtn = document.getElementById("close-preferences-btn");
    const savePrefsBtn = document.getElementById("save-preferences-btn");
    const resetPrefsBtn = document.getElementById("reset-preferences-btn");

    // Voice input buttons
    const startVoiceBtn = document.getElementById("start-voice-input-btn");
    const stopVoiceBtn = document.getElementById("stop-voice-input-btn");

    // Template buttons
    const templateBtns = document.querySelectorAll(".template-btn");

    if (startConvBtn) startConvBtn.addEventListener("click", startConversation);
    if (startRecBtn) startRecBtn.addEventListener("click", startRecording);
    if (stopRecBtn) stopRecBtn.addEventListener("click", stopRecording);
    if (finishBtn) finishBtn.addEventListener("click", completeConversation);
    if (loadDiariesBtn) loadDiariesBtn.addEventListener("click", loadDiaries);
    if (searchBtn) searchBtn.addEventListener("click", searchDiaries);
    if (searchClearBtn) {
        searchClearBtn.addEventListener("click", () => {
            const input = document.getElementById("diary-search-input");
            if (input) input.value = "";
            loadDiaries();
        });
    }
    if (editBtn) editBtn.addEventListener("click", editCurrentDiary);
    if (deleteBtn) deleteBtn.addEventListener("click", deleteCurrentDiary);
    if (openPrefsBtn) openPrefsBtn.addEventListener("click", openPreferencesModal);
    if (closePrefsBtn) closePrefsBtn.addEventListener("click", closePreferencesModal);
    if (savePrefsBtn) savePrefsBtn.addEventListener("click", savePreferences);
    if (resetPrefsBtn) resetPrefsBtn.addEventListener("click", resetPreferences);

    // Voice input
    if (startVoiceBtn) startVoiceBtn.addEventListener("click", startVoiceInput);
    if (stopVoiceBtn) stopVoiceBtn.addEventListener("click", stopVoiceInput);

    // Template buttons
    templateBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const template = btn.dataset.template;
            if (template) applyTemplate(template);
        });
    });

    // Close modal when clicking outside
    const modal = document.getElementById("preferences-modal");
    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                closePreferencesModal();
            }
        });
    }
    setupNav();
});

