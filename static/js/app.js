// app.js — Single-Page Application Logic

let ws = null;
let pollTimer = null;
let allLeads = [];
let selectedLeadIds = new Set();
let lastEvaluatedManualLead = null;
let stagedOpportunities = [];
let editingStagedId = null;
let currentEvaluatingLeadId = null;
let manualLinkedinVariants = [];

// Canonical match_score -> Priority thresholds, mirrored from
// app/config/constants.py's score_to_priority() so the dashboard, SharePoint
// export, and AI JD extraction never disagree on what a score means.
const SCORE_PRIORITY_HIGH_THRESHOLD = 70;
const SCORE_PRIORITY_MEDIUM_THRESHOLD = 40;

function getSelectedOwner() {
    const manualOwnerEl = document.getElementById('manual-owner');
    const leadsOwnerEl = document.getElementById('leads-owner');
    if (manualOwnerEl && manualOwnerEl.value) return manualOwnerEl.value;
    if (leadsOwnerEl && leadsOwnerEl.value) return leadsOwnerEl.value;
    return 'Meet';
}

function setSelectedOwner(val) {
    if (!val) return;
    const manualOwnerEl = document.getElementById('manual-owner');
    const leadsOwnerEl = document.getElementById('leads-owner');
    if (manualOwnerEl) manualOwnerEl.value = val;
    if (leadsOwnerEl) leadsOwnerEl.value = val;
}

function initOwnerSynchronization() {
    const leadsOwnerEl = document.getElementById('leads-owner');
    const manualOwnerEl = document.getElementById('manual-owner');
    if (leadsOwnerEl) {
        leadsOwnerEl.addEventListener('change', () => {
            if (manualOwnerEl) manualOwnerEl.value = leadsOwnerEl.value;
        });
    }
    if (manualOwnerEl) {
        manualOwnerEl.addEventListener('change', () => {
            if (leadsOwnerEl) leadsOwnerEl.value = manualOwnerEl.value;
        });
    }
}

function scoreToPriority(score) {
    if (score === null || score === undefined || isNaN(Number(score))) return 'Low';
    const value = Number(score);
    if (value >= SCORE_PRIORITY_HIGH_THRESHOLD) return 'High';
    if (value >= SCORE_PRIORITY_MEDIUM_THRESHOLD) return 'Medium';
    return 'Low';
}

function scoreBadgeClasses(score) {
    switch (scoreToPriority(score)) {
        case 'High': return 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
        case 'Medium': return 'bg-blue-50 text-blue-800 border-blue-300 font-bold';
        default: return 'bg-rose-50 text-rose-700 border-rose-300 font-semibold';
    }
}

function toggleLeadSelection(leadId, isChecked) {
    const idStr = String(leadId);
    if (isChecked) {
        selectedLeadIds.add(idStr);
    } else {
        selectedLeadIds.delete(idStr);
    }
    updateSelectedLeadsUI();
}

function toggleSelectAllLeads(isChecked) {
    if (isChecked) {
        allLeads.forEach(l => selectedLeadIds.add(String(l.id)));
    } else {
        selectedLeadIds.clear();
    }
    // Update individual checkboxes without full re-render for speed
    document.querySelectorAll('.lead-select-cb').forEach(cb => {
        cb.checked = isChecked;
    });
    updateSelectedLeadsUI();
}

function updateSelectedLeadsUI() {
    const total = allLeads.length;
    const selectedCount = allLeads.filter(l => selectedLeadIds.has(String(l.id))).length;

    // Update select-all checkbox state
    const selectAllCb = document.getElementById('select-all-leads');
    if (selectAllCb) {
        selectAllCb.checked = total > 0 && selectedCount === total;
        selectAllCb.indeterminate = selectedCount > 0 && selectedCount < total;
    }

    // Update count badge
    const countEl = document.getElementById('leads-count');
    if (countEl) {
        if (total > 0 && selectedCount < total) {
            countEl.textContent = `${selectedCount}/${total} Selected`;
        } else {
            countEl.textContent = `${total}`;
        }
    }

    // Update Download Excel and SharePoint buttons text/href
    const navDl = document.getElementById('nav-download-btn');
    const tblDl = document.getElementById('table-download-btn');
    const navSp = document.getElementById('nav-sharepoint-btn');
    const tblSp = document.getElementById('table-sharepoint-btn');

    const dlText = selectedCount < total && selectedCount > 0
        ? `Download Excel (${selectedCount})`
        : 'Download Excel';
    const spText = selectedCount < total && selectedCount > 0
        ? `Sync to SharePoint (${selectedCount})`
        : 'Sync to SharePoint';

    [navDl, tblDl].forEach(btn => {
        if (!btn) return;
        const svg = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>`;
        btn.innerHTML = `${svg} ${dlText}`;
    });

    [navSp, tblSp].forEach(btn => {
        if (!btn) return;
        if (!btn.disabled) {
            const svg = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>`;
            btn.innerHTML = `${svg} ${spText}`;
        }
    });
}

function getSelectedCountries() {
    const radios = document.querySelectorAll('input[name="country_radio"]:checked');
    if (radios.length > 0) {
        return Array.from(radios).map(cb => cb.value);
    }
    const checkboxes = document.querySelectorAll('input[name="country_checkbox"]:checked');
    const selected = Array.from(checkboxes).map(cb => cb.value);
    return selected.length > 0 ? selected : ['US'];
}

function updateSelectedCountryDisplay() {
    updateSelectedCountriesDisplay();
}

function updateSelectedCountriesDisplay() {
    const selectedInput = document.querySelector('input[name="country_radio"]:checked') ||
                          document.querySelector('input[name="country_checkbox"]:checked');
    const bar = document.getElementById('selected-countries-bar');
    const badge = document.getElementById('country-count-badge');
    
    // Highlight the selected country card and reset others
    document.querySelectorAll('.country-item-label').forEach(lbl => {
        const radio = lbl.querySelector('input[type="radio"]');
        if (radio && radio.checked) {
            lbl.classList.add('border-blue-500', 'bg-blue-50/70', 'ring-1', 'ring-blue-400/40');
            lbl.classList.remove('border-slate-200', 'bg-white');
        } else {
            lbl.classList.remove('border-blue-500', 'bg-blue-50/70', 'ring-1', 'ring-blue-400/40');
            lbl.classList.add('border-slate-200', 'bg-white');
        }
    });

    const code = selectedInput ? selectedInput.value : 'US';
    const name = selectedInput ? (selectedInput.getAttribute('data-name') || code) : 'United States';

    if (badge) {
        badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200';
        badge.textContent = `1 Selected (${code}) — Stealth Mode Active`;
    }

    if (!bar) return;

    bar.innerHTML = `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold bg-emerald-50 text-emerald-800 border border-emerald-200 shadow-2xs">
        <span>🌐 ${esc(name)}</span>
        <span class="text-emerald-500 font-mono text-[11px]">(${esc(code)})</span>
        <span class="text-emerald-400 text-[10px] font-normal">&bull; Single Country Focus Active</span>
    </span>`;
}

function selectAllCountries() {
    const checkboxes = document.querySelectorAll('input[name="country_checkbox"]');
    checkboxes.forEach(cb => cb.checked = true);
    updateSelectedCountriesDisplay();
}

function clearAllCountries() {
    const checkboxes = document.querySelectorAll('input[name="country_checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
    updateSelectedCountriesDisplay();
}

// 11 Core Keywords & Checkbox Management
const DEFAULT_CORE_KEYWORDS = [
    "SharePoint",
    "Power Apps",
    "Power Automate",
    "Power BI",
    "Purview",
    "AI",
    ".NET",
    "React",
    "SPFx",
    "n8n",
    "Intune"
];

function getSelectedKeywords() {
    const checkedBoxes = document.querySelectorAll('input[name="keyword_checkbox"]:checked');
    const selected = Array.from(checkedBoxes).map(cb => cb.value.trim()).filter(Boolean);
    return selected.length > 0 ? selected : DEFAULT_CORE_KEYWORDS;
}

function selectAllKeywords(checkAll) {
    const checkboxes = document.querySelectorAll('input[name="keyword_checkbox"]');
    checkboxes.forEach(cb => cb.checked = !!checkAll);
    updateSelectedKeywordsDisplay();
}

function updateSelectedKeywordsDisplay() {
    const checkedBoxes = document.querySelectorAll('input[name="keyword_checkbox"]:checked');
    const totalBoxes = document.querySelectorAll('input[name="keyword_checkbox"]');
    const badge = document.getElementById('keyword-count-badge');
    const queueBar = document.getElementById('active-keywords-queue');

    const count = checkedBoxes.length;

    if (badge) {
        if (count === 0) {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-700 border border-rose-200';
            badge.textContent = '0 Selected (Select at least 1)';
        } else if (count === totalBoxes.length) {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200';
            badge.textContent = `${count} Active (All Core Selected)`;
        } else {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-700 border border-blue-200';
            badge.textContent = `${count} / ${totalBoxes.length} Selected`;
        }
    }

    if (!queueBar) return;

    if (count === 0) {
        queueBar.innerHTML = `<span class="text-rose-500 text-xs italic">No keywords selected. Please check at least one role above.</span>`;
        return;
    }

    queueBar.innerHTML = Array.from(checkedBoxes).map((cb, idx) => `
        <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 shadow-2xs shrink-0">
            <span class="w-3.5 h-3.5 rounded-full bg-blue-200 text-blue-800 text-[10px] flex items-center justify-center font-bold">${idx + 1}</span>
            <span>${esc(cb.value)}</span>
        </span>
    `).join('');
}

function handleKeywordInputKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        addCustomKeywordCheckbox();
    }
}

function addCustomKeywordCheckbox() {
    const input = document.getElementById('input-new-keyword');
    if (!input) return;
    const rawVal = (input.value || '').trim();
    if (!rawVal) return;

    const parts = rawVal.split(',').map(p => p.trim()).filter(Boolean);
    const grid = document.getElementById('keywords-checkbox-grid');
    if (!grid) return;

    parts.forEach(kw => {
        // Check if already exists
        const existing = Array.from(document.querySelectorAll('input[name="keyword_checkbox"]'))
            .some(cb => cb.value.toLowerCase() === kw.toLowerCase());
        if (existing) return;

        const label = document.createElement('label');
        label.className = 'keyword-item flex items-center gap-2 bg-blue-50/50 hover:bg-blue-50 border border-blue-300 rounded-xl px-3 py-2 cursor-pointer transition-all shadow-2xs group';
        label.innerHTML = `
            <input type="checkbox" name="keyword_checkbox" value="${esc(kw)}" checked onchange="updateSelectedKeywordsDisplay()"
                class="w-4 h-4 rounded bg-white border-slate-300 text-blue-600 focus:ring-blue-500/20 accent-blue-600 cursor-pointer">
            <span class="text-xs text-slate-800 font-bold group-hover:text-blue-700 truncate">${esc(kw)}</span>
            <button type="button" onclick="this.closest('label').remove(); updateSelectedKeywordsDisplay();" class="ml-auto text-slate-400 hover:text-rose-500 text-xs font-bold" title="Remove">&times;</button>
        `;
        grid.appendChild(label);
    });

    input.value = '';
    updateSelectedKeywordsDisplay();
}

// --- Dice tab: keyword/country multi-select state, kept separate from the
// scraper tab's own keyword/country state above (DEFAULT_CORE_KEYWORDS,
// getSelectedKeywords, etc.) so the two panels never cross-contaminate each
// other's search parameters. ---

const DICE_MAX_SEARCH_COMBINATIONS = 15;

function getDiceSelectedKeywords() {
    const checkedBoxes = document.querySelectorAll('input[name="dice_keyword_checkbox"]:checked');
    return Array.from(checkedBoxes).map(cb => cb.value.trim()).filter(Boolean);
}

function getDiceSelectedCountries() {
    const checkedBoxes = document.querySelectorAll('input[name="dice_country_checkbox"]:checked');
    return Array.from(checkedBoxes).map(cb => cb.value.trim()).filter(Boolean);
}

function diceSelectAllKeywords(checkAll) {
    document.querySelectorAll('input[name="dice_keyword_checkbox"]').forEach(cb => cb.checked = !!checkAll);
    updateDiceKeywordDisplay();
}

function diceSelectAllCountries(checkAll) {
    document.querySelectorAll('input[name="dice_country_checkbox"]').forEach(cb => cb.checked = !!checkAll);
    updateDiceCountryDisplay();
}

function updateDiceKeywordDisplay() {
    const checkedBoxes = document.querySelectorAll('input[name="dice_keyword_checkbox"]:checked');
    const totalBoxes = document.querySelectorAll('input[name="dice_keyword_checkbox"]');
    const badge = document.getElementById('dice-keyword-count-badge');
    const count = checkedBoxes.length;

    if (badge) {
        if (count === 0) {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-700 border border-rose-200';
            badge.textContent = '0 Selected (Select at least 1)';
        } else if (count === totalBoxes.length) {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200';
            badge.textContent = `${count} Active (All Selected)`;
        } else {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-700 border border-blue-200';
            badge.textContent = `${count} / ${totalBoxes.length} Selected`;
        }
    }

    updateDiceComboCount();
}

function updateDiceCountryDisplay() {
    const count = getDiceSelectedCountries().length;
    const badge = document.getElementById('dice-country-count-badge');

    if (badge) {
        if (count === 0) {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600 border border-slate-200';
            badge.textContent = '0 Selected (Any)';
        } else {
            badge.className = 'px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-700 border border-blue-200';
            badge.textContent = `${count} Selected`;
        }
    }

    updateDiceComboCount();
}

function updateDiceComboCount() {
    const keywordCount = getDiceSelectedKeywords().length;
    const countryCount = Math.max(getDiceSelectedCountries().length, 1);
    const combos = keywordCount * countryCount;

    const btn = document.getElementById('btn-dice-search');
    const statusNote = document.getElementById('dice-status-note');
    const overCap = combos > DICE_MAX_SEARCH_COMBINATIONS;

    if (btn) btn.disabled = keywordCount === 0 || overCap;

    if (statusNote) {
        if (keywordCount === 0) {
            statusNote.className = 'text-xs text-rose-500 font-medium';
            statusNote.textContent = 'Select at least one keyword.';
        } else if (overCap) {
            statusNote.className = 'text-xs text-rose-500 font-medium';
            statusNote.textContent = `Too many combinations (${combos}). Narrow to ${DICE_MAX_SEARCH_COMBINATIONS} or fewer keyword × country pairs.`;
        } else {
            statusNote.className = 'text-xs text-slate-500 font-medium';
            statusNote.textContent = `Will run ${combos} search${combos === 1 ? '' : 'es'} (${keywordCount} keyword${keywordCount === 1 ? '' : 's'} × ${getDiceSelectedCountries().length || 1} location${getDiceSelectedCountries().length === 1 ? '' : 's'}).`;
        }
    }
}

function handleDiceKeywordInputKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        addDiceCustomKeywordCheckbox();
    }
}

function addDiceCustomKeywordCheckbox() {
    const input = document.getElementById('dice-input-new-keyword');
    if (!input) return;
    const rawVal = (input.value || '').trim();
    if (!rawVal) return;

    const parts = rawVal.split(',').map(p => p.trim()).filter(Boolean);
    const grid = document.getElementById('dice-keywords-checkbox-grid');
    if (!grid) return;

    parts.forEach(kw => {
        const existing = Array.from(document.querySelectorAll('input[name="dice_keyword_checkbox"]'))
            .some(cb => cb.value.toLowerCase() === kw.toLowerCase());
        if (existing) return;

        const label = document.createElement('label');
        label.className = 'dice-keyword-item flex items-center gap-2 bg-blue-50/50 hover:bg-blue-50 border border-blue-300 rounded-xl px-3 py-2 cursor-pointer transition-all shadow-2xs group';
        label.innerHTML = `
            <input type="checkbox" name="dice_keyword_checkbox" value="${esc(kw)}" checked onchange="updateDiceKeywordDisplay()"
                class="w-4 h-4 rounded bg-white border-slate-300 text-blue-600 focus:ring-blue-500/20 accent-blue-600 cursor-pointer">
            <span class="text-xs text-slate-800 font-bold group-hover:text-blue-700 truncate">${esc(kw)}</span>
            <button type="button" onclick="this.closest('label').remove(); updateDiceKeywordDisplay();" class="ml-auto text-slate-400 hover:text-rose-500 text-xs font-bold" title="Remove">&times;</button>
        `;
        grid.appendChild(label);
    });

    input.value = '';
    updateDiceKeywordDisplay();
}

let isSearchRunning = false;

function setSearchButtonState(disabled, text = 'Search Jobs') {
    const btn = document.getElementById('btn-search');
    const label = document.getElementById('btn-search-label') || btn;
    const icon = document.getElementById('btn-search-icon');
    if (!btn) return;

    btn.disabled = !!disabled;
    if (disabled) {
        btn.classList.add('opacity-60', 'cursor-not-allowed');
        if (label) label.textContent = text;
        if (icon) {
            icon.outerHTML = `<svg id="btn-search-icon" class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg>`;
        }
    } else {
        btn.classList.remove('opacity-60', 'cursor-not-allowed');
        if (label) label.textContent = 'Search Jobs';
        if (icon) {
            icon.outerHTML = `<svg id="btn-search-icon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>`;
        }
    }
}

function setStopButtonState(disabled, text = 'Stop') {
    const btn = document.getElementById('btn-stop');
    const label = document.getElementById('btn-stop-label') || btn;
    const icon = document.getElementById('btn-stop-icon');
    if (!btn) return;

    btn.disabled = !!disabled;
    if (disabled) {
        btn.classList.add('opacity-40', 'cursor-not-allowed');
        if (label) label.textContent = text;
        if (icon) {
            icon.outerHTML = `<svg id="btn-stop-icon" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"/></svg>`;
        }
    } else {
        btn.classList.remove('opacity-40', 'cursor-not-allowed');
        if (label) label.textContent = 'Stop';
        if (icon) {
            icon.outerHTML = `<svg id="btn-stop-icon" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"/></svg>`;
        }
    }
}

// Start User-Defined Search (1 Country + Selected Keywords)
async function startSearch() {
    const btnSearch = document.getElementById('btn-search');
    // Prevent duplicate clicks: immediately return if already running or button disabled
    if (isSearchRunning || (btnSearch && btnSearch.disabled)) {
        return;
    }

    const countries = getSelectedCountries();
    const keywords = getSelectedKeywords();

    if (keywords.length === 0) {
        showAlertModal('Selection Required', 'Please check at least 1 keyword to search.', 'warning');
        return;
    }

    const locationType = document.getElementById('input-location')?.value || 'remote';
    const fromage = document.getElementById('input-fromage')?.value || '1';
    const pages = parseInt(document.getElementById('input-pages')?.value || '1');
    const parserEngine = document.getElementById('input-parser')?.value || 'beautifulsoup';

    // Lock UI immediately so no one can click again
    isSearchRunning = true;
    setSearchButtonState(true, 'Starting Search...');
    setStopButtonState(false);
    const countryCode = countries[0] || 'US';
    document.getElementById('search-status').textContent = `Status: Initializing ${keywords.length} keywords in ${countryCode}...`;

    try {
        const res = await fetch('/api/scraper/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                countries,
                queries: keywords,
                query: keywords[0],
                location_type: locationType,
                fromage,
                max_pages: pages,
                parser_engine: parserEngine
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            isSearchRunning = false;
            setSearchButtonState(false);
            setStopButtonState(true);
            document.getElementById('search-status').textContent = 'Status: Ready';
            showAlertModal('Search Notice', data.detail || 'Failed to start search', 'warning');
            return;
        }

        document.getElementById('search-status').textContent = `Status: Scraping ${keywords.length} keywords in ${countryCode}...`;
        setSearchButtonState(true, 'Scraping Active...');
        setStopButtonState(false);

        // Start polling for live table and progress updates
        if (pollTimer) clearInterval(pollTimer);
        fetchLeads();
        fetchScraperProgress();
        pollTimer = setInterval(() => {
            fetchLeads();
            fetchScraperProgress();
        }, 1500);

    } catch (e) {
        isSearchRunning = false;
        setSearchButtonState(false);
        setStopButtonState(true);
        document.getElementById('search-status').textContent = 'Status: Ready';
        showAlertModal('Connection Error', e.message, 'error');
    }
}

async function stopSearch() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
    setStopButtonState(true, 'Stopping...');
    document.getElementById('search-status').textContent = 'Status: Stopping Scraper...';
    try {
        await fetch('/api/scraper/stop', { method: 'POST' });
    } catch (e) {
        console.error('Failed to trigger stop:', e);
    }
    // Immediately unlock UI and reset state so user can search again without delay
    isSearchRunning = false;
    setSearchButtonState(false);
    setStopButtonState(true);
    const searchStatusEl = document.getElementById('search-status');
    if (searchStatusEl) {
        searchStatusEl.textContent = 'Status: Stopped. Ready to search.';
    }
    fetchLeads();
}

let lastLeadsHash = '';
let isUserHoveringSkills = false;

// Global floating tooltip element
let globalTooltip = null;

function initGlobalTooltip() {
    if (globalTooltip) return;
    globalTooltip = document.createElement('div');
    globalTooltip.id = 'skills-floating-tooltip';
    globalTooltip.className = 'fixed z-[9999] hidden flex-col bg-white border border-slate-200 rounded-xl shadow-2xl p-3 min-w-[220px] max-w-[340px] pointer-events-none transition-opacity duration-150 text-xs';
    document.body.appendChild(globalTooltip);
}

function showSkillsTooltip(event, type, skillsJson) {
    initGlobalTooltip();
    isUserHoveringSkills = true;
    let skills = [];
    try {
        skills = typeof skillsJson === 'string' ? JSON.parse(decodeURIComponent(skillsJson)) : skillsJson;
    } catch(e) {
        skills = [];
    }

    if (!skills || skills.length === 0) return;

    const isMatched = type === 'matched';
    const titleColor = isMatched ? 'text-emerald-800' : 'text-rose-800';
    const titleIcon = isMatched ? '✓ All Matched Skills' : '✕ All Missing Skills';
    const badgeBg = isMatched 
        ? 'bg-emerald-50 text-emerald-800 border-emerald-200' 
        : 'bg-rose-50 text-rose-700 border-rose-200';

    const badgesHtml = skills.map(s => 
        `<span class="inline-block ${badgeBg} border text-[10px] font-medium px-1.5 py-0.5 rounded shadow-2xs">${esc(s)}</span>`
    ).join(' ');

    globalTooltip.innerHTML = `
        <div class="text-[10px] font-bold ${titleColor} uppercase tracking-wider mb-2 flex items-center justify-between border-b border-slate-100 pb-1">
            <span>${titleIcon}</span>
            <span class="font-extrabold bg-slate-100 px-1.5 py-0.2 rounded-full text-slate-700 text-[9px]">${skills.length}</span>
        </div>
        <div class="flex flex-wrap gap-1 max-h-[220px] overflow-y-auto pr-0.5">
            ${badgesHtml}
        </div>
    `;

    globalTooltip.classList.remove('hidden');
    positionSkillsTooltip(event.currentTarget || event.target);
}

function positionSkillsTooltip(targetEl) {
    if (!globalTooltip || !targetEl) return;
    const rect = targetEl.getBoundingClientRect();
    const tooltipRect = globalTooltip.getBoundingClientRect();

    let top = rect.top - tooltipRect.height - 8;
    let left = rect.left;

    // If top is outside viewport (or clipped by sticky header), show below target
    if (top < 10) {
        top = rect.bottom + 8;
    }
    // If right side goes outside viewport, shift left
    if (left + tooltipRect.width > window.innerWidth - 16) {
        left = window.innerWidth - tooltipRect.width - 16;
    }
    if (left < 10) left = 10;

    globalTooltip.style.top = `${top}px`;
    globalTooltip.style.left = `${left}px`;
}

function hideSkillsTooltip() {
    isUserHoveringSkills = false;
    if (globalTooltip) {
        globalTooltip.classList.add('hidden');
    }
}

async function fetchLeads() {
    try {
        const res = await fetch('/api/leads');
        const data = await res.json();
        const incomingLeads = data.leads || [];

        // allLeads/selectedLeadIds/the table and its buttons are shared, mode-owned state.
        // This poll keeps running in the background while a scrape is active even if the
        // user has switched to another tab, so don't let it clobber a different mode's
        // view of that shared state. (Scraper progress/log polling is a separate function,
        // fetchScraperProgress(), and is unaffected by this early return.)
        if (currentAppMode !== 'scraper') {
            return;
        }

        // Auto-select newly scraped leads if not already in selectedLeadIds
        incomingLeads.forEach(l => {
            const idStr = String(l.id);
            if (!selectedLeadIds.has(idStr)) {
                selectedLeadIds.add(idStr);
            }
        });

        // Remove old IDs that no longer exist
        const incomingIdSet = new Set(incomingLeads.map(l => String(l.id)));
        for (const id of Array.from(selectedLeadIds)) {
            if (!incomingIdSet.has(id)) {
                selectedLeadIds.delete(id);
            }
        }

        allLeads = incomingLeads;

        // Check if data actually changed to prevent DOM blinking
        const currentHash = JSON.stringify(allLeads.map(l => [l.id, l.match_score, l.job_title, l.company]));
        if (currentHash !== lastLeadsHash) {
            // Only update table if content changed AND user is not actively hovering skills popup
            if (!isUserHoveringSkills) {
                lastLeadsHash = currentHash;
                renderTable(allLeads);
            }
        } else {
            updateSelectedLeadsUI();
        }

        // Show download, SharePoint sync, and Clear buttons if leads exist
        const navDl = document.getElementById('nav-download-btn');
        const tblDl = document.getElementById('table-download-btn');
        const navSp = document.getElementById('nav-sharepoint-btn');
        const tblSp = document.getElementById('table-sharepoint-btn');
        const tblOutreach = document.getElementById('table-generate-outreach-btn');
        const tblClr = document.getElementById('table-clear-btn');
        const hasLeads = allLeads.length > 0;

        [navDl, tblDl].forEach(b => b && b.classList.toggle('hidden', !hasLeads));
        const showSp = hasLeads && (currentAppMode === 'scraper');
        [navSp, tblSp].forEach(b => b && b.classList.toggle('hidden', !showSp));
        if (tblOutreach) tblOutreach.classList.toggle('hidden', !showSp);
        if (tblClr) tblClr.classList.toggle('hidden', !hasLeads);
    } catch (e) {
        console.error('Error fetching leads:', e);
    }
}

