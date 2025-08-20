import argparse
import glob
import math
import os
import re
import sys
import pandas as pd
import requests
from PIL import Image, ImageDraw

def sanitize_filename(name):
    """Replace illegal Windows filename characters with underscores."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def download_card_images(decklist_path, output_dir="scryfall_images"):
    os.makedirs(output_dir, exist_ok=True)

    # Read decklist file
    with open(decklist_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    card_data = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):  # skip blank or commented lines
            continue

        try:
            qty, name = line.split(" ", 1)
            qty = int(qty)
        except ValueError:
            print(f"Skipping malformed line: {line}")
            continue

        # Query Scryfall
        url = f"https://api.scryfall.com/cards/named?exact={name}"
        r = requests.get(url)
        if r.status_code != 200:
            print(f"⚠️ Could not find card: {name}")
            continue
        card_json = r.json()

        # Try normal image, fallback to other printings if needed
        image_url = None
        if "image_uris" in card_json:
            image_url = card_json["image_uris"].get("png") or card_json["image_uris"].get("large")
        elif "card_faces" in card_json:  # double-faced cards
            image_url = card_json["card_faces"][0]["image_uris"].get("png")

        if not image_url:
            print(f"No image found for {name}")
            continue

        # Save N copies
        for i in range(qty):
            safe_name = sanitize_filename(f"{name}_{i+1}")
            filename = f"{safe_name}.png"
            filepath = os.path.join(output_dir, filename)

            try:
                img_data = requests.get(image_url).content
                with open(filepath, "wb") as img_file:
                    img_file.write(img_data)
            except Exception as e:
                print(f"⚠️ Could not save image for {name}: {e}")
                continue

            card_data.append({
                "name": name,
                "set": card_json.get("set"),
                "collector_number": card_json.get("collector_number"),
                "rarity": card_json.get("rarity"),
                "type_line": card_json.get("type_line"),
                "mana_cost": card_json.get("mana_cost"),
                "oracle_text": card_json.get("oracle_text"),
                "image_path": filepath
            })

    # Build DataFrame for filtering later
    df = pd.DataFrame(card_data)
    return df

def images_to_page(input_folder, output_folder="output_sheets"):
    # Page size in inches
    page_width_in, page_height_in = 8.5, 11
    dpi = 300
    page_width = int(page_width_in * dpi)
    page_height = int(page_height_in * dpi)

    # Card size in inches
    card_width_in, card_height_in = 2.5, 3.5
    card_width = int(card_width_in * dpi)
    card_height = int(card_height_in * dpi)

    # Margins in inches
    margin_left_in, margin_top_in = 0.5, 0.25
    margin_left = int(margin_left_in * dpi)
    margin_top = int(margin_top_in * dpi)

    # How many cards fit across and down (after margins)
    cols = (page_width - margin_left) // card_width
    rows = (page_height - margin_top) // card_height
    cards_per_page = cols * rows

    os.makedirs(output_folder, exist_ok=True)

    image_files = sorted([
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ])

    for page_index in range(math.ceil(len(image_files) / cards_per_page)):
        page = Image.new("RGB", (page_width, page_height), "white")
        batch = image_files[page_index * cards_per_page : (page_index + 1) * cards_per_page]

        for i, img_path in enumerate(batch):
            img = Image.open(img_path).convert("RGBA")
            img = img.resize((card_width, card_height), Image.LANCZOS)

            # Fill transparency with white
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.split()[3])  # use alpha channel as mask

            col = i % cols
            row = i // cols
            x = margin_left + col * card_width
            y = margin_top + row * card_height

            page.paste(bg, (x, y))

        output_path = os.path.join(output_folder, f"card_sheet_{page_index+1}.jpg")
        page.save(output_path, "JPEG", quality=95)

def delete_folder(folder_path):
    """Delete all .jpg and .jpeg files in the folder, then remove the folder itself."""
    if not os.path.exists(folder_path):
        print(f"Folder does not exist: {folder_path}")
        return

    # Delete .jpg and .jpeg files
    jpg_files = glob.glob(os.path.join(folder_path, "*.jpg"))
    jpg_files += glob.glob(os.path.join(folder_path, "*.jpeg"))
    jpg_files += glob.glob(os.path.join(folder_path, "*.png"))

    for file in jpg_files:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")

    # Remove the folder itself
    try:
        os.rmdir(folder_path)
        print(f"Folder removed: {folder_path}")
    except Exception as e:
        print(f"Error removing folder {folder_path}: {e}")

def jpgs_to_pdf_with_background(input_folder, background_path, output_pdf="output.pdf"):
    # Gather all JPG files in the folder
    jpg_files = sorted([
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(".jpg")
    ])

    if not jpg_files:
        print("No JPG files found in folder.")
        return

    # Open the background image once
    background = Image.open(background_path).convert("RGB")

    pages = []
    for jpg in jpg_files:
        img = Image.open(jpg).convert("RGB")
        pages.append(img)
        pages.append(background.copy())  # Insert background after each image

    # Save all pages to PDF
    pages[0].save(output_pdf, save_all=True, append_images=pages[1:])
    print(f"PDF saved as {output_pdf}")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a decklist of card images into a printable PDF."
    )

    parser.add_argument(
        "--decklist",
        type=str,
        default="test.txt",
        help="Path to the decklist text file (default: Xyris.txt)"
    )

    parser.add_argument(
        "--card_back",
        type=str,
        default="background.jpg",
        help="Path to the card back image used between cards (default: background.jpg)"
    )

    parser.add_argument(
        "--deckname",
        type=str,
        default="ready_to_print.pdf",
        help="Output path for the generated PDF (default: deck_ready_to_print.pdf)"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Validation
    if not args.decklist.lower().endswith(".txt"):
        print(f"Error: decklist must be a .txt file: {args.decklist}")
        sys.exit(1)
    if not args.card_back.lower().endswith(".jpg"):
        print(f"Error: card_back must be a .jpg file: {args.card_back}")
        sys.exit(1)
    if not args.deckname.lower().endswith(".pdf"):
        print(f"Error: deckname must be a .pdf file: {args.deckname}")
        sys.exit(1)

    decklist = args.decklist
    card_back = args.card_back
    save_loc = args.deckname

    df = download_card_images(decklist, output_dir="temp_images")
    print(df.head())
    images_to_page("temp_images", output_folder= "temp_sheets")
    delete_folder("temp_images")  # delete the temporary storage
    jpgs_to_pdf_with_background("temp_sheets", background_path=card_back, output_pdf=save_loc)
    delete_folder("temp_sheets")
