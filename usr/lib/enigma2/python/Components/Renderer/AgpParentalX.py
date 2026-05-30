#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
## __author__ = "Lululla"         ##
## __copyright__ = "AGP Team"     ##
## __modified_by__ = "MNASR"      ##
###################################
from __future__ import absolute_import, print_function

from os.path import join, exists, getsize
from re import findall
from json import load as json_load, dump as json_dump
from threading import Lock, Thread

from Components.Renderer.Renderer import Renderer
from enigma import ePixmap, loadPNG, eEPGCache
from Components.config import config
import gettext
from urllib.request import urlopen

from Plugins.Extensions.Aglare.api_config import cfg
from Plugins.Extensions.Aglare.api_config import ApiKeyManager

from .Agp_Utils import IMOVIE_FOLDER, clean_for_tvdb, logger
from .Agp_lib import build_search_title, quoteEventName, clean_search_title, smart_capitalize_title, should_skip_title

if not IMOVIE_FOLDER.endswith("/"):
    IMOVIE_FOLDER += "/"

api_key_manager = ApiKeyManager()
_ = gettext.gettext
cur_skin = config.skin.primary_skin.value.replace('/skin.xml', '')

PARENTAL_ICON_PATH = f'/usr/share/enigma2/{cur_skin}/parental/'
PARENT_SOURCE = cfg.info_parental_mode.value
DEFAULT_RATING = 'UN'
NA_RATING = 'NA'
DEFAULT_ICON = 'FSK_UN.png'

RATING_MAP = {
    'TV-Y': '6', 'TV-Y7': '6', 'TV-G': '0', 'TV-PG': '16',
    'TV-14': '16', 'TV-MA': '18',
    'G': '0', 'PG': '12', 'PG-13': '16', 'R': '18',
    'NC-17': '18',
    'PEGI-12': '12', 'PEGI-16': '16', 'PEGI-18': '18',
    '': DEFAULT_RATING, 'NA': NA_RATING,
    'NOT RATED': NA_RATING, 'UNRATED': NA_RATING, 'UN': DEFAULT_RATING
}

try:
    lng = config.osd.language.value
    lng = lng[:-3]
except BaseException:
    lng = 'en'


