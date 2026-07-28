// app.js — Single-Page Application Logic

let ws = null;
let pollTimer = null;
let allLeads = [];

function getSelectedCountries() {
    const checkboxes = document.querySelectorAll('input[name="country_checkbox"]:checked');
    const selected = Array.from(checkboxes).map(cb => cb.value);
    return selected.length > 0 ? selected : ['US'];
}

function updateSelectedCountriesDisplay() {
    const checkboxes = document.querySelectorAll('input[name="country_checkbox"]:checked');
    const bar = document.getElementById('selected-countries-bar');
    const badge = document.getElementById('country-count-badge');
    
    if (badge) {
        const count = checkboxes.length;
        badge.textContent = count === 1 ? '1 Country Selected' : `${count} Countries Selected`;
    }

    if (!bar) return;

    if (checkboxes.length === 0) {
        bar.innerHTML = `<span class="text-amber-400 text-xs italic">No country selected. Defaulting to US.</span>`;
        return;
    }

    bar.innerHTML = Array.from(checkboxes).map(cb => {
        const code = cb.value;
        const name = cb.getAttribute('data-name') || code;
        return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shrink-0">
            ${esc(name)} <span class="text-cyan-400 text-[10px]">(${esc(code)})</span>
        </span>`;
    }).join('');
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

// Start User-Defined Search
async function startSearch() {
    const countries = getSelectedCountries();
    const query = document.getElementById('input-query')?.value || 'AI Developer';
    const locationType = document.getElementById('input-location')?.value || 'all';
    const fromage = document.getElementById('input-fromage')?.value || 'all';
    const pages = parseInt(document.getElementById('input-pages')?.value || '1');
    const parserEngine = document.getElementById('input-parser')?.value || 'beautifulsoup';

    if (!query.trim()) {
        alert('Please enter a job role or keyword.');
        return;
    }

    try {
        const res = await fetch('/api/scraper/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                countries,
                query,
                location_type: locationType,
                fromage,
                max_pages: pages,
                parser_engine: parserEngine
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            alert(`Error: ${data.detail || 'Failed to start search'}`);
            return;
        }

        document.getElementById('search-status').textContent = `Status: Scraping ${countries.length} ${countries.length === 1 ? 'country' : 'countries'}...`;
        document.getElementById('btn-search').disabled = true;
        document.getElementById('btn-stop').disabled = false;

        // Start polling for live table updates
        if (pollTimer) clearInterval(pollTimer);
        fetchLeads();
        pollTimer = setInterval(fetchLeads, 2000);

    } catch (e) {
        alert(`Failed: ${e.message}`);
    }
}

async function stopSearch() {
    await fetch('/api/scraper/stop', { method: 'POST' });
    document.getElementById('search-status').textContent = 'Status: Stopping...';
}

async function fetchLeads() {
    try {
        const res = await fetch('/api/leads');
        const data = await res.json();
        allLeads = data.leads || [];

        renderTable(allLeads);

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
                <td colspan="9" class="px-5 py-12 text-center text-gray-500">
                    No leads found yet. Click <strong>"Search Jobs"</strong> above.
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = leads.map(l => `
        <tr class="border-b border-navy-800/50 hover:bg-navy-800/40 transition-colors">
            <td class="px-5 py-3 text-xs text-white font-medium">
                ${esc(l.job_title)}
            </td>
            <td class="px-5 py-3 text-xs text-gray-300">
                ${esc(l.company)}
            </td>
            <td class="px-5 py-3 text-xs text-cyan-300 font-semibold">
                ${esc(l.country || 'US')}
            </td>
            <td class="px-5 py-3 text-xs text-gray-300">
                ${esc(l.location_remote_type || l.location || l.remote_type || 'Not listed')}
            </td>
            <td class="px-5 py-3 text-xs text-gray-300">
                ${esc(l.salary)}
            </td>
            <td class="px-5 py-3 text-xs text-gray-400">
                ${esc(l.industry || 'Not listed')}
            </td>
            <td class="px-5 py-3 text-xs text-gray-400">
                ${esc(l.company_size || 'Not listed')}
            </td>
            <td class="px-5 py-3 text-xs text-gray-500">
                ${esc(l.posted_date || 'Not listed')}
            </td>
            <td class="px-5 py-3">
                ${l.job_url ? `<a href="${esc(l.job_url)}" target="_blank" class="text-xs text-cyan-400 hover:underline">View Indeed ↗</a>` : '—'}
            </td>
        </tr>
    `).join('');
}

function filterTable() {
    const q = (document.getElementById('filter-search')?.value || '').toLowerCase();
    if (!q) {
        renderTable(allLeads);
        return;
    }
    const filtered = allLeads.filter(l =>
        (l.job_title || '').toLowerCase().includes(q) ||
        (l.company || '').toLowerCase().includes(q) ||
        (l.country || '').toLowerCase().includes(q)
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

        if (statusDot) {
            const colors = { running: 'bg-green-500 animate-pulse', idle: 'bg-gray-500', completed: 'bg-blue-500', error: 'bg-red-500' };
            statusDot.className = `w-2.5 h-2.5 rounded-full ${colors[p.status] || 'bg-gray-500'}`;
        }
        if (statusText) statusText.textContent = p.status ? p.status.charAt(0).toUpperCase() + p.status.slice(1) : 'Idle';

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

        if (p.log_messages && p.log_messages.length > 0) {
            if (logText) logText.textContent = p.log_messages[p.log_messages.length - 1];
        }

        if (p.status === 'completed' || p.status === 'idle' || p.status === 'stopped') {
            document.getElementById('btn-search').disabled = false;
            document.getElementById('btn-stop').disabled = true;
            if (p.status === 'completed') {
                document.getElementById('search-status').textContent = 'Status: Search Completed 🎉';
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

document.addEventListener('DOMContentLoaded', () => {
    updateSelectedCountriesDisplay();
    connectWebSocket();
    fetchLeads();
});
