#!/usr/bin/env python3
"""Flask web app for the mridangam konnakol converter."""

import os

from flask import Flask, request, jsonify, send_from_directory
from convert_notes_to_thalam import convert, parse_rtf, strip_comment_lines, build_preview_html

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/preview-rtf", methods=["POST"])
def preview_rtf_endpoint():
    data = request.get_json(force=True)
    rtf_content      = data.get("rtf_content", "")
    speed            = data.get("speed", 3)
    increase_one_speed = data.get("increase_one_speed", False)

    if not rtf_content or not rtf_content.strip():
        return jsonify({"preview": ""}), 200

    try:
        speed = int(speed)
    except (TypeError, ValueError):
        speed = 3

    try:
        preview = build_preview_html(rtf_content, speed, increase_one_speed)
        return jsonify({"preview": preview})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/convert", methods=["POST"])
def convert_endpoint():
    data = request.get_json(force=True)

    rtf_content = data.get("rtf_content", "")
    notes_content = data.get("notes_content", "")
    speed = data.get("speed", 3)
    increase_one_speed = data.get("increase_one_speed", False)

    if not rtf_content or not rtf_content.strip():
        return jsonify({"error": "No RTF content provided."}), 400

    try:
        speed = int(speed)
        if speed < 1 or speed > 6:
            return jsonify({"error": "Speed must be between 1 and 6."}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Speed must be an integer."}), 400

    try:
        html = convert(rtf_content, speed, increase_one_speed)
        return jsonify({"html": html})
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5678))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print(f"Starting mridangam web app at http://localhost:{port}")
    app.run(debug=debug, host="0.0.0.0", port=port)
