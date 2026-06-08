/**
 * Displays a toast notification.
 * @param {string} message The message to display.
 * @param {'success'|'error'|'info'|'warning'} type The type of toast.
 */
function showToast(message, type = 'success') {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        document.body.appendChild(toast);
    }
    toast.className = `toast ${type} show`;
    toast.innerText = message;

    let duration = 3500; // Default for success
    if (type === 'error') duration = 4500;
    if (type === 'info') duration = 3200;
    if (type === 'warning') duration = 4000;

    setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

/**
 * Formats an error message for the report preview box.
 * @param {string|string[]} details The error details.
 * @returns {string} The formatted error message.
 */
function formatReportError(details) {
    if (Array.isArray(details) && details.length > 0) {
        return `Please complete the following required data before generating report:\n\n${details.map((item, idx) => `${idx + 1}. ${item}`).join('\n')}`;
    }
    if (typeof details === 'string' && details.trim()) {
        return details;
    }
    return 'Unable to generate report.';
}

/**
 * Resets the report export UI elements to a disabled state.
 */
function invalidateReportExport() {
    const exportBtn = document.getElementById('export-btn');
    const pdfReport = document.getElementById('pdf-ai-report');
    const missingPanel = document.getElementById('missing-data-panel');
    const reportOutput = document.getElementById('report-output');
    const reportJson = document.getElementById('report-json');
    if (exportBtn) exportBtn.disabled = true;
    if (pdfReport) pdfReport.value = '';
    const pdfProjectName = document.getElementById('pdf-project-name');
    const pdfClaimantId = document.getElementById('pdf-claimant-user-id');
    if (pdfProjectName) pdfProjectName.value = document.getElementById('project-select') ? document.getElementById('project-select').value : '';
    if (pdfClaimantId) pdfClaimantId.value = document.getElementById('claimant-select') ? document.getElementById('claimant-select').value : '';
    if (missingPanel) missingPanel.style.display = 'none';
    if (reportOutput) reportOutput.style.display = 'none';
    if (reportJson) reportJson.innerText = '';
}

function getProjectClaimantMap() {
    const configElement = document.getElementById('report-dashboard-config');
    if (configElement && configElement.dataset && configElement.dataset.projectClaimants) {
        try {
            return JSON.parse(configElement.dataset.projectClaimants || '{}');
        } catch (error) {
            return {};
        }
    }
    return window.REPORT_PROJECT_CLAIMANTS || {};
}

function getDashboardDefaults() {
    const configElement = document.getElementById('report-dashboard-config');
    if (configElement && configElement.dataset) {
        return {
            project: configElement.dataset.defaultProject || '',
            claimant: configElement.dataset.defaultClaimant || '',
        };
    }
    return {
        project: window.REPORT_DEFAULT_PROJECT || '',
        claimant: window.REPORT_DEFAULT_CLAIMANT || '',
    };
}

function isOthersProject(projectName) {
    const value = String(projectName || '').trim();
    return value === 'Others / Unassigned' || value === 'Others / Unrelated' || value === '__others__';
}

function getKnownProjectNames() {
    const map = getProjectClaimantMap();
    return new Set(Object.keys(map).map((item) => String(item || '').trim()).filter(Boolean));
}

function getUnassignedDefectUnits() {
    // Determine unassigned units by checking defects whose owner_id is not
    // present among known claimant homeowner IDs (server-provided), or
    // defects explicitly marked with an Others project name.
    const map = getProjectClaimantMap();
    const knownProjects = getKnownProjectNames();
    const units = new Set();
    const othersProjectNames = new Set(['Others / Unassigned', 'Others / Unrelated', '__others__']);

    if (!Array.isArray(allDefects)) {
        return [];
    }

    // Build a set of known homeowner IDs from project_claimants_map
    const knownHomeownerIds = new Set();
    Object.values(map).forEach((list) => {
        if (Array.isArray(list)) {
            list.forEach((c) => {
                if (c && c.homeowner_id) knownHomeownerIds.add(String(c.homeowner_id));
            });
        }
    });

    allDefects.forEach((defect) => {
        const projectName = String(defect.project_name || '').trim();
        const unitName = String(defect.unit || '').trim();
        const ownerId = defect.owner_id != null ? String(defect.owner_id) : '';

        // Consider unassigned if:
        // - defect's project is explicitly Others/Unrelated
        // - OR defect's project is missing or unknown to the dashboard
        // AND the defect's owner is not a known claimant (no homeowner profile in map)
        const projectUnknown = !projectName || !knownProjects.has(projectName);
        const isOthers = othersProjectNames.has(projectName);

        if (unitName && (isOthers || (projectUnknown && !knownHomeownerIds.has(ownerId)))) {
            units.add(unitName);
        }
    });

    return Array.from(units).sort((left, right) => left.localeCompare(right));
}

