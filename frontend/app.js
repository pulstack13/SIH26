const fileInput = document.querySelector('#file-input');
const dropzone = document.querySelector('#dropzone');
const previewWrap = document.querySelector('#preview-wrap');
const preview = document.querySelector('#document-preview');
const removeFile = document.querySelector('#remove-file');
const analyzeButton = document.querySelector('#analyze-button');
const analysisStatus = document.querySelector('#analysis-status');
const auditButton = document.querySelector('#audit-button');
const auditStatus = document.querySelector('#audit-status');
const results = document.querySelector('#results');
const emptyState = document.querySelector('#empty-state');
const riskBadge = document.querySelector('#risk-badge');
const auditProof = document.querySelector('#audit-proof');
const demoPicker = document.querySelector('#demo-picker');
const recapturePrompt = document.querySelector('#recapture-prompt');
const recaptureButton = document.querySelector('#recapture-button');
const recaptureCopy = document.querySelector('#recapture-copy');
const blockchainStatus = document.querySelector('#blockchain-status');
const docTypePicker = document.querySelector('#doc-type-picker');
const doctypeNotice = document.querySelector('#doctype-notice');
const doctypeChip = document.querySelector('#doctype-chip');
const captureTitle = document.querySelector('#capture-title');
const dropzoneTitle = document.querySelector('#dropzone-title');
const dropzoneSub = document.querySelector('#dropzone-sub');
const helperDoctype = document.querySelector('#helper-doctype');
const fieldsTitle = document.querySelector('#fields-title');

// Split hosting: same-origin by default. For Netlify frontend + Render API,
// set window.GARUDA_API_BASE="https://<your-api>.onrender.com" in index.html
// or open the site as https://<site>.netlify.app/?api=https://<your-api>.onrender.com
const API_BASE = (() => {
  try {
    const q = new URLSearchParams(location.search).get('api');
    const base = (q || window.GARUDA_API_BASE || '').trim().replace(/\/$/, '');
    if (base) localStorage.setItem('garuda_api_base', base);
    return base || localStorage.getItem('garuda_api_base') || '';
  } catch { return (window.GARUDA_API_BASE || '').trim().replace(/\/$/, ''); }
})();
const api = (path) => `${API_BASE}${path}`;

let selectedFile = null;
let currentAnalysis = null;
let selectedDocType = 'passport';
let lang = 'en';
let faceIdFile = null;
let faceSelfieFile = null;

const DOC_TYPES = {
  passport: {
    label: 'Passport',
    drop: 'Add passport biodata page',
    sub: 'PNG / JPG / WEBP · Max 10 MB · Both 44-char MRZ lines visible',
    helper: 'Passport: ICAO 9303 MRZ checks.',
    fields: 'Extracted fields — Passport (TD3)',
    notice: 'Passport selected — full TD3 MRZ validation (ICAO 9303).',
  },
  visa: {
    label: 'Visa',
    drop: 'Add visa page',
    sub: 'PNG / JPG / WEBP · Max 10 MB',
    helper: 'Visa: number, type, issue/expiry checks.',
    fields: 'Extracted fields — Visa',
    notice: 'Visa selected — number, type, stay, issue/expiry validation.',
  },
  national_id: {
    label: 'National ID',
    drop: 'Add national ID (front)',
    sub: 'PNG / JPG / WEBP · Max 10 MB · Aadhaar / PAN / Voter ID',
    helper: 'National ID: Aadhaar Verhoeff + PAN + EPIC checks.',
    fields: 'Extracted fields — National ID',
    notice: 'National ID selected — Aadhaar (UIDAI Verhoeff), PAN (ITD), EPIC (ECI) checks.',
  },
  driving_licence: {
    label: 'Driving Licence',
    drop: 'Add driving licence (front)',
    sub: 'PNG / JPG / WEBP · Max 10 MB · Parivahan format',
    helper: 'Driving licence: Parivahan SS-RR-YYYY-NNNNNNN checks.',
    fields: 'Extracted fields — Driving Licence',
    notice: 'Driving licence selected — state/RTO/year/serial + expiry checks.',
  },
  permit: {
    label: 'Permit',
    drop: 'Add permit document',
    sub: 'PNG / JPG / WEBP · Max 10 MB',
    helper: 'Permit: number + issue/expiry checks.',
    fields: 'Extracted fields — Permit',
    notice: 'Permit selected — number + issue/expiry validation.',
  },
};

