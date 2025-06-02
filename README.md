# Journey → Day One Converter

This repository contains a single‑purpose Python script that converts an **export
from the Journey journaling application** into a Day One import archive
(`Journey.dayone.zip`).

It preserves every major feature that is available in Journey exports:

| Feature                       | Supported | Notes |
| ----------------------------- | :-------: | ----- |
| Text (rich & plain)           | ✅        | Journey’s HTML is converted to Markdown and Day One *richText*. |
| Photos                        | ✅        | Copied losslessly, renamed to their MD5 sum so Day One can locate them. |
| Audio recordings              | ✅        | MP3 files are trans‑encoded to high‑quality AAC / M4A; existing AAC / WAV are copied. |
| Weather, location, tags       | ✅        | Directly mapped. |
| Nested and numbered lists     | ✅        | Re‑encoded using Day One’s native list attributes. |

---

## 1.  Requirements

| Component | Purpose | Minimum Version |
| --------- | ------- | --------------- |
| **Python** | Running the converter | 3.10 |
| **pip** | Installing Python deps | latest |
| **ffmpeg** | Audio transcoding (MP3 → AAC) | 5.0 |

### libfdk\_aac encoder

Day One stores audio in **AAC / M4A**.  
To avoid a second generation of loss when Journey recordings are already lossy
MP3, the script re‑encodes them **once** using the high‑quality `libfdk_aac`
encoder at 320 kbps CBR.

Because `libfdk_aac` is distributed under the *Fraunhofer FDK* license,
**ffmpeg is not compiled with it by default on most platforms**.

#### macOS (Homebrew)

```bash
# remove the pre‑built keg to avoid a naming conflict
brew uninstall --ignore-dependencies ffmpeg

# tap the community formulae that allow non‑free options
brew tap homebrew-ffmpeg/ffmpeg

# build ffmpeg with libfdk_aac enabled
brew install ffmpeg --with-fdk-aac --enable-nonfree
```

#### Linux (from source)

```bash
sudo apt-get remove ffmpeg         # remove distro build
sudo apt-get install autoconf automake build-essential libtool pkg-config                          libmp3lame-dev libopus-dev libvorbis-dev

git clone https://github.com/mstorsjo/fdk-aac.git && cd fdk-aac
autoreconf -fiv && ./configure --disable-shared && make -j$(nproc)
sudo make install && cd ..

git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg && cd ffmpeg
./configure --enable-gpl --enable-nonfree --enable-libfdk_aac             --enable-libmp3lame --enable-libopus
make -j$(nproc)
sudo make install
```

---

## 2.  Installation

```bash
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt    # installs Pillow, mutagen, html-to-markdown
```

`requirements.txt`

```
beautifulsoup4==4.13.4
html-to-markdown==1.3.2
html2text==2025.4.15
markdownify==1.1.0
mutagen==1.47.0
pillow==11.2.1
pytz==2025.2
six==1.17.0
soupsieve==2.7
typing_extensions==4.13.2
tzlocal==5.3.1
```

---

## 3.  Preparing the source data

1. In **Journey ➜ Settings ➜ Export**, choose **JSON**.  
   The export is a folder that contains one `.json` file per entry and a copy
   of every attached photo / audio file.

2. Place that folder (or its contents) into `journey_exports/`  
   (the default expected by the script).  
   The final directory structure should look like:

```
journey_exports/
├── 1522482448669-3fc298412714b3e4.json
├── 1522482448669-3fc298412714b3e4.jpg
├── ...
```

---

## 4.  Running the converter

```bash
python journey_to_dayone.py
```

* On completion you will see something like:  

  ```
  Exported 182 entries → dayone_export/Journey.json
  Packed Day One import → Journey.dayone.zip
  ```

* `dayone_export/` is a fully‑formed Day One bundle (unzipped).  
  The script additionally packs it into `Journey.dayone.zip` for convenience.

---

## 5.  Import into Day One

1. **macOS** – *File ➜ Import ➜ From JSON…* and select `Journey.dayone.zip`.  
2. **iOS** – share the ZIP to Day One, or copy it into iCloud Drive and import
   the same way.

All entries, photos, recordings, locations, weather, lists and Markdown
formatting should appear exactly as they did in Journey.

---

## 6.  Implementation details

### Markdown normalisation (`strip_html`)
* Journey stores the entry body as HTML.  
  `html‑to‑markdown` converts it to Markdown.
* Excess blank lines are collapsed and Journey’s `*` bullets are rewritten to
  `-` solely for consistency.
* Escaped punctuation introduced by Journey (`\#`, `\-`, `\+` …) is removed
  except where required (e.g. literal backticks).

### Day One richText synthesis
* Each line is inspected for headers, bullets or ordered‑list prefixes.  
  Matching lines receive a `line` attribute with the appropriate `header`,
  `listStyle`, `indentLevel`, and – for numbered lists – `listIndex`.
* Photos and audios are appended as `embeddedObjects`.

### Media handling
* **Photos** – copied byte‑for‑byte.  The destination filename is the file’s
  MD5 hash plus its original extension (`.jpg` / `.png`).  That is the naming
  convention used by Day One.
* **Audio** –  
  * If the source is already AAC (`.m4a` / `.aac`) or WAV, the file is copied.  
  * If the source is MP3, it is re‑encoded to AAC/M4A using `libfdk_aac` at
    320 kbps CBR to minimise further quality loss.

### Entry metadata
* Timestamps (`creationDate`, `modifiedDate`) are preserved and converted to
  RFC‑3339.
* Weather, GPS position, tags and favourites are mapped 1‑to‑1.

---

## 7.  License

The converter script itself is released under the MIT License.  
You are responsible for complying with the license terms of the Fraunhofer
FDK AAC codec when building ffmpeg with `--enable-nonfree`.

