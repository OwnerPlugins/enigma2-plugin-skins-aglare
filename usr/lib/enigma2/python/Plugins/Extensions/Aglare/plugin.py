#!/usr/bin/python
# -*- coding: utf-8 -*-
# # skin name = Aglare-PLI-FHD # #
###################################
# # __author__ = "Lululla"      # #
# # __copyright__ = "AGP Team"  # #
# # __modified_by__ = "MNASR"   # #
###################################
from __future__ import absolute_import, print_function

# Standard library
import json
import re
import shutil
from glob import glob as glob_glob
from os import listdir, makedirs, remove, stat, system as os_system
from os.path import exists, join

from pathlib import Path
from time import localtime, mktime
from urllib.request import Request, urlopen

# Third-party libraries
from PIL import Image, ImageDraw, ImageFont
from twisted.internet import reactor

# Enigma2 core
from enigma import ePicLoad, eTimer, loadPic

# Enigma2 Components
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.AVSwitch import AVSwitch
from Components.config import (
    config,
    configfile,
    ConfigNothing,
    ConfigSelection,
    ConfigSubsection,
    getConfigListEntry,
    NoSave
)
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.Progress import Progress
from Components.Sources.StaticText import StaticText

# Enigma2 Plugins
from Plugins.Plugin import PluginDescriptor

# Enigma2 Screens
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Standby import TryQuitMainloop
from Screens.VirtualKeyBoard import VirtualKeyBoard


# Enigma2 Tools
from Tools.Directories import fileExists
from Tools.Downloader import downloadWithProgress

# Plugin-local imports
from . import _
from .Agp_Substitute import AglareTitleSubstituteScreen
from .api_config import ApiKeyManager, BG_COLOR_CHOICES, TRANSPARENCY_CHOICES, cfg
from .DownloadControl import startBackdropAutoDB, startPosterAutoDB

skinversion = ''
api_key_manager = ApiKeyManager()
version = '7.2'


