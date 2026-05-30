#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__author__ = "Lululla"         ##
# #__copyright__ = "AGP Team"     ##
# #__created_by__ = "MNASR"       ##
# ##################################
from __future__ import absolute_import, print_function
from os import makedirs
from os.path import join, exists, getsize
from threading import Thread, Lock
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

from enigma import ePixmap, loadPNG, eTimer, eServiceCenter
from Components.Renderer.Renderer import Renderer
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from Plugins.Extensions.Aglare.api_config import ApiKeyManager
from Components.Renderer.AglDownloadThread import AglDownloadThread

from .Agp_Utils import logger
from .AgpEMCBase import EMC_ROOT, EMC_LOGO_FOLDER, ensure_emc_dirs, build_emc_search_title, extract_emc_year, extract_emc_episode_marker, is_emc_episode, is_video_file

lemc_queue = Queue()
api_key_manager = ApiKeyManager()


class AgpLEMC(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.storage_path = EMC_LOGO_FOLDER
        self.release_year = None
        self.logo_path = ""
        self.retry_count = 0
        self._timer = eTimer()
        self._timer.callback.append(self._retryLogo)
        ensure_emc_dirs(EMC_ROOT)

    def applySkin(self, desktop, parent):
        super().applySkin(desktop, parent)
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
            if movie_path and is_video_file(movie_path):
                self._process_movie_path(movie_path)
            else:
                self.instance.hide()
        except Exception as e:
            logger.error("AgpLEMC Render Error: {}".format(str(e)))
            self.instance.hide()

    def _process_movie_path(self, movie_path):
        clean_title = build_emc_search_title(movie_path)
        if not clean_title:
            self.instance.hide()
            return

        is_episode = is_emc_episode(movie_path)

        # For TV episodes, do not pass a movie year. It can bias TMDB toward movies.
        self.release_year = "" if is_episode else extract_emc_year(movie_path)

        logo_path = join(self.storage_path, "%s.png" % clean_title)
        if _validate_logo(logo_path):
            self.waitLogo(logo_path)
        else:
            self._queue_for_download(clean_title, clean_title, logo_path, is_episode, movie_path)

    def _queue_for_download(self, search_title, clean_title, logo_path, is_episode=False, movie_path=""):
        if not AgpDBlemc or not AgpDBlemc.is_alive():
            return
        lemc_queue.put((search_title, clean_title, logo_path, self.release_year, is_episode, movie_path))
        self.runLogoThread(logo_path)

    def runLogoThread(self, logo_path):
        Thread(target=self.waitLogo, args=(logo_path,), daemon=True).start()

    def display_logo(self, path=None):
        if self.instance and path and _validate_logo(path):
            self.instance.setPixmap(loadPNG(path))
            self.instance.setScale(1)
            self.instance.show()
            self.instance.invalidate()
            self.instance.show()
        elif self.instance:
            self.instance.hide()

    def waitLogo(self, path=None):
        if not self.instance or not path:
            return
        self.logo_path = path
        self.retry_count = 0
        if self._timer.isActive():
            self._timer.stop()
        self._timer.start(100, True)

    def _retryLogo(self):
        if _validate_logo(self.logo_path):
            self.display_logo(self.logo_path)
            return
        self.retry_count += 1
        if self.retry_count < 5:
            self._timer.start(500 + self.retry_count * 200, True)
        else:
            self.instance.hide()


class LogoDBLEMC(AglDownloadThread):
    def __init__(self):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.queued = set()
        self.lock = Lock()

    def run(self):
        while True:
            item = lemc_queue.get()
            self.executor.submit(self._process_item, item)
            lemc_queue.task_done()

    def _process_item(self, item):
        if len(item) == 6:
            search_title, clean_title, logo_path, release_year, is_episode, movie_path = item
        elif len(item) == 5:
            search_title, clean_title, logo_path, release_year, is_episode = item
            movie_path = ""
        else:
            search_title, clean_title, logo_path, release_year = item
            is_episode = False
            movie_path = ""

        with self.lock:
            if search_title in self.queued:
                return
            self.queued.add(search_title)
        try:
            if exists(logo_path) and getsize(logo_path) > 100:
                return
            api_key = api_key_manager.get_api_key("tmdb")
            if not api_key:
                return
            episode_shortdesc = ""
            episode_fulldesc = ""
            if is_episode:
                episode_shortdesc, episode_fulldesc = extract_emc_episode_marker(movie_path)

            shortdesc = episode_shortdesc if is_episode else None
            fulldesc = episode_fulldesc if is_episode else None
            search_year = None if is_episode else release_year

            logger.info("AgpLEMC provider hint | title='{}' | is_episode='{}' | shortdesc='{}' | fulldesc='{}'".format(
                search_title, str(is_episode), str(shortdesc), str(fulldesc)
            ))

            self.search_tmdb_logo(
                dwn_logo=logo_path,
                title=search_title,
                shortdesc=shortdesc,
                fulldesc=fulldesc,
                year=search_year,
                channel=clean_title,
                api_key=api_key
            )
        finally:
            with self.lock:
                self.queued.discard(search_title)


def _validate_logo(path):
    return exists(path) and getsize(path) > 100


db_lock = Lock()
AgpDBlemc = None
with db_lock:
    if AgpDBlemc is None or not AgpDBlemc.is_alive():
        AgpDBlemc = LogoDBLEMC()
        AgpDBlemc.daemon = True
        AgpDBlemc.start()
