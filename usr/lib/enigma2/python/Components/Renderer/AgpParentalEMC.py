#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
## __author__ = "Lululla"         ##
## __copyright__ = "AGP Team"     ##
## __created_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function
from json import load as json_load
from os import makedirs
from os.path import join, exists, getsize

from Components.Renderer.Renderer import Renderer
from enigma import ePixmap, loadPNG, eTimer, eServiceCenter
from Components.config import config
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from .Agp_Utils import logger
from .AgpEMCBase import EMC_ROOT, EMC_INFO_FOLDER, ensure_emc_dirs, build_emc_search_title, is_video_file

cur_skin = config.skin.primary_skin.value.replace('/skin.xml', '')
PARENTAL_ICON_PATH = '/usr/share/enigma2/{}/parental/'.format(cur_skin)

DEFAULT_RATING = 'UN'
NA_RATING = 'NA'
DEFAULT_ICON = 'FSK_UN.png'

RATING_MAP = {
    'TV-Y': '6', 'TV-Y7': '6', 'TV-G': '0', 'TV-PG': '16',
    'TV-14': '16', 'TV-MA': '18',
    'G': '0', 'PG': '12', 'PG-13': '16', 'R': '18',
    'NC-17': '18',
    'PEGI-12': '12', 'PEGI-16': '16', 'PEGI-18': '18',
    'FSK 0': '0', 'FSK 6': '6', 'FSK 12': '12', 'FSK 16': '16', 'FSK 18': '18',
    '0': '0', '6': '6', '12': '12', '16': '16', '18': '18',
    '': DEFAULT_RATING, 'NA': NA_RATING,
    'NOT RATED': NA_RATING, 'UNRATED': NA_RATING, 'UN': DEFAULT_RATING
}


class AgpParentalEMC(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.storage_path = EMC_INFO_FOLDER
        self.current_key = None
        self.current_json = ""
        self.retry_count = 0
        self.max_retries = 6
        self.retry_interval_ms = 5000
        self._json_timer = eTimer()
        self._json_timer.callback.append(self._retry_json_read)
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

        if what and what[0] == self.CHANGED_CLEAR:
            self.current_key = None
            self.current_json = ""
            self.retry_count = 0
            if self._json_timer.isActive():
                self._json_timer.stop()
            self.instance.hide()
            return

        source = self.source
        service_ref = None
        movie_path = None
        service_handler = eServiceCenter.getInstance()

        try:
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
                self.instance.hide()
                return

            if movie_path == self.current_key:
                return

            self.current_key = movie_path
            title = build_emc_search_title(movie_path)
            self.current_json = join(self.storage_path, "%s.json" % title)
            self.retry_count = 0
            self._start_json_retry()

        except Exception as e:
            logger.error("AgpParentalEMC changed error: {}".format(str(e)))
            self.instance.hide()

    def _start_json_retry(self):
        if self._json_timer.isActive():
            self._json_timer.stop()
        self._json_timer.start(100, True)

    def _retry_json_read(self):
        try:
            if exists(self.current_json) and getsize(self.current_json) > 0:
                with open(self.current_json, "r") as f:
                    data = json_load(f)
                self.process_data(data)
                return

            self.retry_count += 1
            if self.retry_count < self.max_retries:
                self._json_timer.start(self.retry_interval_ms, True)
            else:
                self.instance.hide()

        except Exception as e:
            logger.error("AgpParentalEMC retry error: {}".format(str(e)))
            self.instance.hide()

    def _extract_parental(self, data):
        # 1) already normalized field
        for key in ("Rated", "rated", "certification", "Certification"):
            value = str(data.get(key, "") or "").strip().upper()
            if value:
                return value

        # 2) TMDB movie release_dates
        release_dates = (
            ((data.get("release_dates") or {}).get("results")) or [])
        for entry in release_dates:
            if entry.get("iso_3166_1") == "US":
                for rd in entry.get("release_dates", []):
                    cert = str(
                        rd.get(
                            "certification",
                            "") or "").strip().upper()
                    if cert:
                        return cert

        # 3) TMDB tv content_ratings
        content_ratings = (
            ((data.get("content_ratings") or {}).get("results")) or [])
        for entry in content_ratings:
            if entry.get("iso_3166_1") == "US":
                cert = str(entry.get("rating", "") or "").strip().upper()
                if cert:
                    return cert

        return ""

    def process_data(self, data):
        try:
            rated = self._extract_parental(data)
            rating_code = RATING_MAP.get(rated, DEFAULT_RATING)
            icon_file = "FSK_" + rating_code + ".png"
            icon_path = join(PARENTAL_ICON_PATH, icon_file)

            if not exists(icon_path):
                icon_path = join(PARENTAL_ICON_PATH, DEFAULT_ICON)

            if self.instance and exists(icon_path):
                self.instance.setPixmap(loadPNG(icon_path))
                self.instance.show()
            else:
                self.instance.hide()

        except Exception as e:
            logger.error(
                "AgpParentalEMC process_data error: {}".format(
                    str(e)))
            self.instance.hide()
