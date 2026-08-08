#!/usr/bin/python
# -*- coding: utf-8 -*-
# # skin name = Aglare-PLI-FHD
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
                if any(img in issue for img in ['openbh', 'openvix', 'teamblue', 'openatv', 'egami', 'pure2']):
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
    ret_time = mktime((now_time.tm_year, now_time.tm_mon, now_time.tm_mday,
                      hours, minutes, 0, now_time.tm_wday, now_time.tm_yday, now_time.tm_isdst))
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
        for provider in ("elcinema", "google", "imdb", "programmetv", "molotov"):
            if self._coerce_enabled(getattr(config.plugins.Aglare, provider, False)):
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
                    return True, _("Key {} successfully loaded!").format(api.upper())
            return False, _("File {} not found or empty").format(tmp_file)

        except Exception as e:
            return False, _("Error loading: {}").format(str(e))


""" Config and setting maintenance """
config.plugins.Aglare = ConfigSubsection()

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
    default="3c3efcf47c3577558812bb9d64019d65", visible_width=50, fixed_size=False)

config.plugins.Aglare.fanart = ConfigOnOff(default=False)
config.plugins.Aglare.load_fanart_api = ConfigYesNo(default=False)
config.plugins.Aglare.fanart_api = ConfigText(
    default="6d231536dea4318a88cb2520ce89473b", visible_width=50, fixed_size=False)

config.plugins.Aglare.thetvdb = ConfigOnOff(default=False)
config.plugins.Aglare.load_thetvdb_api = ConfigYesNo(default=False)
config.plugins.Aglare.thetvdb_api = ConfigText(
    default="a99d487bb3426e5f3a60dea6d3d3c7ef", visible_width=50, fixed_size=False)

config.plugins.Aglare.omdb = ConfigOnOff(default=False)
config.plugins.Aglare.load_omdb_api = ConfigYesNo(default=False)
config.plugins.Aglare.omdb_api = ConfigText(
    default="4ca6ea60", visible_width=50, fixed_size=False)

config.plugins.Aglare.elcinema = ConfigOnOff(default=False)
config.plugins.Aglare.google = ConfigOnOff(default=False)
config.plugins.Aglare.imdb = ConfigOnOff(default=False)
config.plugins.Aglare.programmetv = ConfigOnOff(default=False)
config.plugins.Aglare.molotov = ConfigOnOff(default=False)

config.plugins.Aglare.cache = ConfigOnOff(default=False)
agp_use_cache = config.plugins.Aglare.cache

config.plugins.Aglare.pstdown = ConfigOnOff(default=False)
config.plugins.Aglare.bkddown = ConfigOnOff(default=False)
config.plugins.Aglare.pscan_time = ConfigClock(calcTime(0, 0))  # 00:00
config.plugins.Aglare.bscan_time = ConfigClock(calcTime(2, 0))  # 02:00


# Live Events
config.plugins.Aglare.rating_source = ConfigOnOff(default=True)
config.plugins.Aglare.show_poster = ConfigOnOff(default=True)
config.plugins.Aglare.show_backdrop = ConfigOnOff(default=True)
config.plugins.Aglare.show_logo = ConfigOnOff(default=True)
config.plugins.Aglare.genre_source = ConfigOnOff(default=True)
config.plugins.Aglare.info_display_mode = ConfigSelection(default="tmdb", choices=[
    ("auto", _("Automatic")),
    ("tmdb", _("TMDB Only")),
    ("omdb", _("OMDB Only")),
    ("off", _("Off"))
])


config.plugins.Aglare.info_parental_mode = ConfigSelection(default="tmdb", choices=[
    ("auto", _("Automatic")),
    ("tmdb", _("TMDB Only")),
    ("omdb", _("OMDB Only")),
    ("off", _("Off"))
])


# Enhanced Movie Center
config.plugins.Aglare.xemc_poster = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_poster = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_backdrop = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_logo = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_info = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_star = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_cast = ConfigOnOff(default=True)
config.plugins.Aglare.xemc_parental = ConfigOnOff(default=True)

# remove png
config.plugins.Aglare.png = NoSave(ConfigYesNo(default=False))

