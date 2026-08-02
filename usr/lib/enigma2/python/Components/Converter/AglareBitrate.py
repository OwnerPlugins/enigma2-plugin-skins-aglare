# -*- coding: utf-8 -*-

# based on version by areq 2015-12-13 http://areq.eu.org/
# mod by Fhroma version 12.10.2018
# improved version
# fixed command to use apid instead of vpid twice
# added support for multiple display modes (video, audio, both, inline)

# fixed on openpli by Lululla 20260802
# now supports VTI, OpenPLi and OpenATV correctly

from __future__ import absolute_import
from enigma import (
    eConsoleAppContainer,
    eTimer,
    iServiceInformation,
)
from Components.Console import Console
from Components.Converter.Converter import Converter
from Components.Element import cached
from Components.config import config
import six
from datetime import datetime
from os import path
import platform
import os

DBG = True
DEBUG_FILE = '/tmp/AglareComponents.log'
BITRATE_BIN = None
_append_to_file = False
_image_type = None


def agb_debug(my_text=None, append=True, debug_file=DEBUG_FILE):
    global _append_to_file
    if not debug_file or not my_text:
        return
    try:
        mode = 'a' if _append_to_file and append else 'w'
        _append_to_file = True
        with open(debug_file, mode) as f:
            f.write(f'{datetime.now()}\t{my_text}\n')
        if path.getsize(debug_file) > 100000:
            with open(debug_file, 'r+') as f:
                lines = f.readlines()
                f.seek(0)
                f.writelines(lines[10:])
                f.truncate()
    except Exception as e:
        try:
            with open(debug_file, 'a') as f:
                f.write(f'Exception: {e}\n')
        except BaseException:
            pass


def isImageType(img_name=''):
    global _image_type
    if _image_type is None:
        feed_conf = '/etc/opkg/all-feed.conf'
        if path.exists(feed_conf):
            try:
                with open(feed_conf, 'r') as f:
                    content = f.read().lower()
                    if 'vti' in content:
                        _image_type = 'vti'
                    elif 'code.vuplus.com' in content:
                        _image_type = 'vuplus'
                    elif 'openpli-7' in content:
                        _image_type = 'openpli7'
                    elif 'openatv' in content:
                        _image_type = 'openatv'
                        if '/5.3/' in content:
                            _image_type += '5.3'
            except BaseException:
                pass
        if _image_type is None:
            if path.exists(
                    '/usr/lib/enigma2/python/Plugins/SystemPlugins/VTIPanel/'):
                _image_type = 'vti'
            elif path.exists('/usr/lib/enigma2/python/Plugins/Extensions/Infopanel/'):
                _image_type = 'openatv'
            elif path.exists('/usr/lib/enigma2/python/Blackhole'):
                _image_type = 'blackhole'
            elif path.exists('/etc/init.d/start_pkt.sh'):
                _image_type = 'pkt'
            else:
                _image_type = 'unknown'
    return img_name.lower() == _image_type.lower()


def _find_bitrate_binary():
    machine = platform.machine()
    if machine == 'sh4':
        names = ['bitrate1_sh4', 'bitrate_sh4']
    elif machine == 'mips':
        names = ['bitrate1_mips', 'bitrate_mips']
    elif machine in ('aarch64', 'armv7l'):
        names = ['bitrate_arm', 'bitrate1_arm']
    else:
        names = ['bitrate_mips', 'bitrate']
    for base in ['/usr/bin', '/usr/local/bin']:
        for name in names:
            full = f"{base}/{name}"
            if os.path.exists(full) and os.access(full, os.X_OK):
                return full
    return '/usr/bin/bitrate'


