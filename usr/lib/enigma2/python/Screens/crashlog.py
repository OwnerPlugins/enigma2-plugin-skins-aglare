#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
****************************************
*        modded by Lululla             *
*             26/04/2024               *
****************************************
# --------------------#
# Info Linuxsat-support.com  corvoboys.org
'''
import sys

from os import remove
from os.path import exists, isfile, getsize, getmtime, basename
from datetime import datetime
from enigma import getDesktop, eTimer
from Components.ActionMap import ActionMap
from Components.ScrollLabel import ScrollLabel
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.config import config
from Screens.Screen import Screen
from Tools.Directories import SCOPE_SKIN, resolveFilename
from Tools.LoadPixmap import LoadPixmap

import gettext
_ = gettext.gettext

version = '1.4'


def isMountReadonly(mnt):
    mount_point = ''
    try:
        with open('/proc/mounts', 'r') as f:
            for line in f:
                line_parts = line.split()
                if len(line_parts) < 4:
                    continue
                device, mount_point, filesystem, flags = line_parts[:4]
                if mount_point == mnt:
                    return 'ro' in flags
    except IOError as e:
        print("I/O Error: %s" % str(e), file=sys.stderr)
    except Exception as err:
        print("Error: %s" % str(err), file=sys.stderr)
    return "mount: '%s' doesn't exist" % mnt


def paths():
    return [
        "/media/hdd",
        "/media/usb",
        "/media/mmc",
        "/home/root",
        "/home/root/logs/",
        "/media/hdd/logs",
        "/media/usb/logs",
        "/ba/",
        "/ba/logs",
        "/tmp/"]


def get_log_path():
    """Get the primary log directory path"""
    try:
        path_folder_log = config.crash.debug_path.value
        if path_folder_log and exists(
                path_folder_log) and not isMountReadonly(path_folder_log):
            return path_folder_log.rstrip('/') + '/'
    except (KeyError, AttributeError):
        pass

    possible_paths = paths()
    for path in possible_paths:
        if exists(path) and not isMountReadonly(path):
            return path.rstrip('/') + '/'

    return "/tmp/"


def find_log_files():
    """Find all crash log files - FIXED VERSION"""
    import glob

    log_files = []

    # Search patterns that include /tmp
    search_patterns = [
        "/tmp/*crash*.log",
        "/tmp/*.log",  # All .log files in /tmp
        "/home/root/*crash*.log",
        "/home/root/logs/*crash*.log",
        "/media/hdd/*crash*.log",
        "/media/hdd/logs/*crash*.log",
        "/media/usb/*crash*.log",
        "/media/usb/logs/*crash*.log",
        "/media/mmc/*crash*.log",
        "/ba/*crash*.log",
        "/ba/logs/*crash*.log"
    ]

    # Get primary path
    primary_path = get_log_path()
    if primary_path and primary_path not in ["/tmp/", "/home/root/"]:
        search_patterns.extend([
            "%s*crash*.log" % primary_path,
            "%slogs/*crash*.log" % primary_path,
            "%stwisted.log" % primary_path
        ])

    # Search all patterns
    for pattern in search_patterns:
        try:
            found_files = glob.glob(pattern)
            for file_path in found_files:
                # Check if it's a file and not a directory
                if isfile(file_path) and file_path not in log_files:
                    # Check if it's really a crash log
                    filename = basename(file_path).lower()
                    if ('crash' in filename or
                            'error' in filename or
                            'log' in filename):  # Accept all .log files
                        log_files.append(file_path)
        except BaseException:
            pass

    # Also check specific known files
    specific_files = [
        "/tmp/enigma2_crash.log",
        "/home/root/enigma2_crash.log",
        "/tmp/Enigma2-Crash.log",
        "/tmp/crash.log",
        "/tmp/crash_log.log"
    ]

    for file_path in specific_files:
        if isfile(file_path) and file_path not in log_files:
            log_files.append(file_path)

    return log_files


def delete_log_files(files):
    """Delete list of log files"""
    for file in files:
        try:
            remove(file)
            print('File deleted:', file)
        except OSError as e:
            print("Error deleting file %s:" % file, str(e))


class CrashLogScreen(Screen):
    def __init__(self, session):
        self.session = session
        Screen.__init__(self, session)

        sz_w = getDesktop(0).size().width()
        if sz_w == 2560:
            self.skin = """
                <screen name="CrashLogScreen" position="center,center" size="1280,1000" title="View or Remove Crashlog files">
                    <widget source="Redkey" render="Label" position="160,900" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Greenkey" render="Label" position="415,900" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Yellowkey" render="Label" position="670,900" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Bluekey" render="Label" position="925,900" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <eLabel backgroundColor="#00ff0000" position="160,948" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#0000ff00" position="415,948" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#00ffff00" position="670,948" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#000000ff" position="925,948" size="250,6" zPosition="12" />
                    <eLabel name="" position="1194,901" size="52,52" backgroundColor="#003e4b53" halign="center" valign="center" transparent="0" cornerRadius="26" font="Regular; 17" zPosition="1" text="INFO" />
                    <widget source="menu" render="Listbox" position="80,67" size="1137,781" scrollbarMode="showOnDemand">
                    <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos = (80, 5), size = (580, 46), font=0, flags = RT_HALIGN_LEFT | RT_VALIGN_CENTER, text = 0),
                        MultiContentEntryText(pos = (80, 55), size = (580, 38), font=1, flags = RT_HALIGN_LEFT | RT_VALIGN_CENTER, text = 1),
                        MultiContentEntryPixmapAlphaTest(pos = (5, 35), size = (51, 40), png = 2),
                            ],
                    "fonts": [gFont("Regular", 42),gFont("Regular", 34)],
                    "itemHeight": 100
                    }
                    </convert>
                    </widget>
                </screen>"""
        elif sz_w == 1920:
            self.skin = """
                <screen name="CrashLogScreen" position="center,center" size="1000,880" title="View or Remove Crashlog files">
                    <widget source="Redkey" render="Label" position="0,814" size="250,45" zPosition="11" font="Regular; 26" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Greenkey" render="Label" position="252,813" size="250,45" zPosition="11" font="Regular; 26" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Yellowkey" render="Label" position="499,814" size="250,45" zPosition="11" font="Regular; 26" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Bluekey" render="Label" position="749,814" size="250,45" zPosition="11" font="Regular; 26" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <eLabel backgroundColor="#00ff0000" position="0,858" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#0000ff00" position="250,858" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#00ffff00" position="500,858" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#000000ff" position="750,858" size="250,6" zPosition="12" />
                    <eLabel name="" position="933,753" size="52,52" backgroundColor="#003e4b53" halign="center" valign="center" transparent="0" cornerRadius="26" font="Regular; 17" zPosition="1" text="INFO" />
                    <widget source="menu" render="Listbox" position="20,10" size="961,781" scrollbarMode="showOnDemand">
                    <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos = (70, 2), size = (580, 34), font=0, flags = RT_HALIGN_LEFT, text = 0),
                        MultiContentEntryText(pos = (80, 29), size = (580, 30), font=1, flags = RT_HALIGN_LEFT, text = 1),
                        MultiContentEntryPixmapAlphaTest(pos = (5, 15), size = (51, 40), png = 2),
                            ],
                    "fonts": [gFont("Regular", 30),gFont("Regular", 26)],
                    "itemHeight": 70
                    }
                    </convert>
                    </widget>
                </screen>"""
        else:
            self.skin = """
                <screen name="CrashLogScreen" position="center,center" size="640,586" title="View or Remove Crashlog files">
                    <widget source="Redkey" render="Label" position="6,536" size="160,35" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Greenkey" render="Label" position="166,536" size="160,35" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Yellowkey" render="Label" position="325,536" size="160,35" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Bluekey" render="Label" position="485,536" size="160,35" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <eLabel backgroundColor="#00ff0000" position="5,570" size="160,6" zPosition="12" />
                    <eLabel backgroundColor="#0000ff00" position="165,570" size="160,6" zPosition="12" />
                    <eLabel backgroundColor="#00ffff00" position="325,570" size="160,6" zPosition="12" />
                    <eLabel backgroundColor="#000000ff" position="480,570" size="160,6" zPosition="12" />
                    <eLabel name="" position="586,495" size="42,35" backgroundColor="#003e4b53" halign="center" valign="center" transparent="0" cornerRadius="26" font="Regular; 14" zPosition="1" text="INFO" />
                    <widget source="menu" render="Listbox" position="13,6" size="613,517" scrollbarMode="showOnDemand">
                    <convert type="TemplatedMultiContent">
                    {"template": [
                        MultiContentEntryText(pos = (46, 1), size = (386, 22), font=0, flags = RT_HALIGN_LEFT, text = 0),
                        MultiContentEntryText(pos = (53, 19), size = (386, 20), font=1, flags = RT_HALIGN_LEFT, text = 1),
                        MultiContentEntryPixmapAlphaTest(pos = (3, 10), size = (34, 26), png = 2),
                            ],
                    "fonts": [gFont("Regular", 18),gFont("Regular", 16)],
                    "itemHeight": 50
                    }
                    </convert>
                    </widget>
                </screen>"""

        self["shortcuts"] = ActionMap(["ShortcutActions",
                                       "OkCancelActions",
                                       "WizardActions",
                                       "EPGSelectActions"],
                                      {"ok": self.Ok,
                                       "cancel": self.exit,
                                       "back": self.exit,
                                       "red": self.exit,
                                       "green": self.Ok,
                                       "yellow": self.YellowKey,
                                       "blue": self.BlueKey,
                                       "info": self.infoKey})
        self["Redkey"] = StaticText(_("Close"))
        self["Greenkey"] = StaticText(_("View"))
        self["Yellowkey"] = StaticText(_("Remove"))
        self["Bluekey"] = StaticText(_("Remove All"))
        # self["Title"] = StaticText(_("View or Remove Crashlog files"))
        self.list = []
        self["menu"] = List(self.list)
        self.CfgMenu()
        self.showing_info = False
        self.in_confirm_mode = False

    def CfgMenu(self):
        """Display list of crash log files"""
        self.list = []

        # Use find_log_files() function
        log_files = find_log_files()

        # Load icon
        try:
            cur_skin = config.skin.primary_skin.value.replace('/skin.xml', '')
            minipng = LoadPixmap(
                cached=True,
                path=resolveFilename(
                    SCOPE_SKIN,
                    str(cur_skin) +
                    "/mainmenu/crashlog.png"))
        except BaseException:
            minipng = None

        # Process each found file
        for file_path in log_files:
            try:
                if exists(file_path):
                    # Get file info
                    file_size = getsize(file_path)
                    if file_size < 1024:
                        size_str = "%d B" % file_size
                    elif file_size < 1024 * 1024:
                        size_str = "%.1f KB" % (file_size / 1024.0)
                    else:
                        size_str = "%.1f MB" % (file_size / (1024.0 * 1024.0))

                    # Get modification time
                    mtime = getmtime(file_path)
                    file_date = datetime.fromtimestamp(
                        mtime).strftime("%Y-%m-%d %H:%M")

                    file_name = basename(file_path)

                    display_name = (
                        file_name,
                        "Size: %s - Date: %s" % (size_str, file_date),
                        minipng,
                        file_path
                    )
                    if display_name not in self.list:
                        self.list.append(display_name)
            except Exception as e:
                print("Error processing file %s: %s" % (file_path, str(e)))

        # If no files found
        if not self.list:
            self.list.append((
                _("No crash logs found"),
                _("Search completed"),
                minipng,
                ""
            ))

        self["menu"].setList(self.list)

    def Ok(self):
        if self.in_confirm_mode:
            return
        item = self["menu"].getCurrent()
        print("DEBUG: item =", item, "type =", type(item))
        if item:
            print("DEBUG: len(item) =", len(item) if hasattr(item, '__len__') else 'N/A')
        try:
            if item and len(item) >= 4 and item[3]:
                Crashfile = str(item[3])
                print("DEBUG: Crashfile =", Crashfile)
                self.session.openWithCallback(
                    self.CfgMenu, CrashLogView, Crashfile)
            else:
                print("DEBUG: item non valido o senza 4 elementi")
                self.showTempMessage(_("Invalid selection"))
        except Exception as e:
            print("Error opening log:", e)
            self.showTempMessage(_("Cannot open this file"))

    def YellowKey(self):
        """Remove selected file"""
        if self.in_confirm_mode:
            return

        item = self["menu"].getCurrent()

        if not item or len(item) < 4 or not item[3]:
            self.showTempMessage(_("No file selected"), 1500)
            return

        file_path = str(item[3])

        if not exists(file_path):
            self.showTempMessage(_("File already removed"), 1500)
            self.CfgMenu()
            return

        try:
            # Remove the file
            remove(file_path)

            # Show confirmation
            self.showTempMessage(_("Removed: %s") % basename(file_path), 1500)

            # Refresh list
            self.CfgMenu()

        except Exception as e:
            self.showTempMessage(_("Error: %s") % str(e), 2000)

    def BlueKey(self):
        """Delete all crash log files - FORCE REFRESH"""
        if self.in_confirm_mode:
            return

        try:
            log_files = find_log_files()
            if not log_files:
                self.showTempMessage(_("No crash logs found"), 2000)
                return

            # Store original title
            original_title = self.getTitle()

            # Delete all files
            deleted = 0
            for file_path in log_files:
                try:
                    if exists(file_path):
                        remove(file_path)
                        deleted += 1
                        print("Deleted:", file_path)
                except Exception as e:
                    print("Failed to delete %s: %s" % (file_path, str(e)))

            # Show immediate feedback
            if deleted > 0:
                self.setTitle(_("Deleted %d files") % deleted)
            else:
                self.setTitle(_("No files deleted"))

            # FORCE refresh list NOW
            self.CfgMenu()

            # Restore title after 1.5 seconds
            timer = eTimer()
            timer.callback.append(lambda: self.setTitle(original_title))
            timer.start(1500, True)

        except Exception as e:
            print("Error in BlueKey:", str(e))
            original_title = self.getTitle()
            self.setTitle(_("Error: %s") % str(e))
            self.CfgMenu()
            timer = eTimer()
            timer.callback.append(lambda: self.setTitle(original_title))
            timer.start(2000, True)

    def enterConfirmationMode(self, file_count):
        """Enter confirmation mode for deleting all files"""
        self.in_confirm_mode = True
        self.file_count = file_count
        self.original_title = self.getTitle()

        self.setTitle(_("Delete ALL? RED=YES, GREEN=NO"))

        try:
            red_img = LoadPixmap(
                "/usr/share/enigma2/skin_default/buttons/red.png")
        except BaseException:
            red_img = None

        try:
            green_img = LoadPixmap(
                "/usr/share/enigma2/skin_default/buttons/green.png")
        except BaseException:
            green_img = None

        self.list = [
            (_("YES - Delete all %d files") %
             file_count,
             _("Press RED button"),
                red_img),
            (_("NO - Cancel operation"),
             _("Press GREEN button"),
                green_img)]
        self["menu"].setList(self.list)

        self["shortcuts"].actions.update({
            "red": self.confirmDeleteYes,
            "green": self.confirmDeleteNo,
            "cancel": self.confirmDeleteNo,
            "ok": self.confirmDeleteNo
        })

    def confirmDeleteYes(self):
        """Confirm yes - delete all files"""
        if not self.in_confirm_mode:
            return

        log_files = find_log_files()
        deleted = 0

        for file_path in log_files:
            try:
                remove(file_path)
                deleted += 1
            except Exception as e:
                print("Failed to delete %s: %s" % (file_path, str(e)))

        if deleted > 0:
            message = _("Deleted %d files") % deleted
        else:
            message = _("No files deleted")

        self.exitConfirmationMode(message)

    def confirmDeleteNo(self):
        """Confirm no - cancel operation"""
        if not self.in_confirm_mode:
            return

        self.exitConfirmationMode(_("Operation cancelled"))

    def exitConfirmationMode(self, message):
        """Exit confirmation mode and show result"""
        self.in_confirm_mode = False
        self.setTitle(message)
        timer = eTimer()
        timer.callback.append(self.restoreNormalMode)
        timer.start(2000, True)

    def restoreNormalMode(self):
        """Restore normal mode after confirmation"""
        if hasattr(self, 'original_title'):
            self.setTitle(self.original_title)

        self["shortcuts"].actions.update({
            "ok": self.Ok,
            "cancel": self.exit,
            "back": self.exit,
            "red": self.exit,
            "green": self.Ok,
            "yellow": self.YellowKey,
            "blue": self.BlueKey,
            "info": self.infoKey
        })

        # Reload file list
        self.CfgMenu()

    def showTempMessage(self, message, duration=2000):
        """Show temporary message"""
        if self.in_confirm_mode:
            return

        original_title = self.getTitle()
        self.setTitle(message)

        timer = eTimer()
        timer.callback.append(lambda: self.setTitle(original_title))
        timer.start(duration, True)

    def infoKey(self):
        """Mostra informazioni sul plugin"""
        if self.in_confirm_mode:
            return

        info_items = []
        info_items.append(("=" * 50, "", None, ""))
        info_items.append(("CRASHLOG VIEWER - INFO", "", None, ""))
        info_items.append(("=" * 50, "", None, ""))
        info_items.append(("Version: " + version, "", None, ""))
        info_items.append(("Developer: 2boom", "", None, ""))
        info_items.append(("Modifier: Evg77734", "", None, ""))
        info_items.append(("Update from Lululla", "", None, ""))
        info_items.append(("=" * 50, "", None, ""))
        info_items.append(("Press OK or RED to return", "", None, ""))

        self["menu"].setList(info_items)

        self["Redkey"].setText(_("Back"))
        self["Greenkey"].setText("")
        self["Yellowkey"].setText("")
        self["Bluekey"].setText("")

        self.showing_info = True

        self["shortcuts"].actions.update({
            "ok": self.returnFromInfo,
            "cancel": self.returnFromInfo,
            "red": self.returnFromInfo,
            "green": lambda: None,      # Disabilita
            "yellow": lambda: None,     # Disabilita
            "blue": lambda: None,       # Disabilita
            "info": lambda: None        # Disabilita
        })

    def returnFromInfo(self):
        if hasattr(self, 'showing_info') and self.showing_info:
            self.showing_info = False
            self.CfgMenu()

            self["Redkey"].setText(_("Close"))
            self["Greenkey"].setText(_("View"))
            self["Yellowkey"].setText(_("Remove"))
            self["Bluekey"].setText(_("Remove All"))

            self["shortcuts"].actions.update({
                "ok": self.Ok,
                "cancel": self.exit,
                "back": self.exit,
                "red": self.exit,
                "green": self.Ok,
                "yellow": self.YellowKey,
                "blue": self.BlueKey,
                "info": self.infoKey,
            })

    def exit(self):
        if self.in_confirm_mode:
            self.exitConfirmationMode(_("Cancelled"))
        else:
            self.close()


class CrashLogView(Screen):
    def __init__(self, session, Crashfile):
        self.session = session
        self.crashfile = Crashfile
        sz_w = getDesktop(0).size().width()
        if sz_w == 1920:
            self.skin = """
                <screen name="CrashLogView" position="center,center" size="1880,980" title="View Crashlog file">
                    <widget source="Redkey" render="Label" position="16,919" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Greenkey" render="Label" position="266,919" size="250,45" zPosition="11" font="Regular; 30" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <eLabel backgroundColor="#00ff0000" position="20,963" size="250,6" zPosition="12" />
                    <eLabel backgroundColor="#0000ff00" position="270,963" size="250,6" zPosition="12" />
                    <widget name="text" position="10,70" size="1860,830" font="Console; 24" text="text" />
                </screen>"""
        else:
            self.skin = """
                <screen name="CrashLogView" position="center,center" size="1253,653" title="View Crashlog file">
                    <widget source="Redkey" render="Label" position="19,609" size="172,33" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <widget source="Greenkey" render="Label" position="191,609" size="172,33" zPosition="11" font="Regular; 22" valign="center" halign="center" backgroundColor="#050c101b" transparent="1" foregroundColor="white" />
                    <eLabel backgroundColor="#00ff0000" position="20,643" size="172,6" zPosition="12" />
                    <eLabel backgroundColor="#0000ff00" position="192,643" size="172,6" zPosition="12" />
                    <widget name="text" position="6,50" size="1240,550" font="Console; 16" text="text" />
                </screen>"""

        Screen.__init__(self, session)
        self.setTitle("View Crashlog file: " + basename(Crashfile))
        self.current_view = "full"
        self.full_text = ""
        self.error_text = ""

        self["text"] = ScrollLabel("")
        self["text2"] = ScrollLabel("")

        self["actions"] = ActionMap(
            ["DirectionActions", "ColorActions", "OkCancelActions"],
            {
                "cancel": self.exit,
                "ok": self.exit,
                "red": self.exit,
                "green": self.switchView,
                "up": self.pageUp,
                "down": self.pageDown,
                "left": self.pageUp,
                "right": self.pageDown
            }
        )
        self["Redkey"] = StaticText(_("Close"))
        self["Greenkey"] = StaticText(_("Switch View"))
        self.onLayoutFinish.append(self.listcrah)

    def pageUp(self):
        self["text"].pageUp()

    def pageDown(self):
        self["text"].pageDown()

    def switchView(self):
        if self.current_view == "full":
            self.current_view = "error"
            self["text"].setText(self.error_text)
            self["Greenkey"].setText(_("Full Log"))
        else:
            self.current_view = "full"
            self["text"].setText(self.full_text)
            self["Greenkey"].setText(_("Error Only"))
        self["text"].lastPage()

    def exit(self):
        self.close()

    def listcrah(self):
        try:
            with open(self.crashfile, "r") as crashfile:
                content = crashfile.read()
                self.full_text = content

                # Extract error
                lines = content.split('\n')
                error_lines = []
                for i, line in enumerate(lines):
                    if "Traceback (most recent call last):" in line or "Backtrace:" in line:
                        for j in range(i, min(i + 20, len(lines))):
                            error_lines.append(lines[j])
                        break

                if not error_lines:
                    # Try to find any error message
                    for line in lines:
                        if "Error:" in line or "Exception:" in line or "FATAL" in line:
                            error_lines.append(line)

                if not error_lines:
                    error_lines = ["No specific error trace found in log"]

                self.error_text = '\n'.join(error_lines)

        except Exception as e:
            error_msg = "Error opening file: %s" % str(e)
            self.full_text = error_msg
            self.error_text = error_msg

        # Set initial view to full log
        self["text"].setText(self.full_text)
        self["Greenkey"].setText(_("Error Only"))
