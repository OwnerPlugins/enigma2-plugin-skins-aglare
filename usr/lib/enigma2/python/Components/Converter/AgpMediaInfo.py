#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
## __created_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function

import json
import os
import subprocess
import time
from datetime import datetime

from Components.Converter.Converter import Converter
from Components.Element import cached
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
from Components.Sources.EventInfo import EventInfo
import NavigationInstance

from Components.Renderer.AgpEMCBase import clean_movie_filename

CACHE_TTL = 15
LOG_DIR = "/tmp/agplog"
LOG_FILE = "/tmp/agplog/AgpMediaInfo.log"


class AgpMediaInfo(Converter, object):
    def __init__(self, type):
        Converter.__init__(self, type)
        self.type = "summary"
        self.separator = " • "
        self._parse_options(type)
        self._log(
            "INIT",
            "AgpMediaInfo initialized | type='{}' | sep='{}'".format(
                self.type,
                self.separator))

    def changed(self, what):
        Converter.changed(self, what)

    def _log(self, level, message):
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            with open(LOG_FILE, "a") as f:
                f.write("{} {}: {}\n".format(datetime.now(), level, message))
        except Exception:
            pass

    def _parse_options(self, options):
        if not options:
            return

        parts = [x.strip() for x in str(options).split(",") if x.strip()]
        if not parts:
            return

        first = parts[0]
        if "=" not in first:
            self.type = first.strip().lower()

        parse_parts = parts[1:] if "=" not in first else parts

        for item in parse_parts:
            if "=" not in item:
                continue

            key, value = [x.strip() for x in item.split("=", 1)]
            key = key.lower()
            value_low = value.lower()

            if key == "sep":
                self.separator = {
                    "pipe": " | ",
                    "pip": " | ",
                    "dot": " • ",
                    "middot": " · ",
                    "bigdot": " ● ",
                    "bullet": " ● ",
                    "dash": " - ",
                    "slash": " / ",
                    "comma": ", ",
                    "space": " ",
                }.get(value_low, self.separator)

    def _safe_get_path_from_ref(self, ref):
        try:
            if ref is None:
                return ""
            if hasattr(ref, "getPath"):
                return str(ref.getPath() or "")
            return ""
        except Exception:
            return ""

    def _resolve_path(self):
        try:
            source = self.source
            class_name = getattr(
                getattr(
                    source,
                    "__class__",
                    None),
                "__name__",
                "unknown")
            self._log("INFO", "source class='{}'".format(class_name))

            if class_name == "EMCServiceEvent":
                srv = getattr(source, "service", None)
                path = self._safe_get_path_from_ref(srv)
                self._log("INFO", "EMCServiceEvent path='{}'".format(path))
                if path:
                    return path

            if class_name == "EMCCurrentService":
                try:
                    playable = source.getCurrentService()
                    self._log(
                        "INFO",
                        "EMCCurrentService returned playable='{}'".format(
                            bool(playable)))
                except Exception as e:
                    playable = None
                    self._log(
                        "ERROR",
                        "EMCCurrentService getCurrentService failed: {}".format(
                            str(e)))

                try:
                    ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                    path = self._safe_get_path_from_ref(ref)
                    self._log(
                        "INFO", "EMCCurrentService fallback ref path='{}'".format(path))
                    if path:
                        return path
                except Exception as e:
                    self._log(
                        "ERROR",
                        "EMCCurrentService fallback ref failed: {}".format(
                            str(e)))

            if isinstance(source, ServiceEvent):
                try:
                    ref = source.getCurrentService()
                    path = self._safe_get_path_from_ref(ref)
                    self._log("INFO", "ServiceEvent path='{}'".format(path))
                    if path:
                        return path
                except Exception as e:
                    self._log(
                        "ERROR",
                        "ServiceEvent path resolve failed: {}".format(
                            str(e)))

            if isinstance(source, CurrentService):
                try:
                    ref = source.getCurrentServiceRef()
                    path = self._safe_get_path_from_ref(ref)
                    self._log("INFO", "CurrentService path='{}'".format(path))
                    if path:
                        return path
                except Exception as e:
                    self._log(
                        "ERROR",
                        "CurrentService path resolve failed: {}".format(
                            str(e)))

            if isinstance(source, EventInfo):
                try:
                    ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                    path = self._safe_get_path_from_ref(ref)
                    self._log("INFO", "EventInfo path='{}'".format(path))
                    if path:
                        return path
                except Exception as e:
                    self._log(
                        "ERROR",
                        "EventInfo path resolve failed: {}".format(
                            str(e)))

            try:
                if hasattr(source, "service"):
                    ref = getattr(source, "service", None)
                    path = self._safe_get_path_from_ref(ref)
                    self._log(
                        "INFO", "generic source.service path='{}'".format(path))
                    if path:
                        return path
            except Exception as e:
                self._log(
                    "ERROR",
                    "generic source.service resolve failed: {}".format(
                        str(e)))

            try:
                if hasattr(source, "getCurrentServiceRef"):
                    ref = source.getCurrentServiceRef()
                    path = self._safe_get_path_from_ref(ref)
                    self._log(
                        "INFO", "generic getCurrentServiceRef path='{}'".format(path))
                    if path:
                        return path
            except Exception as e:
                self._log(
                    "ERROR",
                    "generic getCurrentServiceRef resolve failed: {}".format(
                        str(e)))

            try:
                ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                path = self._safe_get_path_from_ref(ref)
                self._log("INFO", "final fallback path='{}'".format(path))
                if path:
                    return path
            except Exception as e:
                self._log(
                    "ERROR",
                    "final fallback resolve failed: {}".format(
                        str(e)))

            self._log("INFO", "resolved path=''")
            return ""

        except Exception as e:
            self._log("ERROR", "_resolve_path failed: {}".format(str(e)))
            return ""

    def _which(self, name):
        for base in ("/usr/bin", "/usr/local/bin", "/bin"):
            candidate = os.path.join(base, name)
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                self._log(
                    "INFO", "found binary {}='{}'".format(
                        name, candidate))
                return candidate
        self._log("INFO", "binary not found '{}'".format(name))
        return None

    def _run(self, cmd):
        try:
            self._log("INFO", "run command='{}'".format(" ".join(cmd)))
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = proc.communicate()

            if not isinstance(out, str):
                out = out.decode("utf-8", "ignore")
            if not isinstance(err, str):
                err = err.decode("utf-8", "ignore")

            self._log("INFO", "command rc={} stderr='{}'".format(
                proc.returncode, err[:300]))
            if proc.returncode != 0:
                return ""
            return out
        except Exception as e:
            self._log("ERROR", "_run failed: {}".format(str(e)))
            return ""

    def _fmt_duration(self, seconds):
        try:
            seconds = float(seconds)
            if seconds <= 0:
                return ""
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            if h > 0:
                return "%d:%02d:%02d" % (h, m, s)
            return "%d:%02d" % (m, s)
        except Exception:
            return ""

    def _fmt_bitrate(self, value):
        try:
            if value in (None, "", 0, "0"):
                return ""
            v = float(value)
            if v >= 1000000:
                return "%.2f Mb/s" % (v / 1000000.0)
            if v >= 1000:
                return "%.0f kb/s" % (v / 1000.0)
            return "%.0f b/s" % v
        except Exception:
            return ""

    def _fmt_size(self, value):
        try:
            if value in (None, "", 0, "0"):
                return ""
            v = float(value)
            units = ["B", "KB", "MB", "GB", "TB"]
            idx = 0
            while v >= 1024.0 and idx < len(units) - 1:
                v /= 1024.0
                idx += 1
            if idx == 0:
                return "%d %s" % (int(v), units[idx])
            return "%.2f %s" % (v, units[idx])
        except Exception:
            return ""

    def _fmt_bitdepth(self, value):
        try:
            text = str(value or "").strip()
            if not text:
                return ""
            if text.endswith("-bit"):
                return text
            return "{}-bit".format(text)
        except Exception:
            return ""

    def _parse_fraction(self, value):
        try:
            text = str(value or "").strip()
            if "/" in text:
                a, b = text.split("/", 1)
                a = float(a)
                b = float(b)
                if b:
                    return a / b
                return 0.0
            return float(text)
        except Exception:
            return 0.0

    def _normalize_codec(self, codec_name, codec_long_name):
        text = " ".join([str(codec_name or ""),
                         str(codec_long_name or "")]).strip()
        if not text:
            return ""
        lower = text.lower()

        mapping = [
            ("hevc", "HEVC"),
            ("h265", "HEVC"),
            ("x265", "HEVC"),
            ("avc", "AVC"),
            ("h264", "AVC"),
            ("x264", "AVC"),
            ("mpeg2video", "MPEG-2"),
            ("mpeg4", "MPEG-4"),
            ("vc1", "VC-1"),
            ("vp9", "VP9"),
            ("av1", "AV1"),
            ("truehd", "TrueHD"),
            ("eac3", "E-AC3"),
            ("ac3", "AC3"),
            ("dts", "DTS"),
            ("aac", "AAC"),
            ("flac", "FLAC"),
            ("mp3", "MP3"),
        ]
        for needle, value in mapping:
            if needle in lower:
                return value
        return text

    def _detect_hdr(self, video):
        blob = " ".join([
            str(video.get("codec_name", "")),
            str(video.get("codec_long_name", "")),
            str(video.get("profile", "")),
            str(video.get("color_transfer", "")),
            str(video.get("color_space", "")),
            str(video.get("color_primaries", "")),
            str(video.get("pix_fmt", "")),
            str(video.get("master_display", "")),
            str(video.get("content_light_level", "")),
            str(video.get("hdr_format", "")),
        ]).lower()

        if "dolby vision" in blob or "dovi" in blob:
            return "Dolby Vision"
        if "smpte2084" in blob or "pq" in blob:
            return "HDR10"
        if "arib-std-b67" in blob or "hlg" in blob:
            return "HLG"
        if "hdr" in blob:
            return "HDR"
        return ""

    def _detect_dolby(self, audio):
        blob = " ".join([
            str(audio.get("codec_name", "")),
            str(audio.get("codec_long_name", "")),
            str(audio.get("profile", "")),
            str(audio.get("format_commercial", "")),
            str(audio.get("title", "")),
        ]).lower()

        if "atmos" in blob:
            return "Dolby Atmos"
        if "truehd" in blob:
            return "Dolby TrueHD"
        if "e-ac-3" in blob or "eac3" in blob or "dd+" in blob:
            return "Dolby Digital Plus"
        if "ac-3" in blob or "ac3" in blob or "dolby digital" in blob:
            return "Dolby Digital"
        return ""

    def _extract_streams(self, data):
        streams = data.get("streams", []) or []
        video = None
        audio = None
        subtitles = []

        for stream in streams:
            codec_type = str(stream.get("codec_type", "")).lower()
            if codec_type == "video" and video is None:
                video = stream
            elif codec_type == "audio" and audio is None:
                audio = stream
            elif codec_type == "subtitle":
                subtitles.append(stream)

        return video or {}, audio or {}, subtitles

    _cache = {}

    def _ffprobe_info(self, path):
        ffprobe = self._which("ffprobe")
        if not ffprobe or not path:
            self._log(
                "INFO",
                "_ffprobe_info skipped | ffprobe='{}' path='{}'".format(
                    bool(ffprobe),
                    path))
            return {}

        cmd = [
            ffprobe, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path
        ]
        output = self._run(cmd)
        if not output:
            self._log("INFO", "_ffprobe_info no output")
            return {}

        try:
            raw = json.loads(output)
        except Exception as e:
            self._log(
                "ERROR",
                "_ffprobe_info json parse failed: {}".format(
                    str(e)))
            return {}

        fmt = raw.get("format", {}) or {}
        video, audio, subtitles = self._extract_streams(raw)

        result = {
            "path": path,
            "file_name": os.path.basename(path),
            "container": fmt.get("format_long_name") or fmt.get("format_name") or "",
            "duration": self._fmt_duration(fmt.get("duration")),
            "size": self._fmt_size(fmt.get("size")),
            "overall_bitrate": self._fmt_bitrate(fmt.get("bit_rate")),
            "bitrate": self._fmt_bitrate(fmt.get("bit_rate")),
            "video_codec": self._normalize_codec(video.get("codec_name"), video.get("codec_long_name")),
            "video_profile": str(video.get("profile", "")).strip(),
            "video_bitrate": self._fmt_bitrate(video.get("bit_rate") or fmt.get("bit_rate")),
            "width": str(video.get("width", "") or ""),
            "height": str(video.get("height", "") or ""),
            "resolution": "",
            "frame_rate": "",
            "aspect": str(video.get("display_aspect_ratio", "") or ""),
            "bit_depth": str(video.get("bits_per_raw_sample", "") or ""),
            "color_space": str(video.get("color_space", "") or ""),
            "color_primaries": str(video.get("color_primaries", "") or ""),
            "color_transfer": str(video.get("color_transfer", "") or ""),
            "hdr": "",
            "video_scan_type": str(video.get("field_order", "") or ""),
            "audio_codec": self._normalize_codec(audio.get("codec_name"), audio.get("codec_long_name")),
            "audio_profile": str(audio.get("profile", "") or ""),
            "audio_bitrate": self._fmt_bitrate(audio.get("bit_rate")),
            "audio_channels": str(audio.get("channels", "") or ""),
            "audio_sample_rate": "",
            "audio_language": "",
            "dolby": "",
            "subtitle_count": str(len(subtitles)),
            "has_subtitles": "1" if len(subtitles) > 0 else "",
            "has_hdr": "",
            "has_dolby": "",
            "raw_json": output,
        }

        if result["width"] and result["height"]:
            result["resolution"] = "%sx%s" % (
                result["width"], result["height"])

        fps = self._parse_fraction(
            video.get("avg_frame_rate") or video.get("r_frame_rate"))
        if fps > 0:
            result["frame_rate"] = "%.3f fps" % fps

        try:
            sample_rate = int(str(audio.get("sample_rate", "") or "0"))
            if sample_rate > 0:
                result["audio_sample_rate"] = "%.1f kHz" % (
                    sample_rate / 1000.0)
        except Exception:
            pass

        tags = audio.get("tags", {}) or {}
        lang = tags.get("language") or tags.get("LANGUAGE") or ""
        if lang:
            result["audio_language"] = str(lang)

        hdr = self._detect_hdr(video)
        dolby = self._detect_dolby(audio)
        result["hdr"] = hdr
        result["dolby"] = dolby
        result["has_hdr"] = "1" if hdr else ""
        result["has_dolby"] = "1" if dolby else ""

        self._log(
            "INFO",
            "_ffprobe_info extracted | resolution='{}' video='{}' vbitrate='{}' fps='{}' bitdepth='{}' hdr='{}' audio='{}' abitrate='{}' dolby='{}'".format(
                result["resolution"],
                result["video_codec"],
                result["video_bitrate"],
                result["frame_rate"],
                result["bit_depth"],
                result["hdr"],
                result["audio_codec"],
                result["audio_bitrate"],
                result["dolby"]))
        return result

    def _analyze(self, path):
        if not path:
            self._log("INFO", "_analyze skipped: empty path")
            return {}

        now = time.time()
        cached_entry = self._cache.get(path)
        if cached_entry and now - cached_entry[0] < CACHE_TTL:
            self._log("INFO", "_analyze cache hit path='{}'".format(path))
            return cached_entry[1]

        info = self._ffprobe_info(path)

        if not info:
            info = {
                "path": path,
                "file_name": os.path.basename(path),
                "container": os.path.splitext(path)[1].lstrip(".").upper(),
            }

        self._cache[path] = (now, info)
        self._log("INFO", "_analyze cache store path='{}'".format(path))
        return info

    def _clean_media_name(self, path):
        try:
            cleaned = clean_movie_filename(os.path.basename(str(path or "")))
            if not cleaned:
                return ""

            parts = cleaned.rsplit(" ", 1)
            if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
                return "{} ({})".format(parts[0], parts[1])

            return cleaned
        except Exception as e:
            self._log("ERROR", "_clean_media_name failed: {}".format(str(e)))
            return ""

    def _summary(self, info):
        parts = []

        if info.get("video_codec"):
            if info.get("video_bitrate"):
                parts.append(
                    "{} {}".format(
                        info.get("video_codec"),
                        info.get("video_bitrate")))
            else:
                parts.append(info.get("video_codec"))

        if info.get("resolution"):
            parts.append(info.get("resolution"))

        if info.get("frame_rate"):
            parts.append(info.get("frame_rate"))

        bit_depth = self._fmt_bitdepth(info.get("bit_depth"))
        if bit_depth:
            parts.append(bit_depth)

        if info.get("hdr"):
            parts.append(info.get("hdr"))

        if info.get("audio_codec"):
            if info.get("audio_bitrate"):
                parts.append(
                    "{} {}".format(
                        info.get("audio_codec"),
                        info.get("audio_bitrate")))
            else:
                parts.append(info.get("audio_codec"))

        if info.get("dolby"):
            parts.append(info.get("dolby"))

        if info.get("audio_channels"):
            parts.append("{}ch".format(info.get("audio_channels")))

        return self.separator.join([str(x).strip()
                                   for x in parts if str(x).strip()])

    def _get_value(self):
        path = self._resolve_path()
        info = self._analyze(path)

        mapping = {
            "all": self._summary(info),
            "summary": self._summary(info),
            "android": self._summary(info),
            "medianame": self._clean_media_name(path),
            "mediatitle": self._clean_media_name(path),
            "filename": info.get("file_name", ""),
            "path": info.get("path", ""),
            "container": info.get("container", ""),
            "duration": info.get("duration", ""),
            "size": info.get("size", ""),
            "overallbitrate": info.get("overall_bitrate", ""),
            "bitrate": info.get("bitrate", ""),
            "videocodec": info.get("video_codec", ""),
            "videoprofile": info.get("video_profile", ""),
            "videobitrate": info.get("video_bitrate", ""),
            "resolution": info.get("resolution", ""),
            "framerate": info.get("frame_rate", ""),
            "aspect": info.get("aspect", ""),
            "bitdepth": self._fmt_bitdepth(info.get("bit_depth", "")),
            "colorspace": info.get("color_space", ""),
            "colorprimaries": info.get("color_primaries", ""),
            "colortransfer": info.get("color_transfer", ""),
            "hdr": info.get("hdr", ""),
            "videoscantype": info.get("video_scan_type", ""),
            "audiocodec": info.get("audio_codec", ""),
            "audioprofile": info.get("audio_profile", ""),
            "audiobitrate": info.get("audio_bitrate", ""),
            "audiochannels": info.get("audio_channels", ""),
            "audiosamplerate": info.get("audio_sample_rate", ""),
            "audiolanguage": info.get("audio_language", ""),
            "dolby": info.get("dolby", ""),
            "subtitlecount": info.get("subtitle_count", ""),
            "hassubtitles": info.get("has_subtitles", ""),
            "hashdr": info.get("has_hdr", ""),
            "hasdolby": info.get("has_dolby", ""),
            "rawjson": info.get("raw_json", ""),
        }

        value = str(mapping.get(self.type, self._summary(info)) or "")
        self._log(
            "INFO",
            "_get_value type='{}' value='{}'".format(
                self.type,
                value))
        return value

    @cached
    def getText(self):
        return self._get_value()

    text = property(getText)

    @cached
    def getBoolean(self):
        return self._get_value() not in ("", "0", "False", "false", "None", None)

    boolean = property(getBoolean)