class AglareBitrate(Converter, object):
    def __init__(self, type):
        Converter.__init__(self, type)
        self.mode = (type or "").strip().lower()
        self.clear_values()
        self.is_running = False
        self.is_suspended = False
        self.my_console = Console()
        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.app_closed)
        self.container.dataAvail.append(self.data_avail)

        global BITRATE_BIN
        if BITRATE_BIN is None:
            BITRATE_BIN = _find_bitrate_binary()
        if BITRATE_BIN and path.exists(BITRATE_BIN):
            self.my_console.ePopen(f'chmod 755 {BITRATE_BIN}')

        self.start_timer = eTimer()
        self.start_timer.callback.append(self.start)
        self.start_timer.start(100, True)

        self.run_timer = eTimer()
        self.run_timer.callback.append(self.run_bitrate)

    def _format_rate(self, value, prefix):
        value = value if 0 < value < 100000 else 0
        if value <= 0:
            return ""
        try:
            unit = config.plugins.Aglare.bitrate_unit.value
        except BaseException:
            unit = "kb"
        if unit == "mb":
            return f"{prefix}: {value / 1000.0:.2f} Mb/s"
        return f"{prefix}: {value} Kb/s"

    @cached
    def getText(self):
        vcur = self.vcur if 0 < self.vcur < 100000 else 0
        acur = self.acur if 0 < self.acur < 100000 else 0

        if self.mode in ("video", "v"):
            return self._format_rate(vcur, "V")
        if self.mode in ("audio", "a"):
            return self._format_rate(acur, "A")
        if self.mode in ("inline", "single", "oneline", "line"):
            vt = self._format_rate(vcur, "V")
            at = self._format_rate(acur, "A")
            if vt and at:
                return f"{vt} {at}"
            elif vt:
                return vt
            elif at:
                return at
            return ""
        # both (default) - two lines
        vt = self._format_rate(vcur, "V")
        at = self._format_rate(acur, "A")
        if vt and at:
            return f"{vt}\n{at}"
        elif vt:
            return vt
        elif at:
            return at
        return ""

    text = property(getText)

    def doSuspend(self, suspended):
        if DBG:
            agb_debug(
                f"[AglareBitrate:suspended] self.is_suspended={
                    self.is_suspended}, suspended={suspended}")
        if not suspended:
            self.is_suspended = False
            self.start_timer.start(100, True)
        else:
            self.start_timer.stop()
            self.is_suspended = True
            self.my_console.ePopen('killall -9 bitrate', self.clear_values)

    def start(self):
        if not self.is_running and not self.is_suspended:
            if self.source and self.source.service:
                if DBG:
                    agb_debug("[AglareBitrate:start] initiate run_timer")
                self.is_running = True
                self.run_timer.start(100, True)
            else:
                if DBG:
                    agb_debug("[AglareBitrate:start] wait for service")
                self.start_timer.start(100, True)

    def run_bitrate(self):
        if DBG:
            agb_debug("[AglareBitrate:run_bitrate] >>>")

        adapter = 0
        demux = 0

        try:
            stream = self.source.service.stream()
            if stream:
                if DBG:
                    agb_debug(
                        "[AglareBitrate:run_bitrate] Collecting stream data...")
                stream_data = stream.getStreamingData()
                if stream_data:
                    demux = max(stream_data.get('demux', 0), 0)
                    adapter = max(stream_data.get('adapter', 0), 0)
        except Exception as e:
            if DBG:
                agb_debug(f"[AglareBitrate:run_bitrate] Exception stream: {e}")

        try:
            info = self.source.service.info()
            vpid = info.getInfo(iServiceInformation.sVideoPID)
            apid = info.getInfo(iServiceInformation.sAudioPID)
        except Exception as e:
            if DBG:
                agb_debug(f"[AglareBitrate:run_bitrate] Exception info: {e}")
            return

        if vpid < 0 and apid < 0:
            if DBG:
                agb_debug("[AglareBitrate:run_bitrate] no valid PIDs")
            self.run_timer.start(100, True)
            return

        vpid = max(vpid, 0)
        apid = max(apid, 0)

        self.clear_values()
        self.is_running = True

        # use apid instead of vpid twice
        if isImageType('vti'):
            cmd = f'killall -9 bitrate > /dev/null 2>&1; nice {BITRATE_BIN} {demux} {vpid} {apid}'
        else:
            # OpenPLi / OpenATV: use adapter demux vpid apid
            cmd = f'killall -9 bitrate > /dev/null 2>&1; nice {BITRATE_BIN} {adapter} {demux} {vpid} {apid}'

        if DBG:
            agb_debug(f'[AglareBitrate:run_bitrate] starting "{cmd}"')
        self.container.execute(cmd)

    def clear_values(self, *args):
        if DBG:
            agb_debug("[AglareBitrate:clear_values] >>>")
        self.is_running = False
        self.vmin = self.vmax = self.vavg = self.vcur = 0
        self.amin = self.amax = self.aavg = self.acur = 0
        self.remaining_data = ''
        self.data_lines = []
        Converter.changed(self, (self.CHANGED_POLL,))

    def app_closed(self, retval):
        if DBG:
            agb_debug(
                f"[AglareBitrate:app_closed] retval={retval}, is_suspended={
                    self.is_suspended}")
        self.is_running = False
        if self.is_suspended:
            self.clear_values()
        else:
            self.run_timer.start(100, True)

    def data_avail(self, data):
        if DBG:
            agb_debug(f"[AglareBitrate:data_avail] data '{data}'")

        data_str = self.remaining_data + \
            (str(data) if six.PY2 else str(data, 'utf-8', 'ignore'))
        lines = data_str.split('\n')

        self.remaining_data = lines[-1] if lines[-1] else ''
        lines = lines[:-1] if lines[-1] else lines

        self.data_lines.extend(lines)

        if len(self.data_lines) >= 2:
            try:
                self.vmin, self.vmax, self.vavg, self.vcur = map(
                    int, self.data_lines[0].split())
                self.amin, self.amax, self.aavg, self.acur = map(
                    int, self.data_lines[1].split())
                if DBG:
                    agb_debug(f"[AglareBitrate] V={self.vcur}, A={self.acur}")
            except ValueError:
                pass
            self.data_lines = []
            Converter.changed(self, (self.CHANGED_POLL,))
