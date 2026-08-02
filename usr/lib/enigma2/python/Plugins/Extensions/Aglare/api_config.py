#!/usr/bin/python
# -*- coding: utf-8 -*-
# skin name = Aglare-PLI-FHD ##
from __future__ import absolute_import, print_function
# Enigma2 Components
from Components.config import (
    config,
    ConfigOnOff,
    ConfigYesNo,
    ConfigText,
    ConfigClock,
    NoSave,
    ConfigSelection,
    ConfigSubsection,
    configfile
)
from time import localtime, mktime

# Enigma2 Tools
from Tools.Directories import fileExists

# Plugin-local imports
from . import _


def detect_image_group():
    # Default to openpli group as requested
    group = 'openpli'
    try:
        if fileExists('/etc/issue'):
            with open('/etc/issue', 'r') as f:
                issue = f.read().lower()
                # Add keywords for the "new images group"
                if any(
                    img in issue for img in [
                        'openbh',
                        'openvix',
                        'teamblue',
                        'openatv',
                        'egami',
                        'pure2']):
                    group = 'new_images'
    except Exception:
        pass
    return group


# constants
my_cur_skin = False
mvi = '/usr/share/'
cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "").strip()


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


class ApiKeyManager:
    """Loads API keys from skin files or falls back to defaults.
    Args:
        API_CONFIG (dict): Configuration mapping for each API.
    """

    def __init__(self):
        self.API_CONFIG = {
            "tmdb": {
                "skin_file": "tmdb_api",
                "default_key": "3c3efcf47c3577558812bb9d64019d65",
                "config_entry": config.plugins.Aglare.tmdb_api,
                "load_action": config.plugins.Aglare.load_tmdb_api
            },
            "fanart": {
                "skin_file": "fanart_api",
                "default_key": "6d231536dea4318a88cb2520ce89473b",
                "config_entry": config.plugins.Aglare.fanart_api,
                "load_action": config.plugins.Aglare.load_fanart_api
            },
            "thetvdb": {
                "skin_file": "thetvdb_api",
                "default_key": "a99d487bb3426e5f3a60dea6d3d3c7ef",
                "config_entry": config.plugins.Aglare.thetvdb_api,
                "load_action": config.plugins.Aglare.load_thetvdb_api
            },
            "omdb": {
                "skin_file": "omdb_api",
                "default_key": "cb1d9f55",
                "config_entry": config.plugins.Aglare.omdb_api,
                "load_action": config.plugins.Aglare.load_omdb_api
            }
        }

        self.init_paths()
        self.load_all_keys()

    def init_paths(self):
        """Initialize skin file paths"""
        for api, cfg in self.API_CONFIG.items():
            setattr(self, f"{api}_skin",
                    f"{mvi}enigma2/{cur_skin}/{cfg['skin_file']}")

    def _coerce_enabled(self, entry):
        """Return a safe bool from ConfigElement-like entries or raw booleans.

        Some skins/config loaders may assign `config.plugins.Aglare.<provider> = True`
        instead of `config.plugins.Aglare.<provider>.value = True`. This helper accepts
        both ConfigOnOff objects and plain booleans so provider activation remains robust.
        """
        try:
            return bool(entry.value)
        except Exception:
            return bool(entry)

    def get_active_providers(self):
        active = {}

        # Providers that require API keys
        for api, cfg in self.API_CONFIG.items():
            enabled = self._coerce_enabled(
                getattr(config.plugins.Aglare, api, False))
            api_value = cfg['config_entry'].value
            key_valid = bool(api_value)

            if enabled and key_valid:
                active[api] = True

        # Providers that do not require API keys
        for provider in (
            "elcinema",
            "google",
            "imdb",
            "programmetv",
                "molotov"):
            if self._coerce_enabled(
                getattr(
                    config.plugins.Aglare,
                    provider,
                    False)):
                active[provider] = True
        return active

    def get_api_key(self, provider):
        """Retrieve API key for the specified provider."""
        if provider in self.API_CONFIG:
            return self.API_CONFIG[provider]['config_entry'].value
        return None

    def load_all_keys(self):
        """Upload all API keys from different sources"""
        global my_cur_skin
        if my_cur_skin:
            return

        try:
            # Loading from skin file
            for api, cfg in self.API_CONFIG.items():
                skin_path = f"/usr/share/enigma2/{cur_skin}/{cfg['skin_file']}"
                if fileExists(skin_path):
                    with open(skin_path, "r") as f:
                        key_value = f.read().strip()
                    if key_value:
                        cfg['config_entry'].value = key_value

            # Overwriting from default values
            for api, cfg in self.API_CONFIG.items():
                if not cfg['config_entry'].value:
                    cfg['config_entry'].value = cfg['default_key']

            my_cur_skin = True

        except Exception as e:
            print(f"Error loading API keys: {str(e)}")
            my_cur_skin = False

    def handle_load_key(self, api):
        """Handles loading keys from /tmp"""
        tmp_file = f"/tmp/{api}key.txt"
        cfg = self.API_CONFIG.get(api)

        try:
            if fileExists(tmp_file):
                with open(tmp_file, "r") as f:
                    key_value = f.read().strip()

                if key_value:
                    cfg['config_entry'].value = key_value
                    cfg['config_entry'].save()
                    return True, _("Key {} successfully loaded!").format(
                        api.upper())
            return False, _("File {} not found or empty").format(tmp_file)

        except Exception as e:
            return False, _("Error loading: {}").format(str(e))