# SKIN STYLE MANAGEMENT =========================================================
config.plugins.Aglare.ImageGroup = ConfigSelection(default=detect_image_group(), choices=[
    ('openpli', _('OpenPLi / Satlodge (OpenPLi Group)')),
    ('new_images', _('OpenBH / OpenViX / TeamBlue (New Images Group)'))
])
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
    ('color9', _('Mix1')),
    ('colorcustom', _('Custom')),
    ('colorcustom2', _('Custom2'))
])

BG_COLOR_CHOICES = [
    ('3e4b53', _('Aero Slate')),
    ('101820', _('Anthracite Blue')),
    ('434c5e', _('Arctic Blue Gray')),
    ('6a7782', _('Ash Fog')),
    ('535b66', _('Asphalt Blue')),
    ('000000', _('Black')),
    ('333c4d', _('Blue Ash')),
    ('263238', _('Blue Charcoal')),
    ('64727c', _('Blue Fog')),
    ('495464', _('Blue Granite')),
    ('1e2a33', _('Blue Gray')),
    ('374151', _('Blue Gray 700')),
    ('707d8a', _('Blue Haze')),
    ('58626f', _('Blue Mist')),
    ('2f3744', _('Blue Smoke')),
    ('633034', _('Brick Red')),
    ('2e2413', _('Bronze Night')),
    ('1f1812', _('Brown Night')),
    ('2a1416', _('Burgundy Night')),
    ('343a40', _('Carbon Gray')),
    ('171a1c', _('Charcoal')),
    ('413021', _('Chestnut')),
    ('6c757d', _('Classic Gray')),
    ('57606f', _('Cloud Blue')),
    ('364152', _('Cloud Navy')),
    ('46515d', _('Clouded Steel')),
    ('20242b', _('Coal')),
    ('6a4e36', _('Cocoa')),
    ('5c432e', _('Coffee Brown')),
    ('697681', _('Cold Fog')),
    ('5c6670', _('Cold Mist')),
    ('3a4452', _('Cold Steel')),
    ('221c10', _('Dark Amber')),
    ('54606c', _('Dark Frost')),
    ('303640', _('Dark Silver Blue')),
    ('1d283c', _('Dark Steel Blue')),
    ('29313a', _('Dark Teal Gray')),
    ('2a1f16', _('Dark Walnut')),
    ('222e47', _('Deep Indigo')),
    ('3a2c16', _('Deep Ochre')),
    ('356b46', _('Deep Olive Green')),
    ('2d2040', _('Deep Purple')),
    ('18202a', _('Deep Slate')),
    ('421e22', _('Deep Wine')),
    ('66737d', _('Dim Mist')),
    ('444c56', _('Dim Navy')),
    ('47515d', _('Dusk Gray')),
    ('4f5b66', _('Dust Blue')),
    ('9f7d39', _('Dust Gold')),
    ('73828f', _('Dust Haze')),
    ('513970', _('Dust Purple')),
    ('28343b', _('Dust Slate')),
    ('854548', _('Dusty Red')),
    ('35404a', _('Dusty Teal')),
    ('35271b', _('Espresso Brown')),
    ('234531', _('Evergreen')),
    ('4c566a', _('Fjord Gray')),
    ('71808c', _('Fog Blue')),
    ('14301f', _('Forest Night')),
    ('778693', _('Gentle Haze')),
    ('5b646e', _('Granite Blue')),
    ('1c1f24', _('Graphite')),
    ('2a2f3a', _('Graphite Blue')),
    ('24303b', _('Gunmetal')),
    ('58431f', _('Honey Bronze')),
    ('241a33', _('Indigo Plum')),
    ('1a2336', _('Midnight Navy')),
    ('3d4554', _('Ink Steel')),
    ('383d45', _('Iron Blue')),
    ('616e77', _('Iron Mist')),
    ('4a8d5b', _('Jade Smoke')),
    ('7d5da6', _('Lavender Smoke')),
    ('505a64', _('Lead Blue')),
    ('3f7c50', _('Leaf Green')),
    ('51606b', _('Marine Gray')),
    ('5a5a5a', _('Medium Gray')),
    ('0c101b', _('Midnight Ink')),
    ('6d7a84', _('Mild Steel')),
    ('6f7c88', _('Mist Blue')),
    ('1b3a2b', _('Moss Green')),
    ('886548', _('Muted Brown')),
    ('52272b', _('Muted Crimson')),
    ('4d5e7c', _('Muted Denim')),
    ('5aa06a', _('Muted Emerald')),
    ('687580', _('Muted Fog')),
    ('47361a', _('Muted Gold')),
    ('39424e', _('Muted Graphite')),
    ('2d5a3d', _('Muted Green')),
    ('758491', _('Muted Haze')),
    ('4a5568', _('Muted Indigo Gray')),
    ('23314c', _('Muted Navy')),
    ('6e5094', _('Muted Purple')),
    ('7983a3', _('Muted Purple Gray')),
    ('965154', _('Muted Rose')),
    ('8d6d31', _('Muted Saffron')),
    ('56606a', _('Muted Slate')),
    ('5e6770', _('Muted Storm')),
    ('38284f', _('Muted Violet')),
    ('212d40', _('Navy Slate')),
    ('080b11', _('Near Black Blue')),
    ('525252', _('Neutral Gray')),
    ('121826', _('Night Navy')),
    ('3b4252', _('Nord Blue Gray')),
    ('2e3440', _('Nord Gray')),
    ('151b25', _('Obsidian Blue')),
    ('5f6b76', _('Ocean Mist')),
    ('2d3d5b', _('Ocean Steel')),
    ('7b5e2a', _('Old Gold')),
    ('35181c', _('Oxblood')),
    ('6e7b86', _('Pale Slate')),
    ('283752', _('Petrol Blue')),
    ('102018', _('Pine Night')),
    ('44305f', _('Plum Smoke')),
    ('201112', _('Red Night')),
    ('743a3e', _('Rosewood')),
    ('55616d', _('Sea Ash')),
    ('1f2d3a', _('Sea Slate')),
    ('27313f', _('Shadow Blue')),
    ('7a858e', _('Silver Haze')),
    ('626f79', _('Silver Slate')),
    ('40454f', _('Slate Carbon')),
    ('48515b', _('Slate Dust')),
    ('67747e', _('Slate Fog')),
    ('72808e', _('Slate Haze')),
    ('606c76', _('Slate Mist')),
    ('31363f', _('Slate Night')),
    ('3c4454', _('Slate Ocean')),
    ('63707a', _('Smoke Slate')),
    ('2b3440', _('Smoky Blue')),
    ('424b54', _('Smoky Steel')),
    ('141a1f', _('Soft Black')),
    ('987252', _('Soft Brown')),
    ('6bb37a', _('Soft Green')),
    ('768592', _('Soft Haze')),
    ('5f4482', _('Soft Indigo')),
    ('8d6bb8', _('Soft Lavender')),
    ('b18d42', _('Soft Mustard')),
    ('a75d60', _('Soft Red')),
    ('65727d', _('Soft Steel')),
    ('ededed', _('Soft White')),
    ('414c57', _('Steel Fog')),
    ('25313d', _('Steel Gray')),
    ('5d6b75', _('Steel Mist')),
    ('4b5563', _('Stone Blue')),
    ('32363c', _('Stone Gray')),
    ('1b1f2a', _('Storm Blue')),
    ('45505b', _('Storm Fog')),
    ('2c3340', _('Storm Gray')),
    ('748390', _('Storm Haze')),
    ('59636f', _('Storm Mist')),
    ('6b7280', _('Tailwind Gray')),
    ('4e5a65', _('Teal Smoke')),
    ('202738', _('Twilight Blue')),
    ('1b1426', _('Violet Night')),
    ('79593f', _('Walnut')),
    ('695024', _('Warm Brass')),
    ('4e3927', _('Warm Brown')),
    ('ffffff', _('White')),
]

