#!/usr/bin/env python3
import argparse
import re
import sys


SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info",
    "pict", "object", "fldinst", "rxe", "txe", "xe",
    "ftnsep", "ftnsepc", "ftncn", "themedata", "colorschememapping",
    "latentstyles", "datastore",
}


def parse_rtf(content):
    """Parse RTF and return list of (char, is_underlined, is_bold, color_index, line_num) tuples.
    color_index is a 0-based index into the colortbl (0 = default/black).
    """
    # ── Pass 1: extract colortbl ──────────────────────────────────────────────
    # Format: {\colortbl;\red255\green255\blue255;\red0\green0\blue0;...}
    # Entry 0 is implicit default (no \red\green\blue before first semicolon).
    colortbl = ["#000000"]  # index 0 = default black
    ctbl_match = re.search(r'\{\\colortbl([^}]*)\}', content)
    if ctbl_match:
        entries_str = ctbl_match.group(1)
        # Split on semicolons; each entry is either empty (default) or \redN\greenN\blueN
        entries = entries_str.split(";")
        colortbl = []
        for entry in entries:
            r = re.search(r'\\red(\d+)', entry)
            g = re.search(r'\\green(\d+)', entry)
            b = re.search(r'\\blue(\d+)', entry)
            if r and g and b:
                colortbl.append(f"rgb({r.group(1)},{g.group(1)},{b.group(1)})")
            else:
                colortbl.append(None)  # empty entry = default color

    # ── Pass 2: parse character stream ───────────────────────────────────────
    result = []
    # Stack frames: {'ul': bool, 'bold': bool, 'cf': int, 'ignore': bool}
    stack = [{"ul": False, "bold": False, "cf": 0, "ignore": False}]
    line_num = 0
    i = 0

    while i < len(content):
        ch = content[i]

        if ch == "{":
            stack.append(dict(stack[-1]))
            i += 1
        elif ch == "}":
            if len(stack) > 1:
                stack.pop()
            i += 1
        elif ch == "\\":
            i += 1
            if i >= len(content):
                break
            next_ch = content[i]

            if next_ch in "\\{}":
                if not stack[-1]["ignore"]:
                    result.append((next_ch, stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                i += 1
            elif next_ch == "'":
                # Hex-encoded character \'XX
                i += 1
                if i + 1 < len(content):
                    try:
                        char_code = int(content[i : i + 2], 16)
                        if not stack[-1]["ignore"]:
                            result.append((chr(char_code), stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                    except ValueError:
                        pass
                    i += 2
            elif next_ch == "-":
                if not stack[-1]["ignore"]:
                    result.append(("-", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                i += 1
            elif next_ch == "_":
                # Non-breaking hyphen
                if not stack[-1]["ignore"]:
                    result.append(("-", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                i += 1
            elif next_ch == "~":
                # Non-breaking space
                if not stack[-1]["ignore"]:
                    result.append((" ", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                i += 1
            elif next_ch in "\r\n":
                # \<newline> — line boundary in this RTF dialect
                if not stack[-1]["ignore"]:
                    result.append((" ", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                    line_num += 1
                i += 1
            elif next_ch == "*":
                # Ignorable destination — skip rest of current group
                stack[-1]["ignore"] = True
                i += 1
            elif next_ch.isalpha():
                j = i
                while j < len(content) and content[j].isalpha():
                    j += 1
                ctrl_word = content[i:j]
                i = j
                num_str = ""
                if i < len(content) and (
                    content[i].isdigit()
                    or (content[i] == "-" and i + 1 < len(content) and content[i + 1].isdigit())
                ):
                    k = i
                    if content[k] == "-":
                        k += 1
                    while k < len(content) and content[k].isdigit():
                        k += 1
                    num_str = content[i:k]
                    i = k
                if i < len(content) and content[i] in " \r\n":
                    i += 1

                if ctrl_word in SKIP_DESTINATIONS:
                    stack[-1]["ignore"] = True

                if not stack[-1]["ignore"]:
                    if ctrl_word == "ul":
                        stack[-1]["ul"] = num_str != "0"
                    elif ctrl_word == "ulnone":
                        stack[-1]["ul"] = False
                    elif ctrl_word in ("uldash", "ulwave", "uld", "uldb", "ulth", "ulhwave", "ulldash"):
                        stack[-1]["ul"] = True
                    elif ctrl_word == "b":
                        stack[-1]["bold"] = num_str != "0"
                    elif ctrl_word == "cf":
                        stack[-1]["cf"] = int(num_str) if num_str else 0
                    elif ctrl_word == "plain":
                        stack[-1]["ul"] = False
                        stack[-1]["bold"] = False
                        stack[-1]["cf"] = 0
                    elif ctrl_word == "par":
                        result.append(("\n", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                        line_num += 1
                    elif ctrl_word == "line":
                        result.append(("\n", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
                    elif ctrl_word == "tab":
                        result.append(("\t", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
            else:
                i += 1
        elif ch in "\r\n":
            if not stack[-1]["ignore"]:
                result.append((" ", stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
            i += 1
        else:
            if not stack[-1]["ignore"]:
                result.append((ch, stack[-1]["ul"], stack[-1]["bold"], stack[-1]["cf"], line_num))
            i += 1

    return result, colortbl


def strip_comment_lines(char_tuples):
    """Remove characters belonging to any line whose first non-space
    character is '#' (comment lines in the input file)."""
    lines = {}
    for t in char_tuples:
        lines.setdefault(t[4], []).append(t[0])  # line_num is now index 4
    comment_lines = {
        line_num for line_num, chars in lines.items()
        if "".join(chars).lstrip(" \t").startswith("#")
    }
    return [t for t in char_tuples if t[4] not in comment_lines]


def load_notes(path):
    """Load token list from a notes file (one token per line).
    Returns (tokens, delete_hyphen). If '-' is in the file, delete_hyphen=True
    and '-' is excluded from the returned token list.
    """
    tokens = []
    delete_hyphen = False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            token = line.rstrip("\n")
            if token == "-":
                delete_hyphen = True
            elif token:
                tokens.append(token)
    return tokens, delete_hyphen


def tokenize_with_notes(char_tuples, tokens, delete_hyphen):
    """Greedy longest-match tokenizer driven by the notes token list.
    Spaces, newlines, and (optionally) hyphens are skipped as separators.
    Returns list of (token, ul, bold, line_num) tuples.
    Raises ValueError with a 1-based line number on unknown input.
    """
    sorted_tokens = sorted(set(tokens), key=len, reverse=True)
    skip = set(" \n\t\r\xa0-")  # hyphen always skipped (separator); notes '-' entry confirms this

    result = []
    i = 0
    total = len(char_tuples)

    while i < total:
        ch, ul, bold, line_num = char_tuples[i]

        if ch in skip:
            i += 1
            continue

        matched = False
        for token in sorted_tokens:
            end = i + len(token)
            if end > total:
                continue
            candidate = "".join(char_tuples[j][0] for j in range(i, end))
            if candidate == token:
                result.append((token, ul, bold, line_num))
                i = end
                matched = True
                break

        if not matched:
            context = "".join(char_tuples[j][0] for j in range(i, min(i + 10, total)))
            raise ValueError(f"Unknown note at line {line_num + 1}: '{context}'. Make sure these notes are part of notes.txt")

    return result


def char_triples_to_words(char_triples):
    """Tokenize (char, ul, bold, cf, line_num) tuples into (word, ul, bold, line_num) tuples.
    Delimiters: space, newline, tab, hyphen. Comma is its own token unless
    immediately followed by a newline (end-of-line punctuation).
    cf (color index) is discarded — color is only used in the preview."""
    words = []
    current_chars = []
    current_ul = False
    current_bold = False
    current_line = 0
    n = len(char_triples)

    for idx in range(n):
        char, ul, bold, cf, line_num = char_triples[idx]
        if char in " \n\t\r\xa0":
            if current_chars:
                words.append(("".join(current_chars), current_ul, current_bold, current_line))
                current_chars = []
        elif char == "-":
            if current_chars:
                words.append(("".join(current_chars), current_ul, current_bold, current_line))
                current_chars = []
        elif char == ",":
            if current_chars:
                words.append(("".join(current_chars), current_ul, current_bold, current_line))
                current_chars = []
            words.append((",", ul, bold, line_num))
        else:
            if current_chars and (ul != current_ul or bold != current_bold):
                words.append(("".join(current_chars), current_ul, current_bold, current_line))
                current_chars = []
            current_chars.append(char)
            current_ul = ul
            current_bold = bold
            current_line = line_num

    if current_chars:
        words.append(("".join(current_chars), current_ul, current_bold, current_line))

    return words



def merge_formatted(word_tuples):
    """Merge consecutive formatted words into single tokens.
    bold+underlined: chunk every 4 into 1
    underlined only or bold only: chunk every 2 into 1
    Returns list of (word, line_num) pairs.
    """
    result = []
    i = 0
    while i < len(word_tuples):
        word, ul, bold, line_num = word_tuples[i]
        if ul and bold:
            group = []
            while i < len(word_tuples) and word_tuples[i][1] and word_tuples[i][2]:
                group.append((word_tuples[i][0], word_tuples[i][3]))
                i += 1
            for j in range(0, len(group), 4):
                chunk = group[j : j + 4]
                result.append(("".join(w for w, _ in chunk), chunk[0][1]))
        elif ul or bold:
            group = []
            while i < len(word_tuples) and word_tuples[i][1] == ul and word_tuples[i][2] == bold:
                group.append((word_tuples[i][0], word_tuples[i][3]))
                i += 1
            for j in range(0, len(group), 2):
                chunk = group[j : j + 2]
                result.append(("".join(w for w, _ in chunk), chunk[0][1]))
        else:
            result.append((word, line_num))
            i += 1
    return result


def speed_up_transform(word_tuples):
    """Transform word list for one speed increase. Returns (word, line_num) pairs.
    - Plain words: word + comma (fills 2 mathras at the new speed)
    - Underlined or bold runs: keep components as separate cells (no commas)
    - Bold+underlined runs: keep components as separate cells (no commas)
    """
    result = []
    i = 0
    while i < len(word_tuples):
        word, ul, bold, line_num = word_tuples[i]
        if ul or bold:
            # Collect the consecutive run of same formatting and emit each word separately
            while i < len(word_tuples) and word_tuples[i][1] == ul and word_tuples[i][2] == bold:
                result.append((word_tuples[i][0], word_tuples[i][3]))
                i += 1
        else:
            result.append((word, line_num))
            result.append((",", line_num))
            i += 1
    return result


LINE_COLORS = ["#cce8ff", "#ccf0d8"]  # light blue, light green


def build_html_string(words, n, mathras_per_beat):
    """Build and return the HTML table as a string (used by the web app).
    Each content <td> gets a data-pos attribute equal to its index in the word list.
    """
    rows = [words[i : i + n] for i in range(0, len(words), n)]
    total_cols = n + 2  # n word columns + 1 marker column + 1 count column

    header_cells = ""
    header_cells += "    <th></th>\n"  # count column (left)
    for i in range(1, n + 1):
        style = "border-right: 3px solid #555" if i % mathras_per_beat == 0 else ""
        header_cells += f'    <th style="{style}">{i}</th>\n'
    header_cells += "    <th></th>\n"  # marker column (right)
    html_rows = [
        f"  <tr>\n{header_cells}  </tr>",
        f'  <tr><td colspan="{total_cols}" style="border:none; height:8px"></td></tr>',
    ]

    double_bar_count = 0
    pos = 0  # global word index across all rows
    for row_num, row in enumerate(rows, start=1):
        padded_row = row + [("", 0)] * (n - len(row))
        marker = "||" if row_num % 2 == 0 else "|"
        cells = ""
        if marker == "|":
            cells += f'    <td style="font-size:1.4em; font-weight:bold; border:none">{double_bar_count + 1}</td>\n'
        else:
            cells += f'    <td style="border:none"></td>\n'
        for col_idx, (w, line_num) in enumerate(padded_row):
            style = f"background:{LINE_COLORS[line_num % 2]}"
            if (col_idx + 1) % mathras_per_beat == 0:
                style += "; border-right: 3px solid #555"
            cells += f'    <td style="{style}" data-pos="{pos}">{w}</td>\n'
            pos += 1
        cells += f'    <td style="color:red; font-weight:bold">{marker}</td>\n'
        if marker == "||":
            double_bar_count += 1
        html_rows.append(f"  <tr>\n{cells}  </tr>")
        if marker == "||":
            html_rows.append(f'  <tr><td colspan="{total_cols + 1}" style="border:none; height:8px"></td></tr>')
    table_body = "\n".join(html_rows)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  table {{ border-collapse: collapse; }}
  td, th {{ border: 1px solid #999; padding: 6px 10px; text-align: center; }}
  th {{ background: #d0d0d0; }}
  td.highlighted {{ outline: 3px solid #e67e22; background: #fef3cd !important; }}
</style>
</head>
<body>
<table>
{table_body}
</table>
</body>
</html>
"""


def build_preview_html(rtf_content, speed, increase_one_speed=False):
    """Build a styled HTML preview of the RTF content where each word span
    carries a data-pos attribute matching the corresponding output cell index.

    This runs the same pipeline as convert() so the positions are exact:
      parse_rtf → strip_comment_lines → char_triples_to_words
      → merge_formatted (or speed_up_transform)

    Comment lines are shown in the preview but carry no data-pos.

    Returns: HTML string (fragment, no <html> wrapper needed).
    """
    char_tuples, colortbl = parse_rtf(rtf_content)

    # ── Build the output word list (same as convert()) to get positions ───────
    stripped = strip_comment_lines(char_tuples)
    word_tuples = char_triples_to_words(stripped)
    if increase_one_speed:
        output_words = speed_up_transform(word_tuples)
    else:
        output_words = merge_formatted(word_tuples)

    # Map from input-word index → output cell (data-pos).
    # merge_formatted / speed_up_transform consume word_tuples in order and
    # produce output_words. We replay merge_formatted here to build the mapping.
    # input_to_output[i] = output cell index for word_tuples[i]
    input_to_output = {}
    if increase_one_speed:
        out_pos = 0
        i = 0
        while i < len(word_tuples):
            word, ul, bold, line_num = word_tuples[i]
            if ul or bold:
                run_start = i
                while i < len(word_tuples) and word_tuples[i][1] == ul and word_tuples[i][2] == bold:
                    input_to_output[i] = out_pos
                    out_pos += 1
                    i += 1
            else:
                input_to_output[i] = out_pos
                out_pos += 1  # word cell
                out_pos += 1  # comma cell
                i += 1
    else:
        out_pos = 0
        i = 0
        while i < len(word_tuples):
            word, ul, bold, line_num = word_tuples[i]
            if ul and bold:
                group_start = i
                group = []
                while i < len(word_tuples) and word_tuples[i][1] and word_tuples[i][2]:
                    group.append(i)
                    i += 1
                for chunk_start in range(0, len(group), 4):
                    for gi in group[chunk_start:chunk_start + 4]:
                        input_to_output[gi] = out_pos
                    out_pos += 1
            elif ul or bold:
                group = []
                while i < len(word_tuples) and word_tuples[i][1] == ul and word_tuples[i][2] == bold:
                    group.append(i)
                    i += 1
                for chunk_start in range(0, len(group), 2):
                    for gi in group[chunk_start:chunk_start + 2]:
                        input_to_output[gi] = out_pos
                    out_pos += 1
            else:
                input_to_output[i] = out_pos
                out_pos += 1
                i += 1

    # ── Build preview HTML with per-word spans and data-pos ───────────────────
    # We work from char_tuples (NOT stripped) so comment lines appear,
    # but we need to know which char_tuple index maps to which word_tuple index.
    # Strategy: re-run char_triples_to_words on stripped tuples to get word
    # boundaries, tracking which char index each word started at; then map
    # char positions back into the full (unstripped) char stream.
    #
    # Simpler approach: work at the word level directly.
    # Re-tokenize stripped chars to get (word, ul, bold, cf, line_num) with color,
    # then render them with data-pos. Comment lines are injected separately.

    # Collect comment line numbers from the full stream
    lines_content = {}
    for t in char_tuples:
        lines_content.setdefault(t[4], []).append(t[0])
    comment_line_nums = {
        ln for ln, chars in lines_content.items()
        if "".join(chars).lstrip(" \t").startswith("#")
    }

    # Re-tokenize stripped chars keeping color info
    colored_words = []  # (word, ul, bold, cf, line_num)
    current_chars = []
    current_ul = current_bold = False
    current_cf = 0
    current_line = 0
    sc = stripped  # shorthand
    n_sc = len(sc)

    for idx in range(n_sc):
        char, ul, bold, cf, line_num = sc[idx]
        if char in " \n\t\r\xa0":
            if current_chars:
                colored_words.append(("".join(current_chars), current_ul, current_bold, current_cf, current_line))
                current_chars = []
        elif char == "-":
            if current_chars:
                colored_words.append(("".join(current_chars), current_ul, current_bold, current_cf, current_line))
                current_chars = []
        elif char == ",":
            if current_chars:
                colored_words.append(("".join(current_chars), current_ul, current_bold, current_cf, current_line))
                current_chars = []
            colored_words.append((",", ul, bold, cf, line_num))
        else:
            if current_chars and (ul != current_ul or bold != current_bold or cf != current_cf):
                colored_words.append(("".join(current_chars), current_ul, current_bold, current_cf, current_line))
                current_chars = []
            current_chars.append(char)
            current_ul = ul
            current_bold = bold
            current_cf = cf
            current_line = line_num
    if current_chars:
        colored_words.append(("".join(current_chars), current_ul, current_bold, current_cf, current_line))

    # Build line_num → list of (word, ul, bold, cf, input_word_idx) mapping
    # so we can inject comment lines at the right positions.
    # Group colored_words by their line_num.
    # input_word_idx is the index into word_tuples (for looking up input_to_output).
    # Note: colored_words aligns with word_tuples (same tokenization), so index matches.
    by_line = {}  # line_num → [(word, ul, bold, cf, word_tuple_idx)]
    wt_idx = 0
    for w, ul, bold, cf, line_num in colored_words:
        by_line.setdefault(line_num, []).append((w, ul, bold, cf, wt_idx))
        wt_idx += 1

    # Collect all line nums (content + comment), sorted
    all_line_nums = sorted(set(list(by_line.keys()) + list(comment_line_nums)))

    def make_span(text, ul, bold, cf, pos):
        styles = []
        if bold:  styles.append("font-weight:bold")
        if ul:    styles.append("text-decoration:underline")
        if cf and cf < len(colortbl) and colortbl[cf]:
            styles.append(f"color:{colortbl[cf]}")
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        style_attr = f' style="{";".join(styles)}"' if styles else ''
        pos_attr   = f' data-pos="{pos}"' if pos is not None else ''
        if style_attr or pos_attr:
            return f'<span{style_attr}{pos_attr}>{esc}</span>'
        return esc

    parts = []
    prev_ln = all_line_nums[0] if all_line_nums else 0

    for ln in all_line_nums:
        if ln != prev_ln:
            parts.append("<br>")
            prev_ln = ln

        if ln in comment_line_nums:
            # Render comment line as plain grey text (no data-pos)
            comment_text = "".join(lines_content.get(ln, []))
            esc = comment_text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            parts.append(f'<span style="color:#999;font-style:italic">{esc.strip()}</span>')
        else:
            for w, ul, bold, cf, wt_idx in by_line.get(ln, []):
                out_pos = input_to_output.get(wt_idx)
                parts.append(make_span(w, ul, bold, cf, out_pos))

    return "".join(parts)


def convert(rtf_content, speed, increase_one_speed=False):
    """Convert RTF konnakol content to an HTML table string.

    Args:
        rtf_content (str): Raw RTF file content.
        speed (int): Speed level (mathras_per_beat = 2^(speed-1)).
        increase_one_speed (bool): Insert a comma after every plain word before fusing.

    Returns:
        str: Complete HTML document as a string.
    """
    mathras_per_beat = 2 ** (speed - 1)
    n = mathras_per_beat * 4  # 4 beats per line

    char_tuples, _colortbl = parse_rtf(rtf_content)
    char_tuples = strip_comment_lines(char_tuples)
    word_tuples = char_triples_to_words(char_tuples)

    if increase_one_speed:
        words = speed_up_transform(word_tuples)
    else:
        words = merge_formatted(word_tuples)

    return build_html_string(words, n, mathras_per_beat)


def write_html(words, n, mathras_per_beat, output_path):
    """Write the HTML table to a file (used by the CLI)."""
    html = build_html_string(words, n, mathras_per_beat)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="Output konnakol as HTML table.")
    parser.add_argument("--konnakol", help="Path to the input file (.txt or .rtf)")
    parser.add_argument("--speed", type=int, required=True, help="Speed level (mathras_per_beat = 2^(speed-1))")
    parser.add_argument("--increase-one-speed-from-input", action="store_true", help="Insert a comma after every word before fusing")
    parser.add_argument("-o", "--output", help="Output HTML file (default: input filename with .html extension)")
    args = parser.parse_args()

    mathras_per_beat = 2 ** (args.speed - 1)
    n = mathras_per_beat * 4  # 4 beats per line

    try:
        with open(args.konnakol, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(args.konnakol, "r", encoding="latin-1") as f:
            content = f.read()

    if args.konnakol.lower().endswith(".rtf"):
        char_tuples, _colortbl = parse_rtf(content)
        char_tuples = strip_comment_lines(char_tuples)
        word_tuples = char_triples_to_words(char_tuples)
    else:
        content = "\n".join(
            line for line in content.split("\n") if not line.lstrip(" \t").startswith("#")
        )
        plain_words = re.findall(r",|[^ \n\-,]+", content)
        word_tuples = [(w, False, False, 0) for w in plain_words]

    if args.increase_one_speed_from_input:
        words = speed_up_transform(word_tuples)
    else:
        words = merge_formatted(word_tuples)

    output_path = args.output or re.sub(r'\.[^.]+$', '.html', args.konnakol)
    write_html(words, n, mathras_per_beat, output_path)
    print(f"Written to {output_path} (speed={args.speed}, mathras_per_beat={mathras_per_beat}, mathras_per_line={n})")


if __name__ == "__main__":
    main()
