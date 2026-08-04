#!/usr/bin/python
# -*- coding: utf-8 -*-
# skin name = Aglare-PLI-FHD
# __author__ = "Lululla"
# __copyright__ = "AGP Team"
# __modified_by__ = "MNASR"
from __future__ import absolute_import, print_function
# Standard library
from glob import glob as glob_glob
from os import remove, stat, listdir, system as os_system
from os.path import exists, join
from re import sub
import shutil
# Third-party libraries
from PIL import Image

# Enigma2 core
from enigma import ePicLoad, eTimer, loadPic

# Enigma2 Components
from Components.AVSwitch import AVSwitch
from Components.ActionMap import HelpableActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.Progress import Progress
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
from time import localtime, mktime
from Components.config import (
    configfile,
    config,
    getConfigListEntry,
    ConfigNothing,
    NoSave,
    ConfigSelection,
    ConfigSubsection
)

# Enigma2 Screens
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Standby import TryQuitMainloop

# Enigma2 Tools
from Tools.Directories import fileExists
from Tools.Downloader import downloadWithProgress
from twisted.internet import reactor
from urllib.request import Request, urlopen

# Plugin-local imports
from . import _
from .api_config import cfg, ApiKeyManager
from .DownloadControl import startPosterAutoDB, startBackdropAutoDB

skinversion = ''
api_key_manager = ApiKeyManager()
version = '7.1'


ECM_COMBO_CHOICES = [
    ('source prov caid ecm_time',
     _('Source + Prov + Caid + ECM Time')),
    ('source prov caid server port ecm_time',
     _('Source + Prov + Caid + Server + Port + ECM Time')),
    ('source caid reader ecm_time',
     _('Source + Caid + Reader + ECM Time')),
    ('source prov caid protocol server port ecm_time',
     _('Source + Prov + Caid + Protocol + Server + Port + ECM Time')),
    ('source caid reader protocol server port ecm_time',
     _('Source +  Caid + Reader + Protocol + Server + Port + ECM Time')),
    ('caid reader protocol server ecm_time',
     _('Caid + Reader + Protocol + Server + ECM Time')),
    ('caid protocol server ecm_time',
     _('Caid + Protocol + Server + ECM Time')),
]


def ensure_myemupara_config():
    if not hasattr(config.plugins, 'Aglare'):
        config.plugins.Aglare = ConfigSubsection()

    if not hasattr(config.plugins.Aglare, 'myemupara'):
        config.plugins.Aglare.myemupara = ConfigSelection(
            default='source prov caid ecm_time',
            choices=ECM_COMBO_CHOICES
        )

    if not hasattr(cfg, 'myemupara'):
        cfg.myemupara = config.plugins.Aglare.myemupara

    return cfg.myemupara


ensure_myemupara_config()

"""
HELPER
🔑 How the API Key Loading System Works
This plugin uses a dynamic system to load API keys for various external services
(e.g., TMDB, FANART, THETVDB, OMDB, IMDB, ELCINEMA, GOOGLE, PROGRAMMETV, MOLOTOV)
from skin files in the Enigma2 environment.

📁 Configuration Structure
API configurations are defined in a dictionary called API_CONFIG, which contains the following for each API:

skin_file: the expected filename in the skin directory (e.g., tmdbkey)
default_key: fallback key if no file is found
var_name: the variable name to bind the key globally

🔁 Automatic Global Assignment
When the plugin is initialized, it automatically sets global variables for both:

The path to the API key file in the skin directory (e.g., tmdb_skin)
The API key itself, using either the default or the value read from the file

📥 Dynamic Loading from Skin
The function load_api_keys() checks if the skin-specific key files exist,
and if they do, loads their contents and overrides the global default keys.
This allows the plugin to use custom API keys depending on the active skin.

"""

""" assign path """


def calcTime(hours, minutes):
    now_time = localtime()
    ret_time = mktime(
        (now_time.tm_year,
         now_time.tm_mon,
         now_time.tm_mday,
         hours,
         minutes,
         0,
         now_time.tm_wday,
         now_time.tm_yday,
         now_time.tm_isdst))
    return ret_time


def isMountedInRW(mount_point):
    with open("/proc/mounts", "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) > 1 and parts[1] == mount_point:
                return True
    return False


path_poster = "/tmp/poster"
patch_backdrop = "/tmp/backdrop"

if exists("/media/usb") and isMountedInRW("/media/usb"):
    path_poster = "/media/usb/poster"
    patch_backdrop = "/media/usb/backdrop"

elif exists("/media/hdd") and isMountedInRW("/media/hdd"):
    path_poster = "/media/hdd/poster"
    patch_backdrop = "/media/hdd/backdrop"

elif exists("/media/mmc") and isMountedInRW("/media/mmc"):
    path_poster = "/media/mmc/poster"
    patch_backdrop = "/media/mmc/backdrop"

""" end assign path """

# constants
cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "").strip()
fullurl = None


# Mapping of color values to directory names
COLOR_DIR_MAPPING = {
    'color0': 'Default',
    'color1': 'Black',
    'color2': 'Brown',
    'color3': 'Green',
    'color4': 'Magenta',
    'color5': 'Blue',
    'color6': 'Red',
    'color7': 'Purple',
    'color8': 'Green2',
    'color9': 'Mix1',
    # Add more mappings as needed
}


