#!/usr/bin/python
# -*- coding: utf-8 -*-

# Improved version of AglareNxtEvnt
# Original by digiteng...05.2020, 07.2020, 11.2021
#
# Usage examples for skin:
#
# Show up to 10 next events:
# <widget source="ServiceEvent" render="AglareNxtEvnt" nxtEvents="10" snglEvent="" font="Regular;20" position="933,705" size="240,80" zPosition="5" backgroundColor="yellow" transparent="1" />
#
# Show only one specific event:
# <widget source="ServiceEvent" render="AglareNxtEvnt" nxtEvents="" snglEvent="0" font="Regular;20" position="933,705" size="240,80" zPosition="5" backgroundColor="yellow" transparent="1" />
#
# Notes:
# - nxtEvents and snglEvent should not both be used at the same time.
# - snglEvent="0" means the currently running event.
# - snglEvent="1" means the first upcoming event after the current one.
# - nxtEvents is capped at 10.

from __future__ import absolute_import

from time import localtime

from Components.Renderer.Renderer import Renderer
from Components.VariableText import VariableText
from enigma import eLabel, eEPGCache


class AglareNxtEvnt(Renderer, VariableText):
    GUI_WIDGET = eLabel

    MAX_EVENTS = 10
    EPG_LOOKUP_MINUTES = 1200

    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)

        # Skin values are strings, so keep these as strings.
        self.nxEvnt = ''
        self.snglEvnt = ''

        self.epgcache = eEPGCache.getInstance()

    def applySkin(self, desktop, parent):
        # Consume custom attributes here and remove them before passing the
        # remaining attributes to the base renderer.
        attribs = []

        for attrib, value in self.skinAttributes:
            if attrib == 'nxtEvents':
                self.nxEvnt = value.strip()
            elif attrib == 'snglEvent':
                self.snglEvnt = value.strip()
            else:
                attribs.append((attrib, value))

        self.skinAttributes = attribs
        return Renderer.applySkin(self, desktop, parent)

    def _safe_int(self, value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _format_event(self, event):
        # lookupEvent(['IBDCT', ...]) returns tuples where:
        # event[1] = begin time
        # event[4] = event title
        try:
            title = event[4] or ''
            begin_time = localtime(event[1])
            return '%02d:%02d - %s' % (begin_time[3], begin_time[4], title)
        except Exception:
            return ''

    def _get_events(self, ref):
        if not ref:
            return []

        events = self.epgcache.lookupEvent([
            'IBDCT',
            (
                ref.toString(),
                0,
                -1,
                self.EPG_LOOKUP_MINUTES
            )
        ])

        return events or []

    def changed(self, what):
        self.text = ''

        try:
            ref = self.source.service
            events = self._get_events(ref)

            if not events:
                return ''

            lines = []

            # Usually events[0] is the currently running event.
            # Upcoming events start from events[1].
            upcoming_events = events[1:]

            if self.snglEvnt != '':
                # snglEvent="0" means the current event.
                # snglEvent="1" means the first upcoming event after the current one.
                requested_index = self._safe_int(self.snglEvnt, -1)

                if requested_index < 0:
                    return ''

                if requested_index == 0:
                    selected_event = events[0]
                else:
                    zero_based_index = requested_index - 1

                    if zero_based_index >= len(upcoming_events):
                        return ''

                    selected_event = upcoming_events[zero_based_index]

                line = self._format_event(selected_event)
                if line:
                    lines.append(line)

            else:
                requested_count = self._safe_int(self.nxEvnt, self.MAX_EVENTS)

                if requested_count <= 0:
                    requested_count = self.MAX_EVENTS

                count = min(requested_count, self.MAX_EVENTS, len(upcoming_events))

                for event in upcoming_events[:count]:
                    line = self._format_event(event)
                    if line:
                        lines.append(line)

            self.text = '\n'.join(lines)

        except Exception:
            self.text = ''
            return ''
