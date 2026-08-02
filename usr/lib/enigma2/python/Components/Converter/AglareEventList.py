# -*- coding: utf-8 -*-

"""
<widget
    source="ServiceEvent"
    render="AglareEventListDisplay"
    position="1080,610"
    size="1070,180"
    column0="0,100,yellow,Regular,30,0,0"
    column1="100,950,white,Regular,28,0,1"
    primetimeoffset="0"
    rowHeight="35"
    backgroundColor="#FF101010"
    transparent="1"
    zPosition="50">
    <convert type="AglareEventList">beginOnly=yes,primetime=yes,eventcount=4</convert>
</widget>
"""

from Components.Converter.Converter import Converter
from Components.Element import cached
from enigma import eEPGCache, eServiceReference
from time import localtime, strftime, mktime, time
from datetime import datetime, timedelta
import logging

# Configure the logger
logger = logging.getLogger("EventListLogger")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class AglareEventList(Converter, object):
    def __init__(self, type):
        Converter.__init__(self, type)
        self.epgcache = eEPGCache.getInstance()
        self.primetime = 0
        self.eventcount = 0
        self.beginOnly = False

        # Parse the input arguments
        if len(type):
            args = type.split(',')
            i = 0
            while i <= len(args) - 1:
                type_c, value = args[i].split('=')
                if type_c == "eventcount":
                    self.eventcount = int(value)
                elif type_c == "primetime":
                    if value == "yes":
                        self.primetime = 1
                elif type_c == "beginOnly":
                    if value == "yes":
                        self.beginOnly = True
                i += 1

    @cached
    def getContent(self):
        contentList = []
        seen_begins = set()  # Track event start times to prevent duplicates
        ref = self.source.service
        info = ref and self.source.info
        if info is None:
            return []

        event = self.source.getCurrentEvent()
        if not event:
            return contentList

        i = 1
        while i <= self.eventcount and event:
            begin = event.getBeginTime()
            dur = event.getDuration()

            # Stop if event data is invalid
            if begin is None or dur is None:
                break

            # Append current event if we haven't seen it yet
            if begin not in seen_begins:
                contentList.append(self.getEventTuple(event))
                seen_begins.add(begin)
                i += 1  # Only increment the counter if a unique event was added

            # Calculate next event time
            next_start_time = begin + dur
            next_event = self.epgcache.lookupEventTime(
                eServiceReference(ref.toString()), next_start_time
            )

            # Failsafe: if EPG overlaps and returns the exact same event, push
            # the time forward 1 minute
            if next_event and next_event.getBeginTime() == begin:
                next_start_time += 60
                next_event = self.epgcache.lookupEventTime(
                    eServiceReference(ref.toString()), next_start_time
                )

            event = next_event

        # Primetime logic
        if self.primetime == 1:
            now = localtime(time())
            dt = datetime(now.tm_year, now.tm_mon, now.tm_mday, 20, 15)
            if time() > mktime(dt.timetuple()):
                dt += timedelta(days=1)  # Skip to the next day...
            primeTime = int(mktime(dt.timetuple()))

            event = self.epgcache.lookupEventTime(
                eServiceReference(ref.toString()), primeTime
            )
            if event:
                bt = event.getBeginTime()
                # Ensure the primetime event is valid AND hasn't already been
                # added
                if bt is not None and bt <= primeTime and bt not in seen_begins:
                    contentList.append(self.getEventTuple(event))

        return contentList

    def getEventTuple(self, event):
        try:
            begin = event.getBeginTime()
            dur = event.getDuration()

            if begin is None or dur is None:
                return ("", "", "")

            if self.beginOnly:
                event_time = "%s" % (strftime("%H:%M", localtime(begin)))
            else:
                end = begin + dur
                event_time = "%s - %s" % (
                    strftime("%H:%M", localtime(begin)),
                    strftime("%H:%M", localtime(end)),
                )

            title = event.getEventName() or ""
            duration = "%d min" % (dur / 60)
            return (event_time, title, duration)
        except Exception as e:
            # Log the error con maggiore dettaglio
            logger.error("Error in getEventTuple: %s", e)
            return ("Error", "Error retrieving event", "")

    def changed(self, what):
        if what[0] != self.CHANGED_SPECIFIC:
            Converter.changed(self, what)