""" Config and setting maintenance """
config.plugins.Aglare = ConfigSubsection()

# config.plugins.Aglare.InfobarSoftCSA = ConfigYesNo(default=False)

config.plugins.Aglare.xpath = ConfigSelection(
    default="/media/hdd",
    choices=[
        ("/media/hdd", "HDD (/media/hdd)"),
        ("/media/usb", "USB (/media/usb)"),
        ("/media/mmc", "MMC (/media/mmc)"),
        ("/media/net", "NAS (/media/net)"),
        ("/media/autofs", "NAS (/media/autofs)"),
    ]
)

config.plugins.Aglare.download_now_poster = NoSave(ConfigYesNo(default=False))
config.plugins.Aglare.download_now_backdrop = NoSave(
    ConfigYesNo(default=False))

config.plugins.Aglare.actapi = ConfigOnOff(default=True)
config.plugins.Aglare.tmdb = ConfigOnOff(default=True)
config.plugins.Aglare.load_tmdb_api = ConfigYesNo(default=False)
config.plugins.Aglare.tmdb_api = ConfigText(
    default="3c3efcf47c3577558812bb9d64019d65",
    visible_width=50,
    fixed_size=False)

config.plugins.Aglare.fanart = ConfigOnOff(default=False)
config.plugins.Aglare.load_fanart_api = ConfigYesNo(default=False)
config.plugins.Aglare.fanart_api = ConfigText(
    default="6d231536dea4318a88cb2520ce89473b",
    visible_width=50,
    fixed_size=False)

config.plugins.Aglare.thetvdb = ConfigOnOff(default=False)
config.plugins.Aglare.load_thetvdb_api = ConfigYesNo(default=False)
config.plugins.Aglare.thetvdb_api = ConfigText(
    default="a99d487bb3426e5f3a60dea6d3d3c7ef",
    visible_width=50,
    fixed_size=False)

config.plugins.Aglare.omdb = ConfigOnOff(default=False)
config.plugins.Aglare.load_omdb_api = ConfigYesNo(default=False)
config.plugins.Aglare.omdb_api = ConfigText(
    default="4ca6ea60", visible_width=50, fixed_size=False)

config.plugins.Aglare.elcinema = ConfigOnOff(default=True)
config.plugins.Aglare.google = ConfigOnOff(default=True)
config.plugins.Aglare.imdb = ConfigOnOff(default=False)
config.plugins.Aglare.programmetv = ConfigOnOff(default=False)
config.plugins.Aglare.molotov = ConfigOnOff(default=False)

config.plugins.Aglare.cache = ConfigOnOff(default=False)
agp_use_cache = config.plugins.Aglare.cache

