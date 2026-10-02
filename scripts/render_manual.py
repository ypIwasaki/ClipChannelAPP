"""Render the Markdown manual as a portable, offline HTML page.

Documentation-only dependency: Markdown (python -m pip install Markdown).
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import struct
import markdown
from build_manual import load_inputs, validate, build, check_tables

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / 'docs' / 'manual'


class GalleryCheck(HTMLParser):
    """Read rendered image/table pairs, so HTML preserves the Markdown contract."""
    def __init__(self):
        super().__init__()
        self.pending = None
        self.in_table = False
        self.in_cell = False
        self.row = []
        self.cell = ""
        self.numbers = []
        self.images = {}

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "img" and attrs.get("src", "").startswith("images/"):
            if self.pending:
                raise ValueError("Image has no numbered table")
            self.pending = attrs["src"].removeprefix("images/")
            if self.pending in self.images:
                raise ValueError("Duplicate manual image")
        elif tag == "table" and self.pending:
            self.in_table = True
            self.numbers = []
        elif tag == "tr" and self.in_table:
            self.row = []
        elif tag == "td" and self.in_table:
            self.in_cell = True
            self.cell = ""

    def handle_data(self, data):
        if self.in_cell:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.in_table:
            self.in_cell = False
            self.row.append(self.cell.strip())
        elif tag == "tr" and self.in_table and self.row:
            if len(self.row) != 3 or not all(self.row):
                raise ValueError("Incomplete HTML explanation row")
            self.numbers.append(int(self.row[0]))
        elif tag == "table" and self.in_table:
            self.images[self.pending] = self.numbers
            self.pending = None
            self.in_table = False


def verify_html(body, screens):
    check = GalleryCheck()
    check.feed(body)
    expected = {screen["file"]: list(range(1, len(screen["boxes"]) + 1)) for screen in screens}
    if check.pending or check.images != expected:
        raise ValueError("HTML images and numbered explanation rows do not match")


def main():
    source = (MANUAL / 'manual.md').read_text(encoding='utf-8')
    screens, content = load_inputs()
    validate(screens, content)
    check_tables(source, screens)
    if source != build(screens, content):
        raise ValueError("manual.md is out of date; run scripts/build_manual.py")
    renderer = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc'],
                                 extension_configs={'toc': {'toc_depth': '2-3'}})
    body = renderer.convert(source)
    verify_html(body, screens)
    # Lazy loading avoids decoding dozens of screenshots at startup.
    def image_attributes(match):
        tag = match.group(0)
        filename = re.search(r'src="([^"]+)"', tag).group(1)
        image = MANUAL / filename
        width, height = struct.unpack('>II', image.read_bytes()[16:24])
        return tag.replace('<img ', f'<img loading="lazy" decoding="async" tabindex="0" '
                           f'width="{width}" height="{height}" style="max-width:{width}px" ')
    body = re.sub(r'<img\s[^>]+>', image_attributes, body)
    page = '''<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClipChannelAPP 使い方マニュアル</title>
<style>
:root{color-scheme:light;--ink:#172f4a;--blue:#175da6;--line:#cfdae8}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f7fc;color:var(--ink);font:16px/1.85 "Yu Gothic UI","Meiryo",sans-serif}
a{color:var(--blue)}header{padding:18px 28px;background:#173e69;color:white}header strong{font-size:21px}header a{color:white;margin-left:20px}
.layout{display:grid;grid-template-columns:300px minmax(0,1fr);max-width:1560px;margin:auto}
nav{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;padding:22px 18px;background:#eaf1fa;border-right:1px solid var(--line);font-size:14px}
nav ul{list-style:none;padding-left:12px}nav>div>ul{padding-left:0}nav li{margin:7px 0}nav a{text-decoration:none}nav a:hover{text-decoration:underline}
main{padding:30px 42px;min-width:0;background:white}h1{font-size:32px;margin:0 0 18px}h2{margin:52px 0 20px;padding-top:15px;border-top:3px solid #bad0e8;font-size:25px;scroll-margin-top:20px}h3{margin-top:32px;font-size:20px;scroll-margin-top:20px}
p{margin:14px 0}li{margin:5px 0}strong{color:#113b67}img{display:block;width:100%;max-width:1360px;height:auto;margin:20px auto;border:1px solid var(--line);border-radius:5px;cursor:zoom-in;box-shadow:0 3px 14px #123b6512}
img:focus-visible{outline:3px solid var(--blue)}code{font-size:.92em;background:#eef3f9;padding:2px 5px;border-radius:4px;overflow-wrap:anywhere}pre{overflow:auto;background:#eef3f9;padding:18px;border-radius:6px;line-height:1.6}pre code{padding:0}
table{border-collapse:collapse;width:100%;font-size:15px;margin:20px 0}th,td{border:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eaf1fa}tr:nth-child(even){background:#f7faff}
.top{position:fixed;bottom:20px;right:20px;background:#173e69;color:white;padding:8px 15px;border-radius:6px;text-decoration:none}
dialog{max-width:96vw;max-height:96vh;padding:15px;border:0;border-radius:8px;background:#f4f8ff}dialog::backdrop{background:#102138bb}dialog button{font:inherit;cursor:pointer;border:1px solid #abbdd2;background:white;border-radius:4px;padding:6px 18px}dialog img{width:auto;max-width:90vw;max-height:80vh;object-fit:contain;margin:12px auto;cursor:default}dialog p{margin:8px 0;font-size:14px}
@media(max-width:1050px){.layout{grid-template-columns:240px minmax(0,1fr)}main{padding:25px}nav{font-size:13px}}
@media(max-width:760px){.layout{display:block}nav{position:static;height:auto;max-height:300px;border-bottom:1px solid var(--line)}main{padding:22px 16px}h1{font-size:25px}h2{font-size:22px}table{font-size:13px}header{padding:16px}header a{display:block;margin-left:0}}
@media print{nav,header,.top,dialog{display:none}.layout{display:block}main{padding:0}h2{break-before:page}img,table{break-inside:avoid}a{color:inherit}body{font-size:11pt}}
</style></head><body id="top">
<header><strong>ClipChannelAPP 操作ガイド</strong><a href="manual.md">Markdown版</a><a href="screens.json">画面一覧</a></header>
<div class="layout"><nav aria-label="目次"><strong>目次</strong>''' + renderer.toc + '''</nav>
<main>''' + body + '''</main></div><a class="top" href="#top">先頭へ</a>
<dialog id="image-view"><button type="button" id="close-image">閉じる（Esc）</button><p id="image-caption"></p><img id="large-image" alt=""></dialog>
<script>
const viewer=document.querySelector('#image-view'),large=document.querySelector('#large-image'),caption=document.querySelector('#image-caption');
function openImage(image){large.src=image.getAttribute('src');large.alt=image.alt;caption.textContent=image.alt;viewer.showModal();}
document.querySelectorAll('main img').forEach(image=>{image.addEventListener('click',()=>openImage(image));image.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openImage(image);}});});
document.querySelector('#close-image').addEventListener('click',()=>viewer.close());
viewer.addEventListener('click',event=>{if(event.target===viewer){const bounds=viewer.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)viewer.close();}});
</script></body></html>'''
    destination = MANUAL / 'index.html'
    destination.write_text(page, encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    main()
