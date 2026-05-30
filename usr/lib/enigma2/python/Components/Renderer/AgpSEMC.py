#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__author__ = "Lululla"         ##
# #__copyright__ = "AGP Team"     ##
# #__created_by__ = "MNASR"       ##
# ##################################
from __future__ import absolute_import, print_function

from json import load as json_load
from os import makedirs
from os.path import exists, getsize
from threading import Lock

from Components.Renderer.Renderer import Renderer
from Components.VariableValue import VariableValue
from enigma import eSlider, eWidget, ePoint, eSize, loadPNG, eTimer, eServiceCenter
from Components.config import config
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

# from .Agp_Utils import logger
from .AgpEMCBase import EMC_ROOT, EMC_INFO_FOLDER, ensure_emc_dirs, build_emc_search_title, is_video_file


class AgpSEMC(VariableValue, Renderer):
    GUI_WIDGET = eWidget
    sources = ["Service", "ServiceEvent"]

    def __init__(self):
        Renderer.__init__(self)
        VariableValue.__init__(self)

        self.lock = Lock()
        self.__start = 0
        self.__end = 100
        self.star = None
        self.pxmp = None
        self.szX = 200
        self.szY = 20
        self.storage_path = EMC_INFO_FOLDER
        self.pending_info_file = ""
        self.pending_title = ""
        self.retry_count = 0
        self.max_retries = 6
        self.retry_interval_ms = 5000
        self.current_key = None

        self._json_timer = eTimer()
        self._json_timer.callback.append(self._retry_json_read)

        ensure_emc_dirs(EMC_ROOT)

    def _get_skin_star_background(self):
        try:
            skin_value = config.skin.primary_skin.value
            skin_folder = str(skin_value).replace('/skin.xml', '').strip('/')
            return "/usr/share/enigma2/{}/xtra/star_back.png".format(skin_folder)
        except Exception:
            return "/usr/share/enigma2/Aglare-FHD/xtra/star_back.png"

    def _get_skin_filled_pixmap(self):
        try:
            if self.pxmp:
                if str(self.pxmp).startswith("/"):
                    return self.pxmp
                skin_value = config.skin.primary_skin.value
                skin_folder = str(skin_value).replace('/skin.xml', '').strip('/')
                return "/usr/share/enigma2/{}/{}".format(skin_folder, str(self.pxmp).lstrip("/"))
        except Exception:
            pass
        try:
            skin_value = config.skin.primary_skin.value
            skin_folder = str(skin_value).replace('/skin.xml', '').strip('/')
            return "/usr/share/enigma2/{}/xtra/star.png".format(skin_folder)
        except Exception:
            return "/usr/share/enigma2/Aglare-FHD/xtra/star.png"

    def _hide_star(self):
        try:
            if self.star:
                self.star.hide()
            if self.instance:
                self.instance.hide()
        except Exception:
            pass

    def _reset_star(self):
        try:
            if self.star:
                self.star.setRange(0, 100)
                self.star.setValue(0)
                self.star.hide()
            if self.instance:
                self.instance.hide()
        except Exception:
            pass

    def applySkin(self, desktop, screen):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == 'size':
                self.szX = int(value.split(',')[0])
                self.szY = int(value.split(',')[1])
                attribs.append((attrib, value))
            elif attrib == 'pixmap':
                self.pxmp = value
            elif attrib == 'path':
                self.storage_path = str(value)
                if not exists(self.storage_path):
                    makedirs(self.storage_path, exist_ok=True)
            elif attrib == 'alphatest':
                pass
            else:
                attribs.append((attrib, value))

        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, screen)

    def GUIcreate(self, parent):
        self.instance = eWidget(parent)
        self.star = eSlider(self.instance)

    def changed(self, what):
        if what and what[0] == self.CHANGED_CLEAR:
            if self._json_timer.isActive():
                self._json_timer.stop()
            self.current_key = None
            self.pending_info_file = ""
            self.pending_title = ""
            self._reset_star()
            return
        self.infos()

    def infos(self):
        source = self.source
        service = None
        movie_path = None
        service_handler = eServiceCenter.getInstance()

        try:
            if hasattr(source, "__class__"):
                class_name = source.__class__.__name__

                if class_name == "EMCServiceEvent":
                    service = getattr(source, "service", None)
                    if service:
                        try:
                            movie_path = service.getPath()
                        except Exception:
                            movie_path = None

                elif class_name == "EMCCurrentService":
                    try:
                        service = source.getCurrentService()
                    except Exception:
                        service = None
                    if service:
                        try:
                            movie_path = service.getPath()
                        except Exception:
                            movie_path = None

            if not movie_path:
                if isinstance(source, ServiceEvent):
                    service = source.getCurrentService()
                    movie_path = service.getPath() if service else None
                elif isinstance(source, CurrentService):
                    service = source.getCurrentServiceRef()
                    movie_path = service.getPath() if service else None
                elif isinstance(source, EventInfo):
                    service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                    movie_path = service.getPath() if service else None

            if not movie_path:
                service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                if service:
                    info = service_handler.info(service)
                    if info:
                        movie_path = service.getPath()

            if not movie_path or not is_video_file(movie_path):
                self._hide_star()
                return

            if movie_path == self.current_key:
                return

            self.current_key = movie_path
            self._reset_star()

            self.pending_title = build_emc_search_title(movie_path)
            base = self.storage_path if str(self.storage_path).endswith("/") else str(self.storage_path) + "/"
            self.pending_info_file = "{}{}.json".format(base, self.pending_title)
            self.retry_count = 0
            self._start_json_retry()

        except Exception:
            self._hide_star()

    def _start_json_retry(self):
        if self._json_timer.isActive():
            self._json_timer.stop()
        self._json_timer.start(100, True)

    def _retry_json_read(self):
        try:
            if not self.instance or not self.star:
                return

            if exists(self.pending_info_file) and getsize(self.pending_info_file) > 0:
                with open(self.pending_info_file, "r") as f:
                    data = json_load(f)
                self.process_data(data)
                return

            self._hide_star()
            self.retry_count += 1
            if self.retry_count < self.max_retries:
                self._json_timer.start(self.retry_interval_ms, True)
            else:
                self._hide_star()

        except Exception:
            self._hide_star()

    def process_data(self, data):
        try:
            rating = data.get('vote_average', 0)
            if not rating and data.get('imdbRating') not in (None, '', 'N/A'):
                try:
                    rating = float(data.get('imdbRating'))
                except Exception:
                    rating = 0

            try:
                rtng = min(int(float(rating) * 10), 100) if rating else 0
            except Exception:
                rtng = 0

            if rtng <= 0:
                self._hide_star()
                return

            filled_pix = self._get_skin_filled_pixmap()
            background_pix = self._get_skin_star_background()

            with self.lock:
                self.star.move(ePoint(0, 0))
                self.star.resize(eSize(self.szX, self.szY))

                # OpenViX eSlider may not implement setAlphatest().
                # This is optional, so skip it when unavailable.
                if hasattr(self.star, "setAlphatest"):
                    try:
                        self.star.setAlphatest(2)
                    except Exception:
                        pass

                self.star.setRange(0, 100)
                self.star.setPixmap(loadPNG(filled_pix))
                self.star.setBackgroundPixmap(loadPNG(background_pix))
                self.star.setValue(rtng)
                self.star.show()
                self.instance.resize(eSize(self.szX, self.szY))
                self.instance.show()

        except Exception:
            self._hide_star()

    def postWidgetCreate(self, instance):
        if self.star is not None:
            self.star.setRange(self.__start, self.__end)
