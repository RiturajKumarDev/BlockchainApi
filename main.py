import os
import json
import base64
import hashlib

from flask import Flask, request, jsonify
from algosdk import account, mnemonic
from algosdk.v2client import algod
from algosdk import transaction

app = Flask(__name__)

ALGOD_SERVER = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
ALGOD_TOKEN = os.getenv("ALGOD_TOKEN", "")
DEPLOYER_MNEMONIC = os.getenv("DEPLOYER_MNEMONIC", "")
APP_ID = int(os.getenv("APP_ID", "0"))


def get_algod_client() -> algod.AlgodClient:
    headers = {}
    if ALGOD_TOKEN:
        headers["X-API-Key"] = ALGOD_TOKEN
    return algod.AlgodClient(ALGOD_TOKEN, ALGOD_SERVER, headers)


def get_private_key() -> str:
    if not DEPLOYER_MNEMONIC.strip():
        raise ValueError("DEPLOYER_MNEMONIC missing")
    return mnemonic.to_private_key(DEPLOYER_MNEMONIC.strip())


def get_address() -> str:
    return account.address_from_private_key(get_private_key())


def canonical_hash(data: dict) -> str:
    canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def wait_for_confirmation(client: algod.AlgodClient, txid: str, timeout: int = 10):
    start_round = client.status()["last-round"] + 1
    current_round = start_round

    while current_round < start_round + timeout:
        pending_txn = client.pending_transaction_info(txid)
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        client.status_after_block(current_round)
        current_round += 1

    raise TimeoutError(f"Transaction not confirmed after {timeout} rounds: {txid}")


@app.get("/")
def home():
    return jsonify({"message": "Fruit Hash API is running"})


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/store-hash")
def store_hash():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        if APP_ID <= 0:
            return (
                jsonify({"success": False, "error": "APP_ID missing or invalid"}),
                500,
            )

        data_hash = canonical_hash(body)

        client = get_algod_client()
        private_key = get_private_key()
        sender = get_address()

        params = client.suggested_params()

        # Ye simple app-call hai:
        # app_args[0] = "store_hash"
        # app_args[1] = actual hash
        txn = transaction.ApplicationNoOpTxn(
            sender=sender,
            sp=params,
            index=APP_ID,
            app_args=[
                b"store_hash",
                data_hash.encode("utf-8"),
            ],
        )

        signed_txn = txn.sign(private_key)
        txid = client.send_transaction(signed_txn)
        confirmed = wait_for_confirmation(client, txid, 10)

        return jsonify(
            {
                "success": True,
                "hash": data_hash,
                "tx_id": txid,
                "confirmed_round": confirmed.get("confirmed-round"),
                "app_id": APP_ID,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/get-hash")
def get_hash():
    try:
        if APP_ID <= 0:
            return (
                jsonify({"success": False, "error": "APP_ID missing or invalid"}),
                500,
            )

        client = get_algod_client()
        app_info = client.application_info(APP_ID)

        global_state = app_info.get("params", {}).get("global-state", [])

        decoded_state = {}
        for item in global_state:
            key_b64 = item.get("key", "")
            value = item.get("value", {})

            key = base64.b64decode(key_b64).decode("utf-8")

            if value.get("type") == 1:  # bytes
                decoded_value = base64.b64decode(value.get("bytes", "")).decode("utf-8")
            else:
                decoded_value = value.get("uint", 0)

            decoded_state[key] = decoded_value

        return jsonify(
            {
                "success": True,
                "app_id": APP_ID,
                "global_state": decoded_state,
                "stored_hash": decoded_state.get("hash", ""),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
