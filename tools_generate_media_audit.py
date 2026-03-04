#!/usr/bin/env python3
import hashlib
import json
import mimetypes
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from typing import Any

ROOT = Path('.')
OUTPUT = ROOT / 'media-audit.html'

MEDIA_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tif', '.tiff', '.ico', '.avif',
    '.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv', '.wmv', '.flv', '.mpeg', '.mpg',
    '.mp3', '.wav', '.m4a', '.ogg', '.oga', '.flac', '.aac', '.opus',
    '.pdf'
}

# Exclude UI/decorative assets that are typically bundled with themes/plugins and
# are usually low copyright-risk compared to editorial media (photos/videos/docs).
LOW_RISK_PATH_PARTS = [
    '/wp-content/plugins/',
    '/wp-content/themes/',
    '/wp-includes/',
    '/skin-ilightbox/',
    '/fontawesome/',
    '/eleganticons',
]

LOW_RISK_FILENAME_PATTERNS = [
    'icon', 'icons', 'sprite', 'gradient', 'pattern', 'shadow', 'loader',
    'preloader', 'arrow-', 'arrow_', 'button', 'buttons', 'close',
    'fullscreen', 'thumb-overlay', 'now-loading', 'x-mark', 'gridtile', 'fade', 'backblue',
]

SIZE_SUFFIX_RE = re.compile(r'^(?P<base>.+)-(?P<w>\d+)x(?P<h>\d+)$', re.IGNORECASE)
FFPROBE_CACHE: dict[str, dict[str, Any]] = {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_svg(path: Path) -> dict[str, Any]:
    try:
        txt = path.read_text(encoding='utf-8', errors='ignore')
        width = re.search(r'\bwidth=["\']([^"\']+)["\']', txt)
        height = re.search(r'\bheight=["\']([^"\']+)["\']', txt)
        viewbox = re.search(r'\bviewBox=["\']([^"\']+)["\']', txt)
        return {
            'image_width': width.group(1) if width else None,
            'image_height': height.group(1) if height else None,
            'svg_viewbox': viewbox.group(1) if viewbox else None,
        }
    except Exception:
        return {}


def parse_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as img:
            width, height = img.size
            fmt = img.format
            mode = img.mode
        return {
            'image_width': width,
            'image_height': height,
            'image_format': fmt,
            'image_mode': mode,
        }
    except Exception:
        return {}


def parse_av(path: Path) -> dict[str, Any]:
    key = path.as_posix()
    if key in FFPROBE_CACHE:
        return FFPROBE_CACHE[key]

    try:
        proc = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if proc.returncode != 0:
            FFPROBE_CACHE[key] = {}
            return {}

        data = json.loads(proc.stdout)
        meta: dict[str, Any] = {}

        fmt = data.get('format', {})
        if 'duration' in fmt:
            try:
                meta['duration_seconds'] = round(float(fmt['duration']), 3)
            except Exception:
                pass
        if 'bit_rate' in fmt:
            meta['bit_rate'] = fmt.get('bit_rate')

        for stream in data.get('streams', []):
            codec_type = stream.get('codec_type')
            if codec_type == 'video':
                if stream.get('width'):
                    meta['video_width'] = stream['width']
                if stream.get('height'):
                    meta['video_height'] = stream['height']
                if stream.get('codec_name'):
                    meta['video_codec'] = stream['codec_name']
                if stream.get('r_frame_rate'):
                    meta['video_fps_raw'] = stream['r_frame_rate']
            elif codec_type == 'audio':
                if stream.get('codec_name'):
                    meta['audio_codec'] = stream['codec_name']
                if stream.get('sample_rate'):
                    meta['audio_sample_rate'] = stream['sample_rate']
                if stream.get('channels'):
                    meta['audio_channels'] = stream['channels']

        FFPROBE_CACHE[key] = meta
        return meta
    except Exception:
        FFPROBE_CACHE[key] = {}
        return {}


def file_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    ext = path.suffix.lower()
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or 'application/octet-stream'
    rel = str(path.as_posix()).lstrip('./')

    entry: dict[str, Any] = {
        'path': rel,
        'filename': path.name,
        'extension': ext,
        'mime_type': mime,
        'size_bytes': stat.st_size,
        'size_kb': round(stat.st_size / 1024, 2),
        'modified_utc': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        'sha256': sha256_file(path),
    }

    if ext == '.svg':
        entry.update(parse_svg(path))
    elif mime.startswith('image/'):
        entry.update(parse_image(path))
    elif mime.startswith('video/') or mime.startswith('audio/'):
        entry.update(parse_av(path))

    return entry


def gather_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if '.git' in dirnames:
            dirnames.remove('.git')
        for name in filenames:
            p = Path(dirpath) / name
            if p == OUTPUT:
                continue
            if p.suffix.lower() in MEDIA_EXTENSIONS:
                files.append(p)
    files.sort()
    return files


def gather_html_files() -> list[Path]:
    html_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        if '.git' in dirnames:
            dirnames.remove('.git')
        for name in filenames:
            p = Path(dirpath) / name
            if p == OUTPUT:
                continue
            if p.suffix.lower() in {'.html', '.htm'}:
                html_files.append(p)
    html_files.sort()
    return html_files


MEDIA_REF_RE = re.compile(r'[^\s"\'<>]+\.(?:jpe?g|png|gif|webp|svg|bmp|tiff?|ico|avif|mp4|mov|m4v|webm|avi|mkv|wmv|flv|mpe?g|mp3|wav|m4a|ogg|oga|flac|aac|opus|pdf)(?:\?[^\s"\'<>]*)?(?:#[^\s"\'<>]*)?', re.IGNORECASE)


def normalize_media_ref(ref: str) -> str | None:
    s = unquote(ref.strip())
    if not s:
        return None

    parts = urlsplit(s)
    if parts.scheme and parts.scheme not in {'http', 'https'}:
        return None

    path = parts.path
    if not path:
        return None
    if parts.netloc:
        path = path.lstrip('/')
    path = path.lstrip('./')
    if not path:
        return None
    return path


def index_media_occurrences(html_files: list[Path]) -> dict[str, list[str]]:
    occurrences: dict[str, set[str]] = defaultdict(set)

    for html in html_files:
        rel_html = html.as_posix().lstrip('./')
        try:
            txt = html.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        for m in MEDIA_REF_RE.finditer(txt):
            normalized = normalize_media_ref(m.group(0))
            if normalized:
                occurrences[normalized].add(rel_html)

    return {k: sorted(v) for k, v in occurrences.items()}


def is_likely_design_asset(path: Path) -> bool:
    p = '/' + path.as_posix().lower().lstrip('./')
    name = path.name.lower()

    if any(part in p for part in LOW_RISK_PATH_PARTS):
        return True
    if any(pattern in name for pattern in LOW_RISK_FILENAME_PATTERNS):
        return True
    if path.suffix.lower() == '.svg':
        return True
    return False


def variant_key(entry: dict[str, Any]) -> str:
    if not str(entry.get('mime_type', '')).startswith('image/'):
        return entry['path']

    p = Path(entry['path'])
    stem = p.stem
    m = SIZE_SUFFIX_RE.match(stem)
    base = m.group('base') if m else stem
    return str((p.parent / f'{base}{p.suffix.lower()}').as_posix())


def image_sort_score(entry: dict[str, Any]) -> tuple[int, int]:
    w = entry.get('image_width')
    h = entry.get('image_height')
    if isinstance(w, int) and isinstance(h, int):
        return (w * h, entry.get('size_bytes', 0))
    return (0, entry.get('size_bytes', 0))


def aggregate_entries(entries: list[dict[str, Any]], occurrence_index: dict[str, list[str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        grouped.setdefault(variant_key(e), []).append(e)

    aggregated: list[dict[str, Any]] = []

    for key, group in grouped.items():
        group_sorted = sorted(group, key=lambda e: image_sort_score(e), reverse=True)
        representative = group_sorted[0]

        variants = []
        for g in sorted(group, key=lambda e: (e['path'])):
            variants.append({
                'path': g['path'],
                'filename': g['filename'],
                'image_width': g.get('image_width'),
                'image_height': g.get('image_height'),
                'size_bytes': g['size_bytes'],
                'size_kb': g['size_kb'],
            })

        agg = dict(representative)
        agg['variant_group_key'] = key
        agg['variant_count'] = len(group)
        agg['variant_files'] = variants
        agg['all_paths_search'] = ' '.join(v['path'] for v in variants)

        occurrence_pages: set[str] = set()
        for v in variants:
            occurrence_pages.update(occurrence_index.get(v['path'], []))
        agg['occurrence_pages'] = sorted(occurrence_pages)
        agg['occurrence_count'] = len(occurrence_pages)
        agg['all_occurrence_pages_search'] = ' '.join(agg['occurrence_pages'])
        aggregated.append(agg)

    aggregated.sort(key=lambda e: e['path'])
    return aggregated


def build_html(entries: list[dict[str, Any]], generated_at: str, raw_file_count: int) -> str:
    entries_json = json.dumps(entries, ensure_ascii=False)
    template = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Media Audit Index</title>
  <style>
    body {{ font-family: Inter, Segoe UI, Arial, sans-serif; margin: 0; padding: 1rem; background: #f7f7f8; color: #111; }}
    h1 {{ margin: 0 0 .25rem; }}
    .meta {{ color: #444; margin-bottom: 1rem; }}
    .toolbar {{ display: flex; gap: .75rem; flex-wrap: wrap; margin-bottom: .75rem; }}
    input, select {{ padding: .45rem .55rem; border: 1px solid #bbb; border-radius: .35rem; min-width: 13rem; }}
    label {{ display: inline-flex; align-items: center; gap: .35rem; background: #fff; border: 1px solid #bbb; padding: .4rem .55rem; border-radius: .35rem; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d7d7d7; }}
    th, td {{ border-bottom: 1px solid #ececec; padding: .45rem .5rem; text-align: left; vertical-align: top; font-size: 12px; }}
    th {{ background: #f0f3f8; position: sticky; top: 0; z-index: 3; }}
    tr:hover {{ background: #f9fbff; }}
    .small {{ color: #555; font-size: 11px; }}
    .path {{ max-width: 30rem; word-break: break-all; }}
    .variants {{ max-width: 28rem; word-break: break-all; }}
    .num {{ text-align: right; white-space: nowrap; }}
    a {{ color: #0b57d0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>Copyright-Risk Media Audit</h1>
  <div class=\"small\">Low-risk design assets (icons, gradients, theme/plugin UI media, SVG iconography) are excluded by default. Resized image variants (e.g. <code>-1536x1024</code>) are grouped so you can review once per image family.</div>
  <div class=\"meta\" id=\"summary\"></div>
  <div class=\"toolbar\">
    <input id=\"search\" placeholder=\"Search filename, path, SHA-256…\" />
    <select id=\"typeFilter\">
      <option value=\"\">All media types</option>
      <option value=\"image/\">Images</option>
      <option value=\"video/\">Videos</option>
      <option value=\"audio/\">Audio</option>
      <option value=\"application/pdf\">PDF</option>
    </select>
    <label><input type=\"checkbox\" id=\"dupesOnly\" /> Only show duplicate-content rows</label>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Preview (largest variant)</th>
        <th>Main file</th>
        <th>Variants</th>
        <th>Type</th>
        <th>HTML occurrences</th>
        <th>Size</th>
        <th>Metadata</th>
        <th>SHA-256</th>
      </tr>
    </thead>
    <tbody id=\"rows\"></tbody>
  </table>

<script>
const entries = {entries_json};
const generatedAt = {json.dumps(generated_at)};
const rawFileCount = {raw_file_count};

const hashCounts = new Map();
for (const e of entries) hashCounts.set(e.sha256, (hashCounts.get(e.sha256) || 0) + 1);

function previewHtml(e) {{
  if (e.mime_type.startsWith('image/')) return `<img src="/${{e.path}}" alt="" style="max-width:110px;max-height:70px;object-fit:contain" loading="lazy">`;
  if (e.mime_type.startsWith('video/')) return `<video src="/${{e.path}}" style="max-width:110px;max-height:70px" preload="metadata" controls></video>`;
  if (e.mime_type.startsWith('audio/')) return `<audio src="/${{e.path}}" controls preload="metadata"></audio>`;
  if (e.mime_type === 'application/pdf') return `<a href="/${{e.path}}" target="_blank">Open PDF</a>`;
  return '';
}}

function metadataHtml(e) {{
  const parts = [];
  const maybe = (k, label) => (e[k] !== undefined && e[k] !== null && e[k] !== '') ? parts.push(`<div><strong>${{label}}:</strong> ${{e[k]}}</div>`) : null;
  maybe('image_width', 'Width');
  maybe('image_height', 'Height');
  maybe('svg_viewbox', 'viewBox');
  maybe('duration_seconds', 'Duration (s)');
  maybe('video_codec', 'Video codec');
  maybe('audio_codec', 'Audio codec');
  maybe('video_width', 'Video width');
  maybe('video_height', 'Video height');
  maybe('audio_channels', 'Audio channels');
  maybe('audio_sample_rate', 'Audio sample rate');
  maybe('bit_rate', 'Bit rate');
  maybe('modified_utc', 'Modified UTC');
  return parts.join('') || '<span class="small">No extra metadata available</span>';
}}

function variantsHtml(e) {{
  if (!e.variant_files || e.variant_files.length <= 1) return '<span class="small">—</span>';
  return e.variant_files.map(v => {{
    const dims = (v.image_width && v.image_height) ? ` (${{v.image_width}}×${{v.image_height}})` : '';
    return `<div><a href="/${{v.path}}" target="_blank">${{v.filename}}</a>${{dims}} <span class="small">· ${{v.size_kb}} KB</span></div>`;
  }}).join('');
}}

function occurrencesHtml(e) {{
  if (!e.occurrence_pages || e.occurrence_pages.length === 0) return '<span class="small">None found</span>';
  return e.occurrence_pages.map(p => `<div><a href="/${{p}}" target="_blank">${{p}}</a></div>`).join('') +
    `<div class="small">Total pages: ${{e.occurrence_count}}</div>`;
}}

function render() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const tf = document.getElementById('typeFilter').value;
  const dupesOnly = document.getElementById('dupesOnly').checked;

  const filtered = entries.filter(e => {{
    if (tf && !e.mime_type.startsWith(tf) && e.mime_type !== tf) return false;
    if (dupesOnly && (hashCounts.get(e.sha256) || 0) < 2) return false;
    if (!q) return true;
    return [e.path, e.filename, e.sha256, e.mime_type, e.extension, e.all_paths_search || '', e.all_occurrence_pages_search || ''].join(' ').toLowerCase().includes(q);
  }});

  const rows = filtered.map((e, i) => {{
    const dupes = hashCounts.get(e.sha256) || 0;
    return `<tr>
      <td class="num">${{i+1}}</td>
      <td>${{previewHtml(e)}}</td>
      <td class="path"><a href="/${{e.path}}" target="_blank">${{e.path}}</a><div class="small">Filename: ${{e.filename}}</div></td>
      <td class="variants">${{variantsHtml(e)}}<div class="small">Total variants: ${{e.variant_count || 1}}</div></td>
      <td><div>${{e.mime_type}}</div><div class="small">${{e.extension}}</div>${{dupes > 1 ? `<div class="small"><strong>Duplicates:</strong> ${{dupes}}</div>` : ''}}</td>
      <td class="path">${{occurrencesHtml(e)}}</td>
      <td class="num">${{e.size_bytes.toLocaleString()}} B<div class="small">${{e.size_kb}} KB</div></td>
      <td>${{metadataHtml(e)}}</td>
      <td class="path"><code>${{e.sha256}}</code></td>
    </tr>`;
  }}).join('');

  document.getElementById('rows').innerHTML = rows;

  const uniqueHashes = new Set(entries.map(e => e.sha256)).size;
  const dupRows = entries.filter(e => (hashCounts.get(e.sha256)||0) > 1).length;
  document.getElementById('summary').innerHTML =
    `Generated: <strong>${{generatedAt}}</strong> · Source files scanned after risk filter: <strong>${{rawFileCount}}</strong> · Review rows after variant grouping: <strong>${{entries.length}}</strong> · Unique content hashes: <strong>${{uniqueHashes}}</strong> · Duplicate-content rows: <strong>${{dupRows}}</strong> · Showing: <strong>${{filtered.length}}</strong>`;
}}

for (const id of ['search','typeFilter','dupesOnly']) document.getElementById(id).addEventListener('input', render);
render();
</script>
</body>
</html>
"""
    return template


def main() -> None:
    files = gather_files()
    html_files = gather_html_files()
    occurrence_index = index_media_occurrences(html_files)
    filtered_files = [p for p in files if not is_likely_design_asset(p)]
    raw_entries = [file_metadata(p) for p in filtered_files]
    aggregated_entries = aggregate_entries(raw_entries, occurrence_index)
    generated_at = datetime.now(timezone.utc).isoformat()
    OUTPUT.write_text(build_html(aggregated_entries, generated_at, len(filtered_files)), encoding='utf-8')
    print(
        f'Wrote {OUTPUT} with {len(aggregated_entries)} review rows '
        f'from {len(filtered_files)} files (excluded {len(files) - len(filtered_files)} likely design assets)'
    )


if __name__ == '__main__':
    main()
