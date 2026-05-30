#!/usr/bin/python
# -*- coding: utf-8 -*-
# ##################################
# #__created_by__ = "MNASR"       ##
# ##################################
from Components.Converter.Converter import Converter
from Components.Element import cached
from time import time, localtime
from Tools.Hex2strColor import Hex2strColor
from skin import parseColor


class AglareEventBarTextSimple(Converter):
    def __init__(self, type):
        Converter.__init__(self, type)
        self.separator = " | "
        self.separator_color = ""
        self.text_color = ""
        self.minus = True
        self.unit = "clock"
        self.now_label = ""
        self.next_label = ""
        self.range_sep = " - "
        self.namewidth = 0
        self._parseOptions(type)

    def _parseColor(self, value):
        value = value.strip()
        if not value:
            return ""

        try:
            return Hex2strColor(parseColor(value).argb())
        except Exception:
            pass

        if value.startswith("#"):
            value = value[1:]
        elif value.lower().startswith("0x"):
            value = value[2:]

        if len(value) == 6:
            value = "00" + value
        elif len(value) != 8:
            return ""

        try:
            return Hex2strColor(int(value, 16))
        except Exception:
            return ""

    def _parseOptions(self, options):
        if not options:
            return

        for item in [x.strip() for x in options.split(",") if x.strip()]:
            if "=" in item:
                key, value = [x.strip() for x in item.split("=", 1)]
                key = key.lower()
            else:
                key, value = item.strip().lower(), "yes"

            if key == "sep":
                self.separator = {
                    "pipe": " | ",
                    "pip": " | ",
                    "dot": " · ",
                    "bigdot": " ● ",
                    "bullet": " ● ",
                    "dash": " - ",
                    "slash": " / ",
                    "comma": ", ",
                    "space": " ",
                }.get(value.lower(), self.separator)

            elif key == "sepcolor":
                self.separator_color = self._parseColor(value)

            elif key == "textcolor":
                self.text_color = self._parseColor(value)

            elif key == "minus":
                self.minus = value.lower() not in ("no", "false", "0", "off")

            elif key == "unit":
                v = value.lower()
                if v in ("clock", "time", "hh:mm:ss"):
                    self.unit = "clock"
                elif v in ("minutes", "mins", "min"):
                    self.unit = "minutes"

            elif key == "labelnow":
                self.now_label = value

            elif key == "labelnext":
                self.next_label = value

            elif key == "namewidth":
                try:
                    self.namewidth = int(value)
                except Exception:
                    self.namewidth = 0

            elif key == "rangesep":
                self.range_sep = {
                    "dash": " - ",
                    "to": " to ",
                    "arrow": " -> ",
                    "slash": " / ",
                    "none": "-",
                    "tightdash": "-",
                }.get(value.lower(), self.range_sep)

    def _buildSeparator(self):
        if not self.separator_color:
            return self.separator

        normal = self.text_color or ""

        sep_map = {
            " | ": (" ", "|", " "),
            " · ": (" ", "·", " "),
            " ● ": (" ", "●", " "),
            " - ": (" ", "-", " "),
            " / ": (" ", "/", " "),
            ", ": ("", ",", " "),
            " ": (" ", "", ""),
        }

        left, symbol, right = sep_map.get(self.separator, ("", self.separator, ""))

        if not symbol:
            return self.separator

        return left + self.separator_color + symbol + normal + right

    def _joinColored(self, parts):
        parts = [x for x in parts if x]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]

        return self._buildSeparator().join(parts)

    def _truncateName(self, text):
        if not text or self.namewidth <= 0:
            return text

        # Approximation for Regular;30 in Enigma labels.
        # Average visible character width is roughly 14 px.
        max_chars = max(1, self.namewidth // 14)

        if len(text) <= max_chars:
            return text

        if max_chars <= 3:
            return text[:max_chars]

        return text[:max_chars - 3].rstrip() + "..."

    def _fmtClock(self, value):
        t = localtime(value)
        return "%02d:%02d" % (t.tm_hour, t.tm_min)

    def _fmtClockDuration(self, seconds):
        if seconds < 0:
            seconds = 0
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return "%02d:%02d:%02d" % (hours, minutes, secs)

    def _fmtMinutesDuration(self, seconds):
        if seconds < 0:
            seconds = 0
        minutes = seconds // 60
        return "%d min" % minutes

    def _fmtDuration(self, seconds, add_plus=False):
        text = self._fmtMinutesDuration(seconds) if self.unit == "minutes" else self._fmtClockDuration(seconds)
        if add_plus and self.minus:
            return "+" + text
        return text

    @cached
    def getText(self):
        event = self.source.event
        if event is None:
            return ""

        begin = event.getBeginTime()
        duration = event.getDuration()
        name = self._truncateName(event.getEventName() or "")
        if not begin or duration <= 0:
            return name

        end = begin + duration
        now = int(time())
        is_now = begin <= now <= end

        timerange = "%s%s%s" % (self._fmtClock(begin), self.range_sep, self._fmtClock(end))
        if is_now:
            last = self._fmtDuration(end - now, True)
            label = self.now_label
        else:
            last = self._fmtDuration(duration, False)
            label = self.next_label

        parts = []
        if label:
            parts.append(label)
        parts.append(timerange)
        parts.append(name)
        parts.append(last)
        return self._joinColored(parts)

    text = property(getText)
