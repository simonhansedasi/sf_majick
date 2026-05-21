import sys
import os
import json
import pathlib
import re

from flask import Flask, send_from_directory, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf_majick.sim.org_config import OrgConfig

app = Flask(__name__, static_folder=None)

BASE_DIR   = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
GUI_DIR    = BASE_DIR / "sf_majick" / "sim" / "gui"
CONFIG_DIR = BASE_DIR / "data" / "fitted_configs"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)

_VALID_FIELDS = set(OrgConfig.__dataclass_fields__.keys())


# ── Static serving ────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(GUI_DIR), "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(GUI_DIR), filename)


# ── API ───────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/save_config", methods=["POST"])
def save_config():
    body   = request.get_json(force=True)
    name   = str(body.get("name", "")).strip()
    config = body.get("config")

    if not config:
        return jsonify({"error": "config is required"}), 400

    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64].strip("_") or \
           "fitted_" + __import__("datetime").date.today().isoformat().replace("-", "")

    path = CONFIG_DIR / f"{safe}.json"
    with open(path, "w") as f:
        json.dump(config, f, indent=2)

    return jsonify({"saved": path.name, "path": str(path)})


@app.route("/api/configs")
def list_configs():
    configs = []
    for p in sorted(CONFIG_DIR.glob("*.json")):
        st = p.stat()
        configs.append({
            "name":     p.stem,
            "filename": p.name,
            "size":     st.st_size,
            "mtime":    st.st_mtime,
        })
    return jsonify(configs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5008, debug=False)
