"""
Journey-to-Day One converter
────────────────────────────
 • Photos copied losslessly, named <md5>.ext
 • MP3 → AAC/M4A re-encode (libfdk_aac 320 kbps CBR)
 • Existing M4A / AAC / WAV are *not* touched – just copied.
 • MD5 hash stored in entry JSON so Day One finds the asset.
"""

import os, json, uuid, shutil, hashlib, re, html, zipfile, subprocess, tempfile, re, pytz
from datetime import datetime, timezone
from html.parser import HTMLParser
from html_to_markdown import convert_to_markdown
from pytz import country_timezones, country_names
from PIL import Image
from mutagen._file import File as MutagenFile

# ─── user paths ──────────────────────────────────────────────────────────────
JOURNEY_INPUT_DIR = "journey_exports"
DAYONE_OUTPUT_DIR = "dayone_export"
PHOTOS_DIR        = os.path.join(DAYONE_OUTPUT_DIR, "photos")
AUDIOS_DIR        = os.path.join(DAYONE_OUTPUT_DIR, "audios")
DAYONE_JSON_PATH  = os.path.join(DAYONE_OUTPUT_DIR, "Journey.json")


# --- build a global “timezone → country” dict once --------------------------
_TZ2COUNTRY: dict[str, str] = {}
for cc, tz_list in country_timezones.items():
    cname = country_names.get(cc, cc)          # e.g.  "RS" → "Serbia"
    for tz in tz_list:
        _TZ2COUNTRY[tz] = cname


def tz_to_country(tz: str | None) -> str | None:
    """'Europe/Belgrade' → 'Serbia'  |  None when unknown."""
    if not tz:
        return None
    return _TZ2COUNTRY.get(tz)

# ─── markdown from Journey HTML ──────────────────────────────────────────────
def strip_html(src: str) -> str:
    """Journey’s HTML → Markdown with tidy spacing & ‘-’ bullets."""
    raw = html.unescape(src or "")
    if not raw.strip():
        return ""
    md = convert_to_markdown(raw).strip()

    # --- tidy escape sequences ------------------------------------------
    md = re.sub(r"\n{2,3}", "\n", md)                    # collapse blank lines
    md = re.sub(r"^\* ",  "- ", md, flags=re.MULTILINE) # use "-" bullets

    # 1. un-escape bullets / headers only at BOL
    md = re.sub(r"(?m)^\\([#*\-+>`])", r"\1", md)

    # 2. un-escape ordinary inline punctuation
    md = re.sub(r"\\([.\-+!*_])", r"\1", md)            # now includes “+” and “!”

    # 3. re-fix bold that the previous step broke:  *\*text\*  ->  **text**
    md = re.sub(r"\*\\\*(.*?)\\\*\*", r"**\1**", md)
    
    return md


# ─── rich-text + plain builder ───────────────────────────────────────────────
_hdr_re = re.compile(r'^(#{1,6})\s*(.*)$')          # 1–6 leading # → header 1-6

def _markdown_to_dayone_contents(markdown: str) -> list[dict]:
    """
    Turn the Markdown we already produced from Journey’s HTML into Day One
    `richText.contents` — with **native** bullets and numbered lists.

    Rules
    -----
    •  “# …” → header (level = #-count)
    •  “- …”, “* …”, “+ …”  → bulleted list
    •  “1. …”, “1) …” etc   → numbered list (listIndex is the literal number)
    •   Leading spaces define nesting depth (2 spaces = one indentLevel)
    """
    contents: list[dict] = []

    for raw in markdown.splitlines(keepends=True):

        # ---------- headers -------------------------------------------------
        m = _hdr_re.match(raw)
        if m:
            level = len(m.group(1))
            text  = m.group(2) + ("\n" if raw.endswith("\n") else "")
            contents.append({
                "attributes": {
                    "line": {
                        "header": level,
                        "identifier": uuid.uuid4().hex.upper()
                    }
                },
                "text": text,
            })
            continue

        # ---------- unordered bullets ---------------------------------------
        m = re.match(r'^(\s*)[*\-+]\s+(.*)', raw)
        if m:
            indent_spaces = len(m.group(1))
            indent_level  = indent_spaces // 2 + 1        # every 2 spaces = +1
            contents.append({
                "attributes": {
                    "line": {
                        "listStyle": "bulleted",
                        "indentLevel": indent_level,
                        "identifier": uuid.uuid4().hex.upper()
                    }
                },
                "text": m.group(2) + ("\n" if raw.endswith("\n") else ""),
            })
            continue

        # ---------- numbered bullets ----------------------------------------
        m = re.match(r'^(\s*)(\d+)[\.\)]\s+(.*)', raw)
        if m:
            indent_spaces = len(m.group(1))
            indent_level  = indent_spaces // 2 + 1
            list_index    = int(m.group(2))
            contents.append({
                "attributes": {
                    "line": {
                        "listStyle": "numbered",
                        "indentLevel": indent_level,
                        "listIndex":   list_index,
                        "identifier":  uuid.uuid4().hex.upper()
                    }
                },
                "text": m.group(3) + ("\n" if raw.endswith("\n") else ""),
            })
            continue

        # ---------- plain line ----------------------------------------------
        contents.append({"text": raw})

    return contents


