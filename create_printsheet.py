import argparse
import glob
import math
import os
import re
import sys
import pandas as pd
import requests
from PIL import Image, ImageDraw
from urllib.parse import quote
import time

def sanitize_filename(name):
    """Replace illegal Windows filename characters with underscores."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def download_card_images(decklist_path, output_dir="scryfall_images"):
    os.makedirs(output_dir, exist_ok=True)

    # Read decklist file
    with open(decklist_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Set custom headers required by Scryfall
    headers = {
        "User-Agent": "MTGPrintSheetGenerator/1.0",
        "Accept": "application/json"
    }

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
        r = requests.get(url, headers=headers)
        time.sleep(0.1)
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
            print(f"⚠️ No image URL found for: {name}")
            continue

        print(f"{name}")

        # Fetch actual image with headers included
        try:
            img_resp = requests.get(image_url, headers=headers)
            time.sleep(0.1)

            if img_resp.status_code != 200:
                print(f"⚠️ Image HTTP Error {img_resp.status_code} for {name}")
                continue

            img_data = img_resp.content

        except Exception as e:
            print(f"⚠️ Failed to request image for {name}: {e}")
            continue

        # Save N copies
        for i in range(qty):
            safe_name = sanitize_filename(f"{name}_{i+1}")
            filename = f"{safe_name}.png"
            filepath = os.path.join(output_dir, filename)

            try:
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

def images_to_page(input_folder, output_folder="output_sheets", fill_borders_black=False):
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

            # Composite on white background
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.split()[3])

            col = i % cols
            row = i // cols
            x = margin_left + col * card_width
            y = margin_top + row * card_height

            page.paste(bg, (x, y))

            # Draw larger black diamonds in corners if requested
            if fill_borders_black:
                draw = ImageDraw.Draw(page)
                # original diamond size (you previously used 0.07*card_width*1.3)
                diamond_size = int(0.07 * card_width * 1.3)
                half = diamond_size // 2

                # For each corner we decide whether the corner lies on the page edge.
                # If so, draw only the inward triangle; otherwise draw the full diamond.
                # corner order: top-left, top-right, bottom-left, bottom-right
                corners_info = [
                    # (cx, cy, is_edge) where is_edge True => draw triangle inside
                    (x, y, (col == 0) or (row == 0)),                             # top-left
                    (x + card_width, y, (col == cols - 1) or (row == 0)),        # top-right
                    (x, y + card_height, (col == 0) or (row == rows - 1)),      # bottom-left
                    (x + card_width, y + card_height, (col == cols - 1) or (row == rows - 1)),  # bottom-right
                ]

                for idx, (cx, cy, is_edge) in enumerate(corners_info):
                    if not is_edge:
                        # full diamond (rotated square)
                        diamond = [
                            (cx, cy - half),  # up
                            (cx + half, cy),  # right
                            (cx, cy + half),  # down
                            (cx - half, cy)   # left
                        ]
                        draw.polygon(diamond, fill="black")
                    else:
                        # draw only the inward triangle (quarter of the diamond)
                        # map corner index to which quarter to keep:
                        # 0: top-left -> keep bottom-right triangle
                        # 1: top-right -> keep bottom-left triangle
                        # 2: bottom-left -> keep top-right triangle
                        # 3: bottom-right -> keep top-left triangle
                        if idx == 0:  # top-left: keep bottom-right => center, right, down
                            tri = [(cx, cy), (cx + half, cy), (cx, cy + half)]
                        elif idx == 1:  # top-right: keep bottom-left => center, left, down
                            tri = [(cx, cy), (cx - half, cy), (cx, cy + half)]
                        elif idx == 2:  # bottom-left: keep top-right => center, right, up
                            tri = [(cx, cy), (cx + half, cy), (cx, cy - half)]
                        else:  # idx == 3 bottom-right: keep top-left => center, left, up
                            tri = [(cx, cy), (cx - half, cy), (cx, cy - half)]
                        draw.polygon(tri, fill="black")

        output_path = os.path.join(output_folder, f"card_sheet_{page_index+1}.jpg")
        page.save(output_path, "JPEG", quality=95)

def images_to_page2(input_folder, output_folder="output_sheets"):
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

def resize_background(background, fill_borders_black=False):
    # Page setup
    page_width_in, page_height_in = 8.5, 11
    dpi = 300
    page_width = int(page_width_in * dpi)
    page_height = int(page_height_in * dpi)

    # Card (tile) size in inches
    card_width_in, card_height_in = 2.5, 3.5
    card_width = int(card_width_in * dpi)
    card_height = int(card_height_in * dpi)

    # Margins in inches
    margin_left_in, margin_top_in = 0.5, 0.25
    margin_left = int(margin_left_in * dpi)
    margin_top = int(margin_top_in * dpi)

    # Compute grid
    cols = (page_width - margin_left) // card_width
    rows = (page_height - margin_top) // card_height

    # Stretch background to card slot, preserving requested size
    orig_w, orig_h = background.size
    bg_resized = background.resize((card_width, card_height), Image.LANCZOS)

    # Compute and print stretch ratios
    stretch_x = card_width / orig_w
    stretch_y = card_height / orig_h
    print(f"Resized background from {orig_w}×{orig_h} → {card_width}×{card_height} "
          f"(stretch_x = {stretch_x:.2f}, stretch_y = {stretch_y:.2f})")

    # Create tiled background
    background_tiled = Image.new("RGB", (page_width, page_height), "white")
    draw = ImageDraw.Draw(background_tiled)

    for row in range(rows):
        for col in range(cols):
            x = margin_left + col * card_width
            y = margin_top + row * card_height
            background_tiled.paste(bg_resized, (x, y))

            if fill_borders_black:
                # same diamond logic as front-side
                diamond_size = int(0.07 * card_width * 1.3)
                half = diamond_size // 2

                corners_info = [
                    (x, y, (col == 0) or (row == 0)),                             # top-left
                    (x + card_width, y, (col == cols - 1) or (row == 0)),        # top-right
                    (x, y + card_height, (col == 0) or (row == rows - 1)),       # bottom-left
                    (x + card_width, y + card_height, (col == cols - 1) or (row == rows - 1)),  # bottom-right
                ]

                for idx, (cx, cy, is_edge) in enumerate(corners_info):
                    if not is_edge:
                        diamond = [
                            (cx, cy - half),
                            (cx + half, cy),
                            (cx, cy + half),
                            (cx - half, cy)
                        ]
                        draw.polygon(diamond, fill="black")
                    else:
                        # only inward quarter triangles for outer edges
                        if idx == 0:  # top-left
                            tri = [(cx, cy), (cx + half, cy), (cx, cy + half)]
                        elif idx == 1:  # top-right
                            tri = [(cx, cy), (cx - half, cy), (cx, cy + half)]
                        elif idx == 2:  # bottom-left
                            tri = [(cx, cy), (cx + half, cy), (cx, cy - half)]
                        else:  # bottom-right
                            tri = [(cx, cy), (cx - half, cy), (cx, cy - half)]
                        draw.polygon(tri, fill="black")

    return background_tiled

def jpgs_to_pdf_with_background(input_folder, background_path, args, output_pdf="output.pdf"):
    # Gather all sheets of magic cards
    jpg_files = sorted([
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(".jpg")
    ])

    if not jpg_files:
        print("No JPG files found in folder.")
        return

    # Create background image.
    background = Image.open(background_path).convert("RGB")
    background_tiled = resize_background(background, fill_borders_black= args.fill_borders)

    pages = []
    for jpg in jpg_files:
        img = Image.open(jpg).convert("RGB")
        pages.append(img)
        pages.append(background_tiled.copy())

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

    parser.add_argument(
        "--fill_borders",
        action="store_true",
        help="If set, fills the borders and gaps between cards with black instead of white."
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
        args.deckname = args.deckname.split(".")[0] + ".pdf"

    decklist = args.decklist
    card_back = args.card_back
    save_loc = args.deckname

    df = download_card_images(decklist, output_dir="temp_images")
    images_to_page("temp_images", output_folder= "temp_sheets", fill_borders_black= args.fill_borders)
    delete_folder("temp_images")  # delete the temporary storage
    jpgs_to_pdf_with_background("temp_sheets", background_path=card_back, output_pdf=save_loc, args=args)
    delete_folder("temp_sheets")
