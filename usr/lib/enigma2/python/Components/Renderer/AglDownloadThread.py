#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__author__ = "Lululla"         ##
# #__copyright__ = "AGP Team"     ##
# #__created_by__ = "MNASR"       ##
# ##################################
from __future__ import absolute_import, print_function
from os import remove, makedirs
from os.path import exists, getsize, dirname
from re import compile, findall, sub, IGNORECASE
from threading import Thread
from random import choice
from time import sleep
import threading
import urllib3
import logging

from requests import get, codes, Session
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import HTTPError
from functools import lru_cache

from Components.config import config
from .Agp_apikeys import tmdb_api
from .Agp_Utils import logger
from .Agp_lib import split_title_and_year, quoteEventName

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

try:
    lng = config.osd.language.value[:-3]
except BaseException:
    lng = 'en'

AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_4_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0",
]
headers = {"User-Agent": choice(AGENTS)}

global srch


class AglDownloadThread(Thread):
    def __init__(self, *args, **kwargs):
        Thread.__init__(self)
        self._stop_event = threading.Event()
        self.search_year = ""
        if config.plugins.Aglare.cache.value:
            self.search_tmdb_logo = lru_cache(maxsize=250)(self.search_tmdb_logo)

    def _normalize_match_title(self, value):
        value = str(value or "").lower().strip()
        value = value.replace("&", " and ")
        value = sub(r"[^a-z0-9\u0600-\u06FF]+", " ", value)
        value = sub(r"\s+", " ", value).strip()
        return value

    def _contains_arabic(self, value):
        try:
            return bool(compile(r'[\u0600-\u06FF]').search(str(value or "")))
        except Exception:
            return False

    def _get_tmdb_search_language(self, title):
        try:
            if self._contains_arabic(title):
                return "ar"
            return lng if lng else "en"
        except Exception:
            return "en"

    def _build_logo_language_list(self, title, srch=None):
        langs = []

        if self._contains_arabic(title):
            langs.extend(["ar", "null"])
        else:
            langs.extend([lng, "en", "null", "ar"])

        result = []
        for lang in langs:
            lang = str(lang or "").strip()
            if not lang:
                continue
            if lang not in result:
                result.append(lang)

        return result

    def _select_best_tmdb_result(self, results, title_safe, shortdesc="", fulldesc="", year=None):
        target = self._normalize_match_title(title_safe)
        srch, _fd = self.checkType(shortdesc, fulldesc)

        candidates = []

        for each in results:
            title = each.get('name', each.get('title', ''))
            original_title = each.get('original_name', each.get('original_title', ''))
            media_type = str(each.get('media_type', '')).lower()

            if not media_type:
                if srch == "tv":
                    media_type = "serie"
                elif srch == "movie":
                    media_type = "movie"

            if media_type == "tv":
                media_type = "serie"

            image_path = each.get('poster_path') or each.get('backdrop_path')
            if media_type not in ['movie', 'serie'] or not image_path:
                continue

            title_n = self._normalize_match_title(title)
            orig_n = self._normalize_match_title(original_title)
            result_year = each.get('release_date', each.get('first_air_date', ''))[:4]

            score = 0

            if title_n == target:
                score += 500
            if orig_n == target:
                score += 500

            if target and target in title_n:
                score += 120
            if target and target in orig_n:
                score += 120
            if title_n and title_n in target:
                score += 80
            if orig_n and orig_n in target:
                score += 80

            if srch == 'movie' and media_type == 'movie':
                score += 200
            elif srch in ('tv', 'serie') and media_type == 'serie':
                score += 200
            elif srch == 'multi':
                if media_type == 'movie':
                    score += 30
                elif media_type == 'serie':
                    score += 10

            if year:
                if result_year:
                    if str(year) == str(result_year):
                        score += 600
                    else:
                        score -= 500
                else:
                    score -= 150

            try:
                score += min(float(each.get('popularity', 0)), 10)
            except Exception:
                pass

            candidates.append((each, score, result_year))

        if not candidates:
            return None, -1

        if year:
            exact_year = [(each, score) for each, score, result_year in candidates if str(result_year) == str(year)]
            if exact_year:
                exact_year.sort(key=lambda x: x[1], reverse=True)
                return exact_year[0][0], exact_year[0][1]

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0], candidates[0][1]

    def _select_best_tmdb_logo(self, logos, preferred_langs=None):
        best = None
        best_score = -1
        preferred_langs = preferred_langs or [lng, "en", "ar", "null"]

        for logo in logos:
            file_path = logo.get("file_path", "")
            if not file_path:
                continue

            score = 0
            iso = logo.get("iso_639_1")
            iso_key = "null" if iso is None else str(iso).lower()

            if iso_key in preferred_langs:
                score += 200 - (preferred_langs.index(iso_key) * 30)

            if file_path.lower().endswith(".png"):
                score += 80

            try:
                score += min(int(logo.get("vote_count", 0)), 20)
                score += min(float(logo.get("vote_average", 0)) * 5, 50)
            except Exception:
                pass

            try:
                score += min(int(logo.get("width", 0)) // 20, 50)
            except Exception:
                pass

            if score > best_score:
                best_score = score
                best = logo

        return best, best_score

    def search_tmdb_logo(self, dwn_logo, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
        def _strip_year_for_search(t):
            t = str(t).strip()
            t = sub(r"\s*[\(\[]\s*(?:19|20)\d{2}\s*[\)\]]\s*", " ", t)
            t = sub(r"(?<!^)\s+(?:19|20)\d{2}\s*$", "", t)
            return sub(r"\s+", " ", t).strip()

        tmdb_api_key = api_key or tmdb_api
        if not tmdb_api_key:
            return False, "No API key"

        try:
            if not dwn_logo or not title:
                return False, "Invalid input parameters"

            clean_input_title = title.replace("+", " ").replace('–', '').strip()
            # logger.info("[tmdb-logo] year flow | step='clean_input_title' | value='{}'".format(str(clean_input_title or "")))

            forced_year = ""
            split_title = clean_input_title
            try:
                split_title, forced_year = split_title_and_year(clean_input_title)
                # logger.info("[tmdb-logo] year flow | step='split_title_and_year' | split_title='{}' | forced_year='{}'".format(str(split_title or ""), str(forced_year or "")year flow))
            except Exception as e:
                print(str(e))
                # logger.info("[tmdb-logo] year flow | step='split_title_and_year_error' | error='{}'".format(str(e)))
                forced_year = ""
                split_title = clean_input_title

            local_title_safe = _strip_year_for_search(split_title)
            # logger.info("[tmdb-logo] year flow | step='strip_year_for_search' | title_safe='{}'".format(str(local_title_safe or "")))
            if not local_title_safe:
                return False, "Invalid title after cleaning"

            srch, fd = self.checkType(shortdesc, fulldesc)
            # logger.info("[tmdb-logo] year flow | step='checkType' | srch='{}' | fd='{}'".format(str(srch or ""), str(fd or "")))

            search_language = self._get_tmdb_search_language(local_title_safe)

            logger.info("[tmdb-logo] language flow | title='{}' | language='{}' | srch='{}'".format(
                str(local_title_safe or ""),
                str(search_language or ""),
                str(srch or "")
            ))
            desc_year = ""
            if not year:
                year = self._extract_year(fd)
                desc_year = year
                print(str(desc_year))
            # logger.info("[tmdb-logo] year flow | step='extract_year' | desc_year='{}' | incoming_year='{}'".format(str(desc_year or ""), str(year or "")))

            if forced_year and not year:
                year = forced_year
                # logger.info("[tmdb-logo] year flow | step='apply_forced_year' | applied_year='{}'".format(str(year or "")))
            else:
                logger.info("[tmdb-logo] year flow | step='skip_forced_year' | forced_year='{}' | final_year_before_search='{}'".format(str(forced_year or ""), str(year or "")))

            local_search_year = year or ""
            # logger.info("[tmdb-logo] year flow | step='final_search_parts' | title_safe='{}' | search_year='{}'".format(str(local_title_safe or ""), str(local_search_year or "")))

            request_url = "https://api.themoviedb.org/3/search/{}?api_key={}&language={}&query={}".format(
                srch,
                tmdb_api_key,
                search_language,
                quoteEventName(local_title_safe)
            )
            if year and srch in ("movie", "multi"):
                request_url += "&year={}".format(year)

            logger.info("[tmdb-logo] title flow | original='{}' | final='{}' | year='{}' | channel='{}'".format(
                str(title or ""), str(local_title_safe or ""), str(year or ""), str(channel or "")
            ))
            logger.info("[tmdb-logo] search link | url={}".format(request_url))

            retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retries)
            http = Session()
            http.mount("http://", adapter)
            http.mount("https://", adapter)

            response = http.get(request_url, headers=headers, timeout=(10, 20), verify=False)
            response.raise_for_status()
            if response.status_code != codes.ok:
                return False, "No results"

            data = response.json()
            if not data or not data.get("results"):
                logger.warning("No results found on TMDB for logo")
                return False, "No results"

            best, best_score = self._select_best_tmdb_result(
                data.get("results", []),
                local_title_safe,
                shortdesc,
                fulldesc,
                local_search_year or self._extract_year(fulldesc or shortdesc or "")
            )
            if not best:
                logger.warning("No valid TMDB result after ranking for logo")
                return False, "No valid result"

            media_type = str(best.get("media_type", "")).lower()
            if not media_type:
                media_type = "tv" if srch in ("tv", "serie") else "movie"
            if media_type == "serie":
                media_type = "tv"

            item_id = best.get("id")
            if not item_id:
                return False, "Missing TMDB id"

            preferred_langs = self._build_logo_language_list(clean_input_title, srch)

            # First try: filtered by preferred languages
            images_url = "https://api.themoviedb.org/3/{}/{}/images?api_key={}&include_image_language={}".format(
                media_type, item_id, tmdb_api_key, ",".join(preferred_langs)
            )
            logger.info("[tmdb-logo] images link | url={}".format(images_url))

            img_response = http.get(images_url, headers=headers, timeout=(10, 20), verify=False)
            img_response.raise_for_status()
            images_data = img_response.json()
            logos = images_data.get("logos", [])

            if not logos:
                logger.warning("[tmdb-logo] no logos with language filter | langs='{}' | retrying without language filter".format(
                    ",".join(preferred_langs)
                ))

                # Second try: no language filter at all
                fallback_images_url = "https://api.themoviedb.org/3/{}/{}/images?api_key={}&include_image_language=".format(
                    media_type, item_id, tmdb_api_key
                )
                logger.info("[tmdb-logo] fallback images link | url={}".format(fallback_images_url))

                fallback_response = http.get(fallback_images_url, headers=headers, timeout=(10, 20), verify=False)
                fallback_response.raise_for_status()
                fallback_images_data = fallback_response.json()
                logos = fallback_images_data.get("logos", [])

            if not logos:
                logger.warning("[tmdb-logo] no logos found even after fallback")
                return False, "No logos found"

            best_logo, logo_score = self._select_best_tmdb_logo(logos, preferred_langs)
            if not best_logo:
                return False, "No valid logo"

            file_path = best_logo.get("file_path", "")
            logo_url = "https://image.tmdb.org/t/p/w500{}".format(file_path)
            logger.info("[tmdb-logo] selected result | title='{}' | original_title='{}' | score='{}' | logo_score='{}' | logo_path='{}'".format(
                str(best.get('name', best.get('title', '')) or ""),
                str(best.get('original_name', best.get('original_title', '')) or ""),
                str(best_score),
                str(logo_score),
                str(file_path)
            ))

            success = self.saveLogo(logo_url, dwn_logo)
            if success and exists(dwn_logo):
                return True, "[SUCCESS] Logo match"

            return False, "Logo download failed"

        except HTTPError as e:
            logger.error("TMDb logo HTTP error: " + str(e))
            return False, "HTTP error during TMDb logo search"
        except Exception as e:
            logger.error("TMDb logo search error: " + str(e))
            return False, "Unexpected error during TMDb logo search"

    def saveLogo(self, url, filepath):
        if not url:
            return False
        lock = threading.Lock()
        with lock:
            try:
                folder = dirname(filepath)
                if folder and not exists(folder):
                    makedirs(folder, exist_ok=True)
            except Exception as e:
                logger.error("Failed to create logo folder {}: {}".format(dirname(filepath), str(e)))
                return False
            if exists(filepath):
                try:
                    with open(filepath, "rb") as f:
                        if f.read(8) == b'\x89PNG\r\n\x1a\n' and getsize(filepath) > 100:
                            return True
                    remove(filepath)
                except Exception:
                    if exists(filepath):
                        remove(filepath)

            for attempt in range(3):
                try:
                    logo_headers = {
                        "User-Agent": choice(AGENTS),
                        "Accept": "image/png,image/*",
                        "Accept-Encoding": "gzip"
                    }
                    response = get(url, headers=logo_headers, stream=True, timeout=(15, 30))
                    response.raise_for_status()
                    with open(filepath, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    with open(filepath, "rb") as f:
                        if f.read(8) != b'\x89PNG\r\n\x1a\n' or getsize(filepath) < 100:
                            remove(filepath)
                            raise ValueError("Invalid PNG file")
                    logger.debug("Successfully saved logo: {} -> {}".format(url, filepath))
                    return True
                except Exception as e:
                    if exists(filepath):
                        try:
                            remove(filepath)
                        except Exception:
                            pass
                    logger.debug("Logo attempt {} failed: {}".format(attempt + 1, str(e)))
                    sleep(2 * (attempt + 1))
            return False

    def _extract_year(self, description):
        try:
            year_matches = findall(r"19\d{2}|20\d{2}", description)
            return year_matches[0] if year_matches else ""
        except Exception:
            return ""

    def checkType(self, shortdesc, fulldesc):
        if shortdesc and shortdesc != '':
            fd = shortdesc.splitlines()[0]
        elif fulldesc and fulldesc != '':
            fd = fulldesc.splitlines()[0]
        else:
            fd = ''
        text = "{} {}".format(shortdesc or "", fulldesc or "").lower()
        tv_patterns = [
            r'\bseason\s*\d+\b', r'\bs\d+\s*e\d+\b', r'\bepisode\s*\d+\b',
            r'\bepisodio\s*\d+\b', r'\bstagione\s*\d+\b', r'\bep\.?\s*\d+\b',
            r'\bج\s*\d+\b', r'\bح\s*\d+\b', r'\bجزء\s*\d+\b',
            r'\bحلقة\s*\d+\b', r'\bالموسم\s*\d+\b', r'\bالحلقة\s*\d+\b'
            r'\bodc\.?\s*\d+\b',
            r'\bodcinek\s*\d+\b',
        ]
        movie_patterns = [
            r'\bfilm\b', r'\bmovie\b', r'\bpel[íi]cula\b', r'\bcinema\b',
            r'\bcin[eé]ma\b', r'\bфильм\b', r'\bkino\b', r'\bfilma\b'
        ]
        global srch
        srch = "multi"
        for pattern in tv_patterns:
            if compile(pattern, IGNORECASE).search(text):
                srch = "tv"
                return srch, fd
        for pattern in movie_patterns:
            if compile(pattern, IGNORECASE).search(text):
                srch = "movie"
                return srch, fd
        return srch, fd
