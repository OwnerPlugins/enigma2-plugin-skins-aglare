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


class AgpInfoEvents(Renderer, VariableText):
    GUI_WIDGET = eLabel

    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)
        self.current_request = None
        self.current_request_key = None
        self.last_event = None
        self.last_prefetch_key = None
        self.lock = Lock()
        self.text = ""
        self.nxts = 0
        self.canal = [None] * 6
        self.oldCanal = None

        self.adsl = True

        self.storage_path = IMOVIE_FOLDER
        self.timer = eTimer()
        self.timer.callback.append(self.delayed_update)
        logger.info("AgpInfoEvents Renderer initialized")

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

    def get_labels(self):
        return {
            'title': _('Title'),
            'year': _('Year'),
            'rating': _('Rating'),
            'genre': _('Genre'),
            'director': _('Director'),
            'writer': _('Writer'),
            'cast': _('Cast'),
            'country': _('Country'),
            'awards': _('Awards'),
            'runtime': _('Runtime'),
            'plot': _('Plot'),
            'offline': _('Offline mode')
        }

    def get_search_title(self, title, shortdesc="", fulldesc=""):
        try:
            result = build_search_title(title or "", shortdesc or "", fulldesc or "")
            return smart_capitalize_title(result)
        except Exception:
            return smart_capitalize_title(clean_search_title(title or ""))

    def _clear_display(self):
        self.text = ""
        try:
            if self.timer.isActive():
                self.timer.stop()
        except Exception:
            pass
        if self.instance:
            self.instance.hide()

    def changed(self, what):
        if what is None or not self.adsl or DATA_SOURCE == "off":
            self._clear_display()
            return

        if what[0] == self.CHANGED_CLEAR:
            self.oldCanal = None
            self.current_request_key = None
            self.last_prefetch_key = None
            self._clear_display()
            return self.text

        source = self.source
        source_type = type(source)
        service = None
        servicetype = None

        try:
            if source_type is ServiceEvent:
                service = source.getCurrentService()
                servicetype = "ServiceEvent"
            elif source_type is CurrentService:
                service = source.getCurrentServiceRef()
                servicetype = "CurrentService"
            elif source_type is EventInfo:
                service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                servicetype = "EventInfo"
            elif source_type is Event:
                servicetype = "Event"

                # For direct Event source, use the actual event object.
                # This avoids stale NavigationInstance / EPG lookup during zap.
                if getattr(source, "event", None) is not None and not self.nxts:
                    event = source.event
                    self.canal = [None] * 6
                    self.canal[1] = event.getBeginTime()
                    self.canal[2] = event.getEventName()
                    self.canal[3] = event.getExtendedDescription()
                    self.canal[4] = event.getShortDescription()
                    self.canal[5] = event.getEventName()
                    service = None
                else:
                    # Only use service lookup when nexts is requested.
                    service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
            else:
                servicetype = None

            if service is not None:
                service_str = service.toString()
                events = epgcache.lookupEvent(['IBDCTESX', (service_str, 0, -1, -1)])
                logger.info("AgpInfoEvents event list | nexts='{}' | events_count='{}'".format(
                    str(self.nxts), str(len(events) if events else 0)
                ))
                if not events or len(events) <= self.nxts:
                    self.current_request_key = None
                    self._clear_display()
                    return

                service_name = ServiceReference(service).getServiceName().replace('\xc2\x86', '').replace('\xc2\x87', '')
                self.canal = [None] * 6
                self.canal[0] = service_name
                self.canal[1] = events[self.nxts][1]
                self.canal[2] = events[self.nxts][4]
                self.canal[3] = events[self.nxts][5]
                self.canal[4] = events[self.nxts][6]
                self.canal[5] = self.canal[2]

            if not servicetype or not self.canal[5]:
                self.current_request_key = None
                self._clear_display()
                return

            curCanal = "%s-%s-%s" % (self.nxts, self.canal[1], self.canal[2])
            if curCanal == self.oldCanal:
                return

            self.oldCanal = curCanal
            self.evnt = self.canal[2]
            self._clear_display()
            logger.info("AgpInfoEvents selected event | nexts='{}' | title='{}'".format(
                str(self.nxts), self.evnt
            ))
            self.start_data_fetch()

        except Exception as e:
            logger.error("AgpInfoEvents changed error: {}".format(str(e)), exc_info=True)
            self.current_request_key = None
            self._clear_display()

    def start_data_fetch(self):
        request_key = "%s-%s-%s" % (
            self.nxts,
            self.canal[1] if self.canal and len(self.canal) > 1 else "",
            self.canal[2] if self.canal and len(self.canal) > 2 else getattr(self, "evnt", "")
        )

        if getattr(self, "current_request_key", None) == request_key:
            if self.current_request and self.current_request.is_alive():
                return

        self.current_request_key = request_key
        self.current_request = Thread(target=self.fetch_event_data, args=(request_key,))
        self.current_request.daemon = True
        self.current_request.start()

    def fetch_event_data(self, request_key=None):
        if DATA_SOURCE == "off":
            return

        with self.lock:
            try:
                if request_key is not None and request_key != self.current_request_key:
                    return

                data = None
                clean_title = self.get_search_title(self.canal[5], self.canal[4], self.canal[3])
                skip_title, skip_word = should_skip_title(clean_title)
                if skip_title:
                    logger.info("AgpInfoEvents skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                        getattr(self, "evnt", self.canal[2]), clean_title, skip_word
                    ))
                    self.current_request_key = None
                    self._clear_display()
                    return

                json_file = join(self.storage_path, "{}.json".format(clean_title))
                year = self.extract_year_from_canal()

                if exists(json_file) and getsize(json_file) > 0:
                    with open(json_file, "r") as f:
                        data = json_load(f)
                    logger.info("AgpInfoEvents loaded cached json | file='{}' | title='{}' | vote='{}' | has_release_dates='{}' | has_content_ratings='{}' | rated='{}'".format(
                        json_file,
                        clean_title,
                        str(data.get('vote_average', data.get('imdbRating', ''))),
                        str('release_dates' in data),
                        str('content_ratings' in data),
                        str(data.get('Rated', ''))
                    ))
                else:
                    if DATA_SOURCE == "tmdb" or (DATA_SOURCE == "auto" and api_key_manager.get_api_key('tmdb')):
                        data = self.fetch_tmdb_data(clean_title, year)
                    else:
                        data = self.fetch_omdb_data(clean_title, year)

                    if data:
                        with open(json_file, "w") as f:
                            json_dump(data, f, indent=2)
                        logger.info("AgpInfoEvents saved json | file='{}' | title='{}' | has_vote='{}' | vote='{}' | has_release_dates='{}' | has_content_ratings='{}' | rated='{}'".format(
                            json_file,
                            clean_title,
                            str('vote_average' in data or 'imdbRating' in data),
                            str(data.get('vote_average', data.get('imdbRating', ''))),
                            str('release_dates' in data),
                            str('content_ratings' in data),
                            str(data.get('Rated', ''))
                        ))

                if request_key is not None and request_key != self.current_request_key:
                    return

                if data:
                    self.process_data(data, request_key=request_key)
                else:
                    logger.info("AgpInfoEvents no data found | title='{}'".format(clean_title))
                    self.current_request_key = None
                    self._clear_display()

                if self.nxts == 0 and request_key == self.current_request_key:
                    self.prefetch_next_event_json()

            except Exception as e:
                logger.error("AgpInfoEvents Data fetch error: {}".format(str(e)), exc_info=True)
                self.current_request_key = None
                self._clear_display()

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

    def prefetch_next_event_json(self):
        try:
            service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
            if service is None:
                return

            service_str = service.toString()
            events = epgcache.lookupEvent(['IBDCTESX', (service_str, 0, -1, -1)])
            if not events or len(events) <= 1:
                return

            next_title_raw = events[1][4]
            if not next_title_raw:
                return

            clean_title = self.get_search_title(next_title_raw, events[1][6], events[1][5])
            skip_title, skip_word = should_skip_title(clean_title)
            if skip_title:
                logger.info("AgpInfoEvents prefetch skipping NEXT | original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                    next_title_raw, clean_title, skip_word
                ))
                return

            json_file = join(self.storage_path, "{}.json".format(clean_title))
            if exists(json_file) and getsize(json_file) > 0:
                logger.info("AgpInfoEvents prefetch NEXT already cached | file='{}'".format(json_file))
                return

            desc = "{}\n{}\n{}".format(events[1][4], events[1][6], events[1][5])
            years = findall(r'\b\d{4}\b', desc)
            year = None
            if years:
                valid_years = [y for y in years if 1900 <= int(y) <= 2100]
                if valid_years:
                    year = max(valid_years)

            prefetch_key = "{}::{}".format(self.canal[2] if self.canal and len(self.canal) > 2 else "", clean_title)
            if prefetch_key == self.last_prefetch_key:
                return
            self.last_prefetch_key = prefetch_key

            logger.info("AgpInfoEvents prefetch NEXT start | original='{}' | final_search_title='{}' | file='{}'".format(
                next_title_raw, clean_title, json_file
            ))

            if DATA_SOURCE == "tmdb" or (DATA_SOURCE == "auto" and api_key_manager.get_api_key('tmdb')):
                data = self.fetch_tmdb_data(clean_title, year)
            else:
                data = self.fetch_omdb_data(clean_title, year)

            if data:
                with open(json_file, "w") as f:
                    json_dump(data, f, indent=2)
                logger.info("AgpInfoEvents prefetch NEXT saved json | file='{}' | title='{}' | vote='{}'".format(
                    json_file, clean_title, str(data.get('vote_average', data.get('imdbRating', '')))
                ))

        except Exception as e:
            logger.error("AgpInfoEvents prefetch NEXT error: {}".format(str(e)), exc_info=True)

    def fetch_tmdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('tmdb')
            search_url = (
                "https://api.themoviedb.org/3/search/multi?api_key=" + api_key +
                "&language=" + lng +
                "&query=" + quoteEventName(title) +
                ("&year=" + str(year) if year else "")
            )
            logger.info("AgpInfoEvents TMDB search link | url={}".format(search_url))
            with urlopen(search_url) as response:
                search_data = json_load(response)

            if not search_data.get("results"):
                return None

            result = self.select_best_result(search_data["results"], title)
            content_type = result["media_type"]
            content_id = result["id"]

            details_url = (
                "https://api.themoviedb.org/3/" +
                content_type +
                "/" +
                str(content_id) +
                "?api_key=" +
                api_key +
                "&language=" +
                lng +
                "&append_to_response=credits"
            )
            logger.info("AgpInfoEvents TMDB details link | url={}".format(details_url))
            with urlopen(details_url) as response:
                return json_load(response)

        except Exception as e:
            logger.error("AgpInfoEvents TMDB API error: {}".format(str(e)))
            return None

    def fetch_omdb_data(self, title, year):
        try:
            api_key = api_key_manager.get_api_key('omdb')
            params = "t={}{}&plot=full".format(
                quoteEventName(title),
                "&y={}".format(year) if year else ""
            )
            url = "http://www.omdbapi.com/?apikey={}&{}".format(api_key, params)
            logger.info("AgpInfoEvents OMDB request link | url={}".format(url))
            with urlopen(url) as response:
                return json_load(response)
        except Exception as e:
            logger.error("AgpInfoEvents OMDB API error: {}".format(str(e)))
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

            if year:
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

    def process_data(self, data, request_key=None):
        info_lines = []

        try:
            if request_key is not None and request_key != self.current_request_key:
                return

            if 'title' in data or 'name' in data:
                info_lines.append("{}: {}".format(_('Title'), data.get('title', data.get('name'))))

                if data.get('release_date'):
                    year = data['release_date'].split('-')[0]
                    info_lines.append("{}: {}".format(_('Year'), year))

                if data.get('vote_average'):
                    info_lines.append("{}: {}/10".format(_('Rating'), data['vote_average']))

                if data.get('genres'):
                    genres = ", ".join([g['name'] for g in data['genres']])
                    info_lines.append("{}: {}".format(_('Genre'), genres))

                if data.get('credits'):
                    crew = data['credits'].get('crew', [])
                    directors = [m['name'] for m in crew if m.get('job') == 'Director']
                    writers = [m['name'] for m in crew if m.get('department') == 'Writing']

                    if directors:
                        info_lines.append("{}: {}".format(_('Director'), ', '.join(directors)))
                    if writers:
                        info_lines.append("{}: {}".format(_('Writer'), ', '.join(writers)))

                if data.get('production_countries'):
                    countries = ", ".join([c['name'] for c in data['production_countries']])
                    info_lines.append("{}: {}".format(_('Country'), countries))
            else:
                info_lines.append("{}: {}".format(_('Title'), data.get('Title')))
                info_lines.append("{}: {}".format(_('Year'), data.get('Year')))
                info_lines.append("{}: {}".format(_('Rating'), data.get('imdbRating')))
                info_lines.append("{}: {}".format(_('Genre'), data.get('Genre')))
                info_lines.append("{}: {}".format(_('Director'), data.get('Director')))
                info_lines.append("{}: {}".format(_('Writer'), data.get('Writer')))
                info_lines.append("{}: {}".format(_('Cast'), data.get('Actors')))
                info_lines.append("{}: {}".format(_('Country'), data.get('Country')))

            runtime = data.get('runtime') or data.get('Runtime')
            if runtime:
                info_lines.append("{}: {}".format(_('Runtime'), runtime))

            plot = data.get('overview') or data.get('Plot')
            if plot:
                info_lines.append("\n{}: {}".format(_('Plot'), plot))

            new_text = "\n".join([line for line in info_lines if line]).strip()
            if not new_text:
                self.current_request_key = None
                self._clear_display()
                return

            if new_text == self.text:
                self.current_request_key = None
                return

            self.text = new_text
            self.current_request_key = None
            self.timer.start(100, True)

        except Exception as e:
            logger.error("AgpInfoEvents Data processing error: {}".format(str(e)))
            self.current_request_key = None
            self._clear_display()

    def delayed_update(self):
        if self.instance:
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
        except Exception as e:
            logger.warning("AgpInfoEvents Year extraction failed: {}".format(str(e)))
            return None

    def onHide(self):
        try:
            if hasattr(self, 'timer') and self.timer:
                self.timer.stop()
        except Exception:
            pass

    def onShow(self):
        pass
