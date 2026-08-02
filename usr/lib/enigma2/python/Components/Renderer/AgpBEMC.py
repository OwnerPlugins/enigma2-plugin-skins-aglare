#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
## __author__ = "Lululla"         ##
## __copyright__ = "AGP Team"     ##
## __created_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function

from os import makedirs
from os.path import join, exists, getsize
from threading import Thread, Lock
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

from enigma import ePixmap, loadJPG, eTimer, eServiceCenter
from Components.Renderer.Renderer import Renderer
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from Plugins.Extensions.Aglare.api_config import ApiKeyManager
from Components.Renderer.AgbDownloadThread import AgbDownloadThread

from .Agp_Utils import logger
from .AgpEMCBase import EMC_ROOT, EMC_BACKDROP_FOLDER, ensure_emc_dirs, build_emc_search_title, extract_emc_year, extract_emc_episode_marker, is_emc_episode, is_video_file

bemc_queue = Queue()
api_key_manager = ApiKeyManager()


class AgpBEMC(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.storage_path = EMC_BACKDROP_FOLDER
        self.release_year = None
        self.backdrop_path = ""
        self.retry_count = 0
        self._timer = eTimer()
        self._timer.callback.append(self._retryBackdrop)
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
            logger.error("AgpBEMC Render Error: {}".format(str(e)))
            self.instance.hide()

    def _process_movie_path(self, movie_path):
        clean_title = build_emc_search_title(movie_path)
        if not clean_title:
            self.instance.hide()
            return

        is_episode = is_emc_episode(movie_path)

        # For TV episodes, do not pass a movie year. It can bias TMDB toward
        # movies.
        self.release_year = "" if is_episode else extract_emc_year(movie_path)

        backdrop_path = join(self.storage_path, "%s.jpg" % clean_title)
        if _validate_backdrop(backdrop_path):
            self.waitBackdrop(backdrop_path)
        else:
            self._queue_for_download(
                clean_title,
                clean_title,
                backdrop_path,
                is_episode,
                movie_path)

    def _queue_for_download(
            self,
            search_title,
            clean_title,
            backdrop_path,
            is_episode=False,
            movie_path=""):
        if not AgpDBbemc or not AgpDBbemc.is_alive():
            return
        bemc_queue.put(
            (search_title,
             clean_title,
             backdrop_path,
             self.release_year,
             is_episode,
             movie_path))
        self.runBackdropThread(backdrop_path)

    def runBackdropThread(self, backdrop_path):
        Thread(
            target=self.waitBackdrop,
            args=(
                backdrop_path,
            ),
            daemon=True).start()

    def display_backdrop(self, path=None):
        if self.instance and path and _validate_backdrop(path):
            self.instance.setPixmap(loadJPG(path))
            self.instance.setScale(1)
            self.instance.show()
            self.instance.invalidate()
            self.instance.show()
        elif self.instance:
            self.instance.hide()

    def waitBackdrop(self, path=None):
        if not self.instance or not path:
            return
        self.backdrop_path = path
        self.retry_count = 0
        if self._timer.isActive():
            self._timer.stop()
        self._timer.start(100, True)

    def _retryBackdrop(self):
        if _validate_backdrop(self.backdrop_path):
            self.display_backdrop(self.backdrop_path)
            return
        self.retry_count += 1
        if self.retry_count < 5:
            self._timer.start(500 + self.retry_count * 200, True)
        else:
            self.instance.hide()


class BackdropDBBEMC(AgbDownloadThread):
    def __init__(self):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.providers = api_key_manager.get_active_providers()
        self.provider_engines = self.build_providers()
        self.queued = set()
        self.lock = Lock()

    def build_providers(self):
        provider_mapping = {
            "tmdb": (
                self.search_tmdb, 0), "fanart": (
                self.search_fanart, 1), "google": (
                self.search_google, 2)}
        return [(name, func, prio) for name, (func, prio)
                in provider_mapping.items() if self.providers.get(name, False)]

    def run(self):
        while True:
            item = bemc_queue.get()
            self.executor.submit(self._process_item, item)
            bemc_queue.task_done()

    def _process_item(self, item):
        if len(item) == 6:
            search_title, clean_title, backdrop_path, release_year, is_episode, movie_path = item
        elif len(item) == 5:
            search_title, clean_title, backdrop_path, release_year, is_episode = item
            movie_path = ""
        else:
            search_title, clean_title, backdrop_path, release_year = item
            is_episode = False
            movie_path = ""

        with self.lock:
            if search_title in self.queued:
                return
            self.queued.add(search_title)
        try:
            if exists(backdrop_path) and getsize(backdrop_path) > 1024:
                return
            for provider_name, provider_func, _ in sorted(
                    self.provider_engines, key=lambda x: x[2]):
                api_key = api_key_manager.get_api_key(provider_name)
                if not api_key:
                    continue
                try:
                    episode_shortdesc = ""
                    episode_fulldesc = ""
                    if is_episode:
                        episode_shortdesc, episode_fulldesc = extract_emc_episode_marker(
                            movie_path)

                    shortdesc = episode_shortdesc if is_episode else None
                    fulldesc = episode_fulldesc if is_episode else None
                    search_year = None if is_episode else release_year

                    logger.info(
                        "AgpBEMC provider hint | title='{}' | is_episode='{}' | shortdesc='{}' | fulldesc='{}'".format(
                            search_title, str(is_episode), str(shortdesc), str(fulldesc)))

                    result = provider_func(
                        dwn_backdrop=backdrop_path,
                        title=search_title,
                        shortdesc=shortdesc,
                        fulldesc=fulldesc,
                        year=search_year,
                        channel=clean_title,
                        api_key=api_key
                    )
                    if result and _validate_backdrop(backdrop_path):
                        break
                except Exception as e:
                    logger.error(
                        "AgpBEMC Error from %s: %s",
                        provider_name,
                        str(e))
        finally:
            with self.lock:
                self.queued.discard(search_title)


def _validate_backdrop(path):
    return exists(path) and getsize(path) > 100


db_lock = Lock()
AgpDBbemc = None
if any(api_key_manager.get_active_providers().values()):
    with db_lock:
        if AgpDBbemc is None or not AgpDBbemc.is_alive():
            AgpDBbemc = BackdropDBBEMC()
            AgpDBbemc.daemon = True
            AgpDBbemc.start()
