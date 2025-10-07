# Spotify → TIDAL Playlist Migrator

This project is a Python script that helps you **migrate your playlists from Spotify to TIDAL**.

It uses the official **Spotify Web API** and **TIDAL OpenAPI** to:

* Authenticate your Spotify and TIDAL accounts via OAuth2
* Fetch all (or selected) Spotify playlists and their tracks
* Create new playlists on TIDAL
* Search and match tracks from Spotify on TIDAL
* Populate your TIDAL playlists with the matched tracks

---

## 🚀 Features

* 🔑 OAuth2 authentication for both Spotify and TIDAL
* 📂 Export Spotify playlists and tracks to JSON
* 🎵 Create new playlists on TIDAL with the same names
* 🔍 Search for matching tracks in TIDAL (with retry & rate-limit handling)
* 📝 Save tracks that couldn’t be found in `tidal_not_found.txt`

---

## ⚙️ Requirements

* Python **3.8+**
* Spotify **Client ID & Client Secret**
* TIDAL **Client ID**
* Installed dependencies (see below)

---

## 📦 Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/maggenium/Spotify-to-Tidal.git
cd Spotify-to-Tidal
pip install -r requirements.txt
```

Create a `.env` file in the project root and add your credentials:

```
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
TIDAL_CLIENT_ID=your_tidal_client_id
```

---

## ▶️ Usage

Run the script:

```bash
python main.py
```

Steps:

1. The script opens a browser window asking you to **log in to Spotify** and authorize.
2. It fetches your playlists (except those you blacklist in the code).
3. It saves them to a JSON file (`playlists3.json`).
4. The script opens another browser window asking you to **log in to TIDAL** and authorize.
5. It creates corresponding playlists on TIDAL and fills them with tracks.

---

## 📝 Notes & Limitations

* Some Spotify tracks may not exist on TIDAL. Missing tracks are logged in `tidal_not_found.txt`.
* There is basic retry logic for Spotify/TIDAL rate limits.
* Currently, blacklists are hardcoded in the script.
* Only **new playlists** are created on TIDAL (no merging with existing playlists yet).

---

## 🔮 Future Development

* Add **CLI arguments** for custom runs (blacklist/whitelist, specific playlists, etc.)
* Improve **error handling**
* Option to **update existing playlists** instead of always creating new ones
* Build a **UI with progress bars** for friendlier use

---

## ⚠️ Disclaimer

This project is an unofficial tool and is **not affiliated with Spotify or TIDAL**.
It uses their public APIs to migrate playlists between platforms.

Use at your own discretion.

* Your account credentials are handled only via the official OAuth2 login pages.
* The developer of this script assumes **no responsibility for data loss, API changes, account issues, or playlist mismatches**.
* Always back up your playlists before running migration tools.

---

## 📜 License

MIT License – feel free to use and adapt.

---