ECM_COMBO_CHOICES = [
    ('source prov caid ecm_time', _('Source + Prov + Caid + ECM Time')),
    ('source prov caid server port ecm_time', _(
        'Source + Prov + Caid + Server + Port + ECM Time')),
    ('source caid reader ecm_time', _('Source + Caid + Reader + ECM Time')),
    ('source prov caid protocol server port ecm_time', _(
        'Source + Prov + Caid + Protocol + Server + Port + ECM Time')),
    ('source caid reader protocol server port ecm_time', _(
        'Source +  Caid + Reader + Protocol + Server + Port + ECM Time')),
    ('caid reader protocol server ecm_time', _(
        'Caid + Reader + Protocol + Server + ECM Time')),
    ('caid protocol server ecm_time', _('Caid + Protocol + Server + ECM Time')),
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
    ret_time = mktime((now_time.tm_year, now_time.tm_mon, now_time.tm_mday,
                      hours, minutes, 0, now_time.tm_wday, now_time.tm_yday, now_time.tm_isdst))
    return ret_time


def isMountedInRW(mount_point):
    with open("/proc/mounts", "r") as f:
        for line in f:
            parts = line.split()
            if len(parts) > 1 and parts[1] == mount_point:
                return True
    return False


def ensure_writable_path(base_path, subdir="poster"):
    """Tenta di creare la cartella e verifica la scrivibilità.
       Restituisce (path, ok) dove ok è True se il percorso è utilizzabile."""
    target = join(base_path, subdir)
    try:
        makedirs(target, exist_ok=True)
        # Verifica che il mount point sia RW (o testa con un file)
        if isMountedInRW(base_path):
            return target, True
        else:
            return target, False
    except Exception:
        return target, False


base = cfg.xpath.value
poster_path, poster_ok = ensure_writable_path(base, "poster")
backdrop_path, backdrop_ok = ensure_writable_path(base, "backdrop")

if poster_ok and backdrop_ok:
    path_poster = poster_path
    patch_backdrop = backdrop_path
else:
    # Fallback a /tmp (o eventualmente ad altre cartelle)
    path_poster = "/tmp/poster"
    patch_backdrop = "/tmp/backdrop"
    # Opzionale: tenta di creare /tmp/poster e /tmp/backdrop
    makedirs(path_poster, exist_ok=True)
    makedirs(patch_backdrop, exist_ok=True)

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
    'colorcustom': 'Default',
    'colorcustom2': 'Default',
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
                <widget name="ColorPreview" position="1455,20" size="100,100" zPosition="2" />
                <widget name="config" font="Regular; 24" itemHeight="50" position="5,5" scrollbarMode="showOnDemand" size="990,600" />
                <widget name="description" position="1057,445" size="498,150" font="Regular;24" foregroundColor="white" backgroundColor="#12000000" transparent="0" valign="top" halign="left" />
            </screen>
        '''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.version = skinversion
        self.skinFile = join("/usr/share/enigma2",
                             config.skin.primary_skin.value)
        print("self.skinFile: {}".format(self.skinFile))

        if cfg.ImageGroup.value == 'openpli':
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample_pli/'
        else:
            self.previewFiles = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/sample/'

        self["epg_actions"] = ActionMap(["SetupActions", "ColorActions", "EPGSelectActions"], {
            "epg": self.openTitleSubstitution,
            "info": self.openTitleSubstitution,  # Catch remotes where info acts as EPG
        }, -2)

        self.colorPresetDir = '/etc/enigma2/aglare'
        self.export_custom1_colors_action = None
        self.import_custom1_colors_choice = None
        self.export_custom2_colors_action = None
        self.import_custom2_colors_choice = None

        self['Preview'] = Pixmap()
        self['ColorPreview'] = Pixmap()
        self['description'] = Label('')
        self.onChangedEntry = []
        self.setup_title = (cur_skin)

        list = []
        section = '--------------------------( GENERAL SKIN  SETUP )-----------------------'
        list.append(getConfigListEntry(section))
        section = '--------------------------( APIKEY SKIN SETUP )-----------------------'
        list.append(getConfigListEntry(section))
        ConfigListScreen.__init__(
            self, list, session=self.session, on_change=self.changedEntry)

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
                "ok": self.keyRun,
                "info": self.info,
                "blue": self.info,
                "tv": self.Checkskin,
                "back": self.keyExit,
                "text": self.KeyText,
                "showVirtualKeyboard": self.KeyText
            },
            -1
        )
        self.createSetup()
        self.PicLoad = ePicLoad()
        self.Scale = AVSwitch().getFramebufferScale()

        self.previewRefreshTimer = eTimer()
        try:
            self.previewRefreshTimer_conn = self.previewRefreshTimer.timeout.connect(
                self._delayed_preview_refresh)
        except BaseException:
            self.previewRefreshTimer.callback.append(
                self._delayed_preview_refresh)

        self.onLayoutFinish.append(self.ShowPicture)
        self.onLayoutFinish.append(self.ShowColorPreview)
        self.onLayoutFinish.append(self.__layoutFinished)
        self.onLayoutFinish.append(self.updateDescription)

    def openTitleSubstitution(self):
        self.session.open(AglareTitleSubstituteScreen)

    def __layoutFinished(self):
        self.setTitle(self.setup_title)

    def passs(self, foo):
        pass

    def KeyText(self):
        sel = self["config"].getCurrent()
        if not sel:
            return

        key = self._current_config_key() if hasattr(
            self, "_current_config_key") else None
        current_text = self["config"].getCurrent()[1].value

        if key in ('odem1', 'odem2', 'odem3', 'odem4', 'odem5', 'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16'):
            current_text = (current_text or '').strip()
            if current_text:
                current_text = self._normalize_color_input(current_text)
                if not current_text.startswith('#'):
                    current_text = '#' + current_text
            else:
                current_text = '#'
        elif key and key.endswith('_color1'):
            current_text = self._normalize_rgb6_input(current_text, '000000')
        elif key and key.endswith('_alpha1'):
            current_text = self._normalize_pct_input(current_text, '0')

        self.session.openWithCallback(
            self.VirtualKeyBoardCallback,
            VirtualKeyBoard,
            title=self["config"].getCurrent()[0],
            text=current_text
        )

    def _normalize_color_input(self, value):
        value = (value or '').strip()
        if not value:
            return '#'
        if not value.startswith('#'):
            value = '#' + value
        hex_part = value[1:]
        if re.match(r'^[0-9A-Fa-f]{6}$', hex_part):
            return '#' + '00' + hex_part.lower()
        if re.match(r'^[0-9A-Fa-f]{8}$', hex_part):
            return '#' + hex_part.lower()
        return value

    def _is_valid_color_input(self, value):
        return bool(re.match(r'^#[0-9A-Fa-f]{8}$', value or ''))

    def _alpha_percent_from_color(self, value):
        value = self._normalize_preview_color(value, '#00080b11')
        try:
            alpha = int(value[1:3], 16)
            percent = int(round((alpha / 255.0) * 100))
            return percent
        except Exception:
            return 0

    def _delayed_preview_refresh(self):
        self._refresh_preview_after_color_edit()

    def _refresh_preview_after_color_edit(self):
        try:
            idx = self["config"].getCurrentIndex()
        except Exception:
            idx = None

        try:
            current = self["config"].getCurrent()
            if current:
                self["config"].invalidate(current)
        except Exception:
            pass

        self.updateDescription()
        self.ShowPicture()
        self.ShowColorPreview()

        try:
            if idx is not None:
                prev_idx = max(0, idx - 1)
                self["config"].setCurrentIndex(prev_idx)
                self.ShowPicture()
                self["config"].setCurrentIndex(idx)
                self["config"].invalidate(self["config"].getCurrent())
        except Exception as e:
            print("refresh preview error:", e)

        self.updateDescription()
        self.ShowPicture()

    def VirtualKeyBoardCallback(self, callback=None):
        if callback is None:
            return

        current = self["config"].getCurrent()
        if not current or len(current) <= 1:
            return

        key = self._current_config_key() if hasattr(
            self, "_current_config_key") else None
        old_value = current[1].value
        value = callback

        if key in ('odem1', 'odem2', 'odem3', 'odem4', 'odem5', 'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16'):
            value = self._normalize_color_input(callback)
            if not self._is_valid_color_input(value):
                self.session.open(
                    MessageBox,
                    _('Invalid color value. Use #RRGGBB or #AARRGGBB, for example ff0000 or #80ff0000'),
                    MessageBox.TYPE_ERROR,
                    timeout=5
                )
                try:
                    current[1].value = old_value
                    self["config"].invalidate(current)
                except Exception:
                    pass
                self.ShowPicture()
                self.ShowColorPreview()
                return
        elif key and key.endswith('_color1'):
            value = self._normalize_rgb6_input(callback, '')
            if not re.match(r'^[0-9a-f]{6}$', value or ''):
                self.session.open(
                    MessageBox,
                    _('Invalid color value. Use exactly 6 hex digits, for example ff0000'),
                    MessageBox.TYPE_ERROR,
                    timeout=5
                )
                try:
                    current[1].value = old_value
                    self["config"].invalidate(current)
                except Exception:
                    pass
                self.ShowPicture()
                self.ShowColorPreview()
                return
        elif key and key.endswith('_alpha1'):
            value = self._normalize_pct_input(callback, old_value)

        current[1].value = value
        try:
            current[1].save()
        except Exception:
            pass
        self["config"].invalidate(current)

        if key in ('odem1', 'odem2', 'odem3', 'odem4', 'odem5', 'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16') and cfg.colorSelector.value == 'colorcustom':
            self.ShowPicture()
            try:
                self.previewRefreshTimer.start(50, True)
            except Exception:
                self._refresh_preview_after_color_edit()
        else:
            self.ShowPicture()
        return

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

    def _custom1_slots(self):
        return list(range(1, 17))

    def _custom1_color_key(self, idx):
        return 'odem{}_color1'.format(idx)

    def _custom1_alpha_key(self, idx):
        return 'odem{}_alpha1'.format(idx)

    def _normalize_rgb6_input(self, value, fallback='000000'):
        value = (value or '').strip().lower().replace('#', '')
        return value if re.match(r'^[0-9a-f]{6}$', value) else fallback

    def _normalize_pct_input(self, value, fallback='0'):
        value = (value or '').strip()
        if re.match(r'^\d{1,3}$', value):
            return str(max(0, min(100, int(value))))
        return str(fallback)

    def _percent_to_alpha_hex(self, pct_text):
        pct = int(self._normalize_pct_input(pct_text, '0'))
        return '{:02X}'.format(int(round((pct / 100.0) * 255)))

    def _custom1_combined_value(self, idx):
        return '#{}{}'.format(
            self._percent_to_alpha_hex(
                getattr(cfg, self._custom1_alpha_key(idx)).value),
            self._normalize_rgb6_input(
                getattr(cfg, self._custom1_color_key(idx)).value, '000000')
        )

    def _sync_custom1_hex_values(self):
        if cfg.colorSelector.value != 'colorcustom':
            return
        for idx in self._custom1_slots():
            getattr(cfg, 'odem{}'.format(idx)
                    ).value = self._custom1_combined_value(idx)

    def _color_description_map(self):
        return {
            1: _('Screen background upper color.'),
            2: _('Screen background middle color.'),
            3: _('Screen background lower color.'),
            4: _('Buttons background color.'),
            5: _('List background color.'),
            6: _('Rounded icon background upper color.'),
            7: _('Rounded icon background lower color.'),
            8: _('Menu selector middle color.'),
            9: _('Menu selector upper and lower color.'),
            10: _('Infobar lower color.'),
            11: _('Infobar upper color.'),
            12: _('Second Infobar background color.'),
            13: _('Progress bar background color.'),
            14: _('Screen icon background left color.'),
            15: _('Screen icon background right color.'),
            16: _('window title foreground.')
        }

    def _custom2_slots(self):
        return list(range(1, 17))

    def _custom2_color_key(self, idx):
        return 'odem{}_color2'.format(idx)

    def _custom2_alpha_key(self, idx):
        return 'odem{}_alpha2'.format(idx)

    def _combine_argb(self, alpha_hex, rgb_hex):
        alpha_hex = (alpha_hex or '00').strip().upper()
        rgb_hex = (rgb_hex or '000000').strip().lower().replace('#', '')
        if len(alpha_hex) != 2:
            alpha_hex = '00'
        if len(rgb_hex) != 6:
            rgb_hex = '000000'
        return '#{}{}'.format(alpha_hex, rgb_hex)

    def _custom2_combined_value(self, idx):
        return self._combine_argb(getattr(cfg, self._custom2_alpha_key(idx)).value, getattr(cfg, self._custom2_color_key(idx)).value)

    def _sync_custom2_hex_values(self):
        if cfg.colorSelector.value != 'colorcustom2':
            return
        for idx in self._custom2_slots():
            getattr(cfg, 'odem{}'.format(idx)
                    ).value = self._custom2_combined_value(idx)

    def _custom_color_keys(self):
        return [
            'odem1', 'odem2', 'odem3', 'odem4', 'odem5', 'odem6', 'odem7', 'odem8',
            'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16'
        ]

    def _ensure_color_preset_dir(self):
        try:
            if not exists(self.colorPresetDir):
                makedirs(self.colorPresetDir)
            return True
        except Exception as e:
            self.session.open(
                MessageBox,
                _('Could not create preset folder: {}').format(str(e)),
                MessageBox.TYPE_ERROR,
                timeout=5
            )
            return False

    def _sanitize_preset_name(self, name):
        name = (name or '').strip()
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', name)
        name = name.strip('._-')
        return name

    def _preset_mode_suffix(self, mode):
        """Return the requested filename suffix.

        Keep the ``custum`` spelling for compatibility with the filename format
        requested by the skin maintainer, for example:
        ``night_custum1_color.json`` and ``night_custum2_color.json``.
        """
        if mode == 'colorcustom2':
            return '_custum2_color.json'
        return '_custum1_color.json'

    def _preset_mode_label(self, mode):
        return 'Custom2' if mode == 'colorcustom2' else 'Custom1'

    def _mode_from_payload(self, payload):
        mode = str(payload.get('mode', '') or '').strip()
        preset_type = str(payload.get('type', '') or '').strip().lower()
        if mode in ('colorcustom', 'colorcustom2'):
            return mode
        if preset_type == 'aglare_custom2_colors':
            return 'colorcustom2'
        if preset_type == 'aglare_custom1_colors':
            return 'colorcustom'
        return ''

    def _preset_matches_mode(self, path, mode):
        filename = Path(path).name.lower()
        suffix = self._preset_mode_suffix(mode)
        if filename.endswith(suffix):
            return True

        # Compatibility with presets produced by older plugin versions.
        try:
            with open(path, 'r') as f:
                payload = json.load(f)
            payload_mode = self._mode_from_payload(payload)
            if payload_mode:
                return payload_mode == mode
            if mode == 'colorcustom2':
                return bool(payload.get('custom2_values') or payload.get('custom2'))
            return bool(payload.get('custom1') or payload.get('colors'))
        except Exception:
            return False

    def _get_color_preset_choices(self, mode):
        try:
            if not exists(self.colorPresetDir):
                return [('', _('No saved {} color styles').format(self._preset_mode_label(mode)))]
            files = sorted(
                [x for x in listdir(self.colorPresetDir) if x.lower().endswith('.json')])
            matching = [x for x in files if self._preset_matches_mode(
                join(self.colorPresetDir, x), mode)]
            if not matching:
                return [('', _('No saved {} color styles').format(self._preset_mode_label(mode)))]
            return [(join(self.colorPresetDir, f), f) for f in matching]
        except Exception:
            return [('', _('No saved {} color styles').format(self._preset_mode_label(mode)))]

    def _build_current_color_payload(self):
        data = {}
        for key in self._custom_color_keys():
            data[key] = getattr(cfg, key).value
        return data

    def _build_current_custom1_payload(self):
        data = {}
        for idx in self._custom1_slots():
            data[self._custom1_color_key(idx)] = getattr(
                cfg, self._custom1_color_key(idx)).value
            data[self._custom1_alpha_key(idx)] = getattr(
                cfg, self._custom1_alpha_key(idx)).value
        return data

    def _choice_display_name(self, choices, current_value):
        current_value = str(current_value or '').strip()
        for value, label in choices:
            if str(value).strip().lower() == current_value.lower():
                return str(label)
        return current_value

    def _build_current_custom2_payload(self, use_display_names=True):
        """Build Custom2 payload.

        Custom2 is presented as named selections in JSON. A second machine-safe
        block is also exported so imports remain reliable if translations change.
        """
        data = {}
        for idx in self._custom2_slots():
            color_key = self._custom2_color_key(idx)
            alpha_key = self._custom2_alpha_key(idx)
            color_value = getattr(cfg, color_key).value
            alpha_value = getattr(cfg, alpha_key).value
            if use_display_names:
                data[color_key] = self._choice_display_name(
                    BG_COLOR_CHOICES, color_value)
                data[alpha_key] = self._choice_display_name(
                    TRANSPARENCY_CHOICES, alpha_value)
            else:
                data[color_key] = color_value
                data[alpha_key] = alpha_value
        return data

    def _resolve_choice_value(self, raw_value, choices, fallback):
        if isinstance(raw_value, dict):
            candidates = [raw_value.get('value'), raw_value.get(
                'name'), raw_value.get('label')]
        else:
            candidates = [raw_value]

        normalized_choices = []
        for value, label in choices:
            normalized_choices.append((str(value).strip(), str(label).strip()))

        for candidate in candidates:
            if candidate is None:
                continue
            candidate = str(candidate).strip()
            candidate_no_hash = candidate.replace('#', '')
            for value, label in normalized_choices:
                if candidate.lower() == value.lower() or candidate_no_hash.lower() == value.lower():
                    return value
                if candidate.lower() == label.lower():
                    return value
        return fallback

    def _apply_imported_custom1_payload(self, payload):
        changed = False
        for idx in self._custom1_slots():
            ck = self._custom1_color_key(idx)
            ak = self._custom1_alpha_key(idx)
            if ck in payload:
                getattr(cfg, ck).value = self._normalize_rgb6_input(
                    str(payload[ck]), '000000')
                changed = True
            if ak in payload:
                getattr(cfg, ak).value = self._normalize_pct_input(
                    str(payload[ak]), '0')
                changed = True
        if changed:
            cfg.colorSelector.value = 'colorcustom'
            self._sync_custom1_hex_values()
        return changed

    def _apply_imported_custom2_payload(self, payload):
        changed = False
        for idx in self._custom2_slots():
            color_key = self._custom2_color_key(idx)
            alpha_key = self._custom2_alpha_key(idx)
            color_entry = getattr(cfg, color_key)
            alpha_entry = getattr(cfg, alpha_key)
            if color_key in payload:
                color_entry.value = self._resolve_choice_value(
                    payload[color_key], BG_COLOR_CHOICES, color_entry.value)
                changed = True
            if alpha_key in payload:
                alpha_entry.value = self._resolve_choice_value(
                    payload[alpha_key], TRANSPARENCY_CHOICES, alpha_entry.value)
                changed = True
        if changed:
            cfg.colorSelector.value = 'colorcustom2'
            self._sync_custom2_hex_values()
        return changed

    def _apply_imported_combined_colors(self, colors, mode):
        """Import legacy combined #AARRGGBB values into the selected custom mode."""
        changed = False
        for idx in self._custom1_slots():
            key = 'odem{}'.format(idx)
            if key not in colors:
                continue
            value = self._normalize_color_input(str(colors[key]))
            if not self._is_valid_color_input(value):
                continue
            alpha_hex = value[1:3].upper()
            rgb_hex = value[3:9].lower()
            if mode == 'colorcustom2':
                color_entry = getattr(cfg, self._custom2_color_key(idx))
                alpha_entry = getattr(cfg, self._custom2_alpha_key(idx))
                color_entry.value = self._resolve_choice_value(
                    rgb_hex, BG_COLOR_CHOICES, color_entry.value)
                alpha_entry.value = self._resolve_choice_value(
                    alpha_hex, TRANSPARENCY_CHOICES, alpha_entry.value)
            else:
                getattr(cfg, self._custom1_color_key(idx)).value = rgb_hex
                pct = int(round((int(alpha_hex, 16) / 255.0) * 100))
                getattr(cfg, self._custom1_alpha_key(idx)).value = str(pct)
            changed = True

        if changed:
            cfg.colorSelector.value = mode
            if mode == 'colorcustom2':
                self._sync_custom2_hex_values()
            else:
                self._sync_custom1_hex_values()
        return changed

    def _refresh_import_choice(self, choice_entry, mode):
        if choice_entry is None:
            return
        choices = self._get_color_preset_choices(mode)
        current = choice_entry.value if hasattr(choice_entry, 'value') else ''
        valid_values = [v for v, _ in choices]
        if current not in valid_values:
            current = choices[0][0]
        choice_entry.setChoices(choices, default=current)

    def _refresh_import_choices(self):
        self._refresh_import_choice(
            self.import_custom1_colors_choice, 'colorcustom')
        self._refresh_import_choice(
            self.import_custom2_colors_choice, 'colorcustom2')

    def _strip_known_preset_suffix(self, preset_name):
        for suffix in (
            '_custum1_color', '_custum2_color',
            '_custom1_color', '_custom2_color',
            '_color'
        ):
            if preset_name.lower().endswith(suffix):
                return preset_name[:-len(suffix)]
        return preset_name

    def _export_color_style_named(self, preset_name, mode):
        preset_name = self._sanitize_preset_name(preset_name)
        if not preset_name:
            self.session.open(
                MessageBox,
                _('Invalid preset name.'),
                MessageBox.TYPE_ERROR,
                timeout=4
            )
            return

        if preset_name.lower().endswith('.json'):
            preset_name = preset_name[:-5]
        preset_name = self._strip_known_preset_suffix(preset_name)
        preset_name += self._preset_mode_suffix(mode)

        if not self._ensure_color_preset_dir():
            return

        if mode == 'colorcustom2':
            self._sync_custom2_hex_values()
            payload = {
                'name': preset_name,
                'type': 'aglare_custom2_colors',
                'version': 3,
                'mode': 'colorcustom2',
                'colors': self._build_current_color_payload(),
                'custom2': self._build_current_custom2_payload(use_display_names=True),
                'custom2_values': self._build_current_custom2_payload(use_display_names=False)
            }
        else:
            self._sync_custom1_hex_values()
            payload = {
                'name': preset_name,
                'type': 'aglare_custom1_colors',
                'version': 3,
                'mode': 'colorcustom',
                'colors': self._build_current_color_payload(),
                'custom1': self._build_current_custom1_payload()
            }

        out_path = join(self.colorPresetDir, preset_name)
        try:
            with open(out_path, 'w') as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            self._refresh_import_choices()
            self.createSetup()
            self.session.open(
                MessageBox,
                _('{} color style exported to {}').format(
                    self._preset_mode_label(mode), out_path),
                MessageBox.TYPE_INFO,
                timeout=4
            )
        except Exception as e:
            self.session.open(
                MessageBox,
                _('Export failed: {}').format(str(e)),
                MessageBox.TYPE_ERROR,
                timeout=5
            )

    def _ask_export_color_style_name(self, mode):
        self.session.openWithCallback(
            lambda name: self._export_color_style_named(name, mode),
            VirtualKeyBoard,
            title=_('Enter {} color style name').format(
                self._preset_mode_label(mode)),
            text=''
        )

    def _import_selected_color_style(self, mode):
        choices = self._get_color_preset_choices(mode)
        valid_choices = [(label, value) for value, label in choices if value]
        if not valid_choices:
            self.session.open(
                MessageBox,
                _('No saved {} color style available to import.').format(
                    self._preset_mode_label(mode)),
                MessageBox.TYPE_INFO,
                timeout=4
            )
            return

        choice_list = [(label, value) for label, value in valid_choices]
        self.session.openWithCallback(
            lambda choice: self._on_color_style_selected(choice, mode),
            ChoiceBox,
            title=_('Select {} color style to import').format(
                self._preset_mode_label(mode)),
            list=choice_list
        )

    def _save_imported_color_values(self, mode):
        try:
            cfg.colorSelector.save()
        except Exception:
            pass

        for idx in self._custom1_slots():
            try:
                getattr(cfg, 'odem{}'.format(idx)).save()
            except Exception:
                pass

        for idx in self._custom1_slots():
            try:
                if mode == 'colorcustom2':
                    getattr(cfg, self._custom2_color_key(idx)).save()
                    getattr(cfg, self._custom2_alpha_key(idx)).save()
                else:
                    getattr(cfg, self._custom1_color_key(idx)).save()
                    getattr(cfg, self._custom1_alpha_key(idx)).save()
            except Exception:
                pass

        try:
            configfile.save()
        except Exception:
            pass

    def _on_color_style_selected(self, choice, mode):
        if not choice:
            return
        preset_path = choice[1]
        try:
            with open(preset_path, 'r') as f:
                payload = json.load(f)

            imported = False
            if mode == 'colorcustom2':
                custom2_payload = payload.get(
                    'custom2_values') or payload.get('custom2', {})
                if custom2_payload:
                    imported = self._apply_imported_custom2_payload(
                        custom2_payload)
            else:
                custom1_payload = payload.get('custom1', {})
                if custom1_payload:
                    imported = self._apply_imported_custom1_payload(
                        custom1_payload)

            if not imported:
                imported = self._apply_imported_combined_colors(
                    payload.get('colors', payload), mode)

            if not imported:
                raise ValueError(_('{} preset data was not found in this file.').format(
                    self._preset_mode_label(mode)))

            self._save_imported_color_values(mode)
            self.createSetup()
            self.ShowPicture()
            self.ShowColorPreview()
            self.session.open(
                MessageBox,
                _('Imported {} color style: {}').format(
                    self._preset_mode_label(mode), Path(preset_path).name),
                MessageBox.TYPE_INFO,
                timeout=4
            )
        except Exception as e:
            self.session.open(
                MessageBox,
                _('Import failed: {}').format(str(e)),
                MessageBox.TYPE_ERROR,
                timeout=5
            )

    def _current_config_key(self):
        current = self["config"].getCurrent()
        if not current or len(current) < 2:
            return None

        entry = current[1]
        for key in (
            'colorSelector',
            'odem1', 'odem2', 'odem3', 'odem4', 'odem5',
            'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16',
            'odem1_color1', 'odem1_alpha1', 'odem2_color1', 'odem2_alpha1', 'odem3_color1', 'odem3_alpha1',
            'odem4_color1', 'odem4_alpha1', 'odem5_color1', 'odem5_alpha1', 'odem6_color1', 'odem6_alpha1',
            'odem7_color1', 'odem7_alpha1', 'odem8_color1', 'odem8_alpha1', 'odem9_color1', 'odem9_alpha1',
            'odem10_color1', 'odem10_alpha1', 'odem11_color1', 'odem11_alpha1', 'odem12_color1', 'odem12_alpha1',
            'odem13_color1', 'odem13_alpha1', 'odem14_color1', 'odem14_alpha1', 'odem15_color1', 'odem15_alpha1',
            'odem16_color1', 'odem16_alpha1',
            'odem1_color2', 'odem1_alpha2', 'odem2_color2', 'odem2_alpha2', 'odem3_color2', 'odem3_alpha2',
            'odem4_color2', 'odem4_alpha2', 'odem5_color2', 'odem5_alpha2', 'odem6_color2', 'odem6_alpha2',
            'odem7_color2', 'odem7_alpha2', 'odem8_color2', 'odem8_alpha2', 'odem9_color2', 'odem9_alpha2',
            'odem10_color2', 'odem10_alpha2', 'odem11_color2', 'odem11_alpha2', 'odem12_color2', 'odem12_alpha2',
            'odem13_color2', 'odem13_alpha2', 'odem14_color2', 'odem14_alpha2', 'odem15_color2', 'odem15_alpha2',
            'odem16_color2', 'odem16_alpha2'
        ):
            try:
                if getattr(cfg, key) is entry:
                    return key
            except Exception:
                pass
        return None

    def _is_custom_color_preview_entry(self):
        key = self._current_config_key()
        return key in (
            'colorSelector',
            'odem1', 'odem2', 'odem3', 'odem4', 'odem5',
            'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16',
            'odem1_color1', 'odem1_alpha1', 'odem2_color1', 'odem2_alpha1', 'odem3_color1', 'odem3_alpha1',
            'odem4_color1', 'odem4_alpha1', 'odem5_color1', 'odem5_alpha1', 'odem6_color1', 'odem6_alpha1',
            'odem7_color1', 'odem7_alpha1', 'odem8_color1', 'odem8_alpha1', 'odem9_color1', 'odem9_alpha1',
            'odem10_color1', 'odem10_alpha1', 'odem11_color1', 'odem11_alpha1', 'odem12_color1', 'odem12_alpha1',
            'odem13_color1', 'odem13_alpha1', 'odem14_color1', 'odem14_alpha1', 'odem15_color1', 'odem15_alpha1',
            'odem16_color1', 'odem16_alpha1',
            'odem1_color2', 'odem1_alpha2', 'odem2_color2', 'odem2_alpha2', 'odem3_color2', 'odem3_alpha2',
            'odem4_color2', 'odem4_alpha2', 'odem5_color2', 'odem5_alpha2', 'odem6_color2', 'odem6_alpha2',
            'odem7_color2', 'odem7_alpha2', 'odem8_color2', 'odem8_alpha2', 'odem9_color2', 'odem9_alpha2',
            'odem10_color2', 'odem10_alpha2', 'odem11_color2', 'odem11_alpha2', 'odem12_color2', 'odem12_alpha2',
            'odem13_color2', 'odem13_alpha2', 'odem14_color2', 'odem14_alpha2', 'odem15_color2', 'odem15_alpha2',
            'odem16_color2', 'odem16_alpha2'
        )

    def _normalize_preview_color(self, value, fallback):
        value = (value or '').strip()
        if len(value) == 9 and value.startswith('#'):
            return value
        return fallback

    def _hex_to_preview_rgb(self, value, fallback):
        value = self._normalize_preview_color(value, fallback)
        try:
            r = int(value[3:5], 16)
            g = int(value[5:7], 16)
            b = int(value[7:9], 16)
            return (r, g, b)
        except Exception:
            return (32, 32, 32)

    def _load_preview_font(self, size=24):
        font_candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/DejaVuSans.ttf',
        ]
        for font_path in font_candidates:
            try:
                if fileExists(font_path):
                    return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _draw_preview_text_center(self, draw, text, y, width=498, fill=(255, 255, 255), size=24):
        font = self._load_preview_font(size)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
        except Exception:
            text_w = len(text) * max(6, int(size * 0.6))
        x = max(0, int((width - text_w) / 2))
        try:
            draw.text((x, y), text, fill=fill, font=font)
        except Exception:
            draw.text((x, y), text, fill=fill)

    def _get_preview_color_value(self):
        key = self._current_config_key()
        fallback_map = {
            'odem1': '#00080b11',
            'odem2': '#002d3d5b',
            'odem3': '#00222e47',
            'odem4': '#001a2336',
            'odem5': '#00171a1c',
            'odem6': '#0028343b',
            'odem7': '#003e4b53',
            'odem8': '#00283752',
            'odem9': '#004d5e7c',
            'odem10': '#001d283c',
            'odem11': '#441d283c',
            'odem12': '#10171a1c',
            'odem13': '#005a5a5a',
            'odem14': '#0023314c',
            'odem15': '#000c101b',
            'odem16': '#00ededed',
        }

        if key in fallback_map:
            return self._normalize_preview_color(getattr(cfg, key).value, fallback_map[key]), key

        for idx in self._custom1_slots():
            if key in (self._custom1_color_key(idx), self._custom1_alpha_key(idx)):
                return self._custom1_combined_value(idx), 'odem{}'.format(idx)

        for idx in self._custom2_slots():
            if key in (self._custom2_color_key(idx), self._custom2_alpha_key(idx)):
                return self._custom2_combined_value(idx), 'odem{}'.format(idx)

        if cfg.colorSelector.value == 'colorcustom':
            return self._custom1_combined_value(1), 'odem1'
        if cfg.colorSelector.value == 'colorcustom2':
            return self._custom2_combined_value(1), 'odem1'

        return self._normalize_preview_color(cfg.odem1.value, '#00080b11'), 'odem1'

    def _get_dynamic_preview_path(self):
        preview_path = '/tmp/aglare_dynamic_preview.png'
        color_value, color_key = self._get_preview_color_value()
        rgb = self._hex_to_preview_rgb(color_value, '#00080b11')

        image = Image.new('RGB', (498, 280), rgb)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 497, 279), outline=(255, 255, 255), width=2)
        draw.rectangle((6, 6, 491, 273), outline=(0, 0, 0), width=1)

        strip_fill = (0, 0, 0)
        draw.rectangle((18, 16, 480, 104), fill=strip_fill)
        draw.rectangle((18, 178, 480, 262), fill=strip_fill)

        alpha_percent = self._alpha_percent_from_color(color_value)
        self._draw_preview_text_center(
            draw, 'COLOR PREVIEW', 24, width=498, size=30)
        self._draw_preview_text_center(draw, '{} = {}'.format(
            color_key, color_value), 58, width=498, size=24)
        self._draw_preview_text_center(draw, 'Transparency: {}%'.format(
            alpha_percent), 194, width=498, size=26)
        self._draw_preview_text_center(
            draw, '0% = fully visible, 100% = max alpha', 226, width=498, size=18)

        image.save(preview_path, 'PNG')
        return preview_path

    def _get_screen_preview_for_current_color(self):
        key = self._current_config_key()
        if not key:
            return None
        m = re.match(r'odem(\d+)(?:_(?:color1|alpha1|color2|alpha2))?$', key)
        if not m:
            return None
        path = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/screens/odem{}.jpg'.format(
            m.group(1))
        if fileExists(path):
            return convert_image(path)
        return None

    def _get_color_chip_preview_path(self):
        preview_path = '/tmp/aglare_color_chip_preview.png'
        color_value, _ = self._get_preview_color_value()
        rgb = self._hex_to_preview_rgb(color_value, '#00080b11')

        image = Image.new('RGB', (100, 100), rgb)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 99, 99), outline=(255, 255, 255), width=2)

        image.save(preview_path, 'PNG')
        return preview_path

    def _sync_infobar_dependents_for_style(self):
        current_style = cfg.InfobarStyle.value
        if current_style == 'infobar_base6':
            cfg.InfobarECM.value = 'infobar_ecm_off'
            cfg.InfobarPosterx.value = 'infobar_posters_posterx_off'
            cfg.InfobarXtraevent.value = 'infobar_posters_xtraevent_off'
        elif current_style == 'infobar_base5':
            cfg.InfobarECM.value = 'infobar_ecm_off'
            if cfg.InfobarPosterx.value not in ('infobar_posters_posterx_off', 'infobar_posters_posterx_cd1', 'infobar_posters_posterx_cd2'):
                cfg.InfobarPosterx.value = 'infobar_posters_posterx_off'
            if cfg.InfobarXtraevent.value not in ('infobar_posters_xtraevent_off', 'infobar_posters_xtraevent_cd'):
                cfg.InfobarXtraevent.value = 'infobar_posters_xtraevent_off'

    def createSetup(self):
        try:
            self.editListEntry = None
            self.export_custom1_colors_action = None
            self.import_custom1_colors_choice = None
            self.export_custom2_colors_action = None
            self.import_custom2_colors_choice = None

            current_style = cfg.InfobarStyle.value
            is_style5_cd = (current_style == 'infobar_base5')
            is_style6_default = (current_style == 'infobar_base6')

            if current_style in ('infobar_base5', 'infobar_base6'):
                self._sync_infobar_dependents_for_style()

            is_ecm_on = (cfg.InfobarECM.value == 'infobar_ecm_on')

            if is_style6_default:
                posterx_choices = [('infobar_posters_posterx_off', _('OFF'))]
            elif is_style5_cd:
                posterx_choices = [
                    ('infobar_posters_posterx_off', _('OFF')),
                    ('infobar_posters_posterx_cd1', _('CD1')),
                    ('infobar_posters_posterx_cd2', _('CD2')),
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
                    ('infobar_posters_posterx_on_all1', _('ALL1')),
                    ('infobar_posters_posterx_on_all2', _('ALL2')),
                ]

            if cfg.InfobarPosterx.value not in [v for v, _ in posterx_choices]:
                cfg.InfobarPosterx.value = posterx_choices[0][0]
            cfg.InfobarPosterx.setChoices(posterx_choices)

            if is_style6_default:
                xtraevent_choices = [
                    ('infobar_posters_xtraevent_off', _('OFF'))]
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

            if cfg.InfobarXtraevent.value not in [v for v, _ in xtraevent_choices]:
                cfg.InfobarXtraevent.value = xtraevent_choices[0][0]
            cfg.InfobarXtraevent.setChoices(xtraevent_choices)

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

            # --- GENERAL SKIN SETUP ---
            section = '-------------------------( GENERAL SKIN  SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('Image Compatibility Group:'), cfg.ImageGroup, _(
                'Select the target image base group (OpenPLi vs Others).')))
            list.append(getConfigListEntry(_('Color Style:'), cfg.colorSelector, _(
                'Select the main color preset used by the skin.')))

            desc_map = self._color_description_map()
            if cfg.colorSelector.value == 'colorcustom':
                section = ' ----------( Start Of Colors )----------'
                list.append((_(section), NoSave(ConfigNothing())))
                for idx in self._custom1_slots():
                    list.append(getConfigListEntry(_('  odem{} color').format(idx), getattr(
                        cfg, self._custom1_color_key(idx)), desc_map.get(idx, '')))
                    list.append(getConfigListEntry(_('  odem{} transparency %').format(idx), getattr(cfg, self._custom1_alpha_key(
                        idx)), _('Transparency percent for odem{}. 0 = OFF, 100 = fully transparent.').format(idx)))
                self.export_custom1_colors_action = NoSave(ConfigNothing())
                self.import_custom1_colors_choice = ConfigSelection(
                    default='', choices=self._get_color_preset_choices('colorcustom'))
                list.append(getConfigListEntry(_('  Export Custom1 colors (OK)'), self.export_custom1_colors_action, _(
                    'Export Custom1 color values to /etc/enigma2/aglare as <name>_custum1_color.json.')))
                list.append(getConfigListEntry(_('  Import Custom1 colors'), self.import_custom1_colors_choice, _(
                    'Select a saved Custom1 JSON color style from /etc/enigma2/aglare, then press OK to import it.')))
                section = ' ----------( End Of Colors )----------'
                list.append((_(section), NoSave(ConfigNothing())))
            elif cfg.colorSelector.value == 'colorcustom2':
                section = ' ----------( Start Of Colors )----------'
                list.append((_(section), NoSave(ConfigNothing())))
                for idx in self._custom2_slots():
                    list.append(getConfigListEntry(_('  odem{} color').format(idx), getattr(
                        cfg, self._custom2_color_key(idx)), desc_map.get(idx, '')))
                    list.append(getConfigListEntry(_('  odem{} transparency').format(idx), getattr(
                        cfg, self._custom2_alpha_key(idx)), _('Select transparency for odem{}.').format(idx)))
                self.export_custom2_colors_action = NoSave(ConfigNothing())
                self.import_custom2_colors_choice = ConfigSelection(
                    default='', choices=self._get_color_preset_choices('colorcustom2'))
                list.append(getConfigListEntry(_('  Export Custom2 colors (OK)'), self.export_custom2_colors_action, _(
                    'Export Custom2 named color and transparency selections to /etc/enigma2/aglare as <name>_custum2_color.json.')))
                list.append(getConfigListEntry(_('  Import Custom2 colors'), self.import_custom2_colors_choice, _(
                    'Select a saved Custom2 JSON color style from /etc/enigma2/aglare, then press OK to import it.')))
                section = ' ----------( End Of Colors )----------'
                list.append((_(section), NoSave(ConfigNothing())))

            list.append(getConfigListEntry(_('Select Your Font:'), cfg.FontStyle, _(
                'Select the font package used by the generated skin.')))
            list.append(getConfigListEntry(_('Skin Style:'), cfg.skinSelector, _(
                'Select the base skin layout file.')))
            list.append(getConfigListEntry(_('InfoBar Style:'), cfg.InfobarStyle, _(
                'Select infobar layout. Style5 forces ECM off and allows only OFF/CD poster modes. Style6 forces ECM, PosterX, and Xtraevent off.')))
            list.append(getConfigListEntry(_('InfoBar ECM:'), cfg.InfobarECM, _(
                'Show or hide ECM information in the infobar.')))
            list.append(getConfigListEntry(_('InfoBar PosterX:'), cfg.InfobarPosterx, _(
                'Select PosterX display mode for the infobar.')))
            list.append(getConfigListEntry(_('InfoBar Xtraevent:'), cfg.InfobarXtraevent, _(
                'Select XtraEvent display mode for the infobar.')))
            list.append(getConfigListEntry(_('InfoBar Date:'), cfg.InfobarDate, _(
                'Show or hide the date panel in the infobar.')))
            list.append(getConfigListEntry(_('InfoBar Weather:'), cfg.InfobarWeather, _(
                'Select weather provider display for the infobar.')))
            list.append(getConfigListEntry(_('SecondInfobar Style:'),
                        cfg.SecondInfobarStyle, _('Select second infobar layout.')))
            list.append(getConfigListEntry(_('SecondInfobar Weather:'), cfg.SecondInfobarWeather, _(
                'Select weather provider display for the second infobar.')))
            list.append(getConfigListEntry(_('SecondInfobar Posterx:'), cfg.SecondInfobarPosterx, _(
                'Show or hide PosterX in the second infobar.')))
            list.append(getConfigListEntry(_('SecondInfobar Xtraevent:'), cfg.SecondInfobarXtraevent, _(
                'Show or hide XtraEvent in the second infobar.')))
            list.append(getConfigListEntry(_('ChannelSelection Style:'), cfg.ChannSelector, _(
                'Select channel selection screen style.')))
            list.append(getConfigListEntry(_('EventView Style:'),
                        cfg.EventView, _('Select event view screen style.')))
            list.append(getConfigListEntry(_('VolumeBar Style:'),
                        cfg.VolumeBar, _('Select volume bar style.')))
            list.append(getConfigListEntry(_('Enable Poster:'), cfg.show_poster, _(
                "Enable or disable the display of posters.")))
            list.append(getConfigListEntry(_('Enable Backdrop:'), cfg.show_backdrop, _(
                "Enable or disable the display of backdrops.")))
            list.append(getConfigListEntry(_('Enable Logo:'), cfg.show_logo, _(
                "Enable or disable the display of channel/event logos.")))
            list.append(getConfigListEntry(_('Enable Rating Star:'), cfg.rating_source, _(
                "Enable the display of rating stars for events.")))
            list.append(getConfigListEntry(_('Enable Parental Icons:'), cfg.info_parental_mode, _(
                "Show parental guidance icons on events.")))
            list.append(getConfigListEntry(_('Enable Display InfoEvents:'), cfg.info_display_mode, _(
                "Enable extended event information (cast, crew, plot) in the info widget.")))
            list.append(getConfigListEntry(_('Enable Display Genre icons:'),
                        cfg.genre_source, _("Show genre icons for events.")))

            # --- Special Appearance ---
            section = '--------------------------( Special Appearance )-----------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('Channel Foreground Color:'),
                        cfg.ChannForegroundColor, _('Select channel list foreground color.')))
            list.append(getConfigListEntry(_('Channel Selected Foreground Color:'),
                        cfg.ChannForegroundColorSelected, _('Select channel list selected foreground color.')))
            list.append(getConfigListEntry(_('Channel Description Color:'), cfg.ChannServiceDescriptionColor, _(
                'Select channel list event description color.')))
            list.append(getConfigListEntry(_('Channel Selected Description Color:'),
                        cfg.ChannServiceDescriptionColorSelected, _('Select selected channel event description color.')))
            list.append(getConfigListEntry(_('ECM Short Format:'), cfg.myemupara, _(
                'Select which ECM fields are shown when the skin uses Short MYEMUPARA.')))
            list.append(getConfigListEntry(_('Bitrate Unit:'), cfg.bitrate_unit, _(
                'Choose whether bitrate is shown in Kb/s or Mb/s.')))

            # --- Special Plugins ---
            section = '--------------------------( Special Plugins )-----------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('Support E2iplayer Skins:'), cfg.E2iplayerskins, _(
                'Enable or disable bundled E2iPlayer screens.')))

            # --- EMC DISPLAY TOGGLES ---
            section = '--------------------------( EMC DISPLAY TOGGLES )-----------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('EMC screens Style:'),
                        cfg.Emc, _('Select EMC style.')))
            list.append(getConfigListEntry(_('Enable Display XMC Poster:'),
                        cfg.xemc_poster, _("Show poster from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Backdrop:'),
                        cfg.xemc_backdrop, _("Show backdrop from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Logo:'),
                        cfg.xemc_logo, _("Show logo from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Info:'),
                        cfg.xemc_info, _("Show info from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Star:'),
                        cfg.xemc_star, _("Show star from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Cast:'),
                        cfg.xemc_cast, _("Show cast from movie in local folder")))
            list.append(getConfigListEntry(_('Enable Display XMC Parental:'),
                        cfg.xemc_parental, _("Show parental from movie in local folder")))

            # --- UTILITY SKIN SETUP ---
            section = '--------------------------( UTILITY SKIN SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry(_('Choice device download image folder'), cfg.xpath, _(
                "This operation assign device path folder to download image (Poster-Backdrop)")))
            list.append(getConfigListEntry(_('Remove all png (poster - backdrop) (OK)'), cfg.png,
                        _("This operation remove all png from folder device (Poster-Backdrop)")))

            # --- APIKEY SKIN SETUP ---
            section = '---------------------------( APIKEY SKIN SETUP )------------------------'
            list.append((_(section), NoSave(ConfigNothing())))
            list.append(getConfigListEntry("API KEY SETUP:",
                        cfg.actapi, _("Settings Apikey Server")))

            if cfg.actapi.value:
                for api in api_key_manager.API_CONFIG:
                    upper = api.upper()
                    list.append(getConfigListEntry(
                        "{}:".format(upper), getattr(cfg, api), _(
                            "Activate/Deactivate {}".format(upper))
                    ))
                    if getattr(cfg, api).value:
                        cfg_ap = api_key_manager.API_CONFIG[api]
                        list.append(getConfigListEntry(
                            "-- Load Key {}".format(upper), cfg_ap['load_action'], _(
                                "Load from /tmp/{}key.txt".format(api))
                        ))
                        list.append(getConfigListEntry(
                            "-- Set key {}".format(upper), cfg_ap['config_entry'], _(
                                "Personal API key for {}".format(upper))
                        ))

                list.append(getConfigListEntry(
                    "ELCINEMA:", cfg.elcinema, _("Activate/Deactivate ELCINEMA")))
                list.append(getConfigListEntry(
                    "GOOGLE:", cfg.google, _("Activate/Deactivate GOOGLE")))
                list.append(getConfigListEntry(
                    "IMDB:", cfg.imdb, _("Activate/Deactivate IMDB")))
                list.append(getConfigListEntry(
                    "MOLOTOV:", cfg.molotov, _("Activate/Deactivate MOLOTOV")))
                list.append(getConfigListEntry(
                    "PROGRAMMETV:", cfg.programmetv, _("Activate/Deactivate PROGRAMMETV")))
                section = '------------------------------------------------------------------------'
                list.append((_(section), NoSave(ConfigNothing())))
                if cfg.actapi.value:
                    list.append(getConfigListEntry("Use Cache on download:", cfg.cache, _(
                        "Enable or disable caching during event download to speed up repeated searches.")))
                    list.append(getConfigListEntry(_('Download now poster'), cfg.download_now_poster, _(
                        "Start downloading poster immediately")))
                    list.append(getConfigListEntry(_('Automatic download of poster'), cfg.pstdown, _(
                        "Automatically fetch posters for favorite events based on EPG")))
                    if cfg.pstdown.value is True:
                        list.append(getConfigListEntry(_('Set Time our - minute for Poster download'), cfg.pscan_time, _(
                            "Configure the delay time (in minutes) before starting the automatic poster download")))
                    list.append(getConfigListEntry(_('Download now backdrop'), cfg.download_now_backdrop, _(
                        "Start downloading backdrop immediately")))
                    list.append(getConfigListEntry(_('Automatic download of backdrop'), cfg.bkddown, _(
                        "Automatically fetch backdrop for favorite events based on EPG")))
                    if cfg.bkddown.value is True:
                        list.append(getConfigListEntry(_('Set Time our - minute for Backdrop download'), cfg.bscan_time, _(
                            "Configure the delay time (in minutes) before starting the automatic poster download")))

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
            MessageBox.TYPE_YESNO
        )

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
        PicturePath = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/screens/default.jpg'

        if self._is_custom_color_preview_entry() and cfg.colorSelector.value in ('colorcustom', 'colorcustom2'):
            custom_screen = self._get_screen_preview_for_current_color()
            if custom_screen:
                return custom_screen
            return convert_image(PicturePath)

        current = self['config'].getCurrent()
        returnValue = current[1].value if current and len(
            current) > 1 else None
        if not isinstance(returnValue, str):
            return convert_image(PicturePath)

        path = '/usr/lib/enigma2/python/Plugins/Extensions/Aglare/screens/' + returnValue + '.jpg'
        if fileExists(path):
            return convert_image(path)
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

    def ShowColorPreview(self, data=None):
        if self["ColorPreview"].instance:
            size = self['ColorPreview'].instance.size()
            if size.isNull():
                size.setWidth(100)
                size.setHeight(100)
            pixmapx = self._get_color_chip_preview_path()
            if not fileExists(pixmapx):
                return
            png = loadPic(pixmapx, size.width(), size.height(), 0, 0, 0, 1)
            self["ColorPreview"].instance.setPixmap(png)

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
                cur_skin, version),
            MessageBox.TYPE_INFO
        )
        aboutbox.setTitle(_("Setup Aglare Skin Info"))

    def removPng(self):
        self.session.openWithCallback(
            self.removPng2,
            MessageBox,
            _("[RemovePng] This operation will remove all PNGs from the device folder (Poster-Backdrop)...\nDo you really want to continue?"),
            MessageBox.TYPE_YESNO
        )

    def removPng2(self, result):
        if result:
            print('from remove png......')
            removePng()
            print('png are removed')
            aboutbox = self.session.open(MessageBox, _(
                'All png are removed from folder!'), MessageBox.TYPE_INFO)
            aboutbox.setTitle(_('Info...'))

    def keyRun(self):
        sel = self["config"].getCurrent()[1]
        if not sel:
            return

        action_map = {
            cfg.png: self.handle_png,
            **{getattr(cfg, f"load_{api}_api"): lambda x=api: self.handle_api_load(x) for api in api_key_manager.API_CONFIG},
            **{getattr(cfg, f"{api}_api"): self.KeyText for api in api_key_manager.API_CONFIG},
            cfg.download_now_poster: lambda: self.handle_download_now_poster(),
            cfg.download_now_backdrop: lambda: self.handle_download_now_backdrop(),
        }

        handler = action_map.get(sel)
        if handler:
            handler()
            return

        if self.export_custom1_colors_action is not None and sel is self.export_custom1_colors_action:
            self._ask_export_color_style_name('colorcustom')
            return
        if self.import_custom1_colors_choice is not None and sel is self.import_custom1_colors_choice:
            self._import_selected_color_style('colorcustom')
            return
        if self.export_custom2_colors_action is not None and sel is self.export_custom2_colors_action:
            self._ask_export_color_style_name('colorcustom2')
            return
        if self.import_custom2_colors_choice is not None and sel is self.import_custom2_colors_choice:
            self._import_selected_color_style('colorcustom2')
            return

        key = self._current_config_key() if hasattr(
            self, "_current_config_key") else None
        if key in ('odem1', 'odem2', 'odem3', 'odem4', 'odem5', 'odem6', 'odem7', 'odem8', 'odem9', 'odem10', 'odem11', 'odem12', 'odem13', 'odem14', 'odem15', 'odem16') or (key and (key.endswith('_color1') or key.endswith('_alpha1'))):
            self.KeyText()

    def handle_download_now_poster(self):
        try:
            current_session = self.session
            cfg.download_now_poster.value = False
            cfg.download_now_poster.save()

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
                    timeout=5
                )

            current_session.open(
                MessageBox,
                _("Poster download will start in 2 minutes.\nYou can safely exit this menu."),
                MessageBox.TYPE_INFO,
                timeout=5
            )

            def _start_download(session_ref=current_session):
                try:
                    startPosterAutoDB(enabled_providers, session=session_ref)
                except Exception as e:
                    reactor.callFromThread(session_ref.open, MessageBox, _(
                        "Error: {}").format(str(e)), MessageBox.TYPE_ERROR)

            reactor.callLater(120, reactor.callInThread, _start_download)
        except Exception as e:
            self.session.open(MessageBox, _("Poster download error: {}").format(
                str(e)), MessageBox.TYPE_ERROR)

    def handle_download_now_backdrop(self):
        try:
            current_session = self.session
            cfg.download_now_backdrop.value = False
            cfg.download_now_backdrop.save()

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
                current_session.open(MessageBox, _(
                    "Warning: You are using default API keys!\nWe strongly recommend configuring your own API keys in the plugin settings."), MessageBox.TYPE_INFO, timeout=5)
            current_session.open(MessageBox, _(
                "Backdrop download will start in 2 minutes.\nYou can safely exit this menu."), MessageBox.TYPE_INFO, timeout=5)

            def _start_download(session_ref=current_session):
                try:
                    startBackdropAutoDB(enabled_providers, session=session_ref)
                except Exception as e:
                    reactor.callFromThread(session_ref.open, MessageBox, _(
                        "Error: {}").format(str(e)), MessageBox.TYPE_ERROR)

            reactor.callLater(120, reactor.callInThread, _start_download)
        except Exception as e:
            self.session.open(MessageBox, _("Backdrop download error: {}").format(
                str(e)), MessageBox.TYPE_ERROR)

    def handle_api_load(self, api, answer=None):
        cfg = api_key_manager.API_CONFIG[api]
        api_file = f"/tmp/{api}key.txt"
        skin_file = getattr(api_key_manager, f"{api}_skin")

        if answer is None:
            if fileExists(api_file):
                file_info = stat(api_file)
                if file_info.st_size > 0:
                    self.session.openWithCallback(
                        lambda answer: self.handle_api_load(api, answer),
                        MessageBox,
                        _("Import key {0} from {1}?").format(
                            api.upper(), api_file)
                    )
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
        self.ShowColorPreview()
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
            **{getattr(cfg, "load_%s_api" % api): (getattr(cfg, "load_%s_api" % api), self.make_api_handler(api)) for api in api_key_manager.API_CONFIG}
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
        self.updateDescription()

    def keyRight(self):
        ConfigListScreen.keyRight(self)
        self.handleKeyActions()
        self.updateDescription()

    def keyDown(self):
        self['config'].instance.moveSelection(self['config'].instance.moveDown)
        self.createSetup()
        self.ShowPicture()
        self.ShowColorPreview()
        self.updateDescription()

    def keyUp(self):
        self['config'].instance.moveSelection(self['config'].instance.moveUp)
        self.createSetup()
        self.ShowPicture()
        self.ShowColorPreview()
        self.updateDescription()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        self._sync_custom1_hex_values()
        self._sync_custom2_hex_values()
        self.updateDescription()
        self.ShowPicture()
        self.ShowColorPreview()
        for x in self.onChangedEntry:
            x()

    def getCurrentValue(self):
        if self["config"].getCurrent() and len(self["config"].getCurrent()) > 0:
            return str(self["config"].getCurrent()[1].getText())
        return ""

    def getCurrentEntry(self):
        return self["config"].getCurrent() and self["config"].getCurrent()[0] or ""

    def createSummary(self):
        from Screens.Setup import SetupSummary
        return SetupSummary

    def normalize_hex_color(self, value, fallback):
        value = (value or '').strip()
        if len(value) == 9 and value.startswith('#'):
            return value
        return fallback

    def apply_custom_head_colors(self, content):
        if cfg.colorSelector.value == 'colorcustom':
            self._sync_custom1_hex_values()
        elif cfg.colorSelector.value == 'colorcustom2':
            self._sync_custom2_hex_values()

        color_map = {
            'wpuc': self.normalize_hex_color(cfg.odem1.value, '#00080b11'),
            'wpmc': self.normalize_hex_color(cfg.odem2.value, '#002d3d5b'),
            'wplc': self.normalize_hex_color(cfg.odem3.value, '#00222e47'),
            'buttonsc': self.normalize_hex_color(cfg.odem4.value, '#001a2336'),
            'mcolor2': self.normalize_hex_color(cfg.odem5.value, '#00171a1c'),
            'mcolor3': self.normalize_hex_color(cfg.odem6.value, '#0028343b'),
            'mcolor4': self.normalize_hex_color(cfg.odem7.value, '#003e4b53'),
            'mcolor5': self.normalize_hex_color(cfg.odem8.value, '#00283752'),
            'mcolor6': self.normalize_hex_color(cfg.odem9.value, '#004d5e7c'),
            'mcolor7': self.normalize_hex_color(cfg.odem12.value, '#10171a1c'),
            'igsdt': self.normalize_hex_color(cfg.odem11.value, '#441d283c'),
            'igsd': self.normalize_hex_color(cfg.odem10.value, '#001d283c'),
            'progbg': self.normalize_hex_color(cfg.odem13.value, '#005a5a5a'),
            'sidec1': self.normalize_hex_color(cfg.odem14.value, '#0023314c'),
            'sidec2': self.normalize_hex_color(cfg.odem15.value, '#000c101b'),
            'chselfg': self.normalize_hex_color(cfg.odem16.value, '#00ededed'),
        }
        for color_name, color_value in color_map.items():
            pattern = r'(<color\s+name="%s"\s+value=")[^"]*("\s*/>)' % re.escape(
                color_name)
            content = re.sub(pattern, r'\1%s\2' % color_value, content)
        return content

    def modify_channel_colors(self, content):
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

        block = re.sub(
            r'foregroundColor="[^"]*"', f'foregroundColor="{fg_color}"', block)
        block = re.sub(
            r'foregroundColorSelected="[^"]*"', f'foregroundColorSelected="{fg_selected_color}"', block)
        block = re.sub(
            r'colorServiceDescription="[^"]*"', f'colorServiceDescription="{desc_color}"', block)
        block = re.sub(
            r'colorServiceDescriptionSelected="[^"]*"', f'colorServiceDescriptionSelected="{desc_selected_color}"', block)

        return content[:block_start] + block + content[second:]

    def keySave(self):
        self._sync_infobar_dependents_for_style()
        self._sync_custom1_hex_values()
        self._sync_custom2_hex_values()
        # --- Determine version file path from active skin ---
        cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "")
        if cur_skin == "Aglare-FHD-PLI":
            version_file = "/usr/share/enigma2/Aglare-FHD-PLI/.Aglare-FHD-PLI"
        elif cur_skin == "Aglare-FHD":
            version_file = "/usr/share/enigma2/Aglare-FHD/.Aglare-FHD"
        else:
            self.session.open(
                MessageBox,
                _("Skin not supported."),
                MessageBox.TYPE_ERROR)
            self.close()
            return

        # If version file doesn't exist, create it with current version
        if not fileExists(version_file):
            try:
                with open(version_file, 'w') as f:
                    f.write(version)   # 'version' is defined globally as '7.1'
                print("Version file created:", version_file)
            except Exception as e:
                self.session.open(
                    MessageBox, _("Cannot create version file: {}").format(
                        str(e)), MessageBox.TYPE_ERROR)
                self.close()
                return

        self.version = skinversion
        print("version skin: {}".format(self.version))

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

            if cfg.colorSelector.value in ('colorcustom', 'colorcustom2'):
                head_file = 'head-color0.xml'
            else:
                head_file = 'head-' + cfg.colorSelector.value + '.xml'

            file_path = self.previewFiles + head_file
            if cfg.colorSelector.value in ('colorcustom', 'colorcustom2'):
                try:
                    with open(file_path, 'r') as f:
                        head_content = f.read()
                    head_content = self.apply_custom_head_colors(head_content)
                    skin_lines.extend(head_content.splitlines(True))
                except Exception as e:
                    print("Error processing custom head file {}: {}".format(
                        file_path, e))
            else:
                skin_lines.extend(load_xml_to_skin_lines(file_path))

            xml_files = [
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
                'e2iplayer-' + cfg.E2iplayerskins.value,
            ]

            for filename in xml_files[:11]:
                skin_lines.extend(load_xml_to_skin_lines(
                    self.previewFiles + filename + '.xml'))

            cur_skin = config.skin.primary_skin.value.replace("/skin.xml", "")
            if cur_skin == "Aglare-FHD-PLI":
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
                                    print(
                                        f"Error copying {w_src_file} to {w_dest_file}: {e}")
                    else:
                        print(
                            f"Source directory does not exist: {window_color_dir}")

                channellist_file = self.previewFiles + \
                    'channellist-' + cfg.ChannSelector.value + '.xml'
                try:
                    with open(channellist_file, 'r') as f:
                        channellist_content = f.read()
                    channellist_content = self.modify_channel_colors(
                        channellist_content)
                    skin_lines.extend(channellist_content.splitlines(True))
                except FileNotFoundError:
                    print("Channel selection file not found:", channellist_file)
            else:
                skin_lines.extend(load_xml_to_skin_lines(
                    self.previewFiles + 'channellist-' + cfg.ChannSelector.value + '.xml'))

            for filename in xml_files[11:]:
                skin_lines.extend(load_xml_to_skin_lines(
                    self.previewFiles + filename + '.xml'))

            base_file = 'base1.xml' if cfg.skinSelector.value == 'base1' else 'base.xml'
            skin_lines.extend(load_xml_to_skin_lines(
                self.previewFiles + base_file))

            print("Writing to file: {}".format(self.skinFile))
            with open(self.skinFile, 'w') as xFile:
                xFile.writelines(skin_lines)

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
            self.session.open(MessageBox, _('Error by processing the skin file: {}').format(
                str(e)), MessageBox.TYPE_ERROR)

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
        if not fullurl:
            self.session.open(MessageBox, _(
                "Update URL not initialised – open the plugin once from the Plugins menu first."), MessageBox.TYPE_ERROR)
            return

        try:
            tmp_file = f'/tmp/{destr}'
            req = Request(
                fullurl,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
            )
            data = urlopen(req).read().decode('utf‑8')
            with open(tmp_file, 'w') as f:
                f.write(data)

            if not fileExists(tmp_file):
                raise IOError("Failed to write tmp version file")

            with open(tmp_file, 'r') as fh:
                line = fh.readline().strip()

            try:
                version_server, self.updateurl = (
                    x.strip() for x in line.split('#', 1))
            except ValueError:
                raise ValueError(f"Malformed version string: {line}")

            if version_server == version:
                self.session.open(MessageBox, _("You already have the latest version ({}).").format(
                    version), MessageBox.TYPE_INFO)
            elif version_server > version:
                self.session.openWithCallback(
                    self.update,
                    MessageBox,
                    _("Server version: {}\nInstalled version: {}\n\n A newer build is available – update now?").format(
                        version_server, version),
                    MessageBox.TYPE_YESNO
                )
            else:
                self.session.open(MessageBox, _("Local build ({}) is newer than server build ({}).").format(
                    version, version_server), MessageBox.TYPE_INFO)
        except Exception as e:
            self.session.open(MessageBox, _("Update check failed: {}").format(
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
            self.downloadFinished).addErrback(self.downloadFailed)

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
                MessageBox.TYPE_YESNO
            )
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
        self['progresstext'].text = '{} of {} kB ({:.2f} %)'.format(
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
        json_file_backdrop = glob_glob(join(patch_backdrop, "*.json"))
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
        session.open(MessageBox, "Skin not supported.\nPlugin closed.",
                     MessageBox.TYPE_ERROR, timeout=5)
        return
    session.open(AglareSetup)


def Plugins(**kwargs):
    return PluginDescriptor(
        name='Setup Aglare',
        description=_('Customization tool for %s Skin') % cur_skin,
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon='logo.png',
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
