# <widget source="ServiceEvent" render="AglareNextEpgInfo2" position="970,670" size="920,280" zPosition="3" font="Regular; 26" transparent="1" backgroundColor="background" NumberOfItems="12" timeColor="yellow" />

from Components.VariableText import VariableText
from Components.Renderer.Renderer import Renderer
from enigma import eLabel, eEPGCache, eServiceReference
from time import localtime, strftime
from skin import parseColor

try:
    from gettext import pgettext
except ImportError:
    def pgettext(context, message):
        return message


class AglareNextEpgInfo2(Renderer, VariableText):
    def __init__(self):
        Renderer.__init__(self)
        VariableText.__init__(self)
        self.epgcache = eEPGCache.getInstance()
        self.numberOfItems = 1
        self.hideLabel = 0
        self.timecolor = ''
        self.labelcolor = ''
        # FIXED: Replaced invalid '00?0?0?0' with standard E2 valid hex
        self.foregroundColor = '00f0f0f0'
        self.numOfSpaces = 1

    GUI_WIDGET = eLabel

    def changed(self, what):
        self.text = ''
        reference = self.source.service
        info = reference and self.source.info
        currentEvent = self.source.getCurrentEvent()

        if not reference or not info or currentEvent is None:
            return

        spaces = ' ' * self.numOfSpaces

        try:
            self.epgcache.startTimeQuery(
                eServiceReference(reference.toString()),
                currentEvent.getBeginTime() + currentEvent.getDuration()
            )
        except Exception:
            return

        if self.numberOfItems == 1:
            event = self.epgcache.getNextTimeEntry()
            if event is None:
                return

            if self.hideLabel:
                self.text = '%s%s%s%s%s' % (
                    self.timecolor,
                    strftime('%H:%M', localtime(event.getBeginTime())),
                    spaces,
                    self.foregroundColor,
                    event.getEventName()
                )
            else:
                self.text = '%s%s%s%s%s' % (
                    self.labelcolor,
                    pgettext("now/next: 'next' event label", 'Next:'),
                    spaces,
                    self.foregroundColor,
                    event.getEventName()
                )
        else:
            for x in range(self.numberOfItems):
                event = self.epgcache.getNextTimeEntry()
                if event is None:
                    break

                self.text += '%s%s%s%s%s\n' % (
                    self.timecolor,
                    strftime('%H:%M', localtime(event.getBeginTime())),
                    spaces,
                    self.foregroundColor,
                    event.getEventName()
                )

            if not self.hideLabel:
                self.text = self.text and '%s%s\n%s' % (
                    self.labelcolor,
                    pgettext("now/next: 'next' event label", 'Next:'),
                    self.text
                ) or ''

    def applySkin(self, desktop, parent):
        attribs = []
        for attrib, value in self.skinAttributes:
            if attrib == 'NumberOfItems':
                self.numberOfItems = int(value)
                attribs.append((attrib, value))
            if attrib == 'noLabel':
                self.hideLabel = int(value)
                attribs.append((attrib, value))
            if attrib == 'numOfSpaces':
                self.numOfSpaces = int(value)
                attribs.append((attrib, value))
            if attrib == 'timeColor':
                self.timecolor = self.hex2strColor(parseColor(value).argb())
                attribs.append((attrib, value))
            if attrib == 'labelColor':
                self.labelcolor = self.hex2strColor(parseColor(value).argb())
                attribs.append((attrib, value))
            if attrib == 'foregroundColor':
                self.foregroundColor = self.hex2strColor(
                    parseColor(value).argb())
                attribs.append((attrib, value))
        for attrib, value in attribs:
            self.skinAttributes.remove((attrib, value))
        self.timecolor = self.formatColorString(self.timecolor)
        self.labelcolor = self.formatColorString(self.labelcolor)
        self.foregroundColor = self.formatColorString(self.foregroundColor)
        return Renderer.applySkin(self, desktop, parent)

    def hex2strColor(self, rgb):
        # FIXED: Generates strict 8-character valid hex digits (e.g.,
        # '00ffff00')
        return '%08x' % rgb

    def formatColorString(self, color):
        if color:
            return '%s%s' % ('\\c', color)
        else:
            return '%s%s' % ('\\c', self.foregroundColor)
