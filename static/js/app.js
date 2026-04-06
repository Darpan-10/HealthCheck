/* ============================================================
   HealthCheck — Chat Application Logic
   ============================================================ */

(function () {
    'use strict';

    // ---- DOM Elements ----
    const chatMessages  = document.getElementById('chatMessages');
    const chatContainer = document.getElementById('chatContainer');
    const userInput     = document.getElementById('userInput');
    const sendBtn       = document.getElementById('sendBtn');
    const inputWrapper  = document.getElementById('inputWrapper');
    const dropdown      = document.getElementById('autocompleteDropdown');
    const followupBtns  = document.getElementById('followupButtons');
    const btnYes        = document.getElementById('btnYes');
    const btnNo         = document.getElementById('btnNo');

    // ---- State ----
    const STATE = {
        IDLE: 'idle',
        WAITING_SYMPTOM: 'waiting_symptom',
        WAITING_DAYS: 'waiting_days',
        ASKING_FOLLOWUP: 'asking_followup',
        DONE: 'done'
    };

    let currentState = STATE.IDLE;
    let allSymptoms = [];
    let chosenSymptom = '';
    let predictedDisease = '';
    let followupSymptoms = [];
    let followupIndex = 0;
    let symptomResponses = {};
    let numDays = 1;
    let activeAutocompleteIndex = -1;

    // ---- Initialize ----
    async function init() {
        // No longer fetching a fixed list of symptoms since we are 100% Gemini-powered.
        // Symptoms are suggested dynamically via /api/search-symptoms.
        allSymptoms = []; 

        // Show welcome hero
        showWelcomeHero();
        currentState = STATE.WAITING_SYMPTOM;
        userInput.placeholder = 'Describe your symptom…';
        userInput.focus();
    }

    // ---- Welcome Hero ----
    function showWelcomeHero() {
        const hero = document.createElement('div');
        hero.className = 'welcome-hero';
        hero.innerHTML = `
            <div class="hero-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
            </div>
            <h2>How are you feeling today?</h2>
            <p>Describe your symptoms and I'll help identify potential conditions, provide precautions, and guide you on next steps.</p>
            <div class="hero-chips">
                <span class="hero-chip" data-symptom="headache">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
                    Headache
                </span>
                <span class="hero-chip" data-symptom="fever">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/></svg>
                    Fever
                </span>
                <span class="hero-chip" data-symptom="fatigue">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
                    Fatigue
                </span>
                <span class="hero-chip" data-symptom="cough">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2c3 0 5 2 8 2s4-1 4-1v11s-1 1-4 1-5-2-8-2-4 1-4 1V2s1-1 4-1"/><line x1="4" y1="22" x2="4" y2="15"/></svg>
                    Cough
                </span>
                <span class="hero-chip" data-symptom="skin rash">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><circle cx="6" cy="6" r="1"/><circle cx="18" cy="18" r="1"/><circle cx="18" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>
                    Skin Rash
                </span>
            </div>
        `;
        chatMessages.appendChild(hero);

        // Chip click listeners
        hero.querySelectorAll('.hero-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const symptom = chip.dataset.symptom;
                userInput.value = symptom;
                handleSend();
            });
        });

        scrollToBottom();
    }

    // ---- Message Rendering ----
    function addBotMessage(html) {
        const msg = document.createElement('div');
        msg.className = 'message bot';
        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="18" height="18" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
            </div>
            <div class="message-bubble">${html}</div>
        `;
        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    function addUserMessage(text) {
        const msg = document.createElement('div');
        msg.className = 'message user';
        msg.innerHTML = `
            <div class="message-avatar">Y</div>
            <div class="message-bubble">${escapeHtml(text)}</div>
        `;
        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    function addDiagnosisCard(result) {
        const card = document.createElement('div');
        card.className = 'message bot';

        let precautionsHtml = '';
        if (result.precautions && result.precautions.length > 0) {
            const items = result.precautions
                .filter(p => p && p.trim())
                .map(p => `<li>${escapeHtml(p.trim())}</li>`)
                .join('');
            precautionsHtml = `
                <div class="diagnosis-section">
                    <h4>Recommended Precautions</h4>
                    <ul class="precautions-list">${items}</ul>
                </div>`;
        }

        let secondaryHtml = '';
        if (result.secondary_disease) {
            secondaryHtml = `
                <div class="secondary-hint">
                    💡 This could also indicate <strong>${escapeHtml(result.secondary_disease)}</strong>. Consider consulting a specialist.
                </div>`;
        }

        const severityIcon = result.severity === 'serious' ? '⚠️' : '✅';
        const headerGradientClass = result.severity === 'serious' ? 'style="background: linear-gradient(135deg, #F59E0B, #EF4444);"' : '';

        card.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="18" height="18" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
            </div>
            <div class="diagnosis-card">
                <div class="diagnosis-card-header" ${headerGradientClass}>
                    <div class="header-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 12l2 2 4-4"/>
                            <circle cx="12" cy="12" r="10"/>
                        </svg>
                    </div>
                    <div>
                        <h3>Assessment Complete</h3>
                        <span class="header-label">AI Health Report</span>
                    </div>
                </div>
                <div class="diagnosis-card-body">
                    <div class="disease-name">
                        ${escapeHtml(result.primary_disease)}
                        <span class="severity-badge ${result.severity}">${severityIcon} ${result.severity}</span>
                    </div>

                    <div class="diagnosis-section">
                        <h4>Description</h4>
                        <p>${escapeHtml(result.description)}</p>
                    </div>

                    ${precautionsHtml}
                    ${secondaryHtml}

                    <div class="severity-advice ${result.severity}">
                        ${result.severity === 'serious' ? '⚠️' : '💚'} ${escapeHtml(result.severity_advice)}
                    </div>

                    <button class="new-chat-btn" onclick="window.location.reload()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
                            <polyline points="1 4 1 10 7 10"/>
                            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                        </svg>
                        Start New Check
                    </button>
                </div>
            </div>
        `;

        chatMessages.appendChild(card);
        scrollToBottom();
    }

    function showTyping() {
        const typing = document.createElement('div');
        typing.className = 'message bot';
        typing.id = 'typingIndicator';
        typing.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="18" height="18" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"></line>
                    <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
            </div>
            <div class="message-bubble">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(typing);
        scrollToBottom();
    }

    function removeTyping() {
        const el = document.getElementById('typingIndicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        });
    }

    // ---- Autocomplete ----
    async function showAutocomplete(query) {
        if (!query || query.length < 2 || currentState !== STATE.WAITING_SYMPTOM) {
            hideAutocomplete();
            return;
        }

        try {
            const res = await fetch(`/api/search-symptoms?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            const matches = data.results || [];

            if (matches.length === 0) {
                hideAutocomplete();
                return;
            }

            dropdown.innerHTML = matches.map((s, i) => {
                const highlighted = s.replace(
                    new RegExp(`(${escapeRegExp(query)})`, 'gi'),
                    '<mark>$1</mark>'
                );
                return `<div class="autocomplete-item" data-index="${i}" data-value="${s}">${highlighted}</div>`;
            }).join('');

            dropdown.classList.add('show');
            activeAutocompleteIndex = -1;
        } catch (e) {
            console.error('Autocomplete fetch failed:', e);
            hideAutocomplete();
        }
    }

    function hideAutocomplete() {
        dropdown.classList.remove('show');
        dropdown.innerHTML = '';
        activeAutocompleteIndex = -1;
    }

    function selectAutocompleteItem(value) {
        userInput.value = value;
        hideAutocomplete();
        handleSend();
    }

    // ---- Input Handling ----
    async function handleSend() {
        const value = userInput.value.trim();
        if (!value) return;

        userInput.value = '';
        hideAutocomplete();

        switch (currentState) {
            case STATE.WAITING_SYMPTOM:
                await handleSymptomInput(value);
                break;
            case STATE.WAITING_DAYS:
                await handleDaysInput(value);
                break;
        }
    }

    async function handleSymptomInput(symptom) {
        // Remove welcome hero if present
        const hero = chatMessages.querySelector('.welcome-hero');
        if (hero) {
            hero.style.animation = 'none';
            hero.style.opacity = '0';
            hero.style.transform = 'translateY(-10px)';
            hero.style.transition = 'all 0.3s ease';
            setTimeout(() => hero.remove(), 300);
        }

        addUserMessage(symptom);
        showTyping();

        try {
            // Check if this symptom is recognized by Gemini.
            const res = await fetch(`/api/search-symptoms?q=${encodeURIComponent(symptom)}`);
            const data = await res.json();
            const matches = data.results || [];

            removeTyping();

            // If Gemini doesn't find any close symptom match, we use the user's exact wording.
            // This allows for freer description of symptoms.
            chosenSymptom = (matches.length > 0) ? matches[0] : symptom;

            if (matches.length > 0 && matches[0].toLowerCase() !== symptom.toLowerCase()) {
                addBotMessage(`I'll look into <strong>${escapeHtml(chosenSymptom)}</strong> for you.<br><br>How many days have you been experiencing this?`);
            } else {
                addBotMessage(`Got it — <strong>${escapeHtml(chosenSymptom)}</strong>.<br><br>How many days have you been experiencing this symptom?`);
            }

            currentState = STATE.WAITING_DAYS;
            userInput.placeholder = 'Number of days…';
            userInput.focus();

        } catch (err) {
            removeTyping();
            addBotMessage('Something went wrong. Please try again.');
            console.error(err);
        }
    }

    async function handleDaysInput(input) {
        const days = parseInt(input);
        if (isNaN(days) || days < 1 || days > 365) {
            addBotMessage('Please enter a valid number of days (1–365).');
            return;
        }

        numDays = days;
        addUserMessage(`${days} day${days > 1 ? 's' : ''}`);
        showTyping();

        try {
            const res = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symptom: chosenSymptom,
                    num_days: numDays
                })
            });

            const data = await res.json();
            removeTyping();

            if (data.error) {
                addBotMessage(data.error);
                currentState = STATE.WAITING_SYMPTOM;
                userInput.placeholder = 'Describe your symptom…';
                return;
            }

            predictedDisease = data.disease;
            followupSymptoms = data.followup_symptoms || [];
            followupIndex = 0;
            symptomResponses = {};

            if (followupSymptoms.length > 0) {
                currentState = STATE.ASKING_FOLLOWUP;
                askNextFollowup();
            } else {
                await getFinalDiagnosis();
            }

        } catch (err) {
            removeTyping();
            addBotMessage('Something went wrong. Please try again.');
            console.error(err);
        }
    }

    function askNextFollowup() {
        if (followupIndex >= followupSymptoms.length) {
            getFinalDiagnosis();
            return;
        }

        const symptom = followupSymptoms[followupIndex];
        addBotMessage(`Are you also experiencing <strong>${escapeHtml(symptom)}</strong>?`);

        inputWrapper.style.display = 'none';
        followupBtns.style.display = 'flex';
    }

    function handleFollowupAnswer(answer) {
        const symptom = followupSymptoms[followupIndex];
        symptomResponses[symptom] = answer;
        addUserMessage(answer ? 'Yes' : 'No');

        followupIndex++;

        if (followupIndex >= followupSymptoms.length) {
            followupBtns.style.display = 'none';
            inputWrapper.style.display = 'flex';
            getFinalDiagnosis();
        } else {
            askNextFollowup();
        }
    }

    async function getFinalDiagnosis() {
        currentState = STATE.DONE;
        followupBtns.style.display = 'none';
        inputWrapper.style.display = 'flex';
        showTyping();

        try {
            const res = await fetch('/api/final-diagnosis', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    initial_symptom: chosenSymptom,
                    disease: predictedDisease,
                    symptom_responses: symptomResponses,
                    num_days: numDays
                })
            });

            const result = await res.json();
            removeTyping();
            addDiagnosisCard(result);

            userInput.placeholder = 'Refresh to start a new check…';
            userInput.disabled = true;
            sendBtn.disabled = true;

        } catch (err) {
            removeTyping();
            addBotMessage('Something went wrong generating the diagnosis. Please refresh and try again.');
            console.error(err);
        }
    }

    // ---- Event Listeners ----
    sendBtn.addEventListener('click', handleSend);

    userInput.addEventListener('keydown', function (e) {
        const items = dropdown.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeAutocompleteIndex = Math.min(activeAutocompleteIndex + 1, items.length - 1);
            updateActiveItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeAutocompleteIndex = Math.max(activeAutocompleteIndex - 1, 0);
            updateActiveItem(items);
        } else if (e.key === 'Enter') {
            if (activeAutocompleteIndex >= 0 && items[activeAutocompleteIndex]) {
                e.preventDefault();
                selectAutocompleteItem(items[activeAutocompleteIndex].dataset.value);
            } else {
                handleSend();
            }
        } else if (e.key === 'Escape') {
            hideAutocomplete();
        }
    });

    userInput.addEventListener('input', function () {
        showAutocomplete(this.value.trim());
    });

    userInput.addEventListener('focus', function () {
        if (this.value.trim().length > 0 && currentState === STATE.WAITING_SYMPTOM) {
            showAutocomplete(this.value.trim());
        }
    });

    dropdown.addEventListener('click', function (e) {
        const item = e.target.closest('.autocomplete-item');
        if (item) {
            selectAutocompleteItem(item.dataset.value);
        }
    });

    document.addEventListener('click', function (e) {
        if (!inputWrapper.contains(e.target)) {
            hideAutocomplete();
        }
    });

    btnYes.addEventListener('click', () => handleFollowupAnswer(true));
    btnNo.addEventListener('click', () => handleFollowupAnswer(false));

    function updateActiveItem(items) {
        items.forEach(item => item.classList.remove('active'));
        if (items[activeAutocompleteIndex]) {
            items[activeAutocompleteIndex].classList.add('active');
            items[activeAutocompleteIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    // ---- Utilities ----
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeRegExp(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // ---- Start ----
    init();

})();