function applyDocType(type) {
  selectedDocType = DOC_TYPES[type] ? type : 'passport';
  const cfg = DOC_TYPES[selectedDocType];
  if (docTypePicker) docTypePicker.querySelectorAll('[data-doctype]').forEach((b) =>
    b.classList.toggle('active', b.dataset.doctype === selectedDocType)
  );
  if (doctypeChip) doctypeChip.textContent = cfg.label;
  if (captureTitle) captureTitle.textContent = cfg.label;
  if (dropzoneTitle) dropzoneTitle.textContent = cfg.drop;
  if (dropzoneSub) dropzoneSub.textContent = cfg.sub;
  if (helperDoctype) helperDoctype.textContent = cfg.helper;
  if (doctypeNotice) doctypeNotice.textContent = cfg.notice;
  if (fieldsTitle) fieldsTitle.textContent = cfg.fields;
  if (analyzeButton) analyzeButton.textContent = (lang === 'hi' ? 'सत्यापित करें: ' : 'Verify ') + cfg.label;
  // Per-doc filtering: show only this type's samples, clear stale file/report.
  if (demoPicker) demoPicker.querySelectorAll('[data-demo]').forEach((b) => {
    const show = !b.dataset.doctype || b.dataset.doctype === selectedDocType;
    b.hidden = !show;
  });
  const demoLabel = document.querySelector('#demo-label');
  if (demoLabel) demoLabel.textContent = `Sample images for ${cfg.label} (this type only):`;
  clearFile();
  if (results) results.hidden = true;
  if (emptyState) emptyState.hidden = false;
  const emptyText = document.querySelector('#empty-text');
  if (emptyText) emptyText.textContent = `Select ${cfg.label}, upload its image and click Verify. No ${cfg.label} image is loaded right now.`;
  document.querySelectorAll('[id^="guide-"]').forEach((row) => {
    row.classList.toggle('guide-active', row.id === `guide-${selectedDocType}`);
  });
}

if (docTypePicker) {
  docTypePicker.addEventListener('click', (event) => {
    const button = event.target.closest('[data-doctype]');
    if (!button) return;
    applyDocType(button.dataset.doctype);
    setAnalysisStatus(`${DOC_TYPES[selectedDocType].label} selected — now add its image.`);
  });
  applyDocType('passport');
}

async function refreshBlockchainStatus() {
  try {
    const response = await fetch(api('/api/blockchain-status'));
    const status = await response.json();
    blockchainStatus.classList.toggle('offline', !status.connected || !status.contract_deployed);
    blockchainStatus.querySelector('b').textContent = status.connected && status.contract_deployed
      ? `Chain ${status.chain_id} · block ${status.latest_block}`
      : status.connected ? 'Chain online · contract missing' : 'Local chain offline';
  } catch {
    blockchainStatus.classList.add('offline');
    blockchainStatus.querySelector('b').textContent = 'Local chain offline';
  }
}

refreshBlockchainStatus();
async function refreshWatchlistStatus() {
  try {
    const res = await fetch(api('/api/watchlist-status'));
    const data = await res.json();
    const el = document.querySelector('#watchlist-status');
    if (el) el.textContent = `Watchlist DB: ${data.entries || 0} demo entries loaded (${data.seen_ids || 0} IDs seen this session). Edit backend/data/watchlist.json to update. Test blacklist with Aadhaar 2000 0041 3739.`;
  } catch {
    const el = document.querySelector('#watchlist-status');
    if (el) el.textContent = 'Watchlist DB: API unreachable — check GARUDA_API_BASE / backend status.';
  }
}
refreshWatchlistStatus();

function selectFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  if (preview.src.startsWith('blob:')) URL.revokeObjectURL(preview.src);
  selectedFile = file;
  preview.src = URL.createObjectURL(file);
  previewWrap.hidden = false;
  dropzone.hidden = true;
  analyzeButton.disabled = false;
  recapturePrompt.hidden = true;
  // Auto-link: same upload becomes face Step 1 (no second upload needed).
  faceIdFile = file;
  const facePrev = document.querySelector('#face-id-preview');
  const faceSt = document.querySelector('#face-status');
  if (facePrev) { facePrev.src = URL.createObjectURL(file); facePrev.hidden = false; }
  if (faceSt) { faceSt.textContent = 'Step 1 done — document image linked as ID portrait. Ab camera se selfie lo.'; faceSt.classList.remove('error'); faceSt.hidden = false; }
}