def build_rich_and_plain(markdown: str, photos, audios):
    # -------- richText -------------------------------------------------------
    contents = _markdown_to_dayone_contents(markdown)
    for p in photos:
        contents.append({"embeddedObjects": [{"identifier": p["identifier"], "type": "photo"}]})
    for a in audios:
        contents.append({"embeddedObjects": [{"identifier": a["identifier"], "type": "audio"}]})

    rich = json.dumps(
        {"contents": contents,
         "meta": {"created": {"platform": "com.bloombuilt.dayone-mac", "version": 1667},
                  "small-lines-removed": True, "version": 1}},
        ensure_ascii=False
    )

    # -------- plain Markdown -------------------------------------------------
    blocks = [markdown] if markdown else []
    blocks += [f"![](dayone-moment://{p['identifier']})" for p in photos]
    blocks += [f"![](dayone-moment:/audio/{a['identifier']})" for a in audios]

    return rich, "\n".join(blocks)        # ← single newline separator

def ensure_dirs() -> None:
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    os.makedirs(AUDIOS_DIR, exist_ok=True)


def rfc3339(ms: int) -> str:
    return (
        datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
        + "Z"
    )


def md5_for_path(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audio_meta(path: str):
    """duration (s, 3-dec)  |  sample-rate str  (or (0,None))"""
    try:
        m = MutagenFile(path)
        if m and m.info:
            dur = round(m.info.length, 3)
            sr  = f"{round(m.info.sample_rate/1000,1)} kHz"
            return dur, sr
    except Exception:
        pass
    return 0, None


# ─── audio transcoder ────────────────────────────────────────────────────────
def transcode_to_m4a(src: str) -> str:
    """
    MP3  →  losslessly-as-possible AAC/M4A (320 kbps CBR, libfdk_aac)
    returns path to the temporary m4a file
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".m4a")
    os.close(fd)                      # we just needed a filename
    cmd = [
        "ffmpeg",
        "-y",                         # overwrite
        "-i", src,
        "-vn",
        "-c:a", "libfdk_aac",
        "-b:a", "320k",               # maximum CBR
        tmp_path,
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode:
        raise RuntimeError("ffmpeg failed: " + res.stderr.decode(errors="ignore"))
    return tmp_path


# ─── media saver (copies or re-encodes, returns identifiers + md5) ───────────
def save_media(src: str, dest_dir: str, ext: str, is_mp3: bool):
    """
    Copy *src* (or its high-quality AAC conversion) into *dest_dir*
    under the file’s **MD5** name. Returns (identifier, md5_hex, dest_path, new_ext)
    """
    if is_mp3:
        src_for_hash = transcode_to_m4a(src)
        ext = "m4a"
    else:
        src_for_hash = src

    md5_hex = md5_for_path(src_for_hash)
    dst = os.path.join(dest_dir, f"{md5_hex}.{ext.lower()}")
    shutil.copy2(src_for_hash, dst)

    if is_mp3:
        os.remove(src_for_hash)  # temp file no longer needed

    return uuid.uuid4().hex.upper(), md5_hex, dst, ext


# ─── convert photos + audios ────────────────────────────────────────────────
def convert_media(j, media_dir, creation_iso, location):
    photo_entries, audio_entries = [], []

    for idx, item in enumerate(j.get("photos", [])):
        fname = os.path.basename(item) if isinstance(item, str) else ""
        if not fname:
            continue
        src = os.path.join(media_dir, fname)
        if not os.path.exists(src):
            continue

        ext = os.path.splitext(fname)[1].lower().lstrip(".")
        is_photo = ext in {"jpg", "jpeg", "png"}
        is_audio_ok = ext in {"m4a", "aac", "wav"}
        is_mp3 = ext == "mp3"

        if not is_photo and not (is_audio_ok or is_mp3):
            continue

        identifier, md5_hex, new_path, final_ext = save_media(
            src,
            PHOTOS_DIR if is_photo else AUDIOS_DIR,
            ext=ext,
            is_mp3=is_mp3,
        )
        size = os.path.getsize(new_path)

        if is_photo:
            try:
                width, height = Image.open(new_path).size
            except Exception:
                width = height = 0
            photo_entries.append(
                {
                    "identifier": identifier,
                    "fileSize": size,
                    "orderInEntry": idx,
                    "type": final_ext,
                    "date": creation_iso,
                    "width": width,
                    "height": height,
                    "md5": md5_hex,
                    "favorite": False,
                    "duration": 0,
                    "creationDevice": "Miloš’s MacBook Pro",
                    "exposureBiasValue": 0,
                    "isSketch": False,
                }
            )
        else:  # audio
            duration, sr = audio_meta(new_path)
            audio_entries.append(
                {
                    "identifier": identifier,
                    "fileSize": size,
                    "orderInEntry": idx,
                    "format": final_ext,
                    "audioChannels": "Mono",
                    "duration": duration,
                    "sampleRate": sr,
                    "date": creation_iso,
                    "md5": md5_hex,
                    "favorite": False,
                    "recordingDevice": "Microphone",
                    "creationDevice": "Miloš’s MacBook Pro",
                    "height": 0,
                    "width": 0,
                    "timeZoneName": "Europe/Belgrade",
                    **({"location": location} if location else {}),
                }
            )

    return photo_entries, audio_entries


# ─── entry builder ───────────────────────────────────────────────────────────
def journey_to_dayone_entry(j):
    created = rfc3339(j["date_journal"])
    modified = rfc3339(j.get("date_modified", j["date_journal"]))
    location = convert_location(j)
    weather = convert_weather(j)

    photos, audios = convert_media(j, JOURNEY_INPUT_DIR, created, location)

    plain_text = strip_html(html.unescape(j.get("text", "")))
    rich, full_text = build_rich_and_plain(plain_text, photos, audios)

    entry = {
        "uuid": uuid.uuid4().hex.upper(),
        "creationDate": created,
        "modifiedDate": modified,
        "text": full_text,
        "richText": rich,
        "starred": j.get("favourite", False),
        "creationDevice": "Miloš’s MacBook Pro",
        "creationDeviceType": "MacBook Pro",
        "creationOSVersion": "15.5",
        "creationDeviceModel": "Mac16,7",
        "creationOSName": "macOS",
        "isPinned": False,
        "isAllDay": False,
        "duration": 0,
        "tags": j.get("tags", []),
    }
    if location:
        entry["location"] = location
    if weather:
        entry["weather"] = weather
    if photos:
        entry["photos"] = photos
    if audios:
        entry["audios"] = audios
    return entry


def convert_location(j: dict) -> dict | None:
    """
    Build Day One-style location block.

    * latitude / longitude come from Journey
    * time-zone is preserved exactly
    * country is looked-up from the TZ database
    """
    lat, lon = j.get("lat"), j.get("lon")
    tz       = j.get("timezone") or j.get("timeZone") or "UTC"    # Journey uses both keys
    if lat is None or lon is None or lat > 1e6:
        return None

    return {
        "region": {
            "center": {"latitude": lat, "longitude": lon},
            "radius": 75
        },
        "latitude":       lat,
        "longitude":      lon,
        "timeZoneName":   tz,
        "timeZone":       tz,
        "country":        tz_to_country(tz) or "Unknown",
        "placeName":      j.get("address", ""),
        "localityName":   j.get("weather", {}).get("place", ""),
        "administrativeArea": j.get("address", "").split(",")[-1].strip() if j.get("address") else "",
    }


def convert_weather(j):
    w = j.get("weather", {})
    if not w or w.get("degree_c", 1e9) > 1e5:
        return None
    return {
        "conditionsDescription": w.get("description", ""),
        "temperatureCelsius": w.get("degree_c"),
        "weatherCode": "clear",
        "weatherServiceName": "JourneyImport",
    }


# ─── ZIP helper ──────────────────────────────────────────────────────────────
def build_import_zip(source: str, dest_zip: str):
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_STORED) as z:
        for folder, _dirs, files in os.walk(source):
            for f in files:
                abs_path = os.path.join(folder, f)
                rel_path = os.path.relpath(abs_path, source)
                z.write(abs_path, rel_path)


# ─── main ────────────────────────────────────────────────────────────────────
def main():
    ensure_dirs()
    entries = []
    for fn in os.listdir(JOURNEY_INPUT_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(JOURNEY_INPUT_DIR, fn), encoding="utf-8") as fh:
            try:
                journey = json.load(fh)
                entries.append(journey_to_dayone_entry(journey))
            except Exception as e:
                print(f"{fn}: {e}")

    with open(DAYONE_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump({"metadata": {"version": "1.0"}, "entries": entries}, fh, ensure_ascii=False, indent=2)

    print(f"Exported {len(entries)} entries → {DAYONE_JSON_PATH}")

    zip_target = os.path.join(os.path.dirname(DAYONE_OUTPUT_DIR), "Journey.dayone.zip")
    build_import_zip(DAYONE_OUTPUT_DIR, zip_target)
    print(f"Packed Day One import → {zip_target}")


if __name__ == "__main__":
    main()