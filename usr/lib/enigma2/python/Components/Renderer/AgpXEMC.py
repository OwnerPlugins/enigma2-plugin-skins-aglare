#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
##__author__ = "Lululla"         ##
##__copyright__ = "AGP Team"     ##
##__modified_by__ = "MNASR"       ##
###################################
from __future__ import absolute_import, print_function
from datetime import datetime
from os import remove, makedirs
from os.path import join, exists, getsize, basename
from threading import Thread, Lock
from queue import LifoQueue
from concurrent.futures import ThreadPoolExecutor
from re import findall

from enigma import ePixmap, loadJPG, eTimer, eServiceCenter
from Components.Renderer.Renderer import Renderer
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance

from Plugins.Extensions.Aglare.api_config import cfg
from Plugins.Extensions.Aglare.api_config import ApiKeyManager
from Components.Renderer.AgpDownloadThread import AgpDownloadThread

from .Agp_Utils import IMOVIE_FOLDER, clean_for_tvdb, logger, create_secure_log_dir
from .Agp_lib import sanitize_filename

secure_log_dir = create_secure_log_dir()

if not IMOVIE_FOLDER.endswith("/"):
    IMOVIE_FOLDER += "/"

pdbemc = LifoQueue()
api_key_manager = ApiKeyManager()
extensions = ['.jpg']
PARENT_SOURCE = cfg.xemc_poster.value