config.plugins.Aglare.pstdown = ConfigOnOff(default=False)
config.plugins.Aglare.bkddown = ConfigOnOff(default=False)
config.plugins.Aglare.pscan_time = ConfigClock(calcTime(0, 0))  # 00:00
config.plugins.Aglare.bscan_time = ConfigClock(calcTime(2, 0))  # 02:00

# stars
config.plugins.Aglare.rating_source = ConfigOnOff(default=False)

# infoevents
config.plugins.Aglare.info_display_mode = ConfigSelection(default="off", choices=[
    ("auto", _("Automatic")),
    ("tmdb", _("TMDB Only")),
    ("omdb", _("OMDB Only")),
    ("off", _("Off"))
])

# parental
config.plugins.Aglare.info_parental_mode = ConfigSelection(default="off", choices=[
    ("auto", _("Automatic")),
    ("tmdb", _("TMDB Only")),
    ("omdb", _("OMDB Only")),
    ("off", _("Off"))
])

# genre
config.plugins.Aglare.genre_source = ConfigOnOff(default=False)

# Enhanced Movie Center
config.plugins.Aglare.xemc_poster = ConfigOnOff(default=False)

# remove png
config.plugins.Aglare.png = NoSave(ConfigYesNo(default=False))

# SKIN STYLE MANAGEMENT ==================================================
config.plugins.Aglare.ImageGroup = ConfigSelection(
    default=detect_image_group(),
    choices=[
        ('openpli',
         _('OpenPLi / Satlodge (OpenPLi Group)')),
        ('new_images',
         _('OpenBH / OpenViX / TeamBlue (New Images Group)'))])
config.plugins.Aglare.colorSelector = ConfigSelection(default='color0', choices=[
    ('color0', _('Default')),
    ('color1', _('Black')),
    ('color2', _('Brown')),
    ('color3', _('Green')),
    ('color4', _('Magenta')),
    ('color5', _('Blue')),
    ('color6', _('Red')),
    ('color7', _('Purple')),
    ('color8', _('Green2')),
    ('color9', _('Mix1'))
])
config.plugins.Aglare.FontStyle = ConfigSelection(default='basic', choices=[
    ('basic', _('Default')),
    ('font1', _('HandelGotD')),
    ('font2', _('KhalidArtboldRegular')),
    ('font3', _('BebasNeue')),
    ('font4', _('Greta')),
    ('font5', _('Segoe UI light')),
    ('font6', _('MV Boli')),
    ('font7', _('Lucida'))
])
config.plugins.Aglare.skinSelector = ConfigSelection(default='base', choices=[
    ('base', _('Default'))
])
config.plugins.Aglare.InfobarStyle = ConfigSelection(default='infobar_base1', choices=[
    ('infobar_base1', _('Default')),
    ('infobar_base2', _('Style2')),
    ('infobar_base3', _('Style3')),
    ('infobar_base4', _('Style4')),
    ('infobar_base5', _('Style5 CD')),
    ('infobar_base6', _('Style6'))
])
config.plugins.Aglare.InfobarECM = ConfigSelection(
    default='infobar_ecm_off', choices=[
        ('infobar_ecm_off', _('OFF')), ('infobar_ecm_on', _('ON'))])
config.plugins.Aglare.InfobarPosterx = ConfigSelection(
    default='infobar_posters_posterx_off',
    choices=[
        ('infobar_posters_posterx_off',
         _('OFF')),
        ('infobar_posters_posterx_on',
         _('ON')),
        ('infobar_posters_posterx_on_all',
         _('TEST')),
        ('infobar_posters_posterx_cd',
         _('CD')),
        ('infobar_posters_posterx_ecm',
         _('1 poster'))])
config.plugins.Aglare.InfobarXtraevent = ConfigSelection(
    default='infobar_posters_xtraevent_off',
    choices=[
        ('infobar_posters_xtraevent_off',
         _('OFF')),
        ('infobar_posters_xtraevent_on',
         _('ON')),
        ('infobar_posters_xtraevent_cd',
         _('CD')),
        ('infobar_posters_xtraevent_info',
         _('Backdrop')),
        ('infobar_posters_xtraevent_ecm',
         _('1 poster'))])
