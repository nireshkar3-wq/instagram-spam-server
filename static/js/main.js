document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    const botForm = document.getElementById('bot-form');
    const startBtn = document.getElementById('start-btn');
    const btnText = startBtn.querySelector('span');
    const btnLoader = startBtn.querySelector('.btn-loader');
    const logConsole = document.getElementById('log-console');
    const clearLogsBtn = document.getElementById('clear-logs');
    const statusBadge = document.getElementById('bot-status-badge');
    const statusText = document.getElementById('status-text');

    // Global Error Catcher
    window.onerror = function (msg, url, line) {
        const errorMsg = `JS Error: ${msg} (at ${url}:${line})`;
        console.error(errorMsg);
        if (typeof addLogEntry === 'function') {
            addLogEntry(errorMsg, "ERROR", new Date().toLocaleTimeString());
        }
        return false;
    };

    // Profile management elements
    const profileSelect = document.getElementById('profile_select');
    const toggleAddBtn = document.getElementById('toggle-add-profile');
    const addProfileForm = document.getElementById('add-profile-form');
    const saveProfileBtn = document.getElementById('save-profile-btn');
    const deleteProfileBtn = document.getElementById('delete-profile-btn');
    const monitorBotBtn = document.getElementById('monitor-bot-btn');
    const screenshotModal = document.getElementById('screenshot-modal');
    const botScreenshot = document.getElementById('bot-screenshot');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const modalProfileName = document.getElementById('modal-profile-name');
    const screenshotLoader = document.getElementById('screenshot-loader');

    let isRunning = false;
    let currentProfile = "";

    // --- Init ---
    fetchProfiles();
    checkStatus();

    // Set interval to periodically check status in case socket is missed
    setInterval(() => {
        if (currentProfile) checkStatus();
    }, 5000);

    // --- Socket Listeners ---
    socket.on('bot_log', (data) => {
        addLogEntry(data.message, data.level, data.timestamp);
    });

    socket.on('bot_finished', (data) => {
        if (data.profile === currentProfile) {
            setBotRunning(false);
            addLogEntry("Process finished.", "system", new Date().toLocaleTimeString());
        }
    });

    // --- Profile Helpers ---
    async function fetchProfiles() {
        try {
            const resp = await fetch('/profiles');
            const profiles = await resp.json();

            // Clear existing except placeholder
            profileSelect.innerHTML = '<option value="">-- Please select an account --</option>';

            Object.keys(profiles).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                profileSelect.appendChild(opt);
            });
        } catch (err) {
            console.error("Failed to fetch profiles", err);
        }
    }

    async function saveProfile() {
        const name = document.getElementById('new_profile_name').value;
        const username = document.getElementById('new_username').value;
        const password = document.getElementById('new_password').value;

        if (!name || !username || !password) {
            alert("Please fill all fields to save a profile.");
            return;
        }

        try {
            const resp = await fetch('/profiles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, username, password })
            });

            if (resp.ok) {
                document.getElementById('new_profile_name').value = '';
                document.getElementById('new_username').value = '';
                document.getElementById('new_password').value = '';
                addProfileForm.classList.add('hidden');
                fetchProfiles();
            }
        } catch (err) {
            alert("Error saving profile: " + err.message);
        }
    }

    async function deleteProfile() {
        const name = profileSelect.value;
        if (!name) return;

        if (!confirm(`Are you sure you want to delete profile "${name}"?`)) return;

        try {
            await fetch(`/profiles/${name}`, { method: 'DELETE' });
            fetchProfiles();
        } catch (err) {
            alert("Error deleting profile: " + err.message);
        }
    }


    // --- Monitoring Logic ---
    let screenshotInterval = null;

    function showScreenshotModal() {
        console.log("showScreenshotModal clicked. currentProfile:", currentProfile);
        if (!currentProfile) {
            alert("Please select an account profile first to use Live View.");
            return;
        }
        modalProfileName.textContent = currentProfile;
        screenshotModal.classList.add('active'); // Use .active instead of removing .hidden
        console.log("Screenshot modal .active added.");
        startScreenshotPolling();
    }

    function hideScreenshotModal() {
        screenshotModal.classList.remove('active');
        stopScreenshotPolling();
    }

    function startScreenshotPolling() {
        stopScreenshotPolling();
        updateScreenshot();
        screenshotInterval = setInterval(updateScreenshot, 3000);
    }

    function stopScreenshotPolling() {
        if (screenshotInterval) {
            clearInterval(screenshotInterval);
            screenshotInterval = null;
        }
    }

    async function updateScreenshot() {
        if (!currentProfile || !screenshotModal.classList.contains('active')) return;

        screenshotLoader.classList.remove('hidden');
        try {
            // Add cache buster
            const imgUrl = `/screenshot/${currentProfile}?t=${Date.now()}`;

            // Preload image to avoid flickering
            const tempImg = new Image();
            tempImg.onload = () => {
                botScreenshot.src = imgUrl;
                botScreenshot.classList.remove('hidden');
                document.getElementById('bot-offline-msg').classList.add('hidden');
                screenshotLoader.classList.add('hidden');
            };
            tempImg.onerror = () => {
                // If the image fails to load, it's likely a 404 because the bot is offline
                botScreenshot.classList.add('hidden');
                document.getElementById('bot-offline-msg').classList.remove('hidden');
                screenshotLoader.classList.add('hidden');
            };
            tempImg.src = imgUrl;

        } catch (err) {
            console.error("Screenshot update error:", err);
            screenshotLoader.classList.add('hidden');
        }
    }

    // --- Helper Functions ---
    function addLogEntry(message, level, timestamp) {
        const entry = document.createElement('div');
        entry.className = `log-entry ${level}`;

        entry.innerHTML = `
            <span class="timestamp">[${timestamp}]</span>
            <span class="message">${message}</span>
        `;

        logConsole.appendChild(entry);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    async function checkStatus() {
        if (!currentProfile) return;
        try {
            const resp = await fetch(`/status/${currentProfile}`);
            const status = await resp.json();

            if (status.running && !isRunning) {
                setBotRunning(true);
                addLogEntry(`Bot is active: ${status.current_task}`, "system", new Date().toLocaleTimeString());
            } else if (!status.running && isRunning) {
                setBotRunning(false);
                addLogEntry("Detected bot idle. UI reset.", "system", new Date().toLocaleTimeString());
            }
        } catch (err) {
            console.error("Failed to check status", err);
        }
    }

    function setBotRunning(running) {
        isRunning = running;
        startBtn.disabled = running;
        const loader = startBtn.querySelector('.btn-loader');
        const btnText = startBtn.querySelector('span');

        if (running) {
            statusBadge.classList.add('running');
            statusText.textContent = "Running";
            loader.classList.remove('hidden');
            btnText.textContent = "Automation Active...";
            monitorBotBtn.classList.remove('hidden');
            console.log("Monitor button shown for profile:", currentProfile);
            addLogEntry("📺 Live View enabled. Click the eye icon in the header to monitor progress.", "system", new Date().toLocaleTimeString());
        } else {
            statusBadge.classList.remove('running');
            statusText.textContent = "Ready";
            loader.classList.add('hidden');
            btnText.textContent = "Initiate Task";
            monitorBotBtn.classList.add('hidden');
            hideScreenshotModal();
        }
    }

    // --- Event Handlers ---
    toggleAddBtn.addEventListener('click', () => {
        addProfileForm.classList.toggle('hidden');
    });

    saveProfileBtn.addEventListener('click', saveProfile);
    deleteProfileBtn.addEventListener('click', deleteProfile);

    profileSelect.addEventListener('change', () => {
        const newProfile = profileSelect.value;
        if (currentProfile) {
            socket.emit('leave', { profile: currentProfile });
        }

        currentProfile = newProfile;

        if (currentProfile) {
            socket.emit('join', { profile: currentProfile });
            // Clear console when switching accounts to avoid confusion
            logConsole.innerHTML = '';
            addLogEntry(`Switched to account: ${currentProfile}`, "system", new Date().toLocaleTimeString());
            // Immediately check status for the new profile
            checkStatus();
        }
    });

    monitorBotBtn.addEventListener('click', showScreenshotModal);
    closeModalBtn.addEventListener('click', hideScreenshotModal);
    document.getElementById('close-modal-x').addEventListener('click', hideScreenshotModal);

    // Close modal on click outside
    screenshotModal.addEventListener('click', (e) => {
        if (e.target === screenshotModal) hideScreenshotModal();
    });

    botForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const post_url = document.getElementById('post_url').value;
        const comment = document.getElementById('comment').value;
        const count = document.getElementById('count').value;
        const headless = document.getElementById('headless').checked;
        const profile_name = profileSelect.value;

        if (!profile_name) {
            alert("Please select an account profile first.");
            return;
        }

        if (!post_url || !comment) return;

        setBotRunning(true);
        addLogEntry(`Starting bot for: ${post_url} [Profile: ${profile_name}]`, "system", new Date().toLocaleTimeString());

        try {
            const response = await fetch('/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_url, comment, count, headless, profile_name })
            });

            const result = await response.json();

            if (!response.ok) {
                addLogEntry(`Error: ${result.error}`, "ERROR", new Date().toLocaleTimeString());
                setBotRunning(false);
            }
        } catch (err) {
            addLogEntry(`Network Error: ${err.message}`, "ERROR", new Date().toLocaleTimeString());
            setBotRunning(false);
        }
    });

    clearLogsBtn.addEventListener('click', () => {
        logConsole.innerHTML = '';
        addLogEntry("Logs cleared.", "system", new Date().toLocaleTimeString());
    });
    // --- Password Toggle ---
    const togglePasswordBtn = document.getElementById('toggle-password-btn');
    const newPasswordField = document.getElementById('new_password');
    const eyeIcon = togglePasswordBtn.querySelector('.eye-icon');
    const eyeOffIcon = togglePasswordBtn.querySelector('.eye-off-icon');

    togglePasswordBtn.addEventListener('click', () => {
        const isPassword = newPasswordField.type === 'password';
        newPasswordField.type = isPassword ? 'text' : 'password';

        eyeIcon.classList.toggle('hidden', isPassword);
        eyeOffIcon.classList.toggle('hidden', !isPassword);
    });
});
