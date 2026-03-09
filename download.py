import os
import sys
import json
import subprocess
import argparse
import re
import time
import signal
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# its basicly just color template you can ignore it
class C:
    R = "[0m"   # reset
    B = "[1m"   # bold
    D = "[2m"   # dim
    RD = "[31m" # red
    G = "[32m"  # green
    Y = "[33m"  # yellow
    BL = "[34m" # blue
    M = "[35m"  # magenta
    C = "[36m"  # cyan
    W = "[37m"  # white
    BR = "[91m" # red (bright)
    BG = "[92m" # green (bright)
    BY = "[93m" # yellow (bright)
    BB = "[94m" # blue (bright)
    BM = "[95m" # magenta (bright)
    BC = "[96m" # cyan (bright)
    BW = "[97m" # white (bright)

OK = f"{C.BG}[OK]{C.R}"
INFO = f"{C.BC}[INFO]{C.R}"
WARN = f"{C.BY}[WARNING]{C.R}"
ERR = f"{C.BR}{C.B}[ERROR]{C.R}"
TITLE = f"{C.BM}{C.B}"
BORDER = f"{C.C}"

try:
    from tqdm import tqdm
    import requests
except ImportError:
    print(f"{ERR} Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)
    
class DownloadStatus(Enum):
    PENDING = "pending"
    FETCHING = "fetching_info"
    READY = "ready"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

class FormatType(Enum):
    VIDEO_AUDIO = "video_audio"
    AUDIO_ONLY = "audio_only"

@dataclass
class VideoInfo:
    url: str
    title: str = ""
    duration: str = ""
    duration_seconds: int = 0
    uploader: str = ""
    formats: Dict = field(default_factory=dict)
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    selected_format: Optional[Dict] = None
    output_path: str = ""
    error_message: str = ""
    playlist_name: str = ""
    playlist_index: int = 0
    retry_count: int = 0
    is_private: bool = False

@dataclass
class PlaylistInfo:
    url: str
    title: str = ""
    uploader: str = ""
    total_count: int = 0
    valid_count: int = 0
    videos: List[VideoInfo] = field(default_factory=list)
    format_mode: str = "mp4"
    quality_mode: str = "best"
    output_folder: Optional[Path] = None


class YouTubeDownloader:
    def __init__(self, config_path: str = "config.json"):
        self.base_dir = Path(__file__).parent.absolute()
        self.config_path = self.base_dir / config_path
        self.bin_dir = self.base_dir / "bin"
        self.downloads_dir = self.base_dir / "downloads"
        self.downloads_dir.mkdir(exist_ok=True)
        self.config = self._load_config()
        self.yt_dlp_path = self._get_binary_path("yt-dlp")
        self.ffmpeg_path = self._get_binary_path("ffmpeg")
        self.queue: List[VideoInfo] = []
        self.queue_lock = threading.Lock()
        self.max_parallel = self.config.get("max_parallel_downloads", 2)
        self.active_downloads = 0
        self._stop_playlist = False
        self._current_playlist = None

    def _load_config(self) -> Dict:
        default_config = {
            "max_parallel_downloads": 2,
            "default_video_format": "mp4",
            "default_audio_format": "mp3",
            "default_video_quality": "720p",
            "default_audio_quality": "192k",
            "auto_update_ytdlp": True,
            "download_subtitles": False,
            "embed_thumbnail": False,
            "write_metadata": True
        }

        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                print(f"{WARN} Error loading config: {e}. Using defaults.")
                return default_config
        else:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            return default_config

    def _get_binary_path(self, name: str) -> str:
        bin_path = self.bin_dir / f"{name}.exe"
        if bin_path.exists():
            return str(bin_path.absolute())
        try:
            result = subprocess.run(
                ["where", name] if os.name == "nt" else ["which", name],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip().split("\n")[0]
        except:
            return name

    def check_binaries(self) -> Tuple[bool, List[str]]:
        missing = []
        for binary in ["yt-dlp", "ffmpeg"]:
            path = getattr(self, f"{binary.replace('-', '_')}_path")
            try:
                cmd = [path, "--version"] if binary != "ffmpeg" else [path, "-version"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    missing.append(binary)
            except:
                missing.append(binary)
        return len(missing) == 0, missing

    def check_update_yt_dlp(self) -> bool:
        if not self.config.get("auto_update_ytdlp", True):
            return True
        print("\n[CHECKING] Checking for yt-dlp updates...")
        try:
            result = subprocess.run([self.yt_dlp_path, "--version"],
                                  capture_output=True, text=True, timeout=10)
            current_version = result.stdout.strip()
            try:
                response = requests.get("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
                                       timeout=10)
                latest_version = response.json().get("tag_name", "").lstrip("v")
                if latest_version and latest_version != current_version:
                    print(f"[UPDATE AVAILABLE] yt-dlp {current_version} → {latest_version}")
                    choice = input("Update yt-dlp now? [Y/n]: ").strip().lower()
                    if choice in ["y", "yes", ""]:
                        print("[UPDATING] Downloading latest yt-dlp...")
                        update_result = subprocess.run([self.yt_dlp_path, "-U"],
                                                      capture_output=True, text=True, timeout=120)
                        if update_result.returncode == 0:
                            print(f"{OK} yt-dlp updated successfully!")
                        else:
                            print(f"{ERR} Update failed: {update_result.stderr}")
                            return False
                else:
                    print(f"{OK} yt-dlp is up to date ({current_version})")
                return True
            except requests.RequestException:
                print(f"{WARN} Could not check for updates (no internet?)")
                return True
        except Exception as e:
            print(f"{ERR} Could not check yt-dlp version: {e}")
            return True

    def _format_duration(self, seconds: int) -> str:
        if not seconds:
            return "Unknown"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
    def _format_size(self, size_bytes: int) -> str:
        if not size_bytes:
            return "Unknown"
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _get_unique_folder_name(self, base_path: Path, folder_name: str) -> Path:
        folder_path = base_path / folder_name
        counter = 1
        original_name = folder_name
        while folder_path.exists():
            folder_name = f"{original_name}({counter})"
            folder_path = base_path / folder_name
            counter += 1
        return folder_path



    def is_playlist_url(self, url: str) -> bool:

        playlist_patterns = [
            r'youtube\.com/playlist\?list=',
            r'youtube\.com/watch\?.*list=',
            r'youtu\.be/.*\?list=',
            r'youtube\.com/[^/]+/playlists',
            r'music\.youtube\.com/playlist\?list=',
            r'youtube\.com/shorts/.*list=',
            r'youtube\.com/channel/[^/]+/videos',
            r'youtube\.com/c/[^/]+/videos',
            r'youtube\.com/user/[^/]+/videos',
            r'youtube\.com/@\w+/videos',
            r'youtube\.com/@\w+/shorts'
        ]
        return any(re.search(pattern, url) for pattern in playlist_patterns)

    def extract_playlist_metadata(self, url: str) -> Optional[Dict]:

        print(f"{INFO} Getting playlist metadata...")
        try:
            cmd = [
                self.yt_dlp_path,
                "--flat-playlist",
                "--dump-single-json",
                "--no-warnings",
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                print(f"{ERR} Failed to fetch playlist: {result.stderr.strip()}")
                return None

            data = json.loads(result.stdout)
            return {
                "title": data.get("title", "Unknown Playlist"),
                "uploader": data.get("uploader", data.get("channel", "Unknown")),
                "total_count": len(data.get("entries", [])),
                "entries": data.get("entries", [])
            }
        except subprocess.TimeoutExpired:
            print(f"{ERR} Timeout fetching playlist metadata")
            return None
        except Exception as e:
            print(f"{ERR} Exception: {e}")
            return None

    def extract_playlist_entries(self, url: str) -> Tuple[List[VideoInfo], str, str, int]:

        metadata = self.extract_playlist_metadata(url)
        if not metadata:
            return []

        videos = []
        valid_index = 0

        for idx, entry in enumerate(metadata["entries"], 1):
            if not entry:
                continue


            if entry.get("availability") == "private" or not entry.get("title"):
                print(f"{WARN} Private/Unavailable video at position {idx}")
                continue

            valid_index += 1
            video = VideoInfo(
                url=entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                title=entry.get("title", "Unknown Title"),
                duration=self._format_duration(entry.get("duration", 0)),
                duration_seconds=entry.get("duration", 0),
                uploader=entry.get("uploader", entry.get("channel", "Unknown")),
                playlist_index=valid_index,
                status=DownloadStatus.PENDING
            )
            videos.append(video)

        return videos, metadata["title"], metadata["uploader"], valid_index

    def playlist_settings(self) -> Tuple[str, str]:

        print("\n" + "="*60)
        print("PLAYLIST DOWNLOAD SETTINGS")
        print("="*60)


        print("\nSelect format:")
        print("  1. MP4 Video + Audio")
        print("  2. MP3 Audio Only")

        while True:
            choice = input("\nChoice [1-2]: ").strip()
            if choice == "1":
                format_mode = "mp4"
                break
            elif choice == "2":
                format_mode = "mp3"
                break
            else:
                print(f"{ERR} Please enter 1 or 2")


        print("\nSelect quality:")
        print("  1. Best (recommended)")
        print("  2. Worst (smaller file)")

        while True:
            choice = input("\nChoice [1-2]: ").strip()
            if choice == "1":
                quality_mode = "best"
                break
            elif choice == "2":
                quality_mode = "worst"
                break
            else:
                print(f"{ERR} Please enter 1 or 2")

        return format_mode, quality_mode

    def playlist_mode(self):

        print(f"\n{BORDER}{"="*80}{C.R}")
        print(f"{'PLAYLIST DOWNLOAD MODE':^80}")
        print(f"{BORDER}{"="*80}{C.R}")


        url = input("\nEnter YouTube Playlist URL: ").strip()
        if not url:
            print(f"{ERR} No URL provided")
            return

        if not self.is_playlist_url(url):
            print(f"{ERR} This doesn't appear to be a playlist URL")
            print("Supported formats:")
            print("  - youtube.com/playlist?list=...")
            print("  - youtube.com/watch?v=...&list=...")
            print("  - youtube.com/@channel/videos")
            print("  - music.youtube.com/playlist?list=...")
            return


        print("\n[FETCHING] Extracting playlist entries...")
        videos, playlist_title, uploader, valid_count = self.extract_playlist_entries(url)

        if not videos:
            print(f"{ERR} No valid videos found in playlist")
            return

        print(f"{INFO} Playlist: {playlist_title}")
        print(f"{INFO} Channel: {uploader}")
        print(f"{INFO} Valid videos: {valid_count}")


        format_mode, quality_mode = self.playlist_settings()


        safe_title = re.sub(r'[\\/*?:"<>|]', "", playlist_title)
        output_folder = self._get_unique_folder_name(self.downloads_dir, safe_title)


        print("\n" + "="*60)
        print("PREVIEW (first 10 videos):")
        print("="*60)
        for i, video in enumerate(videos[:10], 1):
            print(f"{video.playlist_index:2d}. {video.title[:50]}{'...' if len(video.title) > 50 else ''} ({video.duration})")

        if len(videos) > 10:
            print(f"\n... and {len(videos) - 10} more videos")

        print(f"\nOutput folder: {output_folder}")
        print(f"Format: {format_mode.upper()} | Quality: {quality_mode.upper()}")
        print(f"{INFO}Press ctrl + c to stop download")


        confirm = input("\nStart download? [Y/n]: ").strip().lower()
        if confirm not in ["y", "yes", ""]:
            print(f"{WARN} Download aborted")
            return


        playlist_info = PlaylistInfo(
            url=url,
            title=playlist_title,
            uploader=uploader,
            total_count=len(videos),
            valid_count=valid_count,
            videos=videos,
            format_mode=format_mode,
            quality_mode=quality_mode,
            output_folder=output_folder
        )


        self._stop_playlist = False
        self._current_playlist = playlist_info
        self.download_playlist(playlist_info)

    def download_playlist(self, playlist: PlaylistInfo):

        print(f"\n{BORDER}{"="*80}{C.R}")
        print(f"{'STARTING PLAYLIST DOWNLOAD':^80}")
        print(f"{BORDER}{"="*80}{C.R}")


        playlist.output_folder.mkdir(parents=True, exist_ok=True)


        original_sigint = signal.getsignal(signal.SIGINT)
        def signal_handler(sig, frame):
            print("\n[INTERRUPT] Stopping playlist download...")
            self._stop_playlist = True
        signal.signal(signal.SIGINT, signal_handler)

        completed = 0
        failed = 0
        skipped = 0

        try:
            for i, video in enumerate(playlist.videos, 1):
                if self._stop_playlist:
                    print(f"\n[STOPPED] Download stopped at video {i}/{len(playlist.videos)}")
                    break


                print(f"\n[{i}/{len(playlist.videos)}] {video.title[:60]}")
                print("-" * 60)


                video.playlist_name = playlist.title


                success = self.download_with_retry(video, playlist)

                if success:
                    completed += 1
                elif video.status == DownloadStatus.SKIPPED:
                    skipped += 1
                else:
                    failed += 1


                if i < len(playlist.videos) and not self._stop_playlist:
                    time.sleep(0.5)

        finally:

            signal.signal(signal.SIGINT, original_sigint)
            self._current_playlist = None


        print(f"\n{BORDER}{"="*80}{C.R}")
        print(f"{'PLAYLIST DOWNLOAD COMPLETE':^80}")
        print(f"{BORDER}{"="*80}{C.R}")
        print(f"  Total: {len(playlist.videos)}")
        print(f"  [92mCompleted:[0m {completed}")
        print(f"  [91mFailed:[0m {failed}")
        print(f"  [93mSkipped:[0m {skipped}")
        print(f"  Location: {playlist.output_folder}")

        if failed > 0:
            print("\nFailed downloads:")
            for v in playlist.videos:
                if v.status == DownloadStatus.FAILED:
                    print(f"  - {v.playlist_index:2d}. {v.title}: {v.error_message}")

    def download_with_retry(self, video: VideoInfo, playlist: PlaylistInfo, max_retry: int = 3) -> bool:

        for attempt in range(max_retry):
            if self._stop_playlist:
                return False


            pbar = tqdm(
                total=100,
                desc=f"{video.playlist_index:02d}. {video.title[:30]}",
                unit="%",
                bar_format="{desc:<35} |{bar:20}| {percentage:6.2f}% {rate_fmt} ETA: {remaining}",
                position=0,
                leave=True
            )

            success = self.download_single_playlist_video(video, playlist, pbar)
            pbar.close()

            if success:
                return True

            video.retry_count += 1
            if video.retry_count < max_retry and not self._stop_playlist:
                print(f"{WARN}[RETRY {video.retry_count}/{max_retry}] Retrying in 2 seconds...")
                time.sleep(2)

        print(f"{ERR} {video.title[:50]} after {max_retry} retries")
        video.status = DownloadStatus.FAILED
        return False

    def download_single_playlist_video(self, video: VideoInfo, playlist: PlaylistInfo, progress_bar: tqdm) -> bool:

        if not video.selected_format:

            format_mode = playlist.format_mode
            quality_mode = playlist.quality_mode

            if format_mode == "mp4":
                if quality_mode == "best":
                    format_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                else:
                    format_spec = "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst"
                video.selected_format = {
                    "type": FormatType.VIDEO_AUDIO,
                    "format_spec": format_spec
                }
            else:
                if quality_mode == "best":
                    format_spec = "bestaudio/best"
                else:
                    format_spec = "worstaudio/worst"
                video.selected_format = {
                    "type": FormatType.AUDIO_ONLY,
                    "format_spec": format_spec
                }

        video.status = DownloadStatus.DOWNLOADING


        safe_title = re.sub(r'[\\/*?:"<>|]', "", video.title)
        output_template = str(playlist.output_folder / f"{video.playlist_index:02d}. {safe_title}.%(ext)s")

        format_type = video.selected_format.get("type")
        format_spec = video.selected_format.get("format_spec", "best")

        if format_type == FormatType.VIDEO_AUDIO:
            cmd = [
                self.yt_dlp_path,
                "-f", format_spec,
                "--merge-output-format", "mp4",
                "--ffmpeg-location", self.ffmpeg_path,
                "-o", output_template,
                "--newline",
                "--progress",
                "--no-warnings",
                "--ignore-errors"
            ]
        else:
            cmd = [
                self.yt_dlp_path,
                "-f", format_spec,
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "--ffmpeg-location", self.ffmpeg_path,
                "-o", output_template,
                "--newline",
                "--progress",
                "--no-warnings",
                "--ignore-errors"
            ]
            if self.config.get("embed_thumbnail"):
                cmd.append("--embed-thumbnail")

        cmd.append(video.url)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            last_progress = 0

            for line in process.stdout:
                line = line.strip()


                if "[download]" in line and "%" in line:
                    try:
                        match = re.search(r'(\d+\.\d+)%', line)
                        if match:
                            progress = float(match.group(1))
                            video.progress = progress
                            progress_bar.n = progress
                            progress_bar.refresh()

                        speed_match = re.search(r'at\s+(\S+)', line)
                        if speed_match:
                            video.speed = speed_match.group(1)

                        eta_match = re.search(r'ETA\s+(\S+)', line)
                        if eta_match:
                            video.eta = eta_match.group(1)
                    except:
                        pass

                if "ERROR:" in line:
                    video.error_message = line
                    print(f"\n{ERR} {line}")

                if self._stop_playlist:
                    process.terminate()
                    video.status = DownloadStatus.CANCELLED
                    return False

            process.wait()

            if process.returncode == 0:
                video.status = DownloadStatus.COMPLETED
                video.progress = 100.0
                progress_bar.n = 100
                progress_bar.refresh()


                for ext in ["mp4", "mp3", "m4a", "webm"]:
                    potential_file = playlist.output_folder / f"{video.playlist_index:02d}. {safe_title}.{ext}"
                    if potential_file.exists():
                        video.output_path = str(potential_file)
                        break

                return True
            else:
                video.status = DownloadStatus.FAILED
                if not video.error_message:
                    video.error_message = f"Download failed (exit code: {process.returncode})"
                return False

        except Exception as e:
            video.status = DownloadStatus.FAILED
            video.error_message = str(e)
            return False



    def fetch_video_info(self, url: str) -> Optional[VideoInfo]:
        print(f"\n[FETCHING] Getting info for: {url}")
        try:
            cmd = [
                self.yt_dlp_path,
                "--dump-json",
                "--no-warnings",
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "Private video" in error_msg:
                    print(f"{ERR} Video is private: {url}")
                elif "Video unavailable" in error_msg:
                    print(f"{ERR} Video unavailable (region blocked or deleted): {url}")
                else:
                    print(f"{ERR} Failed to fetch info: {error_msg}")
                return None

            info = json.loads(result.stdout.split("\n")[0])

            video_info = VideoInfo(
                url=url,
                title=info.get("title", "Unknown Title"),
                duration=self._format_duration(info.get("duration", 0)),
                duration_seconds=info.get("duration", 0),
                uploader=info.get("uploader", "Unknown"),
                status=DownloadStatus.READY
            )

            formats = info.get("formats", [])
            video_formats = []
            for f in formats:
                if f.get("vcodec") != "none" and f.get("acodec") != "none":
                    height = f.get("height", 0)
                    if height:
                        video_formats.append({
                            "format_id": f["format_id"],
                            "resolution": f"{height}p",
                            "height": height,
                            "ext": f.get("ext", "mp4"),
                            "filesize": f.get("filesize") or f.get("filesize_approx", 0)
                        })

            audio_formats = []
            for f in formats:
                if f.get("acodec") != "none" and f.get("vcodec") == "none":
                    abr = f.get("abr", 0)
                    if abr:
                        audio_formats.append({
                            "format_id": f["format_id"],
                            "abr": abr,
                            "quality": f"{int(abr)}k",
                            "ext": f.get("ext", "m4a"),
                            "filesize": f.get("filesize") or f.get("filesize_approx", 0)
                        })

            video_formats.sort(key=lambda x: x["height"], reverse=True)
            audio_formats.sort(key=lambda x: x["abr"], reverse=True)

            seen_res = set()
            unique_video = []
            for f in video_formats:
                if f["resolution"] not in seen_res:
                    seen_res.add(f["resolution"])
                    unique_video.append(f)

            seen_abr = set()
            unique_audio = []
            for f in audio_formats:
                if f["quality"] not in seen_abr:
                    seen_abr.add(f["quality"])
                    unique_audio.append(f)

            video_info.formats = {
                "video_audio": unique_video,
                "audio_only": unique_audio
            }

            print(f"{OK} Found: {video_info.title} ({video_info.duration})")
            return video_info

        except subprocess.TimeoutExpired:
            print(f"{ERR} Timeout fetching info for: {url}")
            return None
        except Exception as e:
            print(f"{ERR} Exception fetching info: {e}")
            return None

    def display_queue(self):
        print(f"\n{BORDER}{"="*80}{C.R}")
        print(f"{'QUEUE':^80}")
        print(f"{BORDER}{"="*80}{C.R}")

        if not self.queue:
            print("Queue is empty. Add some videos!")
            print(f"{BORDER}{"="*80}{C.R}")
            return

        print(f"{'#':<4} {'Title':<40} {'Status':<15} {'Progress':<10}")
        print(f"{BORDER}{"-"*80}{C.R}")

        for i, video in enumerate(self.queue, 1):
            title = video.title[:37] + "..." if len(video.title) > 40 else video.title
            status = video.status.value.replace("_", " ").title()
            progress = f"{video.progress:.1f}%" if video.progress > 0 else "-"

            status_display = status
            if video.status == DownloadStatus.COMPLETED:
                status_display = f"{OK} {status}"
            elif video.status == DownloadStatus.FAILED:
                status_display = f"[X] {status}"
            elif video.status == DownloadStatus.DOWNLOADING:
                status_display = f"[>] {status}"

            print(f"{i:<4} {title:<40} {status_display:<15} {progress:<10}")

        print(f"{BORDER}{"="*80}{C.R}")
        print(f"Total: {len(self.queue)} videos | Parallel downloads: {self.max_parallel}")
        print(f"{BORDER}{"="*80}{C.R}")

    def add_to_queue(self, url: str) -> bool:
        for video in self.queue:
            if video.url == url:
                print(f"{WARN} URL already in queue: {url}")
                return False

        video_info = self.fetch_video_info(url)
        if video_info:
            with self.queue_lock:
                self.queue.append(video_info)
            return True
        return False

    def remove_from_queue(self, index: int) -> bool:
        with self.queue_lock:
            if 1 <= index <= len(self.queue):
                video = self.queue.pop(index - 1)
                print(f"[REMOVED] {video.title}")
                return True
            else:
                print(f"{ERR} Invalid index: {index}")
                return False

    def clear_queue(self):
        with self.queue_lock:
            self.queue = [v for v in self.queue if v.status in [DownloadStatus.DOWNLOADING, DownloadStatus.COMPLETED]]
            print("[CLEARED] Queue cleared (completed downloads kept in history)")

    def select_format(self, video: VideoInfo) -> Optional[Dict]:
        print(f"\n{'='*60}")
        print(f"Select format for: {video.title}")
        print(f"Duration: {video.duration} | Uploader: {video.uploader}")
        print(f"{'='*60}")

        print("\nFormat options:")
        print("1. MP4 Video + Audio (Recommended)")
        print("2. MP3 Audio Only")

        while True:
            choice = input("\nSelect format [1-2]: ").strip()

            if choice == "1":
                formats = video.formats.get("video_audio", [])
                if not formats:
                    print(f"{ERR} No video+audio formats available")
                    continue

                print("\nAvailable resolutions:")
                for i, f in enumerate(formats, 1):
                    size = self._format_size(f.get("filesize", 0))
                    print(f"{i}. {f['resolution']} ({size})")

                try:
                    res_choice = int(input("\nSelect resolution: "))
                    if 1 <= res_choice <= len(formats):
                        selected = formats[res_choice - 1]
                        selected["type"] = FormatType.VIDEO_AUDIO
                        return selected
                except ValueError:
                    pass
                print(f"{ERR} Invalid selection")

            elif choice == "2":
                formats = video.formats.get("audio_only", [])
                if not formats:
                    print(f"{ERR} No audio formats available")
                    continue

                print("\nAvailable qualities:")
                for i, f in enumerate(formats, 1):
                    size = self._format_size(f.get("filesize", 0))
                    print(f"{i}. {f['quality']} ({size})")

                try:
                    qual_choice = int(input("\nSelect quality: "))
                    if 1 <= qual_choice <= len(formats):
                        selected = formats[qual_choice - 1]
                        selected["type"] = FormatType.AUDIO_ONLY
                        return selected
                except ValueError:
                    pass
                print(f"{ERR} Invalid selection")
            else:
                print(f"{ERR} Please enter 1 or 2")

    def download_video(self, video: VideoInfo, progress_bar: tqdm) -> bool:
        if not video.selected_format:
            print(f"{ERR} No format selected for: {video.title}")
            return False

        video.status = DownloadStatus.DOWNLOADING

        safe_title = re.sub(r'[\\/*?:"<>|]', "", video.title)
        output_template = str(self.downloads_dir / f"{safe_title}.%(ext)s")

        format_type = video.selected_format.get("type")

        if format_type == FormatType.VIDEO_AUDIO:
            format_spec = f"bestvideo[height<={video.selected_format['height']}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            cmd = [
                self.yt_dlp_path,
                "-f", format_spec,
                "--merge-output-format", "mp4",
                "--ffmpeg-location", self.ffmpeg_path,
                "-o", output_template,
                "--newline",
                "--progress",
                "--no-warnings"
            ]
        elif format_type == FormatType.AUDIO_ONLY:
            format_spec = f"bestaudio[abr<={video.selected_format['abr']}]/bestaudio"
            cmd = [
                self.yt_dlp_path,
                "-f", format_spec,
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "--ffmpeg-location", self.ffmpeg_path,
                "-o", output_template,
                "--newline",
                "--progress",
                "--no-warnings"
            ]
            if self.config.get("embed_thumbnail"):
                cmd.append("--embed-thumbnail")
            cmd = [c for c in cmd if c]
        else:
            print(f"{ERR} Unknown format type: {format_type}")
            return False

        cmd.append(video.url)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            for line in process.stdout:
                line = line.strip()

                if "[download]" in line and "%" in line:
                    try:
                        match = re.search(r'(\d+\.\d+)%', line)
                        if match:
                            progress = float(match.group(1))
                            video.progress = progress
                            progress_bar.n = progress
                            progress_bar.refresh()

                        speed_match = re.search(r'at\s+(\S+)', line)
                        if speed_match:
                            video.speed = speed_match.group(1)

                        eta_match = re.search(r'ETA\s+(\S+)', line)
                        if eta_match:
                            video.eta = eta_match.group(1)
                    except:
                        pass

                if "ERROR:" in line:
                    video.error_message = line
                    print(f"\n{ERR} {line}")

            process.wait()

            if process.returncode == 0:
                video.status = DownloadStatus.COMPLETED
                video.progress = 100.0
                progress_bar.n = 100
                progress_bar.refresh()
                progress_bar.close()

                for ext in ["mp4", "mp3", "m4a", "webm"]:
                    potential_file = self.downloads_dir / f"{safe_title}.{ext}"
                    if potential_file.exists():
                        video.output_path = str(potential_file)
                        break

                return True
            else:
                video.status = DownloadStatus.FAILED
                if not video.error_message:
                    video.error_message = "Download failed (unknown error)"
                progress_bar.close()
                return False

        except Exception as e:
            video.status = DownloadStatus.FAILED
            video.error_message = str(e)
            progress_bar.close()
            return False

    def start_downloads(self):
        pending_videos = [v for v in self.queue if v.status == DownloadStatus.READY]

        if not pending_videos:
            print("\n{INFO} No videos ready to download")
            return

        print(f"\n{INFO} Preparing {len(pending_videos)} videos for download...")

        for video in pending_videos:
            if not video.selected_format:
                selected = self.select_format(video)
                if selected:
                    video.selected_format = selected
                else:
                    video.status = DownloadStatus.CANCELLED

        to_download = [v for v in pending_videos if v.selected_format]

        if not to_download:
            print(f"{INFO} No videos to download")
            return

        print(f"\n[START] Downloading {len(to_download)} videos (max parallel: {self.max_parallel})...")
        print(f"{BORDER}{"="*80}{C.R}")

        progress_bars = {}
        for video in to_download:
            pbar = tqdm(
                total=100,
                desc=video.title[:30],
                unit="%",
                bar_format="{desc:<35} |{bar:20}| {percentage:6.2f}% {rate_fmt} ETA: {remaining}",
                position=0,
                leave=True
            )
            progress_bars[video.url] = pbar

        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_video = {
                executor.submit(self.download_video, video, progress_bars[video.url]): video
                for video in to_download
            }

            for future in as_completed(future_to_video):
                video = future_to_video[future]
                try:
                    success = future.result()
                    if success:
                        print(f"[COMPLETED] {video.title}")
                    else:
                        print(f"{ERR} {video.title}: {video.error_message}")
                except Exception as e:
                    print(f"[EXCEPTION] {video.title}: {e}")
                    video.status = DownloadStatus.FAILED

        print(f"\n{BORDER}{"="*80}{C.R}")
        print("[DONE] All downloads completed!")
        print(f"{BORDER}{"="*80}{C.R}")

        completed = sum(1 for v in to_download if v.status == DownloadStatus.COMPLETED)
        failed = sum(1 for v in to_download if v.status == DownloadStatus.FAILED)

        print(f"\nSummary:")
        print(f"  [92mCompleted:[0m {completed}")
        print(f"  [91mFailed:[0m {failed}")
        print(f"  Download location: {self.downloads_dir}")

        if failed > 0:
            print("\nFailed downloads:")
            for v in to_download:
                if v.status == DownloadStatus.FAILED:
                    print(f"  - {v.title}: {v.error_message}")

    def interactive_mode(self):
        print(f"\n{BORDER}{"="*80}{C.R}")
        print(f"{TITLE}{'YOUTUBE DOWNLOADER':^80}{C.R}")
        print(f"{TITLE}{'Queue-based Parallel Downloader':^80}{C.R}")
        print(f"{BORDER}{"="*80}{C.R}")

        ok, missing = self.check_binaries()
        if not ok:
            print(f"\n{ERR} Missing required binaries: {', '.join(missing)}")
            print(f"Please place these files in: {self.bin_dir}")
            print("Or ensure they are in your system PATH")
            return

        print(f"\n{OK} All binaries found")
        print(f"  yt-dlp: {self.yt_dlp_path}")
        print(f"  ffmpeg: {self.ffmpeg_path}")

        if not self.check_update_yt_dlp():
            return

        while True:
            self.display_queue()

            print("\nCommands:")
            print("  [36m[A][0mdd URL      - Add single video to queue")
            print("  [36m[P][0mlaylist     - Enter playlist download mode")
            print("  [36m[R][0memove #     - Remove video from queue")
            print("  [36m[S][0mtart        - Start downloading queue")
            print("  [36m[C][0mlear        - Clear pending queue")
            print("  [36m[Q][0muit         - Exit application")

            choice = input("\nEnter command: ").strip().lower()

            if choice == "a" or choice == "add":
                url = input("Enter YouTube URL: ").strip()
                if url:
                    if "youtube.com" in url or "youtu.be" in url:

                        if self.is_playlist_url(url):
                            print(f"{INFO} This appears to be a playlist URL.")
                            print("Use [36m[P][0mlaylist command for better playlist handling.")
                            cont = input("Add as single video anyway? [y/N]: ").strip().lower()
                            if cont == "y":
                                self.add_to_queue(url)
                        else:
                            self.add_to_queue(url)
                    else:
                        print(f"{ERR} Invalid YouTube URL")

            elif choice == "p" or choice == "playlist":
                self.playlist_mode()

            elif choice.startswith("r") or choice.startswith("remove"):
                try:
                    parts = choice.split()
                    if len(parts) > 1:
                        idx = int(parts[1])
                    else:
                        idx = int(input("Enter index to remove: "))
                    self.remove_from_queue(idx)
                except ValueError:
                    print(f"{ERR} Please enter a valid number")

            elif choice == "s" or choice == "start":
                self.start_downloads()

            elif choice == "c" or choice == "clear":
                confirm = input("Clear all pending videos? [y/N]: ").strip().lower()
                if confirm == "y":
                    self.clear_queue()

            elif choice == "q" or choice == "quit":
                downloading = any(v.status == DownloadStatus.DOWNLOADING for v in self.queue)
                if downloading:
                    confirm = input("Downloads in progress. Quit anyway? [y/N]: ").strip().lower()
                    if confirm != "y":
                        continue
                print("\nGoodbye!")
                break
            else:
                print(f"{ERR} Unknown command")

    def quick_download(self, urls: List[str], format_type: str = None, quality: str = None):

        print("\n[QUICK MODE] Adding videos to queue...")


        if not format_type:
            format_type = "mp4"
            print(f"{INFO} No format specified, defaulting to MP4")

        if not quality:
            quality = "best"
            print(f"{INFO} No quality specified, defaulting to '{quality}'")
        elif quality not in ["best", "worst"]:
            print(f"{WARN} Quality '{quality}' not recognized. Using 'best'")
            quality = "best"

        print(f"{INFO} Format: {format_type.upper()} | Quality: {quality.upper()}")

        successful = 0
        failed = 0

        for url in urls:
            if self.add_to_queue(url):
                video = self.queue[-1]


                if format_type == "mp4":
                    formats = video.formats.get("video_audio", [])
                    if formats:
                        if quality == "best":
                            selected = formats[0]
                        else:
                            selected = formats[-1]

                        selected["type"] = FormatType.VIDEO_AUDIO

                        selected["format_spec"] = f"bestvideo[height<={selected['height']}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                        video.selected_format = selected
                        successful += 1
                        print(f"  ✓ {video.title} - {selected['resolution']} (best{'' if quality == 'best' else ' worst'})")
                    else:
                        print(f"  ✗ {video.title} - No video formats available")
                        video.status = DownloadStatus.SKIPPED
                        failed += 1

                elif format_type == "mp3":
                    formats = video.formats.get("audio_only", [])
                    if formats:
                        if quality == "best":
                            selected = formats[0]
                        else:
                            selected = formats[-1]

                        selected["type"] = FormatType.AUDIO_ONLY

                        selected["format_spec"] = f"bestaudio[abr<={selected['abr']}]/bestaudio"
                        video.selected_format = selected
                        successful += 1
                        print(f"  ✓ {video.title} - {selected['quality']} (best{'' if quality == 'best' else ' worst'})")
                    else:
                        print(f"  ✗ {video.title} - No audio formats available")
                        video.status = DownloadStatus.SKIPPED
                        failed += 1
            else:
                failed += 1

        print(f"\n{INFO} Ready to download: {successful} video(s), Failed: {failed} video(s)")

        if successful > 0:
            self.start_downloads()
        else:
            print(f"{ERR} No videos available to download")

    def quick_playlist_download(self, url: str, format_type: str = "mp4", quality: str = "best"):

        print("\n[QUICK PLAYLIST MODE] Starting download...")

        if not self.is_playlist_url(url):
            print(f"{ERR} This doesn't appear to be a playlist URL")
            return


        videos, playlist_title, uploader, valid_count = self.extract_playlist_entries(url)

        if not videos:
            print(f"{ERR} No valid videos found in playlist")
            return

        print(f"{INFO} Playlist: {playlist_title}")
        print(f"{INFO} Videos: {valid_count}")
        print(f"{INFO} Format: {format_type.upper()} | Quality: {quality.upper()}")


        safe_title = re.sub(r'[\\/*?:"<>|]', "", playlist_title)
        output_folder = self._get_unique_folder_name(self.downloads_dir, safe_title)
        output_folder.mkdir(parents=True, exist_ok=True)


        playlist_info = PlaylistInfo(
            url=url,
            title=playlist_title,
            uploader=uploader,
            total_count=len(videos),
            valid_count=valid_count,
            videos=videos,
            format_mode=format_type,
            quality_mode=quality,
            output_folder=output_folder
        )


        self._stop_playlist = False
        self._current_playlist = playlist_info
        self.download_playlist(playlist_info)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Downloader - Queue-based Parallel Downloader with Playlist Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Interactive mode
  %(prog)s -u URL1 URL2              # Quick download (best quality MP4)
  %(prog)s -u URL -f mp3            # Download as MP3 audio
  %(prog)s -u URL -f mp4 -q best    # Download MP4 at best
  %(prog)s -p PLAYLIST_URL          # Quick playlist download (best MP4)
  %(prog)s -p URL -f mp3 -q worst  # Playlist as MP3, worst quality
        """
    )

    parser.add_argument(
        "-u", "--url",
        nargs="+",
        help="YouTube URL(s) to download"
    )

    parser.add_argument(
        "-p", "--playlist",
        dest="playlist_url",
        help="YouTube Playlist URL for quick download (uses best/worst quality)"
    )

    parser.add_argument(
        "-f", "--format",
        choices=["mp4", "mp3"],
        help="Download format (mp4 or mp3)"
    )

    parser.add_argument(
        "-q", "--quality",
        help="Quality for quick mode: best/worst for playlist and url videos"
    )

    parser.add_argument(
        "--max-parallel",
        type=int,
        default=2,
        help="Maximum parallel downloads (default: 2)"
    )

    args = parser.parse_args()

    downloader = YouTubeDownloader()

    if args.max_parallel:
        downloader.max_parallel = args.max_parallel

    ok, missing = downloader.check_binaries()
    if not ok:
        print(f"{ERR} Missing required binaries: {', '.join(missing)}")
        print(f"Please place these files in: {downloader.bin_dir}")
        print("Or ensure they are in your system PATH")
        sys.exit(1)


    if args.playlist_url:
        if not downloader.check_update_yt_dlp():
            sys.exit(1)

        format_type = args.format if args.format else "mp4"
        quality = args.quality if args.quality else "best"


        if quality not in ["best", "worst"]:
            print(f"{WARN} For playlist mode, quality should be 'best' or 'worst'")
            print(f"{INFO} Defaulting to 'best'")
            quality = "best"

        downloader.quick_playlist_download(args.playlist_url, format_type, quality)


    elif args.url:
        if not args.format:
            print(f"{INFO} No format specified, defaulting to MP4")
            args.format = "mp4"

        if not downloader.check_update_yt_dlp():
            sys.exit(1)

        downloader.quick_download(args.url, args.format, args.quality)


    else:
        downloader.interactive_mode()


if __name__ == "__main__":
    main()