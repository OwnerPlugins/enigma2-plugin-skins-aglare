#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Plugin RadioM is developed
from Lululla to Mmark
"""
from __future__ import print_function
from datetime import datetime as dt
from os import remove, replace, walk, makedirs
from os.path import dirname, exists, getsize
from sys import version_info
from time import time
from json import loads as json_loads
from re import sub
from urllib.parse import quote
from urllib.request import Request, urlopen
from PIL import Image
import requests
from enigma import (
    RT_HALIGN_LEFT,
    RT_VALIGN_CENTER,
    eListboxPythonMultiContent,
    ePicLoad,
    eServiceReference,
    eTimer,
    gFont,
    getDesktop,
    loadPNG,
)
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryPixmapAlphaTest, MultiContentEntryText
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import InfoBarBase
from Components.config import config
from Screens.InfoBarGenerics import (
    InfoBarMenu,
    InfoBarNotifications,
    InfoBarSeek,
    InfoBarShowHide,
)
from Screens.Screen import Screen
from Tools.Directories import resolveFilename
import hashlib

import gettext
_ = gettext.gettext


try:
    from Tools.Directories import SCOPE_GUISKIN as SCOPE_SKIN
except ImportError:
    from Tools.Directories import SCOPE_SKIN


try:
    from Components.AVSwitch import AVSwitch
except ImportError:
    from Components.AVSwitch import eAVControl as AVSwitch


"""
Plugin RadioM is developed
from Lululla to Mmark 2020
"""

# constant
version = '1.5'
HD = getDesktop(0).size()
PY3 = version_info.major >= 3
screenWidth = getDesktop(0).size().width()
cur_skin = config.skin.primary_skin.value.replace('/skin.xml', '')
path_png = dirname(resolveFilename(SCOPE_SKIN, str(cur_skin))) + "/radio/"
sc = AVSwitch().getFramebufferScale()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"}


def ReadUrl2(url, referer):
    try:
        import ssl
        CONTEXT = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    except BaseException:
        CONTEXT = None

    TIMEOUT_URL = 30
    print('ReadUrl1:\n  url = %s' % url)
    try:
        req = Request(url)
        req.add_header('User-Agent', RequestAgent())
        req.add_header('Referer', referer)
        try:
            r = urlopen(req, None, TIMEOUT_URL, context=CONTEXT)
        except Exception as e:
            r = urlopen(req, None, TIMEOUT_URL)
            print('CreateLog Codifica ReadUrl: %s.' % str(e))
        link = r.read()
        r.close()
        dec = 'Null'
        dcod = 0
        tlink = link
        if str(type(link)).find('bytes') != -1:
            try:
                tlink = link.decode('utf-8')
                dec = 'utf-8'
            except Exception as e:
                dcod = 1
                print('ReadUrl2 - Error: ', str(e))
            if dcod == 1:
                dcod = 0
                try:
                    tlink = link.decode('cp437')
                    dec = 'cp437'
                except Exception as e:
                    dcod = 1
                    print('ReadUrl3 - Error:', str(e))
            if dcod == 1:
                dcod = 0
                try:
                    tlink = link.decode('iso-8859-1')
                    dec = 'iso-8859-1'
                except Exception as e:
                    dcod = 1
                    print('CreateLog Codific ReadUrl: ', str(e))
            link = tlink
        elif str(type(link)).find('str') != -1:
            dec = 'str'
        print('CreateLog Codifica ReadUrl: %s.' % dec)
    except Exception as e:
        print('ReadUrl5 - Error: ', str(e))
        link = None
    return link


def geturl(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        return response.content
    except Exception as e:
        print(str(e))
        return ''


class radioList(MenuList):
    def __init__(self, list):
        MenuList.__init__(self, list, True, eListboxPythonMultiContent)
        if screenWidth >= 1920:
            self.l.setItemHeight(50)
            self.l.setFont(0, gFont('Regular', 38))
        else:
            self.l.setItemHeight(40)
            self.l.setFont(0, gFont('Regular', 34))


def RListEntry(download):
    res = [(download)]
    col = 0xffffff
    colsel = 0xf07655
    pngx = dirname(
        resolveFilename(
            SCOPE_SKIN,
            str(cur_skin))) + "/radio/folder.png"
    if screenWidth >= 1920:
        res.append(
            MultiContentEntryPixmapAlphaTest(
                pos=(
                    10, 10), size=(
                    30, 30), png=loadPNG(pngx)))
        res.append(
            MultiContentEntryText(
                pos=(
                    60,
                    0),
                size=(
                    600,
                    50),
                font=0,
                text=download,
                color=col,
                color_sel=colsel,
                flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    else:
        res.append(
            MultiContentEntryText(
                pos=(
                    0,
                    0),
                size=(
                    400,
                    40),
                font=0,
                text=download,
                color=col,
                color_sel=colsel,
                flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER))
    return res


def showlist(datal, list):
    plist = []
    for name in datal:
        plist.append(RListEntry(name))
    list.setList(plist)


def resizePoster(x, y, dwn_poster):
    try:
        from PIL import Image
        with Image.open(dwn_poster) as img:
            new_width = x
            new_height = y
            try:
                rimg = img.resize((new_width, new_height), Image.LANCZOS)
            except Exception:
                rimg = img.resize((new_width, new_height), Image.ANTIALIAS)
            rimg.save(dwn_poster)
            # no need to close rimg, it's in memory
    except Exception as e:
        print("ERROR:{}".format(e))


def titlesong2(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def titlesong(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, verify=False)
        data = r.json()

        real_duration = data.get("track", {}).get("duration", 0)

        if real_duration <= 0:
            real_duration = 210  # 3.5 minuts

        start_time = dt.strptime(
            data.get(
                "started_at", "")[
                :19], "%Y-%m-%d %H:%M:%S")
        end_time = dt.strptime(
            data.get(
                "ends_at", "")[
                :19], "%Y-%m-%d %H:%M:%S")
        timestamp_duration = int((end_time - start_time).total_seconds())

        real_duration = timestamp_duration if 30 < timestamp_duration < 600 else real_duration
        comeback = (
            'Artist: ' + data.get("artist", {}).get("name", "") + '\n' +
            'Title: ' + data.get("title", "") + '\n' +
            'Duration: ' + str(real_duration) + ' sec'
        )

        return {
            "comeback": comeback,
            "duration": real_duration,
            "title": data.get("title", ""),
            "artist": data.get("artist", {}).get("name", "")
        }

    except Exception as e:
        return {"error": str(e)}


def download_image(url, cache_path="/tmp/radiom_cache/"):
    """Scarica un'immagine da URL e restituisce il percorso locale."""
    try:
        if not exists(cache_path):
            makedirs(cache_path)

        filename = hashlib.md5(url.encode('utf-8')).hexdigest() + ".jpg"
        local_file = cache_path + filename

        if exists(local_file):
            return local_file

        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            with open(local_file, 'wb') as f:
                f.write(response.content)
            return local_file

    except Exception as e:
        print("Download error:", e)

    return None