config.plugins.Aglare.InfobarDate = ConfigSelection(default='infobar_no_date', choices=[
    ('infobar_no_date', _('Infobar_NO_Date')),
    ('infobar_date', _('Infobar_Date'))
])

config.plugins.Aglare.InfobarWeather = ConfigSelection(
    default='infobar_no_weather',
    choices=[
        ('infobar_no_weather',
         _('Infobar_NO_Weather')),
        ('infobar_MSNweather',
         _('Infobar_MSNWeather')),
        ('infobar_OAweather',
         _('Infobar_OAWeather'))])
config.plugins.Aglare.SecondInfobarStyle = ConfigSelection(
    default='secondinfobar_base1',
    choices=[
        ('secondinfobar_base1',
         _('Default')),
        ('secondinfobar_base2',
         _('Style2')),
        ('secondinfobar_base3',
         _('Style3')),
        ('secondinfobar_base4',
         _('Style4'))])
config.plugins.Aglare.SecondInfobarWeather = ConfigSelection(
    default='secondinfobar_no_weather',
    choices=[
        ('secondinfobar_no_weather',
         _('Second Infobar_NO_Weather')),
        ('secondinfobar_MSNweather',
         _('Second Infobar_MSNWeather')),
        ('secondinfobar_OAweather',
         _('Second Infobar_OAWeather'))])
config.plugins.Aglare.SecondInfobarPosterx = ConfigSelection(
    default='secondinfobar_posters_posterx_off',
    choices=[
        ('secondinfobar_posters_posterx_off',
         _('OFF')),
        ('secondinfobar_posters_posterx_on',
         _('ON'))])
config.plugins.Aglare.SecondInfobarXtraevent = ConfigSelection(
    default='secondinfobar_posters_xtraevent_off',
    choices=[
        ('secondinfobar_posters_xtraevent_off',
         _('OFF')),
        ('secondinfobar_posters_xtraevent_on',
         _('ON'))])
config.plugins.Aglare.ChannSelector = ConfigSelection(default='channellist_no_posters', choices=[
    ('channellist_no_posters', _('ChannelSelection_NO_Posters')),
    ('channellist_no_posters_no_picon', _('ChannelSelection_NO_Posters_NO_Picon')),
    ('channellist_backdrop_v', _('ChannelSelection_BackDrop_V_EX')),
    ('channellist_backdrop_v_posterx', _('ChannelSelection_BackDrop_V_PX')),
    ('channellist_backdrop_h', _('ChannelSelection_BackDrop_H_EX')),
    ('channellist_backdrop_h_posterx', _('ChannelSelection_BackDrop_H_PX')),
    ('channellist_1_poster_PX', _('ChannelSelection_1_Poster_PX')),
    ('channellist_1_poster_EX', _('ChannelSelection_1_Poster_EX')),
    ('channellist_4_posters_PX', _('ChannelSelection_4_Posters_PX')),
    ('channellist_4_posters_EX', _('ChannelSelection_4_Posters_EX')),
    ('channellist_6_posters_PX', _('ChannelSelection_6_Posters_PX')),
    ('channellist_6_posters_PX_all', _('ChannelSelection_6_Posters_PX_test')),
    ('channellist_6_posters_EX', _('ChannelSelection_6_Posters_EX')),
    ('channellist_big_mini_tv', _('ChannelSelection_big_mini_tv'))
])
config.plugins.Aglare.EventView = ConfigSelection(
    default='eventview_no_posters',
    choices=[
        ('eventview_no_posters',
         _('EventView_NO_Posters')),
        ('eventview_7_posters',
         _('EventView_7_Posters'))])