function populateClaimantsForProject(projectName, preferredClaimantId = '') {
    const claimantSelect = document.getElementById('claimant-select');
    if (!claimantSelect) return;

    const claimantList = Array.isArray(getProjectClaimantMap()[projectName]) ? getProjectClaimantMap()[projectName] : [];
    claimantSelect.innerHTML = '';
    claimantSelect.disabled = false;

    if (!projectName) {
        claimantSelect.innerHTML = '<option value="">Choose project first</option>';
        const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
        if (pdfClaimantIdInput) {
            pdfClaimantIdInput.value = '';
        }
        return;
    }

    if (isOthersProject(projectName)) {
        // Prefer server-provided unassigned claimants (project_claimants_map['Others / Unrelated'])
        const serverUnassigned = Array.isArray(getProjectClaimantMap()[projectName]) ? getProjectClaimantMap()[projectName] : [];
        claimantSelect.disabled = false;

        if (serverUnassigned && serverUnassigned.length) {
            claimantSelect.innerHTML = '';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Choose unassigned unit';
            placeholder.selected = !preferredClaimantId;
            claimantSelect.appendChild(placeholder);

            serverUnassigned.forEach((claimant) => {
                const option = document.createElement('option');
                // For unassigned entries we use the unit as the option value
                const unitName = String(claimant.unit || claimant.homeowner_id || '').trim();
                option.value = unitName;
                option.textContent = unitName ? `Unit ${unitName}` : (claimant.name || 'Unnamed');
                if (String(preferredClaimantId) === unitName) {
                    option.selected = true;
                }
                claimantSelect.appendChild(option);
            });
        } else {
            // Fallback: scan defects on the page for unassigned units
            const unassignedUnits = getUnassignedDefectUnits();

            if (!unassignedUnits.length) {
                claimantSelect.innerHTML = '<option value="">No unassigned units available</option>';
            } else {
                claimantSelect.innerHTML = '';

                const placeholder = document.createElement('option');
                placeholder.value = '';
                placeholder.textContent = 'Choose unassigned unit';
                placeholder.selected = !preferredClaimantId;
                claimantSelect.appendChild(placeholder);

                unassignedUnits.forEach((unitName) => {
                    const option = document.createElement('option');
                    option.value = unitName;
                    option.textContent = `Unit ${unitName}`;
                    if (String(preferredClaimantId) === unitName) {
                        option.selected = true;
                    }
                    claimantSelect.appendChild(option);
                });
            }
        }

        const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
        if (pdfClaimantIdInput) {
            pdfClaimantIdInput.value = '';
        }
        return;
    }

    if (!claimantList.length) {
        claimantSelect.innerHTML = '<option value="">No claimant / no defects for selected project</option>';
    } else {
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Choose claimant';
        placeholder.selected = !preferredClaimantId;
        claimantSelect.appendChild(placeholder);

        claimantList.forEach((claimant) => {
            const option = document.createElement('option');
            option.value = claimant.homeowner_id;
            // claimant.name is already formatted as "Name(Unit)" by the backend.
            // Show the unit in the selector; keep the homeowner_id as the value.
            option.textContent = claimant.unit || claimant.name || `Unit ${claimant.homeowner_id}`;
            if (String(preferredClaimantId) && String(preferredClaimantId) === String(claimant.homeowner_id)) {
                option.selected = true;
            }
            claimantSelect.appendChild(option);
        });
    }

    const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
    if (pdfClaimantIdInput) {
        pdfClaimantIdInput.value = claimantSelect.value || '';
    }
}

function handleProjectChange() {
    const projectSelect = document.getElementById('project-select');
    const claimantSelect = document.getElementById('claimant-select');
    const projectName = projectSelect ? projectSelect.value : '';
    const defaultClaimantId = '';
    populateClaimantsForProject(projectName, defaultClaimantId);
    if (claimantSelect && claimantSelect.options.length) {
        const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
        if (pdfClaimantIdInput) pdfClaimantIdInput.value = claimantSelect.value || '';
    }
    const pdfProjectName = document.getElementById('pdf-project-name');
    if (pdfProjectName) pdfProjectName.value = projectName;
    invalidateReportExport();
    if (typeof applyFilters === 'function') {
        applyFilters();
    }
}

/**
 * Escapes HTML special characters in a string.
 * @param {any} value The value to escape.
 * @returns {string} The escaped string.
 */
