import os
import json
import uuid
import shutil
import hashlib
from datetime import datetime, timezone
from PIL import Image
from mutagen._file import File as MutagenFile
import html
import re

JOURNEY_INPUT_DIR = "journey_exports"
DAYONE_OUTPUT_DIR = "dayone_export"
PHOTOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "photos")
AUDIOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "audios")
DAYONE_JSON_PATH = os.path.join(DAYONE_OUTPUT_DIR, "Journey.json")
TAG_RE = re.compile(r"<[^>]+>")

def strip_html(src: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    out = TAG_RE.sub("", src)
    # Day One likes normalized line-breaks
    out = re.sub(r"\r\n|\r", "\n", out)
    return out.strip()

def build_rich_text_and_text(original_text, photos, audios):
    original_text = strip_html(original_text or "")
    contents   = []
    plain_lines = []

    if original_text:
        contents.append({"text": original_text})
        plain_lines.append(original_text)

    for p in photos:
        contents.append({"embeddedObjects":[{"identifier": p["identifier"], "type":"photo"}]})
        plain_lines.append(f"![](dayone-moment://{p['identifier']})")

    for a in audios:
        contents.append({"embeddedObjects":[{"identifier": a["identifier"], "type":"audio"}]})
        plain_lines.append(f"![](dayone-moment:/audio/{a['identifier']})")

    rich_dict = {
        "contents": contents,
        "meta": {
            "created": {"platform":"com.bloombuilt.dayone-mac","version":1667},
            "small-lines-removed": True,
            "version": 1
        }
    }
    return json.dumps(rich_dict, ensure_ascii=False), "\n\n".join(plain_lines)

def ensure_dirs():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    os.makedirs(AUDIOS_DIR, exist_ok=True)


def convert_timestamp(ms: int) -> str:
    """ms since epoch → RFC3339 with trailing Z (UTC)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) \
                   .replace(tzinfo=None) \
                   .isoformat(timespec="seconds") + "Z"


def convert_text(j):
    raw = html.unescape(j.get("text", ""))
    return strip_html(raw)


def convert_rich_text(j):
    text = html.unescape(j.get("text", ""))
    rich_text_data = {
        "contents": [{"text": text}],
        "meta": {
            "created": {"platform": "com.bloombuilt.dayone-mac", "version": 1667},
            "small-lines-removed": True,
            "version": 1
        }
    }
    return json.dumps(rich_text_data, ensure_ascii=False)


def convert_dates(j):
    created = convert_timestamp(j["date_journal"])
    modified = convert_timestamp(j.get("date_modified", j["date_journal"]))
    return created, modified


def convert_location(j):
    lat = j.get("lat")
    lon = j.get("lon")
    address = j.get("address", "")
    place = j.get("weather", {}).get("place", "")

    if lat is None or lon is None or lat > 1e6:
        return None

    return {
        "region": {
            "center": {
                "latitude": lat,
                "longitude": lon
            },
            "radius": 75
        },
        "latitude": lat,
        "longitude": lon,
        "placeName": address,
        "localityName": place,
        "administrativeArea": "Central Serbia",
        "country": "Serbia",
        "timeZoneName": "Europe/Belgrade"
    }


def convert_weather(j):
    w = j.get("weather", {})
    if not w or w.get("degree_c", 1e6) > 1e5:
        return None
    return {
        "conditionsDescription": w.get("description", ""),
        "temperatureCelsius": w.get("degree_c"),
        "weatherCode": "clear",
        "weatherServiceName": "JourneyImport"
    }


def convert_tags(j):
    return j.get("tags", [])


def get_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_audio_metadata(file_path):
    try:
        audio = MutagenFile(file_path)
        if audio and audio.info:
            duration = round(audio.info.length, 3)
            sample_rate = f"{round(audio.info.sample_rate/1000,1)} kHz"
            return duration, sample_rate
    except Exception:
        pass
    # fallback
    return None, None


def convert_media_enhanced_with_audio(j, media_dir, creation_iso, location):
    photo_entries, audio_entries = [], []

    for idx,item in enumerate(j.get("photos", [])):
        fname = os.path.basename(item) if isinstance(item,str) else None
        if not fname: continue
        src = os.path.join(media_dir, fname)
        if not os.path.exists(src): continue

        ext = os.path.splitext(fname)[1].lower().lstrip(".")
        identifier = uuid.uuid4().hex.upper()   # NEW unique ID
        new_name   = f"{identifier}.{ext}"
        dst_dir    = PHOTOS_DIR if ext in ["jpg","jpeg","png"] else AUDIOS_DIR
        dst        = os.path.join(dst_dir, new_name)
        shutil.copy2(src, dst)                  # copy under the new name
        md5_hash   = get_md5(dst)
        size       = os.path.getsize(dst)

        if ext in ["jpg","jpeg","png"]:           # photo entry
            try: w,h = Image.open(dst).size
            except: w,h = 0,0
            photo_entries.append({
                "fileSize": size, "orderInEntry": idx+1,
                "creationDevice": "Miloš’s MacBook Pro","duration":0,
                "favorite": False,"type":ext,"identifier":identifier,
                "date": creation_iso,"exposureBiasValue":0,
                "height": h,"width": w,"md5": md5_hash,"isSketch": False
            })
        else:                                     # audio entry
            duration,sample_rate = get_audio_metadata(dst)
            audio_entry = {
                "fileSize": size,"orderInEntry": idx,
                "recordingDevice":"MacBook Microphone","creationDevice":"Miloš’s MacBook Pro",
                "audioChannels":"Mono","duration":duration,"favorite":False,
                "identifier":identifier,"format":ext,"date":creation_iso,
                "height":0,"width":0,"md5":md5_hash,"sampleRate":sample_rate,
                "timeZoneName":"Europe/Belgrade"
            }
            if location: audio_entry["location"]=location
            if duration: audio_entry["duration"]=duration
            if sample_rate: audio_entry["sampleRate"]=sample_rate
            audio_entries.append(audio_entry)

    return photo_entries, audio_entries


def journey_to_dayone_entry(j, media_dir):
    uuid_str = str(uuid.uuid4()).replace("-", "").upper()
    created, modified = convert_dates(j)
    location = convert_location(j)
    weather = convert_weather(j)
    text = convert_text(j)

    entry = {
        "uuid": uuid_str,
        "creationDate": created,
        "modifiedDate": modified,
        "text": text,
        "richText": "",
        "starred": j.get("favourite", False),
        "creationDevice": "Miloš’s MacBook Pro",
        "creationDeviceType": "MacBook Pro",
        "creationOSVersion": "15.5",
        "creationDeviceModel": "Mac16,7",
        "creationOSName": "macOS",
        "timeZone": "Europe/Belgrade",
        "isPinned": False,
        "isAllDay": False,
        "duration": 0,
        "tags": convert_tags(j)
    }

    if location:
        entry["location"] = location
    if weather:
        entry["weather"] = weather

    photo_entries, audio_entries = convert_media_enhanced_with_audio(j, media_dir, created, location)
    if photo_entries:
        entry["photos"] = photo_entries
    if audio_entries:
        entry["audios"] = audio_entries

    rich_str, full_text = build_rich_text_and_text(text, photo_entries, audio_entries)
    entry["richText"] = rich_str
    entry["text"]     = full_text

    return entry


def main():
    ensure_dirs()
    entries = []
    for fname in os.listdir(JOURNEY_INPUT_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(JOURNEY_INPUT_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                j = json.load(f)
                entry = journey_to_dayone_entry(j, JOURNEY_INPUT_DIR)
                entries.append(entry)
            except Exception as e:
                print(f"Error processing {fname}: {e}")

    dayone_export = {
        "metadata": {"version": "1.0"},
        "entries": entries
    }

    with open(DAYONE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(dayone_export, f, ensure_ascii=False, indent=2)

    print(f"✅ Exported {len(entries)} entries to {DAYONE_JSON_PATH}")


if __name__ == "__main__":
    main()