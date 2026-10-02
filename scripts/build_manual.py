"""Build and validate the illustrated manual from captured UI controls."""
import argparse
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"


def load_inputs():
    screens = json.loads((MANUAL / "screens.json").read_text(encoding="utf-8"))
    content = json.loads((MANUAL / "manual_content.json").read_text(encoding="utf-8"))
    return screens, content


def validate(screens, content):
    errors = []
    files, controls, covered_sections = set(), set(), set()
    for screen in screens:
        filename = screen["file"]
        if filename in files or Path(filename).name != filename:
            errors.append(f"Duplicate or unsafe image filename: {filename}")
        files.add(filename)
        image = MANUAL / "images" / filename
        if not image.is_file():
            errors.append(f"Missing image: {filename}")
            continue
        raw = image.read_bytes()
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"Not a PNG: {filename}")
            continue
        width, height = struct.unpack(">II", raw[16:24])
        boxes = screen["boxes"]
        if [box["number"] for box in boxes] != list(range(1, len(boxes) + 1)):
            errors.append(f"Numbers must be consecutive from 1: {filename}")
        if not boxes:
            errors.append(f"No annotated controls: {filename}")
        local_controls = set()
        for box in boxes:
            identity = box["control_id"]
            if identity in local_controls:
                errors.append(f"Duplicate control on one image: {filename}: {identity}")
            local_controls.add(identity)
            controls.add(identity)
            left, top, right, bottom = box["bounds"]
            if not (0 <= left < right < width and 0 <= top < bottom < height):
                errors.append(f"Annotation outside image: {filename}: {identity}")
            badge = box.get("badge_bounds")
            if badge is not None:
                a, b, c, d = badge
                if not (0 <= a < c < width and 0 <= b < d < height):
                    errors.append(f"Number badge outside image: {filename}: {identity}")
                for other in boxes:
                    if other["number"] >= box["number"]:
                        continue
                    previous = other.get("badge_bounds")
                    if previous:
                        x, y, z, w = previous
                        if max(a, x) < min(c, z) and max(b, y) < min(d, w):
                            errors.append(f"Number badges overlap: {filename}: {identity}")
            item = content["controls"].get(identity)
            if not item or not item.get("label", "").strip() or not item.get("description", "").strip():
                errors.append(f"Missing explanation: {identity}")
            elif item["label"] != box["label"]:
                errors.append(f"Capture label differs from explanation: {identity}")
        if "work" in screen:
            covered_sections.add((screen["work"], screen["tab"], screen["role"], screen["title"]))
    stale = set(content["controls"]) - controls
    if stale:
        errors.append(f"Unused explanations: {sorted(stale)}")
    inventory_path = MANUAL / "control-inventory.json"
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        expected_sections = {(s["work"], s["tab"], s["role"], s["title"]) for s in inventory if "work" in s}
        if covered_sections != expected_sections:
            errors.append("Captured sections do not match the current UI inventory")
        expected_controls = {box["control_id"]: box for screen in inventory for box in screen["controls"]}
        expected = set(expected_controls)
        missing, extra = expected - controls, controls - expected
        if missing:
            errors.append(f"Controls never photographed: {sorted(missing)}")
        if extra:
            errors.append(f"Captured controls no longer in the UI: {sorted(extra)}")
        for screen in screens:
            for box in screen["boxes"]:
                current = expected_controls.get(box["control_id"])
                if current and current["widget_class"] != box["widget_class"]:
                    errors.append(f"Control type changed: {box['control_id']}")
                if current and current["widget_class"] in ("Button", "TButton", "Checkbutton", "TCheckbutton"):
                    if current["label"] != box["label"]:
                        errors.append(f"Button label changed in current UI: {box['control_id']}")
    else:
        errors.append("Missing control-inventory.json; run manual_capture.py --inventory-only")
    if errors:
        raise ValueError("\n".join(errors))


def cell(value):
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_screen(screen, content):
    label = screen["title"]
    if "tab" in screen:
        label = f"{screen['tab']}：{label}"
    page_count = screen.get("page_count", 1)
    if page_count > 1:
        label += f"（{screen['page_index']}/{page_count}）"
    lines = [f'<a id="{Path(screen["file"]).stem}"></a>', "", f"### {label}", ""]
    if "work" in screen:
        lines += [f"移動：**{screen['work']} → {screen['tab']} → 表示「{screen['role']}」→ 項目「{screen['title']}」**。", ""]
    note = content.get("screens", {}).get(screen["screen_id"], {}).get("note")
    if note:
        lines += [note, ""]
    if page_count > 1:
        lines += ["詳細設定の内部をスクロールして、この範囲を表示します。", ""]
    lines += [f"![{label}](images/{screen['file']})", "", "| 画像の番号 | 画面の項目 | 説明・操作 |", "|---|---|---|"]
    for box in screen["boxes"]:
        item = content["controls"][box["control_id"]]
        lines.append(f"| {box['number']} | {cell(item['label'])} | {cell(item['description'])} |")
    lines += ["", f"この画像の番号は **{len(screen['boxes'])}個**、説明表は **{len(screen['boxes'])}件**です。", ""]
    if screen.get("sample"):
        lines += [f"撮影条件：{screen['sample']}", ""]
    return "\n".join(lines)


def build(screens, content):
    intro = (MANUAL / "workflow.md").read_text(encoding="utf-8").rstrip()
    editor = (MANUAL / "editor-and-management.md").read_text(encoding="utf-8").rstrip()
    gallery = ['<a id="screen-reference"></a>', "", "## 画面ごとの番号説明", "", "各画像右側の番号は、直下の表の同じ番号に対応します。手順の実施順とは別です。番号は画像ごとに1から振り直します。", ""]
    for screen in screens:
        gallery.append(render_screen(screen, content))
    return intro + "\n\n" + editor + "\n\n" + "\n".join(gallery).rstrip() + "\n"


def check_tables(source, screens):
    pairs = re.findall(r"!\[[^\]]*\]\(images/([^\)]+)\)\n\n(\| 画像の番号 .*?)(?=\n\n)", source, re.S)
    expected = {screen["file"]: list(range(1, len(screen["boxes"]) + 1)) for screen in screens}
    actual = {}
    for filename, table in pairs:
        if filename in actual:
            raise ValueError(f"Repeated image: {filename}")
        actual[filename] = [int(number) for number in re.findall(r"^\| (\d+) \|", table, re.M)]
    if actual != expected:
        raise ValueError("Manual images and numbered explanation rows do not match")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check saved outputs without writing")
    args = parser.parse_args()
    screens, content = load_inputs()
    validate(screens, content)
    result = build(screens, content)
    check_tables(result, screens)
    destination = MANUAL / "manual.md"
    if args.check:
        if destination.read_text(encoding="utf-8") != result:
            raise ValueError("manual.md is out of date; run scripts/build_manual.py")
    else:
        destination.write_text(result, encoding="utf-8")
    print(f"Verified {len(screens)} images / {sum(len(s['boxes']) for s in screens)} numbered explanations")


if __name__ == "__main__":
    main()
