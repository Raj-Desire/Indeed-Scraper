// app.js — Single-Page Application Logic

let ws = null;
let pollTimer = null;
let allLeads = [];

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
        alert('Please check at least 1 keyword to search.');
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
            alert(`Notice: ${data.detail || 'Failed to start search'}`);
            return;
        }

        document.getElementById('search-status').textContent = `Status: Scraping ${keywords.length} keywords in ${countryCode}...`;
        setSearchButtonState(true, 'Scraping Active...');
        setStopButtonState(false);

        // Start polling for live table updates
        if (pollTimer) clearInterval(pollTimer);
        fetchLeads();
        pollTimer = setInterval(fetchLeads, 2000);

    } catch (e) {
        isSearchRunning = false;
        setSearchButtonState(false);
        setStopButtonState(true);
        document.getElementById('search-status').textContent = 'Status: Ready';
        alert(`Connection Failed: ${e.message}`);
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
        allLeads = data.leads || [];

        // Check if data actually changed to prevent DOM blinking
        const currentHash = JSON.stringify(allLeads.map(l => [l.id, l.match_score, l.job_title, l.company]));
        if (currentHash !== lastLeadsHash) {
            // Only update table if content changed AND user is not actively hovering skills popup
            if (!isUserHoveringSkills) {
                lastLeadsHash = currentHash;
                renderTable(allLeads);
            }
        }

        // Show download, SharePoint sync, and Clear buttons if leads exist
        const navDl = document.getElementById('nav-download-btn');
        const tblDl = document.getElementById('table-download-btn');
        const navSp = document.getElementById('nav-sharepoint-btn');
        const tblSp = document.getElementById('table-sharepoint-btn');
        const tblClr = document.getElementById('table-clear-btn');
        const hasLeads = allLeads.length > 0;

        [navDl, tblDl].forEach(b => b && b.classList.toggle('hidden', !hasLeads));
        [navSp, tblSp].forEach(b => b && b.classList.toggle('hidden', !hasLeads));
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
                <td colspan="12" class="px-5 py-12 text-center text-slate-400 font-medium">
                    No leads found yet. Click <strong class="text-slate-700">"Search Jobs"</strong> above.
                </td>
            </tr>`;
        return;
    }

    // Sort leads client-side: Highest Match Score first (unranked at bottom)
    const sortedLeads = [...leads].sort((a, b) => {
        const scoreA = (a.match_score !== null && a.match_score !== undefined) ? Number(a.match_score) : -1;
        const scoreB = (b.match_score !== null && b.match_score !== undefined) ? Number(b.match_score) : -1;
        return scoreB - scoreA;
    });

    tbody.innerHTML = sortedLeads.map(l => {
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
            let badgeBg = 'bg-slate-100 text-slate-700 border-slate-200';
            if (score >= 75) {
                badgeBg = 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
            } else if (score >= 50) {
                badgeBg = 'bg-blue-50 text-blue-800 border-blue-300 font-bold';
            } else if (score >= 25) {
                badgeBg = 'bg-amber-50 text-amber-800 border-amber-300 font-bold';
            } else {
                badgeBg = 'bg-rose-50 text-rose-700 border-rose-300 font-semibold';
            }
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
        <tr class="border-b border-slate-100 hover:bg-slate-50/80 transition-colors">
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
}

function openDescriptionModal(jobId) {
    const job = allLeads.find(l => String(l.id) === String(jobId));
    if (!job) return;

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
        matchScoreEl.className = 'px-2.5 py-0.5 rounded-full text-xs font-bold border shadow-2xs ' + 
            (score >= 75 ? 'bg-emerald-100 text-emerald-800 border-emerald-300' :
             score >= 50 ? 'bg-blue-100 text-blue-800 border-blue-300' :
             score >= 25 ? 'bg-amber-100 text-amber-800 border-amber-300' : 'bg-rose-100 text-rose-800 border-rose-300');
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

    const modal = document.getElementById('job-modal');
    if (modal) modal.classList.remove('hidden');
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

function connectWebSocket() {
    ws = new WebSocket(`ws://${location.host}/ws/progress`);
    ws.onopen = () => console.log('WebSocket connected');
    ws.onclose = () => setTimeout(connectWebSocket, 3000);

    ws.onmessage = (e) => {
        const p = JSON.parse(e.data);

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
    };
}

