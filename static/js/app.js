/* ============================================================
   HealthCheck — Application Logic
   Features: Multilingual chat + Nearby facility tracker
   ============================================================ */

(function () {
    'use strict';

    // ── Assumes translations.js is loaded first (provides t, tf, setLang, getLang, applyTranslations, LANG_META) ──

    // ---- DOM References ----
    const chatMessages   = document.getElementById('chatMessages');
    const chatContainer  = document.getElementById('chatContainer');
    const userInput      = document.getElementById('userInput');
    const sendBtn        = document.getElementById('sendBtn');
    const inputWrapper   = document.getElementById('inputWrapper');
    const dropdown       = document.getElementById('autocompleteDropdown');
    const followupBtns   = document.getElementById('followupButtons');
    const btnYes         = document.getElementById('btnYes');
    const btnNo          = document.getElementById('btnNo');

    // Navbar buttons
    const langBtn        = document.getElementById('langBtn');
    const nearbyBtn      = document.getElementById('nearbyBtn');
    const activeLangFlag = document.getElementById('activeLangFlag');

    // Language modal
    const langModalOverlay = document.getElementById('langModalOverlay');
    const langModalClose   = document.getElementById('langModalClose');
    const langOptions      = document.querySelectorAll('.lang-option');

    // Location modal
    const locModalOverlay = document.getElementById('locModalOverlay');
    const locModalClose   = document.getElementById('locModalClose');
    const locLoading      = document.getElementById('locLoading');
    const locLoadingMsg   = document.getElementById('locLoadingMsg');
    const locError        = document.getElementById('locError');
    const locErrorMsg     = document.getElementById('locErrorMsg');
    const locResults      = document.getElementById('locResults');
    const hospitalsList   = document.getElementById('hospitalsList');
    const pharmaciesList  = document.getElementById('pharmaciesList');
    const locRetryBtn     = document.getElementById('locRetryBtn');

    // ---- Chat State Machine ----
    const STATE = {
        IDLE:           'idle',
        WAITING_SYMPTOM:'waiting_symptom',
        WAITING_DAYS:   'waiting_days',
        ASKING_FOLLOWUP:'asking_followup',
        DONE:           'done'
    };

    let currentState          = STATE.IDLE;
    let chosenSymptom         = '';
    let predictedDisease      = '';
    let followupSymptoms      = [];
    let followupIndex         = 0;
    let symptomResponses      = {};
    let numDays               = 1;
    let activeAutocompleteIdx = -1;

    // ============================================================
    // INIT
    // ============================================================
    function init() {
        showWelcomeHero();
        currentState = STATE.WAITING_SYMPTOM;
        applyTranslations();
        userInput.focus();
    }

    // ============================================================
    // WELCOME HERO
    // ============================================================
    function showWelcomeHero() {
        const hero = document.createElement('div');
        hero.className = 'welcome-hero';
        hero.id = 'welcomeHero';
        hero.innerHTML = `
            <div class="hero-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <h2 data-i18n="heroTitle">${t('heroTitle')}</h2>
            <p data-i18n="heroDesc">${t('heroDesc')}</p>
            <div class="hero-chips">
                <span class="hero-chip" data-symptom="headache">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>
                    <span data-i18n="chip_headache">${t('chip_headache')}</span>
                </span>
                <span class="hero-chip" data-symptom="fever">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/></svg>
                    <span data-i18n="chip_fever">${t('chip_fever')}</span>
                </span>
                <span class="hero-chip" data-symptom="fatigue">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
                    <span data-i18n="chip_fatigue">${t('chip_fatigue')}</span>
                </span>
                <span class="hero-chip" data-symptom="cough">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2c3 0 5 2 8 2s4-1 4-1v11s-1 1-4 1-5-2-8-2-4 1-4 1V2s1-1 4-1"/><line x1="4" y1="22" x2="4" y2="15"/></svg>
                    <span data-i18n="chip_cough">${t('chip_cough')}</span>
                </span>
                <span class="hero-chip" data-symptom="skin rash">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><circle cx="6" cy="6" r="1"/><circle cx="18" cy="18" r="1"/><circle cx="18" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>
                    <span data-i18n="chip_rash">${t('chip_rash')}</span>
                </span>
            </div>
        `;
        chatMessages.appendChild(hero);

        hero.querySelectorAll('.hero-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                userInput.value = chip.dataset.symptom;
                handleSend();
            });
        });

        scrollToBottom();
    }

    function refreshHero() {
        const hero = document.getElementById('welcomeHero');
        if (!hero) return;
        hero.querySelector('[data-i18n="heroTitle"]').innerHTML = t('heroTitle');
        hero.querySelector('[data-i18n="heroDesc"]').innerHTML = t('heroDesc');
        hero.querySelectorAll('[data-i18n]').forEach(el => {
            if (el.dataset.i18n !== 'heroTitle' && el.dataset.i18n !== 'heroDesc') {
                el.textContent = t(el.dataset.i18n);
            }
        });
    }

    // ============================================================
    // MESSAGE RENDERING
    // ============================================================
    function addBotMessage(html) {
        const msg = document.createElement('div');
        msg.className = 'message bot';
        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
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
            <div class="message-avatar">You</div>
            <div class="message-bubble">${escapeHtml(text)}</div>
        `;
        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    function addDiagnosisCard(result) {
        const card = document.createElement('div');
        card.className = 'message bot';

        const isSerious = result.severity === 'serious';

        let precautionsHtml = '';
        if (result.precautions && result.precautions.length > 0) {
            const items = result.precautions
                .filter(p => p && p.trim())
                .map(p => `<li>${escapeHtml(p.trim())}</li>`)
                .join('');
            precautionsHtml = `
                <div class="diagnosis-section">
                    <h4>${t('precautionsLabel')}</h4>
                    <ul class="precautions-list">${items}</ul>
                </div>`;
        }

        let secondaryHtml = '';
        if (result.secondary_disease) {
            secondaryHtml = `
                <div class="secondary-hint">
                    ${tf('secondaryHint', { disease: escapeHtml(result.secondary_disease) })}
                </div>`;
        }

        const severityIcon = isSerious ? '⚠️' : '✅';
        const severityText = isSerious ? t('severityAdviceSerious') : t('severityAdviceMild');

        card.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <div class="diagnosis-card">
                <div class="diagnosis-card-header ${isSerious ? 'serious' : ''}">
                    <div class="header-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 12l2 2 4-4"/>
                            <circle cx="12" cy="12" r="10"/>
                        </svg>
                    </div>
                    <div>
                        <h3>${t('assessmentTitle')}</h3>
                        <span class="header-label">${t('assessmentLabel')}</span>
                    </div>
                </div>
                <div class="diagnosis-card-body">
                    <div class="disease-name">
                        ${escapeHtml(result.primary_disease)}
                        <span class="severity-badge ${result.severity}">${severityIcon} ${result.severity}</span>
                    </div>
                    <div class="diagnosis-section">
                        <h4>${t('descriptionLabel')}</h4>
                        <p>${escapeHtml(result.description)}</p>
                    </div>
                    ${precautionsHtml}
                    ${secondaryHtml}
                    <div class="severity-advice ${result.severity}">
                        ${isSerious ? '⚠️' : '💚'} ${escapeHtml(severityText)}
                    </div>
                    <button class="new-chat-btn" onclick="window.location.reload()">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                            <polyline points="1 4 1 10 7 10"/>
                            <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                        </svg>
                        ${t('startNew')}
                    </button>
                </div>
            </div>
        `;

        chatMessages.appendChild(card);
        scrollToBottom();
    }

    // ============================================================
    // TYPING INDICATOR
    // ============================================================
    function showTyping() {
        const el = document.createElement('div');
        el.className = 'message bot';
        el.id = 'typingIndicator';
        el.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <div class="message-bubble">
                <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
        `;
        chatMessages.appendChild(el);
        scrollToBottom();
    }

    function removeTyping() {
        const el = document.getElementById('typingIndicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        requestAnimationFrame(() => { chatContainer.scrollTop = chatContainer.scrollHeight; });
    }

    // ============================================================
    // AUTOCOMPLETE
    // ============================================================
    async function showAutocomplete(query) {
        if (!query || query.length < 2 || currentState !== STATE.WAITING_SYMPTOM) {
            hideAutocomplete(); return;
        }
        try {
            const res = await fetch(`/api/search-symptoms?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            const matches = data.results || [];

            if (matches.length === 0) { hideAutocomplete(); return; }

            dropdown.innerHTML = matches.map((s, i) => {
                const hi = s.replace(new RegExp(`(${escapeRegExp(query)})`, 'gi'), '<mark>$1</mark>');
                return `<div class="autocomplete-item" data-index="${i}" data-value="${s}">${hi}</div>`;
            }).join('');

            dropdown.classList.add('show');
            activeAutocompleteIdx = -1;
        } catch (e) {
            hideAutocomplete();
        }
    }

    function hideAutocomplete() {
        dropdown.classList.remove('show');
        dropdown.innerHTML = '';
        activeAutocompleteIdx = -1;
    }

    function selectAutocompleteItem(value) {
        userInput.value = value;
        hideAutocomplete();
        handleSend();
    }

    function updateActiveItem(items) {
        items.forEach(item => item.classList.remove('active'));
        if (items[activeAutocompleteIdx]) {
            items[activeAutocompleteIdx].classList.add('active');
            items[activeAutocompleteIdx].scrollIntoView({ block: 'nearest' });
        }
    }

    // ============================================================
    // CHAT FLOW — INPUT HANDLING
    // ============================================================
    async function handleSend() {
        const value = userInput.value.trim();
        if (!value) return;
        userInput.value = '';
        hideAutocomplete();

        switch (currentState) {
            case STATE.WAITING_SYMPTOM: await handleSymptomInput(value); break;
            case STATE.WAITING_DAYS:   await handleDaysInput(value); break;
        }
    }

    async function handleSymptomInput(symptom) {
        const hero = chatMessages.querySelector('.welcome-hero');
        if (hero) {
            hero.style.transition = 'all 0.3s ease';
            hero.style.opacity = '0';
            hero.style.transform = 'translateY(-10px)';
            setTimeout(() => hero.remove(), 300);
        }

        addUserMessage(symptom);
        showTyping();

        try {
            const res = await fetch(`/api/search-symptoms?q=${encodeURIComponent(symptom)}`);
            const data = await res.json();
            const matches = data.results || [];
            removeTyping();

            chosenSymptom = (matches.length > 0) ? matches[0] : symptom;

            if (matches.length > 0 && matches[0].toLowerCase() !== symptom.toLowerCase()) {
                addBotMessage(tf('msgLookingInto', { symptom: escapeHtml(chosenSymptom) }));
            } else {
                addBotMessage(tf('msgGotIt', { symptom: escapeHtml(chosenSymptom) }));
            }

            // Explicitly ask for days in a separate bubble
            setTimeout(() => {
                addBotMessage(t('msgAskDays'));
            }, 500);

            currentState = STATE.WAITING_DAYS;
            userInput.setAttribute('placeholder', t('daysPlaceholder'));
            userInput.focus();

        } catch (err) {
            removeTyping();
            addBotMessage(t('msgError'));
            console.error(err);
        }
    }

    async function handleDaysInput(input) {
        const days = parseInt(input);
        if (isNaN(days) || days < 1 || days > 365) {
            addBotMessage(t('msgInvalidDays'));
            return;
        }

        numDays = days;
        addUserMessage(`${days} day${days > 1 ? 's' : ''}`);
        showTyping();

        try {
            const res = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symptom: chosenSymptom, num_days: numDays })
            });

            const data = await res.json();
            removeTyping();

            if (data.error) {
                addBotMessage(escapeHtml(data.error));
                currentState = STATE.WAITING_SYMPTOM;
                userInput.setAttribute('placeholder', t('symptomPlaceholder'));
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
            addBotMessage(t('msgError'));
            console.error(err);
        }
    }

    function askNextFollowup() {
        if (followupIndex >= followupSymptoms.length) {
            getFinalDiagnosis();
            return;
        }
        const symptom = followupSymptoms[followupIndex];
        addBotMessage(tf('msgFollowup', { symptom: escapeHtml(symptom) }));
        inputWrapper.style.display = 'none';
        followupBtns.style.display = 'flex';
    }

    function handleFollowupAnswer(answer) {
        const symptom = followupSymptoms[followupIndex];
        symptomResponses[symptom] = answer;
        addUserMessage(answer ? t('yes') : t('no'));
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

            userInput.setAttribute('placeholder', t('refreshPlaceholder'));
            userInput.disabled = true;
            sendBtn.disabled = true;

        } catch (err) {
            removeTyping();
            addBotMessage(t('msgDiagnosisError'));
            console.error(err);
        }
    }

    // ============================================================
    // LANGUAGE MODAL
    // ============================================================
    function openLangModal() {
        langModalOverlay.classList.add('open');
        langModalOverlay.setAttribute('aria-hidden', 'false');
    }

    function closeLangModal() {
        langModalOverlay.classList.remove('open');
        langModalOverlay.setAttribute('aria-hidden', 'true');
    }

    function applyLang(lang) {
        setLang(lang);
        const meta = LANG_META[lang];

        // Update active flag in navbar
        activeLangFlag.textContent = meta.flag;

        // Update active state on options
        langOptions.forEach(opt => {
            opt.classList.toggle('active', opt.dataset.lang === lang);
        });

        // Apply all [data-i18n] translations globally
        applyTranslations();

        // Refresh hero if visible
        refreshHero();

        // Update input placeholder based on state
        if (currentState === STATE.WAITING_SYMPTOM) {
            userInput.setAttribute('placeholder', t('symptomPlaceholder'));
        } else if (currentState === STATE.WAITING_DAYS) {
            userInput.setAttribute('placeholder', t('daysPlaceholder'));
        } else if (currentState === STATE.DONE) {
            userInput.setAttribute('placeholder', t('refreshPlaceholder'));
        }

        // Update Yes/No buttons text
        btnYes.textContent = t('yes');
        btnNo.textContent  = t('no');

        closeLangModal();
    }

    langBtn.addEventListener('click', openLangModal);
    langModalClose.addEventListener('click', closeLangModal);
    langModalOverlay.addEventListener('click', e => {
        if (e.target === langModalOverlay) closeLangModal();
    });

    langOptions.forEach(opt => {
        opt.addEventListener('click', () => applyLang(opt.dataset.lang));
    });

    // ============================================================
    // LOCATION / NEARBY MODAL
    // ============================================================

    // Haversine distance in km
    function haversine(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2
                + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function openLocModal() {
        locModalOverlay.classList.add('open');
        locModalOverlay.setAttribute('aria-hidden', 'false');
        startLocationSearch();
    }

    function closeLocModal() {
        locModalOverlay.classList.remove('open');
        locModalOverlay.setAttribute('aria-hidden', 'true');
    }

    function showLocState(state) {
        locLoading.style.display = state === 'loading' ? 'flex' : 'none';
        locError.style.display   = state === 'error'   ? 'flex' : 'none';
        locResults.style.display = state === 'results' ? 'flex' : 'none';
    }

    function startLocationSearch() {
        showLocState('loading');
        locLoadingMsg.textContent = t('locating');

        // Check for Secure Context (Geolocation requires HTTPS or localhost)
        if (!window.isSecureContext && window.location.hostname !== '127.0.0.1' && window.location.hostname !== 'localhost') {
            showLocError("Location services require a secure connection (HTTPS). Please try accessing the site via localhost or an encrypted link.");
            return;
        }

        if (!navigator.geolocation) {
            showLocError(t('locationUnavailable'));
            return;
        }

        navigator.geolocation.getCurrentPosition(
            pos => {
                locLoadingMsg.textContent = t('searching');
                fetchNearbyFacilities(pos.coords.latitude, pos.coords.longitude);
            },
            err => {
                let msg;
                switch (err.code) {
                    case 1:  msg = t('locationDenied');      break;
                    case 2:  msg = t('locationUnavailable'); break;
                    case 3:  msg = t('locationTimeout');     break;
                    default: msg = t('locationError');       break;
                }
                showLocError(msg);
            },
            { timeout: 12000, maximumAge: 60000 }
        );
    }

    function showLocError(msg) {
        locErrorMsg.textContent = msg;
        showLocState('error');
    }

    async function fetchNearbyFacilities(lat, lon) {
        // Overpass API — no key needed, uses OpenStreetMap data
        const radius = 20000; // 20 km
        const query = `
[out:json][timeout:25];
(
  node["amenity"="hospital"](around:${radius},${lat},${lon});
  way["amenity"="hospital"](around:${radius},${lat},${lon});
  node["amenity"="clinic"](around:${radius},${lat},${lon});
  node["amenity"="pharmacy"](around:${radius},${lat},${lon});
  way["amenity"="pharmacy"](around:${radius},${lat},${lon});
  node["healthcare"="hospital"](around:${radius},${lat},${lon});
  node["healthcare"="pharmacy"](around:${radius},${lat},${lon});
);
out center body;
`.trim();

        try {
            const res = await fetch('https://overpass-api.de/api/interpreter', {
                method: 'POST',
                body: query
            });

            if (!res.ok) throw new Error('Overpass request failed');
            const data = await res.json();

            const hospitals  = [];
            const pharmacies = [];

            for (const el of data.elements) {
                const tags   = el.tags || {};
                const elLat  = el.lat  || (el.center && el.center.lat);
                const elLon  = el.lon  || (el.center && el.center.lon);
                if (!elLat || !elLon) continue;

                // Priority name extraction
                const name = tags.name || tags['name:en'] || tags['operator'] || tags['brand'] || tags.amenity || tags.healthcare;
                if (!name || name === 'hospital' || name === 'pharmacy') continue;

                const dist = haversine(lat, lon, elLat, elLon);
                const isHospital = tags.amenity === 'hospital' || tags.amenity === 'clinic' || tags.healthcare === 'hospital' || tags.healthcare === 'clinic';
                const isPharmacy = tags.amenity === 'pharmacy' || tags.healthcare === 'pharmacy';

                const entry = { name, dist, lat: elLat, lon: elLon };

                if (isHospital) {
                    hospitals.push(entry);
                } else if (isPharmacy) {
                    pharmacies.push(entry);
                }
            }

            hospitals.sort((a, b) => a.dist - b.dist);
            pharmacies.sort((a, b) => a.dist - b.dist);

            renderFacilityList(hospitalsList,  hospitals.slice(0, 8),  'hospital');
            renderFacilityList(pharmaciesList, pharmacies.slice(0, 8), 'pharmacy');
            showLocState('results');

        } catch (err) {
            console.error('Overpass error:', err);
            showLocError(t('locationError'));
        }
    }

    function renderFacilityList(container, facilities, type) {
        if (facilities.length === 0) {
            container.innerHTML = `<p class="facility-empty">${type === 'hospital' ? t('noHospitals') : t('noPharmacies')}</p>`;
            return;
        }

        const hospitalIcon = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>`;

        const pharmacyIcon = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <line x1="12" y1="8" x2="12" y2="16"/>
                <line x1="8" y1="12" x2="16" y2="12"/>
            </svg>`;

        container.innerHTML = facilities.map(f => {
            const distStr = `${f.dist.toFixed(1)} ${t('kmAway')}`;
            const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${f.lat},${f.lon}`;
            const icon = type === 'hospital' ? hospitalIcon : pharmacyIcon;
            return `
                <div class="facility-card">
                    <div class="facility-icon">${icon}</div>
                    <div class="facility-info">
                        <div class="facility-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
                        <div class="facility-dist">📍 ${distStr}</div>
                    </div>
                    <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="facility-dir-btn">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                            <polygon points="3 11 22 2 13 21 11 13 3 11"/>
                        </svg>
                        ${t('getDirections')}
                    </a>
                </div>
            `;
        }).join('');
    }

    nearbyBtn.addEventListener('click', openLocModal);
    locModalClose.addEventListener('click', closeLocModal);
    locModalOverlay.addEventListener('click', e => {
        if (e.target === locModalOverlay) closeLocModal();
    });
    locRetryBtn.addEventListener('click', startLocationSearch);

    // Close any modal on Escape
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            closeLangModal();
            closeLocModal();
            closeImageTypeModal();
        }
    });

    // ============================================================
    // IMAGE UPLOAD — Medicine & Disease Analysis
    // ============================================================
    const attachBtn        = document.getElementById('attachBtn');
    const imageUpload      = document.getElementById('imageUpload');
    const imageTypeOverlay = document.getElementById('imageTypeOverlay');
    const imageTypeClose   = document.getElementById('imageTypeClose');
    const medicineBtnModal = document.getElementById('medicineBtnModal');
    const diseaseBtnModal  = document.getElementById('diseaseBtnModal');

    let pendingImageType = null;

    function openImageTypeModal() {
        imageTypeOverlay.classList.add('open');
        imageTypeOverlay.setAttribute('aria-hidden', 'false');
        pendingImageType = null;
    }

    function closeImageTypeModal() {
        imageTypeOverlay.classList.remove('open');
        imageTypeOverlay.setAttribute('aria-hidden', 'true');
        // NOTE: do NOT reset pendingImageType here — it must survive until
        // the file picker's 'change' event fires after imageUpload.click()
    }

    if (attachBtn && imageUpload) {
        attachBtn.addEventListener('click', openImageTypeModal);

        imageTypeClose.addEventListener('click', () => {
            pendingImageType = null;  // user cancelled — safe to clear
            closeImageTypeModal();
        });
        imageTypeOverlay.addEventListener('click', e => {
            if (e.target === imageTypeOverlay) {
                pendingImageType = null;  // user cancelled — safe to clear
                closeImageTypeModal();
            }
        });

        medicineBtnModal.addEventListener('click', () => {
            pendingImageType = 'medicine';
            closeImageTypeModal();     // type is set BEFORE close, stays set
            imageUpload.click();
        });

        diseaseBtnModal.addEventListener('click', () => {
            pendingImageType = 'disease';
            closeImageTypeModal();     // type is set BEFORE close, stays set
            imageUpload.click();
        });

        imageUpload.addEventListener('change', async function () {
            const file = this.files[0];
            if (!file || !pendingImageType) {
                this.value = '';
                return;
            }
            this.value = ''; // reset

            // Show preview message
            const typeLabel = pendingImageType === 'medicine' ? '💊' : '🔍';
            addUserMessage(`${typeLabel} ${file.name}`);
            showTyping();

            const formData = new FormData();
            formData.append('image', file);
            formData.append('lang', getLang());

            const endpoint = pendingImageType === 'medicine' 
                ? '/api/analyze-image'
                : '/api/analyze-disease-image';

            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    body: formData,
                });
                const data = await res.json();
                removeTyping();

                if (data.error) {
                    addBotMessage(escapeHtml(data.error));
                    return;
                }

                if (pendingImageType === 'medicine') {
                    addMedicineCard(data);
                } else {
                    addDiseaseCard(data);
                }
            } catch (err) {
                removeTyping();
                addBotMessage(t('msgError'));
                console.error(err);
            }
        });
    }

    function addDiseaseCard(d) {
        const msg = document.createElement('div');
        msg.className = 'message bot';

        // Bug 2 fix: fallback to 'mild' if severity is null/undefined
        const severityColor = d.severity === 'severe' ? 'severe'
            : (d.severity === 'moderate' ? 'moderate' : 'mild');

        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <div class="disease-card">
                <div class="disease-card-header ${d.severity}">
                    <div class="disease-header-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <circle cx="12" cy="12" r="6"/>
                        </svg>
                    </div>
                    <div>
                        <h3>${escapeHtml(d.disease_name || 'Skin Condition Analysis')}</h3>
                        <span class="header-label">Visual Analysis</span>
                    </div>
                </div>
                <div class="disease-card-body">
                    <div class="disease-confidence-row">
                        <span class="confidence-label">Analysis Confidence:</span>
                        <span class="confidence-value">${escapeHtml(d.confidence || 'unknown').toUpperCase()}</span>
                    </div>

                    ${d.severity ? `<div class="disease-severity-badge ${severityColor}">
                        Severity: ${escapeHtml(String(d.severity).toUpperCase())}
                    </div>` : ''}

                    ${d.description ? `
                    <div class="disease-section">
                        <div class="disease-section-title">What is this?</div>
                        <p class="disease-text">${escapeHtml(d.description)}</p>
                    </div>` : ''}

                    ${d.symptoms ? `
                    <div class="disease-section">
                        <div class="disease-section-title">Common Symptoms</div>
                        <p class="disease-text">${escapeHtml(d.symptoms)}</p>
                    </div>` : ''}

                    ${d.causes ? `
                    <div class="disease-section">
                        <div class="disease-section-title">Causes &amp; Risk Factors</div>
                        <p class="disease-text">${escapeHtml(d.causes)}</p>
                    </div>` : ''}

                    ${d.when_to_see_doctor ? `
                    <div class="disease-section alert-box">
                        <div class="disease-section-title">⚠️ When to See a Doctor</div>
                        <p class="disease-text">${escapeHtml(d.when_to_see_doctor)}</p>
                    </div>` : ''}

                    ${d.treatment_options ? `
                    <div class="disease-section">
                        <div class="disease-section-title">General Treatment Information</div>
                        <p class="disease-text">${escapeHtml(d.treatment_options)}</p>
                    </div>` : ''}

                    ${d.prevention ? `
                    <div class="disease-section">
                        <div class="disease-section-title">Prevention &amp; Management</div>
                        <p class="disease-text">${escapeHtml(d.prevention)}</p>
                    </div>` : ''}

                    ${d.disclaimer ? `
                    <div class="disease-disclaimer">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                        <span>${escapeHtml(d.disclaimer)}</span>
                    </div>` : ''}
                </div>
            </div>
        `;

        chatMessages.appendChild(msg);
        scrollToBottom();
    }

    function addMedicineCard(d) {
        const msg  = document.createElement('div');
        msg.className = 'message bot';

        const isExpired = d.is_expired === true;
        const expClass  = isExpired ? 'expired' : (d.is_expired === false ? 'valid' : '');

        const metaField = (label, value, cls = '') => value
            ? `<div class="medicine-meta-item">
                 <div class="medicine-meta-label">${escapeHtml(label)}</div>
                 <div class="medicine-meta-value ${cls}">${escapeHtml(String(value))}</div>
               </div>`
            : '';

        const expiredBanner = isExpired
            ? `<div class="medicine-expired-banner">⚠️ This medicine has expired. Do not consume it.</div>`
            : '';

        const warningBlock = d.warnings
            ? `<div>
                 <div class="medicine-section-title">Warnings &amp; Storage</div>
                 <div class="medicine-warning">⚠️ ${escapeHtml(d.warnings)}</div>
               </div>`
            : '';

        const dosageBlock = d.dosage_info
            ? `<div>
                 <div class="medicine-section-title">Dosage</div>
                 <div class="medicine-purpose">${escapeHtml(d.dosage_info)}</div>
               </div>`
            : '';

        // Generate purchase links
        const medicineName = d.medicine_name ? encodeURIComponent(d.medicine_name) : '';
        const purchaseLinks = medicineName ? `
            <div class="medicine-purchase-section">
                <div class="medicine-section-title">Buy Online</div>
                <div class="purchase-links-grid">
                    <a href="https://www.amazon.in/s?k=${medicineName}" target="_blank" rel="noopener noreferrer" class="purchase-link amazon">
                        <span class="purchase-link-icon">📦</span>
                        <span class="purchase-link-name">Amazon</span>
                    </a>
                    <a href="https://www.flipkart.com/search?q=${medicineName}" target="_blank" rel="noopener noreferrer" class="purchase-link flipkart">
                        <span class="purchase-link-icon">📦</span>
                        <span class="purchase-link-name">Flipkart</span>
                    </a>
                    <a href="https://www.pharmeasy.in/search/all?name=${medicineName}" target="_blank" rel="noopener noreferrer" class="purchase-link pharmeasy">
                        <span class="purchase-link-icon">💊</span>
                        <span class="purchase-link-name">PharmEasy</span>
                    </a>
                    <a href="https://www.1mg.com/search/${medicineName}" target="_blank" rel="noopener noreferrer" class="purchase-link onemedical">
                        <span class="purchase-link-icon">💊</span>
                        <span class="purchase-link-name">1mg</span>
                    </a>
                </div>
            </div>
        ` : '';

        msg.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            </div>
            <div class="medicine-card">
                <div class="medicine-card-header">
                    <div class="medicine-header-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="2"/>
                            <line x1="12" y1="8" x2="12" y2="16"/>
                            <line x1="8" y1="12" x2="16" y2="12"/>
                        </svg>
                    </div>
                    <div>
                        <h3>${escapeHtml(d.medicine_name || 'Medicine Analysis')}</h3>
                        <span class="header-label">${escapeHtml(d.dosage_form || 'Medicine Label')}</span>
                    </div>
                </div>
                <div class="medicine-card-body">
                    ${expiredBanner}

                    ${d.medicine_type ? `
                    <div class="medicine-type-badge">
                        🏷️ ${escapeHtml(d.medicine_type)}
                    </div>` : ''}

                    <div class="medicine-meta-grid">
                        ${metaField('MFG Date',    d.mfg_date)}
                        ${metaField('EXP Date',    d.exp_date, expClass)}
                        ${metaField('Batch No.',   d.batch_no)}
                        ${metaField('MRP',         d.mrp)}
                        ${metaField('Manufacturer',d.manufacturer)}
                        ${metaField('Composition', d.composition)}
                    </div>

                    ${d.purpose ? `
                    <div>
                        <div class="medicine-section-title">Purpose / Uses</div>
                        <div class="medicine-purpose">${escapeHtml(d.purpose)}</div>
                    </div>` : ''}

                    ${dosageBlock}
                    ${warningBlock}
                    ${purchaseLinks}

                    <div class="medicine-confidence">
                        Label readability: ${escapeHtml(d.confidence || 'unknown')}
                    </div>
                </div>
            </div>
        `;

        chatMessages.appendChild(msg);
        scrollToBottom();
    }
    sendBtn.addEventListener('click', handleSend);

    userInput.addEventListener('keydown', function (e) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeAutocompleteIdx = Math.min(activeAutocompleteIdx + 1, items.length - 1);
            updateActiveItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeAutocompleteIdx = Math.max(activeAutocompleteIdx - 1, 0);
            updateActiveItem(items);
        } else if (e.key === 'Enter') {
            if (activeAutocompleteIdx >= 0 && items[activeAutocompleteIdx]) {
                e.preventDefault();
                selectAutocompleteItem(items[activeAutocompleteIdx].dataset.value);
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
        if (this.value.trim().length > 1 && currentState === STATE.WAITING_SYMPTOM) {
            showAutocomplete(this.value.trim());
        }
    });

    dropdown.addEventListener('click', function (e) {
        const item = e.target.closest('.autocomplete-item');
        if (item) selectAutocompleteItem(item.dataset.value);
    });

    document.addEventListener('click', function (e) {
        if (!inputWrapper.contains(e.target)) hideAutocomplete();
    });

    btnYes.addEventListener('click', () => handleFollowupAnswer(true));
    btnNo.addEventListener('click',  () => handleFollowupAnswer(false));

    // ============================================================
    // UTILITIES
    // ============================================================
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeRegExp(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // ============================================================
    // START
    // ============================================================
    init();

})();