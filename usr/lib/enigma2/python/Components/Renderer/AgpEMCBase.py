#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
## __author__ = "Lululla"         ##
## __copyright__ = "AGP Team"     ##
## __created_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function
import re
from os import makedirs
from os.path import basename, exists, join

EMC_ROOT = "/media/hdd/AGPEMC"
EMC_POSTER_FOLDER = join(EMC_ROOT, "poster")
EMC_BACKDROP_FOLDER = join(EMC_ROOT, "backdrop")
EMC_LOGO_FOLDER = join(EMC_ROOT, "logo")
EMC_INFO_FOLDER = join(EMC_ROOT, "info")
EMC_CAST_FOLDER = join(EMC_ROOT, "cast")

VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".avi", ".ts", ".mov", ".iso", ".m2ts",
    ".m4v", ".mpeg", ".mpg", ".wmv"
)


def ensure_emc_dirs(root_path=EMC_ROOT):
    root = str(root_path or EMC_ROOT).rstrip("/")
    paths = {
        "root": root,
        "poster": join(root, "poster"),
        "backdrop": join(root, "backdrop"),
        "logo": join(root, "logo"),
        "info": join(root, "info"),
        "cast": join(root, "cast"),
    }
    for path in paths.values():
        if not exists(path):
            makedirs(path, exist_ok=True)
    return paths


def is_video_file(path):
    try:
        lower = str(path or "").lower()
        return any(lower.endswith(ext) for ext in VIDEO_EXTENSIONS)
    except Exception:
        return False


def extract_emc_year(value):
    try:
        text = safe_str(value) if 'safe_str' in globals() else str(value or "")
        # Normal case, also works when the year touches
        # underscores/dots/hyphens.
        m = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text)
        if m:
            return m.group(1)
        # Recovery for common typo seen in filenames: 198h3 -> 1983.
        m = re.search(r"(?<!\d)(19\d)h(\d)(?!\d)", text, flags=re.IGNORECASE)
        if m:
            return "{}{}".format(m.group(1), m.group(2))
        return ""
    except Exception:
        return ""


def is_emc_episode(value):
    try:
        text = str(value or "")
        if re.search(
            r"\bS\s*\d{1,2}[\s._-]*E\s*\d{1,3}\b",
            text,
                flags=re.IGNORECASE):
            return True
        if re.search(r"\b\d{1,2}x\d{1,3}\b", text, flags=re.IGNORECASE):
            return True
        if re.search(r"\bseason[\s._-]*\d+\b", text, flags=re.IGNORECASE):
            return True
        if re.search(r"\bepisode[\s._-]*\d+\b", text, flags=re.IGNORECASE):
            return True
        return False
    except Exception:
        return False


def extract_emc_episode_marker(value):
    """
    Extract a real season/episode marker from an EMC filename/path.

    Returns:
        ("S02E07", "season 2 episode 7") when found.
        ("", "") when no reliable episode marker exists.

    This is used only as a TV hint for TMDB checkType(), not as the search title.
    """
    try:
        text = str(value or "")

        # S02E07 / s2e7 / S02.E07 / S02-E07 / S02_E07
        m = re.search(
            r"\bS\s*(\d{1,2})[\s._-]*E\s*(\d{1,3})\b",
            text,
            flags=re.IGNORECASE)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            return "S%02dE%02d" % (
                season, episode), "season %d episode %d" % (season, episode)

        # 2x07 / 02x007
        m = re.search(r"\b(\d{1,2})x(\d{1,3})\b", text, flags=re.IGNORECASE)
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            return "S%02dE%02d" % (
                season, episode), "season %d episode %d" % (season, episode)

        # Season 2 Episode 7 / Season.2.Episode.7
        m = re.search(
            r"\bseason[\s._-]*(\d{1,2}).*?\bepisode[\s._-]*(\d{1,3})\b",
            text,
            flags=re.IGNORECASE
        )
        if m:
            season = int(m.group(1))
            episode = int(m.group(2))
            return "S%02dE%02d" % (
                season, episode), "season %d episode %d" % (season, episode)

        # Fallback for names that are clearly episodes but do not expose numbers
        # in a supported format. This should be rare, but still forces TV mode.
        if is_emc_episode(text):
            return "S01E01", "season 1 episode 1"

        return "", ""
    except Exception:
        return "", ""


def safe_str(value):
    try:
        return str(value or "")
    except Exception:
        return ""


