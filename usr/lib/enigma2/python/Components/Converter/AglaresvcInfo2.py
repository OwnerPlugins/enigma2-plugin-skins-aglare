from Components.Converter.Converter import Converter
from enigma import iServiceInformation, iPlayableService
from Components.Element import cached
from os.path import exists

WIDESCREEN = [1, 3, 4, 7, 8, 11, 12, 15, 16]


class AglaresvcInfo2(Converter, object):
    HAS_TELETEXT = 1
    IS_MULTICHANNEL = 2
    AUDIO_STEREO = 3
    IS_CRYPTED = 4
    IS_WIDESCREEN = 5
    IS_NOT_WIDESCREEN = 6
    SUBSERVICES_AVAILABLE = 7
    XRES = 8
    YRES = 9
    APID = 10
    VPID = 11
    PCRPID = 12
    PMTPID = 13
    TXTPID = 14
    TSID = 15
    ONID = 16
    SID = 17
    FRAMERATE = 18
    TRANSFERBPS = 19
    HAS_HBBTV = 20
    AUDIOTRACKS_AVAILABLE = 21
    SUBTITLES_AVAILABLE = 22
    EDITMODE = 23
    IS_STREAM = 24
    IS_SD = 25
    IS_HD = 26
    IS_1080 = 27
    IS_720 = 28
    IS_576 = 29
    IS_480 = 30
    IS_4K = 31
    AUDIO_CODEC = 32
    VIDEO_CODEC = 33
    TEST = 34

    def __init__(self, type):
        Converter.__init__(self, type)

        updated = (iPlayableService.evUpdatedInfo,)
        video_changed = (iPlayableService.evVideoSizeChanged,)
        hbbtv_changed = (iPlayableService.evHBBTVInfo,)

        mapping = {
            'HasTeletext': (self.HAS_TELETEXT, updated),
            'IsMultichannel': (self.IS_MULTICHANNEL, updated),
            'AudioStereo': (self.AUDIO_STEREO, updated),
            'IsCrypted': (self.IS_CRYPTED, updated),
            'IsWidescreen': (self.IS_WIDESCREEN, video_changed),
            'IsNotWidescreen': (self.IS_NOT_WIDESCREEN, video_changed),
            'SubservicesAvailable': (self.SUBSERVICES_AVAILABLE, updated),
            'Xres': (self.XRES, video_changed),
            'XRES': (self.XRES, video_changed),
            'Yres': (self.YRES, video_changed),
            'YRES': (self.YRES, video_changed),
            'AudioPid': (self.APID, updated),
            'APID': (self.APID, updated),
            'VideoPid': (self.VPID, updated),
            'VPID': (self.VPID, updated),
            'PcrPid': (self.PCRPID, updated),
            'PCRPID': (self.PCRPID, updated),
            'PmtPid': (self.PMTPID, updated),
            'PMTPID': (self.PMTPID, updated),
            'TxtPid': (self.TXTPID, updated),
            'TXTPID': (self.TXTPID, updated),
            'TsId': (self.TSID, updated),
            'TSID': (self.TSID, updated),
            'OnId': (self.ONID, updated),
            'ONID': (self.ONID, updated),
            'Sid': (self.SID, updated),
            'SID': (self.SID, updated),
            'Framerate': (self.FRAMERATE, video_changed),
            'FRAMERATE': (self.FRAMERATE, video_changed),
            'TransferBPS': (self.TRANSFERBPS, updated),
            'TRANSFERBPS': (self.TRANSFERBPS, updated),
            'HasHBBTV': (self.HAS_HBBTV, hbbtv_changed),
            'HAS_HBBTV': (self.HAS_HBBTV, hbbtv_changed),
            'AudioTracksAvailable': (self.AUDIOTRACKS_AVAILABLE, updated),
            'AUDIOTRACKS_AVAILABLE': (self.AUDIOTRACKS_AVAILABLE, updated),
            'SubtitlesAvailable': (self.SUBTITLES_AVAILABLE, updated),
            'SUBTITLES_AVAILABLE': (self.SUBTITLES_AVAILABLE, updated),
            'Editmode': (self.EDITMODE, updated),
            'EDITMODE': (self.EDITMODE, updated),
            'IsStream': (self.IS_STREAM, updated),
            'IS_STREAM': (self.IS_STREAM, updated),
            'IsSD': (self.IS_SD, video_changed),
            'IS_SD': (self.IS_SD, video_changed),
            'IsHD': (self.IS_HD, video_changed),
            'IS_HD': (self.IS_HD, video_changed),
            'Is1080': (self.IS_1080, video_changed),
            'IS_1080': (self.IS_1080, video_changed),
            'Is720': (self.IS_720, video_changed),
            'IS_720': (self.IS_720, video_changed),
            'Is576': (self.IS_576, video_changed),
            'IS_576': (self.IS_576, video_changed),
            'Is480': (self.IS_480, video_changed),
            'IS_480': (self.IS_480, video_changed),
            'Is4K': (self.IS_4K, video_changed),
            'IS_4K': (self.IS_4K, video_changed),
            'AudioCodec': (self.AUDIO_CODEC, updated),
            'AUDIO_CODEC': (self.AUDIO_CODEC, updated),
            'VideoCodec': (self.VIDEO_CODEC, updated),
            'VIDEO_CODEC': (self.VIDEO_CODEC, updated),
            'Test': (self.TEST, updated),
            'TEST': (self.TEST, updated),
        }

        self.type, self.interesting_events = mapping.get(
            type, (self.IS_WIDESCREEN, video_changed))

    def getServiceInfoString(self, info, what, convert=lambda x: '%d' % x):
        v = info.getInfo(what)
        if v == -1:
            return 'N/A'
        if v == -2:
            return info.getInfoString(what)
        return convert(v)

    def _read_int_file(self, path, base=10):
        if exists(path):
            try:
                with open(path, 'r') as f:
                    return int(f.read().strip(), base)
            except Exception:
                return None
        return None

    @cached
    def getBoolean(self):
        service = self.source.service
        info = service and service.info()
        if not info:
            return False

        video_height = self._read_int_file('/proc/stb/vmpeg/0/yres', 16)
        if not video_height:
            video_height = info.getInfo(iServiceInformation.sVideoHeight)

        video_aspect = self._read_int_file('/proc/stb/vmpeg/0/aspect')
        if not video_aspect:
            video_aspect = info.getInfo(iServiceInformation.sAspect)

        if self.type == self.HAS_TELETEXT:
            tpid = info.getInfo(iServiceInformation.sTXTPID)
            return tpid != -1

        if self.type in (self.IS_MULTICHANNEL, self.AUDIO_STEREO):
            audio = service.audioTracks()
            if audio:
                for idx in range(audio.getNumberOfTracks()):
                    track_info = audio.getTrackInfo(idx)
                    description = track_info.getDescription()
                    if description in ('AC3', 'AC-3', 'DTS'):
                        return self.type == self.IS_MULTICHANNEL
                return self.type == self.AUDIO_STEREO
            return False

        if self.type == self.IS_CRYPTED:
            return info.getInfo(iServiceInformation.sIsCrypted) == 1
        if self.type == self.IS_WIDESCREEN:
            return video_aspect in WIDESCREEN
        if self.type == self.IS_NOT_WIDESCREEN:
            return video_aspect not in WIDESCREEN
        if self.type == self.SUBSERVICES_AVAILABLE:
            subservices = service.subServices()
            return bool(
                subservices and subservices.getNumberOfSubservices() > 0)
        if self.type == self.HAS_HBBTV:
            return info.getInfoString(iServiceInformation.sHBBTVUrl) != ''
        if self.type == self.AUDIOTRACKS_AVAILABLE:
            audio = service.audioTracks()
            return bool(audio and audio.getNumberOfTracks() > 1)
        if self.type == self.SUBTITLES_AVAILABLE:
            subtitle = service and service.subtitle()
            subtitlelist = subtitle and subtitle.getSubtitleList()
            return bool(subtitlelist and len(subtitlelist) > 0)
        if self.type == self.EDITMODE:
            return bool(hasattr(self.source, 'editmode')
                        and self.source.editmode)
        if self.type == self.IS_STREAM:
            return service.streamed() is not None
        if self.type == self.IS_SD:
            return video_height < 720
        if self.type == self.IS_HD:
            return 720 <= video_height < 2152
        if self.type == self.IS_1080:
            return 1000 < video_height <= 1080
        if self.type == self.IS_720:
            return 700 < video_height <= 720
        if self.type == self.IS_576:
            return 500 < video_height <= 576
        if self.type == self.IS_480:
            return 0 < video_height <= 480
        if self.type == self.IS_4K:
            return video_height >= 2152
        return False

    boolean = property(getBoolean)

    @cached
    def getText(self):
        service = self.source.service
        info = service and service.info()
        if not info:
            return ''

        if self.type == self.XRES:
            video_width = self._read_int_file('/proc/stb/vmpeg/0/xres', 16)
            if not video_width:
                try:
                    video_width = int(
                        self.getServiceInfoString(
                            info, iServiceInformation.sVideoWidth))
                except Exception:
                    return ''
            return '%d' % video_width

        if self.type == self.YRES:
            video_height = self._read_int_file('/proc/stb/vmpeg/0/yres', 16)
            if not video_height:
                try:
                    video_height = int(
                        self.getServiceInfoString(
                            info, iServiceInformation.sVideoHeight))
                except Exception:
                    return ''
            return '%d' % video_height

        if self.type == self.APID:
            return self.getServiceInfoString(
                info, iServiceInformation.sAudioPID)
        if self.type == self.VPID:
            return self.getServiceInfoString(
                info, iServiceInformation.sVideoPID)
        if self.type == self.PCRPID:
            return self.getServiceInfoString(info, iServiceInformation.sPCRPID)
        if self.type == self.PMTPID:
            return self.getServiceInfoString(info, iServiceInformation.sPMTPID)
        if self.type == self.TXTPID:
            return self.getServiceInfoString(info, iServiceInformation.sTXTPID)
        if self.type == self.TSID:
            return self.getServiceInfoString(info, iServiceInformation.sTSID)
        if self.type == self.ONID:
            return self.getServiceInfoString(info, iServiceInformation.sONID)
        if self.type == self.SID:
            return self.getServiceInfoString(info, iServiceInformation.sSID)
        if self.type == self.VIDEO_CODEC:
            return self.getServiceInfoString(
                info, iServiceInformation.sTagVideoCodec)
        if self.type == self.AUDIO_CODEC:
            return self.getServiceInfoString(
                info, iServiceInformation.sTagAudioCodec)
        if self.type == self.TEST:
            return self.getServiceInfoString(
                info, iServiceInformation.sTagMaximumBitrate)
        if self.type == self.FRAMERATE:
            video_rate = self._read_int_file('/proc/stb/vmpeg/0/framerate')
            if not video_rate:
                video_rate = int(
                    self.getServiceInfoString(
                        info, iServiceInformation.sFrameRate))
            return '%d fps' % ((video_rate + 500) // 1000)
        if self.type == self.TRANSFERBPS:
            return self.getServiceInfoString(
                info, iServiceInformation.sTransferBPS, lambda x: '%d kB/s' %
                (x // 1024))
        if self.type == self.HAS_HBBTV:
            return info.getInfoString(iServiceInformation.sHBBTVUrl)
        return ''

    text = property(getText)

    @cached
    def getValue(self):
        service = self.source.service
        info = service and service.info()
        if not info:
            return -1

        if self.type == self.XRES:
            video_width = self._read_int_file('/proc/stb/vmpeg/0/xres', 16)
            if not video_width:
                video_width = info.getInfo(iServiceInformation.sVideoWidth)
            return str(video_width)

        if self.type == self.YRES:
            video_height = self._read_int_file('/proc/stb/vmpeg/0/yres', 16)
            if not video_height:
                video_height = info.getInfo(iServiceInformation.sVideoHeight)
            return str(video_height)

        if self.type == self.FRAMERATE:
            video_rate = None
            if exists('/proc/stb/vmpeg/0/framerate'):
                try:
                    with open('/proc/stb/vmpeg/0/framerate', 'r') as f:
                        video_rate = f.read().strip()
                except Exception:
                    pass
            if not video_rate:
                video_rate = info.getInfo(iServiceInformation.sFrameRate)
            return str(video_rate)

        return -1

    value = property(getValue)

    def changed(self, what):
        if what[0] != self.CHANGED_SPECIFIC or what[1] in self.interesting_events:
            Converter.changed(self, what)

    def createVideoCodec(self, info):
        return ('MPEG2', 'AVC', 'MPEG1', 'MPEG4-VC', 'VC1', 'VC1-SM',
                'HEVC', '')[info.getInfo(iServiceInformation.sVideoType)]