function renderTable(leads) {
    const tbody = document.getElementById('leads-body');
    const countEl = document.getElementById('leads-count');
    if (countEl) countEl.textContent = leads.length;

    if (!tbody) return;

    if (!leads || leads.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="14" class="px-5 py-12 text-center text-slate-400 font-medium">
                    No leads found yet. Click <strong class="text-slate-700">"Search Jobs"</strong> above.
                </td>
            </tr>`;
        updateSelectedLeadsUI();
        return;
    }

    // Sort leads client-side: Highest Match Score first (unranked at bottom)
    const sortedLeads = [...leads].sort((a, b) => {
        const scoreA = (a.match_score !== null && a.match_score !== undefined) ? Number(a.match_score) : -1;
        const scoreB = (b.match_score !== null && b.match_score !== undefined) ? Number(b.match_score) : -1;
        return scoreB - scoreA;
    });

    tbody.innerHTML = sortedLeads.map((l, idx) => {
        const isSelected = selectedLeadIds.has(String(l.id));
        const seqNumber = idx + 1;
        const descSnippet = l.job_description ? (l.job_description.length > 80 ? l.job_description.slice(0, 80) + '...' : l.job_description) : 'No description available';
        const expText = l.experience || 'Not specified';
        const isFresher = expText.toLowerCase().includes('fresher') || expText.toLowerCase().includes('entry');
        const expBadgeClass = isFresher 
            ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
            : (expText !== 'Not specified' ? 'bg-amber-50 text-amber-800 border-amber-200' : 'bg-slate-100 text-slate-500 border-slate-200');

        // Match Score Badge styling
        let matchScoreBadge = '<span class="text-slate-400 text-[11px] font-medium">—</span>';
        if (l.match_score !== null && l.match_score !== undefined) {
            const score = Number(l.match_score);
            const badgeBg = scoreBadgeClasses(score);
            matchScoreBadge = `<span class="inline-flex items-center justify-center min-w-[42px] px-2 py-0.5 rounded-full text-xs border shadow-2xs ${badgeBg}">${score}%</span>`;
        }

        // Matched Skills Tags with Floating Portal Hover Tooltip
        let matchedSkillsHtml = '<span class="text-slate-400 text-[11px]">—</span>';
        if (l.matched_skills && l.matched_skills.length > 0) {
            const visible = l.matched_skills.slice(0, 2).map(s => `<span class="inline-block bg-emerald-50 text-emerald-800 border border-emerald-200 text-[10px] font-medium px-1.5 py-0.5 rounded">${esc(s)}</span>`).join(' ');
            const remainingCount = l.matched_skills.length - 2;
            const encodedSkills = encodeURIComponent(JSON.stringify(l.matched_skills));

            matchedSkillsHtml = `
                <div class="inline-flex flex-wrap gap-1 items-center cursor-pointer"
                     onmouseenter="showSkillsTooltip(event, 'matched', '${encodedSkills}')"
                     onmouseleave="hideSkillsTooltip()">
                    ${visible}
                    ${remainingCount > 0 ? `<span class="text-[10px] bg-emerald-100 text-emerald-800 font-bold px-1.5 py-0.5 rounded-full border border-emerald-300 hover:bg-emerald-200 transition-colors">+${remainingCount}</span>` : ''}
                </div>
            `;
        }

        // Missing Skills Tags with Floating Portal Hover Tooltip
        let missingSkillsHtml = '<span class="text-slate-400 text-[11px]">—</span>';
        if (l.missing_skills && l.missing_skills.length > 0) {
            const visible = l.missing_skills.slice(0, 2).map(s => `<span class="inline-block bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-medium px-1.5 py-0.5 rounded">${esc(s)}</span>`).join(' ');
            const remainingCount = l.missing_skills.length - 2;
            const encodedSkills = encodeURIComponent(JSON.stringify(l.missing_skills));

            missingSkillsHtml = `
                <div class="inline-flex flex-wrap gap-1 items-center cursor-pointer"
                     onmouseenter="showSkillsTooltip(event, 'missing', '${encodedSkills}')"
                     onmouseleave="hideSkillsTooltip()">
                    ${visible}
                    ${remainingCount > 0 ? `<span class="text-[10px] bg-rose-100 text-rose-800 font-bold px-1.5 py-0.5 rounded-full border border-rose-300 hover:bg-rose-200 transition-colors">+${remainingCount}</span>` : ''}
                </div>
            `;
        }

        // Job Summary snippet (instead of Match Reason)
        const summaryText = (l.job_summary || l.summary || l.match_reason || '').trim() || 'No summary available';
        const summarySnippet = summaryText.length > 115 ? summaryText.slice(0, 115) + '...' : summaryText;

        return `
        <tr class="border-b border-slate-100 hover:bg-slate-50/80 transition-colors ${isSelected ? 'bg-white' : 'bg-slate-50/40 opacity-70'}">
            <td class="px-3 py-3 text-center">
                <input type="checkbox" class="lead-select-cb w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500/20 accent-blue-600 cursor-pointer"
                    data-id="${esc(l.id)}"
                    ${isSelected ? 'checked' : ''}
                    onchange="toggleLeadSelection('${esc(l.id)}', this.checked)">
            </td>
            <td class="px-3 py-3 text-xs font-mono font-bold text-slate-400 text-center">
                ${seqNumber}
            </td>
            <td class="px-5 py-3 text-xs">
                <div class="font-semibold text-slate-900">${esc(l.job_title)}</div>
                ${l.role ? `<div class="text-[10px] text-slate-500 font-medium mt-0.5">${esc(l.role)}</div>` : ''}
            </td>
            <td class="px-5 py-3 text-xs font-medium text-slate-700 col-company ${currentAppMode === 'manual' ? 'hidden' : ''}">
                ${esc(l.company)}
            </td>
            <td class="px-5 py-3 text-xs font-bold text-blue-600 text-center">
                ${esc(l.country || 'US')}
            </td>
            <td class="px-5 py-3 text-xs text-slate-600">
                ${esc(l.location_remote_type || l.location || l.remote_type || 'Not listed')}
            </td>
            <td class="px-5 py-3 text-xs text-center">
                ${matchScoreBadge}
            </td>
            <td class="px-5 py-3 text-xs max-w-[180px]">
                <div class="flex flex-wrap gap-1 items-center">
                    ${matchedSkillsHtml}
                </div>
            </td>
            <td class="px-5 py-3 text-xs max-w-[180px]">
                <div class="flex flex-wrap gap-1 items-center">
                    ${missingSkillsHtml}
                </div>
            </td>
            <td class="px-5 py-3 text-xs text-slate-700 max-w-[240px]">
                <div class="text-[11px] leading-relaxed line-clamp-2 font-normal" title="${esc(summaryText)}">${esc(summarySnippet)}</div>
            </td>
            <td class="px-5 py-3 text-xs">
                <span class="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold border ${expBadgeClass}">
                    ${esc(expText)}
                </span>
            </td>
            <td class="px-5 py-3 text-xs font-semibold text-emerald-700">
                ${esc(l.salary)}
            </td>
            <td class="px-5 py-3 text-xs text-slate-500 max-w-[220px]">
                <div class="truncate text-[11px] text-slate-600 mb-1" title="${esc(l.job_description)}">${esc(descSnippet)}</div>
                <button type="button" onclick="openDescriptionModal('${esc(l.id)}')" class="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-800 hover:underline font-semibold">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    Full Description
                </button>
            </td>
            <td class="px-5 py-3 text-xs text-center">
                <div class="flex items-center justify-center gap-2">
                    ${l.job_url ? `<a href="${esc(l.job_url)}" target="_blank" class="px-3 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 font-medium rounded-lg text-xs transition-colors flex items-center gap-1 shadow-2xs">Apply ↗</a>` : '—'}
                </div>
            </td>
        </tr>`;
    }).join('');

    updateSelectedLeadsUI();
}

let currentModalLeadId = null;
let currentModalLinkedinVariants = [];

function openDescriptionModal(jobId) {
    const job = allLeads.find(l => String(l.id) === String(jobId));
    if (!job) return;

    currentModalLeadId = jobId;

    document.getElementById('modal-job-title').textContent = job.job_title || 'Job Description';
    document.getElementById('modal-company-info').textContent = `${job.company || 'Company'} • ${job.location_remote_type || job.location || 'Location'} (${job.country || 'US'})`;
    document.getElementById('modal-experience').textContent = job.experience || 'Not specified';
    document.getElementById('modal-salary').textContent = job.salary || 'Not listed';
    document.getElementById('modal-location').textContent = job.location_remote_type || job.location || 'Not listed';
    
    // Summary population
    const summaryEl = document.getElementById('modal-job-summary');
    if (summaryEl) {
        summaryEl.textContent = job.job_summary || job.summary || job.match_reason || 'No description summary available.';
    }
    
    // AI Match Card population
    const matchScoreEl = document.getElementById('modal-match-score');
    const matchedSkillsEl = document.getElementById('modal-matched-skills');
    const missingSkillsEl = document.getElementById('modal-missing-skills');
    const matchReasonEl = document.getElementById('modal-match-reason');

    if (job.match_score !== null && job.match_score !== undefined) {
        const score = Number(job.match_score);
        matchScoreEl.textContent = `${score}% Match`;
        matchScoreEl.className = 'px-2.5 py-0.5 rounded-full text-xs font-bold border shadow-2xs ' + scoreBadgeClasses(score);
    } else {
        matchScoreEl.textContent = 'Not Evaluated';
        matchScoreEl.className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200';
    }

    if (job.matched_skills && job.matched_skills.length) {
        matchedSkillsEl.innerHTML = job.matched_skills.map(s => `<span class="inline-block bg-emerald-50 text-emerald-800 border border-emerald-200 text-[11px] font-medium px-2 py-0.5 rounded-md">${esc(s)}</span>`).join('');
    } else {
        matchedSkillsEl.innerHTML = '<span class="text-slate-400 italic text-[11px]">No specific skills matched</span>';
    }

    if (job.missing_skills && job.missing_skills.length) {
        missingSkillsEl.innerHTML = job.missing_skills.map(s => `<span class="inline-block bg-rose-50 text-rose-700 border border-rose-200 text-[11px] font-medium px-2 py-0.5 rounded-md">${esc(s)}</span>`).join('');
    } else {
        missingSkillsEl.innerHTML = '<span class="text-slate-400 italic text-[11px]">No missing skills detected</span>';
    }

    matchReasonEl.textContent = job.match_reason || 'No evaluation rationale available.';

    const descEl = document.getElementById('modal-description-content');
    if (job.job_description && job.job_description.trim()) {
        descEl.textContent = job.job_description;
    } else {
        descEl.innerHTML = '<span class="text-gray-500 italic">No full description snippet available for this job card.</span>';
    }

    const linkEl = document.getElementById('modal-indeed-link');
    if (job.job_url) {
        linkEl.href = job.job_url;
        linkEl.classList.remove('hidden');
    } else {
        linkEl.classList.add('hidden');
    }

    renderModalOutreach(job);

    // Outreach generation only looks up leads in the Indeed/manual store server-side,
    // so hide the modal's Generate Outreach action for Dice leads (mirrors the batch
    // outreach button, which switchMode() already hides in dice mode).
    const genOutreachBtn = document.getElementById('btn-generate-outreach');
    if (genOutreachBtn) genOutreachBtn.classList.toggle('hidden', currentAppMode === 'dice');

    const modal = document.getElementById('job-modal');
    if (modal) modal.classList.remove('hidden');
}

function renderManualOutreach(lead) {
    const section = document.getElementById('manual-outreach-section');
    const hasOutreach = !!(lead.outreach_email_subject || lead.outreach_email_body || (lead.outreach_linkedin_variants && lead.outreach_linkedin_variants.length));
    if (!section) return;

    if (!hasOutreach) {
        section.classList.add('hidden');
        manualLinkedinVariants = [];
        return;
    }

    section.classList.remove('hidden');
    document.getElementById('manual-outreach-email-subject').value = lead.outreach_email_subject || '';
    document.getElementById('manual-outreach-email-body').value = lead.outreach_email_body || '';

    manualLinkedinVariants = lead.outreach_linkedin_variants || [];
    const selected = lead.outreach_linkedin_message || manualLinkedinVariants[0] || '';
    document.getElementById('manual-outreach-linkedin').value = selected;
    renderLinkedinVariantTabs('manual', manualLinkedinVariants, selected);
}

function renderModalOutreach(job) {
    const emptyEl = document.getElementById('modal-outreach-empty');
    const contentEl = document.getElementById('modal-outreach-content');
    const statusEl = document.getElementById('modal-outreach-save-status');
    if (statusEl) statusEl.textContent = '';

    const hasOutreach = !!(job.outreach_email_subject || job.outreach_email_body || (job.outreach_linkedin_variants && job.outreach_linkedin_variants.length));
    if (!hasOutreach) {
        if (emptyEl) emptyEl.classList.remove('hidden');
        if (contentEl) contentEl.classList.add('hidden');
        currentModalLinkedinVariants = [];
        return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');
    if (contentEl) contentEl.classList.remove('hidden');

    document.getElementById('modal-outreach-email-subject').value = job.outreach_email_subject || '';
    document.getElementById('modal-outreach-email-body').value = job.outreach_email_body || '';

    currentModalLinkedinVariants = job.outreach_linkedin_variants || [];
    const selected = job.outreach_linkedin_message || currentModalLinkedinVariants[0] || '';
    document.getElementById('modal-outreach-linkedin').value = selected;
    renderLinkedinVariantTabs('modal', currentModalLinkedinVariants, selected);
}

function renderLinkedinVariantTabs(context, variants, selectedText) {
    const container = document.getElementById(context === 'modal' ? 'modal-linkedin-variant-tabs' : 'manual-linkedin-variant-tabs');
    if (!container) return;
    if (!variants || variants.length <= 1) {
        container.innerHTML = '';
        return;
    }
    container.innerHTML = variants.map((v, idx) => {
        const isActive = v === selectedText;
        const cls = isActive
            ? 'px-2 py-0.5 rounded-md text-[10px] font-bold bg-indigo-600 text-white cursor-pointer'
            : 'px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 text-slate-600 hover:bg-slate-200 cursor-pointer';
        return `<span class="${cls}" onclick="selectLinkedinVariant('${context}', ${idx})">V${idx + 1}</span>`;
    }).join('');
}

function selectLinkedinVariant(context, index) {
    const variants = context === 'modal' ? currentModalLinkedinVariants : manualLinkedinVariants;
    const text = variants[index];
    if (text === undefined) return;
    const textareaId = context === 'modal' ? 'modal-outreach-linkedin' : 'manual-outreach-linkedin';
    const textarea = document.getElementById(textareaId);
    if (textarea) textarea.value = text;
    renderLinkedinVariantTabs(context, variants, text);
}

async function generateModalOutreach() {
    if (!currentModalLeadId) return;
    const btn = document.getElementById('btn-generate-outreach');
    const label = document.getElementById('btn-generate-outreach-label');
    if (btn) btn.disabled = true;
    if (label) label.textContent = 'Generating...';

    try {
        const res = await fetch(`/api/jobs/${currentModalLeadId}/generate-outreach`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Outreach generation failed');
        }
        const idx = allLeads.findIndex(l => String(l.id) === String(currentModalLeadId));
        if (idx !== -1) allLeads[idx] = { ...allLeads[idx], ...data.lead };
        renderModalOutreach(data.lead);
    } catch (e) {
        showAlertModal('Outreach Generation Failed', e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (label) label.textContent = 'Generate Outreach';
    }
}

async function saveModalOutreach() {
    if (!currentModalLeadId) return;
    const statusEl = document.getElementById('modal-outreach-save-status');
    const payload = {
        email_subject: document.getElementById('modal-outreach-email-subject').value,
        email_body: document.getElementById('modal-outreach-email-body').value,
        linkedin_message: document.getElementById('modal-outreach-linkedin').value,
    };

    try {
        const res = await fetch(`/api/jobs/${currentModalLeadId}/update-outreach`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to save outreach');

        const idx = allLeads.findIndex(l => String(l.id) === String(currentModalLeadId));
        if (idx !== -1) allLeads[idx] = { ...allLeads[idx], ...data.lead };

        if (statusEl) {
            statusEl.textContent = 'Saved ✓';
            statusEl.className = 'text-xs text-emerald-600 font-semibold';
        }
    } catch (e) {
        if (statusEl) {
            statusEl.textContent = 'Failed to save';
            statusEl.className = 'text-xs text-rose-600 font-semibold';
        }
    }
}

function copyOutreachField(elementId) {
    const el = document.getElementById(elementId);
    if (!el || !el.value) return;
    navigator.clipboard.writeText(el.value).then(() => {
        const original = el.style.borderColor;
        el.style.borderColor = '#10b981';
        setTimeout(() => { el.style.borderColor = original; }, 600);
    }).catch(() => {
        showAlertModal('Copy Failed', 'Could not copy to clipboard. Please select and copy the text manually.', 'warning');
    });
}

function closeDescriptionModal() {
    const modal = document.getElementById('job-modal');
    if (modal) modal.classList.add('hidden');
}

// Close modal on Escape key press or clicking outside modal box
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDescriptionModal();
});
document.addEventListener('click', (e) => {
    const modal = document.getElementById('job-modal');
    if (modal && !modal.classList.contains('hidden') && e.target === modal) {
        closeDescriptionModal();
    }
});

function filterTable() {
    const q = (document.getElementById('filter-search')?.value || '').toLowerCase();
    if (!q) {
        renderTable(allLeads);
        return;
    }
    const filtered = allLeads.filter(l =>
        (l.job_title || '').toLowerCase().includes(q) ||
        (l.company || '').toLowerCase().includes(q) ||
        (l.country || '').toLowerCase().includes(q) ||
        (l.experience || '').toLowerCase().includes(q) ||
        (l.job_summary || '').toLowerCase().includes(q) ||
        (l.job_description || '').toLowerCase().includes(q)
    );
    renderTable(filtered);
}

function updateProgressUI(p) {
    if (!p) return;

    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const bar = document.getElementById('progress-bar');
    const pctEl = document.getElementById('progress-pct');
    const jobsFoundEl = document.getElementById('jobs-found');
    const logText = document.getElementById('log-text');

    let latestLog = '';
    if (p.log_messages && p.log_messages.length > 0) {
        latestLog = p.log_messages[p.log_messages.length - 1];
        if (logText) logText.textContent = latestLog;
    }

    const isCooldown = p.status === 'running' && (
        latestLog.includes('Cooldown') ||
        latestLog.includes('cooldown') ||
        latestLog.includes('Pausing') ||
        latestLog.includes('retrying in')
    );

    if (statusDot) {
        const colors = { running: 'bg-emerald-500 animate-pulse', idle: 'bg-slate-400', completed: 'bg-blue-600', error: 'bg-red-500' };
        if (isCooldown) {
            statusDot.className = 'w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse';
        } else {
            statusDot.className = `w-2.5 h-2.5 rounded-full ${colors[p.status] || 'bg-slate-400'}`;
        }
    }

    if (statusText) {
        if (isCooldown) {
            statusText.textContent = 'Anti-Bot Cooldown (60s)';
        } else if (p.status === 'running') {
            const kwStr = p.current_keyword ? ` • "${p.current_keyword}"` : '';
            statusText.textContent = `Running (${p.current_country || 'US'}${kwStr})`;
        } else {
            statusText.textContent = p.status ? p.status.charAt(0).toUpperCase() + p.status.slice(1) : 'Idle';
        }
    }

    // Calculate progress percentage with fallbacks
    let pct = 0;
    if (p.status === 'completed') {
        pct = 100;
    } else if (p.progress_percent !== undefined && p.progress_percent !== null) {
        pct = p.progress_percent;
    } else if (p.max_pages > 0 && p.current_page > 0) {
        pct = Math.min(99, Math.round(((p.current_page - 0.5) / p.max_pages) * 100));
    }

    if (bar) {
        bar.style.width = `${pct}%`;
        if (p.status === 'running') {
            bar.classList.add('animate-pulse');
        } else {
            bar.classList.remove('animate-pulse');
        }
    }
    if (pctEl) pctEl.textContent = `${pct.toFixed(0)}%`;
    if (jobsFoundEl) jobsFoundEl.textContent = p.jobs_found || 0;

    if (p.status === 'running') {
        isSearchRunning = true;
        setSearchButtonState(true, 'Scraping Running...');
        setStopButtonState(false);
        const searchStatusEl = document.getElementById('search-status');
        if (searchStatusEl) {
            if (isCooldown) {
                searchStatusEl.textContent = `Status: ${latestLog}`;
            } else if (latestLog.includes('Starting Country')) {
                searchStatusEl.textContent = `Status: ${latestLog.replace(/---/g, '').trim()}`;
            }
        }
    }

    if (p.status === 'completed' || p.status === 'idle' || p.status === 'stopped' || p.status === 'error') {
        isSearchRunning = false;
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        fetchLeads(); // Final update
        setSearchButtonState(false);
        setStopButtonState(true);
        if (p.status === 'completed') {
            document.getElementById('search-status').textContent = 'Status: Search Completed';
        } else if (p.status === 'stopped') {
            document.getElementById('search-status').textContent = 'Status: Search Stopped';
        } else if (p.status === 'error') {
            const count = p.jobs_found || 0;
            document.getElementById('search-status').textContent = count > 0
                ? `Status: Run Halted (${count} leads secured & exported)`
                : (p.last_error ? `Status: Halted (${p.last_error})` : 'Status: Search Halted');
        }
    }
}

async function fetchScraperProgress() {
    try {
        const res = await fetch('/api/scraper/progress');
        if (res.ok) {
            const p = await res.json();
            updateProgressUI(p);
        }
    } catch (e) {
        console.warn('Fallback progress fetch error:', e);
    }
}

function connectWebSocket() {
    const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
        ws = new WebSocket(`${wsProto}//${location.host}/ws/progress`);
        ws.onopen = () => console.log('WebSocket connected');
        ws.onclose = () => setTimeout(connectWebSocket, 3000);
        ws.onerror = () => console.warn('WebSocket error, falling back to REST progress');
        ws.onmessage = (e) => {
            try {
                const p = JSON.parse(e.data);
                updateProgressUI(p);
            } catch (err) {
                console.error('Failed to parse WebSocket progress payload:', err);
            }
        };
    } catch (err) {
        console.warn('WebSocket connection init failed:', err);
        setTimeout(connectWebSocket, 3000);
    }
}


