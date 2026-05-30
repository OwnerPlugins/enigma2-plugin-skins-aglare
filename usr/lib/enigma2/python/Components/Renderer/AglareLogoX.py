#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__author__ = "Lululla"         ##
# #__copyright__ = "AGP Team"     ##
# #__created_by__ = "MNASR"       ##
# ##################################
from __future__ import absolute_import, print_function
from datetime import datetime, timedelta
from os import remove, makedirs
from os.path import join, exists, getsize
from re import sub
import threading
from threading import Thread, Lock
from time import sleep, time
from traceback import format_exc
from collections import OrderedDict
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from enigma import ePixmap, loadPNG, eEPGCache, eTimer
from Components.Renderer.Renderer import Renderer
from Components.Sources.Event import Event
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
from ServiceReference import ServiceReference
import NavigationInstance

from Plugins.Extensions.Aglare.api_config import cfg, ApiKeyManager
from Components.Renderer.AglDownloadThread import AglDownloadThread
from .Agp_Utils import (
    LOGO_FOLDER,
    check_disk_space,
    clean_for_tvdb,
    logger,
    create_secure_log_dir,
    validate_media_path
)
from .Agp_lib import build_search_title, clean_search_title, smart_capitalize_title, should_skip_title

secure_log_dir = create_secure_log_dir()

epgcache = eEPGCache.getInstance()
epgcache.load()
ldb = Queue()
api_key_manager = ApiKeyManager()

extensions = ['.png']
autobouquet_file = None
apdb = dict()


def get_search_title(title, shortdesc="", fulldesc=""):
    try:
        result = build_search_title(
            title or "", shortdesc or "", fulldesc or "")
        return smart_capitalize_title(result)
    except Exception:
        return smart_capitalize_title(clean_search_title(title or ""))


global global_agl_auto_db
AglDB = None
db_lock = Lock()
global_agl_auto_db = None