class radiom1(Screen):
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.list = []
        sz_w = getDesktop(0).size().width()
        if sz_w >= 1920:
            self.skin = """
                <screen name="radiom1" position="center,center" size="1000,600" title="Radio Stations">
                    <widget name="list" position="50,50" size="900,400" scrollbarMode="showOnDemand" />
                    <widget name="info" position="50,10" size="900,30" font="Regular;24" halign="center" />
                    <widget name="logo" position="50,470" size="100,100" />
                    <ePixmap name="red" position="50,560" size="140,40" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="200,560" size="140,40" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="50,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="200,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """
        else:
            self.skin = """
                <screen name="radiom1" position="center,center" size="640,480" title="Radio Stations">
                    <widget name="list" position="30,50" size="580,300" scrollbarMode="showOnDemand" />
                    <widget name="info" position="30,10" size="580,30" font="Regular;18" halign="center" />
                    <widget name="logo" position="30,360" size="80,80" />
                    <ePixmap name="red" position="30,450" size="140,30" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="180,450" size="140,30" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="30,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="180,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """

        self['list'] = radioList([])
        self['info'] = Label('HOME RADIO VIEW')
        self['key_red'] = Button(_('Exit'))
        self['key_green'] = Button(_('Select'))
        self.currentList = 'list'
        self["logo"] = Pixmap()
        self["back"] = Pixmap()
        self.picload = PicLoader()
        global x, y
        pic = path_png + "ft.jpg"
        x = 340
        y = 340
        resizePoster(x, y, pic)
        self.picload.setPara((x, y, sc[0], sc[1], 0, 1, "#00000000"))
        self.picload.addCallback(self.showback)
        self.picload.startDecode(pic)
        self["setupActions"] = ActionMap(
            [
                "HotkeyActions",
                "OkCancelActions",
                "TimerEditActions",
                "DirectionActions"
            ],
            {
                "red": self.close,
                "green": self.okClicked,
                "cancel": self.close,
                "up": self.up,
                "down": self.down,
                "left": self.left,
                "right": self.right,
                "ok": self.okClicked
            }, -2
        )
        self.onLayoutFinish.append(self.openTest)

    def openTest(self):
        self.names = []
        self.urls = []
        self.pics = []
        self.descriptions = []

        all_stations = []
        page = 1
        while True:
            api_url = f"https://api.laut.fm/stations?limit=50&page={page}&order=click&reverse=1"
            try:
                resp = requests.get(api_url, headers=HEADERS, timeout=10)
                if resp.status_code != 200:
                    break
                data = resp.json()
                stations = data if isinstance(
                    data, list) else data.get(
                    "stations", [])
                if not stations:
                    break
                all_stations.extend(stations)
                page += 1
                if page > 25:
                    break
            except Exception as e:
                print(f"Error: {e}")
                break

        for station in all_stations:
            name = station.get("display_name") or station.get("name")
            if name:
                self.names.append(str(name))
                self.urls.append(str(station.get("stream_url", "")))
                pics = station.get("images", {})
                pic_url = pics.get(
                    "station_120x120", "") or pics.get(
                    "station", "")
                self.pics.append(pic_url if pic_url else path_png + "/ft.jpg")
                self.descriptions.append(station.get("description", ""))

        self.names.insert(0, 'PLAYLIST')
        self.urls.insert(0, 'http://75.119.158.76:8090/radio.mp3')
        self.pics.insert(0, path_png + "/ft.jpg")

        self.names.insert(1, 'RADIO CYRUS')
        self.urls.insert(1, 'http://75.119.158.76:8090/radio.mp3')
        self.pics.insert(1, path_png + "/ft.jpg")

        showlist(self.names, self['list'])

    def okClicked(self):
        idx = self['list'].getSelectionIndex()
        if idx is None:
            return
        name = self.names[idx]
        url = self.urls[idx]
        pic = self.pics[idx]
        if 'PLAYLIST' in name:
            self.session.open(radiom2)
        elif 'RADIO CYRUS' in name:
            self.session.open(Playstream2, name, url)
        else:
            self.session.open(radiom80, name, url, pic)

    def selectpic(self):
        idx = self['list'].getSelectionIndex()
        if idx is None:
            return

        pic = self.pics[idx]

        if isinstance(pic, str) and pic.startswith('http'):
            local_pic = download_image(pic)
            pic = local_pic if local_pic else path_png + "/ft.jpg"
        else:
            pic = path_png + "/ft.jpg"

        self.picload = PicLoader()
        self.picload.setPara((x, y, sc[0], sc[1], 0, 1, "#00000000"))
        self.picload.addCallback(self.showback)
        self.picload.startDecode(pic)

    def showback(self, picInfo=None):
        try:
            ptr = self.picload.getData()
            if ptr:
                self["logo"].instance.setPixmap(ptr.__deref__())
                self["logo"].instance.show()
        except Exception:
            self["logo"].instance.hide()

    def up(self):
        self[self.currentList].up()
        self.selectpic()

    def down(self):
        self[self.currentList].down()
        self.selectpic()

    def left(self):
        self[self.currentList].pageUp()
        self.selectpic()

    def right(self):
        self[self.currentList].pageDown()
        self.selectpic()

    def cancel(self):
        Screen.close(self, False)