class AglareSetup(ConfigListScreen, Screen):
    skin = '''
            <screen name="AglareSetup" position="160,220" size="1600,680" title="Aglare-FHD-PLI Skin Controler" backgroundColor="back">
                <eLabel font="Regular; 24" foregroundColor="#00ff4A3C" halign="center" position="20,620" size="120,40" text="Cancel" />
                <eLabel font="Regular; 24" foregroundColor="#0056C856" halign="center" position="310,620" size="120,40" text="Save" />
                <eLabel font="Regular; 24" foregroundColor="#00fbff3c" halign="center" position="600,620" size="120,40" text="Update" />
                <eLabel font="Regular; 24" foregroundColor="#00403cff" halign="center" position="860,620" size="120,40" text="Info" />
                <widget name="Preview" position="1057,146" size="498,280" zPosition="1" />
                <widget name="config" font="Regular; 24" itemHeight="50" position="5,5" scrollbarMode="showOnDemand" size="990,600" />
                <widget name="description" position="1057,445" size="498,150" font="Regular;24" foregroundColor="white" backgroundColor="#12000000" transparent="0" valign="top" halign="left" />
            </screen>
        '''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.version = skinversion
        self.skinFile = join(
            "/usr/share/enigma2",
            config.skin.primary_skin.value)
        print("self.skinFile: {}".format(self.skinFile))

        if cfg.ImageGroup.value == 'openpli':
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample_pli/'
        else:
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample/'
        self['Preview'] = Pixmap()
        self['description'] = Label('')
        self.onChangedEntry = []
        self.setup_title = (cur_skin)
        list = []
        section = '--------------------------( GENERAL SKIN  SETUP )-----------------------'
        list.append(getConfigListEntry(section))
        section = '--------------------------( APIKEY SKIN SETUP )-----------------------'
        list.append(getConfigListEntry(section))
        ConfigListScreen.__init__(
            self,
            list,
            session=self.session,
            on_change=self.changedEntry)
        self["actions"] = HelpableActionMap(
            self,
            "AglareActions",
            {
                "left": self.keyLeft,
                "right": self.keyRight,
                "down": self.keyDown,
                "up": self.keyUp,
                "cancel": self.keyExit,
                "red": self.keyExit,
                "green": self.keySave,
                "yellow": self.checkforUpdate,
                "showVirtualKeyboard": self.KeyText,
                "ok": self.keyRun,
                "info": self.info,
                "blue": self.info,
                "tv": self.Checkskin,
                "back": self.keyExit,
                "text": self.KeyText
            },
            -1
        )
        self.createSetup()
        self.PicLoad = ePicLoad()
        self.Scale = AVSwitch().getFramebufferScale()
        self.onLayoutFinish.append(self.ShowPicture)
        self.onLayoutFinish.append(self.__layoutFinished)
        self.onLayoutFinish.append(self.updateDescription)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def passs(self, foo):
        pass

    def getCurrentDescription(self):
        try:
            current = self["config"].getCurrent()
            if current and len(current) > 2 and current[2]:
                return str(current[2])
            return _("No description available for this option.")
        except Exception as e:
            print("getCurrentDescription error:", e)
            return ""

    def updateDescription(self):
        try:
            self["description"].setText(self.getCurrentDescription())
        except Exception as e:
            print("updateDescription error:", e)

    def KeyText(self):
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        sel = self["config"].getCurrent()
        if sel:
            self.session.openWithCallback(
                self.VirtualKeyBoardCallback,
                VirtualKeyBoard,
                title=self["config"].getCurrent()[0],
                text=self["config"].getCurrent()[1].value)

    def VirtualKeyBoardCallback(self, callback=None):
        if callback is not None and len(callback):
            self["config"].getCurrent()[1].value = callback
            self["config"].invalidate(self["config"].getCurrent())
        return

    def _sync_infobar_dependents_for_style(self):
        current_style = cfg.InfobarStyle.value
        if current_style == 'infobar_base6':
            cfg.InfobarECM.value = 'infobar_ecm_off'
            cfg.InfobarPosterx.value = 'infobar_posters_posterx_off'
            cfg.InfobarXtraevent.value = 'infobar_posters_xtraevent_off'
        elif current_style == 'infobar_base5':
            cfg.InfobarECM.value = 'infobar_ecm_off'
            if cfg.InfobarPosterx.value not in (
                'infobar_posters_posterx_off',
                    'infobar_posters_posterx_cd'):
                cfg.InfobarPosterx.value = 'infobar_posters_posterx_off'
            if cfg.InfobarXtraevent.value not in (
                'infobar_posters_xtraevent_off',
                    'infobar_posters_xtraevent_cd'):
                cfg.InfobarXtraevent.value = 'infobar_posters_xtraevent_off'

    def createSetup(self):
        try:
            self.editListEntry = None
            is_ecm_on = (cfg.InfobarECM.value == 'infobar_ecm_on')

            current_style = cfg.InfobarStyle.value
            is_style5_cd = (current_style == 'infobar_base5')
            is_style6_default = (current_style == 'infobar_base6')

            # Match Aglare-FHD behavior:
            # Style5 is CD-only for PosterX/Xtraevent and forces ECM OFF.
            # Style6 is clean/default and forces ECM, PosterX and Xtraevent
            # OFF.
            if current_style in ('infobar_base5', 'infobar_base6'):
                self._sync_infobar_dependents_for_style()

            is_ecm_on = (cfg.InfobarECM.value == 'infobar_ecm_on')

            # Handle InfobarPosterx choices
            if is_style6_default:
                posterx_choices = [
                    ('infobar_posters_posterx_off', _('OFF')),
                ]
            elif is_style5_cd:
                posterx_choices = [
                    ('infobar_posters_posterx_off', _('OFF')),
                    ('infobar_posters_posterx_cd', _('CD')),
                ]
            elif is_ecm_on:
                posterx_choices = [
                    ('infobar_posters_posterx_off', _('OFF')),
                    ('infobar_posters_posterx_ecm', _('1 poster'))
                ]
            else:
                posterx_choices = [
                    ('infobar_posters_posterx_off', _('OFF')),
                    ('infobar_posters_posterx_on', _('ON')),
                    ('infobar_posters_posterx_on_all', _('TEST')),
                ]

            if cfg.InfobarPosterx.value not in [v for v, _ in posterx_choices]:
                cfg.InfobarPosterx.value = posterx_choices[0][0]
            cfg.InfobarPosterx.setChoices(posterx_choices)

            # Handle InfobarXtraevent choices
            if is_style6_default:
                xtraevent_choices = [
                    ('infobar_posters_xtraevent_off', _('OFF')),
                ]
            elif is_style5_cd:
                xtraevent_choices = [
                    ('infobar_posters_xtraevent_off', _('OFF')),
                    ('infobar_posters_xtraevent_cd', _('CD')),
                ]
            elif is_ecm_on:
                xtraevent_choices = [
                    ('infobar_posters_xtraevent_off', _('OFF')),
                    ('infobar_posters_xtraevent_ecm', _('1 poster'))
                ]
            else:
                xtraevent_choices = [
                    ('infobar_posters_xtraevent_off', _('OFF')),
                    ('infobar_posters_xtraevent_on', _('ON')),
                ]
                if current_style == 'infobar_base1':
                    xtraevent_choices.append(
                        ('infobar_posters_xtraevent_info', _('Backdrop')))

            if cfg.InfobarXtraevent.value not in [
                    v for v, _ in xtraevent_choices]:
                cfg.InfobarXtraevent.value = xtraevent_choices[0][0]
            cfg.InfobarXtraevent.setChoices(xtraevent_choices)

            # Handle InfobarStyle choices
            infobar_style_choices = [
                ('infobar_base1', _('Default')),
                ('infobar_base2', _('Style2')),
                ('infobar_base3', _('Style3')),
                ('infobar_base4', _('Style4')),
                ('infobar_base5', _('Style5 CD')),
                ('infobar_base6', _('Style6')),
            ]

            if current_style not in [v for v, _ in infobar_style_choices]:
                cfg.InfobarStyle.value = 'infobar_base1'
            cfg.InfobarStyle.setChoices(infobar_style_choices)

            list = []
            section = '-------------------------( GENERAL SKIN  SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(
                getConfigListEntry(
                    _('Image Compatibility Group:'),
                    cfg.ImageGroup,
                    _('Select the target image base group (OpenPLi vs Others).')))
            list.append(
                getConfigListEntry(
                    _('Color Style:'),
                    cfg.colorSelector,
                    _('Select the main color preset used by the skin.')))
            list.append(
                getConfigListEntry(
                    _('Select Your Font:'),
                    cfg.FontStyle,
                    _('Select the font package used by the generated skin.')))
            list.append(
                getConfigListEntry(
                    _('Skin Style:'),
                    cfg.skinSelector,
                    _('Select the base skin layout file.')))
            # list.append(getConfigListEntry(_('Support InfoBar SoftCSA:'), cfg.InfobarSoftCSA))
            list.append(getConfigListEntry(_('InfoBar Style:'), cfg.InfobarStyle, _(
                'Select infobar layout. Style5 forces ECM off and allows only OFF/CD poster modes. Style6 forces ECM, PosterX, and Xtraevent off.')))
            list.append(
                getConfigListEntry(
                    _('InfoBar ECM:'),
                    cfg.InfobarECM,
                    _('Show or hide ECM information in the infobar.')))
            list.append(getConfigListEntry(_('InfoBar PosterX:'), cfg.InfobarPosterx, _(
                'Select PosterX display mode for the infobar. Available choices depend on the selected infobar style and ECM mode.')))
            list.append(getConfigListEntry(_('InfoBar Xtraevent:'), cfg.InfobarXtraevent, _(
                'Select XtraEvent display mode for the infobar. Available choices depend on the selected infobar style and ECM mode.')))
            list.append(
                getConfigListEntry(
                    _('InfoBar Date:'),
                    cfg.InfobarDate,
                    _('Show or hide the date panel in the infobar.')))
            list.append(
                getConfigListEntry(
                    _('InfoBar Weather:'),
                    cfg.InfobarWeather,
                    _('Select weather provider display for the infobar.')))
            list.append(
                getConfigListEntry(
                    _('SecondInfobar Style:'),
                    cfg.SecondInfobarStyle,
                    _('Select second infobar layout.')))
            list.append(
                getConfigListEntry(
                    _('SecondInfobar Weather:'),
                    cfg.SecondInfobarWeather,
                    _('Select weather provider display for the second infobar.')))
            list.append(
                getConfigListEntry(
                    _('SecondInfobar Posterx:'),
                    cfg.SecondInfobarPosterx,
                    _('Show or hide PosterX in the second infobar.')))
            list.append(
                getConfigListEntry(
                    _('SecondInfobar Xtraevent:'),
                    cfg.SecondInfobarXtraevent,
                    _('Show or hide XtraEvent in the second infobar.')))
            list.append(
                getConfigListEntry(
                    _('ChannelSelection Style:'),
                    cfg.ChannSelector,
                    _('Select channel selection screen style.')))
            list.append(
                getConfigListEntry(
                    _('Channel Foreground Color:'),
                    cfg.ChannForegroundColor,
                    _('Select channel list foreground color.')))
            list.append(
                getConfigListEntry(
                    _('Channel Selected Foreground Color:'),
                    cfg.ChannForegroundColorSelected,
                    _('Select channel list selected foreground color.')))
            list.append(
                getConfigListEntry(
                    _('Channel Description Color:'),
                    cfg.ChannServiceDescriptionColor,
                    _('Select channel list event description color.')))
            list.append(
                getConfigListEntry(
                    _('Channel Selected Description Color:'),
                    cfg.ChannServiceDescriptionColorSelected,
                    _('Select selected channel event description color.')))
            list.append(
                getConfigListEntry(
                    _('EventView Style:'),
                    cfg.EventView,
                    _('Select event view screen style.')))
            list.append(
                getConfigListEntry(
                    _('VolumeBar Style:'),
                    cfg.VolumeBar,
                    _('Select volume bar style.')))
            list.append(
                getConfigListEntry(
                    _('EMC screens Style:'),
                    cfg.Emc,
                    _('Select EMC style.')))
            list.append(getConfigListEntry(_('ECM Short Format:'), cfg.myemupara, _(
                'Select which ECM fields are shown when the skin uses Short MYEMUPARA.')))
            list.append(
                getConfigListEntry(
                    _('Bitrate Unit:'),
                    cfg.bitrate_unit,
                    _('Choose whether bitrate is shown in Kb/s or Mb/s.')))
            list.append(
                getConfigListEntry(
                    _('Support SubsSupportPro Skins:'),
                    cfg.Subssupportproskins,
                    _('ON/OFF SubsSupportPro Skins.')))
            list.append(
                getConfigListEntry(
                    _('Support E2iplayer Skins:'),
                    cfg.E2iplayerskins,
                    _('Enable or disable bundled E2iPlayer screens.')))

            section = '--------------------------( UTILITY SKIN SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))

            list.append(getConfigListEntry(_('Choice device download image folder'), cfg.xpath, _(
                "This operation assign device path folder to download image (Poster-Backdrop)")))
            list.append(
                getConfigListEntry(
                    _('Remove all png (poster - backdrop) (OK)'),
                    cfg.png,
                    _("This operation remove all png from folder device (Poster-Backdrop)")))

            section = '---------------------------( APIKEY SKIN SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('Enable Rating Star:'), cfg.rating_source, _(
                "This operation enable the display of rating stars for events, based on the selected rating source.")))
            list.append(getConfigListEntry(_('Enable Parental Icons:'), cfg.info_parental_mode, _(
                "Show parental guidance icons on events to indicate content rating and age suitability.")))
            list.append(getConfigListEntry(_('Enable Display InfoEvents:'), cfg.info_display_mode, _(
                "Enable the display of extended event information, including full cast, crew, plot details, and other metadata, in the info widget.")))
            list.append(getConfigListEntry(_('Enable Display Genre icons:'), cfg.genre_source, _(
                "Show icons representing the genre of each event (e.g., action, comedy, drama)")))
            list.append(
                getConfigListEntry(
                    _('Enable Display XMC Poster:'),
                    cfg.xemc_poster,
                    _("Show poster from movie in local folder")))
            list.append(
                getConfigListEntry(
                    "API KEY SETUP:",
                    cfg.actapi,
                    _("Settings Apikey Server")))

            if cfg.actapi.value:
                for api in api_key_manager.API_CONFIG:
                    upper = api.upper()
                    list.append(getConfigListEntry(
                        "{}:".format(upper),
                        getattr(cfg, api),
                        _("Activate/Deactivate {}".format(upper))
                    ))

                    if getattr(cfg, api).value:
                        cfg_ap = api_key_manager.API_CONFIG[api]
                        list.append(getConfigListEntry(
                            "-- Load Key {}".format(upper),
                            cfg_ap['load_action'],
                            _("Load from /tmp/{}key.txt".format(api))
                        ))
                        list.append(getConfigListEntry(
                            "-- Set key {}".format(upper),
                            cfg_ap['config_entry'],
                            _("Personal API key for {}".format(upper))
                        ))

                list.append(
                    getConfigListEntry(
                        "ELCINEMA:",
                        cfg.elcinema,
                        _("Activate or deactivate ELCINEMA as a metadata provider.")))
                list.append(
                    getConfigListEntry(
                        "GOOGLE:",
                        cfg.google,
                        _("Activate or deactivate GOOGLE as a metadata provider.")))
                list.append(
                    getConfigListEntry(
                        "IMDB:",
                        cfg.imdb,
                        _("Activate or deactivate IMDB as a metadata provider.")))
                list.append(
                    getConfigListEntry(
                        "MOLOTOV:",
                        cfg.molotov,
                        _("Activate or deactivate MOLOTOV as a metadata provider.")))
                list.append(getConfigListEntry("PROGRAMMETV:", cfg.programmetv, _(
                    "Activate or deactivate PROGRAMMETV as a metadata provider.")))
                section = '------------------------------------------------------------------------'
                list.append((_(section), NoSave(ConfigNothing())))
                if cfg.actapi.value:
                    list.append(getConfigListEntry("Use Cache on download:", cfg.cache, _(
                        "Enable or disable caching during event download to speed up repeated searches.")))
                    list.append(
                        getConfigListEntry(
                            _('Download now poster'),
                            cfg.download_now_poster,
                            _("Start downloading poster immediately")))
                    list.append(
                        getConfigListEntry(
                            _('Automatic download of poster'),
                            cfg.pstdown,
                            _("Automatically fetch posters for favorite events based on EPG")))
                    if cfg.pstdown.value is True:
                        list.append(
                            getConfigListEntry(
                                _('Set Time our - minute for Poster download'),
                                cfg.pscan_time,
                                _("Configure the delay time (in minutes) before starting the automatic poster download")))
                    list.append(
                        getConfigListEntry(
                            _('Download now backdrop'),
                            cfg.download_now_backdrop,
                            _("Start downloading backdrop immediately")))
                    list.append(
                        getConfigListEntry(
                            _('Automatic download of backdrop'),
                            cfg.bkddown,
                            _("Automatically fetch backdrop for favorite events based on EPG")))
                    if cfg.bkddown.value is True:
                        list.append(
                            getConfigListEntry(
                                _('Set Time our - minute for Backdrop download'),
                                cfg.bscan_time,
                                _("Configure the delay time (in minutes) before starting the automatic poster download")))

            self["config"].list = list
            self["config"].l.setList(list)
            self.updateDescription()
        except KeyError:
            print("keyError")

    def Checkskin(self):
        self.session.openWithCallback(
            self.Checkskin2,
            MessageBox,
            _("[Checkskin] This operation checks if the skin has its components (not guaranteed)...\nDo you really want to continue?"),
            MessageBox.TYPE_YESNO)

    def Checkskin2(self, answer):
        if answer:
            from .addons import checkskin
            self.check_module = eTimer()
            check = checkskin.check_module_skin()
            try:
                self.check_module_conn = self.check_module.timeout.connect(
                    check)
            except BaseException:
                self.check_module.callback.append(check)
            self.check_module.start(100, True)
            self.openVi()

    def openVi(self, callback=''):
        from .addons.File_Commander import File_Commander
        user_log = '/tmp/my_debug.log'
        if fileExists(user_log):
            self.session.open(File_Commander, user_log)

    def GetPicturePath(self):
        returnValue = self['config'].getCurrent()[1].value
        PicturePath = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/screens/default.jpg'
        if not isinstance(returnValue, str):
            returnValue = PicturePath
        path = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/screens/' + returnValue + '.jpg'
        if fileExists(path):
            return convert_image(path)
        else:
            return convert_image(PicturePath)

    def UpdatePicture(self):
        self.onLayoutFinish.append(self.ShowPicture)

    def ShowPicture(self, data=None):
        if self["Preview"].instance:
            size = self['Preview'].instance.size()
            if size.isNull():
                size.setWidth(498)
                size.setHeight(280)

            pixmapx = self.GetPicturePath()
            if not fileExists(pixmapx):
                print("Immagine non trovata:", pixmapx)
                return
            png = loadPic(pixmapx, size.width(), size.height(), 0, 0, 0, 1)
            self["Preview"].instance.setPixmap(png)

    def DecodePicture(self, PicInfo=None):
        ptr = self.PicLoad.getData()
        if ptr is not None:
            self["Preview"].instance.setPixmap(ptr)
            self["Preview"].instance.show()
        return

    def UpdateComponents(self):
        self.UpdatePicture()

    def info(self):
        aboutbox = self.session.open(
            MessageBox,
            _("Setup Aglare Skin\nfor {0} v.{1}\n\nby Lululla @2020\n\nSupport forum on linuxsat-support.com\n\nSkinner creator: Odem2014 ").format(
                cur_skin,
                version),
            MessageBox.TYPE_INFO)
        aboutbox.setTitle(_("Setup Aglare Skin Info"))

    def removPng(self):
        self.session.openWithCallback(
            self.removPng2,
            MessageBox,
            _("[RemovePng] This operation will remove all PNGs from the device folder (Poster-Backdrop)...\nDo you really want to continue?"),
            MessageBox.TYPE_YESNO)

    def removPng2(self, result):
        if result:
            print('from remove png......')
            removePng()
            print('png are removed')
            aboutbox = self.session.open(
                MessageBox,
                _('All png are removed from folder!'),
                MessageBox.TYPE_INFO)
            aboutbox.setTitle(_('Info...'))

    def keyRun(self):
        sel = self["config"].getCurrent()[1]
        if not sel:
            return

        action_map = {
            cfg.png: self.handle_png,
            **{
                getattr(cfg, f"load_{api}_api"):
                lambda x=api: self.handle_api_load(x)
                for api in api_key_manager.API_CONFIG
            },
            **{
                getattr(cfg, f"{api}_api"): self.KeyText
                for api in api_key_manager.API_CONFIG
            },

            cfg.download_now_poster: lambda: self.handle_download_now_poster(),
            cfg.download_now_backdrop: lambda: self.handle_download_now_backdrop(),
        }

        handler = action_map.get(sel)
        if handler:
            handler()

    def handle_download_now_poster(self):
        try:
            current_session = self.session

            cfg.download_now_poster.value = False
            cfg.download_now_poster.save()

            # We get ALL providers enabled, even with default keys
            enabled_providers = {}
            using_default_keys = False

            for api, cfgdata in api_key_manager.API_CONFIG.items():
                enabled = getattr(config.plugins.Aglare, api).value
                api_value = cfgdata["config_entry"].value
                is_default = (api_value == cfgdata["default_key"])

                if enabled:
                    enabled_providers[api] = True
                    if is_default:
                        using_default_keys = True

            if not enabled_providers:
                raise ValueError(_("No active providers enabled"))

            if using_default_keys:
                current_session.open(
                    MessageBox,
                    _("Warning: You are using default API keys!\nWe strongly recommend configuring your own API keys in the plugin settings."),
                    MessageBox.TYPE_INFO,
                    timeout=5)

            current_session.open(
                MessageBox,
                _("Poster download will start in 2 minutes.\nYou can safely exit this menu."),
                MessageBox.TYPE_INFO,
                timeout=5)

            def _start_download(session_ref=current_session):
                try:
                    startPosterAutoDB(enabled_providers, session=session_ref)
                except Exception as e:
                    reactor.callFromThread(
                        session_ref.open,
                        MessageBox,
                        _("Error: {}").format(str(e)),
                        MessageBox.TYPE_ERROR
                    )

            reactor.callLater(120, reactor.callInThread, _start_download)

        except Exception as e:
            self.session.open(
                MessageBox,
                _("Poster download error: {}").format(str(e)),
                MessageBox.TYPE_ERROR
            )

    def handle_download_now_backdrop(self):
        try:
            current_session = self.session

            cfg.download_now_backdrop.value = False
            cfg.download_now_backdrop.save()

            # Get all enabled providers, including those using default keys
            enabled_providers = {}
            using_default_keys = False

            for api, cfgdata in api_key_manager.API_CONFIG.items():
                enabled = getattr(config.plugins.Aglare, api).value
                api_value = cfgdata["config_entry"].value
                is_default = (api_value == cfgdata["default_key"])

                if enabled:
                    enabled_providers[api] = True
                    if is_default:
                        using_default_keys = True

            if not enabled_providers:
                raise ValueError(_("No active providers enabled"))

            if using_default_keys:
                current_session.open(
                    MessageBox,
                    _("Warning: You are using default API keys!\nWe strongly recommend configuring your own API keys in the plugin settings."),
                    MessageBox.TYPE_INFO,
                    timeout=5)

            current_session.open(
                MessageBox,
                _("Backdrop download will start in 2 minutes.\nYou can safely exit this menu."),
                MessageBox.TYPE_INFO,
                timeout=5)

            def _start_download(session_ref=current_session):
                try:
                    startBackdropAutoDB(enabled_providers, session=session_ref)
                except Exception as e:
                    reactor.callFromThread(
                        session_ref.open,
                        MessageBox,
                        _("Error: {}").format(str(e)),
                        MessageBox.TYPE_ERROR
                    )

            reactor.callLater(120, reactor.callInThread, _start_download)

        except Exception as e:
            self.session.open(
                MessageBox,
                _("Backdrop download error: {}").format(str(e)),
                MessageBox.TYPE_ERROR
            )

    def handle_api_load(self, api, answer=None):
        cfg = api_key_manager.API_CONFIG[api]
        api_file = f"/tmp/{api}key.txt"
        skin_file = getattr(api_key_manager, f"{api}_skin")

        if answer is None:
            if fileExists(api_file):
                file_info = stat(api_file)
                if file_info.st_size > 0:
                    self.session.openWithCallback(
                        lambda answer: self.handle_api_load(
                            api, answer), MessageBox, _("Import key {0} from {1}?").format(
                            api.upper(), api_file))
                else:
                    self.session.open(
                        MessageBox,
                        _("The file %s is empty.") % api_file,
                        MessageBox.TYPE_INFO,
                        timeout=4
                    )
            else:
                self.session.open(
                    MessageBox,
                    _("The file %s was not found.") % api_file,
                    MessageBox.TYPE_INFO,
                    timeout=4
                )
        elif answer:
            try:
                with open(api_file, 'r') as f:
                    fpage = f.readline().strip()

                if not fpage:
                    raise ValueError(_("Key empty"))

                with open(skin_file, "w") as t:
                    t.write(fpage)

                cfg['config_entry'].setValue(fpage)
                cfg['config_entry'].save()

                self.session.open(
                    MessageBox,
                    _("%s key imported!") % api.upper(),
                    MessageBox.TYPE_INFO,
                    timeout=4
                )

            except Exception as e:
                self.session.open(
                    MessageBox,
                    _("Error {0}: {1}").format(api.upper(), str(e)),
                    MessageBox.TYPE_ERROR,
                    timeout=4
                )

        self.createSetup()

    def handleKeyActions(self):
        self.createSetup()
        self.ShowPicture()
        sel = self["config"].getCurrent()[1]
        if not sel:
            return

        download_actions = {
            cfg.download_now_poster: self.handle_download_now_poster,
            cfg.download_now_backdrop: self.handle_download_now_backdrop,
            cfg.png: self.handle_png
        }

        if sel in download_actions:
            sel.value = True
            sel.save()
            download_actions[sel]()
            return
        reset_map = {
            cfg.png: (cfg.png, self.handle_png),
            **{
                getattr(cfg, "load_%s_api" % api):
                (getattr(cfg, "load_%s_api" % api), self.make_api_handler(api))
                for api in api_key_manager.API_CONFIG
            }
        }

        entry_data = reset_map.get(sel)
        if entry_data:
            config_entry, handler = entry_data
            config_entry.setValue(0)
            config_entry.save()
            handler()

    def make_api_handler(self, api):
        def handler():
            self.handle_api_load(api)
        return handler

    def handle_png(self):
        self.removPng()
        cfg.png.setValue(0)
        cfg.png.save()

    def keyLeft(self):
        ConfigListScreen.keyLeft(self)
        self.handleKeyActions()

    def keyRight(self):
        ConfigListScreen.keyRight(self)
        self.handleKeyActions()

    def keyDown(self):
        self['config'].instance.moveSelection(self['config'].instance.moveDown)
        self.createSetup()
        self.ShowPicture()
        self.updateDescription()

    def keyUp(self):
        self['config'].instance.moveSelection(self['config'].instance.moveUp)
        self.createSetup()
        self.ShowPicture()
        self.updateDescription()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        self.updateDescription()
        for x in self.onChangedEntry:
            x()

    def getCurrentValue(self):
        if self["config"].getCurrent() and len(
                self["config"].getCurrent()) > 0:
            return str(self["config"].getCurrent()[1].getText())
        return ""

    def getCurrentEntry(self):
        return self["config"].getCurrent() and self["config"].getCurrent()[
            0] or ""

    def createSummary(self):
        from Screens.Setup import SetupSummary
        return SetupSummary

    def modify_channel_colors(self, content):
        """Replace channel list colors only inside the marked modification block."""
        marker = "<!--channelselectionmodification/-->"
        first = content.find(marker)
        if first == -1:
            print("[Aglare] Channel color block marker not found; colors unchanged.")
            return content

        second = content.find(marker, first + len(marker))
        if second == -1:
            print(
                "[Aglare] Channel color block end marker not found; colors unchanged.")
            return content

        block_start = first + len(marker)
        block = content[block_start:second]

        fg_color = cfg.ChannForegroundColor.value
        fg_selected_color = cfg.ChannForegroundColorSelected.value
        desc_color = cfg.ChannServiceDescriptionColor.value
        desc_selected_color = cfg.ChannServiceDescriptionColorSelected.value

        block = sub(
            r'foregroundColor="[^"]*"',
            f'foregroundColor="{fg_color}"',
            block)
        block = sub(
            r'foregroundColorSelected="[^"]*"',
            f'foregroundColorSelected="{fg_selected_color}"',
            block)
        block = sub(
            r'colorServiceDescription="[^"]*"',
            f'colorServiceDescription="{desc_color}"',
            block)
        block = sub(
            r'colorServiceDescriptionSelected="[^"]*"',
            f'colorServiceDescriptionSelected="{desc_selected_color}"',
            block)

        return content[:block_start] + block + content[second:]

    def keySave(self):
        self._sync_infobar_dependents_for_style()

        # --- Determine version file path from active skin ---
        cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "")
        if cur_skin == "Aglare-FHD-PLI":
            version_file = "/usr/share/enigma2/Aglare-FHD-PLI/.Aglare-FHD-PLI"
        elif cur_skin == "Aglare-FHD":
            version_file = "/usr/share/enigma2/Aglare-FHD/.Aglare-FHD"
        else:
            self.session.open(MessageBox, _("Skin not supported."), MessageBox.TYPE_ERROR)
            self.close()
            return

        # If version file doesn't exist, create it with current version
        if not fileExists(version_file):
            try:
                with open(version_file, 'w') as f:
                    f.write(version)   # 'version' is defined globally as '7.1'
                print("Version file created:", version_file)
            except Exception as e:
                self.session.open(MessageBox, _("Cannot create version file: {}").format(str(e)), MessageBox.TYPE_ERROR)
                self.close()
                return

        self.version = version_file
        print("version skin: {}".format(self.version))

        # Update the path depending on the image group selected
        if cfg.ImageGroup.value == 'openpli':
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample_pli/'
        else:
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample/'

        def load_xml_to_skin_lines(file_path):
            try:
                with open(file_path, 'r') as file:
                    return file.readlines()
            except FileNotFoundError:
                return []

        print("File exists, proceeding with saving...")
        for x in self['config'].list:
            if len(x) > 1:
                print("Saving {}".format(x[1]))
                x[1].save()

        cfg.save()
        configfile.save()

        try:
            skin_lines = []

            xml_files = [
                'head-' + cfg.colorSelector.value,
                'font-' + cfg.FontStyle.value,

                'infobar-' + cfg.InfobarStyle.value,
                'infobar-' + cfg.InfobarECM.value,
                'infobar-' + cfg.InfobarPosterx.value,
                'infobar-' + cfg.InfobarXtraevent.value,
                'infobar-' + cfg.InfobarDate.value,
                'infobar-' + cfg.InfobarWeather.value,

                'secondinfobar-' + cfg.SecondInfobarStyle.value,
                'secondinfobar-' + cfg.SecondInfobarWeather.value,
                'secondinfobar-' + cfg.SecondInfobarPosterx.value,
                'secondinfobar-' + cfg.SecondInfobarXtraevent.value,

                'eventview-' + cfg.EventView.value,
                'vol-' + cfg.VolumeBar.value,
                'emc-' + cfg.Emc.value,
                'subssupportpro-' + cfg.Subssupportproskins.value,
                'e2iplayer-' + cfg.E2iplayerskins.value,
            ]

            # Load all files up to secondinfobar
            for filename in xml_files[:12]:
                skin_lines.extend(load_xml_to_skin_lines(self.previewFiles + filename + '.xml'))

            # Special management for channellists
            cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "")
            if cur_skin == "Aglare-FHD-PLI":
                # Copy images from the color directory
                color_value = cfg.colorSelector.value
                if color_value in COLOR_DIR_MAPPING:
                    color_dir = COLOR_DIR_MAPPING[color_value]
                    window_color_dir = f"/usr/share/enigma2/Aglare-FHD-PLI/main/windowcolor/w_{color_dir}/"
                    window_dest_dir = "/usr/share/enigma2/Aglare-FHD-PLI/window/"

                    if exists(window_color_dir):
                        for filename in listdir(window_color_dir):
                            if filename.endswith(('.png', '.jpg')):
                                w_src_file = join(window_color_dir, filename)
                                w_dest_file = join(window_dest_dir, filename)
                                try:
                                    shutil.copy2(w_src_file, w_dest_file)
                                except Exception as e:
                                    print(f"Error copying {w_src_file} to {w_dest_file}: {e}")
                    else:
                        print(f"Source directory does not exist: {window_color_dir}")

                channellist_file = self.previewFiles + 'channellist-' + cfg.ChannSelector.value + '.xml'
                try:
                    with open(channellist_file, 'r') as f:
                        channellist_content = f.read()
                    channellist_content = self.modify_channel_colors(channellist_content)
                    skin_lines.extend(channellist_content.splitlines(True))
                except FileNotFoundError:
                    print("Channel selection file not found:", channellist_file)
            else:
                skin_lines.extend(load_xml_to_skin_lines(self.previewFiles + 'channellist-' + cfg.ChannSelector.value + '.xml'))

            # Load the remaining files
            for filename in xml_files[12:]:
                skin_lines.extend(load_xml_to_skin_lines(self.previewFiles + filename + '.xml'))

            base_file = 'base1.xml' if cfg.skinSelector.value == 'base1' else 'base.xml'
            skin_lines.extend(load_xml_to_skin_lines(self.previewFiles + base_file))

            print("Writing to file: {}".format(self.skinFile))
            with open(self.skinFile, 'w') as xFile:
                xFile.writelines(skin_lines)

            # Copy skin_sf.xml and skin_templates.xml
            dest_dir = "/usr/share/enigma2/" + cur_skin + "/"
            for extra_file in ['skin_sf.xml', 'skin_templates.xml']:
                src_path = join(self.previewFiles, extra_file)
                dst_path = join(dest_dir, extra_file)
                if fileExists(src_path):
                    try:
                        shutil.copy2(src_path, dst_path)
                        print("Copied {} to {}".format(src_path, dst_path))
                    except Exception as e:
                        print("Error copying {}: {}".format(extra_file, e))

        except Exception as e:
            self.session.open(MessageBox, _('Error processing skin file: {}').format(str(e)), MessageBox.TYPE_ERROR)

        # Ask to restart GUI
        restartbox = self.session.openWithCallback(
            self.restartGUI,
            MessageBox,
            _('GUI needs a restart to apply a new skin.\nDo you want to Restart the GUI now?'),
            MessageBox.TYPE_YESNO
        )
        restartbox.setTitle(_('Restart GUI now?'))

    def restartGUI(self, answer):
        if answer is True:
            self.session.open(TryQuitMainloop, 3)
        else:
            self.close()

    def checkforUpdate(self):
        """Fetch version file from GitHub and prompt the user if an update exists."""
        if not fullurl:
            self.session.open(
                MessageBox,
                _("Update URL not initialised – open the plugin once from the Plugins menu first."),
                MessageBox.TYPE_ERROR)
            return

        try:
            # write server‐side version file into /tmp
            tmp_file = f'/tmp/{destr}'
            req = Request(
                fullurl,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'})
            data = urlopen(req).read().decode('utf‑8')

            with open(tmp_file, 'w') as f:
                f.write(data)

            if not fileExists(tmp_file):
                raise IOError("Failed to write tmp version file")

            with open(tmp_file, 'r') as fh:
                line = fh.readline().strip()

            # expected format: "<version>#<ipk‑url>"
            try:
                version_server, self.updateurl = (
                    x.strip() for x in line.split('#', 1))
            except ValueError:
                raise ValueError(f"Malformed version string: {line}")

            if version_server == version:
                self.session.open(
                    MessageBox,
                    _("You already have the latest version ({}).").format(version),
                    MessageBox.TYPE_INFO)
            elif version_server > version:
                self.session.openWithCallback(
                    self.update,
                    MessageBox,
                    _(
                        "Server version: {}\nInstalled version: {}\n\n"
                        "A newer build is available – update now?"
                    ).format(version_server, version),
                    MessageBox.TYPE_YESNO
                )
            else:  # local build is somehow newer
                self.session.open(
                    MessageBox, _("Local build ({}) is newer than server build ({}).").format(
                        version, version_server), MessageBox.TYPE_INFO)

        except Exception as e:
            self.session.open(
                MessageBox, _("Update check failed: {}").format(
                    str(e)), MessageBox.TYPE_ERROR)

    def update(self, answer):
        if answer is True:
            self.session.open(AglareUpdater, self.updateurl)
        else:
            return

    def keyExit(self):
        self.close()


class AglareUpdater(Screen):

    def __init__(self, session, updateurl):
        self.session = session
        skin = '''
            <screen name="AglareUpdater" position="center,center" size="840,260" flags="wfBorder" backgroundColor="background">
                <widget name="status" position="20,10" size="800,70" transparent="1" font="Regular; 40" foregroundColor="foreground" backgroundColor="background" valign="center" halign="left" noWrap="1" />
                <widget source="progress" render="Progress" position="20,120" size="800,20" transparent="1" borderWidth="0" foregroundColor="white" backgroundColor="background" />
                <widget source="progresstext" render="Label" position="209,164" zPosition="2" font="Regular; 28" halign="center" transparent="1" size="400,70" foregroundColor="foreground" backgroundColor="background" />
            </screen>
            '''
        self.skin = skin
        Screen.__init__(self, session)
        self.updateurl = updateurl
        print('self.updateurl', self.updateurl)
        self['status'] = Label()
        self['progress'] = Progress()
        self['progresstext'] = StaticText()
        self.downloading = False
        self.last_recvbytes = 0
        self.error_message = None
        self.download = None
        self.aborted = False
        self.startUpdate()

    def startUpdate(self):
        self['status'].setText(_('Downloading Aglare...'))
        self.dlfile = '/tmp/aglare.ipk'
        print('self.dlfile', self.dlfile)
        self.download = downloadWithProgress(self.updateurl, self.dlfile)
        self.download.addProgress(self.downloadProgress)
        self.download.start().addCallback(
            self.downloadFinished).addErrback(
            self.downloadFailed)

    def downloadFinished(self, string=""):
        self["status"].setText(_("Installing updates..."))
        package_path = "/tmp/aglare.ipk"
        if fileExists(package_path):
            # Install the package
            os_system("opkg install {}".format(package_path))
            os_system("sync")

            # Remove the package
            remove(package_path)
            os_system("sync")

            # Ask user for GUI restart
            restartbox = self.session.openWithCallback(
                self.restartGUI,
                MessageBox,
                _("Aglare update was done!\nDo you want to restart the GUI now?"),
                MessageBox.TYPE_YESNO)
            restartbox.setTitle(_("Restart GUI now?"))
        else:
            self["status"].setText(_("Update package not found!"))
            self.session.open(
                MessageBox,
                _("The update file was not found in /tmp.\nUpdate aborted."),
                MessageBox.TYPE_ERROR
            )

    def downloadFailed(self, failure_instance=None, error_message=''):
        text = _('Error downloading files!')
        if error_message == '' and failure_instance is not None:
            error_message = failure_instance.getErrorMessage()
            text += ': ' + error_message
        self['status'].setText(text)
        return

    def downloadProgress(self, recvbytes, totalbytes):
        """Update the on‑screen progress bar and text."""
        if totalbytes == 0:
            pct = 0
        else:
            pct = int(100 * recvbytes / float(totalbytes))

        self['status'].setText(_('Download in progress…'))
        self['progress'].value = pct
        self['progresstext'].text = '{} of {} kB ({:.2f}  %)'.format(
            recvbytes // 1024,
            totalbytes // 1024 if totalbytes else 0,
            pct
        )
        self.last_recvbytes = recvbytes

    def restartGUI(self, answer=False):
        if answer is True:
            self.session.open(TryQuitMainloop, 3)
        else:
            self.close()


def removePng():
    # Print message indicating the start of PNG and JPG file removal
    print('Removing PNG and JPG files...')
    if exists(path_poster):
        png_files = glob_glob(join(path_poster, "*.png"))
        jpg_files = glob_glob(join(path_poster, "*.jpg"))
        json_file = glob_glob(join(path_poster, "*.json"))
        files_to_remove = png_files + jpg_files + json_file

        if not files_to_remove:
            print("No PNG or JPG files found in the folder " + path_poster)

        for file in files_to_remove:
            try:
                remove(file)
                print("Removed: " + file)
            except Exception as e:
                print("Error removing " + file + ": " + str(e))
    else:
        print("The folder " + path_poster + " does not exist.")

    if exists(patch_backdrop):
        png_files_backdrop = glob_glob(join(patch_backdrop, "*.png"))
        jpg_files_backdrop = glob_glob(join(patch_backdrop, "*.jpg"))
        json_file_backdrop = glob_glob(join(path_poster, "*.json"))
        files_to_remove_backdrop = png_files_backdrop + \
            jpg_files_backdrop + json_file_backdrop

        if not files_to_remove_backdrop:
            print("No PNG or JPG files found in the folder " + patch_backdrop)
        else:
            for file in files_to_remove_backdrop:
                try:
                    remove(file)
                    print("Removed: " + file)
                except Exception as e:
                    print("Error removing " + file + ": " + str(e))
    else:
        print("The folder " + patch_backdrop + " does not exist.")


def main(session, **kwargs):
    global skinversion, destr, fullurl
    cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "")

    if cur_skin == "Aglare-FHD-PLI":
        skinversion = join("/usr/share/enigma2", cur_skin, ".Aglare-FHD-PLI")
        destr = "aglarepliversion.txt"
        myurl = "https://raw.githubusercontent.com/popking159/skins/main/aglarepli/"
        fullurl = join(myurl, destr)
    elif cur_skin == "Aglare-FHD":
        skinversion = join("/usr/share/enigma2", cur_skin, ".Aglare-FHD")
        destr = "aglareatvversion.txt"
        myurl = "https://raw.githubusercontent.com/popking159/skins/main/aglareatv/"
        fullurl = join(myurl, destr)
    else:
        # Just show the message and exit - no callback needed
        session.open(
            MessageBox,
            "Skin not supported.\nPlugin closed.",
            MessageBox.TYPE_ERROR,
            timeout=5)
        return
    session.open(AglareSetup)


def Plugins(**kwargs):
    # Only use cur_skin in the description if it's actually an Aglare skin.
    # Otherwise, default to "Aglare" so it doesn't show unsupported skin names.
    display_skin = cur_skin if cur_skin in (
        "Aglare-FHD", "Aglare-FHD-PLI") else "Aglare"

    return PluginDescriptor(
        name='Setup Aglare',
        description=_('Customization tool for %s Skin') % display_skin,
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon='plugin.png',
        fnc=main
    )


def remove_exif(image_path):
    with Image.open(image_path) as img:
        img.save(image_path, "PNG")


def convert_image(image):
    path = image
    img = Image.open(path)
    img.save(path, "PNG")
    return image