function clearFile() {
  selectedFile = null;
  faceIdFile = null;
  const facePrev = document.querySelector('#face-id-preview');
  if (facePrev) { facePrev.removeAttribute('src'); facePrev.hidden = true; }
  fileInput.value = '';
  preview.removeAttribute('src');
  previewWrap.hidden = true;
  dropzone.hidden = false;
  analyzeButton.disabled = true;
  analysisStatus.hidden = true;
  auditProof.hidden = true;
  auditProof.innerHTML = '';
  recapturePrompt.hidden = true;
}

async function loadDemo(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error('The demo image could not be loaded.');
  const blob = await response.blob();
  const fileName = path.split('/').pop();
  selectFile(new File([blob], fileName, { type: blob.type || 'image/jpeg' }));
  setAnalysisStatus(`Demo image loaded: ${fileName}`);
}

function setAnalysisStatus(message, isError = false) {
  analysisStatus.textContent = message;
  analysisStatus.classList.toggle('error', isError);
  analysisStatus.hidden = !message;
}

function setAuditStatus(message, isError = false) {
  auditStatus.textContent = message;
  auditStatus.classList.toggle('error', isError);
  auditStatus.hidden = !message;
}

fileInput.addEventListener('change', (event) => selectFile(event.target.files[0]));
removeFile.addEventListener('click', clearFile);
recaptureButton.addEventListener('click', () => {
  clearFile();
  fileInput.click();
});
demoPicker.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-demo]');
  if (!button) return;
  try {
    await loadDemo(button.dataset.demo);
  } catch (error) {
    setAnalysisStatus(error.message, true);
  }
});

['dragenter', 'dragover'].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.remove('dragging');
}));
dropzone.addEventListener('drop', (event) => selectFile(event.dataTransfer.files[0]));