async function exportSharePoint() {
    // If currently in Manual Evaluator mode, sync the current manual opportunity with edited fields
    if (currentAppMode === 'manual') {
        return await addManualToSharePoint();
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
        const res = await fetch('/api/export/sharepoint', { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            alert(`🎉 ${data.message}`);
        } else {
            alert(`⚠️ SharePoint Sync Error: ${data.detail || data.message || 'Failed to sync'}`);
        }
    } catch (e) {
        alert(`❌ Network Error: ${e.message}`);
    } finally {
        btns.forEach(b => {
            b.disabled = false;
            b.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg> Sync to SharePoint`;
        });
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
// Mode Switcher (Scraper vs Manual Evaluator)
// ==========================================
let currentAppMode = 'scraper';

function switchMode(mode) {
    currentAppMode = mode;
    const btnScraper = document.getElementById('tab-btn-scraper');
    const btnManual = document.getElementById('tab-btn-manual');
    const panelScraper = document.getElementById('panel-scraper');
    const panelManual = document.getElementById('panel-manual');
    const thCompany = document.getElementById('th-company');

    if (!btnScraper || !btnManual || !panelScraper || !panelManual) return;

    if (mode === 'scraper') {
        btnScraper.className = 'px-4 py-2 text-xs font-bold rounded-xl transition-all flex items-center gap-2 bg-blue-600 text-white shadow-xs cursor-pointer';
        btnManual.className = 'px-4 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 cursor-pointer';
        panelScraper.classList.remove('hidden');
        panelManual.classList.add('hidden');
        if (thCompany) thCompany.classList.remove('hidden');
        document.querySelectorAll('.col-company').forEach(el => el.classList.remove('hidden'));
    } else {
        btnManual.className = 'px-4 py-2 text-xs font-bold rounded-xl transition-all flex items-center gap-2 bg-blue-600 text-white shadow-xs cursor-pointer';
        btnScraper.className = 'px-4 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 cursor-pointer';
        panelManual.classList.remove('hidden');
        panelScraper.classList.add('hidden');
        if (thCompany) thCompany.classList.add('hidden');
        document.querySelectorAll('.col-company').forEach(el => el.classList.add('hidden'));
    }
}

// ==========================================
// Manual Job Description Evaluation & SharePoint Sync
// ==========================================
let lastEvaluatedManualLead = null;

async function evaluateManualJob() {
    const titleEl = document.getElementById('manual-job-title');
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
        alert('Please paste a job description or technical requirements first.');
        if (descEl) descEl.focus();
        return;
    }

    const payload = {
        job_title: (titleEl ? titleEl.value : '').trim() || 'Untitled Opportunity',
        company: '',
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
        const parsed = data.parsed_fields || {};
        lastEvaluatedManualLead = {
            ...lead,
            extra_notes: parsed.notes || '',
        };

        // Reset previous extracted fields first before populating new values
        if (titleEl) titleEl.value = '';
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

        const ownerEl = document.getElementById('manual-owner');
        if (ownerEl && parsed.owner) {
            ownerEl.value = parsed.owner;
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
                const sc = Number(lead.match_score);
                priorityEl.value = sc >= 75 ? 'High' : (sc >= 45 ? 'Medium' : 'Low');
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

        // Show download, SharePoint, and Clear buttons
        const navDl = document.getElementById('nav-download-btn');
        const tblDl = document.getElementById('table-download-btn');
        const navSp = document.getElementById('nav-sharepoint-btn');
        const tblSp = document.getElementById('table-sharepoint-btn');
        const tblClr = document.getElementById('table-clear-btn');
        [navDl, tblDl, navSp, tblSp, tblClr].forEach(b => b && b.classList.remove('hidden'));

        // Smooth scroll to table so user sees the newly evaluated card
        const tableCard = document.getElementById('leads-body');
        if (tableCard) {
            tableCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

    } catch (err) {
        console.error('Manual evaluate error:', err);
        alert(`Evaluation error: ${err.message}`);
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

    const jobDescription = (descEl ? descEl.value : '').trim();
    if (!jobDescription) {
        alert('Please enter or paste a job description first.');
        if (descEl) descEl.focus();
        return;
    }

    // Always read current checked technology checkboxes
    const selectedTech = [];
    document.querySelectorAll('.manual-tech-checkbox:checked').forEach(cb => selectedTech.push(cb.value));

    // Strictly read current edited values from DOM
    const title = (titleEl ? titleEl.value : '').trim() || (lastEvaluatedManualLead ? lastEvaluatedManualLead.job_title : 'Direct Opportunity');
    const country = countryEl ? countryEl.value : 'US';
    const industry = industryEl ? industryEl.value : 'IT';
    const website = (urlEl ? urlEl.value : '').trim();
    const salary = (salaryEl ? salaryEl.value : '').trim();
    const experience = (expEl ? expEl.value : '').trim();
    const notesContent = (notesEl ? notesEl.value : '').trim() || (lastEvaluatedManualLead ? (lastEvaluatedManualLead.extra_notes || lastEvaluatedManualLead.job_summary || '') : '');

    const payload = {
        title: title,
        country: country,
        industry: industry,
        website: website,
        owner: ownerEl ? ownerEl.value : 'Meet',
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

        const successMsg = `✅ Successfully created Opportunity in SharePoint list '${title}'!`;
        if (noteEl) {
            noteEl.className = 'text-xs text-emerald-600 font-bold';
            noteEl.textContent = successMsg;
        }
        if (bottomNoteEl) {
            bottomNoteEl.className = 'text-xs text-emerald-600 font-bold';
            bottomNoteEl.textContent = successMsg;
        }
        alert(`Successfully added "${title}" to SharePoint Opportunity Tracker!`);

    } catch (err) {
        console.error('SharePoint Opportunity add error:', err);
        alert(`SharePoint Error: ${err.message}`);
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
    [
        'manual-description',
        'manual-job-title',
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
    ].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const countryEl = document.getElementById('manual-country');
    if (countryEl) countryEl.value = 'US';
    const ownerEl = document.getElementById('manual-owner');
    if (ownerEl) ownerEl.value = 'Meet';
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

    // 5. Clear backend leads
    try {
        await fetch('/api/jobs/clear', { method: 'POST' });
    } catch (e) {
        console.error('Error clearing backend jobs:', e);
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
    const tblClr = document.getElementById('table-clear-btn');
    [navDl, tblDl, navSp, tblSp, tblClr].forEach(b => b && b.classList.add('hidden'));
}

function clearManualForm() {
    confirmResetPage();
}

// ==========================================
// Clear All Leads
// ==========================================
async function clearAllLeads() {
    confirmResetPage();
}

window.confirmResetPage = confirmResetPage;
window.closeResetModal = closeResetModal;
window.executeResetPage = executeResetPage;
window.clearManualForm = clearManualForm;
window.clearAllLeads = clearAllLeads;
window.switchMode = switchMode;
window.evaluateManualJob = evaluateManualJob;
window.addManualToSharePoint = addManualToSharePoint;
window.selectAllKeywords = selectAllKeywords;
window.addCustomKeywordCheckbox = addCustomKeywordCheckbox;
window.handleKeywordInputKey = handleKeywordInputKey;
window.startSearch = startSearch;
window.stopSearch = stopSearch;
window.filterTable = filterTable;
window.exportSharePoint = exportSharePoint;
window.openDescriptionModal = openDescriptionModal;
window.closeDescriptionModal = closeDescriptionModal;

document.addEventListener('DOMContentLoaded', () => {
    updateIstClock();
    setInterval(updateIstClock, 1000);
    updateSelectedCountryDisplay();
    updateSelectedKeywordsDisplay();
    connectWebSocket();
    fetchLeads();
});
