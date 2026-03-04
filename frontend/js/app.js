(function () {
    "use strict";

    const API_BASE = "/api";
    const POLL_INTERVAL_MS = 2000;

    // --- Session ---
    function getSessionId() {
        let sid = localStorage.getItem("mapvideo_session_id");
        if (!sid) {
            sid = crypto.randomUUID ? crypto.randomUUID() : _uuidv4();
            localStorage.setItem("mapvideo_session_id", sid);
        }
        return sid;
    }

    function _uuidv4() {
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    const SESSION_ID = getSessionId();

    // --- API helpers ---
    function apiHeaders() {
        return {
            "Content-Type": "application/json",
            "X-Session-ID": SESSION_ID,
        };
    }

    async function apiGet(path) {
        const resp = await fetch(API_BASE + path, { headers: apiHeaders() });
        return resp;
    }

    async function apiPost(path, body) {
        const resp = await fetch(API_BASE + path, {
            method: "POST",
            headers: apiHeaders(),
            body: JSON.stringify(body),
        });
        return resp;
    }

    // --- DOM refs ---
    const tabs = document.querySelectorAll(".tab");
    const singleFields = document.getElementById("single-fields");
    const doubleFields = document.getElementById("double-fields");
    const form = document.getElementById("generate-form");
    const submitBtn = document.getElementById("submit-btn");
    const tasksList = document.getElementById("tasks-list");
    const queueBanner = document.getElementById("queue-banner");
    const queueCount = document.getElementById("queue-count");
    const queueMax = document.getElementById("queue-max");

    let currentMode = "single";
    const pollingTimers = {};

    // --- Mode tabs ---
    tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            tabs.forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            currentMode = tab.dataset.mode;
            if (currentMode === "single") {
                singleFields.classList.remove("hidden");
                doubleFields.classList.add("hidden");
            } else {
                singleFields.classList.add("hidden");
                doubleFields.classList.remove("hidden");
            }
        });
    });

    // --- Form submit ---
    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        submitBtn.disabled = true;

        var body;
        if (currentMode === "single") {
            var city = document.getElementById("city").value.trim();
            if (!city) {
                alert("Введите название города");
                submitBtn.disabled = false;
                return;
            }
            body = { mode: "single", city: city };
        } else {
            var cityA = document.getElementById("city_a").value.trim();
            var cityB = document.getElementById("city_b").value.trim();
            if (!cityA || !cityB) {
                alert("Введите оба города");
                submitBtn.disabled = false;
                return;
            }
            body = { mode: "double", city_a: cityA, city_b: cityB };
        }

        try {
            var resp = await apiPost("/generate", body);
            var data = await resp.json();

            if (resp.status === 429) {
                queueBanner.classList.remove("hidden");
                setTimeout(function () { queueBanner.classList.add("hidden"); }, 5000);
                return;
            }

            if (resp.status === 503) {
                alert("Сервис временно недоступен: Redis не подключён. Убедитесь, что Redis (Memurai) запущен.");
                return;
            }

            if (resp.status === 201) {
                addTaskCard(data.task_id, currentMode, body, "queued");
                startPolling(data.task_id);
                updateQueueInfo();
            } else {
                alert(data.error || "Ошибка при создании задачи");
            }
        } catch (err) {
            alert("Ошибка сети: " + err.message);
        } finally {
            submitBtn.disabled = false;
        }
    });

    // --- Task cards ---
    function citiesLabel(mode, body) {
        if (mode === "single") return body.city || "—";
        return (body.city_a || "?") + " → " + (body.city_b || "?");
    }

    function addTaskCard(taskId, mode, body, status) {
        var card = document.createElement("div");
        card.className = "task-card";
        card.id = "task-" + taskId;

        card.innerHTML =
            '<div class="task-header">' +
            '  <span class="task-cities">' + escapeHtml(citiesLabel(mode, body)) + "</span>" +
            '  <span class="task-status status-' + status + '" id="status-' + taskId + '">' + statusLabel(status) + "</span>" +
            "</div>" +
            '<div class="task-progress" id="progress-' + taskId + '"></div>' +
            '<div class="task-error hidden" id="error-' + taskId + '"></div>' +
            '<div class="task-video hidden" id="video-' + taskId + '"></div>' +
            '<div class="task-actions hidden" id="actions-' + taskId + '"></div>';

        tasksList.prepend(card);
    }

    function statusLabel(s) {
        var map = {
            queued: "В очереди",
            processing: "Обработка",
            completed: "Готово",
            failed: "Ошибка",
        };
        var prefix = s === "processing" ? '<span class="spinner"></span>' : "";
        return prefix + (map[s] || s);
    }

    function updateTaskCard(taskId, data) {
        var statusEl = document.getElementById("status-" + taskId);
        var progressEl = document.getElementById("progress-" + taskId);
        var errorEl = document.getElementById("error-" + taskId);
        var videoEl = document.getElementById("video-" + taskId);
        var actionsEl = document.getElementById("actions-" + taskId);

        if (!statusEl) return;

        statusEl.className = "task-status status-" + data.status;
        statusEl.innerHTML = statusLabel(data.status);

        if (data.progress) {
            progressEl.textContent = data.progress;
            progressEl.classList.remove("hidden");
        } else {
            progressEl.classList.add("hidden");
        }

        if (data.status === "failed" && data.error) {
            errorEl.textContent = data.error;
            errorEl.classList.remove("hidden");
        }

        if (data.status === "completed" && data.video_url) {
            var videoSrc = data.video_url + "?sid=" + SESSION_ID;
            videoEl.innerHTML =
                '<video controls preload="metadata">' +
                '  <source src="' + escapeHtml(videoSrc) + '" type="video/mp4">' +
                "</video>";
            videoEl.classList.remove("hidden");

            actionsEl.innerHTML =
                '<a href="' + escapeHtml(videoSrc) + '" download class="btn-download">Скачать MP4</a>';
            actionsEl.classList.remove("hidden");

            progressEl.classList.add("hidden");
        }
    }

    // --- Polling ---
    function startPolling(taskId) {
        if (pollingTimers[taskId]) return;

        pollingTimers[taskId] = setInterval(async function () {
            try {
                var resp = await apiGet("/status/" + taskId);
                if (!resp.ok) return;
                var data = await resp.json();
                updateTaskCard(taskId, data);

                if (data.status === "completed" || data.status === "failed") {
                    clearInterval(pollingTimers[taskId]);
                    delete pollingTimers[taskId];
                    updateQueueInfo();
                }
            } catch (err) {
                console.error("Polling error:", err);
            }
        }, POLL_INTERVAL_MS);
    }

    // --- Queue info ---
    async function updateQueueInfo() {
        try {
            var resp = await apiGet("/queue/info");
            if (resp.ok) {
                var data = await resp.json();
                queueCount.textContent = data.queue_size;
                queueMax.textContent = data.max_queue_size;
            }
        } catch (err) {
            console.error("Queue info error:", err);
        }
    }

    // --- Load existing tasks ---
    async function loadTasks() {
        try {
            var resp = await apiGet("/tasks");
            if (!resp.ok) return;
            var data = await resp.json();

            data.tasks.forEach(function (task) {
                var body = {};
                if (task.mode === "single") {
                    body.city = task.cities && task.cities[0] ? task.cities[0] : "—";
                } else {
                    body.city_a = task.cities && task.cities[0] ? task.cities[0] : "?";
                    body.city_b = task.cities && task.cities[1] ? task.cities[1] : "?";
                }
                addTaskCard(task.task_id, task.mode, body, task.status);

                if (task.status === "completed" || task.status === "failed") {
                    updateTaskCard(task.task_id, task);
                } else {
                    startPolling(task.task_id);
                }
            });
        } catch (err) {
            console.error("Load tasks error:", err);
        }
    }

    // --- Helpers ---
    function escapeHtml(s) {
        var div = document.createElement("div");
        div.textContent = s;
        return div.innerHTML;
    }

    // --- Init ---
    loadTasks();
    updateQueueInfo();
    setInterval(updateQueueInfo, 10000);
})();
