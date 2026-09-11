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

// 7 Core Keywords & Checkbox Management
const DEFAULT_CORE_KEYWORDS = [
    "SharePoint",
    "Power Apps",
    "Power Automate",
    "AI",
    ".NET",
    "React",
    "n8n"
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

        // Show download & SharePoint sync buttons if leads exist
        const navDl = document.getElementById('nav-download-btn');
        const tblDl = document.getElementById('table-download-btn');
        const navSp = document.getElementById('nav-sharepoint-btn');
        const tblSp = document.getElementById('table-sharepoint-btn');
        const hasLeads = allLeads.length > 0;

        [navDl, tblDl].forEach(b => b && b.classList.toggle('hidden', !hasLeads));
        [navSp, tblSp].forEach(b => b && b.classList.toggle('hidden', !hasLeads));
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
                <td colspan="13" class="px-5 py-12 text-center text-slate-400 font-medium">
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

        // Match Reason snippet
        const reasonSnippet = l.match_reason ? (l.match_reason.length > 90 ? l.match_reason.slice(0, 90) + '...' : l.match_reason) : '—';

        return `
        <tr class="border-b border-slate-100 hover:bg-slate-50/80 transition-colors">
            <td class="px-5 py-3 text-xs">
                <div class="font-semibold text-slate-900">${esc(l.job_title)}</div>
                ${l.role ? `<div class="text-[10px] text-slate-500 font-medium mt-0.5">${esc(l.role)}</div>` : ''}
            </td>
            <td class="px-5 py-3 text-xs font-medium text-slate-700">
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
            <td class="px-5 py-3 text-xs text-slate-600 max-w-[220px]">
                <div class="text-[11px] leading-relaxed line-clamp-2" title="${esc(l.match_reason || '')}">${esc(reasonSnippet)}</div>
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
            <td class="px-5 py-3 text-xs text-slate-500">
                ${esc(l.industry || 'Not listed')}
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
    document.getElementById('modal-industry').textContent = job.industry || 'Not listed';
    
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

document.addEventListener('DOMContentLoaded', () => {
    updateIstClock();
    setInterval(updateIstClock, 1000);
    updateSelectedCountryDisplay();
    updateSelectedKeywordsDisplay();
    connectWebSocket();
    fetchLeads();
});