function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeRegExp(value) {
    return String(value ?? '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const REPORT_DETAIL_LABELS = [
    'Description',
    'Keterangan',
    'Unit',
    'Reported Date',
    'Tarikh Dilaporkan',
    'Scheduled Completion Date',
    'Tarikh Siap Dijadualkan',
    'Actual Completion Date',
    'Completed',
    'Tarikh Siap Sebenar',
    'Tarikh Siap',
    'Days to Complete',
    'Tempoh Siap (Hari)',
    'Status',
    'Current Status',
    'Status Semasa',
    'Overdue Status',
    'Status Tertunggak',
    'HDA Compliance (30 Days)',
    'HDA Compliance Status',
    'Pematuhan HDA (30 Hari)',
    'Status Pematuhan HDA',
    'Priority',
    'Keutamaan',
    'Remarks',
    'Ulasan',
    'Closed Rule',
    'Peraturan Ditutup',
    'Defect Image',
    'Gambar Kecacatan',
    'Uploaded',
    'Muat Naik',
];

function hideEncryptedFragments(value) {
    return String(value ?? '').replace(/gAAAA[A-Za-z0-9_\-=]+/g, '[Encrypted data unavailable]');
}

function preserveLeadingSpaces(value) {
    return String(value ?? '').replace(/^( +)/, (match) => '&nbsp;'.repeat(match.length));
}

function normalizeDefectDetailIndentation(value) {
    let text = String(value ?? '')
        .replace(/(?<!\n)\n(?=[ \t]*(?:[a-z]|[A-Z])\.\s+(?:Defect ID|Kecacatan ID)\b)/g, '\n\n')
        .replace(/^[ \t]*(Peraturan Ditutup\s*:)\s*\n[ \t]*(Ditutup selepas[^\n]*)$/gim, '$1 $2')
        .replace(/^[ \t]*(Closed Rule\s*:)\s*\n[ \t]*(Closed after[^\n]*)$/gim, '$1 $2');

    const escapedLabels = REPORT_DETAIL_LABELS.map(escapeRegExp).join('|');
    const detailLinePattern = new RegExp(`^[ \\t]*(${escapedLabels}\\s*:)`, 'gim');
    return text.replace(detailLinePattern, '   $1');
}

function normalizePriorityValuesForLanguage(value, language) {
    const isMalay = ['ms', 'bm', 'malay', 'melayu'].includes(String(language || '').toLowerCase());
    const replacements = isMalay
        ? { high: 'Tinggi', medium: 'Sederhana', low: 'Rendah' }
        : { tinggi: 'High', sederhana: 'Medium', rendah: 'Low' };
    const labelPattern = isMalay ? '(Keutamaan\\s*:\\s*)' : '(Priority\\s*:\\s*)';
    const valuePattern = isMalay ? '(high|medium|low)' : '(tinggi|sederhana|rendah)';
    const priorityPattern = new RegExp(`^\\s*${labelPattern}${valuePattern}\\s*$`, 'gim');

    return String(value ?? '').replace(priorityPattern, (_match, label, rawValue) => {
        const normalized = replacements[String(rawValue || '').trim().toLowerCase()] || String(rawValue || '').trim();
        return `${label.trim()} ${normalized}`;
    });
}

function normalizeHdaComplianceValues(value, language) {
    const isMalay = ['ms', 'bm', 'malay', 'melayu'].includes(String(language || '').toLowerCase());
    const targetLabel = isMalay ? 'Status Pematuhan HDA' : 'HDA Compliance Status';
    const sourceLabels = [
        'HDA Compliance (30 Days)',
        'HDA Compliance Status',
        'Pematuhan HDA (30 Hari)',
        'Status Pematuhan HDA',
    ].map(escapeRegExp).join('|');

    const valueMap = isMalay
        ? {
            yes: 'Mematuhi',
            ya: 'Mematuhi',
            compliant: 'Mematuhi',
            mematuhi: 'Mematuhi',
            no: 'Tidak Mematuhi',
            tidak: 'Tidak Mematuhi',
            'non-compliant': 'Tidak Mematuhi',
            'tidak mematuhi': 'Tidak Mematuhi',
            pending: 'Tidak Mematuhi',
            'under review': 'Tidak Mematuhi',
            'dalam semakan': 'Tidak Mematuhi',
        }
        : {
            yes: 'Compliant',
            ya: 'Compliant',
            compliant: 'Compliant',
            mematuhi: 'Compliant',
            no: 'Non-Compliant',
            tidak: 'Non-Compliant',
            'non-compliant': 'Non-Compliant',
            'tidak mematuhi': 'Non-Compliant',
            pending: 'Non-Compliant',
            'under review': 'Non-Compliant',
            'dalam semakan': 'Non-Compliant',
        };

    const hdaPattern = new RegExp(`^([ \\t]*)(${sourceLabels})\\s*:\\s*(.+?)\\s*$`, 'gim');
    return String(value ?? '').replace(hdaPattern, (_match, indent, _label, rawValue) => {
        const normalized = String(rawValue || '').trim().toLowerCase();
        const fieldIndent = indent || '   ';
        return `${fieldIndent}${targetLabel}: ${valueMap[normalized] || rawValue.trim()}`;
    });
}

function normalizeOverdueStatusValues(value, language) {
    const isMalay = ['ms', 'bm', 'malay', 'melayu'].includes(String(language || '').toLowerCase());
    const targetLabel = isMalay ? 'Status Tertunggak' : 'Overdue Status';
    const sourceLabels = ['Overdue Status', 'Status Tertunggak'].map(escapeRegExp).join('|');
    const valueMap = isMalay
        ? {
            yes: 'Tertunggak',
            ya: 'Tertunggak',
            overdue: 'Tertunggak',
            tertunggak: 'Tertunggak',
            no: 'Tidak Tertunggak',
            tidak: 'Tidak Tertunggak',
            'not overdue': 'Tidak Tertunggak',
            'tidak tertunggak': 'Tidak Tertunggak',
        }
        : {
            yes: 'Overdue',
            ya: 'Overdue',
            overdue: 'Overdue',
            tertunggak: 'Overdue',
            no: 'Not Overdue',
            tidak: 'Not Overdue',
            'not overdue': 'Not Overdue',
            'tidak tertunggak': 'Not Overdue',
        };

    const overduePattern = new RegExp(`^([ \\t]*)(${sourceLabels})\\s*:\\s*(.+?)\\s*$`, 'gim');
    return String(value ?? '').replace(overduePattern, (_match, indent, _label, rawValue) => {
        const normalized = String(rawValue || '').trim().toLowerCase();
        return `${indent}${targetLabel}: ${valueMap[normalized] || rawValue.trim()}`;
    });
}

function normalizeReportSectionSpacing(value) {
    return String(value ?? '')
        .replace(/\r\n/g, '\n')
        .replace(/\r/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/\n(?!\n)(?=\s*\d+\.\s+)/g, '\n\n')
        .replace(/\n(?!\n)(?=\s*(?:AI\s+DISCLAIMER|PENAFIAN\s+AI)\s*:)/gi, '\n\n')
        .replace(/^(\d+\.\s+[^\n]+)\n(?!\n)/gm, '$1\n\n')
        .replace(/^((?:AI\s+DISCLAIMER|PENAFIAN\s+AI)\s*:)\n(?!\n)/gim, '$1\n\n')
        .replace(
            /\n+\s*(?=(?:1\.\s+Tujuan\s+Laporan|1\.\s+Purpose\s+of\s+the\s+Report|1\.\s+Latar\s+Belakang\s+Kes|1\.\s+Case\s+Background|5\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+Tempoh|5\.\s+Observations\s+on\s+Timeframe\s+Compliance|4\.\s+Pemerhatian\s+Berkaitan\s+Pematuhan\s+dan\s+Tarikh\s+Akhir|3\.\s+Pemerhatian\s+Berkaitan\s+Status\s+dan\s+Tempoh|3\.\s+Recorded\s+Status\s+and\s+Timeframe\s+Observations)\s*$)/gim,
            '\n\n\n'
        );
}

function normalizeLegalStatisticsSection(value) {
    let text = String(value ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    text = text.replace(
        /(2\.\s*Kedudukan Statistik Rekod Kecacatan\s*\n+)\s*Jumlah keseluruhan kecacatan:\s*(\d+)\.?\s*Telah diselesaikan:\s*(\d+)\.?\s*(?:Kes Ditutup:\s*(\d+)\.?\s*)?Masih belum diselesaikan:\s*(\d+)\.?\s*Direkodkan sebagai\s+tertunggak:\s*(\d+)\.?\s*Tidak mematuhi tempoh 30 hari HDA:\s*(\d+)\.?/gis,
        (_match, heading, total, completed, closed, pending, overdue, hda) => (
            `${heading}Jumlah keseluruhan kecacatan: ${total}\n` +
            `Telah diselesaikan: ${completed}\n` +
            `Kes Ditutup: ${closed || '0'}\n` +
            `Masih belum diselesaikan: ${pending}\n` +
            `Direkodkan sebagai tertunggak: ${overdue}\n` +
            `Tidak mematuhi tempoh 30 hari HDA: ${hda}\n\n`
        )
    );

    text = text.replace(
        /(2\.\s*Statistical Position of Defect Records\s*\n+)\s*Total recorded defects:\s*(\d+)\.?\s*Completed:\s*(\d+)\.?\s*(?:Closed Cases:\s*(\d+)\.?\s*)?Still unresolved:\s*(\d+)\.?\s*Recorded as overdue:\s*(\d+)\.?\s*Non-compliant with 30-day HDA requirement:\s*(\d+)\.?/gis,
        (_match, heading, total, completed, closed, pending, overdue, hda) => (
            `${heading}Total recorded defects: ${total}\n` +
            `Completed: ${completed}\n` +
            `Closed Cases: ${closed || '0'}\n` +
            `Still unresolved: ${pending}\n` +
            `Recorded as overdue: ${overdue}\n` +
            `Non-compliant with 30-day HDA requirement: ${hda}\n\n`
        )
    );

    return text;
}

function renderReportPreviewBody(value) {
    let inLegalStatisticsSection = false;
    const reportDetailLinePattern = new RegExp(
        `^(\\s*)(${REPORT_DETAIL_LABELS.map(escapeRegExp).join('|')})\\s*:\\s*(.*)$`,
        'i'
    );
    const legalStatisticLabels = [
        'Total recorded defects',
        'Completed',
        'Closed Cases',
        'Still unresolved',
        'Recorded as overdue',
        'Non-compliant with 30-day HDA requirement',
        'Jumlah keseluruhan kecacatan',
        'Telah diselesaikan',
        'Kes Ditutup',
        'Masih belum diselesaikan',
        'Direkodkan sebagai tertunggak',
        'Tidak mematuhi tempoh 30 hari HDA',
    ];
    const legalStatisticLinePattern = new RegExp(
        `^\\s*(?:${legalStatisticLabels.map(escapeRegExp).join('|')})\\s*:\\s*.+$`,
        'i'
    );

    return String(value ?? '')
        .split('\n')
        .map((line) => {
            if (!line.trim()) {
                return '<div class="preview-line empty">&nbsp;</div>';
            }

            // Match PDF bolding: full-line report headers only. Field labels
            // such as "Description:" / "Keterangan:" remain regular.
            const pdfBoldLinePatterns = [
                /^\s*PENAFIAN\s+AI[:\s]*$/i,
                /^\s*AI\s+DISCLAIMER[:\s]*$/i,
                /^\s*LAMPIRAN\s+A[:\s]/i,
                /^\s*APPENDIX\s+A[:\s]/i,
                /^\s*BUTIRAN\s+KES\s+DITUTUP\b/i,
                /^\s*CLOSED\s+CASE\s+DETAILS\b/i,
                /^\s*MAKLUMAT\s+PEMILIK\s+MENUNTUT[:\s]/i,
                /^\s*REKOD\s+KES\s+DITUTUP\s+PEMILIK\s+MENUNTUT[:\s]/i,
                /^\s*CLAIMANT\s+OWNER\s+DETAILS[:\s]/i,
                /^\s*CLAIMANT\s+OWNER\s+CLOSED\s+CASE\s+RECORDS[:\s]/i,
                /^\s*SENARAI\s+KECACATAN\s+PEMILIK\s+MENUNTUT[:\s]/i,
                /^\s*CLAIMANT\s+OWNER\s+DEFECT\s+LIST[:\s]/i,
                /^\s*MAKLUMAT\s+PEMILIK\s+LAIN[:\s]/i,
                /^\s*REKOD\s+KES\s+DITUTUP\s+PEMILIK\s+LAIN[:\s]/i,
                /^\s*OTHER\s+OWNER\s+DETAILS[:\s]/i,
                /^\s*OTHER\s+OWNER\s+CLOSED\s+CASE\s+RECORDS[:\s]/i,
                /^\s*SENARAI\s+KECACATAN\s+PEMILIK\s+LAIN[:\s]/i,
                /^\s*OTHER\s+OWNER\s+DEFECT\s+LIST[:\s]/i,
                /^\s*KECACATAN\s+BERKAITAN\s+PIHAK\s+YANG\s+MENUNTUT[:\s]/i,
                /^\s*DEFECTS\s+RELATED\s+TO\s+CLAIMANT[:\s]/i,
                /^\s*KECACATAN\s+LAIN\s+DALAM\s+KES[:\s]/i,
                /^\s*OTHER\s+DEFECTS\s+IN\s+CASE[:\s]/i,
                /^\s*LAPORAN\s+SOKONGAN\s+(BAGI|TRIBUNAL)\b/i,
                /^\s*LAPORAN\s+PEMATUHAN\s+BAGI\b/i,
                /^\s*LAPORAN\s+GAMBARAN\s+KESELURUHAN\b/i,
                /^\s*TRIBUNAL\s+SUPPORT\s+REPORT\b/i,
            ];

            // Bold main numbered headers (e.g., "1. Tujuan Laporan") and keep same indent
            const numberedHeaderMatch = line.match(/^(\s*)(\d+\.\s+)(.+)$/);
            if (numberedHeaderMatch) {
                const headerText = numberedHeaderMatch[3].trim();
                inLegalStatisticsSection = /^(Statistical Position of Defect Records|Kedudukan Statistik Rekod Kecacatan)$/i.test(headerText);
                const leading = '&nbsp;'.repeat(numberedHeaderMatch[1].length);
                const numberPart = escapeHtml(numberedHeaderMatch[2]);
                const rest = escapeHtml(numberedHeaderMatch[3]);
                // Bold the entire numbered header (number + text)
                return `\n                    <div class="preview-line hanging">\n                        <span class="preview-label">${leading}<strong>${numberPart}${rest}</strong></span>\n                    </div>\n                `.trim();
            }

            const letteredHeaderMatch = line.match(/^(\s*)([a-z]\.\s+)(.+)$/i);
            if (letteredHeaderMatch) {
                const leading = '&nbsp;'.repeat(letteredHeaderMatch[1].length);
                return `<div class="preview-line header">${leading}<strong>${escapeHtml(letteredHeaderMatch[2])}${escapeHtml(letteredHeaderMatch[3])}</strong></div>`;
            }

            const isPdfBoldLine = pdfBoldLinePatterns.some((p) => p.test(line));
            if (isPdfBoldLine) {
                const appendixMainHeader = /^\s*(APPENDIX\s+A|LAMPIRAN\s+A)\s*:/i.test(line);
                const ownerHeader = /^\s*(CLAIMANT\s+OWNER\s+DETAILS|CLAIMANT\s+OWNER\s+CLOSED\s+CASE\s+RECORDS|OTHER\s+OWNER\s+DETAILS|OTHER\s+OWNER\s+CLOSED\s+CASE\s+RECORDS|MAKLUMAT\s+PEMILIK\s+MENUNTUT|REKOD\s+KES\s+DITUTUP\s+PEMILIK\s+MENUNTUT|MAKLUMAT\s+PEMILIK\s+LAIN|REKOD\s+KES\s+DITUTUP\s+PEMILIK\s+LAIN)\s*:/i.test(line);
                const defectListHeader = /^\s*(CLAIMANT\s+OWNER\s+DEFECT\s+LIST|OTHER\s+OWNER\s+DEFECT\s+LIST|SENARAI\s+KECACATAN\s+PEMILIK\s+MENUNTUT|SENARAI\s+KECACATAN\s+PEMILIK\s+LAIN)\s*:/i.test(line);
                const extraClass = appendixMainHeader
                    ? ' appendix-main'
                    : ownerHeader
                        ? ' appendix-owner'
                        : defectListHeader
                            ? ' appendix-list'
                            : '';
                return `<div class="preview-line header${extraClass}">${preserveLeadingSpaces(escapeHtml(line))}</div>`;
            }

            if (inLegalStatisticsSection && legalStatisticLinePattern.test(line)) {
                const statisticMatch = line.match(/^(\s*)([^:]+)\s*:\s*(.+)$/);
                if (statisticMatch) {
                    const leading = '&nbsp;'.repeat(statisticMatch[1].length);
                    return `
                        <div class="preview-line field-row legal-stat-row">
                            <span class="preview-indent">${leading}</span><span class="preview-field-label">${escapeHtml(statisticMatch[2].trim())}</span><span class="preview-field-colon">:</span><span class="preview-field-value">${escapeHtml(statisticMatch[3].trim())}</span>
                        </div>
                    `.trim();
                }
                return `<div class="preview-line">${escapeHtml(line.trim())}</div>`;
            }

            const detailMatch = line.match(reportDetailLinePattern);
            if (detailMatch) {
                const leading = '&nbsp;'.repeat(detailMatch[1].length);
                const labelText = detailMatch[2];
                const valueText = detailMatch[3];
                if (!valueText.trim() && /^(Defect Image|Gambar Kecacatan)$/i.test(labelText)) {
                    return `
                        <div class="preview-line field-row image-label-row">
                            <span class="preview-indent">${leading}</span><span class="preview-field-label">${escapeHtml(labelText)}:</span>
                        </div>
                    `.trim();
                }
                return `
                    <div class="preview-line field-row">
                        <span class="preview-indent">${leading}</span><span class="preview-field-label">${escapeHtml(labelText)}</span><span class="preview-field-colon">:</span><span class="preview-field-value">${escapeHtml(valueText)}</span>
                    </div>
                `.trim();
            }

            const match = line.match(/^(\s*)([^:]{1,90}:\s+)(.+)$/);
            if (match) {
                const leading = '&nbsp;'.repeat(match[1].length);
                const labelText = match[2].replace(/:\s*$/, '');
                const valueText = match[3];
                return `
                    <div class="preview-line field-row">
                        <span class="preview-indent">${leading}</span><span class="preview-field-label">${escapeHtml(labelText)}</span><span class="preview-field-colon">:</span><span class="preview-field-value">${escapeHtml(valueText)}</span>
                    </div>
                `.trim();
            }

            return `<div class="preview-line">${preserveLeadingSpaces(escapeHtml(line))}</div>`;
        })
        .join('');
}

function scrubEncryptedFragmentsInDefects(defects) {
    if (!Array.isArray(defects)) return;
    defects.forEach((defect) => {
        ['unit', 'desc', 'status', 'display_status', 'original_status', 'remarks', 'deadline'].forEach((key) => {
            if (Object.prototype.hasOwnProperty.call(defect, key)) {
                defect[key] = hideEncryptedFragments(defect[key]);
            }
        });
    });
}

/**
 * Renders the missing data panel with details about what's missing.
 * @param {object|null} missingData The missing data object from the backend.
 */
function renderMissingDataPanel(missingData) {
    const panel = document.getElementById('missing-data-panel');
    const summary = document.getElementById('missing-data-summary');
    const scroll = document.getElementById('missing-data-scroll');
    if (!panel || !summary || !scroll) return;

    if (!missingData || !Object.keys(missingData).length) {
        panel.style.display = 'none';
        summary.innerHTML = '';
        scroll.innerHTML = '';
        return;
    }

    const caseInfo = Array.isArray(missingData?.case_info) ? missingData.case_info : [];
    const claimant = Array.isArray(missingData?.claimant) ? missingData.claimant : [];
    const respondent = Array.isArray(missingData?.respondent) ? missingData.respondent : [];
    const defects = Array.isArray(missingData?.defects) ? missingData.defects : [];
    const defectCount = defects.reduce((count, defect) => count + (Array.isArray(defect.missing) ? defect.missing.length : 0), 0);
    const total = caseInfo.length + claimant.length + respondent.length + defectCount;

    if (!total) {
        panel.style.display = 'none';
        summary.innerHTML = '';
        scroll.innerHTML = '';
        return;
    }

    panel.style.display = 'block';
    summary.innerHTML = `
        <div class="summary-chip">Total missing<strong>${total}</strong></div>
        <div class="summary-chip">Case info<strong>${caseInfo.length}</strong></div>
        <div class="summary-chip">Claimant<strong>${claimant.length}</strong></div>
        <div class="summary-chip">Respondent<strong>${respondent.length}</strong></div>
        <div class="summary-chip">Defects<strong>${defectCount}</strong></div>
    `;

    const groups = [];
    if (caseInfo.length) groups.push({ title: 'Case Information', items: caseInfo });
    if (claimant.length) groups.push({ title: 'Claimant Information', items: claimant });
    if (respondent.length) groups.push({ title: 'Respondent Information', items: respondent });
    if (defects.length) groups.push({ title: 'Defect Records', items: defects });

    scroll.innerHTML = groups.map((group) => {
        const itemsHtml = group.title === 'Defect Records'
            ? group.items.map((defect) => {
                const lines = Array.isArray(defect.missing) ? defect.missing.map((item) => `<li>${escapeHtml(item.label)}</li>`).join('') : '';
                return `<div class="missing-data-group"><h3>Defect ${escapeHtml(defect.defect_id)}</h3><ul class="missing-data-list">${lines}</ul></div>`;
            }).join('')
            : `<ul class="missing-data-list">${group.items.map((item) => `<li>${escapeHtml(item.label)}</li>`).join('')}</ul>`;

        return `<div class="missing-data-group"><h3>${escapeHtml(group.title)}</h3>${itemsHtml}</div>`;
    }).join('');
}

/**
 * Render a simple table listing defects missing evidence.
 * @param {Array<{id:number,unit:string}>} missingList
 */
function renderMissingEvidenceTable(missingList) {
    const panel = document.getElementById('missing-data-panel');
    const summary = document.getElementById('missing-data-summary');
    const scroll = document.getElementById('missing-data-scroll');
    if (!panel || !summary || !scroll) return;

    if (!Array.isArray(missingList) || missingList.length === 0) {
        panel.style.display = 'none';
        summary.innerHTML = '';
        scroll.innerHTML = '';
        return;
    }

    panel.style.display = 'block';
    summary.innerHTML = `<div class="summary-chip">Missing Evidence<strong>${missingList.length}</strong></div>`;

    // Build table similar to defect listing (ID, Unit, Action)
    const rows = missingList.map(item => {
        const id = escapeHtml(item.id || item.defect_id || '');
        const unit = escapeHtml(item.unit || '');
        const count = Number(item.evidence_count || 0);
        const required = Number(item.required_count || 3);
        return `<tr><td>#${id}</td><td>${unit}</td><td>${count}/${required} images</td><td><button class="btn btn-secondary" onclick="document.getElementById('file-${id}') && document.getElementById('file-${id}').click()">Upload 3 Images</button></td></tr>`;
    }).join('');

    scroll.innerHTML = `
        <div class="missing-data-group">
            <h3>Defects Missing Evidence</h3>
            <div style="overflow:auto; max-height:320px;">
                <table class="missing-evidence-table" style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr><th style="text-align:left; padding:8px;">ID</th><th style="text-align:left; padding:8px;">Unit</th><th style="text-align:left; padding:8px;">Evidence</th><th style="text-align:left; padding:8px;">Action</th></tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

/**
 * Updates the summary cards with statistics from the provided data.
 * @param {object[]} data The array of defect data to calculate statistics from.
 */
function updateSummaryCards(data) {
    const stats = {
        total: data.length,
        pending: data.filter(d => d.status === 'Pending').length,
        investigation: data.filter(d => d.status === 'In Progress').length,
        delayed: data.filter(d => d.status === 'Delayed').length,
        overdue: data.filter(d => d.is_overdue).length,
        completed: data.filter(d => d.status === 'Completed' && !d.closed).length,
        closed: data.filter(d => d.closed).length
    };

    // Update all summary card values in order: Total, Pending, In Progress, Delayed, Overdue, Completed, Closed
    document.querySelectorAll('.summary-card .value').forEach((elem, idx) => {
        const values = [stats.total, stats.pending, stats.investigation, stats.delayed, stats.overdue, stats.completed, stats.closed];
        elem.textContent = values[idx] || '0';
    });
}

/**
 * Applies filters to the defect table based on user selection.
 */
function applyFilters() {
    scrubEncryptedFragmentsInDefects(allDefects);
    const statusElement = document.getElementById('filter-status');
    const unitElement = document.getElementById('filter-unit');
    const statusFilter = statusElement ? statusElement.value : '';
    const unitFilter = unitElement ? unitElement.value : '';
    const projectSelect = document.getElementById('project-select');
    const claimantSelect = document.getElementById('claimant-select');
    const projectFilter = projectSelect ? projectSelect.value : '';
    const claimantFilter = claimantSelect ? claimantSelect.value : '';
    const othersSelected = isOthersProject(projectFilter);
    const knownProjects = getKnownProjectNames();

    if (projectSelect && !projectFilter) {
        const tbody = document.getElementById('defect-table-body');
        if (tbody) {
            const table = document.querySelector('table');
            const columnCount = table ? table.querySelectorAll('thead th').length : 7;
            tbody.innerHTML = `<tr><td colspan="${columnCount}" style="text-align:center; color: var(--muted); padding: 2rem;">Choose a project to view related defects.</td></tr>`;
        }
        updateSummaryCards([]);
        return;
    }

    const filtered = allDefects.filter(defect => {
        const statusMatch = !statusFilter || defect.display_status === statusFilter;
        const unitMatch = !unitFilter || defect.unit === unitFilter;
        const projectName = String(defect.project_name || '').trim();
        const claimantSelected = Boolean(claimantFilter);

        // When 'Others' is selected we normally show defects with no/unknown
        // project. However, if a specific unassigned claimant (unit) is
        // selected, we should also include defects that match that unit even
        // if the defect has a project_name set. This allows 'Others /
        // Unrelated' to surface defects belonging to unassigned units.
        let projectMatch;
        if (othersSelected) {
            if (claimantFilter) {
                projectMatch = true; // let claimant/unit selection determine inclusion
            } else {
                projectMatch = (!projectName || !knownProjects.has(projectName));
            }
        } else {
            projectMatch = (!projectFilter || projectName === projectFilter);
            if (claimantSelected) {
                // Some claimant rows are grouped by state label while defects
                // resolve to the underlying project label, so do not block a
                // claimant-owned defect just because the project names differ.
                projectMatch = true;
            }
        }

        const claimantMatch = othersSelected
            ? (!claimantFilter || String(defect.unit || '').trim() === String(claimantFilter).trim())
            : (!claimantFilter || String(defect.owner_id) === String(claimantFilter));

        return statusMatch && unitMatch && projectMatch && claimantMatch;
    });

    populateTable(filtered);
}

/**
 * Resets all filters and repopulates the table with all defects.
 */
function resetFilters() {
    scrubEncryptedFragmentsInDefects(allDefects);
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-unit').value = '';
    applyFilters();
}

// Initialize table on page load
document.addEventListener('DOMContentLoaded', () => {
    const projectSelect = document.getElementById('project-select');
    if (projectSelect) {
        const defaults = getDashboardDefaults();
        const initialProject = defaults.project || '';
        projectSelect.value = initialProject;
        populateClaimantsForProject(initialProject, defaults.claimant || '');
        const pdfProjectName = document.getElementById('pdf-project-name');
        if (pdfProjectName) pdfProjectName.value = initialProject;
    }

    const claimantSelect = document.getElementById('claimant-select');
    if (claimantSelect) {
        const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
        if (pdfClaimantIdInput) pdfClaimantIdInput.value = claimantSelect.value || '';
        claimantSelect.addEventListener('change', () => {
            if (typeof applyFilters === 'function') {
                applyFilters();
            }
        });
    }

    if (typeof populateTable === 'function' && typeof allDefects !== 'undefined') {
        applyFilters();
    }
});

/**
 * Generates an AI-assisted report by fetching data from the backend.
 * @param {string} role The role of the user generating the report (e.g., 'Homeowner', 'Developer').
 */
function generateReport(role) {
    const reportOutput = document.getElementById('report-output');
    const reportJson = document.getElementById('report-json');
    const language = document.getElementById('language-select').value;
    if (!language) {
        showToast('Please select a language before generating report.', 'warning');
        return;
    }

    invalidateReportExport();
    document.getElementById('pdf-language').value = language;
    const projectSelect = document.getElementById('project-select');
    const projectName = projectSelect ? projectSelect.value : '';
    if (projectSelect && !projectName) {
        showToast('Please choose a project before generating report.', 'warning');
        if (reportOutput) reportOutput.style.display = 'block';
        if (reportJson) reportJson.innerText = 'Please choose a project first.';
        return;
    }
    if (isOthersProject(projectName)) {
        showToast('Report generation is not available for Others / Unassigned. Choose a specific project.', 'warning');
        if (reportOutput) reportOutput.style.display = 'block';
        if (reportJson) reportJson.innerText = 'Please choose a specific project to generate report.';
        return;
    }
    const pdfProjectName = document.getElementById('pdf-project-name');
    if (pdfProjectName) pdfProjectName.value = projectName;
    if (reportOutput) reportOutput.style.display = 'block';
    if (reportJson) reportJson.innerText = 'Generating report...';

    const payload = { role, language };
    if (projectName) {
        payload.project_name = projectName;
    }

    const claimantSelect = document.getElementById('claimant-select');
    if (claimantSelect) {
        const claimantUserId = claimantSelect.value;
        if (!claimantUserId) {
            showToast('Please choose a claimant before generating report.', 'warning');
            if (reportOutput) reportOutput.style.display = 'block';
            if (reportJson) reportJson.innerText = 'Please choose a claimant first.';
            return;
        }
        payload.claimant_user_id = claimantUserId;
        const pdfClaimantIdInput = document.getElementById('pdf-claimant-user-id');
        if (pdfClaimantIdInput) {
            pdfClaimantIdInput.value = claimantUserId;
        }
    }

    const requestTimeoutMs = Number(window.AI_REPORT_TIMEOUT_MS) || 180000;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), requestTimeoutMs);

    fetch('/generate_ai_report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
    })
    .then(async res => {
        let data = {};
        try {
            data = await res.json();
        } catch (error) {
            data = { error: 'Invalid server response.' };
        }
        if (!res.ok && !data.error) {
            data.error = `Request failed with status ${res.status}.`;
        }
        return data;
    })
    .then(data => {
        clearTimeout(timeoutId);
        if (data.error) {
            showToast(data.error, 'error');
            if (reportJson) reportJson.innerText = formatReportError(data.details || data.error);
            // If backend returned missing_evidence, render a table for uploads
            if (Array.isArray(data.missing_evidence) && data.missing_evidence.length) {
                renderMissingEvidenceTable(data.missing_evidence);
            } else {
                renderMissingDataPanel(data.missing_data);
            }
            return;
        }
        if (!data.report || data.report.trim() === '') {
            showToast('Report is empty. Check if defects have required data.', 'warning');
            if (reportJson) reportJson.innerText = 'No report data available.';
            renderMissingDataPanel(null);
            return;
        }
        const reportText = hideEncryptedFragments(data.report);
        const reportLanguage = document.getElementById('language-select').value || 'ms';
        const generatedAt = data.generated_at || '';
        const canonicalTitles = {
            ms: {
                ai: 'LAPORAN RINGKASAN TUNTUTAN DIJANA AI',
                tribunal: 'LAPORAN SOKONGAN TRIBUNAL – TEMPOH LIABILITI KECACATAN (DLP)',
                homeowner: 'Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)',
                developer: 'Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)',
                legal: 'Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)',
            },
            en: {
                ai: 'AI-GENERATED CLAIM SUMMARY REPORT',
                tribunal: 'TRIBUNAL SUPPORT REPORT – DEFECT LIABILITY PERIOD (DLP)',
                homeowner: 'Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)',
                developer: 'Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)',
                legal: 'Overview Report on Defect Liability Period (DLP) Compliance',
            },
        };
        const headerLabels = canonicalTitles[reportLanguage] || canonicalTitles.ms;
        const roleKey = String(role || '').toLowerCase();
        const roleReportTitles = {
            ms: {
                homeowner: 'LAPORAN SOKONGAN TRIBUNAL - TEMPOH LIABILITI KECACATAN (DLP)',
                developer: 'LAPORAN PEMATUHAN RESPONDEN - TEMPOH LIABILITI KECACATAN (DLP)',
                legal: 'LAPORAN RUJUKAN TRIBUNAL - TEMPOH LIABILITI KECACATAN (DLP)',
            },
            en: {
                homeowner: 'TRIBUNAL SUPPORT REPORT - DEFECT LIABILITY PERIOD (DLP)',
                developer: 'RESPONDENT COMPLIANCE REPORT - DEFECT LIABILITY PERIOD (DLP)',
                legal: 'TRIBUNAL REFERENCE REPORT - DEFECT LIABILITY PERIOD (DLP)',
            },
        };
        const canonicalSubtitle = headerLabels[roleKey] || headerLabels.homeowner;
        const titleLabels = roleReportTitles[reportLanguage] || roleReportTitles.ms;
        const tribunalTitle = titleLabels[roleKey] || titleLabels.homeowner;
        const generatedLabel = reportLanguage === 'ms' ? 'Tarikh Jana' : 'Generated Date';

        let bodyText = normalizePriorityValuesForLanguage(reportText, reportLanguage);
        const knownHeaderLines = new Set([
            headerLabels.ai,
            headerLabels.tribunal,
            tribunalTitle,
            canonicalSubtitle,
            ...Object.values(roleReportTitles.ms),
            ...Object.values(roleReportTitles.en),
            ...['homeowner', 'developer', 'legal'].map((key) => canonicalTitles.ms[key]),
            ...['homeowner', 'developer', 'legal'].map((key) => canonicalTitles.en[key]),
        ].filter(Boolean).map((item) => String(item).trim().toLowerCase()));
        const bodyLines = bodyText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
        while (bodyLines.length) {
            const candidate = String(bodyLines[0] || '').trim();
            const normalized = candidate.toLowerCase();
            if (!candidate || knownHeaderLines.has(normalized) || /^(tarikh jana|generated date)\s*:/i.test(candidate)) {
                bodyLines.shift();
                continue;
            }
            break;
        }
        bodyText = normalizeLegalStatisticsSection(bodyLines.join('\n').trim());
        bodyText = normalizeOverdueStatusValues(bodyText, reportLanguage);
        bodyText = normalizeHdaComplianceValues(bodyText, reportLanguage);
        bodyText = normalizeReportSectionSpacing(bodyText);
        bodyText = normalizePriorityValuesForLanguage(bodyText, reportLanguage);
        bodyText = normalizeOverdueStatusValues(bodyText, reportLanguage);
        bodyText = normalizeHdaComplianceValues(bodyText, reportLanguage);
        bodyText = normalizeDefectDetailIndentation(bodyText);

        // Render the preview with the canonical header structure matching PDF format
        if (reportJson) {
            const previewBodyHtml = renderReportPreviewBody(bodyText);
            reportJson.innerHTML = `
                <div class="report-header report-header-${escapeHtml(reportLanguage)}">
                    <div class="report-title">${escapeHtml(headerLabels.ai)}</div>
                    ${tribunalTitle ? `<div class="report-subtitle">${escapeHtml(tribunalTitle)}</div>` : ''}
                    ${generatedAt ? `<div class="report-meta">${escapeHtml(generatedLabel)}: ${escapeHtml(generatedAt)}</div>` : ''}
                    <div class="report-role-title">${escapeHtml(canonicalSubtitle)}</div>
                </div>
                <div class="report-content">${previewBodyHtml}</div>
            `;
        }
        
        // Store full report for PDF export using the canonical header text
        document.getElementById('pdf-ai-report').value = [
            headerLabels.ai,
            '',
            tribunalTitle,
            generatedAt ? `${generatedLabel}: ${generatedAt}` : '',
            '',
            canonicalSubtitle,
            '',
            bodyText,
        ].filter((item, index) => item || index === 1 || index === 4 || index === 6).join('\n').trim();
        document.getElementById('export-btn').disabled = false;
        renderMissingDataPanel(null);
        showToast('✓ Report generated successfully!', 'success');
    })
    .catch((error) => {
        clearTimeout(timeoutId);
        const timedOut = error && error.name === 'AbortError';
        const message = timedOut
            ? 'Report generation timed out. Please try again.'
            : 'Unable to generate report.';
        showToast(message, 'error');
        if (reportJson) {
            reportJson.innerText = timedOut
                ? 'Request timed out after 180 seconds. The AI service may be slow or unreachable.'
                : 'Request failed.';
        }
    });
}