config.plugins.Aglare.VolumeBar = ConfigSelection(default='volume1', choices=[
    ('volume1', _('Default')),
    ('volume2', _('volume2'))
])
config.plugins.Aglare.Emc = ConfigSelection(default='emcscreen_default', choices=[
    ('emcscreen_default', _('Default')),
    ('emcscreen_posterx', _('EMC PX'))
])
config.plugins.Aglare.bitrate_unit = ConfigSelection(default='kb', choices=[
    ('kb', _('Kilobit/s (Kb/s)')),
    ('mb', _('Megabit/s (Mb/s)'))
])
config.plugins.Aglare.Subssupportproskins = ConfigSelection(
    default='subssupportpro_skin_off', choices=[
        ('subssupportpro_skin_off', _('OFF')), ('subssupportpro_skin_on', _('ON'))])
config.plugins.Aglare.E2iplayerskins = ConfigSelection(
    default='e2iplayer_skin_off', choices=[
        ('e2iplayer_skin_off', _('OFF')), ('e2iplayer_skin_on', _('ON'))])
config.plugins.Aglare.ChannForegroundColor = ConfigSelection(default='white', choices=[
    ('white', _('White')),
    ('#77ca5b', _('Mint')),
    ('#FFFAFA', _('SnowWhite')),
    ('#008080', _('Teal')),
    ('#FF0000', _('Red')),
    ('#DC143C', _('Crimson')),
    ('#FF6347', _('Tomato')),
    ('#4682B4', _('SteelBlue')),
    ('#32CD32', _('LimeGreen')),
    ('#9ACD32', _('YellowGreen')),
    ('#D3D3D3', _('LightGray')),
    ('#A0522D', _('Sienna')),
    ('#FF4500', _('Orange')),
    ('#663399', _('Purple')),
    ('#FF69B4', _('Pink'))
])

config.plugins.Aglare.ChannForegroundColorSelected = ConfigSelection(default='white', choices=[
    ('white', _('White')),
    ('#77ca5b', _('Mint')),
    ('#FFFAFA', _('SnowWhite')),
    ('#008080', _('Teal')),
    ('#FF0000', _('Red')),
    ('#DC143C', _('Crimson')),
    ('#FF6347', _('Tomato')),
    ('#4682B4', _('SteelBlue')),
    ('#32CD32', _('LimeGreen')),
    ('#9ACD32', _('YellowGreen')),
    ('#D3D3D3', _('LightGray')),
    ('#A0522D', _('Sienna')),
    ('#FF4500', _('Orange')),
    ('#663399', _('Purple')),
    ('#FF69B4', _('Pink'))
])

config.plugins.Aglare.ChannServiceDescriptionColor = ConfigSelection(default='white', choices=[
    ('white', _('White')),
    ('#77ca5b', _('Mint')),
    ('#FFFAFA', _('SnowWhite')),
    ('#008080', _('Teal')),
    ('#FF0000', _('Red')),
    ('#DC143C', _('Crimson')),
    ('#FF6347', _('Tomato')),
    ('#4682B4', _('SteelBlue')),
    ('#32CD32', _('LimeGreen')),
    ('#9ACD32', _('YellowGreen')),
    ('#D3D3D3', _('LightGray')),
    ('#A0522D', _('Sienna')),
    ('#FF4500', _('Orange')),
    ('#663399', _('Purple')),
    ('#FF69B4', _('Pink'))
])

config.plugins.Aglare.ChannServiceDescriptionColorSelected = ConfigSelection(default='white', choices=[
    ('white', _('White')),
    ('#77ca5b', _('Mint')),
    ('#FFFAFA', _('SnowWhite')),
    ('#008080', _('Teal')),
    ('#FF0000', _('Red')),
    ('#DC143C', _('Crimson')),
    ('#FF6347', _('Tomato')),
    ('#4682B4', _('SteelBlue')),
    ('#32CD32', _('LimeGreen')),
    ('#9ACD32', _('YellowGreen')),
    ('#D3D3D3', _('LightGray')),
    ('#A0522D', _('Sienna')),
    ('#FF4500', _('Orange')),
    ('#663399', _('Purple')),
    ('#FF69B4', _('Pink'))
])
cfg = config.plugins.Aglare
configfile.load()  # pull the values that were written to /etc/enigma2/settings
api_key_manager = ApiKeyManager()
