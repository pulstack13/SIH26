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

let selectedFile = null;
let currentAnalysis = null;

async function refreshBlockchainStatus() {
  try {
    const response = await fetch('/api/blockchain-status');
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

function selectFile(file) {
  if (!file || !file.type.startsWith('image/')) return;
  if (preview.src.startsWith('blob:')) URL.revokeObjectURL(preview.src);
  selectedFile = file;
  preview.src = URL.createObjectURL(file);
  previewWrap.hidden = false;
  dropzone.hidden = true;
  analyzeButton.disabled = false;
  recapturePrompt.hidden = true;
}

function clearFile() {
  selectedFile = null;
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
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch('/api/analyze-document', {
      method: 'POST', body: formData, signal: controller.signal
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Analysis could not be completed.');
    }
    return response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('Analysis timed out after 90 seconds. Restart the API and try a smaller, clear image.');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function renderAnalysis(data) {
  currentAnalysis = data;
  document.querySelector('#risk-score').textContent = data.risk;
  document.querySelector('#risk-summary').textContent = data.summary;
  const score = Number.isFinite(data.score) ? data.score : 0;
  document.querySelector('#validation-score').textContent = score;
  document.querySelector('#score-fill').style.width = `${score}%`;
  document.querySelector('.score-track').setAttribute('aria-valuenow', score);
  document.querySelector('#document-fields').innerHTML = Object.entries({ ...data.fields, 'Report ID': data.report_id })
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
  document.querySelector('#validation-list').innerHTML = data.checks
    .map(([label, passed]) => `<li class="${passed ? '' : 'fail'}">${label}</li>`).join('');
  document.querySelector('#reason-list').innerHTML = data.reasons
    .map(([reason, level]) => `<li class="${level}">${reason}</li>`).join('');
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
}

auditButton.addEventListener('click', async () => {
  if (!currentAnalysis) return;
  auditButton.disabled = true;
  auditButton.textContent = 'Recording audit proof…';
  setAuditStatus('Creating a privacy-safe evidence hash…');
  try {
    const response = await fetch('/api/record-audit', {
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
  analyzeButton.disabled = true;
  analyzeButton.innerHTML = 'Analyzing <span>· · ·</span>';
  setAnalysisStatus('Uploading image and starting document checks…');
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
    analyzeButton.innerHTML = 'Analyze document <span>→</span>';
  }
});