class radiom2(Screen):

    def __init__(self, session):
        sz_w = getDesktop(0).size().width()
        if sz_w >= 1920:
            self.skin = """
                <screen name="radiom2" position="center,center" size="1000,600" title="Playlists">
                    <widget name="list" position="50,50" size="900,400" scrollbarMode="showOnDemand" />
                    <widget name="info" position="50,10" size="900,30" font="Regular;24" halign="center" />
                    <widget name="logo" position="50,470" size="100,100" />
                    <ePixmap name="red" position="50,560" size="140,40" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="200,560" size="140,40" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="50,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="200,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """
        else:
            self.skin = """
                <screen name="radiom2" position="center,center" size="640,480" title="Playlists">
                    <widget name="list" position="30,50" size="580,300" scrollbarMode="showOnDemand" />
                    <widget name="info" position="30,10" size="580,30" font="Regular;18" halign="center" />
                    <widget name="logo" position="30,360" size="80,80" />
                    <ePixmap name="red" position="30,450" size="140,30" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="180,450" size="140,30" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="30,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="180,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """

        Screen.__init__(self, session)
        self.list = []
        self['list'] = radioList([])
        self['info'] = Label()
        self['info'].setText('UserList')
        self['key_red'] = Button(_('Exit'))
        self['key_green'] = Button(_('Select'))
        self["logo"] = Pixmap()
        self["back"] = Pixmap()
        self["back"].hide()
        self.picload = PicLoader()
        pic = path_png + "ft.jpg"
        x = 340
        y = 340
        resizePoster(x, y, pic)
        self.picload.setPara((x, y, sc[0], sc[1], 0, 1, "#00000000"))
        self.picload.addCallback(self.showback)
        self.picload.startDecode(pic)
        self["setupActions"] = ActionMap(
            ["SetupActions", "ColorActions", "TimerEditActions"],
            {
                "red": self.close,
                "green": self.okClicked,
                "cancel": self.cancel,
                "ok": self.okClicked,
            },
            -2
        )
        self.onLayoutFinish.append(self.openTest)

    def openTest(self):
        self.names = []
        for root, dirs, files in walk(path_png):
            for name in files:
                if '.txt' in name:
                    self.names.append(name)
        showlist(self.names, self['list'])

    def okClicked(self):
        idx = self['list'].getSelectionIndex()
        if idx is None:
            return
        name = self.names[idx]
        self.session.open(radiom3, name)

    def showback(self, picInfo=None):
        try:
            ptr = self.picload.getData()
            if ptr is not None:
                self["logo"].instance.setPixmap(ptr.__deref__())
                self["logo"].instance.show()
        except Exception as err:
            self["logo"].instance.hide()
            print("ERROR showImage:", err)

    def cancel(self):
        Screen.close(self, False)


