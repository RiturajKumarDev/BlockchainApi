import os
import json
import hashlib
from pathlib import Path
from flask import Flask, request, jsonify
from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod

app = Flask(__name__)

# =========================
# Config
# =========================
ALGOD_ADDRESS = os.getenv("ALGOD_ADDRESS", "https://testnet-api.algonode.cloud")
ALGOD_TOKEN = os.getenv("ALGOD_TOKEN", "")
WALLET_FILE = os.getenv("WALLET_FILE", "algo_wallet.json")

algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


# =========================
# Wallet helpers
# =========================
def create_wallet_file():
    """
    Create a new Algorand account and save it locally.
    NOTE: In production, don't store mnemonic in plain JSON.
    """
    private_key, address = account.generate_account()
    wallet_mnemonic = mnemonic.from_private_key(private_key)

    wallet_data = {"address": address, "mnemonic": wallet_mnemonic}

    with open(WALLET_FILE, "w", encoding="utf-8") as f:
        json.dump(wallet_data, f, indent=2)

    return wallet_data


def load_or_create_wallet():
    wallet_path = Path(WALLET_FILE)

    if not wallet_path.exists():
        return create_wallet_file()

    with open(wallet_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_private_key_and_address():
    wallet = load_or_create_wallet()
    wallet_mnemonic = wallet["mnemonic"]
    private_key = mnemonic.to_private_key(wallet_mnemonic)
    address = wallet["address"]
    return private_key, address


def wait_for_confirmation(client, tx_id, timeout=15):
    """
    Wait for tx confirmation.
    """
    last_round = client.status()["last-round"]
    start_round = last_round + 1

    for current_round in range(start_round, start_round + timeout):
        pending_txn = client.pending_transaction_info(tx_id)
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        client.status_after_block(current_round)

    raise TimeoutError("Transaction not confirmed in time")


# =========================
# Routes
# =========================
@app.get("/")
def home():
    return jsonify({"message": "Fruit Blockchain API is running"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/create-wallet")
def create_wallet():
    try:
        if os.path.exists(WALLET_FILE):
            with open(WALLET_FILE, "r", encoding="utf-8") as f:
                wallet = json.load(f)
            return jsonify(
                {
                    "success": True,
                    "message": "Wallet already exists",
                    "address": wallet["address"],
                }
            )

        wallet = create_wallet_file()
        return jsonify(
            {
                "success": True,
                "message": "Wallet created successfully",
                "address": wallet["address"],
                "mnemonic": wallet["mnemonic"],
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/wallet-info")
def wallet_info():
    try:
        _, address = get_private_key_and_address()
        info = algod_client.account_info(address)

        return jsonify(
            {
                "success": True,
                "address": address,
                "balance_microalgo": info.get("amount", 0),
                "min_balance_microalgo": info.get("min-balance", 0),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.post("/store-data")
def store_data():
    """
    Input JSON lo
    -> canonical JSON banao
    -> SHA256 hash nikalo
    -> blockchain transaction bhejo
    -> tx_id return karo
    """
    try:
        body = request.get_json()
        if not body:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True)
        data_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # Note payload: compact rakho
        note_payload = {
            "type": "fruit_scan",
            "hash": data_hash,
            "fruit": body.get("fruit_type"),
            "device": body.get("device_id"),
            "ts": body.get("timestamp"),
        }
        note_bytes = json.dumps(
            note_payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

        private_key, sender = get_private_key_and_address()

        params = algod_client.suggested_params()

        # self transaction, amount = 0
        txn = transaction.PaymentTxn(
            sender=sender, sp=params, receiver=sender, amt=0, note=note_bytes
        )

        signed_txn = txn.sign(private_key)
        tx_id = algod_client.send_transaction(signed_txn)
        confirmed_txn = wait_for_confirmation(algod_client, tx_id)

        return jsonify(
            {
                "success": True,
                "message": "Data hash stored on blockchain",
                "hash": data_hash,
                "tx_id": tx_id,
                "confirmed_round": confirmed_txn.get("confirmed-round", 0),
                "wallet_address": sender,
                "note_data": note_payload,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
