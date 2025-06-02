
# Journey ➜ Day One Converter

A command‑line utility that losslessly migrates your **[Journey](https://journey.cloud)** diary export (_JSON + media_) into a ready‑to‑import **[Day One](https://dayoneapp.com)** archive.

* Photos are copied bit‑for‑bit and renamed to their MD5 hash  
* MP3 voice notes are transcoded to **AAC (.m4a)** using `libfdk_aac` at 320 kb/s CBR  
* Existing `.m4a / .aac / .wav` recordings are preserved as‑is  
* Rich‑text (headers, bulleted / numbered lists, bold, inline code) is rebuilt as native Day One `richText`  
* Location, weather and tags are transferred when present  

---

## 1. Prerequisites

| Requirement | Version / Notes |
|-------------|-----------------|
| Python      | 3.9 + (tested 3.11) |
| FFmpeg      | Built **with `libfdk_aac`** support – not enabled in Homebrew’s default bottle |

### Why a custom FFmpeg build?

`libfdk_aac` is **GPL/Non‑Free** and therefore excluded from the stock Homebrew build.  
The converter uses it to transcode Journey’s MP3 voice notes to high‑quality AAC so that Day One can play them inline.

Follow the build script below to compile FFmpeg with all needed codecs.

---

## 2. FFmpeg build for Apple Silicon

Save as `build-ffmpeg.sh`, `chmod +x`, then `./build-ffmpeg.sh`.

```bash
#!/bin/bash
set -e

# ---------- dependencies -------------------------------------------------
brew install automake autoconf libtool pkg-config texi2html wget              fdk-aac lame x264 x265 libvpx opus xvid nasm

# ---------- FFmpeg source ------------------------------------------------
mkdir -p ~/ffmpeg-build && cd ~/ffmpeg-build
git clone https://github.com/ffmpeg/ffmpeg.git || true
cd ffmpeg && git pull

export PKG_CONFIG_PATH="/opt/homebrew/opt/fdk-aac/lib/pkgconfig:/opt/homebrew/opt/lame/lib/pkgconfig:/opt/homebrew/opt/opus/lib/pkgconfig:/opt/homebrew/opt/libvpx/lib/pkgconfig:/opt/homebrew/opt/xvid/lib/pkgconfig"

export LDFLAGS="-L/opt/homebrew/opt/fdk-aac/lib -L/opt/homebrew/opt/lame/lib -L/opt/homebrew/opt/opus/lib -L/opt/homebrew/opt/libvpx/lib -L/opt/homebrew/opt/xvid/lib"

export CPPFLAGS="-I/opt/homebrew/opt/fdk-aac/include -I/opt/homebrew/opt/lame/include -I/opt/homebrew/opt/opus/include -I/opt/homebrew/opt/libvpx/include -I/opt/homebrew/opt/xvid/include"

./configure --prefix=/usr/local --enable-gpl --enable-nonfree             --enable-libfdk_aac --enable-libmp3lame --enable-libopus             --enable-libvpx --enable-libx264 --enable-libx265 --enable-libxvid

make -j$(sysctl -n hw.ncpu)
sudo make install
ffmpeg -version
```

> **Note**  
> Paths use `/opt/homebrew` (Apple Silicon).  
> Replace with `/usr/local` on Intel Macs or adapt for Linux.

---

## 3. Installation

```bash
git clone https://github.com/miloshimself/journey2dayone.git
cd journey2dayone
python3 -m venv .venv && source .venv/bin/activate
pip3 install -r requirements.txt
```

---

## 4. Usage

1. **Export from Journey**  
   `Journey ➜ Settings ➜ Preferences ➜ Account, Data & Cloud Services ➜ <Your Account> ➜ Export/Backup`
   Select the date range, and enable "Download High Quality Photos".  
   Place all exported files (.json, photo and audio) in `journey_exports/`.

2. **Run the converter**

   ```bash
   python3 journey2dayone.py
   ```

   * A Day One–ready folder `dayone_export/` is created.  
   * It is automatically zipped as `Journey.dayone.zip`.

3. **Import into Day One**  
   *macOS / iOS* → File ➜ Import ➜ JSON ZIP File → select the generated archive.

---

## 5. Field mapping

| Journey field | Day One field |
|---------------|--------------|
| `text` (HTML) | `text` + `richText` (Markdown & native JSON) |
| `photos[]`    | `photos[]` (metadata + MD5 filenames) |
| `audios[]`    | `audios[]` (AAC) |
| `lat` / `lon` | `location` |
| `weather.*`   | `weather` |
| `tags[]`      | `tags[]` |

---

## 6. Limitations

* Only `.jpg / .jpeg / .png` images and `.mp3 / .m4a / .aac / .wav` audio are processed, though easily extended.
* Journey entries without `lat`/`lon` are imported without location  
* Time‑zone‑to‑country resolution relies on the included IANA ↔ ISO 3166 map

---

## 7. License

MIT.  Use at your own risk.  No affiliation with Journey Cloud or Day One.