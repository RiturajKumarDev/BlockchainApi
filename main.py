import os
import json
import hashlib
from flask import Flask, request, jsonify
from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod

app = Flask(__name__)

ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""
WALLET_FILE = "algo_wallet.json"

algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)


def get_private_key_and_address():
    with open(WALLET_FILE, "r", encoding="utf-8") as f:
        wallet = json.load(f)

    private_key = mnemonic.to_private_key(wallet["mnemonic"])
    address = wallet["address"]
    return private_key, address


def wait_for_confirmation(client, tx_id, timeout=15):
    last_round = client.status()["last-round"]
    for round_num in range(last_round + 1, last_round + timeout + 1):
        pending_txn = client.pending_transaction_info(tx_id)
        if pending_txn.get("confirmed-round", 0) > 0:
            return pending_txn
        client.status_after_block(round_num)
    raise Exception("Transaction not confirmed in time")


@app.post("/store-data")
def store_data():
    try:
        body = request.get_json()
        if not body:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400

        # image/base64 ko direct on-chain mat bhejo
        if "image_base64" in body:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Do not send image_base64 to blockchain API. Upload image to storage and send image_url only.",
                    }
                ),
                400,
            )

        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True)
        data_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        note_payload = {
            "type": "fruit_scan",
            "hash": data_hash,
            "fruit": body.get("fruit_type"),
            "device": body.get("device_id"),
            "ts": body.get("timestamp"),
        }

        note_text = json.dumps(note_payload, separators=(",", ":"), sort_keys=True)
        note_bytes = note_text.encode("utf-8")

        if len(note_bytes) > 1024:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Note payload too large: {len(note_bytes)} bytes. Max allowed is 1024 bytes.",
                    }
                ),
                400,
            )

        private_key, sender = get_private_key_and_address()

        info = algod_client.account_info(sender)
        balance = info.get("amount", 0)

        if balance < 2000:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Insufficient wallet balance. Current balance: {balance} microAlgos",
                    }
                ),
                400,
            )

        params = algod_client.suggested_params()

        txn = transaction.PaymentTxn(
            sender=sender, sp=params, receiver=sender, amt=0, note=note_bytes
        )

        signed_txn = txn.sign(private_key)
        tx_id = algod_client.send_transaction(signed_txn)
        confirmed_txn = wait_for_confirmation(algod_client, tx_id)

        return jsonify(
            {
                "success": True,
                "message": "Hash stored successfully on blockchain",
                "hash": data_hash,
                "tx_id": tx_id,
                "confirmed_round": confirmed_txn.get("confirmed-round", 0),
                "wallet_address": sender,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
