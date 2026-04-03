import os
import json
import hashlib
from flask import Flask, request, jsonify

app = Flask(__name__)


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

        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True)
        data_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # फिलहाल sirf hash return kar rahe hain
        # blockchain integration baad me add karenge
        return jsonify(
            {"success": True, "hash": data_hash, "tx_id": "", "app_id": 758217797}
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
