# GARUDA-ID — AI-Based Fake Identity & Document Screening (SIH26194)

**SIH 2026 · Problem Statement SIH26194 — Student Innovation** · AICTE, MIC-Student Innovation · Theme: Blockchain & Cybersecurity.

Official PS details (sih.gov.in):

| Field | Value |
|---|---|
| Problem Statement ID | 26194 |
| Title | Student Innovation — Provide ideas in a decentralized and distributed ledger technology used to store digital information that powers cryptocurrencies and NFTs and can radically change multiple sectors |
| Organization | AICTE |
| Department | AICTE, MIC-Student Innovation |
| Category | Software |
| Theme | Blockchain & Cybersecurity |

| | |
|---|---|
| 🌐 **Live demo (frontend)** | https://garudaid.netlify.app/ |
| 🔌 **Live API (backend)** | https://garuda-id-api.onrender.com/ |
| 📁 **Repository** | https://github.com/pulstack13/SIH26 |
| 📖 **API docs (local)** | http://127.0.0.1:8000/docs |

> Demo tip: open the live site as `https://garudaid.netlify.app/?api=https://garuda-id-api.onrender.com` to point it at any API, or set `window.GARUDA_API_BASE` in `frontend/index.html`.

Video-demo flow: **select document type → upload image → VERIFY → READY / RECAPTURE → blockchain audit proof + tampering heatmap + face match**.

Only the report ID, quality-check results, timestamp, status, and a SHA-256 evidence hash are written to the chain. Uploaded images and personal data are never written to blockchain or retained by the API.

## SIH26194 module mapping

| SIH module | Status in this prototype |
|---|---|
| 1. OCR Extraction | Passport TD3 MRZ (Windows OCR, PaddleOCR fallback) + Visa / Aadhaar / PAN / EPIC / DL / Permit field extraction |
| 2. Document Validation | ICAO Doc 9303 check digits · UIDAI Aadhaar Verhoeff · Parivahan DL `SS-RR-YYYY-NNNNNNN` · ITD PAN holder-type · ECI EPIC format · blacklist / expired / duplicate-identity watchlist (`backend/data/watchlist.json`) |
| 3. Tampering Detection | ELA recompression diff + block-noise analysis + metadata (editing-software tags) with officer-view heatmap; score ≥ 45 forces RECAPTURE |
| 4. Face Verification | `POST /api/verify-face` — ID portrait (auto-linked from upload) vs camera-only live selfie; Haar/RetinaFace detection, ArcFace embeddings when installed (screening-grade fallback otherwise), passive liveness + morph screening |
| Audit trail | `GarudaAudit.sol:recordScan()` on local Hardhat chain; SHA-256 evidence hash only |

## Project structure

- `frontend/` — govt-portal UI (EN/HI toggle), per-document samples in `demo-assets/`, history (localStorage)
- `backend/` — FastAPI service (`main.py`); `services/` holds `quality`, `ocr`, `mrz`, `indian_ids`, `tampering`, `face`, `watchlist`, `audit`
- `backend/data/watchlist.json` — demo blacklist/expired DB (reloads per request; `seen_ids.json` runtime log is git-ignored)
- `blockchain/` — Hardhat config + `GarudaAudit` contract
- `requirements.txt` / `render.yaml` — hosted API deploy (Render Blueprint)

## Security: keep credentials local

This repository intentionally does **not** contain credentials. The root `.env` file is ignored by Git; `.env.example` is the safe, commit-ready template.

1. Copy the template: `Copy-Item .env.example .env`
2. Put only local demo values in `.env`.
3. Never commit a real wallet private key, API token, or password. Hardhat's printed test keys are for the local demo only.

Before every push, run `git status --ignored` and make sure `.env` appears under ignored files, never under files to be committed. If a secret is ever pushed, revoke or rotate it immediately; deleting it in a later commit does not remove it from Git history.

## Start the app (local, full features)

Use three PowerShell terminals from `C:\Users\HP\OneDrive\Desktop\wx\sih26`. The frontend is served by FastAPI, so it does not need a separate development server.

### Terminal 1 — local blockchain

```powershell
cd "C:\Users\HP\OneDrive\Desktop\wx\sih26\blockchain"
npm install
npm run node
```

### Terminal 2 — deploy the audit contract

Run this once after starting or restarting the local blockchain:

```powershell
cd "C:\Users\HP\OneDrive\Desktop\wx\sih26\blockchain"
npm run deploy
```

If the printed contract address changes, place it in `BLOCKCHAIN_CONTRACT_ADDRESS` inside the root `.env` file.

### Terminal 3 — backend and frontend

```powershell
cd "C:\Users\HP\OneDrive\Desktop\wx\sih26"
uv sync
uv run uvicorn backend.main:app --reload --port 8000
```

Open the frontend at `http://127.0.0.1:8000`. Backend API docs at `http://127.0.0.1:8000/docs`, blockchain status at `http://127.0.0.1:8000/api/blockchain-status`, watchlist status at `http://127.0.0.1:8000/api/watchlist-status`, face engine status at `http://127.0.0.1:8000/api/face-status`.

On Windows, the prototype uses the built-in offline OCR engine. PaddleOCR remains an optional fallback for other platforms.

One-click synthetic demo inputs (filtered per document type):

- Passport: `Clear → READY`, `Blurry/dark → RECAPTURE`, `Edited → TAMPER FLAG`
- Visa / National ID (Aadhaar) / Driving Licence / Permit: per-type `Sample → READY`
- Blacklist test: National ID with Aadhaar `2000 0041 3739` → blacklist HIT

## Hosted vs local capabilities

| Feature | Local (Windows) | Hosted (Netlify + Render free) |
|---|---|---|
| Quality gate, tampering heatmap, face, watchlist, history, Hindi | ✅ | ✅ |
| MRZ / ID-number OCR | ✅ (Windows OCR) | ⚠️ degraded — no Windows OCR / PaddleOCR on free tier |
| On-chain audit proof | ✅ (local Hardhat) | ⚠️ hash-only mode — laptop chain unreachable from cloud |
| Camera selfie | ✅ (localhost = secure context) | ✅ (Netlify HTTPS) |

## Add a local blockchain audit proof

Copy `.env.example` to `.env`, then replace the contract address and private key with the values printed by Hardhat:

```powershell
cd "C:\Users\HP\OneDrive\Desktop\wx\sih26"
Copy-Item .env.example .env
```

Restart the API after editing `.env`. Upload an image, complete verification, then select **Record audit proof**. For this demo, use only Hardhat's local test accounts — never a real wallet or real funds.

## Recording checklist

1. Start the API and local Hardhat node; deploy the contract and add the printed address and test private key to `.env`.
2. In the browser, select Passport → Sample 1, click **Verify Passport**, then **Record audit proof**. Show the evidence hash, block number, and transaction hash in the audit-proof panel.
3. Try Sample 3 (Edited) for the tampering heatmap, and the Face section (document auto-links as ID portrait, camera selfie for liveness).
4. End on the privacy note: images and document fields are never written on-chain; only the evidence hash, decision, and timestamp are recorded.
