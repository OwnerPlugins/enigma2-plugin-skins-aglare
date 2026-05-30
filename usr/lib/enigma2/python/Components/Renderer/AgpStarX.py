#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__author__ = "Lululla"         ##
# #__copyright__ = "AGP Team"     ##
# #__modified_by__ = "MNASR"      ##
# ##################################
from __future__ import absolute_import, print_function
"""
AGP Star renderer - cache only mode
Reads rating from cached JSON in IMOVIE_FOLDER and renders one-widget stars.
Supports ChannelSelection, infobar now/next, and EPG-style screens.
"""

from json import load as json_load
from os import remove, makedirs
from os.path import exists, getsize
from threading import Lock
from re import sub
import urllib3

from Components.Renderer.Renderer import Renderer
from Components.VariableValue import VariableValue
from enigma import eEPGCache, eSlider, eWidget, ePoint, eSize, loadPNG
from enigma import eTimer
from Components.config import config
from Components.Sources.Event import Event
from Components.Sources.EventInfo import EventInfo
from Components.Sources.CurrentService import CurrentService
from Components.Sources.ServiceEvent import ServiceEvent
import NavigationInstance
from ServiceReference import ServiceReference

from Plugins.Extensions.Aglare.api_config import cfg

from .Agp_Utils import IMOVIE_FOLDER, logger  # , clean_for_tvdb
from .Agp_lib import build_search_title, clean_search_title, smart_capitalize_title, should_skip_title

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if not IMOVIE_FOLDER.endswith("/"):
    IMOVIE_FOLDER += "/"

epgcache = eEPGCache.getInstance()
epgcache.load()


