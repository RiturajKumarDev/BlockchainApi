import os
import json
import hashlib
from flask import Flask, request, jsonify

from algokit_utils import AlgorandClient
from smart_contracts.artifacts.fruit_hash.fruit_hash_client import FruitHashClient

app = Flask(__name__)

ALGOD_SERVER = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud")
ALGOD_PORT = int(os.getenv("ALGOD_PORT", "443"))
ALGOD_TOKEN = os.getenv("ALGOD_TOKEN", "")

INDEXER_SERVER = os.getenv("INDEXER_SERVER", "https://testnet-idx.algonode.cloud")
INDEXER_PORT = int(os.getenv("INDEXER_PORT", "443"))
INDEXER_TOKEN = os.getenv("INDEXER_TOKEN", "")

DEPLOYER_MNEMONIC = os.getenv("DEPLOYER_MNEMONIC", "")
APP_ID = int(os.getenv("APP_ID", "0"))


def make_algorand_client() -> AlgorandClient:
    client = AlgorandClient.default_localnet()
    client.set_suggested_params_timeout(10000)

    client.set_algod(
        server=ALGOD_SERVER,
        port=ALGOD_PORT,
        token=ALGOD_TOKEN,
    )
    client.set_indexer(
        server=INDEXER_SERVER,
        port=INDEXER_PORT,
        token=INDEXER_TOKEN,
    )
    return client


def sha256_hex(data: dict) -> str:
    canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
            return jsonify({"error": "No JSON body provided"}), 400

        if not DEPLOYER_MNEMONIC:
            return jsonify({"error": "DEPLOYER_MNEMONIC missing"}), 500

        if APP_ID <= 0:
            return jsonify({"error": "APP_ID missing or invalid"}), 500

        data_hash = sha256_hex(body)

        algorand = make_algorand_client()
        deployer = algorand.account.from_mnemonic(DEPLOYER_MNEMONIC)

        client = FruitHashClient(
            algorand=algorand,
            app_id=APP_ID,
            default_sender=deployer.address,
            default_signer=deployer.signer,
        )

        result = client.store_hash(value=data_hash)

        return jsonify(
            {
                "success": True,
                "hash": data_hash,
                "app_id": APP_ID,
                "tx_id": getattr(result, "tx_id", None),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.get("/get-hash")
def get_hash():
    try:
        if not DEPLOYER_MNEMONIC:
            return jsonify({"error": "DEPLOYER_MNEMONIC missing"}), 500

        if APP_ID <= 0:
            return jsonify({"error": "APP_ID missing or invalid"}), 500

        algorand = make_algorand_client()
        deployer = algorand.account.from_mnemonic(DEPLOYER_MNEMONIC)

        client = FruitHashClient(
            algorand=algorand,
            app_id=APP_ID,
            default_sender=deployer.address,
            default_signer=deployer.signer,
        )

        result = client.get_hash()

        value = getattr(result, "return_value", "")
        return jsonify(
            {
                "success": True,
                "app_id": APP_ID,
                "stored_hash": value,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