async function runAnalysis(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', selectedDocType);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(api('/api/analyze-document'), {
      method: 'POST', body: formData, signal: controller.signal
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Analysis failed (HTTP ${response.status}).`);
    }
    return response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Analysis timed out after 90 seconds. Restart the API and try a smaller, clear image.');
    }
    if (error instanceof TypeError) {
      // Network-level failure: wrong API URL, backend asleep/down, or CORS.
      const where = API_BASE || 'same origin (no API configured)';
      throw new Error(`Cannot reach API at ${where}. Check GARUDA_API_BASE, backend status (/health), and redeploy.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function renderAnalysis(data) {
  currentAnalysis = data;
  const docLabel = DOC_TYPES[selectedDocType] ? DOC_TYPES[selectedDocType].label : 'Passport';
  document.querySelector('#risk-score').textContent = data.risk;
  document.querySelector('#risk-summary').textContent = data.summary;
  const score = Number.isFinite(data.score) ? data.score : 0;
  document.querySelector('#validation-score').textContent = score;
  document.querySelector('#score-fill').style.width = `${score}%`;
  document.querySelector('#score-fill').className = data.risk.toLowerCase();
  const resultTable = document.querySelector('.result-table');
  if (resultTable) resultTable.className = `gov-table result-table ${data.risk.toLowerCase()}`;
  document.querySelector('.score-track').setAttribute('aria-valuenow', score);
  document.querySelector('#document-fields').innerHTML = Object.entries({ 'Document type': docLabel, ...data.fields, 'Report ID': data.report_id })
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
  document.querySelector('#validation-list').innerHTML = data.checks
    .map(([label, passed]) => `<li class="${passed ? '' : 'fail'}">${label}</li>`).join('');
  document.querySelector('#reason-list').innerHTML = data.reasons
    .map(([reason, level]) => `<li class="${level}">${reason}</li>`).join('');
  // Tampering panel (Module 3)
  const tamper = data.tampering || null;
  const tamperSection = document.querySelector('#tamper-section');
  if (tamper && tamperSection) {
    tamperSection.hidden = false;
    document.querySelector('#tamper-score').textContent = tamper.tamper_score ?? '--';
    document.querySelector('#tamper-verdict').textContent = tamper.suspicious ? 'SUSPICIOUS — officer review' : 'No tampering signals';
    document.querySelector('#tamper-list').innerHTML = Object.entries(tamper.checks || {})
      .map(([label, passed]) => `<li class="${passed ? '' : 'fail'}">${label}</li>`).join('');
    const heat = document.querySelector('#tamper-heatmap');
    if (tamper.heatmap) { heat.src = tamper.heatmap; heat.hidden = false; }
    else heat.hidden = true;
  } else if (tamperSection) tamperSection.hidden = true;
  riskBadge.textContent = data.risk;
  riskBadge.className = `risk-badge ${data.risk.toLowerCase()}`;
  emptyState.hidden = true;
  results.hidden = false;
  auditButton.disabled = false;
  setAuditStatus('');
  auditProof.hidden = true;
  auditProof.innerHTML = '';
  const needsRecapture = data.risk === 'RECAPTURE';
  recapturePrompt.hidden = !needsRecapture;
  if (needsRecapture) {
    const firstReason = data.reasons?.[0]?.[0];
    recaptureCopy.textContent = firstReason || 'Use brighter light, hold the camera steady, and keep the entire biodata page in frame.';
  }
  pushHistory({ report_id: data.report_id, doc_type: docLabel, decision: data.risk, score });
}

auditButton.addEventListener('click', async () => {
  if (!currentAnalysis) return;
  auditButton.disabled = true;
  auditButton.textContent = 'Recording audit proof…';
  setAuditStatus('Creating a privacy-safe evidence hash…');
  try {
    const response = await fetch(api('/api/record-audit'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_id: currentAnalysis.report_id,
        status: currentAnalysis.risk,
        checks: currentAnalysis.checks,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Audit record could not be created.');
    setAuditStatus(result.message, !result.recorded);
    auditProof.innerHTML = [
      ['Evidence hash', result.evidence_hash],
      ['On-chain status', result.recorded ? 'Recorded locally' : 'Hash prepared (node not connected)'],
      ...(result.recorded ? [['Block', result.block_number], ['Transaction', result.transaction_hash]] : []),
    ].map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
    auditProof.hidden = false;
  } catch (error) {
    setAuditStatus(error.message, true);
  } finally {
    auditButton.disabled = false;
    auditButton.textContent = 'Record audit proof';
  }
});

analyzeButton.addEventListener('click', async () => {
  if (!selectedFile) return;
  const activeLabel = DOC_TYPES[selectedDocType] ? DOC_TYPES[selectedDocType].label : 'Document';
  analyzeButton.disabled = true;
  analyzeButton.textContent = 'Verifying…';
  setAnalysisStatus(`Uploading ${activeLabel.toLowerCase()} image and starting verification…`);
  const slowNotice = window.setTimeout(() => {
    setAnalysisStatus('Quality checks are taking longer than usual. Please keep this tab open.');
  }, 3000);
  try {
    const result = await runAnalysis(selectedFile);
    renderAnalysis(result);
    setAnalysisStatus('Analysis complete.');
  } catch (error) {
    setAnalysisStatus(error.message, true);
  } finally {
    window.clearTimeout(slowNotice);
    analyzeButton.disabled = false;
    const resetLabel = DOC_TYPES[selectedDocType] ? DOC_TYPES[selectedDocType].label : 'Document';
    analyzeButton.textContent = (lang === 'hi' ? 'सत्यापित करें: ' : 'Verify ') + resetLabel;
  }
});

// ---- C. Face verification in 3 steps (Module 4) ----
// Step 1: ID portrait = uploaded document (one upload only) or separate file.
// Step 2: live selfie = camera only. Step 3: Verify.
const faceIdInput = document.querySelector('#face-id-input');
const faceUseDocBtn = document.querySelector('#face-use-doc-button');
const faceIdPreview = document.querySelector('#face-id-preview');
const faceSelfiePreview = document.querySelector('#face-selfie-preview');
const faceVerifyButton = document.querySelector('#face-verify-button');
const faceStatus = document.querySelector('#face-status');
function showPreview(file, img) {
  if (!file) return;
  if (img.src.startsWith('blob:')) URL.revokeObjectURL(img.src);
  img.src = URL.createObjectURL(file);
  img.hidden = false;
}
if (faceIdInput) faceIdInput.addEventListener('change', () => {
  const f = faceIdInput.files && faceIdInput.files[0];
  if (f) { faceIdFile = f; showPreview(f, faceIdPreview); faceStatus.hidden = true; }
});
if (faceUseDocBtn) faceUseDocBtn.addEventListener('click', () => {
  faceStatus.hidden = false;
  faceStatus.classList.remove('error');
  if (!selectedFile) { faceStatus.textContent = 'Pehle upar document image upload karo — wahi ID portrait banegi.'; faceStatus.classList.add('error'); return; }
  faceIdFile = selectedFile;
  showPreview(selectedFile, faceIdPreview);
  faceStatus.textContent = 'Step 1 done — document image ID portrait ban gayi. Ab Step 2: camera se selfie lo.';
});
if (faceVerifyButton) faceVerifyButton.addEventListener('click', async () => {
  faceStatus.hidden = false;
  if (!faceIdFile || !faceSelfieFile) { faceStatus.textContent = 'Step 1 (ID) aur Step 2 (camera selfie) dono poore karo.'; faceStatus.classList.add('error'); return; }
  faceStatus.classList.remove('error');
  faceStatus.textContent = 'Step 3: matching faces + liveness + morph…';
  faceVerifyButton.disabled = true;
  try {
    const fd = new FormData();
    fd.append('id_image', faceIdFile);
    fd.append('selfie', faceSelfieFile);
    const res = await fetch(api('/api/verify-face'), { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Face verification failed.');
    document.querySelector('#face-results').hidden = false;
    document.querySelector('#face-match').textContent = data.match ? 'MATCH' : 'NO MATCH';
    document.querySelector('#face-score').textContent = `${data.match_score}/100 (threshold ${data.threshold})`;
    document.querySelector('#face-engine').textContent = `${data.engine} · detect ${data.id_engine}/${data.selfie_engine}`;
    document.querySelector('#face-liveness').textContent = `${data.liveness.live ? 'LIVE' : 'REVIEW'} (${data.liveness.liveness_score}/100)`;
    document.querySelector('#face-morph').textContent = `${data.morph.morph_risk} (${data.morph.morph_score}/100)`;
    document.querySelector('#face-list').innerHTML = [
      ...Object.entries(data.liveness.checks || {}),
      ...Object.entries(data.morph.checks || {}),
    ].map(([label, passed]) => `<li class="${passed ? '' : 'fail'}">${label}</li>`).join('');
    faceStatus.textContent = data.message;
  } catch (e) { faceStatus.textContent = e.message; faceStatus.classList.add('error'); }
  finally { faceVerifyButton.disabled = false; }
});

// ---- D. History (localStorage) ----
const HIST_KEY = 'garuda_history_v1';
function getHistory() { try { return JSON.parse(localStorage.getItem(HIST_KEY) || '[]'); } catch { return []; } }
function pushHistory(entry) {
  const h = getHistory();
  h.unshift({ ...entry, time: new Date().toLocaleString() });
  localStorage.setItem(HIST_KEY, JSON.stringify(h.slice(0, 20)));
  renderHistory();
}
function renderHistory() {
  const h = getHistory();
  const total = document.querySelector('#hist-total');
  if (!total) return;
  total.textContent = h.length;
  document.querySelector('#hist-ready').textContent = h.filter((x) => x.decision === 'READY').length;
  document.querySelector('#hist-recapture').textContent = h.filter((x) => x.decision === 'RECAPTURE').length;
  const tbl = document.querySelector('#hist-table');
  tbl.querySelectorAll('tr:not(:first-child)').forEach((r) => r.remove());
  h.forEach((x) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${x.time}</td><td>${x.doc_type}</td><td>${x.report_id}</td><td>${x.decision}</td><td>${x.score}</td>`;
    tbl.appendChild(tr);
  });
}
const histClear = document.querySelector('#hist-clear');
if (histClear) histClear.addEventListener('click', () => { localStorage.removeItem(HIST_KEY); renderHistory(); });
renderHistory();

// ---- Hindi toggle ----
const I18N = {
  en: {
    nav_verify: 'Document Verification', nav_face: 'Face Match', nav_report: 'Verification Report',
    nav_history: 'History', nav_audit: 'Audit Trail', nav_guide: 'Guidelines',
    crumb: 'Home / Document Verification', page_title: 'Document Verification Form',
    page_sub: 'Step 1: select document type. Step 2: upload image. Step 3: verify report. Use synthetic or authorized test documents only.',
    form_a: 'A. Applicant Document Details', doctype_label: '1. Document type',
    upload_label: '2. Upload document image', verify_btn: 'Verify Document',
    form_b: 'B. Verification Report', form_c: 'C. Face Match + Liveness',
    form_d: 'D. Verification History', face_btn: 'Verify Face', toggle: 'हिन्दी',
  },
  hi: {
    nav_verify: 'दस्तावेज़ सत्यापन', nav_face: 'चेहरा मिलान', nav_report: 'सत्यापन रिपोर्ट',
    nav_history: 'इतिहास', nav_audit: 'ऑडिट ट्रेल', nav_guide: 'दिशानिर्देश',
    crumb: 'मुख्य पृष्ठ / दस्तावेज़ सत्यापन', page_title: 'दस्तावेज़ सत्यापन प्रपत्र',
    page_sub: 'चरण 1: दस्तावेज़ चुनें। चरण 2: छवि अपलोड करें। चरण 3: रिपोर्ट जांचें। केवल परीक्षण दस्तावेज़ प्रयोग करें।',
    form_a: 'क. आवेदक दस्तावेज़ विवरण', doctype_label: '1. दस्तावेज़ का प्रकार',
    upload_label: '2. दस्तावेज़ छवि अपलोड करें', verify_btn: 'दस्तावेज़ सत्यापित करें',
    form_b: 'ख. सत्यापन रिपोर्ट', form_c: 'ग. चेहरा मिलान + लiveness',
    form_d: 'घ. सत्यापन इतिहास', face_btn: 'चेहरा सत्यापित करें', toggle: 'English',
  },
};
const langBtn = document.querySelector('#lang-toggle');
if (langBtn) langBtn.addEventListener('click', () => {
  lang = lang === 'en' ? 'hi' : 'en';
  document.documentElement.lang = lang === 'hi' ? 'hi' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (key && I18N[lang][key]) el.textContent = I18N[lang][key];
  });
  langBtn.textContent = I18N[lang].toggle;
});

// ---- Face engine status + camera capture ----
async function refreshFaceStatus() {
  try {
    const res = await fetch(api('/api/face-status'));
    const data = await res.json();
    const el = document.querySelector('#face-engine-status');
    if (el) el.textContent = `Face engines: matcher ${data.active_matcher}, detector ${data.active_detector}. ${data.note || ''}`;
  } catch {
    const el = document.querySelector('#face-engine-status');
    if (el) el.textContent = 'Face engines: API unreachable — check GARUDA_API_BASE / backend status.';
  }
}
refreshFaceStatus();
const faceCameraBtn = document.querySelector('#face-camera-button');
const faceCaptureBtn = document.querySelector('#face-capture-button');
const faceVideo = document.querySelector('#face-video');
let faceStream = null;
if (faceCameraBtn) faceCameraBtn.addEventListener('click', async () => {
  faceStatus.hidden = false;
  faceStatus.classList.remove('error');
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('no-camera');
    faceStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
    faceVideo.srcObject = faceStream;
    faceVideo.hidden = false;
    faceCaptureBtn.hidden = false;
    faceCameraBtn.disabled = true;
    faceStatus.textContent = 'Camera khul gaya — frame me aao aur Capture dabao.';
  } catch { faceStatus.textContent = 'Camera nahi khula (permission/device). HTTPS ya localhost pe allow karo.'; faceStatus.classList.add('error'); faceStatus.hidden = false; }
});
if (faceCaptureBtn) faceCaptureBtn.addEventListener('click', () => {
  const canvas = document.createElement('canvas');
  canvas.width = faceVideo.videoWidth || 640;
  canvas.height = faceVideo.videoHeight || 480;
  canvas.getContext('2d').drawImage(faceVideo, 0, 0);
  canvas.toBlob((blob) => {
    if (!blob) return;
    faceSelfieFile = new File([blob], 'selfie-camera.jpg', { type: 'image/jpeg' });
    showPreview(faceSelfieFile, faceSelfiePreview);
    faceStatus.textContent = 'Step 2 done — live selfie captured. Ab Step 3: Verify Face dabao.';
    faceStatus.classList.remove('error');
    faceStatus.hidden = false;
  }, 'image/jpeg', 0.92);
  if (faceStream) faceStream.getTracks().forEach((t) => t.stop());
  faceVideo.hidden = true;
  faceCaptureBtn.hidden = true;
  faceCameraBtn.disabled = false;
});