class AgpParentalX(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.last_event = None
        self.current_request = None
        self.current_request_key = None
        self.lock = Lock()
        self.epgcache = eEPGCache.getInstance()
        self.epgcache.load()

        self.adsl = True

        self.icon_path = join(PARENTAL_ICON_PATH, DEFAULT_ICON)
        self.storage_path = IMOVIE_FOLDER

    def get_search_title(self, title, shortdesc="", fulldesc=""):
        try:
            result = build_search_title(
                title or "", shortdesc or "", fulldesc or "")
            return smart_capitalize_title(result)
        except Exception:
            return smart_capitalize_title(clean_search_title(title or ""))

    def changed(self, what):
        if what is None or not self.adsl or PARENT_SOURCE == "off":
            if self.instance:
                self.instance.hide()
            return

        self.event = self.source.event
        if self.event:
            name = self.event.getEventName()
            if not name:
                return

            begin = self.event.getBeginTime()
            if begin is None:
                return

            current_event_hash = name + str(begin)
            if current_event_hash != self.last_event:
                self.last_event = current_event_hash
                self.start_data_fetch()

    def start_data_fetch(self):
        request_key = self.event.getEventName() if self.event else ""
        if getattr(self, "current_request_key", None) == request_key:
            if self.current_request and self.current_request.is_alive():
                return
        self.current_request_key = request_key
        self.current_request = Thread(target=self.fetch_data)
        self.current_request.start()

    def fetch_data(self):
        if PARENT_SOURCE == "off":
            return

        with self.lock:
            try:
                clean_title = self.get_search_title(
                    (self.event.getEventName() or "").replace(
                        '\xc2\x86',
                        '').replace(
                        '\xc2\x87',
                        ''),
                    self.event.getShortDescription() or "",
                    self.event.getExtendedDescription() or "")

                skip_title, skip_word = should_skip_title(clean_title)
                if skip_title:
                    logger.info(
                        "AgpParentalX skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                            self.event.getEventName(), clean_title, skip_word))
                    if self.instance:
                        self.instance.hide()
                    return

                parent_json_file = join(
                    self.storage_path,
                    "{} parental.json".format(clean_title))
                info_json_file = join(
                    self.storage_path,
                    "{}.json".format(clean_title))
                year = self.extract_year(self.event)

                data = None

                if exists(parent_json_file) and getsize(parent_json_file) > 0:
                    with open(parent_json_file, "r") as f:
                        data = json_load(f)
                    logger.info(
                        "AgpParentalX loaded cached parental json | file='{}' | rated='{}'".format(
                            parent_json_file, str(
                                data.get(
                                    'Rated', ''))))
                    self.process_data(data)
                    return

                # use info json only as a hint / fallback title presence, but
                # parental requires explicit certification endpoint
                if exists(info_json_file):
                    logger.info(
                        "AgpParentalX info json present | file='{}'".format(info_json_file))

                if PARENT_SOURCE == "tmdb" or (
                        PARENT_SOURCE == "auto" and api_key_manager.get_api_key('tmdb')):
                    data = self.fetch_tmdb_parental(clean_title, year)
                else:
                    data = self.fetch_omdb_data(clean_title, year)

                if data:
                    with open(parent_json_file, "w") as f:
                        json_dump(data, f, indent=2)
                    logger.info(
                        "AgpParentalX saved parental json | file='{}' | rated='{}'".format(
                            parent_json_file, str(
                                data.get(
                                    'Rated', ''))))
                    self.process_data(data)

            except Exception as e:
                logger.error(
                    "AgpParentalX Data fetch error: {}".format(
                        str(e)), exc_info=True)

    def fetch_tmdb_parental(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('tmdb')
            if not api_key:
                return None

            search_kind = "multi"
            desc = "{}\n{}\n{}".format(
                self.event.getEventName() or "",
                self.event.getShortDescription() or "",
                self.event.getExtendedDescription() or ""
            ).lower()
            if any(
                x in desc for x in [
                    "season",
                    "episode",
                    "series",
                    "serie",
                    "s.",
                    "ep.",
                    "episod"]):
                search_kind = "tv"

            search_url = (
                "https://api.themoviedb.org/3/search/{}?api_key={}&language={}&query={}".format(
                    search_kind, api_key, lng, quoteEventName(title)
                ) + ("&year={}".format(year) if year and search_kind != "tv" else "")
            )
            logger.info(
                "AgpParentalX TMDB search link | url={}".format(search_url))
            with urlopen(search_url) as response:
                search_data = json_load(response)

            results = search_data.get("results", [])
            if not results:
                logger.warning("AgpParentalX no TMDB results for parental")
                return None

            result = results[0]
            media_type = result.get("media_type", "")
            if not media_type:
                media_type = "tv" if search_kind == "tv" else "movie"
            if media_type not in ("movie", "tv"):
                media_type = "movie"

            content_id = result["id"]
            rated = ""

            if media_type == "movie":
                details_url = "https://api.themoviedb.org/3/movie/{}?api_key={}&language={}".format(
                    content_id, api_key, lng)
                cert_url = "https://api.themoviedb.org/3/movie/{}/release_dates?api_key={}".format(
                    content_id, api_key)
                logger.info(
                    "AgpParentalX TMDB details link | url={}".format(details_url))
                logger.info(
                    "AgpParentalX TMDB parental link | url={}".format(cert_url))
                with urlopen(details_url) as response:
                    details = json_load(response)
                with urlopen(cert_url) as response:
                    cert_data = json_load(response)
                for entry in cert_data.get("results", []):
                    if entry.get("iso_3166_1") == "US":
                        for rd in entry.get("release_dates", []):
                            cert = (rd.get("certification") or "").strip()
                            if cert:
                                rated = cert
                                break
                        if rated:
                            break
                details["Rated"] = rated
                details["media_type"] = "movie"
                return details

            else:
                details_url = "https://api.themoviedb.org/3/tv/{}?api_key={}&language={}".format(
                    content_id, api_key, lng)
                cert_url = "https://api.themoviedb.org/3/tv/{}/content_ratings?api_key={}".format(
                    content_id, api_key)
                logger.info(
                    "AgpParentalX TMDB details link | url={}".format(details_url))
                logger.info(
                    "AgpParentalX TMDB parental link | url={}".format(cert_url))
                with urlopen(details_url) as response:
                    details = json_load(response)
                with urlopen(cert_url) as response:
                    cert_data = json_load(response)
                for entry in cert_data.get("results", []):
                    if entry.get("iso_3166_1") == "US":
                        cert = (entry.get("rating") or "").strip()
                        if cert:
                            rated = cert
                            break
                details["Rated"] = rated
                details["media_type"] = "tv"
                return details

        except Exception as e:
            logger.error("AgpParentalX TMDB API error: {}".format(str(e)))
            return None

    def fetch_omdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('omdb')
            params = "t={}{}&plot=full".format(
                quoteEventName(title),
                "&y={}".format(year) if year else ""
            )
            url = "http://www.omdbapi.com/?apikey={}&{}".format(
                api_key, params)
            logger.info("AgpParentalX OMDB request link | url={}".format(url))
            with urlopen(url) as response:
                return json_load(response)
        except Exception as e:
            logger.error("AgpParentalX OMDB API error: {}".format(str(e)))
            return None

    def process_data(self, data):
        try:
            rated = (data.get("Rated", "") or "").strip().upper()
            logger.info(
                "AgpParentalX parental extracted | title='{}' | rated='{}'".format(
                    self.get_search_title(
                        self.event.getEventName() or "",
                        self.event.getShortDescription() or "",
                        self.event.getExtendedDescription() or ""),
                    rated))
            rating_code = RATING_MAP.get(rated, DEFAULT_RATING)
            icon_file = "FSK_" + rating_code + ".png"
            self.icon_path = join(PARENTAL_ICON_PATH, icon_file)

            if not exists(self.icon_path):
                logger.debug(
                    "AgpParentalX Rated icon not found for: {}, using default".format(rated))
                self.icon_path = join(PARENTAL_ICON_PATH, DEFAULT_ICON)

            self.update_icon(self.icon_path)

        except Exception as e:
            logger.error(
                "AgpParentalX Error processing data for event: " +
                str(e))
            self.icon_path = join(PARENTAL_ICON_PATH, DEFAULT_ICON)
            self.update_icon(self.icon_path)

    def update_icon(self, icon):
        if self.instance:
            self.instance.setPixmap(loadPNG(icon))
            self.instance.show()

    def extract_year(self, event):
        try:
            desc = "{}\n{}\n{}".format(
                event.getEventName(),
                event.getShortDescription(),
                event.getExtendedDescription()
            )
            years = findall(r'\b\d{4}\b', desc)
            if years:
                valid_years = [y for y in years if 1900 <= int(y) <= 2100]
                if valid_years:
                    return max(valid_years)
            return None
        except Exception:
            return None