class AgpXEMC(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self.storage_path = IMOVIE_FOLDER
        self.release_year = None
        self.log_file = join(secure_log_dir, "PosterDBEMC.log")
        clear_all_log()
        self.adsl = True
        self.poster_path = ""
        self.retry_count = 0

        if not cfg.xemc_poster.value:
            logger.debug("AgpXEMC Movie renderer disabled in configuration")
            self._log_info("AgpXEMC Movie renderer disabled in configuration")
            return

        self._poster_timer = eTimer()
        self._poster_timer.callback.append(self._retryPoster)
        self._log_info("AgpXEMC AGP Movie Renderer initialized")

    def applySkin(self, desktop, parent):
        if not cfg.xemc_poster.value:
            return

        super().applySkin(desktop, parent)
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == "path":
                self.storage_path = str(value)
            else:
                attribs.append((attrib, value))
        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, parent)

    def changed(self, what):
        if not self.instance or not cfg.xemc_poster.value:
            return

        try:
            source = self.source
            service_ref = None
            movie_path = None
            service_handler = eServiceCenter.getInstance()

            if hasattr(source, "__class__"):
                class_name = source.__class__.__name__
                self._log_info("AgpXEMC source class='{}'".format(class_name))

                if class_name == "EMCServiceEvent":
                    service_ref = getattr(source, "service", None)
                    if service_ref:
                        try:
                            movie_path = service_ref.getPath()
                            self._log_info("AgpXEMC EMCServiceEvent movie_path='{}'".format(movie_path))
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
                            self._log_info("AgpXEMC EMCCurrentService movie_path='{}'".format(movie_path))
                        except Exception:
                            movie_path = None

            if not movie_path:
                if isinstance(source, ServiceEvent):
                    service_ref = source.getCurrentService()
                    movie_path = service_ref.getPath() if service_ref else None
                    self._log_info("AgpXEMC ServiceEvent movie_path='{}'".format(movie_path))

                elif isinstance(source, CurrentService):
                    service_ref = source.getCurrentServiceRef()
                    movie_path = service_ref.getPath() if service_ref else None
                    self._log_info("AgpXEMC CurrentService movie_path='{}'".format(movie_path))

                elif isinstance(source, EventInfo):
                    service_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                    movie_path = service_ref.getPath() if service_ref else None
                    self._log_info("AgpXEMC EventInfo movie_path='{}'".format(movie_path))

            if not movie_path:
                service_ref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                if service_ref:
                    info = service_handler.info(service_ref)
                    if info:
                        movie_path = service_ref.getPath()
                        self._log_info("AgpXEMC fallback current movie_path='{}'".format(movie_path))

            if movie_path and _is_video_file(movie_path):
                self._log_info("AgpXEMC processing movie_path='{}'".format(movie_path))
                self._process_movie_path(movie_path)
            else:
                self._log_info("AgpXEMC hide poster | invalid movie_path='{}'".format(movie_path))
                self.instance.hide()

        except Exception as e:
            logger.error("AgpXEMC Render Error: {}".format(str(e)))
            self.instance.hide()

    def _process_movie_path(self, movie_path):
        name = basename(movie_path)
        clean_title = self._sanitize_title(name)
        poster_path = join(self.storage_path, "%s.jpg" % clean_title)

        if _validate_poster(poster_path):
            self.waitPoster(poster_path)
        else:
            search_title = clean_title
            self._queue_for_download(search_title, clean_title, poster_path)

    def _sanitize_title(self, filename):
        name = filename.rsplit('.', 1)[0]
        logger.info("AgpXEMC Original name: {}".format(filename))
        cleaned = sanitize_filename(name)
        cleaned = clean_for_tvdb(cleaned)
        logger.info("AgpXEMC Sanitized title: {}".format(cleaned))

        year_match = findall(r'\b(?:19|20)\d{2}\b', filename)
        logger.info("AgpXEMC Year found: {}".format(year_match))

        if year_match:
            self.release_year = year_match[0]
            logger.info("AgpXEMC Year extract: {}".format(self.release_year))
        else:
            self.release_year = None
            logger.info("AgpXEMC Year not found in file name.")

        logger.info("AgpXEMC Title to find TMDB: {}".format(cleaned))
        self._log_info("AgpXEMC Title to find TMDB: {}".format(cleaned))
        return cleaned.strip()

    def _queue_for_download(self, search_title, clean_title, poster_path):
        if not AgpDBemc or not AgpDBemc.is_alive():
            logger.error("AgpXEMC Thread downloader not active!")
            return
        logger.info("AgpXEMC EMC put: clean_title='%s' poster_path='%s'", search_title, poster_path)
        pdbemc.put((search_title, clean_title, poster_path, self.release_year))
        self.runPosterThread(poster_path)

    def runPosterThread(self, poster_path):
        Thread(target=self.waitPoster, args=(poster_path,), daemon=True).start()

    def display_poster(self, poster_path=None):
        if not self.instance:
            logger.error("AgpXEMC Instance is None in display_poster")
            return

        if poster_path:
            logger.info("AgpXEMC Displaying poster from path: {}".format(poster_path))
            if _validate_poster(poster_path):
                self.instance.setPixmap(loadJPG(poster_path))
                self.instance.setScale(1)
                self.instance.show()
                self.instance.invalidate()
                self.instance.show()
            else:
                logger.error("AgpXEMC Poster file is invalid: {}".format(poster_path))
                self.instance.hide()

    def waitPoster(self, poster_path=None):
        if not self.instance or not poster_path:
            return

        if not exists(poster_path):
            self.instance.hide()

        self.poster_path = poster_path
        self.retry_count = 0
        if self._poster_timer.isActive():
            self._poster_timer.stop()
        self._poster_timer.start(100, True)

    def _retryPoster(self):
        if _validate_poster(self.poster_path):
            logger.debug("AgpXEMC Poster found, displaying")
            self.display_poster(self.poster_path)
            return

        self.retry_count += 1
        if self.retry_count < 5:
            delay = 500 + self.retry_count * 200
            self._poster_timer.start(delay, True)
        else:
            logger.warning("AgpXEMC Poster not found after retries: %s", self.poster_path)
            self.instance.hide()

    def __del__(self):
        try:
            if self._poster_timer.isActive():
                self._poster_timer.stop()
        except Exception:
            pass

    def _log_info(self, message):
        self._write_log("INFO", message)

    def _log_debug(self, message):
        self._write_log("DEBUG", message)

    def _log_error(self, message):
        self._write_log("ERROR", message, error=True)

    def _write_log(self, level, message, error=False):
        try:
            log_dir = "/tmp/agplog"
            if not exists(log_dir):
                makedirs(log_dir)

            if error:
                log_file = log_dir + "/AgpXEMC_errors.log"
            else:
                log_file = log_dir + "/AgpXEMC.log"

            with open(log_file, "a") as w:
                w.write("{} {}: {}\n".format(datetime.now(), level, message))
        except Exception as e:
            print("Logging error: {}".format(e))