class radiom3(Screen):
    def __init__(self, session, name):
        sz_w = getDesktop(0).size().width()
        if sz_w >= 1920:
            self.skin = """
                <screen name="radiom3" position="center,center" size="1000,600" title="Playlist: %s">
                    <widget name="list" position="50,50" size="900,400" scrollbarMode="showOnDemand" />
                    <widget name="info" position="50,10" size="900,30" font="Regular;24" halign="center" />
                    <widget name="logo" position="50,470" size="100,100" />
                    <ePixmap name="red" position="50,560" size="140,40" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="200,560" size="140,40" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="50,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="200,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """ % name
        else:
            self.skin = """
                <screen name="radiom3" position="center,center" size="640,480" title="Playlist: %s">
                    <widget name="list" position="30,50" size="580,300" scrollbarMode="showOnDemand" />
                    <widget name="info" position="30,10" size="580,30" font="Regular;18" halign="center" />
                    <widget name="logo" position="30,360" size="80,80" />
                    <ePixmap name="red" position="30,450" size="140,30" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="180,450" size="140,30" pixmap="skin_default/buttons/green.png" />
                    <widget source="key_red" render="Label" position="30,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="180,450" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                </screen>
                """ % name

        Screen.__init__(self, session)
        self.name = name
        self.list = []
        self['list'] = radioList([])
        self['info'] = Label()
        self['info'].setText(name)
        self['key_red'] = Button(_('Exit'))
        self['key_green'] = Button(_('Select'))
        self["logo"] = Pixmap()
        self["back"] = Pixmap()
        self["back"].hide()
        self.srefOld = self.session.nav.getCurrentlyPlayingServiceReference()
        self.is_playing = False
        self.picload = PicLoader()
        global x, y
        pic = path_png + "ft.jpg"
        x = 340
        y = 340
        resizePoster(x, y, pic)
        self.picload.setPara((x, y, sc[0], sc[1], 0, 1, "#00000000"))
        self.picload.addCallback(self.showback)
        self.picload.startDecode(pic)
        self["setupActions"] = ActionMap(
            ["SetupActions", "ColorActions", "TimerEditActions"],
            {
                "red": self.close,
                "green": self.okClicked,
                "cancel": self.cancel,
                "ok": self.okClicked,
            },
            -2
        )
        self.onLayoutFinish.append(self.openTest)

    def openTest(self):
        file1 = path_png + str(self.name)
        print('Here in showContentA2 file1 = ', file1)
        self.names = []
        self.urls = []
        try:
            with open(file1, "r") as f1:
                for line in f1:
                    if "##" not in line:
                        continue
                    line = line.strip()
                    items = line.split("###")
                    if len(items) < 2:
                        continue
                    name = items[0]
                    url = items[1]
                    self.names.append(name)
                    self.urls.append(url)
                showlist(self.names, self['list'])
        except Exception as e:
            print("Error reading file:", e)

    def okClicked(self):
        idx = self["list"].getSelectionIndex()
        if idx is None:
            return
        name = self.names[idx]
        url = self.urls[idx]
        if self.is_playing:
            self.stop()
            return

        url = url.replace(":", "%3a").replace(" ", "%20")
        ref = "4097:0:1:0:0:0:0:0:0:0:" + str(url)
        print("final reference:   ", ref)
        sref = eServiceReference(ref)
        sref.setName(name)
        self.session.nav.stopService()
        self.session.nav.playService(sref)
        self.is_playing = True

    def stop(self, text=''):
        if self.is_playing:
            try:
                self.is_playing = False
                self.session.nav.stopService()
                self.session.nav.playService(self.srefOld)
                return
            except TypeError as e:
                print(e)
                self.close()

    def showback(self, picInfo=None):
        try:
            ptr = self.picload.getData()
            if ptr is not None:
                self["logo"].instance.setPixmap(ptr.__deref__())
                self["logo"].instance.show()
        except Exception as err:
            self["logo"].instance.hide()
            print("ERROR showImage:", err)

    def cancel(self):
        self.stop()
        Screen.close(self, False)


