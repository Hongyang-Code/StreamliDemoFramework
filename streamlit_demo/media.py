from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from .index import FileEntry


@dataclass(frozen=True)
class Preview:
    kind: str
    source: str
    size: int
    notice: str = ""
    error: str = ""


def _data_url(mime: str, content: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


class PreviewManager:
    def __init__(self, data_dir: Path, cache_limit_mb: float):
        directory_key = hashlib.sha256(str(data_dir.resolve()).encode("utf-8")).hexdigest()[:20]
        self.cache_dir = Path(tempfile.gettempdir()) / "streamlit-demo-framework" / directory_key
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_limit_bytes = int(cache_limit_mb * 1024 * 1024)

    @staticmethod
    def check_video_tools() -> tuple[bool, str]:
        ffmpeg = _ffmpeg_exe()
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            return False, "视频模式需要 ffmpeg 和 ffprobe，请安装后重新启动。"
        if not _h264_encoder():
            return False, "当前 ffmpeg 缺少 libx264 或 libopenh264 编码器，无法生成浏览器兼容预览。"
        return True, ""

    def _cache_path(self, entry: FileEntry, mode: str, budget: int, suffix: str) -> Path:
        key = "|".join(
            (str(entry.path), str(entry.size), str(entry.mtime_ns), mode, str(budget), suffix)
        )
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}{suffix}"

    def _prune(self) -> None:
        files = []
        total = 0
        for path in self.cache_dir.iterdir():
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            total += stat.st_size
            files.append((stat.st_atime_ns, path, stat.st_size))
        if total <= self.cache_limit_bytes:
            return
        for _, path, size in sorted(files):
            path.unlink(missing_ok=True)
            total -= size
            if total <= self.cache_limit_bytes:
                break

    def prepare(self, entry: FileEntry, mode: str, budget_bytes: int) -> Preview:
        try:
            if mode == "image":
                return self._image(entry, budget_bytes)
            if mode == "video":
                return self._video(entry, budget_bytes)
            return self._text(entry, budget_bytes)
        except Exception as exc:  # A broken sample must not take down the page.
            return Preview(kind=mode, source="", size=0, error=f"预览失败: {exc}")

    def _image(self, entry: FileEntry, budget: int) -> Preview:
        with Image.open(entry.path) as image:
            width, height = image.size
            is_large_gif = entry.extension == ".gif" and entry.size > budget
            if entry.size <= budget and max(width, height) <= 1920:
                content = entry.path.read_bytes()
                mime = mimetypes.guess_type(entry.name)[0] or "image/jpeg"
                return Preview("image", _data_url(mime, content), len(content))

            cache_path = self._cache_path(entry, "image", budget, ".webp")
            if cache_path.exists() and cache_path.stat().st_size <= budget:
                os.utime(cache_path, None)
                content = cache_path.read_bytes()
                notice = "大型 GIF 已生成首帧静态预览" if is_large_gif else "已生成压缩预览"
                return Preview("image", _data_url("image/webp", content), len(content), notice)

            image.seek(0)
            converted = ImageOps.exif_transpose(image).convert("RGB")
            converted.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            quality = 86
            content = b""
            while quality >= 35:
                output = BytesIO()
                converted.save(output, format="WEBP", quality=quality, method=4)
                content = output.getvalue()
                if len(content) <= budget:
                    break
                quality -= 10
            while len(content) > budget and max(converted.size) > 480:
                converted.thumbnail(
                    (max(480, int(converted.width * 0.8)), max(480, int(converted.height * 0.8))),
                    Image.Resampling.LANCZOS,
                )
                output = BytesIO()
                converted.save(output, format="WEBP", quality=45, method=4)
                content = output.getvalue()
            notice = "已生成压缩预览"
            if is_large_gif:
                notice = "大型 GIF 已生成首帧静态预览"
            fd, temporary_name = tempfile.mkstemp(prefix=".image.", suffix=".webp", dir=self.cache_dir)
            os.close(fd)
            temporary_path = Path(temporary_name)
            try:
                temporary_path.write_bytes(content)
                os.replace(temporary_path, cache_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            self._prune()
            return Preview("image", _data_url("image/webp", content), len(content), notice)

    def _video(self, entry: FileEntry, budget: int) -> Preview:
        compatible = entry.extension in {".mp4", ".webm", ".ogg", ".m4v"}
        if compatible and entry.size <= budget:
            content = entry.path.read_bytes()
            mime = mimetypes.guess_type(entry.name)[0] or "video/mp4"
            return Preview("video", _data_url(mime, content), len(content))
        ok, error = self.check_video_tools()
        if not ok:
            return Preview("video", "", 0, error=error)

        output_path = self._cache_path(entry, "video", budget, ".mp4")
        if not output_path.exists() or output_path.stat().st_size > int(budget * 1.05):
            duration_result = subprocess.run(
                [
                    shutil.which("ffprobe") or "ffprobe",
                    "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(entry.path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration = max(float(duration_result.stdout.strip()), 0.1)
            target_bits = max(160_000, int((budget * 8 * 0.90) / duration) - 96_000)
            temp_path = output_path.with_suffix(f".{os.getpid()}.working.mp4")
            for scale, ratio in ((720, 1.0), (480, 0.72)):
                temp_path.unlink(missing_ok=True)
                video_bitrate = max(120_000, int(target_bits * ratio))
                encoder = _h264_encoder()
                encoder_options = ["-c:v", encoder]
                if encoder == "libx264":
                    encoder_options += ["-preset", "veryfast"]
                subprocess.run(
                    [_ffmpeg_exe(), "-y", "-v", "error", "-i", str(entry.path),
                        "-vf", f"scale=-2:'min({scale},ih)'", *encoder_options,
                        "-b:v", str(video_bitrate), "-maxrate", str(video_bitrate),
                        "-bufsize", str(video_bitrate * 2), "-c:a", "aac", "-b:a", "96k",
                        "-movflags", "+faststart", str(temp_path)],
                    check=True,
                    capture_output=True,
                    timeout=max(120, int(duration * 4)),
                )
                if temp_path.stat().st_size <= int(budget * 1.05):
                    os.replace(temp_path, output_path)
                    break
            else:
                temp_path.unlink(missing_ok=True)
                raise RuntimeError("视频压缩两次后仍超过预览上限")
            self._prune()
        os.utime(output_path, None)
        content = output_path.read_bytes()
        return Preview("video", _data_url("video/mp4", content), len(content), "已生成压缩视频预览")

    @staticmethod
    def _text(entry: FileEntry, budget: int) -> Preview:
        with entry.path.open("rb") as stream:
            content = stream.read(budget + 1)
        truncated = len(content) > budget or entry.size > budget
        content = content[:budget]
        decoded = None
        for encoding in ("utf-8-sig", "gb18030"):
            candidates = range(0, 5) if truncated else range(0, 1)
            for trim in candidates:
                try:
                    candidate = content if trim == 0 else content[:-trim]
                    decoded = candidate.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if decoded is not None:
                break
        if decoded is None:
            return Preview("text", "", len(content), error="文本无法使用 UTF-8 或 GB18030 解码")
        notice = f"预览已截断（原文件 {entry.size / 1024 / 1024:.2f} MB）" if truncated else ""
        return Preview("text", decoded, len(content), notice)

    def prepare_page(
        self,
        entries: tuple[FileEntry, ...],
        mode: str,
        per_sample_limit_mb: float,
        page_limit_mb: float,
    ) -> list[Preview]:
        if not entries:
            return []
        per_sample = int(per_sample_limit_mb * 1024 * 1024)
        page_share = int(page_limit_mb * 1024 * 1024 / len(entries))
        budget = max(64 * 1024, min(per_sample, page_share))
        return [self.prepare(entry, mode, budget) for entry in entries]


@lru_cache(maxsize=1)
def _h264_encoder() -> str:
    ffmpeg = _ffmpeg_exe()
    if not ffmpeg:
        return ""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, check=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = result.stdout + result.stderr
    for encoder in ("libx264", "libopenh264"):
        if encoder not in output:
            continue
        try:
            subprocess.run(
                [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=s=16x16:d=0.1",
                 "-frames:v", "1", "-c:v", encoder, "-f", "null", "-"],
                capture_output=True, check=True, timeout=20,
            )
            return encoder
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


@lru_cache(maxsize=1)
def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except (ImportError, RuntimeError):
        pass
    return shutil.which("ffmpeg") or ""
