/**
 * HealthSync — Admissions Queue & AI Agent Audit Logic
 */

const API = '/api/v1';

// ── Session helpers ──────────────────────────────────────────
function getSession() {
    const raw = localStorage.getItem('healthsync_doctor');
    return raw ? JSON.parse(raw) : null;
}

function setSession(data) {
    localStorage.setItem('healthsync_doctor', JSON.stringify(data));
}

function clearSession() {
    localStorage.removeItem('healthsync_doctor');
}

// ── Page switching ───────────────────────────────────────────
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(pageId);
    if (page) page.classList.add('active');
}

// ── Global State for Currently Auditing Admission ────────────
let currentAdmissionId = null;
let currentPatientId = null;
let sseSource = null;
let currentPatientContext = {};
let centralPatients = [];

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const session = getSession();
    if (session) {
        initDashboard(session);
    } else {
        window.location.href = '/login';
    }
});

// ============================================================
//  LOGIN
// ============================================================
function initLoginForm() {
    // Load departments dropdown
    fetch(`${API}/departments`)
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('doctor-department');
            sel.innerHTML = '<option value="" disabled selected>Select your specialty</option>';
            (data.departments || []).forEach(d => {
                const opt = document.createElement('option');
                opt.value = d;
                opt.textContent = d.charAt(0).toUpperCase() + d.slice(1);
                sel.appendChild(opt);
            });
        })
        .catch(() => {});

    // Load hospital suggestions
    fetch(`${API}/hospitals`)
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('hospital-suggestions');
            list.innerHTML = '';
            (data.hospitals || []).forEach(h => {
                const opt = document.createElement('option');
                opt.value = h;
                list.appendChild(opt);
            });
        })
        .catch(() => {});

    // Login submit
    document.getElementById('login-form').onsubmit = (e) => {
        e.preventDefault();
        const name = document.getElementById('doctor-name').value.trim();
        const hospital = document.getElementById('doctor-hospital').value.trim();
        const department = document.getElementById('doctor-department').value;

        if (!name || !hospital || !department) return;

        setSession({ name, hospital, department });
        showPage('dashboard-page');
        initDashboard({ name, hospital, department });
    };
}

// ============================================================
//  DASHBOARD INITIALIZATION
// ============================================================
function initDashboard(session) {
    // Set doctor header info
    const initials = session.name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('doctor-avatar').textContent = initials;
    document.getElementById('display-name').textContent = session.name;
    document.getElementById('display-dept-hospital').textContent =
        `${capitalize(session.department)} - ${session.hospital}`;

    // Load initial queue data
    loadAdmissions(session);
    loadResolutionLogs(session);
    loadCentralEHR(session);
    connectSSE(session);

    // Tab navigation
    document.querySelectorAll('.nav-item[data-tab]').forEach(btn => {
        btn.onclick = (e) => {
            e.preventDefault();
            const tabId = btn.dataset.tab;

            document.querySelectorAll('.nav-item[data-tab]').forEach(n => n.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');

            // Refresh current tab data
            if (tabId === 'admissions-tab') loadAdmissions(session);
            else if (tabId === 'conflicts-tab') loadResolutionLogs(session);
            else if (tabId === 'patients-tab') loadCentralEHR(session);
        };
    });

    // Walk-in Simulator Trigger
    document.getElementById('simulate-toggle-btn').onclick = () => {
        simulateWalkIn(session);
    };

    // Refresh Queue Action
    document.getElementById('run-pipeline-btn').onclick = () => {
        loadAdmissions(session);
    };

    // Logout
    document.getElementById('logout-btn').onclick = (e) => {
        e.preventDefault();
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }
        clearSession();
        localStorage.removeItem('healthSyncDoctor');
        localStorage.removeItem('healthSyncHospital');
        window.location.href = '/login';
    };

    // Close review panel
    document.getElementById('close-review').onclick = closeAuditDesk;
    document.getElementById('review-overlay').onclick = (e) => {
        if (e.target === e.currentTarget) closeAuditDesk();
    };

    // Submit Clinical Resolution Form
    document.getElementById('resolution-form').onsubmit = (e) => {
        e.preventDefault();
        submitResolution(session);
    };

    // Nurse Joy Chat Listeners
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-chat-btn');
    
    if(chatInput && sendBtn) {
        sendBtn.onclick = sendJoyMessage;
        chatInput.onkeypress = (e) => {
            if (e.key === 'Enter') sendJoyMessage();
        };
    }

    const joyToggle = document.getElementById('nurse-joy-toggle');
    const joyWidget = document.getElementById('nurse-joy-chat');
    const closeChatBtn = document.getElementById('close-chat-btn');

    if(joyToggle && joyWidget) {
        joyToggle.onclick = () => {
            joyWidget.classList.toggle('active');
            
            // Give a context-aware greeting if opening
            if(joyWidget.classList.contains('active')) {
                const msgContainer = document.getElementById('chat-messages');
                let greeting = "Hello Doctor! How can I assist you with the HealthSync platform today?";
                
                if (currentPatientId) {
                    greeting = `Hello Doctor! I'm reviewing the cross-hospital file for ${currentPatientContext.patient?.name || 'this patient'}. Ask me anything!`;
                }

                msgContainer.innerHTML = `
                    <div class="chat-message joy">
                        ${escHtml(greeting)}
                    </div>
                `;
            }
        };
    }
    
    if(closeChatBtn && joyWidget) {
        closeChatBtn.onclick = () => {
            joyWidget.classList.remove('active');
        };
    }

    const clearPatientBtn = document.getElementById('clear-chat-patient-btn');
    if(clearPatientBtn) {
        clearPatientBtn.onclick = clearSelectedPatient;
    }
}

