// ================== general ==================
let currentUserId = window.CURRENT_USER_ID || null;
let currentConversationId = null;

let mediaRecorder = null;
let audioChunks = [];

function appendMessage(role, text) {
    const log = document.getElementById("conversation-log");
    if (!log) return;

    const div = document.createElement("div");
    div.className = role === "user" ? "msg user" : "msg ai";
    div.textContent = `${role}: ${text}`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
}

function setConversationStatus(text) {
    const el = document.getElementById("conversation-status");
    if (el) el.textContent = text || "";
}

function setRecordingButtons({ canRecord, canStop, canComplete }) {
    const recordBtn = document.getElementById("record-btn");
    const stopBtn = document.getElementById("stop-btn");
    const completeBtn = document.getElementById("complete-btn");

    if (recordBtn) recordBtn.disabled = !canRecord;
    if (stopBtn) stopBtn.disabled = !canStop;
    if (completeBtn) completeBtn.disabled = !canComplete;
}

// ================== conversation ==================

async function startConversation() {
    if (!currentUserId) {
        setConversationStatus("No user id in session.");
        return;
    }

    setConversationStatus("Starting conversation...");

    try {
        const res = await fetch("/api/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: currentUserId }),
        });

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        currentConversationId = data.conversation_id;

        const log = document.getElementById("conversation-log");
        if (log) log.innerHTML = "";

        if (data.first_message) {
            appendMessage("ai", data.first_message);
        }

        setRecordingButtons({
            canRecord: true,
            canStop: false,
            canComplete: true,
        });

        setConversationStatus("Conversation started. Press 🎙 to record.");

    } catch (err) {
        console.error("startConversation error:", err);
        setConversationStatus("Failed to start conversation.");
    }
}

// ================== audio ==================

async function startRecording() {
    if (!currentConversationId) {
        setConversationStatus("Start a conversation first.");
        return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setConversationStatus("This browser does not support microphone.");
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);

        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
            sendAudioMessage(audioBlob);
        
            stream.getTracks().forEach((track) => track.stop());
        };

        mediaRecorder.start();
        setConversationStatus("Recording...");
        setRecordingButtons({
            canRecord: false,
            canStop: true,
            canComplete: false,
        });

    } catch (err) {
        console.error("startRecording error:", err);
        setConversationStatus("Unable to access microphone.");
    }
}

function stopRecording() {
    if (!mediaRecorder) return;
    if (mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        setConversationStatus("Processing audio...");
    }
}

async function sendAudioMessage(audioBlob) {
    if (!currentConversationId) {
        setConversationStatus("Conversation ended. Start a new one.");
        return;
    }

    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");

    try {
        const res = await fetch(
            `/api/conversations/${currentConversationId}/messages`,
            {
                method: "POST",
                body: formData,
            }
        );

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        data = await res.json();

        if (data.user_message) {
            appendMessage("user", data.user_message);
        }
        if (data.ai_response) {
            appendMessage("ai", data.ai_response);
        }

        setConversationStatus("Message sent.");
    } catch (err) {
        console.error("sendAudioMessage error:", err);
        setConversationStatus("Failed to send audio.");
    } finally {
        // record again
        setRecordingButtons({
            canRecord: true,
            canStop: false,
            canComplete: true,
        });
    }
}

async function completeConversation() {
    if (!currentConversationId) {
        setConversationStatus("No active conversation.");
        return;
    }

    setConversationStatus("Generating diary...");

    try {
        const res = await fetch(
            `/api/conversations/${currentConversationId}/complete`,
            {
                method: "POST",
            }
        );

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();

        // 1. add diary to detail section
        const titleEl = document.getElementById("diary-title");
        const contentEl = document.getElementById("diary-content");
        const dateEl = document.getElementById("diary-date");

        if (titleEl) titleEl.textContent = data.title || "";
        if (contentEl) contentEl.textContent = data.content || "";
        if (dateEl) dateEl.textContent = data.date || "";

        setConversationStatus("Diary generated ✔");

        // 2. end con.
        currentConversationId = null;
        setRecordingButtons({
            canRecord: false,
            canStop: false,
            canComplete: false,
        });

        // 3. refresh My Diaries list
        await loadDiaries();

        // 4. switch to “My Diaries” tab
        const diariesBtn = document.querySelector(
            '.bottom-nav .nav-btn[data-target="section-diaries"]'
        );
        if (diariesBtn) {
            diariesBtn.click(); 
        }

    } catch (err) {
        console.error("completeConversation error:", err);
        setConversationStatus("Failed to generate diary.");
    }
}


// ================== diary ==================

async function loadDiaries() {
    if (!currentUserId) return;

    const listEl = document.getElementById("diary-list");
    if (!listEl) return;
    listEl.innerHTML = "";

    try {
        const res = await fetch(
            `/api/users/${currentUserId}/diaries?page=1&limit=10`
        );
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();

        data.diaries.forEach((d) => {
            const li = document.createElement("li");
            li.textContent = `${d.date || ""}  ${d.title || ""}`;
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

    try {
        const res = await fetch(`/api/diaries/${diaryId}`);
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        if (titleEl) titleEl.textContent = data.title || "";
        if (contentEl) contentEl.textContent = data.content || "";
        if (dateEl) dateEl.textContent = data.date || "";
    } catch (err) {
        console.error("loadDiaryDetail error:", err);
    }
}

// ================== menu bar switch==================

function setupBottomNav() {
    const navButtons = document.querySelectorAll(".bottom-nav .nav-btn");
    const sections = document.querySelectorAll(".page-section");

    navButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.dataset.target;

            sections.forEach((sec) => {
                if (sec.id === targetId) {
                    sec.classList.remove("hidden");
                } else {
                    sec.classList.add("hidden");
                }
            });

            navButtons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            // refresh
            if (targetId === "section-diaries") {
                loadDiaries();
            }
        });
    });
}

function logout() {
    window.location.href = "/logout";
}


// ================== initialize binding ==================

document.addEventListener("DOMContentLoaded", () => {
    const startConvBtn = document.getElementById("start-conv-btn");
    const recordBtn = document.getElementById("record-btn");
    const stopBtn = document.getElementById("stop-btn");
    const completeBtn = document.getElementById("complete-btn");
    const loadDiariesBtn = document.getElementById("load-diaries-btn");

    if (startConvBtn) {
        startConvBtn.addEventListener("click", startConversation);
    }
    if (recordBtn) {
        recordBtn.addEventListener("click", startRecording);
    }
    if (stopBtn) {
        stopBtn.addEventListener("click", stopRecording);
    }
    if (completeBtn) {
        completeBtn.addEventListener("click", completeConversation);
    }
    if (loadDiariesBtn) {
        loadDiariesBtn.addEventListener("click", loadDiaries);
    }

    // initialize menu bar
    setupBottomNav();

    setRecordingButtons({
        canRecord: false,
        canStop: false,
        canComplete: false,
    });
});