TRANSPARENCY_CHOICES = [
    ('00', _('OFF')),
    ('1A', _('10%')),
    ('33', _('20%')),
    ('4D', _('30%')),
    ('66', _('40%')),
    ('80', _('50%')),
    ('99', _('60%')),
    ('B3', _('70%')),
    ('CC', _('80%')),
    ('E6', _('90%'))
]

config.plugins.Aglare.odem1 = ConfigText(default="#00080b11", visible_width=12, fixed_size=False)   # wpuc
config.plugins.Aglare.odem2 = ConfigText(default="#002d3d5b", visible_width=12, fixed_size=False)   # wpmc
config.plugins.Aglare.odem3 = ConfigText(default="#00222e47", visible_width=12, fixed_size=False)   # wplc
config.plugins.Aglare.odem4 = ConfigText(default="#001a2336", visible_width=12, fixed_size=False)   # buttonsc
config.plugins.Aglare.odem5 = ConfigText(default="#00171a1c", visible_width=12, fixed_size=False)   # mcolor2
config.plugins.Aglare.odem6 = ConfigText(default="#0028343b", visible_width=12, fixed_size=False)   # mcolor3
config.plugins.Aglare.odem7 = ConfigText(default="#003e4b53", visible_width=12, fixed_size=False)   # mcolor4
config.plugins.Aglare.odem8 = ConfigText(default="#00283752", visible_width=12, fixed_size=False)   # mcolor5
config.plugins.Aglare.odem9 = ConfigText(default="#004d5e7c", visible_width=12, fixed_size=False)   # mcolor6
config.plugins.Aglare.odem10 = ConfigText(default="#001d283c", visible_width=12, fixed_size=False)   # igsd
config.plugins.Aglare.odem11 = ConfigText(default="#441d283c", visible_width=12, fixed_size=False)  # igsdt
config.plugins.Aglare.odem12 = ConfigText(default="#10171a1c", visible_width=12, fixed_size=False)   # mcolor7
config.plugins.Aglare.odem13 = ConfigText(default="#005a5a5a", visible_width=12, fixed_size=False)  # progbg
config.plugins.Aglare.odem14 = ConfigText(default="#0023314c", visible_width=12, fixed_size=False)  # sidec1
config.plugins.Aglare.odem15 = ConfigText(default="#000c101b", visible_width=12, fixed_size=False)  # sidec2
config.plugins.Aglare.odem16 = ConfigText(default="#00ededed", visible_width=12, fixed_size=False)  # wdcolor
config.plugins.Aglare.odem1_color1 = ConfigText(default='080b11', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem1_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem2_color1 = ConfigText(default='2d3d5b', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem2_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem3_color1 = ConfigText(default='222e47', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem3_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem4_color1 = ConfigText(default='1a2336', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem4_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem5_color1 = ConfigText(default='171a1c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem5_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem6_color1 = ConfigText(default='28343b', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem6_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem7_color1 = ConfigText(default='3e4b53', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem7_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem8_color1 = ConfigText(default='283752', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem8_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem9_color1 = ConfigText(default='4d5e7c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem9_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem10_color1 = ConfigText(default='1d283c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem10_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem11_color1 = ConfigText(default='1d283c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem11_alpha1 = ConfigText(default='26', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem12_color1 = ConfigText(default='171a1c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem12_alpha1 = ConfigText(default='6', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem13_color1 = ConfigText(default='5a5a5a', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem13_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem14_color1 = ConfigText(default='23314c', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem14_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem15_color1 = ConfigText(default='0c101b', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem15_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem16_color1 = ConfigText(default='ededed', visible_width=8, fixed_size=False)
config.plugins.Aglare.odem16_alpha1 = ConfigText(default='0', visible_width=4, fixed_size=False)
config.plugins.Aglare.odem1_color2 = ConfigSelection(default='080b11', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem1_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem2_color2 = ConfigSelection(default='2d3d5b', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem2_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem3_color2 = ConfigSelection(default='222e47', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem3_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem4_color2 = ConfigSelection(default='1a2336', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem4_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem5_color2 = ConfigSelection(default='171a1c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem5_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem6_color2 = ConfigSelection(default='28343b', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem6_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem7_color2 = ConfigSelection(default='3e4b53', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem7_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem8_color2 = ConfigSelection(default='283752', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem8_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem9_color2 = ConfigSelection(default='4d5e7c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem9_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem10_color2 = ConfigSelection(default='1d283c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem10_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem11_color2 = ConfigSelection(default='1d283c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem11_alpha2 = ConfigSelection(default='33', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem12_color2 = ConfigSelection(default='171a1c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem12_alpha2 = ConfigSelection(default='1A', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem13_color2 = ConfigSelection(default='5a5a5a', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem13_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem14_color2 = ConfigSelection(default='23314c', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem14_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem15_color2 = ConfigSelection(default='0c101b', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem15_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)
config.plugins.Aglare.odem16_color2 = ConfigSelection(default='ededed', choices=BG_COLOR_CHOICES)
config.plugins.Aglare.odem16_alpha2 = ConfigSelection(default='00', choices=TRANSPARENCY_CHOICES)

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
config.plugins.Aglare.InfobarECM = ConfigSelection(default='infobar_ecm_off', choices=[
    ('infobar_ecm_off', _('OFF')),
    ('infobar_ecm_on', _('ON'))
])
config.plugins.Aglare.InfobarPosterx = ConfigSelection(default='infobar_posters_posterx_off', choices=[
    ('infobar_posters_posterx_off', _('OFF')),
    ('infobar_posters_posterx_on', _('ON')),
    ('infobar_posters_posterx_on_all1', _('ALL1')),
    ('infobar_posters_posterx_on_all2', _('ALL2')),
    ('infobar_posters_posterx_cd1', _('CD1')),
    ('infobar_posters_posterx_cd2', _('CD2')),
    ('infobar_posters_posterx_ecm', _('1 poster'))
])
config.plugins.Aglare.InfobarXtraevent = ConfigSelection(default='infobar_posters_xtraevent_off', choices=[
    ('infobar_posters_xtraevent_off', _('OFF')),
    ('infobar_posters_xtraevent_on', _('ON')),
    ('infobar_posters_xtraevent_cd', _('CD')),
    ('infobar_posters_xtraevent_info', _('Backdrop')),
    ('infobar_posters_xtraevent_ecm', _('1 poster'))
])
config.plugins.Aglare.InfobarDate = ConfigSelection(default='infobar_no_date', choices=[
    ('infobar_no_date', _('Infobar_NO_Date')),
    ('infobar_date1', _('Infobar_Date1')),
    ('infobar_date2', _('Infobar_Date2')),
    ('infobar_date3', _('Infobar_Date3')),
    ('infobar_date4', _('Infobar_Date4')),
    ('infobar_date5', _('Infobar_Date5')),
])

config.plugins.Aglare.InfobarWeather = ConfigSelection(default='infobar_no_weather', choices=[
    ('infobar_no_weather', _('Infobar_NO_Weather')),
    ('infobar_MSNweather', _('Infobar_MSNWeather')),
    ('infobar_OAweather', _('Infobar_OAWeather'))
])
config.plugins.Aglare.SecondInfobarStyle = ConfigSelection(default='secondinfobar_base1', choices=[
    ('secondinfobar_base1', _('Default')),
    ('secondinfobar_base2', _('Style2')),
    ('secondinfobar_base3', _('Style3')),
    ('secondinfobar_base4', _('Style4'))
])
config.plugins.Aglare.SecondInfobarWeather = ConfigSelection(default='secondinfobar_no_weather', choices=[
    ('secondinfobar_no_weather', _('Second Infobar_NO_Weather')),
    ('secondinfobar_MSNweather', _('Second Infobar_MSNWeather')),
    ('secondinfobar_OAweather', _('Second Infobar_OAWeather'))
])
config.plugins.Aglare.SecondInfobarPosterx = ConfigSelection(default='secondinfobar_posters_posterx_off', choices=[
    ('secondinfobar_posters_posterx_off', _('OFF')),
    ('secondinfobar_posters_posterx_on', _('ON')),
    ('secondinfobar_posters_posterx_on_all1', _('ALL1'))
])
config.plugins.Aglare.SecondInfobarXtraevent = ConfigSelection(default='secondinfobar_posters_xtraevent_off', choices=[
    ('secondinfobar_posters_xtraevent_off', _('OFF')),
    ('secondinfobar_posters_xtraevent_on', _('ON'))
])
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
    ('channellist_6_posters_PX_all1', _('ChannelSelection_6_Posters_PX_ALL1')),
    ('channellist_6_posters_EX', _('ChannelSelection_6_Posters_EX')),
    ('channellist_big_mini_tv', _('ChannelSelection_big_mini_tv'))
])
config.plugins.Aglare.EventView = ConfigSelection(default='eventview_no_posters', choices=[
    ('eventview_no_posters', _('EventView_NO_Posters')),
    ('eventview_7_posters', _('EventView_7_Posters')),
    ('eventview_7_posters_all1', _('EventView_7_Posters_ALL1'))
])
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
config.plugins.Aglare.E2iplayerskins = ConfigSelection(default='e2iplayer_skin_off', choices=[
    ('e2iplayer_skin_off', _('OFF')),
    ('e2iplayer_skin_on', _('ON'))
])
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
