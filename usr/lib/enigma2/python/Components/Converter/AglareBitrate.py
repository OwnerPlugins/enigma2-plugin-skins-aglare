from __future__ import absolute_import
from enigma import eConsoleAppContainer, eTimer, iServiceInformation
from Components.Console import Console
from Components.Converter.Converter import Converter
from Components.Element import cached
import six
from datetime import datetime
from os import path
from Components.config import config
import platform
import os

DBG = True
DEBUG_FILE = '/tmp/AglareComponents.log'
BITRATE_BIN = None
_append_flag = False


def _find_bitrate_binary():
    arch = platform.machine()
    if arch == 'sh4':
        name = 'bitrate1_sh4'
    elif arch == 'mips':
        name = 'bitrate1_mips'
    elif arch == 'aarch64':
        name = 'bitrate_arm'
    elif arch == 'armv7l':
        name = 'bitrate_arm'
    else:
        name = 'bitrate_mips'
    for base in ['/usr/bin', '/usr/local/bin']:
        candidate = f"{base}/{name}"
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return '/usr/bin/bitrate'


def _log(msg, append=True):
    global _append_flag
    if not msg:
        return
    try:
        mode = 'a' if _append_flag and append else 'w'
        _append_flag = True
        with open(DEBUG_FILE, mode) as f:
            f.write(f'{datetime.now()}\t{msg}\n')
        if path.getsize(DEBUG_FILE) > 100000:
            with open(DEBUG_FILE, 'r+') as f:
                lines = f.readlines()
                f.seek(0)
                f.writelines(lines[10:])
                f.truncate()
    except BaseException:
        pass


class AglareBitrate(Converter, object):
    def __init__(self, type):
        Converter.__init__(self, type)
        self.mode = (type or "").strip().lower()
        self.clear_values()
        self.is_running = False
        self.is_suspended = False
        self.console = Console()
        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.on_app_closed)
        self.container.dataAvail.append(self.on_data_available)

        global BITRATE_BIN
        if BITRATE_BIN is None:
            BITRATE_BIN = _find_bitrate_binary()
        if BITRATE_BIN and path.exists(BITRATE_BIN):
            self.console.ePopen(f'chmod 755 {BITRATE_BIN}')

        self.start_timer = eTimer()
        self.start_timer.callback.append(self.start)
        self.start_timer.start(100, True)

        self.run_timer = eTimer()
        self.run_timer.callback.append(self.run_bitrate)

    def _format(self, value, prefix):
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
        v = self.vcur if 0 < self.vcur < 100000 else 0
        a = self.acur if 0 < self.acur < 100000 else 0
        if self.mode in ("video", "v"):
            return self._format(v, "V")
        if self.mode in ("audio", "a"):
            return self._format(a, "A")
        if self.mode in ("inline", "single", "oneline", "line"):
            vt = self._format(v, "V")
            at = self._format(a, "A")
            if vt and at:
                return f"{vt} {at}"
            return vt or at or ""
        vt = self._format(v, "V")
        at = self._format(a, "A")
        if vt and at:
            return f"{vt}\n{at}"
        return vt or at or ""

    text = property(getText)

    def doSuspend(self, suspended):
        """
        Called when the infobar is shown/hidden.
        We do NOT kill the bitrate process, so it keeps updating values
        even when the infobar is hidden.
        """
        if DBG:
            _log(
                f"[AglareBitrate] suspend={suspended}, current={
                    self.is_suspended}")
        self.is_suspended = suspended
        # Do NOT kill the process, do NOT clear values
        # The bitrate process continues running in background

    def start(self):
        if not self.is_running and not self.is_suspended:
            if self.source and self.source.service:
                if DBG:
                    _log("[AglareBitrate] starting run timer")
                self.run_timer.start(100, True)
            else:
                if DBG:
                    _log("[AglareBitrate] waiting for service")
                self.start_timer.start(100, True)

    def run_bitrate(self):
        if self.is_running or self.is_suspended:
            return
        if DBG:
            _log("[AglareBitrate] run_bitrate called")
        adapter = 0
        demux = 0
        try:
            stream = self.source.service.stream()
            if stream:
                data = stream.getStreamingData()
                if data:
                    demux = max(data.get('demux', 0), 0)
                    adapter = max(data.get('adapter', 0), 0)
        except Exception as e:
            if DBG:
                _log(f"[AglareBitrate] stream data error: {e}")
        try:
            info = self.source.service.info()
            vpid = info.getInfo(iServiceInformation.sVideoPID)
            apid = info.getInfo(iServiceInformation.sAudioPID)
        except Exception as e:
            if DBG:
                _log(f"[AglareBitrate] service info error: {e}")
            return
        if vpid < 0 and apid < 0:
            if DBG:
                _log("[AglareBitrate] no valid PIDs, retrying")
            self.run_timer.start(100, True)
            return
        vpid = max(vpid, 0)
        apid = max(apid, 0)
        self.clear_values()
        self.is_running = True
        cmd = f"{BITRATE_BIN} {adapter} {demux} {vpid} {apid}"
        if DBG:
            _log(f"[AglareBitrate] executing: {cmd}")
        self.container.execute(cmd)

    def clear_values(self, *args):
        if DBG:
            _log("[AglareBitrate] clear_values")
        self.is_running = False
        self.vmin = self.vmax = self.vavg = self.vcur = 0
        self.amin = self.amax = self.aavg = self.acur = 0
        self.remaining_data = ''
        self.data_lines = []
        Converter.changed(self, (self.CHANGED_POLL,))

    def on_app_closed(self, retval):
        if DBG:
            _log(
                f"[AglareBitrate] app closed, retval={retval}, suspended={
                    self.is_suspended}")
        self.is_running = False
        # If process ended and we're not suspended, restart it
        if not self.is_suspended:
            if self.source and self.source.service:
                self.run_timer.start(500, True)

    def on_data_available(self, data):
        if DBG:
            _log(f"[AglareBitrate] data: {data}")
        text = self.remaining_data + \
            (str(data) if six.PY2 else str(data, 'utf-8', 'ignore'))
        lines = text.split('\n')
        self.remaining_data = lines[-1] if lines[-1] else ''
        lines = lines[:-1] if lines[-1] else lines
        self.data_lines.extend(lines)
        if len(self.data_lines) >= 2:
            try:
                v = self.data_lines[0].split()
                if len(v) >= 4:
                    self.vmin, self.vmax, self.vavg, self.vcur = map(
                        int, v[:4])
                a = self.data_lines[1].split()
                if len(a) >= 4:
                    self.amin, self.amax, self.aavg, self.acur = map(
                        int, a[:4])
            except BaseException:
                pass
            self.data_lines = []
            Converter.changed(self, (self.CHANGED_POLL,))
