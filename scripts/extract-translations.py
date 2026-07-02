import re
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    "src/components/Navigation.tsx",
    "src/components/StoryRecorder.tsx",
    "src/pages/CreateStoryPage.tsx",
    "src/pages/HomePage.tsx",
    "src/pages/LoginPage.tsx",
    "src/components/TopicSelector.tsx",
]

# Matches <BiLabel ...zh="..." ...en="..."... /> or <BiText zh="..." en="..." />
# attrs captured generically, then parsed below. Only matches plain double-quoted
# string literals for zh/en (skips {`...`} dynamic expressions).
TAG_RE = re.compile(
    r'<Bi(Label|Text)\b((?:\s+[a-zA-Z]+=(?:"(?:[^"\\]|\\.)*"|\{[^{}]*\}|true|false))*)\s*/>',
    re.DOTALL,
)
ATTR_RE = re.compile(r'([a-zA-Z]+)=(?:"((?:[^"\\]|\\.)*)"|(\{[^{}]*\})|(\btrue\b|\bfalse\b))')

translations = {}
key_by_pair = {}


def slugify(text, maxlen=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower()
    return s[:maxlen] or "str"


def make_key(zh, en):
    pair = (zh, en)
    if pair in key_by_pair:
        return key_by_pair[pair]
    base = slugify(en) if en else slugify(zh)
    key = base
    i = 2
    while key in translations and translations[key] != {"zh": zh, "en": en}:
        key = f"{base}_{i}"
        i += 1
    translations[key] = {"zh": zh, "en": en}
    key_by_pair[pair] = key
    return key


def replace_in_file(path):
    full = os.path.join(ROOT, path)
    with open(full, "r", encoding="utf-8") as f:
        content = f.read()

    def repl(m):
        tag = m.group(1)  # Label or Text
        attrs_blob = m.group(2)
        attrs = {}
        order = []
        for am in ATTR_RE.finditer(attrs_blob):
            name = am.group(1)
            if am.group(2) is not None:
                value = ("str", am.group(2))
            elif am.group(3) is not None:
                value = ("expr", am.group(3))
            else:
                value = ("bool", am.group(4))
            attrs[name] = value
            order.append(name)

        zh = attrs.get("zh")
        en = attrs.get("en")
        if zh is None or en is None or zh[0] != "str" or en[0] != "str":
            return m.group(0)  # dynamic or incomplete, leave untouched

        key = make_key(zh[1], en[1])
        extra = ""
        for name in order:
            if name in ("zh", "en"):
                continue
            kind, val = attrs[name]
            if kind == "str":
                extra += f' {name}="{val}"'
            elif kind == "expr":
                extra += f" {name}={val}"
            else:
                extra += f" {name}" if val == "true" else f' {name}={{{val}}}'
        return f'<Bi{tag} k="{key}"{extra} />'

    new_content = TAG_RE.sub(repl, content)
    with open(full, "w", encoding="utf-8") as f:
        f.write(new_content)


for f in FILES:
    replace_in_file(f)

out_path = os.path.join(ROOT, "src", "i18n", "translations.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(translations, f, ensure_ascii=False, indent=2, sort_keys=True)
    f.write("\n")

print(f"Wrote {len(translations)} translation keys to {out_path}")
