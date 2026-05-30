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
from os.path import exists, getsize, join
from threading import Thread
from urllib.request import urlopen

from enigma import ePixmap, loadJPG, eTimer, eServiceCenter
from Components.Renderer.Renderer import Renderer
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from .Agp_Utils import logger
from .AgpEMCBase import EMC_ROOT, EMC_INFO_FOLDER, EMC_CAST_FOLDER, ensure_emc_dirs, build_emc_search_title, is_video_file


class AgpCEMC(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.info_path = EMC_INFO_FOLDER
        self.cast_path = EMC_CAST_FOLDER
        self.cast_index = 0
        self.current_key = None
        self.current_image = ""
        self.current_json = ""
        self.retry_count = 0
        self.max_retries = 6
        self.retry_interval = 5000
        self.timer = eTimer()
        self.timer.callback.append(self._retry_show_or_reload)

        ensure_emc_dirs(EMC_ROOT)

    def applySkin(self, desktop, parent):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == "path":
                self.info_path = str(value)
                if not exists(self.info_path):
                    makedirs(self.info_path, exist_ok=True)
            elif attrib == "cast":
                try:
                    self.cast_index = int(value)
                except Exception:
                    self.cast_index = 0
            else:
                attribs.append((attrib, value))

        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, parent)

    def changed(self, what):
        if not self.instance:
            return

        if what and what[0] == self.CHANGED_CLEAR:
            self.current_key = None
            self.current_image = ""
            self.current_json = ""
            self.retry_count = 0
            if self.timer.isActive():
                self.timer.stop()
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
            self.instance.hide()

            title = build_emc_search_title(movie_path)
            self.current_json = join(self.info_path, "%s.json" % title)
            self.retry_count = 0

            self._load_or_retry()

        except Exception as e:
            logger.error("AgpCEMC error: {}".format(str(e)))
            self.instance.hide()

    def _safe_actor_filename(self, actor_name):
        try:
            name = str(actor_name or "").strip()
            if not name:
                return ""
            name = name.replace("/", "_")
            name = name.replace("\\", "_")
            name = name.replace(":", "_")
            name = name.replace("*", "_")
            name = name.replace("?", "")
            name = name.replace('"', "")
            name = name.replace("<", "")
            name = name.replace(">", "")
            name = name.replace("|", "_")
            name = name.replace("'", "")
            name = " ".join(name.split())
            return name
        except Exception:
            return ""

    def _load_or_retry(self):
        try:
            if not exists(
                    self.current_json) or getsize(
                    self.current_json) <= 0:
                self._retry_later()
                return

            with open(self.current_json, "r") as f:
                data = json_load(f)

            cast_list = (((data.get("credits") or {}).get("cast")) or [])
            if len(cast_list) <= self.cast_index:
                self._retry_later()
                return

            cast_item = cast_list[self.cast_index]
            profile_path = str(cast_item.get("profile_path") or "").strip()
            if not profile_path:
                self._retry_later()
                return

            actor_name = str(cast_item.get("name") or "").strip()
            safe_actor = self._safe_actor_filename(actor_name)
            if not safe_actor:
                self._retry_later()
                return

            self.current_image = join(self.cast_path, "%s.jpg" % safe_actor)

            if exists(
                    self.current_image) and getsize(
                    self.current_image) > 1000:
                self._show_image(self.current_image)
                return

            image_url = "https://image.tmdb.org/t/p/w185%s" % profile_path
            Thread(
                target=self._download_image,
                args=(
                    image_url,
                    self.current_image),
                daemon=True).start()

        except Exception as e:
            logger.error("AgpCEMC load error: {}".format(str(e)))
            self._retry_later()

    def _retry_later(self):
        self.retry_count += 1
        if self.retry_count < self.max_retries:
            if self.timer.isActive():
                self.timer.stop()
            self.timer.start(self.retry_interval, True)
        else:
            self.instance.hide()

    def _retry_show_or_reload(self):
        self._load_or_retry()

    def _download_image(self, url, image_file):
        try:
            data = urlopen(url, timeout=10).read()
            with open(image_file, "wb") as f:
                f.write(data)
            self.retry_count = 0
            self.timer.start(100, True)
        except Exception as e:
            logger.error("AgpCEMC image download error: {}".format(str(e)))
            self._retry_later()

    def _show_image(self, image_file):
        try:
            if exists(image_file) and getsize(image_file) > 1000:
                self.instance.setPixmap(loadJPG(image_file))
                self.instance.setScale(1)
                self.instance.show()
            else:
                self.instance.hide()
        except Exception:
            self.instance.hide()