class radiom80(Screen):
    def __init__(self, session, name, url, pic):
        sz_w = getDesktop(0).size().width()
        if sz_w >= 1920:
            self.skin = """
                <screen name="radiom80" position="center,center" size="1200,700" title="%s">
                    <widget name="list" position="50,50" size="500,400" scrollbarMode="showOnDemand" />
                    <widget name="info" position="50,10" size="1100,30" font="Regular;24" halign="center" />
                    <widget name="current_song" position="600,50" size="550,92" font="Regular;22" />
                    <widget name="listeners" position="600,145" size="550,50" font="Regular;20" scrollbarMode="showNever" />
                    <widget name="format" position="600,200" size="550,50" font="Regular;20" />
                    <widget name="description" position="600,250" size="550,131" font="Regular;20" />
                    <widget name="djs" position="600,385" size="550,50" font="Regular;20" />
                    <widget name="logo" position="600,445" size="200,200" />
                    <widget name="back" position="600,445" size="200,200" />
                    <ePixmap name="red" position="50,560" size="140,40" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="200,560" size="140,40" pixmap="skin_default/buttons/green.png" />
                    <ePixmap name="blue" position="350,560" size="140,40" pixmap="skin_default/buttons/blue.png" />
                    <widget source="key_red" render="Label" position="50,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="200,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                    <widget source="key_blue" render="Label" position="350,560" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="blue" foregroundColor="white" transparent="1" />
                </screen>
                """ % name
        else:
            self.skin = """
                <screen name="radiom80" position="center,center" size="800,500" title="%s">
                    <widget name="list" position="10,50" size="330,250" scrollbarMode="showOnDemand" />
                    <widget name="info" position="30,10" size="740,30" font="Regular;18" halign="center" />
                    <widget name="current_song" position="350,45" size="440,52" font="Regular;16" />
                    <widget name="listeners" position="350,100" size="440,35" font="Regular;14" />
                    <widget name="format" position="350,136" size="440,50" font="Regular;14" />
                    <widget name="description" position="350,190" size="440,80" font="Regular;14" />
                    <widget name="djs" position="350,270" size="440,25" font="Regular;14" />
                    <widget name="logo" position="599,301" size="150,150" />
                    <widget name="back" position="599,301" size="150,150" />
                    <ePixmap name="red" position="30,420" size="140,30" pixmap="skin_default/buttons/red.png" />
                    <ePixmap name="green" position="180,420" size="140,30" pixmap="skin_default/buttons/green.png" />
                    <ePixmap name="blue" position="330,420" size="140,30" pixmap="skin_default/buttons/blue.png" />
                    <widget source="key_red" render="Label" position="30,420" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="red" foregroundColor="white" transparent="1" />
                    <widget source="key_green" render="Label" position="180,420" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="green" foregroundColor="white" transparent="1" />
                    <widget source="key_blue" render="Label" position="330,420" size="140,30" font="Regular;16" halign="center" valign="center" backgroundColor="blue" foregroundColor="white" transparent="1" />
                </screen>
                """ % name

        Screen.__init__(self, session)
        self.session = session
        self.name = name
        self.url = url
        self.pic = pic
        self.list = []
        self['list'] = radioList([])
        self['info'] = Label()
        self['info'].setText(name)
        self['current_song'] = Label()
        self['listeners'] = Label()
        self['format'] = Label()
        self['description'] = Label()
        self['djs'] = Label()
        self["logo"] = Pixmap()
        self["back"] = Pixmap()
        self["back"].hide()
        self.player = '1'
        self.picload = PicLoader()
        global x, y
        # pic = pic.replace("\n", "").replace("\r", "")
        # x = 340
        # y = 340
        # resizePoster(x, y, pic)

        pic = pic.replace("\n", "").replace("\r", "")
        x = 430
        y = 430
        if screenWidth == 1920:
            x = 340
            y = 340
        if screenWidth == 2560:
            x = 640
            y = 640

        if pic.startswith('http'):
            local_pic = download_image(pic)
            pic = local_pic if local_pic else path_png + "/ft.jpg"
        else:
            pic = path_png + "/ft.jpg"
        resizePoster(x, y, pic)

        self.picload.setPara((x, y, sc[0], sc[1], 0, 1, "#00000000"))
        self.picload.addCallback(self.showback)
        self.picload.startDecode(self.pic)
        self.srefOld = self.session.nav.getCurrentlyPlayingServiceReference()
        self.is_playing = False
        self.cover_timer = eTimer()
        self.cover_timer.callback.append(self.countdown)
        self.current_artist = ""
        self.current_title = ""
        self.last_song_id = ""
        self.okcoverdown = 'failed'

        self.update_timer = eTimer()
        self.update_timer.callback.append(self.countdown)
        self.update_timer.start(10000, False)
        self.last_cover_request = 0
        self.song_start_time = time()
        self.last_song_hash = ""
        self.current_cover = ""
        self.cover_timeout = 0
        self.backing = ""
        self.current_duration = 0

        self['key_red'] = Button(_('Exit'))
        self['key_blue'] = Label("Player 1-2-3")
        self['key_green'] = Button(_('Select'))
        self['key_green'].hide()
        self["actions"] = ActionMap(
            [
                "OkActions",
                "SetupActions",
                "ColorActions",
                "EPGSelectActions",
                "InfoActions",
                "CancelActions"
            ],
            {
                "red": self.cancel,
                "back": self.cancel,
                "blue": self.typeplayer,
                "green": self.openPlay,
                "info": self.countdown,
                "cancel": self.cancel,
                "ok": self.openPlay,
            }, -2
        )
        self.onShow.append(self.openTest)

    def typeplayer(self):
        if self.player == "2":
            self["key_blue"].setText("Player 3-2-1")
            self.player = "3"
        elif self.player == "1":
            self["key_blue"].setText("Player 2-3-1")
            self.player = "2"
        else:
            self["key_blue"].setText("Player 1-2-3")
            self.player = "1"
        return

    def showback(self, picInfo=None):
        try:
            ptr = self.picload.getData()
            if ptr is not None:
                self["logo"].instance.setPixmap(ptr.__deref__())
                self["logo"].instance.show()
        except Exception as err:
            print("ERROR showback:", err)

    def showback2(self, picInfo=None):
        try:
            self["back"].instance.show()
        except Exception as err:
            self["back"].instance.hide()
            print("ERROR showback2:", err)

    def selectpic(self):
        try:
            if hasattr(self, 'okcoverdown') and self.okcoverdown == 'success':
                temp_path = '/tmp/artist_temp.jpg'
                final_path = '/tmp/artist.jpg'

                if exists(final_path):
                    try:
                        with Image.open(final_path) as img:
                            if img.format != 'JPEG':
                                img.convert('RGB').save(
                                    temp_path, 'JPEG', quality=90)
                                replace(temp_path, final_path)
                    except Exception as conv_err:
                        print("Errore conversione:", conv_err)
                        remove(final_path) if exists(final_path) else None
                        return

                if exists(final_path) and getsize(final_path) > 2048:
                    x = self["logo"].instance.size().width()
                    y = self["logo"].instance.size().height()
                    self["logo"].instance.setPixmap(None)
                    resizePoster(x, y, final_path)
                    self.picload = PicLoader()
                    self.picload.setPara(
                        (x, y, sc[0], sc[1], 0, 1, "#FF000000"))

                    def safe_callback(picInfo=None):
                        try:
                            ptr = self.picload.getData()
                            if ptr:
                                self["logo"].instance.setPixmap(
                                    ptr.__deref__())
                                self["logo"].instance.show()
                        except Exception as e:
                            print("Error callback:", e)

                    self.picload.addCallback(safe_callback)
                    self.picload.startDecode(final_path)
                else:
                    print("Invalid or missing image file")

        except Exception as err:
            print("Error selectpic:", err)
            self.picload.startDecode(self.pic)

    def getCover(self, url):
        try:
            temp_path = '/tmp/artist_temp.jpg'
            final_path = '/tmp/artist.jpg'

            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)

            with Image.open(temp_path) as img:
                img.verify()

            replace(temp_path, final_path)
            return True

        except Exception as e:
            if exists(temp_path):
                remove(temp_path)
            print("Error getCover:", str(e))
            return False

    def downloadCover(self, title):
        try:
            self.okcoverdown = 'failed'
            clean_title = sub(r'\([^)]*\)', '', title).strip()
            search_query = f"{
                self.current_artist} {clean_title}" if self.current_artist else clean_title
            itunes_url = f'https://itunes.apple.com/search?term={
                quote(search_query)}&entity=album&limit=1'
            res = requests.get(itunes_url, timeout=10)
            data = res.json()
            if data.get('resultCount', 0) == 0:
                itunes_url = f'https://itunes.apple.com/search?term={
                    quote(search_query)}&entity=song&limit=1'
                res = requests.get(itunes_url, timeout=10)
                data = res.json()

            if data.get('resultCount', 0) > 0:
                artwork_url = data['results'][0].get('artworkUrl100', '')
                if artwork_url:
                    artwork_url = artwork_url.replace('100x100bb', '600x600bb')
                    if self.getCover(artwork_url):
                        self.okcoverdown = 'success'
        except Exception as e:
            print("Error download:", str(e))

    def loadPlaylist(self):
        """Carica i dati della stazione da API laut.fm (versione corretta)."""
        try:
            station_name = self.name.lower().replace(" ", "-")
            station_url = f"https://api.laut.fm/station/{station_name}"
            data_station = titlesong2(station_url)

            if "error" in data_station:
                print("Station error:", data_station["error"])
                return

            display_name = data_station.get("display_name", self.name)
            stream_url = data_station.get("stream_url", "")
            listeners = data_station.get("listeners", 0)
            fmt = data_station.get("format", "")
            description = data_station.get("description", "")
            djs = data_station.get("djs", "")

            # Current song
            song_url = f"https://api.laut.fm/station/{station_name}/current_song"
            data_song = titlesong2(song_url)

            if "error" in data_song:
                current_song = _("No song")
            else:
                artist = data_song.get("artist", {}).get("name", "")
                title = data_song.get("title", "")
                current_song = f"{artist} - {title}".strip(" -")
                if not current_song:
                    current_song = _("Unknown")

                # Aggiorna cover se cambiata
                if hasattr(
                        self,
                        'last_song') and self.last_song != current_song:
                    self.downloadCover(current_song)
                    self.selectpic()
                elif not hasattr(self, 'last_song'):
                    self.downloadCover(current_song)
                    self.selectpic()
                self.last_song = current_song

            self['current_song'].setText(current_song)
            self['listeners'].setText(_('Online: ') + str(listeners))
            self['format'].setText(fmt)
            self['description'].setText(description)
            self['djs'].setText(_('Dj: ') + str(djs))

            self.names = [display_name]
            self.urls = [stream_url]
            self['info'].setText(_('Select and Play'))
            self['key_green'].show()
            showlist(self.names, self['list'])

        except Exception as e:
            print("Error in loadPlaylist:", e)
            import traceback
            traceback.print_exc()

    def openTest(self):
        """Avvia il caricamento della playlist con timer."""
        self.timer = eTimer()
        try:
            self.timer_conn = self.timer.timeout.connect(self.loadPlaylist)
        except BaseException:
            self.timer.callback.append(self.loadPlaylist)
        self.timer.start(250, True)

    def countdown(self):
        try:
            if not self.backing:
                print("No URLs set for songs")
                return

            data = titlesong(self.backing)
            if "error" in data:
                print("Errore API:", data["error"])
                return

            current_id = f"{data['artist']}-{data['title']}"
            if self.last_song_id != current_id:
                self['current_song'].setText(data["comeback"])
                self.downloadCover(f"{data['artist']} {data['title']}")
                self.selectpic()
                self.last_song_id = current_id

            remaining = data["duration"] - (time() - self.song_start_time)
            if remaining > 0:
                self.cover_timer.start(int(remaining * 1000), False)
            else:
                self.song_start_time = time()
                self.cover_timer.start(1000, False)

        except Exception as e:
            print("Error countdown:", e)

    def openPlay(self):
        idx = self["list"].getSelectionIndex()
        if idx is None:
            return
        self.showback2()
        name = self.names[idx]
        url = self.urls[idx]
        if self.is_playing:
            self.stop()
            return
        try:
            if self.player == "2":
                self.session.open(Playstream2, name, url)
            else:
                url = url.replace(":", "%3a").replace(" ", "%20")
                if self.player == "3":
                    ref = "4097:0:1:0:0:0:0:0:0:0:" + str(url)
                else:
                    ref = "4097:0:2:0:0:0:0:0:0:0:" + str(url)

                print("Final reference:", ref)
                sref = eServiceReference(ref)
                sref.setName(name)
                self.session.nav.stopService()
                self.session.nav.playService(sref)
                self.is_playing = True
                self.countdown()
        except Exception as e:
            print("Error during playback:", e)

    def listener(self, urlx):
        content = None
        try:
            referer = "https://laut.fm"
            raw = ReadUrl2(urlx, referer)
            content = json_loads(raw)
        except Exception as e:
            print("err:", e)
        return content

    def cancel(self):
        self.stop()
        self.close()

    def stop(self, text=""):
        if self.is_playing:
            self.timer.stop()
            try:
                self["back"].instance.hide()
                self.is_playing = False
                self.session.nav.stopService()
                self.session.nav.playService(self.srefOld)
                self.cover_timer.stop()
            except TypeError:
                self.cover_timer.stop()
                self.close()
            aspect_manager.restore_aspect()