def clean_movie_filename(name):
    """
    Clean movie filename and keep only the real movie title + optional year.

    This is intentionally conservative for EMC/TMDB searches:
    - Episodes search by series name only.
    - Movie filenames with a year keep only text before the first year + that year.
    - Release tags/groups/codecs are removed for filenames without a usable year.
    """
    try:
        original = safe_str(name).strip()

        if not re.search(
            r"\.(mp4|mkv|avi|ts|mov|iso|m2ts|m4v|mpeg|mpg|wmv)$",
            original,
                flags=re.IGNORECASE):
            return ""

        name = re.sub(
            r"\.(mp4|mkv|avi|ts|mov|iso|m2ts|m4v|mpeg|mpg|wmv)$",
            "",
            original,
            flags=re.IGNORECASE)

        # Drop leading scene group prefixes, e.g. cocain-petes.dragon ->
        # petes.dragon
        name = re.sub(
            r"^(COCAIN|GECKOS|DRONES|SPARKS|DiAMOND|FGT|ION10|RARBG|YIFY|YTS|ETRG|XVID|MkvCage|ShAaNiG|RUSTED|WAR|GETiT|playSD)-",
            "",
            name,
            flags=re.IGNORECASE
        )

        # Episodes should search by the series name only, not by episode title
        # or release tags.
        if re.search(r"\bS\d{1,2}E\d{1,3}\b", name, flags=re.IGNORECASE):
            name = re.sub(
                r"\bS\d{1,2}E\d{1,3}\b.*$",
                "",
                name,
                flags=re.IGNORECASE)

        # Convert bracketed years to plain years before removing other
        # brackets.
        name = re.sub(r"[\[\(]\s*((?:19|20)\d{2})\s*[\]\)]", r" \1 ", name)

        # Normalize separators. Dot restoration for title decimals happens
        # later.
        name = name.replace("_", " ").replace(".", " ")

        # Remove remaining bracketed release-group/noise text.
        name = re.sub(r"\[[^\]]+\]", " ", name)
        name = re.sub(r"\([^\)]*\)", " ", name)
        name = re.sub(r"\{[^\}]+\}", " ", name)
        name = re.sub(r"\s{2,}", " ", name).strip()

        # Recover/remove common malformed years like Scarface.198h3 -> Scarface
        # 1983.
        name = re.sub(
            r"(?<!\d)(19\d)h(\d)(?!\d)",
            lambda m: "{}{}".format(
                m.group(1),
                m.group(2)),
            name,
            flags=re.IGNORECASE)

        # If a year exists, discard everything after the first year. This removes almost
        # all codecs, sizes, release groups, language tags, and audio tokens in
        # one step.
        year_match = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", name)
        if year_match:
            title_part = name[:year_match.start()].strip(" -._")
            # Remove edition/language/release tags that sometimes appear before
            # the year.
            title_part = re.sub(
                r"\b(EXTENDED|REMASTERED|UNRATED|PROPER|REPACK|INTERNAL|LIMITED|FINAL|THEATRICAL|DIRECTORS? CUT|RUSSIAN|Hindi|Arabic Subbed|RoSubbed|Subbed)\b",
                " ",
                title_part,
                flags=re.IGNORECASE)
            title_part = re.sub(
                r"\bDisc\s*\d+\b",
                " ",
                title_part,
                flags=re.IGNORECASE)
            title_part = re.sub(
                r"(?<!\d)(19\d)h(\d)(?!\d)",
                " ",
                title_part,
                flags=re.IGNORECASE)
            title_part = re.sub(r"\s{2,}", " ", title_part).strip(" -._")
            year_part = year_match.group(1)
            name = "{} {}".format(title_part, year_part).strip()
        else:
            # No year: remove common release noise without damaging valid movie
            # titles.
            split_audio_patterns = [
                r"\bAAC\s*[257]\s*[01]\b",
                r"\bDDP\s*[257]\s*[01]\b",
                r"\bDD\s*[257]\s*[01]\b",
                r"\bAC3\s*[257]\s*[01]\b",
                r"\bDTS\s*[257]\s*[01]\b",
                r"\bEAC3\s*[257]\s*[01]\b",
                r"\bTRUEHD\s*[257]\s*[01]\b",
            ]
            for pattern in split_audio_patterns:
                name = re.sub(pattern, " ", name, flags=re.IGNORECASE)

            garbage_patterns = [
                r"\b(480p|576p|720p|1080p|2160p|4K)\b",
                r"\b(WEBRip|WEB[\- ]DL|WEB|BluRay|BRRip|BRRiP|BDRip|DVDRip|DvDrip|HDRip|HDTV|CAM|TS|TC|SCR|AMZN)\b",
                r"\b(Line|LiNE)\b",
                r"\b(x264|x265|h264|h265|H264|H265|HEVC|AVC|XViD|XviD|XVID)\b",
                r"\b(8bit|10bit|10bits|12bit)\b",
                r"\b(HDR|HDR10|DV|Dolby Vision)\b",
                r"\b(AAC|AC3|EAC3|DD|DDP|DTS|TRUEHD|Atmos|MP3)\b",
                r"\b(2CH|6CH|7CH|8CH|Dual Audio)\b",
                r"\b(REPACK|PROPER|INTERNAL|EXTENDED|REMASTERED|UNRATED|REMUX|LIMITED)\b",
                r"\b(Arabic Subbed|RoSubbed|Subbed|Hindi|RUSSIAN|Eng)\b",
                r"\b(\d+(?:\.\d+)?\s*(?:GB|MB))\b",
                r"\b(YTS|YTS AM|YTS AG|YTS LT|YTS MX|YTS BZ|PSA|Rapta|Rapita|GalaxyRG|NeoNoir|RARBG|BONE|Yify|MkvCage|Mkvking|ShAaNiG|GECKOS|DRONES|COCAIN|SPARKS|DiAMOND|FGT|ION10|WAR|RUSTED|ETRG|BOKUTOX|LOKI|aXXo|iExTV|playSD|getit|FiLMEY|akoam|net|Com|ws|WS|AM)\b",
                r"\b(mp4|mkv|avi)\b",
            ]
            for pattern in garbage_patterns:
                name = re.sub(pattern, " ", name, flags=re.IGNORECASE)

        name = re.sub(r"\bakoam\s+net\b", " ", name, flags=re.IGNORECASE)
        name = re.sub(r"\bSpiderMan\b", "Spider Man", name)

        # General cleanup after either path.
        name = re.sub(r"\b(480p|576p|720p|1080p|2160p|4K)\b",
                      " ", name, flags=re.IGNORECASE)
        name = re.sub(
            r"\b(WEBRip|WEB[\- ]DL|WEB|BluRay|BRRip|BRRiP|BDRip|DVDRip|DvDrip|HDRip|HDTV|AMZN)\b",
            " ",
            name,
            flags=re.IGNORECASE)
        name = re.sub(
            r"\b(x264|x265|h264|h265|H264|H265|HEVC|AVC|XViD|XviD|XVID|MP3|AAC|AC3|DD|DDP|DTS)\b",
            " ",
            name,
            flags=re.IGNORECASE)
        name = re.sub(r"\b(\d+(?:\.\d+)?\s*(?:GB|MB))\b",
                      " ", name, flags=re.IGNORECASE)
        name = re.sub(
            r"\b(YTS|PSA|Rapta|Rapita|GalaxyRG|NeoNoir|RARBG|BONE|Yify|MkvCage|Mkvking|ShAaNiG|GECKOS|DRONES|COCAIN|SPARKS|DiAMOND|FGT|ION10|RUSTED|ETRG|BOKUTOX|LOKI|aXXo|iExTV|playSD|getit|FiLMEY|akoam|Com|ws|WS|AM|AG|LT|MX|BZ|rmteam)\b",
            " ",
            name,
            flags=re.IGNORECASE)
        name = re.sub(r"\s+-\s+", " ", name)
        name = name.replace("-", " ")
        name = re.sub(r"\s{2,}", " ", name).strip()

        # Keep real title decimals like M3GAN 2 0 -> M3GAN 2.0 only when there is
        # no larger integer immediately before it; avoids turning '1 25GB' into
        # '.1'.
        name = re.sub(
            r"(?<!\d\s)\b(\d+)\s+(\d)\b",
            lambda m: "{}.{}".format(m.group(1), m.group(2)),
            name
        )

        years = re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", name)
        keep_year = years[0] if years else ""

        if keep_year:
            body = re.sub(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", " ", name)
            body = re.sub(r"\s{2,}", " ", body).strip(" -._")
            name = "{} {}".format(body, keep_year).strip()
        else:
            name = re.sub(r"\s{2,}", " ", name).strip(" -._")

        # Return empty for pure junk/sample files such as RARBG.COM.avi.
        junk_only = set(["rarbg", "com", "www", "sample",
                        "trailer", "yts", "psa", "mkv", "mp4", "avi"])
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", name)]
        if words and all(w in junk_only for w in words):
            return ""

        return name

    except Exception:
        return ""


def build_emc_search_title(movie_path, keep_year=False):
    raw = basename(safe_str(movie_path))
    cleaned = clean_movie_filename(raw)
    if not cleaned:
        return ""

    if keep_year:
        return cleaned

    cleaned = re.sub(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)$", "", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned
