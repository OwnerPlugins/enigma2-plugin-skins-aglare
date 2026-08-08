import json
import os
from datetime import datetime
from enigma import eEPGCache
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.MessageBox import MessageBox
from Screens.LocationBox import LocationBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.config import config, ConfigSubsection, ConfigText, ConfigSelection, getConfigListEntry, configfile
from Components.ConfigList import ConfigListScreen
from . import _

# Handle Python 2/3 urllib differences
try:
    from urllib.request import urlopen, Request
    from urllib.parse import quote
except ImportError:
    from urllib2 import urlopen, Request
    from urllib import quote

# Initialize Global Configuration for the backup folder, search method,
# and title preference
if not hasattr(config.misc, "AglareSubstitute"):
    config.misc.AglareSubstitute = ConfigSubsection()
    config.misc.AglareSubstitute.backup_dir = ConfigText(
        default="/etc/enigma2/aglare", fixed_size=False)
    config.misc.AglareSubstitute.search_method = ConfigSelection(
        default="web", choices=[
            ("web", _("Default Search (No API)")), ("api", _("API Key Search"))])
    config.misc.AglareSubstitute.name_preference = ConfigSelection(
        default="original_name",
        choices=[
            ("name",
             _("Standard Name (Translated)")),
            ("original_name",
             _("Original Name (Native)"))])


def write_sub_log(msg):
    """Writes log messages specifically for the substitution tool."""
    log_dir = "/var/volatile/tmp/agplog"
    log_file = os.path.join(log_dir, "agp_substitute.log")
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(log_file, "a") as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write("[{}] {}\n".format(timestamp, msg))
    except Exception:
        pass


class AglareSubSettingsScreen(ConfigListScreen, Screen):
    skin = """
        <screen name="AglareSubSettingsScreen" position="center,center" size="600,300" title="Substitution Settings">
            <widget name="config" position="20,20" size="560,200" scrollbarMode="showOnDemand" font="Regular;22" />
            <ePixmap pixmap="skin_default/buttons/red.png" position="20,250" size="140,40" alphatest="on" />
            <ePixmap pixmap="skin_default/buttons/green.png" position="180,250" size="140,40" alphatest="on" />
            <widget name="key_red" position="20,250" size="140,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
            <widget name="key_green" position="180,250" size="140,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self["key_red"] = Label(_("Cancel"))
        self["key_green"] = Label(_("Save"))

        self.folder_config = config.misc.AglareSubstitute.backup_dir
        self.search_config = config.misc.AglareSubstitute.search_method
        self.name_pref_config = config.misc.AglareSubstitute.name_preference

        self.list = [
            getConfigListEntry(_("Search Method"), self.search_config),
            getConfigListEntry(_("Title Preference"), self.name_pref_config),
            getConfigListEntry(
                _("Backup Folder (Press OK to change)"), self.folder_config)
        ]

        ConfigListScreen.__init__(self, self.list, session=self.session)

        self["setupActions"] = ActionMap(["SetupActions", "ColorActions", "OkCancelActions"], {
            "red": self.cancel,
            "green": self.save,
            "cancel": self.cancel,
            "ok": self.keyOK,
        }, -2)

    def keyOK(self):
        current = self["config"].getCurrent()
        if current and current[1] == self.folder_config:
            self.session.openWithCallback(
                self.locationCallback,
                LocationBox,
                windowTitle=_("Select Backup Folder"),
                text=_("Select Folder"),
                currDir=self.folder_config.value)

    def locationCallback(self, path):
        if path is not None:
            self.folder_config.value = path
            self["config"].invalidateCurrent()

    def save(self):
        self.search_config.save()
        self.name_pref_config.save()
        self.folder_config.save()
        configfile.save()
        self.close(True)

    def cancel(self):
        self.search_config.cancel()
        self.name_pref_config.cancel()
        self.folder_config.cancel()
        self.close(False)


class AglareTitleSubstituteScreen(Screen):
    skin = """
        <screen name="AglareTitleSubstituteScreen" position="center,center" size="800,500" title="EPG Title Substitution">
            <ePixmap pixmap="skin_default/buttons/red.png" position="10,5" size="190,40" alphatest="on" />
            <ePixmap pixmap="skin_default/buttons/green.png" position="205,5" size="190,40" alphatest="on" />
            <ePixmap pixmap="skin_default/buttons/yellow.png" position="400,5" size="190,40" alphatest="on" />

            <widget name="key_red" position="10,5" size="190,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
            <widget name="key_green" position="205,5" size="190,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
            <widget name="key_yellow" position="400,5" size="190,40" zPosition="1" font="Regular;20" halign="center" valign="center" transparent="1" />
            <widget name="key_menu" position="600,5" size="190,40" zPosition="1" font="Regular;20" halign="center" valign="center" foregroundColor="#00aaff" transparent="1" />

            <widget name="original_label" position="20,70" size="200,30" font="Regular;22" halign="left" valign="center" />
            <widget name="original_name" position="220,70" size="560,30" font="Regular;22" halign="left" valign="center" foregroundColor="#cccccc" />

            <widget name="editable_label" position="20,110" size="200,30" font="Regular;22" halign="left" valign="center" />
            <widget name="editable_name" position="220,110" size="560,30" font="Regular;22" halign="left" valign="center" foregroundColor="#ffff00" />

            <widget name="results_list" position="20,160" size="760,320" font="Regular;22" scrollbarMode="showOnDemand" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self["key_red"] = Label(_("Edit Event Name"))
        self["key_green"] = Label(_("Search TMDb"))
        self["key_yellow"] = Label(_("Save Selected"))
        self["key_menu"] = Label(_("MENU: Settings"))

        # Updated label to indicate Left/Right navigation
        self["original_label"] = Label(_("Event Name (< / >):"))
        self["editable_label"] = Label(_("Search Query:"))

        self["original_name"] = Label("")
        self["editable_name"] = Label("")

        self.search_results = []
        self["results_list"] = MenuList([])

        # Load the event timeline and set the display
        self.loadEvents()
        self.updateEventDisplay()

        # Added 'left' and 'right' mapping to cycle through events
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "SetupActions"], {
            "cancel": self.handleExit,
            "red": self.openKeyboard,
            "green": self.searchTMDb,
            "yellow": self.saveSubstitution,
            "ok": self.saveSubstitution,
            "menu": self.openSettings,
            "up": self.goUp,
            "down": self.goDown,
            "left": self.prevEvent,
            "right": self.nextEvent
        }, -1)

        self.tmdb_api_key = "3c3efcf47c3577558812bb9d64019d65"
        self.pending_save = None

    def loadEvents(self):
        """Fetches up to 24 hours of events for the current service to allow navigation."""
        self.events_list = []
        self.current_event_index = 0

        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if ref:
            epgcache = eEPGCache.getInstance()
            if epgcache is not None:
                # 'T' = Title only. 1 = Look forward in time, -1 = Start from now, 1440 = Next 24 hrs
                events = epgcache.lookupEvent(
                    ['T', (ref.toString(), 1, -1, 1440)])
                if events:
                    seen = set()
                    for evt in events:
                        if evt and evt[0]:
                            name = evt[0].strip()
                            if name and name not in seen:
                                self.events_list.append(name)
                                seen.add(name)

        # Fallback if cache fails or timeline is completely empty
        if not self.events_list:
            service = self.session.nav.getCurrentService()
            info = service and service.info()
            event = info and info.getEvent(0)
            if event:
                name = event.getEventName()
                self.events_list = [name.strip() if name else "No Event"]
            else:
                self.events_list = ["No Event"]

    def updateEventDisplay(self):
        """Updates the labels when navigating between events."""
        self.original_title = self.events_list[self.current_event_index]
        self.editable_title = self.original_title

        self["original_name"].setText(self.original_title)
        self["editable_name"].setText(self.editable_title)

        # Clear any old search results when switching events
        self.search_results = []
        self["results_list"].setList([])

    def nextEvent(self):
        if self.current_event_index < len(self.events_list) - 1:
            self.current_event_index += 1
            self.updateEventDisplay()

    def prevEvent(self):
        if self.current_event_index > 0:
            self.current_event_index -= 1
            self.updateEventDisplay()

    def openSettings(self):
        self.session.open(AglareSubSettingsScreen)

    def openKeyboard(self):
        self.session.openWithCallback(
            self.keyboardCallback,
            VirtualKeyBoard,
            title=_("Edit Search Query"),
            text=self.editable_title)

    def keyboardCallback(self, res):
        if res is not None:
            self.editable_title = res.strip()
            self["editable_name"].setText(self.editable_title)

    def goUp(self):
        self["results_list"].up()

    def goDown(self):
        self["results_list"].down()

    def searchTMDb(self):
        if not self.editable_title or self.editable_title == "No Event":
            return

        search_mode = config.misc.AglareSubstitute.search_method.value
        name_pref = config.misc.AglareSubstitute.name_preference.value

        if search_mode == "api":
            url = "https://api.themoviedb.org/3/search/multi?api_key={}&query={}".format(
                self.tmdb_api_key, quote(self.editable_title))
            write_sub_log(
                "Initiating TMDb API Key search for query: '{}'".format(
                    self.editable_title))
            headers = {'User-Agent': 'Mozilla/5.0'}
        else:
            url = "https://www.themoviedb.org/search/trending?query={}".format(
                quote(self.editable_title))
            write_sub_log(
                "Initiating TMDb Web Search (No API) for query: '{}'".format(
                    self.editable_title))
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest'}

        try:
            req = Request(url, headers=headers)
            response = urlopen(req, timeout=5).read()
            data = json.loads(response.decode('utf-8'))

            self.search_results = []
            display_list = []

            results = data.get("results", [])
            write_sub_log(
                "Search returned {} total items.".format(len(results)))

            for item in results:
                if not isinstance(item, dict):
                    continue

                media_type = item.get("media_type", "")
                if media_type in ("movie", "tv"):
                    if name_pref == "original_name":
                        title = item.get("original_title") or item.get(
                            "original_name") or item.get("title") or item.get("name")
                    else:
                        title = item.get("title") or item.get("name")

                    year = item.get("release_date", "")[
                        :4] or item.get("first_air_date", "")[:4]

                    if title:
                        display_text = "{} ({})".format(
                            title, year) if year else title
                        display_list.append(display_text)
                        self.search_results.append((title, year))

                        write_sub_log(
                            "Result Discovered | Title: '{}' | Year: '{}' | Type: '{}'".format(
                                title, year, media_type))

            if display_list:
                self["results_list"].setList(display_list)
            else:
                self["results_list"].setList(["No results found"])
                self.search_results = []
                write_sub_log(
                    "No matching movie or TV results found for query: '{}'".format(
                        self.editable_title))

        except Exception as e:
            write_sub_log("Search Error: {}".format(str(e)))
            self["results_list"].setList(["Search Error: " + str(e)])

    def saveSubstitution(self):
        if not self.search_results:
            return

        selected_index = self["results_list"].getSelectedIndex()
        if selected_index < 0 or selected_index >= len(self.search_results):
            return

        tmdb_title, tmdb_year = self.search_results[selected_index]

        original_clean = self.original_title.lower().strip()
        tmdb_clean = tmdb_title.lower().strip()
        editable_clean = self.editable_title.lower().strip()

        replacement_value = tmdb_clean
        method = "replace" if original_clean == editable_clean else "set"

        self.pending_save = (original_clean, replacement_value, method)

        backup_dir = config.misc.AglareSubstitute.backup_dir.value
        json_path = os.path.join(backup_dir, "substitutions.json")
        duplicate_found = False

        if os.path.exists(json_path):
            try:
                import codecs
                with codecs.open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        if item[0] == original_clean:
                            duplicate_found = True
                            break
            except Exception as e:
                write_sub_log("Duplicate check error: " + str(e))

        if duplicate_found:
            self.session.openWithCallback(
                self.overrideCallback,
                MessageBox,
                _("This event name already exists in substitutions.json.\nDo you want to override it?"),
                MessageBox.TYPE_YESNO)
        else:
            self.writeToJson(override=False)

    def overrideCallback(self, answer):
        if answer:
            self.writeToJson(override=True)
        else:
            write_sub_log("Save cancelled by user (duplicate entry rejected).")

    def writeToJson(self, override):
        orig, replacement, method = self.pending_save
        backup_dir = config.misc.AglareSubstitute.backup_dir.value

        if not os.path.exists(backup_dir):
            try:
                os.makedirs(backup_dir)
            except Exception as e:
                self.session.open(
                    MessageBox,
                    _("Directory creation error: ") +
                    str(e),
                    MessageBox.TYPE_ERROR)
                return

        json_path = os.path.join(backup_dir, "substitutions.json")
        data = []

        import codecs
        if os.path.exists(json_path):
            try:
                with codecs.open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        if override:
            for item in data:
                if item[0] == orig:
                    item[1] = replacement
                    item[2] = method
                    break
            write_sub_log(
                "Overrode entry in JSON -> Original: '{}' | Target: '{}' | Method: '{}'".format(
                    orig, replacement, method))
        else:
            data.append([orig, replacement, method])
            write_sub_log(
                "Saved entry to JSON -> Original: '{}' | Target: '{}' | Method: '{}'".format(
                    orig, replacement, method))

        try:
            with codecs.open(json_path, "w", encoding="utf-8") as f:
                import sys
                if sys.version_info[0] >= 3:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                else:
                    json.dump(data, f, indent=4)

            self.session.open(
                MessageBox,
                _("Substitution saved to JSON successfully!\nYou can continue adding more."),
                MessageBox.TYPE_INFO)
        except Exception as e:
            self.session.open(MessageBox, _(
                "JSON Write Error: ") + str(e), MessageBox.TYPE_ERROR)

    def handleExit(self):
        self.close()