class Playstream2(
        Screen,
        InfoBarMenu,
        InfoBarBase,
        InfoBarSeek,
        InfoBarNotifications,
        InfoBarShowHide):
    STATE_PLAYING = 1
    STATE_PAUSED = 2

    def __init__(self, session, name, url):
        Screen.__init__(self, session)
        self.skinName = 'MoviePlayer'
        self.sref = None
        InfoBarMenu.__init__(self)
        InfoBarNotifications.__init__(self)
        InfoBarBase.__init__(self)
        InfoBarShowHide.__init__(self)
        try:
            self.init_aspect = int(self.getAspect())
        except BaseException:
            self.init_aspect = 0
        self.new_aspect = self.init_aspect
        self["actions"] = ActionMap(
            [
                "WizardActions",
                "MoviePlayerActions",
                "EPGSelectActions",
                "MediaPlayerSeekActions",
                "ColorActions",
                "InfobarShowHideActions",
                "InfobarSeekActions",
                "InfobarActions"
            ],
            {
                "leavePlayer": self.stop,                   # Stop the player
                "back": self.stop,                          # Back action to stop the player
                "playpauseService": self.togglePlayPause,   # Toggle play/pause
                # "down": self.adjustAVSettings             # Adjust AV settings or navigate down
            },
            -1
        )
        self.allowPiP = False
        self.is_playing = False
        InfoBarSeek.__init__(self, actionmap='MediaPlayerSeekActions')
        self.icount = 0
        self.name = name
        self.url = url
        self.state = self.STATE_PLAYING
        self.srefOld = self.session.nav.getCurrentlyPlayingServiceReference()
        self.onLayoutFinish.append(self.openPlay)
        return

    def __onStop(self):
        self.stop()

    def openPlay(self):
        if self.is_playing:
            self.stop()
        try:
            url = self.url.replace(':', '%3a').replace(' ', '%20')
            # ref = '4097:0:1:0:0:0:0:0:0:0:' + str(url)  # tv
            ref = '4097:0:2:0:0:0:0:0:0:0:' + str(url)  # radio
            print('final reference:   ', ref)
            sref = eServiceReference(ref)
            sref.setName(self.name)
            self.session.nav.stopService()
            self.session.nav.playService(sref)
            self.is_playing = True
        except BaseException:
            pass

    def stop(self, text=''):
        if self.is_playing:
            try:
                self.is_playing = False
                self.session.nav.stopService()
                self.session.nav.playService(self.srefOld)
                self.exit()
            except TypeError as e:
                print(e)
                self.exit()

    def exit(self):
        aspect_manager.restore_aspect()
        self.close()

    def playpauseService(self):
        if self.state == self.STATE_PLAYING:
            self.pause()
            self.state = self.STATE_PAUSED
        elif self.state == self.STATE_PAUSED:
            self.unpause()
            self.state = self.STATE_PLAYING

    def pause(self):
        self.session.nav.pause(True)

    def unpause(self):
        self.session.nav.pause(False)

    def keyLeft(self):
        self['text'].left()

    def keyRight(self):
        self['text'].right()

    def keyNumberGlobal(self, number):
        self['text'].number(number)


