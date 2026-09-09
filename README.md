# GARUDA-ID Prototype

Video-demo flow: **choose demo image → quality check → READY / RECAPTURE → local blockchain audit proof**.

Only the report ID, quality-check results, timestamp, status, and a SHA-256 evidence hash can be written to the local chain. Uploaded images and personal data are never written to blockchain or retained by the API.

## Project structure

- `frontend/` — browser interface and demo assets
- `backend/` — FastAPI service, document checks, OCR, and audit writer
- `blockchain/` — Hardhat configuration and the local audit contract

## Security: keep credentials local

This repository intentionally does **not** contain credentials. The root `.env` file is ignored by Git; `.env.example` is the safe, commit-ready template.

1. Copy the template: `Copy-Item .env.example .env`
2. Put only local demo values in `.env`.
3. Never commit a real wallet private key, API token, or password. Hardhat's printed test keys are for the local demo only.

Before every push, run `git status --ignored` and make sure `.env` appears under ignored files, never under files to be committed. If a secret is ever pushed, revoke or rotate it immediately; deleting it in a later commit does not remove it from Git history.

## Start the app

Use three PowerShell terminals. The frontend is served by FastAPI, so it does not need a separate development server.

### Terminal 1 — local blockchain

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026\blockchain
npm run node
```

### Terminal 2 — deploy the audit contract

Run this once after starting or restarting the local blockchain:

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026\blockchain
npm run deploy
```

If the printed contract address changes, place it in `BLOCKCHAIN_CONTRACT_ADDRESS` inside the root `.env` file.

### Terminal 3 — backend and frontend

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026
uv sync
uv run uvicorn backend.main:app --reload --port 8000
```

Open the frontend at `http://127.0.0.1:8000`. Backend API documentation is available at `http://127.0.0.1:8000/docs`, and blockchain status is available at `http://127.0.0.1:8000/api/blockchain-status`.

On Windows, the prototype uses the built-in offline OCR engine. PaddleOCR remains an optional fallback for other platforms.

The page includes two one-click, synthetic demo inputs:

- `Clear → READY` is the capture-quality sample. Use a clear synthetic passport biodata page with two valid 44-character MRZ lines for the full MRZ `READY` demonstration.
- `Blurry/dark → RECAPTURE` deliberately fails those capture checks.

## Add a local blockchain audit proof

Open a second terminal:

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026\blockchain
npm install
npm run node
```

Keep that terminal running. It prints test accounts and private keys. In a third terminal, deploy the contract:

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026\blockchain
npm run deploy
```

Copy `.env.example` to `.env`, then replace the contract address and private key with the values printed by Hardhat:

```powershell
cd C:\Users\HP\Documents\Codex\2026-09-08\sih2026
Copy-Item .env.example .env
```

Restart the API after editing `.env`. Upload an image, complete the quality check, then select **Record audit proof**. For this demo, use only Hardhat's local test accounts - never a real wallet or real funds.

## Recording checklist

1. Start the API and local Hardhat node; deploy the contract and add the printed address and test private key to `.env`.
2. In the browser, choose **Clear → READY**, click **Analyze document**, then **Record audit proof**. Show the evidence hash, block number, and transaction hash in the audit-proof panel.
3. Remove the image, choose **Blurry/dark → RECAPTURE**, and analyze it. Show the failed checks and recapture guidance.
4. End on the privacy note: images and document fields are never written on-chain; only the evidence hash, decision, and timestamp are recorded.


