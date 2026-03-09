# YT_POP_CLI 🎥
**YouTube POP Command Line Downloader**

A simple command line interface youtube downloader for windows. Design to help people who want to use yt-dlp.

> [!NOTE]  
> This project is 80% made by kimi k2.5 ( Artificial Intelligence )
---

## ✨ Features
* **Parallel Downloads**: Download multiple videos simultaneously (default: 2) using a thread pool executor.
* **Playlist Support**: Specialized mode for fetching and downloading entire playlists with automatic folder creation.
* **Smart Binary Management**: Automatically detects and uses `yt-dlp` and `ffmpeg` from the `bin/` folder or system PATH.
* **Interactive CLI**: Easy-to-use menu for adding URLs, managing the queue, and selecting formats.
* **Quick Modes**: Command-line arguments for fast single-video or playlist downloads without entering the menu.
* **Automated Setup**: The `run.bat` script handles virtual environment (`.venv`) creation and dependency installation automatically. 

---

## 🚀 Getting Started

### Installation & Launch
You don't need to manually install all dependencies. Simply use the provided launcher:

1.  Download python 3.8+ from [python.org](https://www.python.org/downloads/) or microsoft store
2.  Install dependency from [yt-dlp github](https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#installation) and [ffmpeg official gyandev](https://www.gyan.dev/ffmpeg/builds/).
3.  Clone or download this repository.
4.  Double-click **`run.bat`**. 
5.  The script will:
    * Create a virtual environment if it doesn't exist. 
    * Install/update `pip` and required dependencies (`tqdm`, `requests`). 
    * Start the application. 

---

## 📂 Project Structure
```
.
├── .venv/
│   └── stuff (auto created)
├── bin/
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── yt-dlp.exe
├── downloads/
│   └── (your stuff)
├── config.json
├── download.py
├── license
├── readme.md
├── requirements.txt
└── run.bat
```

---
## 🛠 Usage

### 1. Interactive Mode
Run `run.bat` to access the main menu:
* **[A] Add URL**: Add a single video to your queue.
* **[P] Playlist**: Enter the playlist downloader mode.
* **[S] Start**: Begin downloading all "Ready" items in the queue.
* **[R] Remove**: Delete a specific item from the queue by its index.
* **[C] Clear**: Wipe the pending queue.

### 2. CLI Arguments (Quick Mode)
You can pass arguments directly to `run.bat` (which forwards them to the Python script): 

| Command | Description |
| :--- | :--- |
| `run.bat -u [URL]` | Quick download (Best MP4). |
| `run.bat -u [URL1] [URL2] [URL3]` | Multiple Quick download (Best MP4). |
| `run.bat -u [URL] -f mp3` | Quick download as MP3. |
| `run.bat -u [URL] -q best` | Quick download with best quality. |
| `run.bat -u [URL] -q worst` | Quick download with worst quality. |
| `run.bat -p [URL]` | Quick playlist download. |
| `run.bat --max-parallel 4` | Increase simultaneous downloads. |

---

## 🤝 Contributing
Contributions are what make the open-source community an amazing place to learn, inspire, and create.

1.  **Issues**: If you find a bug or have a suggestion, please **open an Issue**.
2.  **Pull Requests**: 
    * If you have a bug fix or an update, feel free to submit a **Merge Request**.
    * Ensure your code follows the existing style and is well-tested.

---

## 📜 License
This project is licensed under the [**MIT License**](LICENSE). 

Copyright (c) 2026 **Zenith** 
