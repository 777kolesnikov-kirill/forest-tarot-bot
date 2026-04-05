import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from cards import CARDS

output_path = os.path.join(os.path.dirname(__file__), "cards_export.txt")

with open(output_path, "w", encoding="utf-8") as f:
    for card in CARDS:
        f.write(f"Card name: {card['name']}\n")
        f.write(f"Description: {card['description']}\n")
        f.write("\n")

print(f"Exported {len(CARDS)} cards to {output_path}")
