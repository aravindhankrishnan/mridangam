#!/usr/bin/env python3
"""Flask web app for the mridangam konnakol converter."""

import os

from flask import Flask, request, jsonify, send_from_directory
from convert_notes_to_thalam import convert, parse_rtf, strip_comment_lines

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/preview-rtf", methods=["POST"])
def preview_rtf_endpoint():
    data = request.get_json(force=True)
    rtf_content = data.get("rtf_content", "")

    if not rtf_content or not rtf_content.strip():
        return jsonify({"preview": ""}), 200

    try:
        char_tuples = parse_rtf(rtf_content)
        # Do NOT strip comment lines here — show them in the preview as context.

        # Build styled HTML from (char, ul, bold, line_num) tuples.
        # Line breaks come from line_num transitions (RTF \par), not literal \n chars.
        parts = []
        i = 0
        n = len(char_tuples)
        prev_line_num = char_tuples[0][3] if char_tuples else 0

        while i < n:
            ch, ul, bold, line_num = char_tuples[i]

            # Insert a line break whenever line_num advances
            if line_num != prev_line_num:
                for _ in range(line_num - prev_line_num):
                    parts.append("<br>")
                prev_line_num = line_num

            if ch == "\n":
                parts.append("<br>")
                i += 1
                continue

            # Collect a run with the same formatting and line_num
            run_chars = []
            run_ul, run_bold = ul, bold
            while (i < n
                   and char_tuples[i][1] == run_ul
                   and char_tuples[i][2] == run_bold
                   and char_tuples[i][0] != "\n"
                   and char_tuples[i][3] == line_num):
                c = char_tuples[i][0]
                c = c.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                run_chars.append(c)
                i += 1
            text = "".join(run_chars)
            if not text:
                continue
            if run_bold and run_ul:
                parts.append(f'<span style="font-weight:bold;text-decoration:underline">{text}</span>')
            elif run_bold:
                parts.append(f'<span style="font-weight:bold">{text}</span>')
            elif run_ul:
                parts.append(f'<span style="text-decoration:underline">{text}</span>')
            else:
                parts.append(text)

        return jsonify({"preview": "".join(parts)})
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
        html = convert(rtf_content, notes_content, speed, increase_one_speed)
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
