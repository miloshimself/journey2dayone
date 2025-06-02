import os
import json
import uuid
import shutil
import hashlib
from datetime import datetime, timezone
from PIL import Image
from mutagen._file import File as MutagenFile

JOURNEY_INPUT_DIR = "journey_exports"
DAYONE_OUTPUT_DIR = "dayone_export"
PHOTOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "photos")
AUDIOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "audios")
DAYONE_JSON_PATH = os.path.join(DAYONE_OUTPUT_DIR, "Journey.json")


def ensure_dirs():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    os.makedirs(AUDIOS_DIR, exist_ok=True)


def convert_timestamp(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def convert_text(j):
    return j.get("text", "")


def convert_rich_text(j):
    text = j.get("text", "")
    return {
        "contents": [{"text": text}],
        "meta": {
            "created": {"platform": "com.bloombuilt.dayone-mac", "version": 1667},
            "small-lines-removed": True,
            "version": 1
        }
    }


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
        duration = audio.info.length if audio and audio.info else 0
        sample_rate = f"{round(audio.info.sample_rate / 1000, 1)} kHz" if audio and audio.info else "Unknown"
        return duration, sample_rate
    except Exception:
        return 0, "Unknown"


def convert_media_enhanced_with_audio(j, media_dir, creation_date_iso, location):
    media_list = j.get("photos", [])
    photo_entries = []
    audio_entries = []

    for idx, item in enumerate(media_list):
        fname = os.path.basename(item) if isinstance(item, str) else None
        if not fname:
            continue

        ext = os.path.splitext(fname)[1].lower().strip(".")
        src = os.path.join(media_dir, fname)

        if not os.path.exists(src):
            continue

        identifier = os.path.splitext(fname)[0]
        file_size = os.path.getsize(src)
        md5_hash = get_md5(src)

        if ext in ["jpg", "jpeg", "png"]:
            try:
                with Image.open(src) as img:
                    width, height = img.size
            except Exception:
                width, height = 0, 0

            dst = os.path.join(PHOTOS_DIR, fname)
            shutil.copy2(src, dst)

            photo_entry = {
                "fileSize": file_size,
                "orderInEntry": idx + 1,
                "creationDevice": "Miloš’s MacBook Pro",
                "duration": 0,
                "favorite": False,
                "type": ext,
                "identifier": identifier,
                "date": creation_date_iso,
                "exposureBiasValue": 0,
                "height": height,
                "width": width,
                "md5": md5_hash,
                "isSketch": False
            }
            photo_entries.append(photo_entry)

        elif ext in ["m4a", "aac", "mp3"]:
            duration, sample_rate = get_audio_metadata(src)

            dst = os.path.join(AUDIOS_DIR, fname)
            shutil.copy2(src, dst)

            audio_entry = {
                "fileSize": file_size,
                "orderInEntry": idx,
                "recordingDevice": "iPhone Microphone",
                "creationDevice": "Miloš’s iPhone",
                "audioChannels": "Mono",
                "duration": duration,
                "favorite": False,
                "identifier": identifier,
                "format": ext,
                "date": creation_date_iso,
                "height": 0,
                "width": 0,
                "md5": md5_hash,
                "sampleRate": sample_rate,
                "timeZoneName": "Europe/Belgrade"
            }

            if location:
                audio_entry["location"] = location

            audio_entries.append(audio_entry)

    return photo_entries, audio_entries


def journey_to_dayone_entry(j, media_dir):
    uuid_str = str(uuid.uuid4()).replace("-", "").upper()
    created, modified = convert_dates(j)
    location = convert_location(j)
    weather = convert_weather(j)
    text = convert_text(j)
    rich_text = convert_rich_text(j)

    entry = {
        "uuid": uuid_str,
        "creationDate": created,
        "modifiedDate": modified,
        "text": text,
        "richText": rich_text,
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