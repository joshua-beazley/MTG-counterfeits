
### Use Instructions

Create a .txt file with the name of every card and quantity in your deck. This can be easily achieved by visiting 
any deck on archidekt.com and pressing ctrl-a + ctrl-c to copy all card names to clipboard. An example decklist 
is provided in test.txt which is my favorite Xyris, the Writhing Storm group hug / card draw deck. You may 
create your own custom cardbacks or use the sheet I provide in background.jpg. Print the resultant .pdf 
file onto 12 pt cardstock with your favorite color printer. Enjoy endless free magic cards my friend!

To run, use the command ``python create_printsheet.py --decklist "test.txt" --deckname "ready_to_print.pdf"``

⚠️⚠️WARNING -- May take over a minute to complete program because of the server query time. ⚠️⚠️ 

### How it works

The .txt file is parsed and a request is sent to scryfall for an image by that name. The image is saved locally until 
all MTG cards are fetched. Then the images are placed onto sheets ready to print. Finally, these printable sheets
are ordered to have a background image in between each.

### Output
- Output folder will contain:
- PDF pages (`.pdf`) with cards arranged in grid layout.
- Optional intermediate `.jpg` sheets if you enable per-page export.
- Page size: standard 8.5 x 11 inches.
- Card size: 2.5 x 3.5 inches.
- Margins: default 0.5 inch left, 0.25 inch top.

### Credit

ChatGPT assisted greatly with writing this code. I only guided it with prompts and made user interface decisions.
All code is not my own.

### Dependencies
The script requires the following Python libraries:
- `os`, `glob`, `math`, `re`, `argparse`
- `requests`
- `pandas`
- `Pillow` (`PIL`)

Install dependencies with:
```bash
pip install requests pandas pillow