class AglareLogoX(Renderer):
    GUI_WIDGET = ePixmap

    def __init__(self):
        Renderer.__init__(self)
        self._stop_event = threading.Event()
        self._active_event = threading.Event()
        self._active_event.set()
        self.storage_path = LOGO_FOLDER
        self.extensions = extensions
        self.providers = {"tmdb": True}
        self.nxts = 0
        self.canal = [None] * 6
        self.oldCanal = None
        self.logocanal = None
        self.logoNm = None
        self.logo_refresh_count = 0
        self.logo_refresh_max = 20
        self.logo_refresh_delay = 300

        self.adsl = True

        self.show_timer = eTimer()
        self.show_timer.callback.append(self.refreshLogo)

        logger.info(
            "AglareLogoX renderer initialized | storage_path='{}'".format(
                self.storage_path))

        self.logo_db = AglDB
        self.logo_auto_db = global_agl_auto_db

    def applySkin(self, desktop, parent):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == "nexts":
                try:
                    self.nxts = int(value)
                except Exception:
                    self.nxts = 0
            elif attrib == "path":
                self.storage_path = str(value)
                try:
                    if not exists(self.storage_path):
                        makedirs(self.storage_path, exist_ok=True)
                except Exception as e:
                    logger.error(
                        "Failed to create logo path {}: {}".format(
                            self.storage_path, str(e)))
            else:
                attribs.append((attrib, value))

        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, parent)

    def changed(self, what):
        if not self.instance:
            return

        if what[0] not in (
                self.CHANGED_DEFAULT,
                self.CHANGED_ALL,
                self.CHANGED_SPECIFIC,
                self.CHANGED_CLEAR):
            if self.instance:
                self.instance.hide()
            return

        source = self.source
        source_type = type(source)
        servicetype = None
        service = None
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

                if self.nxts:
                    service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                else:
                    if getattr(source, "event", None) is None:
                        logger.info(
                            "AglareLogoX: Event source has no event yet")
                        if self.instance:
                            self.instance.hide()
                        return

                    event = source.event

                    bt = event.getBeginTime()
                    if bt is not None:
                        self.canal[1] = bt

                    event_name = sub(
                        r"[\u0000-\u001F\u007F-\u009F]",
                        "",
                        event.getEventName() or "")
                    if not event_name:
                        logger.info(
                            "AglareLogoX: Event source has empty event name")
                        if self.instance:
                            self.instance.hide()
                        return

                    self.canal[2] = event_name
                    self.canal[3] = event.getExtendedDescription()
                    self.canal[4] = event.getShortDescription()
                    self.canal[5] = event_name

            if service is not None:
                service_str = service.toString()
                events = epgcache.lookupEvent(
                    ['IBDCTESX', (service_str, 0, -1, -1)])
                if not events or len(events) <= self.nxts:
                    if self.instance:
                        self.instance.hide()
                    return

                service_name = ServiceReference(service).getServiceName().replace(
                    '\xc2\x86', '').replace('\xc2\x87', '')
                self.canal = [None] * 6
                self.canal[0] = service_name
                self.canal[1] = events[self.nxts][1]
                self.canal[2] = events[self.nxts][4]
                self.canal[3] = events[self.nxts][5]
                self.canal[4] = events[self.nxts][6]
                self.canal[5] = self.canal[2]
                if not autobouquet_file and service_name not in apdb:
                    apdb[service_name] = service_str

            if not servicetype or not self.canal[5]:
                if self.instance:
                    self.instance.hide()
                return

            curCanal = "%s-%s" % (self.canal[1], self.canal[2])
            if curCanal == self.oldCanal:
                return

            if self.instance:
                self.instance.hide()

            self.oldCanal = curCanal
            self.logocanal = get_search_title(
                self.canal[5], self.canal[4], self.canal[3])
            if not self.logocanal:
                return

            skip_title, skip_word = should_skip_title(self.logocanal)
            if skip_title:
                logger.info(
                    "Skipping before queue: original='{}' | final_search_title='{}' | matched_exclusion='{}' | channel='{}'".format(
                        self.canal[2], self.logocanal, skip_word, self.canal[0]))
                return

            logo_path = join(self.storage_path, "%s.png" % self.logocanal)
            if checkLogoExistence(logo_path):
                self.logoNm = logo_path
                self.logo_refresh_count = 0

                if not self.showLogo(logo_path):
                    try:
                        self.show_timer.start(self.logo_refresh_delay, True)
                    except Exception:
                        pass
                else:
                    try:
                        self.show_timer.start(self.logo_refresh_delay, True)
                    except Exception:
                        pass
            else:
                if hasattr(
                        self.logo_db,
                        "queued_logos") and self.logocanal in self.logo_db.queued_logos:
                    self.logoNm = logo_path
                    self.logo_refresh_count = 0
                    try:
                        self.show_timer.start(self.logo_refresh_delay, True)
                    except Exception:
                        pass
                    return
                logger.info(
                    "Queueing logo download: original='{}' | final_search_title='{}' | channel='{}'".format(
                        self.canal[2], self.logocanal, self.canal[0]))
                ldb.put(self.canal[:])
                self.runLogoThread()
                self.logoNm = logo_path
                self.logo_refresh_count = 0
                try:
                    self.show_timer.start(self.logo_refresh_delay, True)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Error in changed: %s" % str(e))
            if self.instance:
                self.instance.hide()

    def runLogoThread(self):
        Thread(target=self.waitLogo, daemon=True).start()

    def showLogo(self, logo_path=None):
        if not self.instance:
            return

        if not logo_path and self.logoNm:
            logo_path = self.logoNm

        if not logo_path or not checkLogoExistence(logo_path):
            if self.instance:
                self.instance.hide()
            return

        self.logoNm = logo_path

        try:
            pixmap = loadPNG(logo_path)
            if pixmap:
                self.instance.hide()
                self.instance.setPixmap(pixmap)
                self.instance.setScale(1)
                self.instance.show()
                return True
        except Exception as e:
            logger.warning(
                "Logo loadPNG failed | file='{}' | error='{}'".format(
                    logo_path, str(e)))

        if self.instance:
            self.instance.hide()
        return False

    def refreshLogo(self):
        if not self.instance or not self.logoNm:
            return

        if self.showLogo(self.logoNm):
            self.logo_refresh_count = 0
            return

        self.logo_refresh_count += 1

        if self.logo_refresh_count < self.logo_refresh_max:
            try:
                self.show_timer.start(self.logo_refresh_delay, True)
            except Exception:
                pass
        else:
            logger.warning(
                "Logo refresh failed after retries | file='{}'".format(
                    self.logoNm))
            self.logo_refresh_count = 0

    def waitLogo(self):
        if not self.instance or not self.canal[5]:
            return

        logocanal = get_search_title(
            self.canal[5], self.canal[4], self.canal[3])
        logo_path = join(self.storage_path, "%s.png" % logocanal)

        self.logoNm = logo_path
        self.logo_refresh_count = 0

        try:
            self.show_timer.start(self.logo_refresh_delay, True)
        except Exception:
            pass


