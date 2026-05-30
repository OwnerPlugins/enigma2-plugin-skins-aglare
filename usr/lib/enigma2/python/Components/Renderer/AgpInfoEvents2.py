#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
##__author__ = "Lululla"         ##
##__copyright__ = "AGP Team"     ##
##__modified_by__ = "MNASR"      ##
###################################
from __future__ import absolute_import, print_function

from json import load as json_load, dump as json_dump
from threading import Lock, Thread
from os.path import exists, join, getsize
from urllib.request import urlopen
from re import findall
import urllib3
import gettext

from Components.config import config
from Components.Renderer.Renderer import Renderer
from Components.VariableText import VariableText
from enigma import eLabel, eEPGCache, eTimer
from Components.Sources.Event import Event
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance
from ServiceReference import ServiceReference

from Plugins.Extensions.Aglare.api_config import cfg
from Plugins.Extensions.Aglare.api_config import ApiKeyManager
from .Agp_Utils import IMOVIE_FOLDER, logger
from .Agp_lib import build_search_title, quoteEventName, clean_search_title, smart_capitalize_title, should_skip_title

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if not IMOVIE_FOLDER.endswith("/"):
    IMOVIE_FOLDER += "/"

api_key_manager = ApiKeyManager()
DATA_SOURCE = cfg.info_display_mode.value
epgcache = eEPGCache.getInstance()
api_lock = Lock()
_ = gettext.gettext

try:
    lng = config.osd.language.value
    lng = lng[:-3]
except BaseException:
    lng = 'en'


