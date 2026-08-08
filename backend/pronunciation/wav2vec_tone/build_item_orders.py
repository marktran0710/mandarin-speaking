"""Phase D1 — generate the counterbalanced item orders and the tracker template.

Deterministic construction, not a search: the order is built so that no two
adjacent trials share a tone, and so that each item visits each block of the
session across orders. Nothing here uses any outcome.
"""
import collections
import csv
from pathlib import Path

DATA = Path(r"D:\hautran\Lab\mandarin-speaking\backend\pronunciation\wav2vec_tone\data")

items = list(csv.DictReader((DATA / "fresh_validation_items.csv").open(encoding="utf-8")))
by_tone = collections.defaultdict(list)
for row in items:
    by_tone[int(row["expected_tone"])].append(row)
for tone in by_tone:
    by_tone[tone].sort(key=lambda r: r["item_id"])
assert all(len(v) == 4 for v in by_tone.values()), "expected 4 items per tone"

# Six base tone permutations (one per rotation class of the four tones) so the
# orders are not variations of a single cycle. Every order is a rotation of its
# base, which guarantees no tone repeat at a block boundary.
BASES = ([1, 2, 3, 4], [1, 2, 4, 3], [1, 3, 2, 4],
         [1, 3, 4, 2], [1, 4, 2, 3], [1, 4, 3, 2])
N_ORDERS = 12

rows = []
for k in range(N_ORDERS):
    base, rot = BASES[k // 2], k % 4
    order_id = f"O{k + 1:02d}"
    position = 0
    for block in range(4):
        for i in range(4):
            tone = base[(rot + block + i) % 4]
            # The tone rotation and the item cycle must advance at different
            # rates. If both step with k, every order is just a block-rotation
            # of the first one, which counterbalances nothing.
            item = by_tone[tone][(block + 3 * k) % 4]
            position += 1
            rows.append({
                "order_id": order_id, "position": position, "block": block + 1,
                "item_id": item["item_id"],
                "traditional_character": item["traditional_character"],
                "expected_pinyin": item["expected_pinyin"],
                "expected_tone": tone,
            })

# --- verification ---------------------------------------------------------
per_order = collections.defaultdict(list)
for row in rows:
    per_order[row["order_id"]].append(row)

adjacent_same_tone = 0
for order_id, seq in per_order.items():
    assert len(seq) == 16, order_id
    assert len({r["item_id"] for r in seq}) == 16, f"{order_id} repeats an item"
    tones = collections.Counter(r["expected_tone"] for r in seq)
    assert set(tones.values()) == {4}, f"{order_id} tone imbalance {tones}"
    adjacent_same_tone += sum(
        1 for a, b in zip(seq, seq[1:]) if a["expected_tone"] == b["expected_tone"])

distinct = len({tuple(r["item_id"] for r in seq) for seq in per_order.values()})

# A cyclic block rotation of another order is a distinct tuple but is not real
# counterbalancing, so it is checked for separately.
def blocks_of(seq):
    return tuple(tuple(r["item_id"] for r in seq[b * 4:(b + 1) * 4]) for b in range(4))

rotations = 0
sequences = [blocks_of(seq) for seq in per_order.values()]
for a_index, a in enumerate(sequences):
    for b in sequences[a_index + 1:]:
        if any(a == b[shift:] + b[:shift] for shift in range(4)):
            rotations += 1
block_spread = collections.defaultdict(set)
for row in rows:
    block_spread[row["item_id"]].add(row["block"])
mean_pos = {i: sum(r["position"] for r in rows if r["item_id"] == i) / N_ORDERS
            for i in sorted({r["item_id"] for r in rows})}

with (DATA / "fresh_validation_item_orders.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

TRACKER = ["participant_id", "order_id", "pilot_only", "consent_complete",
           "session_complete", "first_attempts_complete_16", "technical_failures",
           "usability_complete", "rater_export_ready", "withdrew",
           "withdrawal_reason", "session_date", "device_used", "notes"]
with (DATA / "fresh_validation_collection_tracker_TEMPLATE.csv").open(
        "w", newline="", encoding="utf-8") as handle:
    csv.writer(handle).writerow(TRACKER)

print(f"orders written        : {N_ORDERS} x 16 = {len(rows)} rows")
print(f"distinct sequences    : {distinct}")
print(f"block-rotation pairs  : {rotations}")
print(f"adjacent same-tone    : {adjacent_same_tone}/{N_ORDERS * 15}")
print(f"items reaching all 4 blocks: "
      f"{sum(1 for v in block_spread.values() if len(v) == 4)}/16")
print(f"mean position range   : {min(mean_pos.values()):.2f} - {max(mean_pos.values()):.2f} "
      f"(uniform would be 8.50)")