class LogoDB(AglDownloadThread):
    def __init__(self, providers=None):
        super().__init__()
        self.providers = {"tmdb": True}
        self.provider_engines = [("tmdb", self.search_tmdb_logo)]
        self.logocanal = None
        self.extensions = extensions
        self.queued_logos = set()
        self.executor = ThreadPoolExecutor(max_workers=1)
        logger.info("LogoDB executor configured | max_workers='1'")

    def run(self):
        while True:
            canal = ldb.get()
            self.process_canal(canal)
            ldb.task_done()

    def process_canal(self, canal):
        self.executor.submit(self._process_canal_task, canal)

    def _process_canal_task(self, canal):
        try:
            local_logocanal = get_search_title(canal[5], canal[4], canal[3])
            if not local_logocanal:
                return

            skip_title, skip_word = should_skip_title(local_logocanal)
            if skip_title:
                logger.info(
                    "Skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}' | channel='{}'".format(
                        canal[2], local_logocanal, skip_word, canal[0]))
                return

            if not exists(LOGO_FOLDER):
                makedirs(LOGO_FOLDER, exist_ok=True)

            logo_path = join(LOGO_FOLDER, "%s.png" % local_logocanal)

            with Lock():
                if local_logocanal in self.queued_logos:
                    return
                self.queued_logos.add(local_logocanal)

            try:
                if self.check_valid_logo(logo_path):
                    return

                logger.info(
                    "Starting logo download: original='{}' | clean_for_tvdb='{}' | final_search_title='{}' | channel='{}'".format(
                        canal[2],
                        clean_for_tvdb(
                            canal[5]),
                        local_logocanal,
                        canal[0]))

                api_key = api_key_manager.get_api_key("tmdb")
                if not api_key:
                    logger.warning("Missing API key for tmdb")
                    return

                result = self.search_tmdb_logo(
                    dwn_logo=logo_path,
                    title=local_logocanal,
                    shortdesc=canal[4],
                    fulldesc=canal[3],
                    channel=canal[0],
                    api_key=api_key
                )

                if result and self.check_valid_logo(logo_path):
                    logger.info("Logo download successful with tmdb")

            finally:
                with Lock():
                    self.queued_logos.discard(local_logocanal)
        except Exception as e:
            logger.error("Critical error in _process_canal_task: %s" % str(e))
            logger.error(format_exc())

    def check_valid_logo(self, path):
        try:
            if not exists(path):
                return False
            if getsize(path) < 100:
                remove(path)
                return False
            with open(path, 'rb') as f:
                if f.read(8) != b'\x89PNG\r\n\x1a\n':
                    remove(path)
                    return False
            return True
        except Exception:
            return False


