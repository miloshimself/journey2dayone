import os
import json
import uuid
import shutil
from datetime import datetime, timezone

JOURNEY_INPUT_DIR = "journey_exports"
DAYONE_OUTPUT_DIR = "dayone_export"
PHOTOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "photos")
AUDIOS_DIR = os.path.join(DAYONE_OUTPUT_DIR, "audios")
DAYONE_JSON_PATH = os.path.join(DAYONE_OUTPUT_DIR, "Personal.json")


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


def deduce_country_from_timezone(tz):
    mapping = {
        "Europe/Belgrade": "Serbia",
        "America/New_York": "United States",
        "America/Los_Angeles": "United States",
        "Europe/London": "United Kingdom",
        "Europe/Paris": "France",
        "Europe/Berlin": "Germany",
        "Asia/Tokyo": "Japan",
        "Asia/Shanghai": "China",
        "Asia/Kolkata": "India",
        "Australia/Sydney": "Australia",
        "Africa/Johannesburg": "South Africa",
        "America/Sao_Paulo": "Brazil",
        "UTC": ""
    }
    return mapping.get(tz, "")


def convert_location(j):
    lat = j.get("lat")
    lon = j.get("lon")
    address = j.get("address", "")
    timezone_name = j.get("timezone", "")
    place = j.get("weather", {}).get("place", "")
    country = deduce_country_from_timezone(timezone_name)

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
        "administrativeArea": "",
        "country": country,
        "timeZoneName": timezone_name
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


def convert_media(j, media_dir):
    media_list = j.get("photos", [])
    photo_entries = []
    audio_entries = []

    for item in media_list:
        fname = os.path.basename(item) if isinstance(item, str) else None
        if not fname:
            continue

        ext = os.path.splitext(fname)[1].lower()
        src = os.path.join(media_dir, fname)

        if not os.path.exists(src):
            continue

        identifier = os.path.splitext(fname)[0]

        if ext in [".jpg", ".jpeg", ".png"]:
            dst = os.path.join(PHOTOS_DIR, fname)
            shutil.copy2(src, dst)
            photo_entries.append({"identifier": identifier, "type": "photo"})

        elif ext in [".m4a", ".aac", ".mp3"]:
            dst = os.path.join(AUDIOS_DIR, fname)
            shutil.copy2(src, dst)
            audio_entries.append({"identifier": identifier, "type": "audio"})

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
        "richText": json.dumps(rich_text),
        "starred": j.get("favourite", False),
        "creationDevice": "Imported from Journey",
        "creationDeviceType": "Other",
        "timeZone": j.get("timezone", "UTC"),
        "isPinned": False,
        "isAllDay": False,
        "duration": 0,
        "tags": convert_tags(j)
    }

    if location:
        entry["location"] = location
    if weather:
        entry["weather"] = weather

    # Media (from 'photos' list in Journey)
    photo_entries, audio_entries = convert_media(j, media_dir)
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