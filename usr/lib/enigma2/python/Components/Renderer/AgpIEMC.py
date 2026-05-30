#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
##__author__ = "Lululla"         ##
##__copyright__ = "AGP Team"     ##
##__created_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function
from json import load as json_load, dump as json_dump
from os import makedirs
from os.path import exists, getsize, join
from urllib.request import urlopen
from threading import Lock, Thread
import urllib3

from Components.Renderer.Renderer import Renderer
from Components.VariableText import VariableText
from enigma import eLabel, eTimer, eServiceCenter
from Components.config import config
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from Plugins.Extensions.Aglare.api_config import cfg, ApiKeyManager
from .Agp_Utils import logger
from .Agp_lib import quoteEventName
from .AgpEMCBase import EMC_ROOT, EMC_INFO_FOLDER, ensure_emc_dirs, build_emc_search_title, extract_emc_year, is_emc_episode, is_video_file

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
api_key_manager = ApiKeyManager()
try:
    lng = config.osd.language.value[:-3]
except BaseException:
    lng = 'en'

class AgpIEMC(Renderer, VariableText):
    GUI_WIDGET = eLabel

    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)
        self.storage_path = EMC_INFO_FOLDER
        self.current_request = None
        self.current_request_key = None
        self.lock = Lock()
        self.text = ""
        self.current_movie_path = ""
        self.timer = eTimer()
        self.timer.callback.append(self.delayed_update)
        ensure_emc_dirs(EMC_ROOT)

    def applySkin(self, desktop, parent):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == "path":
                self.storage_path = str(value)
                if not exists(self.storage_path):
                    makedirs(self.storage_path, exist_ok=True)
            else:
                attribs.append((attrib, value))
        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, parent)

    def changed(self, what):
        if not self.instance:
            return
        if what is None or cfg.info_display_mode.value == "off":
            self._clear_display()
            return
        if what and what[0] == self.CHANGED_CLEAR:
            self.current_request_key = None
            self.current_movie_path = ""
            self._clear_display()
            return
        try:
            source = self.source
            service_ref = None
            movie_path = None
            service_handler = eServiceCenter.getInstance()
            if hasattr(source, "__class__"):
                class_name = source.__class__.__name__
                if class_name == "EMCServiceEvent":
                    service_ref = getattr(source, "service", None)
                    if service_ref:
                        try:
                            movie_path = service_ref.getPath()
                        except Exception:
                            movie_path = None
                elif class_name == "EMCCurrentService":
                    try:
                        service_ref = source.getCurrentService()
                    except Exception:
                        service_ref = None
                    if service_ref:
                        try:
                            movie_path = service_ref.getPath()
                        except Exception:
                            movie_path = None
            if not movie_path:
                if isinstance(source, ServiceEvent):
                    service_ref = source.getCurrentService()
                    movie_path = service_ref.getPath() if service_ref else None
                elif isinstance(source, CurrentService):
                    service_ref = source.getCurrentServiceRef()
                    movie_path = service_ref.getPath() if service_ref else None
                elif isinstance(source, EventInfo):
                    service_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                    movie_path = service_ref.getPath() if service_ref else None
            if not movie_path:
                service_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                if service_ref:
                    info = service_handler.info(service_ref)
                    if info:
                        movie_path = service_ref.getPath()
            if not movie_path or not is_video_file(movie_path):
                self._clear_display()
                return
            if movie_path == self.current_movie_path:
                return
            self.current_movie_path = movie_path
            self._clear_display()
            self.start_data_fetch(movie_path)
        except Exception as e:
            logger.error("AgpIEMC changed error: {}".format(str(e)), exc_info=True)
            self._clear_display()

    def _clear_display(self):
        self.text = ""
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
        if self.instance:
            self.instance.hide()

    def start_data_fetch(self, movie_path):
        request_key = movie_path
        if self.current_request_key == request_key and self.current_request and self.current_request.is_alive():
            return
        self.current_request_key = request_key
        self.current_request = Thread(target=self.fetch_event_data, args=(movie_path, request_key))
        self.current_request.daemon = True
        self.current_request.start()

    def fetch_event_data(self, movie_path, request_key=None):
        with self.lock:
            try:
                if request_key != self.current_request_key:
                    return
                clean_title = build_emc_search_title(movie_path)
                json_file = join(self.storage_path, "%s.json" % clean_title)
                data = None
                year = extract_emc_year(movie_path)
                if exists(json_file) and getsize(json_file) > 0:
                    with open(json_file, "r") as f:
                        data = json_load(f)
                else:
                    data = self.fetch_tmdb_data(clean_title, year, movie_path)
                    if not data:
                        data = self.fetch_omdb_data(clean_title, year)
                    if data:
                        with open(json_file, "w") as f:
                            json_dump(data, f, indent=2)
                if request_key != self.current_request_key:
                    return
                if data:
                    self.process_data(data)
                else:
                    self._clear_display()
            except Exception as e:
                logger.error("AgpIEMC Data fetch error: {}".format(str(e)), exc_info=True)
                self._clear_display()

    def fetch_tmdb_data(self, title, year, movie_path):
        try:
            api_key = api_key_manager.get_api_key('tmdb')
            if not api_key:
                return None
            search_kind = "tv" if is_emc_episode(movie_path) else "multi"
            search_url = "https://api.themoviedb.org/3/search/{}?api_key={}&language={}&query={}".format(search_kind, api_key, lng, quoteEventName(title))
            if year and search_kind != "tv":
                search_url += "&year={}".format(year)
            with urlopen(search_url) as response:
                search_data = json_load(response)
            if not search_data.get("results"):
                return None
            result = self.select_best_result(search_data["results"], title, year)
            content_type = result.get("media_type") or ("tv" if search_kind == "tv" else "movie")
            if content_type not in ("movie", "tv"):
                content_type = "movie"
            content_id = result["id"]
            append_parts = ["credits"]
            if content_type == "movie":
                append_parts.append("release_dates")
            else:
                append_parts.append("content_ratings")
            details_url = "https://api.themoviedb.org/3/{}/{}?api_key={}&language={}&append_to_response={}".format(content_type, content_id, api_key, lng, ",".join(append_parts))
            with urlopen(details_url) as response:
                return json_load(response)
        except Exception as e:
            logger.error("AgpIEMC TMDB API error: {}".format(str(e)))
            return None

    def fetch_omdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('omdb')
            if not api_key:
                return None
            url = "http://www.omdbapi.com/?apikey={}&t={}&plot=full".format(api_key, quoteEventName(title))
            if year:
                url += "&y={}".format(year)
            with urlopen(url) as response:
                return json_load(response)
        except Exception as e:
            logger.error("AgpIEMC OMDB API error: {}".format(str(e)))
            return None

    def select_best_result(self, results, original_title, year=None):
        target = str(original_title or "").strip().lower()
        scored = []
        for result in results:
            media_type = result.get('media_type', '')
            if media_type and media_type not in ('movie', 'tv'):
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
            if year:
                if result_year == str(year):
                    score += 600
                elif result_year:
                    score -= 500
            try:
                score += min(float(result.get('popularity', 0)), 10)
            except Exception:
                pass
            scored.append((result, score))
        if not scored:
            return results[0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def process_data(self, data):
        try:
            title = (data.get('title') or data.get('name') or data.get('Title') or "").strip()
            year = ""
            value = data.get('release_date') or data.get('first_air_date') or data.get('Year') or ""
            if value:
                year = str(value).split('-')[0].strip()
            runtime = data.get('runtime') or data.get('Runtime') or ""
            runtime_text = "%s min" % runtime if isinstance(runtime, int) and runtime > 0 else str(runtime).strip()
            genres = ""
            if data.get('genres'):
                names = [x.get("name", "").strip() for x in data.get('genres', []) if x.get("name", "").strip()]
                genres = " • ".join(names[:3])
            elif data.get('Genre'):
                genres = " • ".join([x.strip() for x in str(data.get('Genre')).split(',') if x.strip()][:3])
            rating = ""
            tmdb_rating = data.get('vote_average')
            imdb_rating = data.get('imdbRating')
            try:
                if tmdb_rating not in (None, "", 0, "0"):
                    rating = "IMDb %s/10" % round(float(tmdb_rating), 1)
            except Exception:
                pass
            try:
                if not rating and imdb_rating not in (None, "", "N/A"):
                    rating = "IMDb %s/10" % round(float(imdb_rating), 1)
            except Exception:
                pass
            overview = (data.get('overview') or data.get('Plot') or "").strip()
            lines = []
            if title:
                lines.append("%s (%s)" % (title, year) if year else title)
            if genres:
                lines.append(genres)
            meta = []
            if rating:
                meta.append(rating)
            if runtime_text:
                meta.append(runtime_text)
            if meta:
                lines.append("   ".join(meta))
            if overview:
                lines.append("")
                lines.append(overview)
            new_text = "\n".join(lines).strip()
            if not new_text:
                self._clear_display()
                return
            self.text = new_text
            self.timer.start(100, True)
        except Exception as e:
            logger.error("AgpIEMC process_data error: {}".format(str(e)))
            self._clear_display()

    def delayed_update(self):
        if self.instance:
            self.instance.setText(self.text)
            if self.text:
                self.instance.show()
            else:
                self.instance.hide()