class PosterDBEMC(AgpDownloadThread):
    def __init__(self, providers=None):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.providers = {}
        self.provider_engines = []
        self.queued = set()
        self.lock = Lock()
        self.api = api_key_manager
        self.providers = api_key_manager.get_active_providers()
        self.provider_engines = self.build_providers()

    def run(self):
        while True:
            item = pdbemc.get()
            self.executor.submit(self._process_item, item)
            pdbemc.task_done()

    def build_providers(self):
        provider_mapping = {
            "tmdb": (self.search_tmdb, 0),
            "omdb": (self.search_omdb, 1),
            "google": (self.search_google, 2)
        }
        return [
            (name, func, prio) for name, (func, prio) in provider_mapping.items()
            if self.providers.get(name, False)
        ]

    def _process_item(self, item):
        search_title, clean_title, poster_path, release_year = item
        logger.debug("AgpXEMC Processing item: {}".format(item))
        with self.lock:
            if search_title in self.queued:
                return
            self.queued.add(search_title)

        try:
            if self._check_existing(poster_path):
                return

            logger.info("AgpXEMC Starting download: %s", search_title)
            sorted_providers = sorted(self.provider_engines, key=lambda x: x[2])

            for provider_name, provider_func, _ in sorted_providers:
                try:
                    api_key = api_key_manager.get_api_key(provider_name)
                    if not api_key:
                        logger.warning("AgpXEMC Missing API key for %s", provider_name)
                        continue

                    logger.info("AgpXEMC EMC processing: search_title='%s' clean_title='%s'", search_title, clean_title)
                    result = provider_func(
                        dwn_poster=poster_path,
                        title=search_title,
                        shortdesc=None,
                        fulldesc=None,
                        year=release_year,
                        channel=clean_title,
                        api_key=api_key
                    )

                    logger.info("AgpXEMC Trying provider: {} with title: {} year: {}".format(
                        provider_name, search_title, release_year
                    ))

                    if result and self.check_valid_poster(poster_path):
                        logger.info("AgpXEMC Download successful with %s", provider_name)
                        break

                except Exception as e:
                    logger.error("AgpXEMC Error from %s: %s", provider_name, str(e))

        finally:
            with self.lock:
                self.queued.discard(search_title)

    def check_valid_poster(self, path):
        try:
            if not exists(path):
                return False
            if getsize(path) < 1024:
                remove(path)
                return False
            with open(path, 'rb') as f:
                header = f.read(2)
                if header != b'\xFF\xD8':
                    remove(path)
                    return False
            return True
        except Exception as e:
            logger.error("AgpXEMC Poster validation error: {}".format(str(e)))
            return False

    def _check_existing(self, path):
        return exists(path) and getsize(path) > 1024

    def _log_info(self, message):
        self._write_log("INFO", message)

    def _log_debug(self, message):
        self._write_log("DEBUG", message)

    def _log_error(self, message):
        self._write_log("ERROR", message, error=True)

    def _write_log(self, level, message, error=False):
        try:
            log_dir = "/tmp/agplog"
            if not exists(log_dir):
                makedirs(log_dir)

            if error:
                log_file = log_dir + "/PosterDBEMC_errors.log"
            else:
                log_file = log_dir + "/PosterDBEMC.log"

            with open(log_file, "a") as w:
                w.write("{} {}: {}\n".format(datetime.now(), level, message))
        except Exception as e:
            print("Logging error: {}".format(e))


def _is_video_file(path):
    vid_exts = ('.mkv', '.avi', '.mp4', '.ts', '.mov', '.iso', '.m2ts')
    return any(path.lower().endswith(ext) for ext in vid_exts) if path else False


def _validate_poster(poster_path):
    return exists(poster_path) and getsize(poster_path) > 100


def clear_all_log():
    log_dir = secure_log_dir
    log_files = [
        log_dir + "/PosterDBEMC_errors.log",
        log_dir + "/PosterDBEMC.log",
        log_dir + "/PosterXEMC.log",
    ]
    for file in log_files:
        try:
            if exists(file):
                remove(file)
                logger.warning("AgpXEMC Removed cache: {}".format(file))
        except Exception as e:
            logger.error("AgpXEMC log_files cleanup failed: {}".format(e))


db_lock = Lock()
AgpDBemc = None
if cfg.xemc_poster.value:
    if any(api_key_manager.get_active_providers().values()):
        logger.debug("AgpXEMC Starting PosterDB with active providers")
        with db_lock:
            if AgpDBemc is None or not AgpDBemc.is_alive():
                AgpDBemc = PosterDBEMC()
                AgpDBemc.daemon = True
                AgpDBemc.start()
                logger.debug("AgpXEMC PosterDBEMC started with PID: {}".format(AgpDBemc.ident))
else:
    logger.debug("AgpXEMC PosterDBEMC not started - no active providers")