class AgpStarX(VariableValue, Renderer):
    GUI_WIDGET = eWidget
    sources = ["Service", "ServiceEvent"]

    def __init__(self):
        Renderer.__init__(self)
        VariableValue.__init__(self)

        self.lock = Lock()
        self.__start = 0
        self.__end = 100
        self.epgcache = eEPGCache.getInstance()

        self.star = None
        self.pxmp = None
        self.szX = 200
        self.szY = 20

        self.storage_path = IMOVIE_FOLDER
        self.pending_info_file = ""
        self.pending_title = ""
        self.retry_count = 0
        self.max_retries = 6
        self.retry_interval_ms = 5000

        self.nxts = 0
        self.canal = [None] * 6
        self.oldCanal = None
        self.last_channel = None

        self.adsl = True

        self.rating_source = cfg.rating_source.value

        self._json_timer = eTimer()
        self._json_timer.callback.append(self._retry_json_read)

        logger.info("AgpStarX Renderer initialized")

    def get_search_title(self, title, shortdesc="", fulldesc=""):
        try:
            result = build_search_title(title or "", shortdesc or "", fulldesc or "")
            return smart_capitalize_title(result)
        except Exception:
            return smart_capitalize_title(clean_search_title(title or ""))

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
            elif attrib == 'nexts':
                try:
                    self.nxts = int(value)
                except Exception:
                    self.nxts = 0
            elif attrib == 'path':
                self.storage_path = str(value)
                try:
                    if not exists(self.storage_path):
                        makedirs(self.storage_path, exist_ok=True)
                except Exception as e:
                    logger.error("Failed to create star path {}: {}".format(self.storage_path, str(e)))
            elif attrib == 'alphatest':
                pass
            else:
                attribs.append((attrib, value))

        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, screen)

    def GUIcreate(self, parent):
        self.instance = eWidget(parent)
        self.star = eSlider(self.instance)

    def _strip_control(self, value):
        try:
            return sub(r"[\u0000-\u001F\u007F-\u009F]", "", str(value or ""))
        except Exception:
            return str(value or "")

    def changed(self, what):
        if what[0] == self.CHANGED_CLEAR:
            # logger.info("AgpStarX changed clear")
            if self._json_timer.isActive():
                self._json_timer.stop()
            self.oldCanal = None
            self.pending_info_file = ""
            self.pending_title = ""
            self._reset_star()
            return

        if not self.rating_source:
            # logger.info("AgpStarX rating_source disabled | value='{}'".format(str(self.rating_source)))
            if self._json_timer.isActive():
                self._json_timer.stop()
            self.oldCanal = None
            self.pending_info_file = ""
            self.pending_title = ""
            self._reset_star()
            return

        self.infos()

    def infos(self):
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

                if self.nxts:
                    service = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
                else:
                    if getattr(source, "event", None) is None:
                        logger.info("AgpStarX infos: Event source has no event yet")
                        self._hide_star()
                        return

                    event = source.event
                    bt = event.getBeginTime()
                    if bt is not None:
                        self.canal[1] = bt

                    event_name = self._strip_control(event.getEventName())
                    if not event_name:
                        logger.info("AgpStarX infos: Event source has empty event name")
                        self._hide_star()
                        return

                    self.canal[2] = event_name
                    self.canal[3] = event.getExtendedDescription()
                    self.canal[4] = event.getShortDescription()
                    self.canal[5] = event_name
            else:
                servicetype = None

            if service is not None:
                service_str = service.toString()
                events = self.epgcache.lookupEvent(['IBDCTESX', (service_str, 0, -1, -1)])
                # logger.info("AgpStarX event list | nexts='{}' | events_count='{}'".format(str(self.nxts), str(len(events) if events else 0)))
                if not events or len(events) <= self.nxts:
                    logger.info("AgpStarX infos: no event at requested nexts='{}'".format(str(self.nxts)))
                    self._hide_star()
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
                logger.info("AgpStarX infos: no usable event")
                self._hide_star()
                return

            curCanal = "%s-%s-%s" % (self.nxts, self.canal[1], self.canal[2])
            if curCanal == self.oldCanal:
                return

            self.oldCanal = curCanal
            self.last_channel = self.canal[2]
            self._reset_star()
            self.pending_title = self.get_search_title(self.canal[5], self.canal[4], self.canal[3])

            skip_title, skip_word = should_skip_title(self.pending_title)
            if skip_title:
                logger.info("AgpStarX skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                    self.canal[2], self.pending_title, skip_word
                ))
                self._hide_star()
                return

            base = self.storage_path if str(self.storage_path).endswith("/") else str(self.storage_path) + "/"
            self.pending_info_file = "{}{}.json".format(base, self.pending_title)
            self.retry_count = 0

            # logger.info("AgpStarX prepared json lookup | original='{}' | final_search_title='{}' | file='{}' | nexts='{}'".format(self.canal[2], self.pending_title, self.pending_info_file, str(self.nxts)))

            self._start_json_retry()

        except Exception as e:
            logger.error("AgpStarX infos error: {}".format(str(e)), exc_info=True)

    def _start_json_retry(self):
        if self._json_timer.isActive():
            self._json_timer.stop()
        self._json_timer.start(100, True)

    def _retry_json_read(self):
        try:
            if not self.instance or not self.star:
                logger.info("AgpStarX retry aborted: widget not ready")
                return

            current_title = self.canal[2] if self.canal and len(self.canal) > 2 else self.last_channel
            if not current_title:
                logger.info("AgpStarX retry waiting: no current title yet")
                self.retry_count += 1
                if self.retry_count < self.max_retries:
                    self._json_timer.start(self.retry_interval_ms, True)
                else:
                    self._hide_star()
                return

            info_file = self.pending_info_file
            if not info_file:
                logger.info("AgpStarX retry aborted: no pending file")
                self._hide_star()
                return

            if exists(info_file):
                try:
                    if getsize(info_file) > 0:
                        with open(info_file, "r") as f:
                            data = json_load(f)
                        logger.info("AgpStarX loaded cached json | file='{}'".format(info_file))
                        # logger.info("AgpStarX cached json keys | keys='{}'".format(",".join(sorted(list(data.keys())[:20]))))
                        self.process_data(data)
                        return
                    else:
                        logger.info("AgpStarX JSON file is empty (0 bytes): {}".format(info_file))
                except Exception as e:
                    logger.warning("AgpStarX invalid json, removing: {} | error={}".format(info_file, str(e)))
                    try:
                        remove(info_file)
                    except Exception:
                        pass

            self._hide_star()
            self.retry_count += 1
            if self.retry_count < self.max_retries:
                logger.info("AgpStarX waiting for json | try='{}/{}' | file='{}'".format(
                    self.retry_count, self.max_retries, info_file
                ))
                self._json_timer.start(self.retry_interval_ms, True)
            else:
                logger.info("AgpStarX json not found after retries | file='{}'".format(info_file))
                self._hide_star()

        except Exception as e:
            logger.error("AgpStarX _retry_json_read error: {}".format(str(e)), exc_info=True)
            self._hide_star()

    def process_data(self, data):
        try:
            self._delayed_ui_update(data)
        except Exception as e:
            logger.error("AgpStarX process_data error: {}".format(str(e)), exc_info=True)

    def _delayed_ui_update(self, data):
        try:
            if not self.instance or not self.star:
                return

            current_title = self.canal[2] if self.canal and len(self.canal) > 2 else self.last_channel
            if not current_title or current_title != self.last_channel:
                return

            rating = data.get('vote_average', 0)
            rating_source = "vote_average"

            if not rating and data.get('imdbRating') not in (None, '', 'N/A'):
                try:
                    rating = float(data.get('imdbRating'))
                    rating_source = "imdbRating"
                    print(rating_source)
                except Exception:
                    rating = 0

            try:
                rtng = min(int(float(rating) * 10), 100) if rating else 0
            except Exception:
                rtng = 0

            if rtng <= 0:
                logger.info("AgpStarX no usable rating | title='{}' | file='{}'".format(
                    self.pending_title, self.pending_info_file
                ))
                self._hide_star()
                return

            if rtng > 100:
                rtng = 100

            filled_pix = self._get_skin_filled_pixmap()
            background_pix = self._get_skin_star_background()

            # logger.info("AgpStarX slider update | title='{}' | slider_value='{}' | filled='{}' | background='{}'".format(self.pending_title, str(rtng), filled_pix, background_pix))

            with self.lock:
                self.star.move(ePoint(0, 0))
                self.star.resize(eSize(self.szX, self.szY))

                # OpenViX eSlider may not implement setAlphatest().
                # Do not fail the whole star widget because of this optional method.
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
                self.instance.show()

        except Exception as e:
            logger.error("AgpStarX UI update skipped: {}".format(str(e)), exc_info=True)

    def postWidgetCreate(self, instance):
        if self.star is not None:
            self.star.setRange(self.__start, self.__end)

    def setRange(self, range):
        (self.__start, self.__end) = range
        if self.star is not None:
            self.star.setRange(self.__start, self.__end)

    def getRange(self):
        return self.__start, self.__end
