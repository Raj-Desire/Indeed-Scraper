// app.js — Single-Page Application Logic

let ws = null;
let pollTimer = null;
let allLeads = [];

// Start User-Defined Search
async function startSearch() {
    const country = document.getElementById('input-country')?.value || 'US';
    const query = document.getElementById('input-query')?.value || 'AI Developer';
    const locationType = document.getElementById('input-location')?.value || 'all';
    const pages = parseInt(document.getElementById('input-pages')?.value || '3');
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
                country,
                query,
                location_type: locationType,
                max_pages: pages,
                parser_engine: parserEngine
            }),
        });
        const data = await res.json();

        if (!res.ok) {
            alert(`Error: ${data.detail || 'Failed to start search'}`);
            return;
        }

        document.getElementById('search-status').textContent = 'Status: Scraping in progress...';
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

        // Show download buttons if leads exist
        const navBtn = document.getElementById('nav-download-btn');
        const tblBtn = document.getElementById('table-download-btn');
        if (allLeads.length > 0) {
            if (navBtn) navBtn.classList.remove('hidden');
            if (tblBtn) tblBtn.classList.remove('hidden');
        } else {
            if (navBtn) navBtn.classList.add('hidden');
            if (tblBtn) tblBtn.classList.add('hidden');
        }
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
                <td colspan="6" class="px-5 py-12 text-center text-gray-500">
                    No leads found yet. Click <strong>"Search Jobs"</strong> above.
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = leads.map(l => `
        <tr class="border-b border-navy-800/50 hover:bg-navy-800/40 transition-colors">
            <td class="px-5 py-3">
                <p class="text-white font-medium leading-tight">${esc(l.job_title)}</p>
                <p class="text-gray-400 text-xs mt-0.5">${esc(l.company)}</p>
            </td>
            <td class="px-5 py-3 text-xs text-gray-300">
                ${esc(l.location || l.country)}
            </td>
            <td class="px-5 py-3 text-xs text-gray-400">
                ${esc(l.remote_type || 'Remote')}
            </td>
            <td class="px-5 py-3 text-xs text-gray-300">
                ${esc(l.salary)}
            </td>
            <td class="px-5 py-3 text-xs text-gray-500">
                ${esc(l.posted_date)}
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
        (l.company || '').toLowerCase().includes(q)
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

function esc(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchLeads();
});
