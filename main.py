import os
import json
import base64
import hashlib
from flask import Flask, request, jsonify
from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod

app = Flask(__name__)

# =========================
# Env variables
# =========================
ALGOD_ADDRESS = os.getenv("ALGOD_ADDRESS", "https://testnet-api.algonode.cloud")
ALGOD_TOKEN = os.getenv("ALGOD_TOKEN", "")  # Algonode ke liye blank ho sakta hai
ALGOD_HEADERS_JSON = os.getenv("ALGOD_HEADERS", "{}")

# 25-word mnemonic of sender wallet
ALGO_MNEMONIC = os.getenv("ALGO_MNEMONIC", "")

# Optional: explorer base
EXPLORER_TX_BASE = os.getenv(
    "EXPLORER_TX_BASE", "https://lora.algokit.io/testnet/transaction/"
)

# Optional existing app id (future smart-contract use)
APP_ID = int(os.getenv("APP_ID", "758217797"))

try:
    ALGOD_HEADERS = json.loads(ALGOD_HEADERS_JSON)
except Exception:
    ALGOD_HEADERS = {}

algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS, headers=ALGOD_HEADERS)


def get_account_from_mnemonic():
    if not ALGO_MNEMONIC.strip():
        raise ValueError("ALGO_MNEMONIC is missing in environment variables")

    private_key = mnemonic.to_private_key(ALGO_MNEMONIC)
    sender_address = account.address_from_private_key(private_key)
    return private_key, sender_address


def wait_for_confirmation(client, tx_id, timeout=10):
    """
    Wait until the transaction is confirmed or timeout rounds pass.
    """
    start_round = client.status().get("last-round", 0) + 1

    for current_round in range(start_round, start_round + timeout):
        pending_txn = client.pending_transaction_info(tx_id)
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        client.status_after_block(current_round)

    raise TimeoutError("Transaction not confirmed after timeout")


@app.get("/")
def home():
    return jsonify({"message": "Fruit Hash API is running with Algorand blockchain"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/account")
def account_info():
    try:
        _, sender = get_account_from_mnemonic()
        info = algod_client.account_info(sender)

        return jsonify(
            {
                "success": True,
                "address": sender,
                "amount_microalgo": info.get("amount", 0),
                "min_balance_microalgo": info.get("min-balance", 0),
                "status": "ready",
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post("/store-hash")
def store_hash():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        # 1) Canonical JSON
        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True)

        # 2) SHA256 hash
        data_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # 3) Algorand note payload
        note_payload = {
            "type": "fruit_freshness_hash",
            "hash": data_hash,
            "sha": "sha256",
            "app_id": APP_ID,
            "ts": body.get("timestamp"),
            "fruit": body.get("fruit_type"),
            "device_id": body.get("device_id"),
        }

        note_bytes = json.dumps(
            note_payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

        # 4) Sender account
        private_key, sender_address = get_account_from_mnemonic()

        # 5) Suggested params
        params = algod_client.suggested_params()

        # 6) Self-payment txn with note
        # amount = 0 microAlgo -> only metadata anchoring
        txn = transaction.PaymentTxn(
            sender=sender_address,
            sp=params,
            receiver=sender_address,
            amt=0,
            note=note_bytes,
        )

        signed_txn = txn.sign(private_key)
        tx_id = algod_client.send_transaction(signed_txn)

        # 7) Wait for confirmation
        confirmed_txn = wait_for_confirmation(algod_client, tx_id, timeout=10)

        confirmed_round = confirmed_txn.get("confirmed-round", 0)

        return jsonify(
            {
                "success": True,
                "message": "Hash stored on Algorand blockchain successfully",
                "hash": data_hash,
                "tx_id": tx_id,
                "confirmed_round": confirmed_round,
                "sender": sender_address,
                "app_id": APP_ID,
                "note_preview": note_payload,
                "explorer_url": f"{EXPLORER_TX_BASE}{tx_id}",
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post("/verify-hash")
def verify_hash():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        tx_id = body.get("tx_id")
        original_data = body.get("data")

        if not tx_id:
            return jsonify({"success": False, "error": "tx_id is required"}), 400

        if not original_data:
            return jsonify({"success": False, "error": "data is required"}), 400

        # Recreate hash from provided data
        canonical = json.dumps(original_data, separators=(",", ":"), sort_keys=True)
        recomputed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        pending = algod_client.pending_transaction_info(tx_id)

        # Sometimes note may not be in pending after confirmation on some providers.
        # So try confirmed transaction lookup via algod block info if needed.
        note_b64 = pending.get("txn", {}).get("txn", {}).get("note")

        if not note_b64:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Could not read note from transaction using current provider. Use indexer for deep verification.",
                    }
                ),
                500,
            )

        note_json = json.loads(base64.b64decode(note_b64).decode("utf-8"))
        onchain_hash = note_json.get("hash")

        return jsonify(
            {
                "success": True,
                "tx_id": tx_id,
                "recomputed_hash": recomputed_hash,
                "onchain_hash": onchain_hash,
                "matched": recomputed_hash == onchain_hash,
                "note_payload": note_json,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