class LogoAutoDB(AglDownloadThread):
    _instance = None

    def __init__(self, providers=None, max_logos=2000):
        super().__init__()
        self._stop_event = threading.Event()
        self._active_event = threading.Event()
        self._scan_lock = Lock()
        self.max_logos = max_logos
        self.min_disk_space = 100
        self.last_scan = 0
        self.apdb = OrderedDict()
        self.provider_engines = [("tmdb", self.search_tmdb_logo)]
        self.logo_folder = "/tmp/logos"
        if not exists(self.logo_folder):
            makedirs(self.logo_folder, mode=0o700)
        self.scheduled_hour = 0
        self.scheduled_minute = 0
        self.daemon = True
        self.active = False
        self._active_event.set()

        if not cfg.pstdown.value:
            return
        if not api_key_manager.get_api_key("tmdb"):
            return
        self.active = True
        self.logo_folder = self._init_logo_folder()
        try:
            scan_time = cfg.pscan_time.value
            self.scheduled_hour = int(scan_time[0])
            self.scheduled_minute = int(scan_time[1])
        except Exception:
            self.scheduled_hour = 0
            self.scheduled_minute = 0

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LogoAutoDB, cls).__new__(cls)
        return cls._instance

    @property
    def active(self):
        return self._active_event.is_set()

    @active.setter
    def active(self, value):
        if value:
            self._active_event.set()
        else:
            self._active_event.clear()

    def start(self):
        if not self.is_alive():
            self.active = True
            super().start()

    def run(self):
        while not self._stop_event.is_set():
            now = datetime.now()
            next_run = datetime(
                year=now.year,
                month=now.month,
                day=now.day,
                hour=self.scheduled_hour,
                minute=self.scheduled_minute,
                second=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            while datetime.now() < next_run and not self._stop_event.is_set():
                sleep(1)
            if not self._stop_event.is_set():
                self._execute_scheduled_scan()

    def stop(self):
        self.active = False
        self._active_event.set()
        if self.is_alive():
            self.join(timeout=2.0)

    def _execute_scheduled_scan(self):
        with self._scan_lock:
            self._full_scan()
            self._process_services()
            self.last_scan = time()

    def _full_scan(self):
        self.service_queue = self._load_services()

    def _load_services(self):
        services = OrderedDict()
        fav_path = "/etc/enigma2/userbouquet.favourites.tv"
        bouquets = [fav_path] if exists(fav_path) else []
        main_path = "/etc/enigma2/bouquets.tv"
        if exists(main_path):
            try:
                with open(main_path, "r") as f:
                    bouquets += ["/etc/enigma2/" + line.split(
                        "\"")[1] for line in f if line.startswith("#SERVICE") and "FROM BOUQUET" in line]
            except Exception:
                pass
        for bouquet in bouquets:
            if exists(bouquet):
                try:
                    with open(bouquet, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith(
                                    "#SERVICE") and "FROM BOUQUET" not in line:
                                service_ref = line[9:]
                                services[service_ref] = None
                                self.apdb[service_ref] = service_ref
                except Exception:
                    pass
        return list(services.keys())

    def _process_services(self):
        for service_ref in self.apdb.values():
            try:
                events = epgcache.lookupEvent(
                    ['IBDCTESX', (service_ref, 0, -1, 1440)])
                if not events:
                    continue
                for evt in events:
                    canal = self._prepare_canal_data(service_ref, evt)
                    if canal:
                        self._download_logo(canal)
            except Exception:
                pass

    def _prepare_canal_data(self, service_ref, event):
        try:
            service_name = ServiceReference(service_ref).getServiceName().replace(
                "\xc2\x86", "").replace("\xc2\x87", "")
            raw_title = event[4] or ""
            event_name = raw_title.strip()
            if not event_name:
                return None
            clean_title = get_search_title(event_name, event[6], event[5])
            return [
                service_name,
                event[1],
                event_name,
                event[5],
                event[6],
                clean_title]
        except Exception:
            return None

    def _download_logo(self, canal):
        ok, local_logocanal = self._pre_download_checks(canal)
        if not ok:
            return

        api_key = api_key_manager.get_api_key("tmdb")
        if not api_key:
            return

        if not exists(LOGO_FOLDER):
            makedirs(LOGO_FOLDER, exist_ok=True)

        logo_path = join(LOGO_FOLDER, "%s.png" % local_logocanal)
        self.search_tmdb_logo(
            dwn_logo=logo_path,
            title=local_logocanal,
            shortdesc=canal[4],
            fulldesc=canal[3],
            channel=canal[0],
            api_key=api_key
        )

    def _pre_download_checks(self, canal):
        if not canal or len(canal) < 6:
            return False, ""

        local_logocanal = get_search_title(canal[5] or "", canal[4], canal[3])
        if not local_logocanal:
            return False, ""

        skip_title, _ = should_skip_title(local_logocanal)
        if skip_title:
            return False, ""

        if not check_disk_space(LOGO_FOLDER, 10):
            return False, ""

        return True, local_logocanal

    def _init_logo_folder(self):
        try:
            return validate_media_path(
                LOGO_FOLDER,
                media_type="logos",
                min_space_mb=self.min_disk_space)
        except Exception:
            fallback = "/tmp/logos"
            try:
                if not exists(fallback):
                    makedirs(fallback, mode=0o700)
            except Exception:
                pass
            return fallback


def checkLogoExistence(logo_path):
    return exists(logo_path)


def clear_all_log():
    pass


if api_key_manager.get_api_key("tmdb"):
    logger.debug("Starting LogoDB with TMDB provider")
    with db_lock:
        if AglDB is None or not AglDB.is_alive():
            AglDB = LogoDB()
            AglDB.daemon = True
            AglDB.start()
            logger.debug("LogoDB started with PID: %s" % AglDB.ident)
else:
    logger.debug("LogoDB not started - missing TMDB API key")

if cfg.pstdown.value and api_key_manager.get_api_key("tmdb"):
    if global_agl_auto_db:
        global_agl_auto_db.stop()
        global_agl_auto_db = None
    logger.debug("Starting LogoAutoDB with TMDB provider")
    global_agl_auto_db = LogoAutoDB()
    global_agl_auto_db.daemon = True
    global_agl_auto_db.start()
    logger.debug("LogoAutoDB started")