async function exportExcel(event) {
    if (event) event.preventDefault();

    const selectedIdsArray = Array.from(selectedLeadIds);
    if (allLeads.length > 0 && selectedIdsArray.length === 0) {
        showAlertModal('No Leads Selected', 'Please select at least one lead from the table to export.', 'warning');
        return;
    }

    const btns = [
        document.getElementById('nav-download-btn'),
        document.getElementById('table-download-btn')
    ].filter(Boolean);

    btns.forEach(b => {
        b.classList.add('pointer-events-none', 'opacity-75');
    });

    try {
        const payload = selectedIdsArray.length < allLeads.length
            ? { selected_ids: selectedIdsArray }
            : {};

        const res = await fetch('/api/export/excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            showAlertModal('Export Error', errData.detail || 'Failed to generate Excel file.', 'error');
            return;
        }

        const blob = await res.blob();
        const disposition = res.headers.get('Content-Disposition') || '';
        let filename = 'indeed_leads.xlsx';
        const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (match && match[1]) {
            filename = match[1].replace(/['"]/g, '');
        }

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch (e) {
        showAlertModal('Network Error', e.message, 'error');
    } finally {
        btns.forEach(b => {
            b.classList.remove('pointer-events-none', 'opacity-75');
        });
    }
}

async function exportSharePoint() {
    // If currently in Manual Evaluator mode, route directly to the unified queue sync
    if (currentAppMode === 'manual') {
        return await syncAllStagedToSharePoint();
    }
    // If currently in Dice Search mode, route to the Dice-specific export endpoint
    if (currentAppMode === 'dice') {
        return await exportDiceSharePoint();
    }

    const selectedIdsArray = Array.from(selectedLeadIds);
    if (allLeads.length > 0 && selectedIdsArray.length === 0) {
        showAlertModal('No Leads Selected', 'Please select at least one lead from the table to sync to SharePoint.', 'warning');
        return;
    }

    const btns = [
        document.getElementById('nav-sharepoint-btn'),
        document.getElementById('table-sharepoint-btn')
    ].filter(Boolean);

    btns.forEach(b => {
        b.disabled = true;
        b.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg> Syncing...`;
    });

    try {
        const payload = selectedIdsArray.length < allLeads.length
            ? { selected_ids: selectedIdsArray }
            : {};

        const ownerEl = document.getElementById('leads-owner');
        if (ownerEl && ownerEl.value) {
            payload.owner = ownerEl.value;
        }

        const res = await fetch('/api/export/sharepoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            showAlertModal('SharePoint Sync Complete', data.message || 'Successfully synced leads to SharePoint!', 'success');
        } else {
            showAlertModal('SharePoint Sync Error', data.detail || data.message || 'Failed to sync', 'error');
        }
    } catch (e) {
        showAlertModal('Network Error', e.message, 'error');
    } finally {
        btns.forEach(b => {
            b.disabled = false;
        });
        updateSelectedLeadsUI();
    }
}

async function generateOutreachForSelectedLeads() {
    const selectedIdsArray = Array.from(selectedLeadIds);
    if (allLeads.length > 0 && selectedIdsArray.length === 0) {
        showAlertModal('No Leads Selected', 'Please select at least one lead from the table to generate outreach for.', 'warning');
        return;
    }

    const leadIds = selectedIdsArray.length < allLeads.length
        ? selectedIdsArray
        : allLeads.map(l => String(l.id));

    const btn = document.getElementById('table-generate-outreach-btn');
    const label = document.getElementById('table-generate-outreach-label');
    const originalLabel = label ? label.textContent : 'Generate Outreach';
    if (btn) btn.disabled = true;
    if (label) label.textContent = `Generating (0/${leadIds.length})...`;

    try {
        const res = await fetch('/api/jobs/generate-outreach-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lead_ids: leadIds })
        });
        const data = await res.json();
        if (!res.ok) {
            showAlertModal('Outreach Generation Error', data.detail || data.message || 'Failed to generate outreach drafts.', 'error');
            return;
        }

        // Merge the freshly generated outreach fields back into allLeads without a full re-fetch.
        const byId = new Map((data.leads || []).map(l => [String(l.id), l]));
        allLeads = allLeads.map(l => {
            const updated = byId.get(String(l.id));
            if (!updated) return l;
            return {
                ...l,
                outreach_email_subject: updated.outreach_email_subject,
                outreach_email_body: updated.outreach_email_body,
                outreach_linkedin_message: updated.outreach_linkedin_message,
                outreach_linkedin_variants: updated.outreach_linkedin_variants,
            };
        });
        lastLeadsHash = '';
        renderTable(allLeads);
        updateSelectedLeadsUI();

        const failedCount = (data.failed || []).length;
        const msg = failedCount > 0
            ? `Generated outreach for ${data.generated} lead(s); ${failedCount} failed and can be retried individually from the lead's detail view.`
            : `Generated outreach for ${data.generated} lead(s). It's saved automatically and will be included the next time you Sync to SharePoint.`;
        showAlertModal('Outreach Generated', msg, failedCount > 0 ? 'warning' : 'success');
    } catch (e) {
        showAlertModal('Network Error', e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (label) label.textContent = originalLabel;
    }
}

function esc(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function updateIstClock() {
    const el = document.getElementById('ist-live-clock');
    if (!el) return;
    try {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', {
            timeZone: 'Asia/Kolkata',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
        el.textContent = `${timeStr} IST`;
    } catch (e) {
        el.textContent = 'IST (GMT+5:30)';
    }
}

// ==========================================
// Mode Switcher (Scraper vs Manual Evaluator vs Dice Search)
// ==========================================
let currentAppMode = 'scraper';

function switchMode(mode) {
    currentAppMode = mode;
    const btnScraper = document.getElementById('tab-btn-scraper');
    const btnManual = document.getElementById('tab-btn-manual');
    const btnDice = document.getElementById('tab-btn-dice');
    const panelScraper = document.getElementById('panel-scraper');
    const panelManual = document.getElementById('panel-manual');
    const panelDice = document.getElementById('panel-dice');
    const thCompany = document.getElementById('th-company');
    const navSp = document.getElementById('nav-sharepoint-btn');
    const tblSp = document.getElementById('table-sharepoint-btn');
    const tblOutreach = document.getElementById('table-generate-outreach-btn');
    const progressCard = document.getElementById('progress-card');
    const stagedCard = document.getElementById('staged-queue-card');

    if (!btnScraper || !btnManual || !btnDice || !panelScraper || !panelManual || !panelDice) return;

    const activeClass = 'px-4 py-2 text-xs font-bold rounded-xl transition-all flex items-center gap-2 bg-blue-600 text-white shadow-xs cursor-pointer';
    const inactiveClass = 'px-4 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 cursor-pointer';

    btnScraper.className = mode === 'scraper' ? activeClass : inactiveClass;
    btnManual.className = mode === 'manual' ? activeClass : inactiveClass;
    btnDice.className = mode === 'dice' ? activeClass : inactiveClass;

    panelScraper.classList.toggle('hidden', mode !== 'scraper');
    panelManual.classList.toggle('hidden', mode !== 'manual');
    panelDice.classList.toggle('hidden', mode !== 'dice');

    if (mode === 'scraper') {
        if (progressCard) progressCard.classList.remove('hidden');
        if (stagedCard) stagedCard.classList.add('hidden');
        if (thCompany) thCompany.classList.remove('hidden');
        document.querySelectorAll('.col-company').forEach(el => el.classList.remove('hidden'));
        // Re-hydrate the shared table/allLeads from the Indeed/manual store so a background
        // scraper poll (mode-gated in fetchLeads()) or a prior Dice search doesn't leave
        // stale/foreign rows visible, which could otherwise export the wrong store.
        lastLeadsHash = '';
        fetchLeads();
    } else if (mode === 'manual') {
        if (progressCard) progressCard.classList.add('hidden');
        if (stagedCard) stagedCard.classList.remove('hidden');
        if (thCompany) thCompany.classList.add('hidden');
        document.querySelectorAll('.col-company').forEach(el => el.classList.add('hidden'));
        // In manual mode, hide redundant navbar and table header sync buttons to avoid conflict
        if (navSp) navSp.classList.add('hidden');
        if (tblSp) tblSp.classList.add('hidden');
        if (tblOutreach) tblOutreach.classList.add('hidden');
    } else if (mode === 'dice') {
        if (progressCard) progressCard.classList.add('hidden');
        if (stagedCard) stagedCard.classList.add('hidden');
        if (thCompany) thCompany.classList.remove('hidden');
        document.querySelectorAll('.col-company').forEach(el => el.classList.remove('hidden'));
        // Dice results sync to a dedicated SharePoint endpoint; outreach batch generation
        // targets the Indeed lead store, so it stays hidden here.
        if (navSp) navSp.classList.add('hidden');
        if (tblOutreach) tblOutreach.classList.add('hidden');
        // Re-hydrate the shared table/allLeads from the Dice store so leftover Indeed rows
        // (and their scraper-mode Sync button) aren't shown while the user is on this tab.
        hydrateDiceTable();
    }
}

async function hydrateDiceTable() {
    const tblSp = document.getElementById('table-sharepoint-btn');
    const tblDl = document.getElementById('table-download-btn');
    const tblClr = document.getElementById('table-clear-btn');
    try {
        const res = await fetch('/api/dice/results');
        const data = await res.json();

        // allLeads/selectedLeadIds/the table and its buttons are shared, mode-owned state.
        // If the user switched away from the Dice tab while this fetch was in flight, don't
        // clobber whatever mode is now active (mirrors the guard in fetchLeads()).
        if (currentAppMode !== 'dice') {
            return;
        }

        allLeads = data.leads || [];
        selectedLeadIds = new Set(allLeads.map(l => String(l.id)));
        lastLeadsHash = '';
        renderTable(allLeads);
    } catch (e) {
        console.error('Error fetching Dice results:', e);
    } finally {
        // Only touch button visibility if Dice is still the active mode; otherwise the
        // now-current mode already owns these buttons and we'd stomp on its state.
        if (currentAppMode === 'dice') {
            if (tblSp) tblSp.classList.toggle('hidden', allLeads.length === 0);
            // Excel export & the generic clear action operate on the Indeed lead store, not Dice's.
            if (tblDl) tblDl.classList.add('hidden');
            if (tblClr) tblClr.classList.add('hidden');
        }
    }
}

// ==========================================
// Dice Search (search_jobs via Dice MCP, reuses the shared leads table)
// ==========================================

async function searchDice(event) {
    if (event) event.preventDefault();

    const keywords = getDiceSelectedKeywords();
    if (keywords.length === 0) {
        showAlertModal('Input Required', 'Please select or add at least one keyword to search Dice.', 'warning');
        return;
    }

    const countries = getDiceSelectedCountries();
    const combos = keywords.length * Math.max(countries.length, 1);
    if (combos > DICE_MAX_SEARCH_COMBINATIONS) {
        showAlertModal(
            'Too Many Combinations',
            `${keywords.length} keyword(s) × ${countries.length || 1} location(s) = ${combos} searches, which exceeds the limit of ${DICE_MAX_SEARCH_COMBINATIONS}. Narrow your keyword or country selection.`,
            'warning'
        );
        return;
    }

    const postedDateEl = document.getElementById('dice-posted-date');
    const easyApplyEl = document.getElementById('dice-easy-apply');
    const sponsorEl = document.getElementById('dice-willing-to-sponsor');
    const statusNote = document.getElementById('dice-status-note');
    const btn = document.getElementById('btn-dice-search');
    const btnIcon = document.getElementById('btn-dice-search-icon');
    const btnLabel = document.getElementById('btn-dice-search-label');

    const payload = {
        keywords,
        countries: countries.length > 0 ? countries : null,
        // Workplace type is always Remote - not user-configurable. Employment type is
        // intentionally left unfiltered (search all job types).
        workplace_types: ['Remote'],
        posted_date: postedDateEl && postedDateEl.value ? postedDateEl.value : null,
        easy_apply: easyApplyEl && easyApplyEl.checked ? true : null,
        willing_to_sponsor: sponsorEl && sponsorEl.checked ? true : null,
    };

    if (btn) btn.disabled = true;
    if (btnIcon) btnIcon.classList.add('animate-spin');
    if (btnLabel) btnLabel.textContent = 'Searching...';
    if (statusNote) statusNote.textContent = '';

    try {
        const resp = await fetch('/api/dice/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showAlertModal('Dice Search Error', err.detail || 'Dice search failed.', 'error');
            return;
        }

        const data = await resp.json();
        allLeads = data.leads || [];
        selectedLeadIds = new Set(allLeads.map(l => String(l.id)));
        lastLeadsHash = '';
        renderTable(allLeads);

        const tblSp = document.getElementById('table-sharepoint-btn');
        const tblDl = document.getElementById('table-download-btn');
        const tblClr = document.getElementById('table-clear-btn');
        if (tblSp) tblSp.classList.toggle('hidden', allLeads.length === 0);
        // Excel export & the generic clear action operate on the Indeed lead store, not Dice's.
        if (tblDl) tblDl.classList.add('hidden');
        if (tblClr) tblClr.classList.add('hidden');

        if (statusNote) {
            const newCount = typeof data.new_count === 'number' ? data.new_count : allLeads.length;
            const ranCombos = typeof data.combos === 'number' ? data.combos : combos;
            statusNote.className = 'text-xs text-slate-500 font-medium';
            statusNote.textContent = `Found ${newCount} new Dice job${newCount === 1 ? '' : 's'} across ${ranCombos} search${ranCombos === 1 ? '' : 'es'}.`;
        }
    } catch (e) {
        showAlertModal('Network Error', e.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (btnIcon) btnIcon.classList.remove('animate-spin');
        if (btnLabel) btnLabel.textContent = 'Search Dice';
    }
}

async function exportDiceSharePoint() {
    const selectedIdsArray = Array.from(selectedLeadIds);
    if (allLeads.length > 0 && selectedIdsArray.length === 0) {
        showAlertModal('No Leads Selected', 'Please select at least one lead from the table to sync to SharePoint.', 'warning');
        return;
    }

    const btns = [document.getElementById('table-sharepoint-btn')].filter(Boolean);
    btns.forEach(b => {
        b.disabled = true;
        b.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg> Syncing...`;
    });

    try {
        const payload = selectedIdsArray.length < allLeads.length
            ? { selected_ids: selectedIdsArray }
            : {};

        const ownerEl = document.getElementById('leads-owner');
        if (ownerEl && ownerEl.value) {
            payload.owner = ownerEl.value;
        }

        const res = await fetch('/api/dice/export/sharepoint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            showAlertModal('SharePoint Sync Complete', data.message || 'Successfully synced Dice leads to SharePoint!', 'success');
        } else {
            showAlertModal('SharePoint Sync Error', data.detail || data.message || 'Failed to sync', 'error');
        }
    } catch (e) {
        showAlertModal('Network Error', e.message, 'error');
    } finally {
        btns.forEach(b => {
            b.disabled = false;
            b.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg> Sync to SharePoint`;
        });
        updateSelectedLeadsUI();
    }
}

// ==========================================
// Manual Job Description Evaluation & SharePoint Sync
// ==========================================

async function evaluateManualJob() {
    const titleEl = document.getElementById('manual-job-title');
    const companyEl = document.getElementById('manual-company');
    const countryEl = document.getElementById('manual-country');
    const urlEl = document.getElementById('manual-job-url');
    const salaryEl = document.getElementById('manual-salary');
    const expEl = document.getElementById('manual-experience');
    const descEl = document.getElementById('manual-description');
    const noteEl = document.getElementById('manual-status-note');
    const btn = document.getElementById('btn-manual-eval');
    const btnLabel = document.getElementById('btn-manual-eval-label');
    const btnIcon = document.getElementById('btn-manual-eval-icon');

    const jobDescription = (descEl ? descEl.value : '').trim();
    if (!jobDescription) {
        showAlertModal('Input Required', 'Please paste a job description or technical requirements first.', 'warning');
        if (descEl) descEl.focus();
        return;
    }

    const payload = {
        job_title: (titleEl ? titleEl.value : '').trim() || 'Untitled Opportunity',
        company: (companyEl ? companyEl.value : '').trim(),
        remote_type: 'Fully Remote',
        country: countryEl ? countryEl.value : 'US',
        job_url: (urlEl ? urlEl.value : '').trim(),
        salary_range: (salaryEl ? salaryEl.value : '').trim() || 'Not listed',
        experience: (expEl ? expEl.value : '').trim() || 'Not specified',
        job_description: jobDescription,
    };

    if (btn) btn.disabled = true;
    if (btnLabel) btnLabel.textContent = 'Evaluating with AI...';
    if (btnIcon) {
        btnIcon.innerHTML = `<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>`;
        btnIcon.classList.add('animate-spin');
    }
    if (noteEl) {
        noteEl.className = 'text-xs text-blue-600 font-semibold animate-pulse';
        noteEl.textContent = 'Analyzing job description against company knowledge base...';
    }

    try {
        const res = await fetch('/api/jobs/manual-evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Evaluation failed on server');
        }

        const lead = data.lead;
        currentEvaluatingLeadId = lead.id;
        const parsed = data.parsed_fields || {};
        lastEvaluatedManualLead = {
            ...lead,
            extra_notes: parsed.notes || '',
        };

        renderManualOutreach(lead);

        // Reset previous extracted fields first before populating new values
        if (titleEl) titleEl.value = '';
        if (companyEl) companyEl.value = '';
        if (urlEl) urlEl.value = '';
        if (salaryEl) salaryEl.value = '';
        if (expEl) expEl.value = '';
        const emailEl = document.getElementById('manual-contact-email');
        if (emailEl) emailEl.value = '';
        const phoneEl = document.getElementById('manual-contact-phone');
        if (phoneEl) phoneEl.value = '';
        const contactNameEl = document.getElementById('manual-contact-name');
        if (contactNameEl) contactNameEl.value = '';
        const notesEl = document.getElementById('manual-notes');
        if (notesEl) notesEl.value = '';
        const estValEl = document.getElementById('manual-estimated-value');
        if (estValEl) estValEl.value = '';
        const followupEl = document.getElementById('manual-followup-date');
        if (followupEl) followupEl.value = '';
        const dueEl = document.getElementById('manual-due-date');
        if (dueEl) dueEl.value = '';
        document.querySelectorAll('.manual-tech-checkbox').forEach(cb => cb.checked = false);

        // Auto-populate extracted form fields
        let autoFilledCount = 0;
        if (titleEl && parsed.job_title) {
            titleEl.value = parsed.job_title;
            autoFilledCount++;
        }
        if (companyEl && parsed.company) {
            companyEl.value = parsed.company;
            autoFilledCount++;
        }
        if (countryEl && parsed.country) {
            const rawCountry = (parsed.country || '').trim().toLowerCase();
            if (rawCountry === 'south africa' || rawCountry === 'za' || rawCountry === 'rsa') {
                countryEl.value = 'South Africa';
            } else if (rawCountry === 'uk' || rawCountry === 'gb' || rawCountry === 'united kingdom' || rawCountry === 'england') {
                countryEl.value = 'UK';
            } else {
                countryEl.value = 'US';
            }
        }
        if (urlEl && parsed.job_url) {
            urlEl.value = parsed.job_url;
            autoFilledCount++;
        }
        if (salaryEl) {
            salaryEl.value = parsed.salary_range || '';
            if (parsed.salary_range) autoFilledCount++;
        }
        if (expEl) {
            expEl.value = parsed.experience || '';
            if (parsed.experience) autoFilledCount++;
        }
        if (emailEl && parsed.email) {
            emailEl.value = parsed.email;
            autoFilledCount++;
        }
        if (phoneEl && parsed.phone) {
            phoneEl.value = parsed.phone;
            autoFilledCount++;
        }
        if (contactNameEl && parsed.contact_name) {
            contactNameEl.value = parsed.contact_name;
            autoFilledCount++;
        }
        if (notesEl && parsed.notes) {
            notesEl.value = parsed.notes;
        }

        const industryEl = document.getElementById('manual-industry');
        if (industryEl && parsed.industry) {
            industryEl.value = parsed.industry;
        }

        if (parsed.owner) {
            setSelectedOwner(parsed.owner);
            autoFilledCount++;
        }

        const leadSourceEl = document.getElementById('manual-lead-source');
        if (leadSourceEl && parsed.lead_source) {
            leadSourceEl.value = parsed.lead_source;
        }

        const statusEl = document.getElementById('manual-status');
        if (statusEl && parsed.status) {
            statusEl.value = parsed.status;
        }

        const currencyEl = document.getElementById('manual-currency');
        if (currencyEl && parsed.currency_code) {
            currencyEl.value = parsed.currency_code;
        }

        if (estValEl) {
            if (parsed.estimated_value !== undefined && parsed.estimated_value !== null && parsed.estimated_value !== '') {
                estValEl.value = parsed.estimated_value;
                autoFilledCount++;
            } else {
                estValEl.value = '';
            }
        }

        // Auto-suggest Priority based on AI extraction or score
        const priorityEl = document.getElementById('manual-priority');
        if (priorityEl) {
            if (parsed.priority) {
                priorityEl.value = parsed.priority;
            } else if (lead.match_score !== null && lead.match_score !== undefined) {
                priorityEl.value = scoreToPriority(lead.match_score);
            }
        }

        // Auto-select Technology based on parsed tech & matched skills
        const parsedTechs = (parsed.technologies || []).map(t => t.toLowerCase());
        const combinedText = ((lead.job_title || '') + ' ' + (lead.matched_skills || []).join(' ') + ' ' + (lead.match_reason || '')).toLowerCase();
        
        document.querySelectorAll('.manual-tech-checkbox').forEach(cb => {
            const val = cb.value.toLowerCase();
            if (parsedTechs.includes(val)) {
                cb.checked = true;
            } else if (val === 'sharepoint' && (combinedText.includes('sharepoint') || combinedText.includes('spfx'))) {
                cb.checked = true;
            } else if (val === 'ai' && (combinedText.includes('ai') || combinedText.includes('openai') || combinedText.includes('llm') || combinedText.includes('machine learning'))) {
                cb.checked = true;
            } else if (val === 'power platform' && (combinedText.includes('power platform') || combinedText.includes('power apps') || combinedText.includes('power automate'))) {
                cb.checked = true;
            } else if (val === '.net' && (combinedText.includes('.net') || combinedText.includes('c#') || combinedText.includes('asp.net'))) {
                cb.checked = true;
            } else if (val === 'power bi' && combinedText.includes('power bi')) {
                cb.checked = true;
            } else if (val === 'dynamics' && combinedText.includes('dynamics')) {
                cb.checked = true;
            }
        });

        if (noteEl) {
            noteEl.className = 'text-xs text-emerald-600 font-bold';
            const extraCountMsg = parsed.extra_parameters && parsed.extra_parameters.length ? ` (+${parsed.extra_parameters.length} extra attributes in Notes)` : '';
            noteEl.textContent = `AI Evaluated & Auto-populated ${autoFilledCount} fields${extraCountMsg} | Match: ${lead.match_score !== null ? lead.match_score + '/100' : 'Evaluated'}. Review & click 'Sync to SharePoint'.`;
        }

        // Add lead to current list and refresh table
        if (parsed.matched_skills && parsed.matched_skills.length) lead.matched_skills = parsed.matched_skills;
        if (parsed.missing_skills && parsed.missing_skills.length) lead.missing_skills = parsed.missing_skills;
        if (parsed.match_score !== null && parsed.match_score !== undefined) lead.match_score = parsed.match_score;
        if (parsed.match_reason) lead.match_reason = parsed.match_reason;
        if (parsed.country) lead.country = parsed.country;
        if (parsed.salary_range) lead.salary = parsed.salary_range;
        if (parsed.experience) lead.experience = parsed.experience;

        allLeads.unshift(lead);
        renderTable(allLeads);

        // Show download and Clear buttons
        const navDl = document.getElementById('nav-download-btn');
        const tblDl = document.getElementById('table-download-btn');
        const navSp = document.getElementById('nav-sharepoint-btn');
        const tblSp = document.getElementById('table-sharepoint-btn');
        const tblOutreach = document.getElementById('table-generate-outreach-btn');
        const tblClr = document.getElementById('table-clear-btn');
        [navDl, tblDl, tblClr].forEach(b => b && b.classList.remove('hidden'));
        if (currentAppMode === 'scraper') {
            [navSp, tblSp, tblOutreach].forEach(b => b && b.classList.remove('hidden'));
        }

    } catch (err) {
        console.error('Manual evaluate error:', err);
        showAlertModal('Evaluation Error', err.message, 'error');
        if (noteEl) {
            noteEl.className = 'text-xs text-rose-600 font-semibold';
            noteEl.textContent = `Failed: ${err.message}`;
        }
    } finally {
        if (btn) btn.disabled = false;
        if (btnLabel) btnLabel.textContent = 'Evaluate & Auto-Fill with AI';
        if (btnIcon) {
            btnIcon.classList.remove('animate-spin');
            btnIcon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>`;
        }
    }
}

async function addManualToSharePoint() {
    const titleEl = document.getElementById('manual-job-title');
    const companyEl = document.getElementById('manual-company');
    const countryEl = document.getElementById('manual-country');
    const urlEl = document.getElementById('manual-job-url');
    const salaryEl = document.getElementById('manual-salary');
    const expEl = document.getElementById('manual-experience');
    const descEl = document.getElementById('manual-description');
    const noteEl = document.getElementById('manual-status-note');
    const bottomNoteEl = document.getElementById('manual-bottom-note');
    const btn = document.getElementById('btn-manual-sharepoint');
    const btnTop = document.getElementById('btn-manual-sharepoint-top');
    const btnLabel = document.getElementById('btn-manual-sp-label');
    const btnIcon = document.getElementById('btn-manual-sp-icon');
    const navSp = document.getElementById('nav-sharepoint-btn');
    const tblSp = document.getElementById('table-sharepoint-btn');

    const ownerEl = document.getElementById('manual-owner');
    const leadSourceEl = document.getElementById('manual-lead-source');
    const industryEl = document.getElementById('manual-industry');
    const priorityEl = document.getElementById('manual-priority');
    const statusEl = document.getElementById('manual-status');
    const currencyEl = document.getElementById('manual-currency');
    const estValEl = document.getElementById('manual-estimated-value');
    const followupEl = document.getElementById('manual-followup-date');
    const dueEl = document.getElementById('manual-due-date');
    const contactNameEl = document.getElementById('manual-contact-name');
    const contactEmailEl = document.getElementById('manual-contact-email');
    const contactPhoneEl = document.getElementById('manual-contact-phone');
    const notesEl = document.getElementById('manual-notes');
    const outreachSubjectEl = document.getElementById('manual-outreach-email-subject');
    const outreachBodyEl = document.getElementById('manual-outreach-email-body');
    const outreachLinkedinEl = document.getElementById('manual-outreach-linkedin');

    const jobDescription = (descEl ? descEl.value : '').trim();
    if (!jobDescription) {
        showAlertModal('Input Required', 'Please enter or paste a job description first.', 'warning');
        if (descEl) descEl.focus();
        return;
    }

    // Always read current checked technology checkboxes
    const selectedTech = [];
    document.querySelectorAll('.manual-tech-checkbox:checked').forEach(cb => selectedTech.push(cb.value));

    // Strictly read current edited values from DOM
    const title = (titleEl ? titleEl.value : '').trim() || (lastEvaluatedManualLead ? lastEvaluatedManualLead.job_title : 'Direct Opportunity');
    const company = (companyEl ? companyEl.value : '').trim() || (lastEvaluatedManualLead ? lastEvaluatedManualLead.company : '');
    const country = countryEl ? countryEl.value : 'US';
    const industry = industryEl ? industryEl.value : 'IT';
    const website = (urlEl ? urlEl.value : '').trim();
    const salary = (salaryEl ? salaryEl.value : '').trim();
    const experience = (expEl ? expEl.value : '').trim();
    const notesContent = (notesEl ? notesEl.value : '').trim() || (lastEvaluatedManualLead ? (lastEvaluatedManualLead.extra_notes || lastEvaluatedManualLead.job_summary || '') : '');

    const payload = {
        title: title,
        company: company,
        country: country,
        industry: industry,
        website: website,
        owner: getSelectedOwner(),
        lead_source: leadSourceEl ? leadSourceEl.value : 'Indeed',
        priority: priorityEl ? priorityEl.value : 'Medium',
        status: statusEl ? statusEl.value : 'New',
        technology: selectedTech,
        currency_code: currencyEl ? currencyEl.value : 'USD',
        estimated_value: estValEl && estValEl.value ? parseFloat(estValEl.value) : null,
        next_follow_up_date: followupEl && followupEl.value ? followupEl.value : null,
        due_date: dueEl && dueEl.value ? dueEl.value : null,
        contact_name: contactNameEl ? contactNameEl.value.trim() : '',
        email: contactEmailEl ? contactEmailEl.value.trim() : '',
        phone: contactPhoneEl ? contactPhoneEl.value.trim() : '',
        salary_range: salary,
        experience_criteria: experience,
        job_requirement: jobDescription,
        matching_score: lastEvaluatedManualLead ? lastEvaluatedManualLead.match_score : null,
        matching_skills: (selectedTech.length > 0) ? selectedTech : (lastEvaluatedManualLead ? lastEvaluatedManualLead.matched_skills : []),
        matching_reason: lastEvaluatedManualLead ? lastEvaluatedManualLead.match_reason : '',
        missing_skills: lastEvaluatedManualLead ? lastEvaluatedManualLead.missing_skills : [],
        notes: notesContent,
        outreach_email_subject: outreachSubjectEl ? outreachSubjectEl.value.trim() : '',
        outreach_email_body: outreachBodyEl ? outreachBodyEl.value.trim() : '',
        outreach_linkedin_message: outreachLinkedinEl ? outreachLinkedinEl.value.trim() : '',
    };

    const allButtons = [btn, btnTop, navSp, tblSp].filter(Boolean);
    allButtons.forEach(b => { b.disabled = true; });
    if (btnLabel) btnLabel.textContent = 'Saving to SharePoint...';
    if (btnTop) btnTop.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg> Saving...`;
    if (navSp) navSp.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg> Syncing...`;
    if (tblSp) tblSp.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg> Syncing...`;

    const msg = 'Posting edited Opportunity to SharePoint via Microsoft Graph API...';
    if (noteEl) {
        noteEl.className = 'text-xs text-blue-600 font-semibold animate-pulse';
        noteEl.textContent = msg;
    }
    if (bottomNoteEl) {
        bottomNoteEl.className = 'text-xs text-blue-600 font-semibold animate-pulse';
        bottomNoteEl.textContent = msg;
    }

    try {
        const res = await fetch('/api/sharepoint/add-opportunity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'SharePoint creation failed');
        }

        // Update in-memory allLeads so the table reflects the edited values
        if (allLeads.length > 0) {
            allLeads[0].job_title = title;
            allLeads[0].country = country;
            allLeads[0].location = country;
            allLeads[0].industry = industry;
            allLeads[0].job_url = website;
            allLeads[0].salary = salary;
            allLeads[0].experience = experience;
            allLeads[0].job_summary = notesContent;
            allLeads[0].matched_skills = payload.matching_skills;
            renderTable(allLeads);
        }

        if (lastEvaluatedManualLead) {
            lastEvaluatedManualLead.job_title = title;
            lastEvaluatedManualLead.country = country;
            lastEvaluatedManualLead.salary = salary;
            lastEvaluatedManualLead.experience = experience;
            lastEvaluatedManualLead.job_summary = notesContent;
            lastEvaluatedManualLead.extra_notes = notesContent;
        }

        if (editingStagedId) {
            const stagedMatch = stagedOpportunities.find(o => o.id === editingStagedId);
            if (stagedMatch) {
                stagedMatch.synced = true;
                stagedMatch.sync_status = 'Synced';
                renderStagedQueue();
            }
        }

        const successMsg = `✅ Successfully created Opportunity in SharePoint list '${title}'!`;
        if (noteEl) {
            noteEl.className = 'text-xs text-emerald-600 font-bold';
            noteEl.textContent = successMsg;
        }
        if (bottomNoteEl) {
            bottomNoteEl.className = 'text-xs text-emerald-600 font-bold';
            bottomNoteEl.textContent = successMsg;
        }
        showAlertModal('SharePoint Sync Complete', `Successfully added "${title}" to SharePoint Opportunity Tracker!`, 'success');

    } catch (err) {
        console.error('SharePoint Opportunity add error:', err);
        showAlertModal('SharePoint Error', err.message, 'error');
        const errMsg = `SharePoint Error: ${err.message}`;
        if (noteEl) {
            noteEl.className = 'text-xs text-rose-600 font-semibold';
            noteEl.textContent = errMsg;
        }
        if (bottomNoteEl) {
            bottomNoteEl.className = 'text-xs text-rose-600 font-semibold';
            bottomNoteEl.textContent = errMsg;
        }
    } finally {
        allButtons.forEach(b => { b.disabled = false; });
        if (btnLabel) btnLabel.textContent = 'Sync to SharePoint';
        if (btnTop) btnTop.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg> <span>Sync to SharePoint</span>`;
        if (navSp) navSp.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg> Sync to SharePoint`;
        if (tblSp) tblSp.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg> Sync to SharePoint`;
    }
}

// ==========================================
// Multi-Job Staging Queue & Batch SharePoint Sync
// ==========================================

function readManualFormValues() {
    const titleEl = document.getElementById('manual-job-title');
    const companyEl = document.getElementById('manual-company');
    const countryEl = document.getElementById('manual-country');
    const urlEl = document.getElementById('manual-job-url');
    const salaryEl = document.getElementById('manual-salary');
    const expEl = document.getElementById('manual-experience');
    const descEl = document.getElementById('manual-description');
    const ownerEl = document.getElementById('manual-owner');
    const leadSourceEl = document.getElementById('manual-lead-source');
    const industryEl = document.getElementById('manual-industry');
    const priorityEl = document.getElementById('manual-priority');
    const statusEl = document.getElementById('manual-status');
    const currencyEl = document.getElementById('manual-currency');
    const estValEl = document.getElementById('manual-estimated-value');
    const followupEl = document.getElementById('manual-followup-date');
    const dueEl = document.getElementById('manual-due-date');
    const contactNameEl = document.getElementById('manual-contact-name');
    const contactEmailEl = document.getElementById('manual-contact-email');
    const contactPhoneEl = document.getElementById('manual-contact-phone');
    const notesEl = document.getElementById('manual-notes');
    const outreachSubjectEl = document.getElementById('manual-outreach-email-subject');
    const outreachBodyEl = document.getElementById('manual-outreach-email-body');
    const outreachLinkedinEl = document.getElementById('manual-outreach-linkedin');

    const jobDescription = (descEl ? descEl.value : '').trim();
    const selectedTech = [];
    document.querySelectorAll('.manual-tech-checkbox:checked').forEach(cb => selectedTech.push(cb.value));

    const title = (titleEl ? titleEl.value : '').trim() || (lastEvaluatedManualLead ? lastEvaluatedManualLead.job_title : 'Direct Opportunity');
    const company = (companyEl ? companyEl.value : '').trim() || (lastEvaluatedManualLead ? lastEvaluatedManualLead.company : '');
    const country = countryEl ? countryEl.value : 'US';
    const industry = industryEl ? industryEl.value : 'IT';
    const website = (urlEl ? urlEl.value : '').trim();
    const salary = (salaryEl ? salaryEl.value : '').trim();
    const experience = (expEl ? expEl.value : '').trim();
    const notesContent = (notesEl ? notesEl.value : '').trim() || (lastEvaluatedManualLead ? (lastEvaluatedManualLead.extra_notes || lastEvaluatedManualLead.job_summary || '') : '');

    return {
        id: 'staged_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8),
        title: title,
        company: company,
        country: country,
        industry: industry,
        website: website,
        owner: getSelectedOwner(),
        lead_source: leadSourceEl ? leadSourceEl.value : 'Indeed',
        priority: priorityEl ? priorityEl.value : 'Medium',
        status: statusEl ? statusEl.value : 'New',
        technology: selectedTech,
        currency_code: currencyEl ? currencyEl.value : 'USD',
        estimated_value: estValEl && estValEl.value ? parseFloat(estValEl.value) : null,
        next_follow_up_date: followupEl && followupEl.value ? followupEl.value : null,
        due_date: dueEl && dueEl.value ? dueEl.value : null,
        contact_name: contactNameEl ? contactNameEl.value.trim() : '',
        email: contactEmailEl ? contactEmailEl.value.trim() : '',
        phone: contactPhoneEl ? contactPhoneEl.value.trim() : '',
        salary_range: salary,
        experience_criteria: experience,
        job_requirement: jobDescription,
        matching_score: lastEvaluatedManualLead ? lastEvaluatedManualLead.match_score : null,
        matching_skills: (selectedTech.length > 0) ? selectedTech : (lastEvaluatedManualLead ? lastEvaluatedManualLead.matched_skills : []),
        matching_reason: lastEvaluatedManualLead ? lastEvaluatedManualLead.match_reason : '',
        missing_skills: lastEvaluatedManualLead ? lastEvaluatedManualLead.missing_skills : [],
        notes: notesContent,
        outreach_email_subject: outreachSubjectEl ? outreachSubjectEl.value.trim() : '',
        outreach_email_body: outreachBodyEl ? outreachBodyEl.value.trim() : '',
        outreach_linkedin_message: outreachLinkedinEl ? outreachLinkedinEl.value.trim() : '',
        synced: false,
        sync_status: 'Pending'
    };
}

function populateManualForm(opp) {
    if (!opp) return;

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = (val !== null && val !== undefined) ? val : '';
    };

    setVal('manual-description', opp.job_requirement);
    setVal('manual-job-title', opp.title);
    setVal('manual-company', opp.company);
    setVal('manual-country', opp.country || 'US');
    setVal('manual-industry', opp.industry || 'IT');
    setVal('manual-job-url', opp.website);
    setSelectedOwner(opp.owner || 'Meet');
    setVal('manual-lead-source', opp.lead_source || 'Indeed');
    setVal('manual-priority', opp.priority || 'Medium');
    setVal('manual-status', opp.status || 'New');
    setVal('manual-currency', opp.currency_code || 'USD');
    setVal('manual-estimated-value', opp.estimated_value);
    setVal('manual-followup-date', opp.next_follow_up_date);
    setVal('manual-due-date', opp.due_date);
    setVal('manual-contact-name', opp.contact_name);
    setVal('manual-contact-email', opp.email);
    setVal('manual-contact-phone', opp.phone);
    setVal('manual-salary', opp.salary_range);
    setVal('manual-experience', opp.experience_criteria);
    setVal('manual-notes', opp.notes);

    const hasOutreach = !!(opp.outreach_email_subject || opp.outreach_email_body || opp.outreach_linkedin_message);
    const outreachSection = document.getElementById('manual-outreach-section');
    if (outreachSection) outreachSection.classList.toggle('hidden', !hasOutreach);
    setVal('manual-outreach-email-subject', opp.outreach_email_subject);
    setVal('manual-outreach-email-body', opp.outreach_email_body);
    setVal('manual-outreach-linkedin', opp.outreach_linkedin_message);
    manualLinkedinVariants = [];
    renderLinkedinVariantTabs('manual', [], '');

    const techList = (opp.technology || []).map(t => String(t).toLowerCase());
    document.querySelectorAll('.manual-tech-checkbox').forEach(cb => {
        cb.checked = techList.includes(cb.value.toLowerCase());
    });

    lastEvaluatedManualLead = {
        job_title: opp.title,
        country: opp.country,
        match_score: opp.matching_score,
        matched_skills: opp.matching_skills || opp.technology || [],
        missing_skills: opp.missing_skills || [],
        match_reason: opp.matching_reason || '',
        salary: opp.salary_range,
        experience: opp.experience_criteria,
        job_summary: opp.notes,
        extra_notes: opp.notes,
    };
}

function resetManualFormOnly() {
    [
        'manual-description',
        'manual-job-title',
        'manual-company',
        'manual-job-url',
        'manual-salary',
        'manual-experience',
        'manual-estimated-value',
        'manual-contact-name',
        'manual-contact-email',
        'manual-contact-phone',
        'manual-followup-date',
        'manual-due-date',
        'manual-notes',
        'manual-outreach-email-subject',
        'manual-outreach-email-body',
        'manual-outreach-linkedin',
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const countryEl = document.getElementById('manual-country');
    if (countryEl) countryEl.value = 'US';
    setSelectedOwner('Meet');
    const leadSourceEl = document.getElementById('manual-lead-source');
    if (leadSourceEl) leadSourceEl.value = 'Indeed';
    const industryEl = document.getElementById('manual-industry');
    if (industryEl) industryEl.value = 'IT';
    const priorityEl = document.getElementById('manual-priority');
    if (priorityEl) priorityEl.value = 'Medium';
    const statusEl = document.getElementById('manual-status');
    if (statusEl) statusEl.value = 'New';
    const currencyEl = document.getElementById('manual-currency');
    if (currencyEl) currencyEl.value = 'USD';

    document.querySelectorAll('.manual-tech-checkbox').forEach(cb => {
        cb.checked = (cb.value === 'SharePoint');
    });

    lastEvaluatedManualLead = null;
    manualLinkedinVariants = [];
    const outreachSection = document.getElementById('manual-outreach-section');
    if (outreachSection) outreachSection.classList.add('hidden');
    renderLinkedinVariantTabs('manual', [], '');

    const noteEl = document.getElementById('manual-status-note');
    if (noteEl) {
        noteEl.className = 'text-xs text-slate-500 font-medium';
        noteEl.textContent = '';
    }
    const bottomNoteEl = document.getElementById('manual-bottom-note');
    if (bottomNoteEl) {
        bottomNoteEl.className = 'text-xs text-slate-400 font-medium';
        bottomNoteEl.textContent = '';
    }
}

function stageCurrentManualJob() {
    if (editingStagedId) {
        updateStagedJob();
        return;
    }

    const descEl = document.getElementById('manual-description');
    const jobDescription = (descEl ? descEl.value : '').trim();
    if (!jobDescription) {
        showAlertModal('Input Required', 'Please enter or paste a job description first before adding to the queue.', 'warning');
        if (descEl) descEl.focus();
        return;
    }

    const opp = readManualFormValues();
    opp.lead_id = currentEvaluatingLeadId;
    stagedOpportunities.push(opp);

    // Synchronize bottom table (allLeads) with user's edited values
    let targetLead = null;
    if (currentEvaluatingLeadId) {
        targetLead = allLeads.find(l => String(l.id) === String(currentEvaluatingLeadId));
    }
    if (!targetLead && allLeads.length > 0) {
        targetLead = allLeads[0];
    }
    if (targetLead) {
        targetLead.job_title = opp.title;
        targetLead.company = opp.company;
        targetLead.country = opp.country;
        targetLead.location = opp.country;
        targetLead.salary = opp.salary_range;
        targetLead.experience = opp.experience_criteria;
        targetLead.job_summary = opp.notes;
        targetLead.matched_skills = opp.technology;
        targetLead.priority = opp.priority;
        targetLead.industry = opp.industry;
        targetLead.staged_id = opp.id;
    } else {
        targetLead = {
            id: opp.id,
            job_title: opp.title,
            company: opp.company || 'Direct Opportunity',
            location: opp.country,
            country: opp.country,
            salary: opp.salary_range,
            experience: opp.experience_criteria,
            job_summary: opp.notes,
            job_description: opp.job_requirement,
            job_url: opp.website,
            matched_skills: opp.technology,
            match_score: opp.matching_score,
            match_reason: opp.matching_reason,
            missing_skills: opp.missing_skills,
            industry: opp.industry,
            owner: opp.owner,
            staged_id: opp.id,
        };
        allLeads.unshift(targetLead);
    }
    renderTable(allLeads);

    // Sync to backend so periodic polling preserves edited values
    fetch('/api/leads/update-manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: currentEvaluatingLeadId || targetLead.id,
            title: opp.title,
            country: opp.country,
            salary: opp.salary_range,
            experience: opp.experience_criteria,
            notes: opp.notes,
            technology: opp.technology,
        })
    }).catch(e => console.warn('Background lead update:', e));

    currentEvaluatingLeadId = null;

    resetManualFormOnly();
    renderStagedQueue();

    const noteEl = document.getElementById('manual-status-note');
    if (noteEl) {
        noteEl.className = 'text-xs text-indigo-600 font-bold';
        noteEl.textContent = `✅ Staged "${opp.title}" (#${stagedOpportunities.length} in queue). Paste your next job description above!`;
    }

    const queueCard = document.getElementById('staged-queue-card');
    if (queueCard) {
        queueCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function editStagedJob(stagedId) {
    const opp = stagedOpportunities.find(o => o.id === stagedId);
    if (!opp) return;

    editingStagedId = stagedId;
    populateManualForm(opp);

    const banner = document.getElementById('editing-staged-banner');
    const titleSpan = document.getElementById('editing-staged-title');
    const badgeSpan = document.getElementById('editing-staged-badge');
    if (banner) banner.classList.remove('hidden');
    if (titleSpan) titleSpan.textContent = opp.title || 'Untitled Opportunity';
    if (badgeSpan) {
        const itemNum = stagedOpportunities.indexOf(opp) + 1;
        badgeSpan.textContent = `Editing Queue Item #${itemNum}`;
    }

    ['btn-update-staged-bottom'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('hidden');
    });
    ['btn-stage-job-bottom'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });

    renderStagedQueue();

    const formCard = document.getElementById('editing-staged-banner');
    if (formCard) {
        formCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    const titleInput = document.getElementById('manual-job-title');
    if (titleInput) titleInput.focus();
}

function updateStagedJob() {
    if (!editingStagedId) return;
    const idx = stagedOpportunities.findIndex(o => o.id === editingStagedId);
    if (idx === -1) {
        cancelEditStagedJob(false);
        return;
    }

    const oldTitle = stagedOpportunities[idx].title;
    const oldLeadId = stagedOpportunities[idx].lead_id;

    const updated = readManualFormValues();
    updated.id = editingStagedId;
    updated.lead_id = oldLeadId;
    updated.synced = false;
    updated.sync_status = 'Pending';
    stagedOpportunities[idx] = updated;

    // Synchronize bottom table (allLeads) with updated values
    let lead = allLeads.find(l => (oldLeadId && String(l.id) === String(oldLeadId)) || l.staged_id === editingStagedId || l.job_title === oldTitle);
    if (lead) {
        lead.job_title = updated.title;
        lead.country = updated.country;
        lead.location = updated.country;
        lead.salary = updated.salary_range;
        lead.experience = updated.experience_criteria;
        lead.job_summary = updated.notes;
        lead.matched_skills = updated.technology;
        lead.priority = updated.priority;
        lead.industry = updated.industry;
        renderTable(allLeads);
    }

    // Update backend so polling keeps edited values
    fetch('/api/leads/update-manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: oldLeadId || (lead ? lead.id : null),
            title: updated.title,
            country: updated.country,
            salary: updated.salary_range,
            experience: updated.experience_criteria,
            notes: updated.notes,
            technology: updated.technology,
        })
    }).catch(e => console.warn('Background lead update:', e));

    cancelEditStagedJob(true);
    renderStagedQueue();

    const noteEl = document.getElementById('manual-status-note');
    if (noteEl) {
        noteEl.className = 'text-xs text-emerald-600 font-bold';
        noteEl.textContent = `✅ Changes saved to Queue for "${updated.title}"!`;
    }
}

function cancelEditStagedJob(shouldReset = true) {
    editingStagedId = null;

    const banner = document.getElementById('editing-staged-banner');
    if (banner) banner.classList.add('hidden');

    ['btn-update-staged-bottom'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
    ['btn-stage-job-bottom'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('hidden');
    });

    if (shouldReset) {
        resetManualFormOnly();
    }
    renderStagedQueue();
}

function removeStagedJob(stagedId) {
    if (editingStagedId === stagedId) {
        cancelEditStagedJob(true);
    }
    const target = stagedOpportunities.find(o => o.id === stagedId);
    stagedOpportunities = stagedOpportunities.filter(o => o.id !== stagedId);
    if (target) {
        allLeads = allLeads.filter(l => l.staged_id !== stagedId && (!target.lead_id || String(l.id) !== String(target.lead_id)));
        renderTable(allLeads);
    }
    renderStagedQueue();
}

async function clearStagedQueue() {
    if (stagedOpportunities.length === 0) return;
    const confirmed = await showConfirmModal('Clear Queue', 'Are you sure you want to clear all staged jobs from the queue?', 'Yes, Clear Queue');
    if (confirmed) {
        if (editingStagedId) {
            cancelEditStagedJob(true);
        }
        // Remove manual staged leads from allLeads
        const stagedIds = new Set(stagedOpportunities.map(o => o.id));
        const leadIds = new Set(stagedOpportunities.map(o => o.lead_id).filter(Boolean).map(String));
        allLeads = allLeads.filter(l => !stagedIds.has(l.staged_id) && !leadIds.has(String(l.id)));
        renderTable(allLeads);

        stagedOpportunities = [];
        renderStagedQueue();
    }
}

function renderStagedQueue() {
    const badge = document.getElementById('staged-count-badge');
    const syncBtn = document.getElementById('btn-batch-sync-sharepoint');
    const syncLabel = document.getElementById('btn-batch-sync-label');
    const emptyState = document.getElementById('staged-queue-empty');
    const tableWrapper = document.getElementById('staged-queue-table-wrapper');
    const tbody = document.getElementById('staged-queue-body');

    const total = stagedOpportunities.length;

    if (badge) {
        badge.textContent = `${total} Job${total === 1 ? '' : 's'} Ready`;
        badge.className = total > 0 
            ? 'px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-700'
            : 'px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-500';
    }

    if (syncLabel) {
        syncLabel.textContent = total > 1 ? `Sync All (${total}) to SharePoint` : 'Sync to SharePoint';
    }
    if (syncBtn) {
        // Keep enabled if queue has jobs or if manual form has text
        const hasFormText = !!(document.getElementById('manual-description')?.value.trim());
        syncBtn.disabled = (total === 0 && !hasFormText);
    }

    if (total === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        if (tableWrapper) tableWrapper.classList.add('hidden');
        if (tbody) tbody.innerHTML = '';
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');
    if (tableWrapper) tableWrapper.classList.remove('hidden');

    if (tbody) {
        tbody.innerHTML = stagedOpportunities.map((opp, idx) => {
            const isEditing = (opp.id === editingStagedId);
            const rowClass = isEditing 
                ? 'bg-amber-50/80 ring-1 ring-amber-300 font-semibold transition-colors' 
                : 'hover:bg-slate-50/80 transition-colors';

            const techPills = (opp.technology && opp.technology.length > 0)
                ? opp.technology.slice(0, 3).map(t => `<span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200">${esc(t)}</span>`).join(' ') +
                  (opp.technology.length > 3 ? ` <span class="text-[10px] text-slate-400 font-semibold">+${opp.technology.length - 3}</span>` : '')
                : '<span class="text-slate-400 italic text-[11px]">None</span>';

            const priorityColor = {
                'High': 'bg-rose-100 text-rose-700 border-rose-200',
                'Medium': 'bg-amber-100 text-amber-700 border-amber-200',
                'Low': 'bg-blue-100 text-blue-700 border-blue-200'
            }[opp.priority] || 'bg-slate-100 text-slate-700 border-slate-200';

            const syncBadge = opp.synced
                ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <svg class="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                    Synced
                   </span>`
                : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                    Ready
                   </span>`;

            return `
                <tr class="${rowClass}">
                    <td class="px-3 py-3 text-center font-mono text-slate-400 text-[11px]">${idx + 1}</td>
                    <td class="px-4 py-3">
                        <div class="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                            <span class="truncate max-w-[200px]" title="${esc(opp.title)}">${esc(opp.title)}</span>
                            ${isEditing ? '<span class="px-1.5 py-0.2 rounded text-[9px] bg-amber-200 text-amber-900 font-bold uppercase">Active</span>' : ''}
                        </div>
                        ${opp.contact_name ? `<div class="text-[11px] text-slate-400 font-normal">Contact: ${esc(opp.contact_name)}</div>` : ''}
                    </td>
                    <td class="px-3 py-3 text-center">
                        <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">${esc(opp.country)}</span>
                    </td>
                    <td class="px-3 py-3 text-slate-700 text-xs">${esc(opp.owner || '-')}</td>
                    <td class="px-3 py-3">
                        <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${priorityColor}">${esc(opp.priority || 'Medium')}</span>
                    </td>
                    <td class="px-3 py-3">
                        <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">${esc(opp.status || 'New')}</span>
                    </td>
                    <td class="px-4 py-3">
                        <div class="flex flex-wrap gap-1 items-center max-w-[220px]">
                            ${techPills}
                        </div>
                    </td>
                    <td class="px-3 py-3 text-slate-600 text-xs whitespace-nowrap">${esc(opp.salary_range || '-')}</td>
                    <td class="px-3 py-3 text-slate-600 text-xs whitespace-nowrap">${esc(opp.experience_criteria || '-')}</td>
                    <td class="px-3 py-3 text-center">${syncBadge}</td>
                    <td class="px-4 py-3 text-right">
                        <div class="flex items-center justify-end gap-1.5">
                            <button type="button" onclick="editStagedJob('${esc(opp.id)}')"
                                class="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-700 font-bold rounded-lg border border-amber-200 transition-colors text-[11px] cursor-pointer flex items-center gap-1 shadow-2xs">
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                                <span>Edit</span>
                            </button>
                            <button type="button" onclick="removeStagedJob('${esc(opp.id)}')"
                                class="p-1 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded-lg transition-colors cursor-pointer"
                                title="Remove from queue">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }
}

async function syncAllStagedToSharePoint() {
    // 1. If currently editing a staged job, automatically save edits to the queue
    if (editingStagedId) {
        updateStagedJob();
    } else {
        // 2. If user evaluated or entered a job in the form but hasn't clicked "Add to Queue", auto-stage it now
        const descEl = document.getElementById('manual-description');
        const descText = (descEl ? descEl.value : '').trim();
        if (descText) {
            stageCurrentManualJob();
        }
    }

    // 3. If queue is still empty, alert user
    if (stagedOpportunities.length === 0) {
        showAlertModal('Queue Empty', 'No staged opportunities in the queue to sync. Please enter a job description or add jobs first.', 'warning');
        return;
    }

    const btn = document.getElementById('btn-batch-sync-sharepoint');
    const label = document.getElementById('btn-batch-sync-label');
    const icon = document.getElementById('batch-sync-icon');

    const totalToSync = stagedOpportunities.length;
    if (btn) btn.disabled = true;
    if (label) label.textContent = totalToSync > 1 ? `Syncing ${totalToSync} Jobs to SharePoint...` : 'Syncing to SharePoint...';
    if (icon) {
        icon.classList.add('animate-spin');
        icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m0 14v1m8-8h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/>`;
    }

    try {
        const res = await fetch('/api/sharepoint/batch-add-opportunity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(stagedOpportunities),
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || 'Batch SharePoint sync failed');
        }

        // Mark all opportunities as synced
        stagedOpportunities.forEach(o => {
            o.synced = true;
            o.sync_status = 'Synced';
        });

        renderStagedQueue();
        showAlertModal('SharePoint Sync Complete', data.message || `Successfully created ${data.count || totalToSync}/${stagedOpportunities.length} opportunities in SharePoint!`, 'success');

    } catch (err) {
        console.error('Batch SharePoint sync error:', err);
        showAlertModal('SharePoint Sync Error', err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
        if (label) {
            label.textContent = stagedOpportunities.length > 1
                ? `Sync All (${stagedOpportunities.length}) to SharePoint`
                : 'Sync to SharePoint';
        }
        if (icon) {
            icon.classList.remove('animate-spin');
            icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>`;
        }
    }
}

// ==========================================
// ==========================================
// Complete Global Reset / Clear Whole Page Modal Handlers
// ==========================================
function confirmResetPage() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) {
        modal.classList.remove('hidden');
    } else {
        if (confirm('Are you sure you want to reset the page? This will clear all input fields, parameters, search results, and table leads.')) {
            executeResetPage();
        }
    }
}

function closeResetModal() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) modal.classList.add('hidden');
}

async function executeResetPage() {
    closeResetModal();

    // 1. Reset Scraper inputs
    const usRadio = document.querySelector('input[name="country_radio"][value="US"]');
    if (usRadio) {
        usRadio.checked = true;
        updateSelectedCountryDisplay();
    }
    selectAllKeywords(true);
    const newKwInput = document.getElementById('input-new-keyword');
    if (newKwInput) newKwInput.value = '';
    const locInput = document.getElementById('input-location');
    if (locInput) locInput.value = 'remote';
    const fromageInput = document.getElementById('input-fromage');
    if (fromageInput) fromageInput.value = '1';

    // 2. Reset Manual Job Evaluator Form
    lastEvaluatedManualLead = null;
    manualLinkedinVariants = [];
    const outreachSection2 = document.getElementById('manual-outreach-section');
    if (outreachSection2) outreachSection2.classList.add('hidden');
    renderLinkedinVariantTabs('manual', [], '');
    [
        'manual-description',
        'manual-job-title',
        'manual-company',
        'manual-job-url',
        'manual-salary',
        'manual-experience',
        'manual-estimated-value',
        'manual-contact-name',
        'manual-contact-email',
        'manual-contact-phone',
        'manual-followup-date',
        'manual-due-date',
        'manual-notes',
        'manual-outreach-email-subject',
        'manual-outreach-email-body',
        'manual-outreach-linkedin',
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const countryEl = document.getElementById('manual-country');
    if (countryEl) countryEl.value = 'US';
    setSelectedOwner('Meet');
    const leadSourceEl = document.getElementById('manual-lead-source');
    if (leadSourceEl) leadSourceEl.value = 'Indeed';
    const industryEl = document.getElementById('manual-industry');
    if (industryEl) industryEl.value = 'IT';
    const priorityEl = document.getElementById('manual-priority');
    if (priorityEl) priorityEl.value = 'Medium';
    const statusEl = document.getElementById('manual-status');
    if (statusEl) statusEl.value = 'New';
    const currencyEl = document.getElementById('manual-currency');
    if (currencyEl) currencyEl.value = 'USD';

    document.querySelectorAll('.manual-tech-checkbox').forEach(cb => {
        cb.checked = (cb.value === 'SharePoint');
    });

    const noteEl = document.getElementById('manual-status-note');
    if (noteEl) {
        noteEl.className = 'text-xs text-slate-500 font-medium';
        noteEl.textContent = '';
    }
    const bottomNoteEl = document.getElementById('manual-bottom-note');
    if (bottomNoteEl) {
        bottomNoteEl.className = 'text-xs text-slate-400 font-medium';
        bottomNoteEl.textContent = '';
    }

    // 3. Reset Live Progress & Status bar
    const statusDot = document.getElementById('status-dot');
    if (statusDot) statusDot.className = 'w-2.5 h-2.5 rounded-full bg-slate-400';
    const statusText = document.getElementById('status-text');
    if (statusText) statusText.textContent = 'Idle';
    const searchStatus = document.getElementById('search-status');
    if (searchStatus) searchStatus.textContent = 'Status: Ready';
    const jobsFound = document.getElementById('jobs-found');
    if (jobsFound) jobsFound.textContent = '0';
    const progressPct = document.getElementById('progress-pct');
    if (progressPct) progressPct.textContent = '0%';
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) progressBar.style.width = '0%';
    const logText = document.getElementById('log-text');
    if (logText) logText.textContent = 'Ready for search query.';

    // 4. Reset Table Filter & leads count
    const filterInput = document.getElementById('filter-search');
    if (filterInput) filterInput.value = '';
    const countEl = document.getElementById('leads-count');
    if (countEl) countEl.textContent = '0';

    // 5. Clear backend leads (both the Indeed/manual store and the Dice store)
    try {
        await fetch('/api/jobs/clear', { method: 'POST' });
    } catch (e) {
        console.error('Error clearing backend jobs:', e);
    }
    try {
        await fetch('/api/dice/clear', { method: 'POST' });
    } catch (e) {
        console.error('Error clearing backend Dice results:', e);
    }

    // 6. Reset leads state and render empty table
    allLeads = [];
    lastLeadsHash = '';
    renderTable([]);

    // 7. Hide Action Buttons
    const navDl = document.getElementById('nav-download-btn');
    const tblDl = document.getElementById('table-download-btn');
    const navSp = document.getElementById('nav-sharepoint-btn');
    const tblSp = document.getElementById('table-sharepoint-btn');
    const tblOutreach = document.getElementById('table-generate-outreach-btn');
    const tblClr = document.getElementById('table-clear-btn');
    [navDl, tblDl, navSp, tblSp, tblOutreach, tblClr].forEach(b => b && b.classList.add('hidden'));

    // 8. Reset Staged Queue
    stagedOpportunities = [];
    editingStagedId = null;
    cancelEditStagedJob(false);
    renderStagedQueue();
}

function clearManualForm() {
    if (editingStagedId) {
        cancelEditStagedJob(true);
        return;
    }
    resetManualFormOnly();
}

// ==========================================
// Custom UI Modal Alerts & Confirmation Popups
// ==========================================
let customConfirmResolver = null;

function showAlertModal(title, message, type = 'success') {
    const modal = document.getElementById('custom-alert-modal');
    const titleEl = document.getElementById('custom-alert-title');
    const msgEl = document.getElementById('custom-alert-message');
    const iconBox = document.getElementById('custom-alert-icon-box');
    const btn = document.getElementById('custom-alert-btn');

    if (!modal) {
        alert(`${title}\n\n${message}`);
        return;
    }

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;

    const icons = {
        success: {
            bg: 'bg-emerald-50 border-emerald-200 text-emerald-600',
            btnBg: 'bg-emerald-600 hover:bg-emerald-700 shadow-emerald-500/20',
            btnText: 'OK',
            svg: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>`
        },
        error: {
            bg: 'bg-rose-50 border-rose-200 text-rose-600',
            btnBg: 'bg-rose-600 hover:bg-rose-700 shadow-rose-500/20',
            btnText: 'Close',
            svg: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`
        },
        warning: {
            bg: 'bg-amber-50 border-amber-200 text-amber-600',
            btnBg: 'bg-amber-600 hover:bg-amber-700 shadow-amber-500/20',
            btnText: 'Got It',
            svg: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>`
        },
        info: {
            bg: 'bg-blue-50 border-blue-200 text-blue-600',
            btnBg: 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20',
            btnText: 'OK',
            svg: `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
        }
    };

    const cfg = icons[type] || icons.info;
    if (iconBox) {
        iconBox.className = `w-12 h-12 rounded-2xl border flex items-center justify-center shrink-0 shadow-2xs ${cfg.bg}`;
        iconBox.innerHTML = cfg.svg;
    }
    if (btn) {
        btn.className = `px-5 py-2.5 text-white rounded-xl text-xs font-bold transition-all shadow-md cursor-pointer active:scale-95 ${cfg.btnBg}`;
        btn.textContent = cfg.btnText;
    }

    modal.classList.remove('hidden');
}

function closeCustomAlertModal() {
    const modal = document.getElementById('custom-alert-modal');
    if (modal) modal.classList.add('hidden');
}

function showConfirmModal(title, message, confirmBtnText = 'Confirm') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-confirm-modal');
        const titleEl = document.getElementById('custom-confirm-title');
        const msgEl = document.getElementById('custom-confirm-message');
        const btn = document.getElementById('custom-confirm-action-btn');

        if (!modal) {
            resolve(confirm(`${title}\n\n${message}`));
            return;
        }

        if (titleEl) titleEl.textContent = title;
        if (msgEl) msgEl.textContent = message;
        if (btn) btn.textContent = confirmBtnText;

        customConfirmResolver = resolve;
        modal.classList.remove('hidden');
    });
}

function closeCustomConfirmModal(result) {
    const modal = document.getElementById('custom-confirm-modal');
    if (modal) modal.classList.add('hidden');
    if (customConfirmResolver) {
        customConfirmResolver(result);
        customConfirmResolver = null;
    }
}

window.showAlertModal = showAlertModal;
window.closeCustomAlertModal = closeCustomAlertModal;
window.showConfirmModal = showConfirmModal;
window.closeCustomConfirmModal = closeCustomConfirmModal;
window.confirmResetPage = confirmResetPage;
window.closeResetModal = closeResetModal;
window.executeResetPage = executeResetPage;
window.clearManualForm = clearManualForm;
window.switchMode = switchMode;
window.evaluateManualJob = evaluateManualJob;
window.addManualToSharePoint = addManualToSharePoint;
window.stageCurrentManualJob = stageCurrentManualJob;
window.editStagedJob = editStagedJob;
window.updateStagedJob = updateStagedJob;
window.cancelEditStagedJob = cancelEditStagedJob;
window.removeStagedJob = removeStagedJob;
window.clearStagedQueue = clearStagedQueue;
window.syncAllStagedToSharePoint = syncAllStagedToSharePoint;
window.renderStagedQueue = renderStagedQueue;
window.resetManualFormOnly = resetManualFormOnly;
window.selectAllKeywords = selectAllKeywords;
window.addCustomKeywordCheckbox = addCustomKeywordCheckbox;
window.handleKeywordInputKey = handleKeywordInputKey;
window.startSearch = startSearch;
window.stopSearch = stopSearch;
window.filterTable = filterTable;
window.exportExcel = exportExcel;
window.exportSharePoint = exportSharePoint;
window.generateOutreachForSelectedLeads = generateOutreachForSelectedLeads;
window.toggleLeadSelection = toggleLeadSelection;
window.toggleSelectAllLeads = toggleSelectAllLeads;
window.openDescriptionModal = openDescriptionModal;
window.closeDescriptionModal = closeDescriptionModal;
window.generateModalOutreach = generateModalOutreach;
window.saveModalOutreach = saveModalOutreach;
window.copyOutreachField = copyOutreachField;
window.selectLinkedinVariant = selectLinkedinVariant;

document.addEventListener('DOMContentLoaded', () => {
    initOwnerSynchronization();
    updateIstClock();
    setInterval(updateIstClock, 1000);
    updateSelectedCountryDisplay();
    updateSelectedKeywordsDisplay();
    updateDiceKeywordDisplay();
    updateDiceCountryDisplay();
    connectWebSocket();
    fetchLeads();
    renderStagedQueue();
});
