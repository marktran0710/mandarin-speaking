
def stories() -> list[dict]:
    result = []
    for lesson, parts in LESSONS.items():
        for order, key in enumerate(("d1", "d2", "r"), 1):
            title, lines = parts[key]
            slug = f"modern-chinese-l{lesson}-{'dialogue-1' if key == 'd1' else 'dialogue-2' if key == 'd2' else 'reading'}"
            image_key = f"l{lesson}{key}"
            result.append({"id": slug, "title": f"第{lesson}課 {title}",
                           "frames": frame_payload(image_key, lines), "published": True,
                           "lessonNumber": lesson, "lessonSubOrder": order,
                           "rubricScores": RUBRIC})
    return result

def seed() -> None:
    for story in stories():
        req = urllib.request.Request(API, data=json.dumps(story, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"{story['id']}: HTTP {response.status}")
        print(f"published {story['id']} ({len(story['frames'])} frames)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-images", action="store_true")
    parser.add_argument("--prepare-bubble-images", action="store_true")
    parser.add_argument("--refresh-bubble-urls", action="store_true")
    parser.add_argument("--apply-dialogue-bubble-text", action="store_true")
    parser.add_argument("--refresh-dialogue-full-urls", action="store_true")
    parser.add_argument("--apply-v2-dialogue-bubble-text", action="store_true")
    parser.add_argument("--refresh-v2-dialogue-full-urls", action="store_true")
    parser.add_argument("--apply-v3-dialogue-bubbles", action="store_true")
    parser.add_argument("--refresh-v3-dialogue-urls", action="store_true")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    if args.prepare_images:
        prepare_images()
    if args.prepare_bubble_images:
        prepare_bubble_images()
    if args.refresh_bubble_urls:
        refresh_published_bubble_urls()
    if args.apply_dialogue_bubble_text:
        apply_dialogue_bubble_text()
    if args.refresh_dialogue_full_urls:
        refresh_dialogue_full_urls()
    if args.apply_v2_dialogue_bubble_text:
        apply_v2_dialogue_bubble_text()
    if args.refresh_v2_dialogue_full_urls:
        refresh_v2_dialogue_full_urls()
    if args.apply_v3_dialogue_bubbles:
        apply_v3_dialogue_bubbles()
    if args.refresh_v3_dialogue_urls:
        refresh_v3_dialogue_urls()
    if args.seed:
        seed()
