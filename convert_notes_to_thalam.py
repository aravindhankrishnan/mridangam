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
    """Parse RTF and return list of (char, is_underlined, is_bold, line_num) tuples."""
    result = []
    # Stack frames: {'ul': bool, 'bold': bool, 'ignore': bool}
    stack = [{"ul": False, "bold": False, "ignore": False}]
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
                    result.append((next_ch, stack[-1]["ul"], stack[-1]["bold"], line_num))
                i += 1
            elif next_ch == "'":
                # Hex-encoded character \'XX
                i += 1
                if i + 1 < len(content):
                    try:
                        char_code = int(content[i : i + 2], 16)
                        if not stack[-1]["ignore"]:
                            result.append((chr(char_code), stack[-1]["ul"], stack[-1]["bold"], line_num))
                    except ValueError:
                        pass
                    i += 2
            elif next_ch == "-":
                if not stack[-1]["ignore"]:
                    result.append(("-", stack[-1]["ul"], stack[-1]["bold"], line_num))
                i += 1
            elif next_ch == "_":
                # Non-breaking hyphen
                if not stack[-1]["ignore"]:
                    result.append(("-", stack[-1]["ul"], stack[-1]["bold"], line_num))
                i += 1
            elif next_ch == "~":
                # Non-breaking space
                if not stack[-1]["ignore"]:
                    result.append((" ", stack[-1]["ul"], stack[-1]["bold"], line_num))
                i += 1
            elif next_ch in "\r\n":
                # \<newline> — line boundary in this RTF dialect
                if not stack[-1]["ignore"]:
                    result.append((" ", stack[-1]["ul"], stack[-1]["bold"], line_num))
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
                    elif ctrl_word == "plain":
                        stack[-1]["ul"] = False
                        stack[-1]["bold"] = False
                    elif ctrl_word == "par":
                        result.append(("\n", stack[-1]["ul"], stack[-1]["bold"], line_num))
                        line_num += 1
                    elif ctrl_word == "line":
                        result.append(("\n", stack[-1]["ul"], stack[-1]["bold"], line_num))
                    elif ctrl_word == "tab":
                        result.append(("\t", stack[-1]["ul"], stack[-1]["bold"], line_num))
            else:
                i += 1
        elif ch in "\r\n":
            if not stack[-1]["ignore"]:
                result.append((" ", stack[-1]["ul"], stack[-1]["bold"], line_num))
            i += 1
        else:
            if not stack[-1]["ignore"]:
                result.append((ch, stack[-1]["ul"], stack[-1]["bold"], line_num))
            i += 1

    return result


def char_triples_to_words(char_triples):
    """Tokenize (char, ul, bold, line_num) tuples into (word, ul, bold, line_num) tuples.
    Delimiters: space, newline, tab, hyphen. Comma is its own token unless
    immediately followed by a newline (end-of-line punctuation)."""
    words = []
    current_chars = []
    current_ul = False
    current_bold = False
    current_line = 0
    n = len(char_triples)

    for idx in range(n):
        char, ul, bold, line_num = char_triples[idx]
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
            next_char = char_triples[idx + 1][0] if idx + 1 < n else ""
            if next_char not in "\n\r":
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


def write_html(words, n, mathras_per_beat, output_path):
    # words is a list of (word, line_num) pairs
    rows = [words[i : i + n] for i in range(0, len(words), n)]
    total_cols = n + 1  # n word columns + 1 marker column

    # Header row with column numbers
    header_cells = ""
    for i in range(1, n + 1):
        style = "border-right: 3px solid #555" if i % mathras_per_beat == 0 else ""
        header_cells += f'    <th style="{style}">{i}</th>\n'
    header_cells += "    <th></th>\n"
    html_rows = [
        f"  <tr>\n{header_cells}  </tr>",
        f'  <tr><td colspan="{total_cols}" style="border:none; height:8px"></td></tr>',
    ]

    for row_num, row in enumerate(rows, start=1):
        row = row + [("", 0)] * (n - len(row))  # pad last row to n columns
        marker = "||" if row_num % 2 == 0 else "|"
        cells = ""
        for col_idx, (w, line_num) in enumerate(row):
            style = f"background:{LINE_COLORS[line_num % 2]}"
            if (col_idx + 1) % mathras_per_beat == 0:
                style += "; border-right: 3px solid #555"
            cells += f'    <td style="{style}">{w}</td>\n'
        cells += f'    <td style="color:red">{marker}</td>\n'
        html_rows.append(f"  <tr>\n{cells}  </tr>")
        if marker == "||":
            html_rows.append(f'  <tr><td colspan="{total_cols}" style="border:none; height:8px"></td></tr>')
    table_body = "\n".join(html_rows)
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  table {{ border-collapse: collapse; }}
  td, th {{ border: 1px solid #999; padding: 6px 10px; text-align: center; }}
  th {{ background: #d0d0d0; }}
</style>
</head>
<body>
<table>
{table_body}
</table>
</body>
</html>
"""
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
        char_tuples = parse_rtf(content)
        word_tuples = char_triples_to_words(char_tuples)
    else:
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
