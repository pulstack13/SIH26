"""Local Ethereum audit writer. Only a hash and non-PII status are recorded."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "reportId", "type": "string"},
            {"internalType": "bytes32", "name": "evidenceHash", "type": "bytes32"},
            {"internalType": "enum GarudaAudit.CaptureStatus", "name": "status", "type": "uint8"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "recordScan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _blockchain_config() -> tuple[str, str | None, str | None]:
    """Read local demo settings on each request so redeploys need no API restart."""
    project_env = dotenv_values(Path(__file__).resolve().parents[2] / ".env")
    rpc_url = str(project_env.get("BLOCKCHAIN_RPC_URL") or os.getenv("BLOCKCHAIN_RPC_URL") or "http://127.0.0.1:8545")
    contract_address = project_env.get("BLOCKCHAIN_CONTRACT_ADDRESS") or os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS")
    private_key = project_env.get("BLOCKCHAIN_ACCOUNT_PRIVATE_KEY") or os.getenv("BLOCKCHAIN_ACCOUNT_PRIVATE_KEY")
    return rpc_url, contract_address, private_key


def build_evidence_hash(record: dict[str, Any]) -> str:
    canonical_record = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()


def get_blockchain_status() -> dict[str, Any]:
    """Return public local-chain details without exposing account credentials."""
    rpc_url, contract_address, _ = _blockchain_config()
    try:
        from web3 import Web3

        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 3}))
        if not web3.is_connected():
            raise RuntimeError("The local blockchain node is not responding.")
        deployed = False
        checksum_address = None
        if contract_address and contract_address.startswith("0x"):
            checksum_address = Web3.to_checksum_address(contract_address)
            deployed = len(web3.eth.get_code(checksum_address)) > 0
        return {
            "connected": True,
            "rpc_url": rpc_url,
            "chain_id": web3.eth.chain_id,
            "latest_block": web3.eth.block_number,
            "contract_address": checksum_address,
            "contract_deployed": deployed,
        }
    except Exception as error:
        return {
            "connected": False,
            "rpc_url": rpc_url,
            "contract_address": contract_address,
            "contract_deployed": False,
            "message": str(error),
        }


def record_audit(report_id: str, status: str, checks: list[list[Any]]) -> dict[str, Any]:
    timestamp = int(datetime.now(timezone.utc).timestamp())
    evidence = {"report_id": report_id, "status": status, "checks": checks, "timestamp": timestamp}
    evidence_hash = build_evidence_hash(evidence)

    rpc_url, contract_address, private_key = _blockchain_config()
    if not all((rpc_url, contract_address, private_key)):
        return {
            "recorded": False,
            "evidence_hash": evidence_hash,
            "message": "Evidence hash created. Configure the local blockchain variables to record it on-chain.",
        }

    try:
        from web3 import Web3

        web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not web3.is_connected():
            raise RuntimeError("Could not connect to the local blockchain node.")
        account = web3.eth.account.from_key(private_key)
        contract = web3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=CONTRACT_ABI)
        transaction = contract.functions.recordScan(
            report_id,
            bytes.fromhex(evidence_hash),
            0 if status == "READY" else 1,
            timestamp,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": web3.eth.get_transaction_count(account.address),
                "chainId": web3.eth.chain_id,
            }
        )
        signed = web3.eth.account.sign_transaction(transaction, private_key)
        transaction_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(transaction_hash, timeout=20)
        return {
            "recorded": True,
            "evidence_hash": evidence_hash,
            "transaction_hash": transaction_hash.hex(),
            "block_number": receipt["blockNumber"],
            "recorded_at": timestamp,
            "message": "Audit proof recorded on the local Ethereum chain.",
        }
    except Exception as error:
        return {"recorded": False, "evidence_hash": evidence_hash, "message": f"Blockchain recording failed: {error}"}