// ============================================================
//  ADMISSIONS DESK QUEUE
// ============================================================
function loadAdmissions(session) {
    const tbody = document.getElementById('admissions-tbody');
    const noMsg = document.getElementById('no-admissions-msg');
    const refreshBtn = document.getElementById('run-pipeline-btn');
    
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Polling admissions queue...</td></tr>';
    refreshBtn.innerHTML = '<i class="fa-solid fa-rotate spin"></i> Refreshing';

    fetch(`${API}/admissions?hospital=${encodeURIComponent(session.hospital)}`)
        .then(r => r.json())
        .then(data => {
            const list = data.data || [];
            document.getElementById('admissions-count-badge').textContent = list.length;
            tbody.innerHTML = '';
            refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh Queue';

            if (list.length === 0) {
                noMsg.style.display = 'block';
                return;
            }

            noMsg.style.display = 'none';
            list.forEach((adm, i) => {
                const tr = document.createElement('tr');
                tr.id = `adm-row-${adm.id}`;
                tr.className = 'fade-in';
                tr.style.animationDelay = `${i * 0.05}s`;

                tr.innerHTML = `
                    <td><strong>${escHtml(adm.name)}</strong></td>
                    <td>${escHtml(adm.gender)}</td>
                    <td><span class="hospital-source-label">${escHtml(adm.source_hospital)}</span></td>
                    <td><span class="status-indicator"><span class="status-dot dot-pending"></span>Waiting Audit</span></td>
                    <td>
                        <button class="review-btn" onclick="openAuditDesk(${adm.id})">
                            <i class="fa-solid fa-user-shield"></i> Audit Report
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(() => {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--danger);">Failed to connect to admissions desk API.</td></tr>';
            refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh Queue';
        });
}

// ============================================================
//  REAL-TIME SIMULATED ADMISSION
// ============================================================
function simulateWalkIn(session) {
    const simBtn = document.getElementById('simulate-toggle-btn');

    simBtn.disabled = true;
    simBtn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Processing walk-in...';

    fetch(`${API}/admit`, { method: 'POST' })
        .then(r => r.json())
        .then(() => {
            simBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Simulate Admission';
            simBtn.disabled = false;
        })
        .catch(() => {
            simBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Simulate Admission';
            simBtn.disabled = false;
        });
}

// ============================================================
//  COOPERATIVE CLINICAL AI AGENTS AUDITING DESK
// ============================================================
function openAuditDesk(admissionId) {
    currentAdmissionId = admissionId;
    
    // Reset state & hide export buttons
    document.getElementById('exporter-group').style.display = 'none';
    const submitBtn = document.getElementById('submit-resolution-btn');
    submitBtn.style.display = 'inline-flex';
    submitBtn.disabled = false;
    submitBtn.innerHTML = '<i class="fa-solid fa-circle-check"></i> Sign & Sync to EHR';

    const overlay = document.getElementById('review-overlay');
    overlay.classList.add('open');

    // Populate visual loading states
    document.getElementById('audit-patient-name').textContent = 'Loading audit profiles...';
    document.getElementById('ingestion-agent-status').textContent = 'Clinical Ingestion Validator executing plausibility check...';
    document.getElementById('auditor-agent-status').textContent = 'Audit Agent initialized. Connecting to PostgreSQL databases...';
    document.getElementById('chief-agent-status').textContent = 'Clinical Chief Agent waiting for Auditor data...';
    document.getElementById('review-recommendation').textContent = 'Cooperative analysis in progress...';
    
    // Clear forms
    document.getElementById('blood-options-container').innerHTML = '';
    document.getElementById('diagnosis-options-container').innerHTML = '';
    document.getElementById('medications-options-container').innerHTML = '';

    fetch(`${API}/admissions/${admissionId}/audit`)
        .then(r => r.json())
        .then(data => {
            currentPatientId = data.patient_id;
            currentPatientContext = {
                patient: data.incoming_report,
                conflicts: data.conflicts
            };
            updateChatPatientBanner(data.name);
            
            // Populate demographics
            document.getElementById('audit-patient-name').textContent = data.name;
            document.getElementById('audit-patient-gender').textContent = `Gender: ${data.incoming_report.gender}`;
            document.getElementById('audit-source-hosp').textContent = data.incoming_report.source_hospital;

            // Update Agent logs
            document.getElementById('ingestion-agent-status').innerHTML = formatAgentReasoning(data.agent_1_assessment);
            document.getElementById('auditor-agent-status').innerHTML = formatAgentReasoning(data.agent_2_reasoning);
            document.getElementById('chief-agent-status').innerHTML = formatAgentReasoning(data.agent_3_recommendations);

            // Render recommendation as structured action cards
            renderRecommendation(data.conflicts, data.agent_3_recommendations);

            // Build dynamic merging options
            const uniqueBloods = new Set();
            const uniqueDiagnoses = new Set();
            const uniqueMedications = new Set();

            // Feed incoming report values
            if (data.incoming_report.blood_group) uniqueBloods.add(data.incoming_report.blood_group);
            (data.incoming_report.diagnosis || []).forEach(d => uniqueDiagnoses.add(d));
            (data.incoming_report.medications || []).forEach(m => uniqueMedications.add(m));

            // Feed historical values
            data.history.forEach(hist => {
                if (hist.blood_group) uniqueBloods.add(hist.blood_group);
                (hist.diagnosis || []).forEach(d => uniqueDiagnoses.add(d));
                (hist.medications || []).forEach(m => uniqueMedications.add(m));
            });

            // 1. Blood Group Merge Input
            const bloodContainer = document.getElementById('blood-options-container');
            if (uniqueBloods.size > 0) {
                Array.from(uniqueBloods).forEach((bg, idx) => {
                    const label = document.createElement('label');
                    label.className = 'merge-radio-option';
                    const isChecked = bg === data.incoming_report.blood_group ? 'checked' : '';
                    label.innerHTML = `
                        <input type="radio" name="blood_group" value="${escHtml(bg)}" ${isChecked} required>
                        <span>${escHtml(bg)}</span>
                    `;
                    bloodContainer.appendChild(label);
                });
            } else {
                bloodContainer.innerHTML = '<small style="color:var(--text-muted)">Not Recorded</small>';
            }

            // 2. Diagnosis Merge Input (Multi select checkboxes)
            const dxContainer = document.getElementById('diagnosis-options-container');
            if (uniqueDiagnoses.size > 0) {
                Array.from(uniqueDiagnoses).forEach((dx) => {
                    const label = document.createElement('label');
                    label.className = 'merge-checkbox-option';
                    const isChecked = (data.incoming_report.diagnosis || []).includes(dx) ? 'checked' : '';
                    label.innerHTML = `
                        <input type="checkbox" name="diagnosis" value="${escHtml(dx)}" ${isChecked}>
                        <span>${escHtml(dx)}</span>
                    `;
                    dxContainer.appendChild(label);
                });
            } else {
                dxContainer.innerHTML = '<small style="color:var(--text-muted)">No Active Diagnoses</small>';
            }

            // 3. Medications Merge Input (Multi select checkboxes)
            const medsContainer = document.getElementById('medications-options-container');
            if (uniqueMedications.size > 0) {
                Array.from(uniqueMedications).forEach((med) => {
                    const label = document.createElement('label');
                    label.className = 'merge-checkbox-option';

                    // Check if this specific medication is part of a dosage conflict
                    const hasDoseConflict = (data.conflicts || []).some(c => 
                        c.field === 'medication_dosage' && 
                        c.values && Object.values(c.values).some(v => v.toLowerCase() === med.toLowerCase())
                    );
                    
                    if (hasDoseConflict) {
                        label.classList.add('med-dose-conflict');
                    }

                    const isChecked = (data.incoming_report.medications || []).includes(med) ? 'checked' : '';
                    label.innerHTML = `
                        <input type="checkbox" name="medications" value="${escHtml(med)}" ${isChecked}>
                        <span>${escHtml(med)} ${hasDoseConflict ? '<i class="fa-solid fa-triangle-exclamation text-warning animate-pulse-icon" style="margin-left:4px;" title="Dosage Conflict Detected"></i>' : ''}</span>
                    `;
                    medsContainer.appendChild(label);
                });
            } else {
                medsContainer.innerHTML = '<small style="color:var(--text-muted)">No Active Prescriptions</small>';
            }
        })
        .catch(() => {
            document.getElementById('audit-patient-name').textContent = 'Error loading audit desk details';
        });
}

function closeAuditDesk() {
    document.getElementById('review-overlay').classList.remove('open');
    
    currentAdmissionId = null;
    currentPatientId = null;
    currentPatientContext = {};
    updateChatPatientBanner(null);
}

// ============================================================
//  RESOLUTION ACTION & EXPORT DOWNLOADS
// ============================================================
function submitResolution(session) {
    if (!currentAdmissionId) return;

    const submitBtn = document.getElementById('submit-resolution-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner spin"></i> Processing & Syncing...';

    // Compile radio values
    const bloodOption = document.querySelector('input[name="blood_group"]:checked');
    const blood_group = bloodOption ? bloodOption.value : '';

    // Compile checkbox arrays
    const dxChecked = document.querySelectorAll('input[name="diagnosis"]:checked');
    const diagnosis = Array.from(dxChecked).map(cb => cb.value);

    const medsChecked = document.querySelectorAll('input[name="medications"]:checked');
    const medications = Array.from(medsChecked).map(cb => cb.value);

    const payload = {
        doctor_name: session.name,
        blood_group,
        diagnosis,
        medications
    };

    fetch(`${API}/admissions/${currentAdmissionId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(data => {
            currentPatientId = data.patient_id;

            submitBtn.style.display = 'none';
            
            // Show bi-directional exports
            document.getElementById('exporter-group').style.display = 'flex';

            // Real-time update desk lists
            loadAdmissions(session);
            loadResolutionLogs(session);
            loadCentralEHR(session);
        })
        .catch(() => {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Sync Failed';
        });
}

function downloadEHR(format) {
    if (!currentPatientId) return;
    // Dynamic file download link redirection
    window.location.href = `${API}/export/${currentPatientId}?format=${format}`;
}

// ============================================================
//  NURSE JOY CHAT LOGIC
// ============================================================
// ============================================================
//  NURSE JOY CHAT LOGIC
// ============================================================
function sendJoyMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if(!msg) return;

    input.value = '';
    
    const msgContainer = document.getElementById('chat-messages');
    msgContainer.innerHTML += `<div class="chat-message doctor">${escHtml(msg)}</div>`;
    msgContainer.scrollTop = msgContainer.scrollHeight;

    const messageId = 'joy-msg-' + Date.now();
    msgContainer.innerHTML += `<div id="${messageId}" class="chat-message joy"><i class="fa-solid fa-ellipsis animate-pulse-icon"></i></div>`;
    msgContainer.scrollTop = msgContainer.scrollHeight;

    // Connect to WebSocket Endpoint for Streaming
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${API}/chat/stream`;
    const socket = new WebSocket(wsUrl);

    let started = false;

    socket.onopen = () => {
        socket.send(JSON.stringify({
            message: msg,
            patient_context: currentPatientContext
        }));
    };

    socket.onmessage = (event) => {
        const token = event.data;
        const bubble = document.getElementById(messageId);
        if (!bubble) return;

        if (token === "[DONE]") {
            socket.close();
            return;
        }

        if (!started) {
            bubble.innerHTML = '';
            started = true;
        }

        // Append to the innerText safely
        bubble.innerText += token;
        // Convert double-newlines or newlines to br
        bubble.innerHTML = escHtml(bubble.innerText).replace(/\n/g, '<br>');
        msgContainer.scrollTop = msgContainer.scrollHeight;
    };

    socket.onerror = (err) => {
        console.error("Nurse Joy websocket error:", err);
        const bubble = document.getElementById(messageId);
        if (bubble) {
            bubble.innerHTML = `<span style="color:var(--danger)">Connection to AI lost. Please check if Ollama is online.</span>`;
        }
    };

    socket.onclose = () => {
        const bubble = document.getElementById(messageId);
        if (bubble && bubble.innerHTML.includes('fa-ellipsis')) {
            bubble.innerHTML = `<span style="color:var(--danger)">Failed to connect to LLM stream.</span>`;
        }
    };
}

// ============================================================
//  PATIENT SELECTION & CHAT CONTEXT
// ============================================================
function selectPatient(patientId, name, gender, bloodGroup, diagnoses, medications) {
    currentPatientId = patientId;
    currentPatientContext = {
        patient: {
            patient_id: patientId,
            name: name,
            gender: gender,
            blood_group: bloodGroup,
            allergies: [],
            diagnosis: diagnoses || [],
            medications: medications || []
        },
        conflicts: []
    };

    // Highlight selected row in EHR table
    document.querySelectorAll('#patients-tbody tr').forEach(tr => {
        tr.classList.remove('selected-row');
    });
    const selectedTr = document.getElementById(`patient-row-${patientId}`);
    if (selectedTr) {
        selectedTr.classList.add('selected-row');
    }

    // Highlight selected row in Conflict logs table
    document.querySelectorAll('#conflicts-tbody tr').forEach(tr => {
        tr.classList.remove('selected-row');
    });

    // Update active patient banner in Nurse Joy chat widget
    updateChatPatientBanner(name);

    // Open chat widget if not active
    const joyWidget = document.getElementById('nurse-joy-chat');
    if (joyWidget && !joyWidget.classList.contains('active')) {
        joyWidget.classList.add('active');
    }

    // Add selected patient notification in chat
    const msgContainer = document.getElementById('chat-messages');
    msgContainer.innerHTML += `
        <div class="chat-message joy" style="background:rgba(32,178,170,0.05); border:1px dashed var(--primary-glow); border-radius:10px; width:100%; max-width:100%; text-align:center; align-self:center; font-style:italic;">
            Active context loaded: <strong>${escHtml(name)}</strong> (${escHtml(gender)}, ${escHtml(bloodGroup)}). Ask me anything about this patient!
        </div>
    `;
    msgContainer.scrollTop = msgContainer.scrollHeight;
}

function updateChatPatientBanner(name) {
    const banner = document.getElementById('chat-patient-banner');
    const nameEl = document.getElementById('chat-patient-name');
    if (banner && nameEl) {
        if (name) {
            nameEl.textContent = name;
            banner.style.display = 'flex';
        } else {
            banner.style.display = 'none';
        }
    }
}

function clearSelectedPatient() {
    currentPatientId = null;
    currentPatientContext = {};
    
    // Clear selection highlights
    document.querySelectorAll('#patients-tbody tr').forEach(tr => {
        tr.classList.remove('selected-row');
    });
    document.querySelectorAll('#conflicts-tbody tr').forEach(tr => {
        tr.classList.remove('selected-row');
    });

    updateChatPatientBanner(null);

    const msgContainer = document.getElementById('chat-messages');
    msgContainer.innerHTML += `
        <div class="chat-message joy" style="background:rgba(0,0,0,0.02); border:1px dashed rgba(0,0,0,0.06); border-radius:10px; width:100%; max-width:100%; text-align:center; align-self:center; font-style:italic;">
            Patient context cleared. Switched back to Global Dashboard Mode.
        </div>
    `;
    msgContainer.scrollTop = msgContainer.scrollHeight;
}

// ============================================================
//  AUDIT RESOLUTION LOGS
// ============================================================
function loadResolutionLogs(session) {
    const tbody = document.getElementById('conflicts-tbody');
    const noMsg = document.getElementById('no-conflicts-msg');
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Polling audit trail log...</td></tr>';

    fetch(`${API}/conflicts?hospital=${encodeURIComponent(session.hospital)}&department=${encodeURIComponent(session.department)}`)
        .then(r => r.json())
        .then(data => {
            const list = data.data || [];
            tbody.innerHTML = '';

            if (list.length === 0) {
                noMsg.style.display = 'block';
                return;
            }

            noMsg.style.display = 'none';
            list.forEach((log, i) => {
                const tr = document.createElement('tr');
                tr.className = 'fade-in clickable-row';
                tr.style.animationDelay = `${i * 0.04}s`;
                
                tr.onclick = () => {
                    const match = centralPatients.find(p => p.patient_id === log.patient_id);
                    if (match) {
                        selectPatient(
                            match.patient_id,
                            match.name,
                            match.gender,
                            match.blood_group,
                            match.diagnosis,
                            match.medications
                        );
                    } else {
                        selectPatient(
                            log.patient_id,
                            log.patient_name,
                            "Unknown",
                            "Unknown",
                            [],
                            []
                        );
                    }
                };

                tr.innerHTML = `
                    <td><strong>${escHtml(log.patient_name)}</strong></td>
                    <td>${escHtml(log.conflict_type)}</td>
                    <td>100%</td>
                    <td>${escHtml(capitalize(log.department))}</td>
                    <td><i class="fa-solid fa-signature" style="color:var(--primary);margin-right:6px;"></i>${escHtml(log.reviewed_by || 'attending')}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(() => {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--danger);">Failed to query resolution logs.</td></tr>';
        });
}

// ============================================================
//  CENTRAL EHR DATABASE (POSTGRESQL)
// ============================================================
function loadCentralEHR(session) {
    const tbody = document.getElementById('patients-tbody');
    const noMsg = document.getElementById('no-patients-msg');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);">Loading central EHR pool...</td></tr>';

    fetch(`${API}/patients?hospital=${encodeURIComponent(session.hospital)}`)
        .then(r => r.json())
        .then(data => {
            const list = data.data || [];
            centralPatients = list; // Cache loaded patients
            tbody.innerHTML = '';

            if (list.length === 0) {
                noMsg.style.display = 'block';
                return;
            }

            noMsg.style.display = 'none';
            list.forEach((p, i) => {
                const tr = document.createElement('tr');
                tr.id = `patient-row-${p.patient_id}`;
                tr.className = 'fade-in clickable-row';
                tr.style.animationDelay = `${i * 0.03}s`;

                tr.onclick = () => {
                    selectPatient(
                        p.patient_id,
                        p.name,
                        p.gender,
                        p.blood_group,
                        p.diagnosis,
                        p.medications
                    );
                };

                const dxStr = Array.isArray(p.diagnosis) ? p.diagnosis.join(', ') : p.diagnosis;
                const medsStr = Array.isArray(p.medications) ? p.medications.join(', ') : p.medications;

                tr.innerHTML = `
                    <td><strong>${escHtml(p.patient_id)}</strong></td>
                    <td>${escHtml(p.name)}</td>
                    <td>${escHtml(p.gender)}</td>
                    <td><strong>${escHtml(p.blood_group)}</strong></td>
                    <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escAttr(dxStr)}">${escHtml(dxStr)}</td>
                    <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escAttr(medsStr)}">${escHtml(medsStr)}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(() => {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--danger);">Failed to query central EHR.</td></tr>';
        });
}

// ============================================================
//  RECOMMENDATION RENDERING
// ============================================================
function renderRecommendation(conflicts, chiefRecs) {
    const container = document.getElementById('review-recommendation');
    container.innerHTML = '';

    if (!conflicts || conflicts.length === 0) {
        container.innerHTML = `
            <div class="rec-action-card urgency-routine">
                <span class="rec-urgency-tag routine">Routine</span>
                <p>All clinical fields are fully aligned. Patient record is ready to be signed and synchronized.</p>
            </div>
        `;
        return;
    }

    // Render list of isolated mismatches
    const dispCard = document.createElement('div');
    dispCard.className = 'rec-action-card urgency-immediate';
    dispCard.style.marginBottom = '12px';
    
    let dispHtml = `<span class="rec-urgency-tag immediate">Mismatches Isolated</span><ul style="margin: 6px 0 0 16px; padding: 0;">`;
    conflicts.forEach(c => {
        let valuesStr = '';
        if (c.values) {
            valuesStr = Object.entries(c.values)
                .map(([hosp, val]) => `<strong>${escHtml(hosp)}</strong>: "${escHtml(val)}"`)
                .join(' vs ');
        }
        dispHtml += `<li style="margin-bottom: 4px;"><strong>${escHtml(c.conflict_type)}:</strong> ${valuesStr}</li>`;
    });
    dispHtml += `</ul>`;
    dispCard.innerHTML = dispHtml;
    container.appendChild(dispCard);

    // Render Chief's recommendations
    if (chiefRecs) {
        const chiefCard = document.createElement('div');
        chiefCard.className = 'rec-action-card urgency-soon';
        chiefCard.innerHTML = `
            <span class="rec-urgency-tag soon">Chief's Rationale</span>
            <div style="white-space: pre-wrap; font-size: 0.85rem; color: var(--text-muted); line-height: 1.4;">
                ${formatAgentReasoning(chiefRecs)}
            </div>
        `;
        container.appendChild(chiefCard);
    }
}

// ============================================================
//  UTILITIES
// ============================================================
function capitalize(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ============================================================
//  REAL-TIME SSE PIPELINE
// ============================================================
function connectSSE(session) {
    if (sseSource) {
        sseSource.close();
    }

    sseSource = new EventSource(`${API}/admissions/stream`);

    sseSource.addEventListener('new_admission', (e) => {
        try {
            const data = JSON.parse(e.data);
            handleNewAdmissionSSE(data, session);
        } catch (err) {
            console.error('Failed to parse SSE event:', err);
        }
    });

    sseSource.onerror = (err) => {
        console.error('SSE connection error, attempting reconnect...', err);
        sseSource.close();
        setTimeout(() => connectSSE(session), 3000);
    };
}

function handleNewAdmissionSSE(adm, session) {
    if (adm.source_hospital !== session.hospital) return;

    const tbody = document.getElementById('admissions-tbody');
    const noMsg = document.getElementById('no-admissions-msg');
    if (noMsg) noMsg.style.display = 'none';

    // Duplicate check
    if (document.getElementById(`adm-row-${adm.id}`)) return;

    // Prepend row
    const tr = document.createElement('tr');
    tr.id = `adm-row-${adm.id}`;
    tr.className = 'fade-in';
    tr.innerHTML = `
        <td><strong>${escHtml(adm.name)}</strong></td>
        <td>${escHtml(adm.gender)}</td>
        <td><span class="hospital-source-label">${escHtml(adm.source_hospital)}</span></td>
        <td><span class="status-indicator"><span class="status-dot dot-pending"></span>Waiting Audit</span></td>
        <td>
            <button class="review-btn" onclick="openAuditDesk(${adm.id})">
                <i class="fa-solid fa-user-shield"></i> Audit Report
            </button>
        </td>
    `;

    // Clear loading or empty row
    if (tbody.rows.length === 1 && tbody.rows[0].cells[0].colSpan > 1) {
        tbody.innerHTML = '';
    }

    tbody.insertBefore(tr, tbody.firstChild);

    // Dynamic badge increment
    const badge = document.getElementById('admissions-count-badge');
    if (badge) {
        const count = parseInt(badge.textContent || '0', 10) + 1;
        badge.textContent = count;
        badge.classList.remove('pulse-animation');
        void badge.offsetWidth; // trigger reflow
        badge.classList.add('pulse-animation');
    }

    // Trigger visual notification banner
    const banner = document.getElementById('sim-alert-banner');
    const bannerText = document.getElementById('sim-alert-text');
    if (banner && bannerText) {
        bannerText.innerHTML = `<strong>Admission Alert:</strong> ${escHtml(adm.name)} checked in from <strong>${escHtml(adm.source_hospital)}</strong>!`;
        banner.style.display = 'flex';
        banner.classList.remove('animate-slide-down');
        void banner.offsetWidth;
        banner.classList.add('animate-slide-down');

        if (window.bannerTimeout) clearTimeout(window.bannerTimeout);
        window.bannerTimeout = setTimeout(() => {
            banner.style.display = 'none';
        }, 6000);
    }
}

function formatAgentReasoning(text) {
    if (!text) return 'No reasoning provided.';
    return text.split('\n').map(line => escHtml(line)).join('<br>');
}
