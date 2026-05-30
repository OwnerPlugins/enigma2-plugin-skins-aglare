#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
##__author__ = "Lululla"         ##
##__copyright__ = "AGP Team"     ##
##__modified_by__ = "MNASR"      ##
###################################
from __future__ import absolute_import, print_function

from os.path import join, exists, getsize
from json import loads as json_loads

from Components.Renderer.Renderer import Renderer
from Components.VariableText import VariableText
from enigma import eLabel
from Components.config import config
import urllib3

from Plugins.Extensions.Aglare.api_config import cfg
from .Agp_Utils import IMOVIE_FOLDER, clean_for_tvdb, logger
from .Agp_lib import build_search_title, quoteEventName, clean_search_title, smart_capitalize_title, should_skip_title

if not IMOVIE_FOLDER.endswith("/"):
    IMOVIE_FOLDER += "/"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AgpGenreX(Renderer, VariableText):
    GUI_WIDGET = eLabel

    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)

        self.adsl = True

        self.storage_path = IMOVIE_FOLDER
        self.text = ""

    def get_search_title(self, title, shortdesc="", fulldesc=""):
        try:
            result = build_search_title(title or "", shortdesc or "", fulldesc or "")
            return smart_capitalize_title(result)
        except Exception:
            return smart_capitalize_title(clean_search_title(title or ""))

    def changed(self, what):
        if not self.instance:
            return

        if what is None or not cfg.genre_source.value:
            self.text = ""
            self.instance.hide()
            return

        self.delay()

    def delay(self):
        event = self.source.event
        if not event:
            self.text = ""
            self.instance.hide()
            return

        ev_name = (event.getEventName() or "").strip().replace('ё', 'е')
        event_name = self.get_search_title(
            ev_name,
            event.getShortDescription() or "",
            event.getExtendedDescription() or ""
        )

        skip_title, skip_word = should_skip_title(event_name)
        if skip_title:
            logger.info("AgpGenreX skipping title: original='{}' | final_search_title='{}' | matched_exclusion='{}'".format(
                ev_name, event_name, skip_word
            ))
            self.text = ""
            self.instance.hide()
            return

        infos_file = join(self.storage_path, event_name + ".json")
        logger.info("AgpGenreX json lookup | file='{}'".format(infos_file))

        genres_text = ""

        if exists(infos_file):
            try:
                if getsize(infos_file) > 0:
                    with open(infos_file, "r") as f:
                        content = f.read()
                    json_data = json_loads(content)

                    genres = json_data.get("genres", [])
                    if genres:
                        names = [g.get("name", "").strip() for g in genres if g.get("name", "").strip()]
                        if names:
                            genres_text = "Genre : " + " • ".join(names)
                            logger.info("AgpGenreX genres extracted | title='{}' | genres='{}'".format(
                                event_name, genres_text
                            ))
                    else:
                        logger.info("AgpGenreX JSON file has no genres data: {}".format(infos_file))
                else:
                    logger.info("AgpGenreX JSON file is empty (0 bytes): {}".format(infos_file))
            except Exception as e:
                logger.warning("AgpGenreX invalid JSON | file='{}' | error='{}'".format(infos_file, str(e)))

        if not genres_text:
            self.text = ""
            self.instance.hide()
            return

        self.text = genres_text
        self.instance.setText(self.text)
        self.instance.show()