ListAgent = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2919.83 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.13 (KHTML, like Gecko) Chrome/24.0.1290.1 Safari/537.13',
]


def RequestAgent():
    from random import choice
    RandomAgent = choice(ListAgent)
    return RandomAgent


class PicLoader:
    def __init__(self):
        self.picload = ePicLoad()
        self.picload_conn = None

    def setSize(self, width, height, sc=None):
        if sc is None:
            sc = AVSwitch().getFramebufferScale()
        self.picload.setPara(
            (width, height, sc[0], sc[1], False, 1, "#ff000000"))

    def load(self, filename):
        if exists('/var/lib/dpkg/status'):
            self.picload.startDecode(filename, False)
        else:
            self.picload.startDecode(filename, 0, 0, False)
        data = self.picload.getData()
        return data

    def destroy(self):
        self.picload = None
        self.picload_conn = None

    def addCallback(self, callback):
        if exists('/var/lib/dpkg/status'):
            self.picload_conn = self.picload.PictureData.connect(callback)
        else:
            self.picload.PictureData.get().append(callback)

    def getData(self):
        return self.picload.getData()

    def setPara(self, *args):
        self.picload.setPara(*args)

    def startDecode(self, f):
        self.picload.startDecode(f)


class AspectManager:
    """Manages aspect ratio settings for the plugin"""

    def __init__(self):
        self.save_current_aspect()  # Salva l'aspect ratio corrente all'inizializzazione
        print("[INFO] Initial aspect ratio saved:", self.init_aspect)

    def save_current_aspect(self):
        """Save current aspect ratio setting"""
        try:
            self.init_aspect = self.get_current_aspect()
            print("[INFO] Current aspect ratio saved:", self.init_aspect)
        except Exception as e:
            print("[ERROR] Failed to save aspect ratio:", str(e))
            self.init_aspect = 0  # Fallback

    def get_current_aspect(self):
        """Get current aspect ratio setting"""
        try:
            aspect = AVSwitch().getAspectRatioSetting()
            return int(aspect) if aspect is not None else 0
        except (ValueError, TypeError, Exception) as e:
            print("[ERROR] Failed to get aspect ratio:", str(e))
            return 0  # Default 4:3

    def restore_aspect(self):
        """Restore original aspect ratio"""
        try:
            if hasattr(self, 'init_aspect') and self.init_aspect is not None:
                print("[INFO] Restoring aspect ratio to:", self.init_aspect)
                AVSwitch().setAspectRatio(self.init_aspect)
            else:
                print("[WARNING] No initial aspect ratio to restore")
        except Exception as e:
            print("[ERROR] Failed to restore aspect ratio:", str(e))


aspect_manager = AspectManager()
aspect_manager.get_current_aspect()
