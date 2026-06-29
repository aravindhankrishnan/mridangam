## Requirements

python3 version >= 3.9.6

___
## How to run

Assumes the notes in the input rtf file is in 3rd speed

```python3 convert_notes_to_thalam.py --konnakol korvai-1.rtf --notes notes.txt --speed 3```

____

Assumes the notes in the input rtf file is STILL in 3rd speed. The `--increase-one-speed-from-input` parameter will produce notes for thalam in 4th speed.

```python3 convert_notes_to_thalam.py --konnakol korvai-1.rtf --notes notes.txt --speed 4 --increase-one-speed-from-input```
____


Assumes the notes in the input rtf file is in 4th speed. The --increase-one-speed-from-input parameter will produce notes for thalam in 4th speed

```python3 convert_notes_to_thalam.py --konnakol korvai-1.rtf --notes notes.txt --speed 4```
____

## Input filename.rtf FILE

The rtf file can be created using *TextEdit* app on Mac; *WordPad*, *MS Word* on Windows; and *Libre Office* on Ubuntu. rtf format is needed to support bold and underline font styles in the konnakol notation.

**Konnakol notation** 
- Underline refers to double speed
- Bold font also refers to double speed
- Bold + Underline refers to 4x speed.

Refer to the rtf files in folders korvais and abiprayams for examples.

___

## Output file

The output will be a html file under the name <konnakol_filename>.html

___

## Copying the output to the excel sheet

Open the output html file in your favourite browser. *Select All* -> *Copy* -> *Paste in Excel*

____


## Adding your own notation for individual notes

You may want to use 'Di' instead of 'Dhi', 'dhIm' instead of 'Dheem', etc. It's your personal preference. `notes.txt` serves the purpose of personalizing your notation. Update `notes.txt` with your preferred notation -- one note per line. **IMPORTANT** -> ',' should be specified as a note too.

____