class AgpInfoEvents2(Renderer, VariableText):
    GUI_WIDGET = eLabel

    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)

        self.current_request = None
        self.current_request_key = None
        self.pending_display_key = None
        self.pending_display_text = ""
        self.last_event = None
        self.lock = Lock()
        self.text = ""
        self.nxts = 0
        self.canal = [None] * 6
        self.oldCanal = None

        self.adsl = True
        self._last_event_list_log = None
        self.storage_path = IMOVIE_FOLDER
        self.timer = eTimer()
        self.timer.callback.append(self.delayed_update)
        logger.info("AgpInfoEvents2 Renderer initialized")

    def applySkin(self, desktop, screen):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == 'nexts':
                try:
                    self.nxts = int(value)
                except Exception:
                    self.nxts = 0
            elif attrib == 'path':
                self.storage_path = str(value)
            else:
                attribs.append((attrib, value))
        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, screen)

    def detect_expected_media_type(self):
        try:
            desc = "{}\n{}\n{}".format(
                self.canal[2] if self.canal and len(self.canal) > 2 else "",
                self.canal[4] if self.canal and len(self.canal) > 4 else "",
                self.canal[3] if self.canal and len(self.canal) > 3 else ""
            ).lower()

            tv_markers = [
                "odc.", "odc ", "odcinek", "episode", "ep.", "ep ",
                "serial", "serie", "series", "season", "saison"
            ]
            movie_markers = [
                "film", "movie", "cinema", "feature film"
            ]

            if any(marker in desc for marker in tv_markers):
                return "tv"
            if any(marker in desc for marker in movie_markers):
                return "movie"
            return None
        except Exception:
            return None

    def get_search_title(self, title, shortdesc="", fulldesc=""):
        try:
            result = build_search_title(title or "", shortdesc or "", fulldesc or "")
            return smart_capitalize_title(result)
        except Exception:
            return smart_capitalize_title(clean_search_title(title or ""))

    def _clear_display(self):
        self.text = ""
        self.pending_display_key = None
        self.pending_display_text = ""
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
        if self.instance:
            self.instance.hide()

    def _strip_service_name(self, service):
        try:
            return ServiceReference(service).getServiceName().replace('\xc2\x86', '').replace('\xc2\x87', '')
        except Exception:
            return ""

    def _resolve_event_from_source(self):
        source = self.source
        source_type = type(source)
        service = None

        if source_type is ServiceEvent:
            service = source.getCurrentService()
        elif source_type is CurrentService:
            service = source.getCurrentServiceRef()
        elif source_type is EventInfo:
            service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
        elif source_type is Event:
            if getattr(source, "event", None) is not None:
                event = source.event
                self.canal = [None] * 6
                self.canal[1] = event.getBeginTime()
                self.canal[2] = event.getEventName()
                self.canal[3] = event.getExtendedDescription()
                self.canal[4] = event.getShortDescription()
                self.canal[5] = event.getEventName()
                return True
            service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()

        if service is None:
            return False

        service_str = service.toString()
        events = epgcache.lookupEvent(['IBDCTESX', (service_str, 0, -1, -1)])
        try:
            current_key = "{}-{}".format(self.nxts, len(events) if events else 0)
            if getattr(self, "_last_event_list_log", None) != current_key:
                logger.info("AgpInfoEvents2 event list | nexts='{}' | events_count='{}'".format(
                    str(self.nxts), str(len(events) if events else 0)
                ))
                self._last_event_list_log = current_key
        except Exception:
            pass

        if not events or len(events) <= self.nxts:
            return False

        self.canal = [None] * 6
        self.canal[0] = self._strip_service_name(service)
        self.canal[1] = events[self.nxts][1]
        self.canal[2] = events[self.nxts][4]
        self.canal[3] = events[self.nxts][5]
        self.canal[4] = events[self.nxts][6]
        self.canal[5] = self.canal[2]
        return True

    def changed(self, what):
        if what is None or not self.adsl or DATA_SOURCE == "off":
            self._clear_display()
            return

        if what[0] == self.CHANGED_CLEAR:
            self._last_event_list_log = None
            self.oldCanal = None
            self.current_request_key = None
            self._clear_display()
            return

        try:
            if not self._resolve_event_from_source() or not self.canal[5]:
                logger.info("AgpInfoEvents2 infos: no usable event")
                self.current_request_key = None
                self._clear_display()
                return

            curCanal = "%s-%s-%s" % (self.nxts, self.canal[1], self.canal[2])
            if curCanal == self.oldCanal:
                return

            self.oldCanal = curCanal
            self._clear_display()
            logger.info("AgpInfoEvents2 selected event | nexts='{}' | title='{}'".format(
                str(self.nxts), self.canal[2]
            ))
            self.start_data_fetch()

        except Exception as e:
            logger.error("AgpInfoEvents2 changed error: {}".format(str(e)), exc_info=True)
            self.current_request_key = None
            self._clear_display()

    def start_data_fetch(self):
        request_key = "%s-%s-%s" % (
            self.nxts,
            self.canal[1] if self.canal and len(self.canal) > 1 else "",
            self.canal[2] if self.canal and len(self.canal) > 2 else ""
        )

        if getattr(self, "current_request_key", None) == request_key:
            if self.current_request and self.current_request.is_alive():
                return

        self.current_request_key = request_key
        self.current_request = Thread(target=self.fetch_event_data, args=(request_key,))
        self.current_request.daemon = True
        self.current_request.start()

    def extract_year_from_canal(self):
        try:
            desc = "{}\n{}\n{}".format(
                self.canal[2] if self.canal and len(self.canal) > 2 else "",
                self.canal[4] if self.canal and len(self.canal) > 4 else "",
                self.canal[3] if self.canal and len(self.canal) > 3 else ""
            )
            years = findall(r'\b\d{4}\b', desc)
            if years:
                valid_years = [y for y in years if 1900 <= int(y) <= 2100]
                if valid_years:
                    return max(valid_years)
            return None
        except Exception:
            return None

    def fetch_event_data(self, request_key=None):
        if DATA_SOURCE == "off":
            return

        with self.lock:
            try:
                if request_key is not None and request_key != self.current_request_key:
                    return

                clean_title = self.get_search_title(self.canal[5], self.canal[4], self.canal[3])
                skip_title, skip_word = should_skip_title(clean_title)
                if skip_title:
                    logger.info("AgpInfoEvents2 skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                        self.canal[2], clean_title, skip_word
                    ))
                    self.current_request_key = None
                    self._clear_display()
                    return

                json_file = join(self.storage_path, "{}.json".format(clean_title))
                year = self.extract_year_from_canal()
                data = None

                if exists(json_file) and getsize(json_file) > 0:
                    with open(json_file, "r") as f:
                        data = json_load(f)
                    logger.info("AgpInfoEvents2 loaded cached json | file='{}' | title='{}' | vote='{}'".format(
                        json_file,
                        clean_title,
                        str(data.get('vote_average', data.get('imdbRating', '')))
                    ))
                else:
                    if DATA_SOURCE == "tmdb" or (DATA_SOURCE == "auto" and api_key_manager.get_api_key('tmdb')):
                        data = self.fetch_tmdb_data(clean_title, year)
                    else:
                        data = self.fetch_omdb_data(clean_title, year)

                    if data:
                        with open(json_file, "w") as f:
                            json_dump(data, f, indent=2)
                        logger.info("AgpInfoEvents2 saved json | file='{}' | title='{}' | vote='{}'".format(
                            json_file,
                            clean_title,
                            str(data.get('vote_average', data.get('imdbRating', '')))
                        ))

                if request_key is not None and request_key != self.current_request_key:
                    return

                if data:
                    self.process_data(data, request_key=request_key)
                else:
                    logger.info("AgpInfoEvents2 no data found | title='{}'".format(clean_title))
                    self.current_request_key = None
                    self._clear_display()

            except Exception as e:
                logger.error("AgpInfoEvents2 Data fetch error: {}".format(str(e)), exc_info=True)
                self.current_request_key = None
                self._clear_display()

    def fetch_tmdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('tmdb')
            expected_type = self.detect_expected_media_type()
            search_year = year if expected_type == "movie" else None

            search_url = (
                "https://api.themoviedb.org/3/search/multi?api_key=" + api_key +
                "&language=" + lng +
                "&query=" + quoteEventName(title) +
                ("&year=" + str(search_year) if search_year else "")
            )
            logger.info("AgpInfoEvents2 TMDB search link | url={}".format(search_url))
            with urlopen(search_url) as response:
                search_data = json_load(response)

            if not search_data.get("results"):
                return None

            result = self.select_best_result(search_data["results"], title)
            content_type = result["media_type"]
            content_id = result["id"]

            append_parts = ["credits"]
            if content_type == "movie":
                append_parts.append("release_dates")
            elif content_type == "tv":
                append_parts.append("content_ratings")

            details_url = (
                "https://api.themoviedb.org/3/" +
                content_type +
                "/" +
                str(content_id) +
                "?api_key=" +
                api_key +
                "&language=" +
                lng +
                "&append_to_response=" + ",".join(append_parts)
            )
            logger.info("AgpInfoEvents2 TMDB details link | url={}".format(details_url))
            with urlopen(details_url) as response:
                return json_load(response)

        except Exception as e:
            logger.error("AgpInfoEvents2 TMDB API error: {}".format(str(e)))
            return None

    def fetch_omdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('omdb')
            params = "t={}{}&plot=full".format(
                quoteEventName(title),
                "&y={}".format(year) if year else ""
            )
            url = "http://www.omdbapi.com/?apikey={}&{}".format(api_key, params)
            logger.info("AgpInfoEvents2 OMDB request link | url={}".format(url))
            with urlopen(url) as response:
                return json_load(response)
        except Exception as e:
            logger.error("AgpInfoEvents2 OMDB API error: {}".format(str(e)))
            return None

    def select_best_result(self, results, original_title):
        target = str(original_title or "").strip().lower()
        expected_type = self.detect_expected_media_type()

        desc = "{}\n{}\n{}".format(
            self.canal[2] if self.canal and len(self.canal) > 2 else "",
            self.canal[4] if self.canal and len(self.canal) > 4 else "",
            self.canal[3] if self.canal and len(self.canal) > 3 else ""
        )
        years = findall(r'\b\d{4}\b', desc)
        year = None
        if years:
            valid_years = [y for y in years if 1900 <= int(y) <= 2100]
            if valid_years:
                year = max(valid_years)

        scored = []
        for result in results:
            media_type = result.get('media_type')
            if media_type not in ('movie', 'tv'):
                continue

            name = (result.get('title') or result.get('name') or "").strip().lower()
            original_name = (result.get('original_title') or result.get('original_name') or "").strip().lower()
            result_year = (result.get('release_date') or result.get('first_air_date') or "")[:4]

            score = 0

            if name == target:
                score += 500
            if original_name == target:
                score += 500
            if target and target in name:
                score += 120
            if target and target in original_name:
                score += 120

            # prefer expected media type from EPG description
            if expected_type == "tv":
                if media_type == "tv":
                    score += 350
                else:
                    score -= 350
            elif expected_type == "movie":
                if media_type == "movie":
                    score += 350
                else:
                    score -= 350

            # Apply strict year matching only for movies.
            # For TV, EPG year is often episode/season/broadcast year, not first_air_date.
            if year and media_type == "movie":
                if result_year:
                    if str(result_year) == str(year):
                        score += 600
                    else:
                        score -= 500
                else:
                    score -= 150

            try:
                score += min(float(result.get('popularity', 0)), 10)
            except Exception:
                pass

            scored.append((result, score, result_year))

        if not scored:
            return results[0]

        if year:
            exact_year = [(r, s) for r, s, ry in scored if str(ry) == str(year)]
            if exact_year:
                exact_year.sort(key=lambda x: x[1], reverse=True)
                return exact_year[0][0]

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _extract_title(self, data):
        return (data.get('title') or data.get('name') or data.get('Title') or "").strip()

    def _extract_year(self, data):
        value = data.get('release_date') or data.get('first_air_date') or data.get('Year') or ""
        if value:
            return str(value).split('-')[0].strip()
        return ""

    def _extract_runtime_text(self, data):
        runtime = data.get('runtime') or data.get('Runtime') or ""
        if isinstance(runtime, int):
            minutes = runtime
        else:
            digits = "".join(ch for ch in str(runtime) if ch.isdigit())
            minutes = int(digits) if digits else 0

        if minutes <= 0:
            return ""

        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return "{} h {} min".format(hours, mins)
        return "{} min".format(mins)

    def _extract_genres_text(self, data):
        names = []
        if data.get('genres'):
            for item in data.get('genres', []):
                name = (item.get('name') or "").strip()
                if name:
                    names.append(name)
        elif data.get('Genre'):
            names = [x.strip() for x in str(data.get('Genre')).split(',') if x.strip()]

        names = names[:3]
        return " • ".join(names)

    def _extract_rating_text(self, data):
        tmdb_rating = data.get('vote_average')
        imdb_rating = data.get('imdbRating')

        star_text = ""
        imdb_text = ""

        try:
            if tmdb_rating not in (None, "", 0, "0"):
                tmdb_float = float(tmdb_rating)
                star_text = "★ {}/5".format(round(tmdb_float / 2.0, 1))
                imdb_text = "IMDb {}/10".format(round(tmdb_float, 1))
        except Exception:
            pass

        try:
            if imdb_rating not in (None, "", "N/A"):
                imdb_float = float(imdb_rating)
                if not star_text:
                    star_text = "★ {}/5".format(round(imdb_float / 2.0, 1))
                imdb_text = "IMDb {}/10".format(round(imdb_float, 1))
        except Exception:
            pass

        parts = []
        if star_text:
            parts.append(star_text)
        if imdb_text:
            parts.append(imdb_text)
        return "   ".join(parts)

    def _extract_overview(self, data):
        return (data.get('overview') or data.get('Plot') or "").strip()

    def process_data(self, data, request_key=None):
        try:
            if request_key is not None and request_key != self.current_request_key:
                return

            title = self._extract_title(data)
            year = self._extract_year(data)
            runtime = self._extract_runtime_text(data)
            genres = self._extract_genres_text(data)
            rating_row = self._extract_rating_text(data)
            overview = self._extract_overview(data)

            lines = []

            title_line = title
            if year and ("({})".format(year) not in title_line):
                title_line = "{} ({})".format(title_line, year)
            if title_line:
                lines.append(title_line)

            if genres:
                lines.append(genres)

            meta_parts = []
            if rating_row:
                meta_parts.append(rating_row)
            if year:
                meta_parts.append(year)
            if runtime:
                meta_parts.append(runtime)

            if meta_parts:
                lines.append("   ".join(meta_parts))

            if overview:
                lines.append("")
                lines.append(overview)

            new_text = "\n".join(lines).strip()
            if not new_text:
                self.current_request_key = None
                self._clear_display()
                return

            if new_text == self.text:
                self.current_request_key = None
                return

            self.pending_display_key = request_key
            self.pending_display_text = new_text

            logger.info("AgpInfoEvents2 formatted text | title='{}' | genres='{}' | meta='{}'".format(
                title,
                genres,
                " | ".join(meta_parts)
            ))

            self.current_request_key = None
            self.timer.start(100, True)

        except Exception as e:
            logger.error("AgpInfoEvents2 Data processing error: {}".format(str(e)))
            self.current_request_key = None
            self._clear_display()

    def delayed_update(self):
        if not self.instance:
            return

        if not self.pending_display_text:
            self.text = ""
            self.instance.hide()
            return

        self.text = self.pending_display_text
        self.instance.setText(self.text)

        if self.text:
            self.instance.show()
        else:
            self.instance.hide()

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

    def onHide(self):
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass

    def onShow(self):
        pass
