#!/usr/bin/python
# -*- coding: utf-8 -*-
###################################
##__author__ = "Lululla"         ##
##__copyright__ = "AGP Team"     ##
##__modified_by__ = "MNASR"      ##
###################################
from __future__ import absolute_import, print_function

# Standard library
from os import remove
from os.path import exists, getsize
from re import compile, findall, DOTALL, sub, IGNORECASE
from threading import Thread
from json import loads as json_loads
from random import choice
from unicodedata import normalize
from time import sleep
import threading
import urllib3
import logging

# Third-party libraries
from PIL import Image
from requests import get, codes, Session
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import HTTPError, RequestException
from twisted.internet.reactor import callInThread
from functools import lru_cache

# Enigma2 specific
from enigma import getDesktop
from Components.config import config

# Local imports
from .Agp_lib import quoteEventName, split_title_and_year
from .Agp_apikeys import tmdb_api, thetvdb_api, fanart_api  # , omdb_api
from .Agp_Utils import logger

# ========================
# DISABLE URLLIB3 DEBUG LOGS
# ========================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


global my_cur_skin, srch


try:
	lng = config.osd.language.value
	lng = lng[:-3]
except BaseException:
	lng = 'en'
	pass


def getRandomUserAgent():
	useragents = [
		'Mozilla/5.0 (compatible; Konqueror/4.5; FreeBSD) KHTML/4.5.4 (like Gecko)',
		'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36',
		'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:29.0) Gecko/20120101 Firefox/29.0',
		'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:33.0) Gecko/20100101 Firefox/33.0',
		'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:35.0) Gecko/20120101 Firefox/35.0',
		'Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0',
		'Mozilla/5.0 (X11; Linux x86_64; rv:28.0) Gecko/20100101 Firefox/28.0',
		'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8) AppleWebKit/537.13+ (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2',
		'Opera/9.80 (Macintosh; Intel Mac OS X 10.6.8; U; de) Presto/2.9.168 Version/11.52',
		'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'
	]
	return choice(useragents)


AGENTS = [
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
	"Mozilla/5.0 (iPhone; CPU iPhone OS 14_4_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0",
	"Mozilla/4.0 (compatible; MSIE 9.0; Windows NT 6.1)",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36 Edge/87.0.664.75",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36 Edge/18.18363"
]
headers = {"User-Agent": choice(AGENTS)}


isz = "1280,720"
screenwidth = getDesktop(0).size()
if screenwidth.width() <= 1280:
	isz = isz.replace(isz, "1280,720")
elif screenwidth.width() <= 1920:
	isz = isz.replace(isz, "1280,720")
else:
	isz = isz.replace(isz, "1280,720")


'''
🖼️ Poster Sizes:
Available: "w92", "w154", "w185", "w342", "w500", "w780", "original"

🖼️ Backdrop Sizes:
Available: "w300", "w780", "w1280", "original"

🧑‍🎤 Profile Sizes:
Available: "w45", "w185", "h632", "original"

📺 Still Frame (Episode Image) Sizes:
Available: "w92", "w185", "w300", "original"

🏷️ Logo Sizes:
Available: "w45", "w92", "w154", "w185", "w300", "w500", "original"

📐 Recommended Image Dimensions (in pixels):


Type    Recommended Size Range  Aspect Ratio
Poster  500×750 → 2000×3000 1.5 (2:3)
TV Season Poster    400×578 → 2000×3000 1.5 (2:3)
Backdrop    1280×720 → 3840×2160    1.777 (16:9)
Still (Episode) 400×225 → 3840×2160 1.777 (16:9)
Profile 300×450 → 2000×3000 1.5 (2:3)
Logo (PNG)  500×1 → 2000×2000   Variable
Logo (SVG)  500×1 → Vector graphic  Variable
'''


class AgbDownloadThread(Thread):
	"""
	Main Backdrop renderer class for Enigma2
	Handles Backdrop display and refresh logic

	Features:
	- Dynamic Backdrop loading based on current program
	- Automatic refresh when channel/program changes
	- Multiple image format support
	- Skin-configurable providers
	- Asynchronous Backdrop loading
	"""

	def __init__(self, *args, **kwargs):
		Thread.__init__(self)
		self._stop_event = threading.Event()
		self.search_year = ""
		self.checkMovie = [
			"film", "movie", "фильм", "кино", "ταινία",
			"película", "cinéma", "cine", "cinema", "filma"
		]
		self.checkTV = [
			"serial", "series", "serie", "serien", "série", "séries",
			"serious", "folge", "episodio", "episode", "épisode",
			"l'épisode", "ep.", "animation", "staffel", "soap", "doku",
			"tv", "talk", "show", "news", "factual", "entertainment",
			"telenovela", "dokumentation", "dokutainment", "documentary",
			"informercial", "information", "sitcom", "reality", "program",
			"magazine", "mittagsmagazin", "т/с", "м/с", "сезон", "с-н",
			"эпизод", "сериал", "серия", "actualité", "discussion",
			"interview", "débat", "émission", "divertissement", "jeu",
			"magasine", "information", "météo", "journal", "sport",
			"culture", "infos", "feuilleton", "téléréalité", "société",
			"clips", "concert", "santé", "éducation", "variété"
		]

		if config.plugins.Aglare.cache.value:
			self.search_tmdb = lru_cache(maxsize=100)(self.search_tmdb)
			self.search_tvdb = lru_cache(maxsize=100)(self.search_tvdb)
			self.search_fanart = lru_cache(maxsize=100)(self.search_fanart)
			self.search_omdb = lru_cache(maxsize=100)(self.search_omdb)
			self.search_imdb = lru_cache(maxsize=100)(self.search_imdb)
			self.search_programmetv_google = lru_cache(maxsize=100)(self.search_programmetv_google)
			self.search_molotov_google = lru_cache(maxsize=100)(self.search_molotov_google)
			self.search_elcinema = lru_cache(maxsize=100)(self.search_elcinema)
			self.search_google = lru_cache(maxsize=100)(self.search_google)

	def _normalize_match_title(self, value):
		value = str(value or "").lower().strip()
		value = value.replace("&", " and ")
		value = sub(r"[^a-z0-9\u0600-\u06FF]+", " ", value)
		value = sub(r"\s+", " ", value).strip()
		return value

	def _select_best_tmdb_result(self, results, shortdesc="", fulldesc="", year=None):
		target = self._normalize_match_title(self.title_safe)
		srch, _fd = self.checkType(shortdesc, fulldesc)

		candidates = []

		for each in results:
			title = each.get('name', each.get('title', ''))
			original_title = each.get('original_name', each.get('original_title', ''))
			media_type = str(each.get('media_type', '')).lower()

			if not media_type:
				if srch == "tv":
					media_type = "serie"
				elif srch == "movie":
					media_type = "movie"

			if media_type == "tv":
				media_type = "serie"

			backdrop_path = each.get('backdrop_path')
			if media_type not in ['movie', 'serie'] or not backdrop_path:
				continue

			title_n = self._normalize_match_title(title)
			orig_n = self._normalize_match_title(original_title)
			result_year = each.get('release_date', each.get('first_air_date', ''))[:4]

			score = 0

			if title_n == target:
				score += 500
			if orig_n == target:
				score += 500

			if target and target in title_n:
				score += 120
			if target and target in orig_n:
				score += 120
			if title_n and title_n in target:
				score += 80
			if orig_n and orig_n in target:
				score += 80

			if srch == 'movie' and media_type == 'movie':
				score += 200
			elif srch in ('tv', 'serie') and media_type == 'serie':
				score += 200
			elif srch == 'multi':
				if media_type == 'movie':
					score += 30
				elif media_type == 'serie':
					score += 10

			if year:
				if result_year:
					if str(year) == str(result_year):
						score += 600
					else:
						score -= 500
				else:
					score -= 150

			try:
				score += min(float(each.get('popularity', 0)), 10)
			except Exception:
				pass

			candidates.append((each, score, result_year))

		if not candidates:
			return None, -1

		if year:
			exact_year = [(each, score) for each, score, result_year in candidates if str(result_year) == str(year)]
			if exact_year:
				exact_year.sort(key=lambda x: x[1], reverse=True)
				return exact_year[0][0], exact_year[0][1]

		candidates.sort(key=lambda x: x[1], reverse=True)
		return candidates[0][0], candidates[0][1]

	def search_tmdb(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""Download backdrop from TMDB with full verification pipeline (thread-safe)"""
		def _strip_year_for_search(t):
			t = str(t).strip()
			t = sub(r"\s*[\(\[]\s*(?:19|20)\d{2}\s*[\)\]]\s*", " ", t)
			t = sub(r"(?<!^)\s+(?:19|20)\d{2}\s*$", "", t)
			return sub(r"\s+", " ", t).strip()

		tmdb_api_key = api_key or tmdb_api
		if not tmdb_api_key:
			return False, "No API key"

		try:
			if not dwn_backdrop or not title:
				return False, "Invalid input parameters"

			clean_input_title = title.replace("+", " ").replace('–', '').strip()
			logger.info("[tmdb] year flow | step='clean_input_title' | value='{}'".format(str(clean_input_title or "")))

			forced_year = ""
			split_title = clean_input_title
			try:
				split_title, forced_year = split_title_and_year(clean_input_title)
				logger.info("[tmdb] year flow | step='split_title_and_year' | split_title='{}' | forced_year='{}'".format(
					str(split_title or ""), str(forced_year or "")
				))
			except Exception as e:
				logger.info("[tmdb] year flow | step='split_title_and_year_error' | error='{}'".format(str(e)))
				forced_year = ""
				split_title = clean_input_title

			local_title_safe = _strip_year_for_search(split_title)
			logger.info("[tmdb] year flow | step='strip_year_for_search' | title_safe='{}'".format(str(local_title_safe or "")))

			if not local_title_safe:
				return False, "Invalid title after cleaning"

			srch, fd = self.checkType(shortdesc, fulldesc)
			logger.info("[tmdb] year flow | step='checkType' | srch='{}' | fd='{}'".format(str(srch or ""), str(fd or "")))

			desc_year = ""
			if not year:
				desc_year = self._extract_year(fd)
				year = desc_year
			logger.info("[tmdb] year flow | step='extract_year' | desc_year='{}' | incoming_year='{}'".format(
				str(desc_year or ""), str(year or "")
			))

			if forced_year and not year:
				year = forced_year
				logger.info("[tmdb] year flow | step='apply_forced_year' | applied_year='{}'".format(str(year or "")))
			else:
				logger.info("[tmdb] year flow | step='skip_forced_year' | forced_year='{}' | final_year_before_search='{}'".format(
					str(forced_year or ""), str(year or "")
				))

			local_search_year = year or ""
			logger.info("[tmdb] year flow | step='final_search_parts' | title_safe='{}' | search_year='{}'".format(
				str(local_title_safe or ""), str(local_search_year or "")
			))

			old_title_safe = getattr(self, "title_safe", None)
			old_search_year = getattr(self, "search_year", None)
			self.title_safe = local_title_safe
			self.search_year = local_search_year

			request_url = f"https://api.themoviedb.org/3/search/{srch}?api_key={tmdb_api_key}&language={lng}&query={local_title_safe}"
			if year and srch in ("movie", "multi"):
				request_url += f"&year={year}"

			try:
				logger.info("[tmdb] title flow | original='{}' | final='{}' | year='{}' | channel='{}'".format(
					str(title or ""), str(local_title_safe or ""), str(year or ""), str(channel or "")
				))
				logger.info("[tmdb] search link | url={}".format(request_url))
			except Exception:
				pass

			retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
			adapter = HTTPAdapter(max_retries=retries)
			http = Session()
			http.mount("http://", adapter)
			http.mount("https://", adapter)

			response = http.get(request_url, headers=headers, timeout=(10, 20), verify=False)
			response.raise_for_status()

			if response.status_code == codes.ok:
				data = response.json()
				if data and data.get('results'):
					rank_year = local_search_year

					# For TV, the year in EPG is often episode/season year, not first_air_date.
					# Do not use it for title ranking.
					if srch == "tv":
						rank_year = ""

					return self.downloadData2(
						data,
						dwn_backdrop,
						shortdesc,
						fulldesc,
						title_safe=local_title_safe,
						search_year=rank_year
					)
				logger.warning("No results found on TMDB")
				return False, "No results"

			logger.warning("No results found on TMDB")
			return False, "No results"

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				return False, "No results found on TMDb"
			else:
				logger.error("TMDb HTTP error: " + str(e))
				return False, "HTTP error during TMDb search"

		except Exception as e:
			logger.error("TMDb search error: " + str(e))
			return False, "Unexpected error during TMDb search"

		finally:
			try:
				self.title_safe = old_title_safe
				self.search_year = old_search_year
			except Exception:
				pass


	def downloadData2(self, data, dwn_backdrop, shortdesc="", fulldesc="", title_safe="", search_year=""):
		if not data.get('results'):
			logger.warning("No results found on TMDB")
			return False, "No results"

		if isinstance(data, bytes):
			data = data.decode("utf-8", errors="ignore")
		data_json = data if isinstance(data, dict) else json_loads(data)

		old_title_safe = getattr(self, "title_safe", None)
		old_search_year = getattr(self, "search_year", None)
		self.title_safe = title_safe or ""
		self.search_year = search_year or ""

		try:
			results = data_json.get('results', [])
			best, best_score = self._select_best_tmdb_result(
				results,
				shortdesc,
				fulldesc,
				(search_year or self._extract_year(fulldesc or shortdesc or ""))
			)

			if not best:
				logger.warning("No valid TMDB result after ranking")
				return False, "No valid result"

			title = best.get('name', best.get('title', ''))
			backdrop_path = best.get('backdrop_path')
			backdrop = f"http://image.tmdb.org/t/p/w780{backdrop_path}"
			if not backdrop.strip():
				backdrop = f"http://image.tmdb.org/t/p/original{backdrop_path}"

			try:
				logger.info("[tmdb] selected result | title='{}' | original_title='{}' | media_type='{}' | score='{}' | backdrop_path='{}'".format(
					str(title or ""),
					str(best.get('original_name', best.get('original_title', '')) or ""),
					str(best.get('media_type', '') or ""),
					str(best_score),
					str(backdrop_path or "")
				))
			except Exception:
				pass

			if backdrop.strip():
				callInThread(self.saveBackdrop, backdrop, dwn_backdrop)
				if exists(dwn_backdrop):
					return True, f"[SUCCESS] backdrop match: {title}"

			return False, "[SKIP] No valid Result"

		finally:
			self.title_safe = old_title_safe
			self.search_year = old_search_year

	def search_tvdb(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""Download backdrop from TVDB with full verification pipeline"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()
		thetvdb_api_key = api_key or thetvdb_api

		if not thetvdb_api_key:
			return False, "No API key"

		try:
			if not exists(dwn_backdrop):
				return (False, "[ERROR] File not created")

			series_nb = -1
			chkType, fd = self.checkType(shortdesc, fulldesc)
			if not year:
				year = self._extract_year(fd)
			url_tvdbg = "https://thetvdb.com/api/GetSeries.php?seriesname={}".format(self.title_safe)
			url_read = get(url_tvdbg).text
			series_id = findall(r"<seriesid>(.*?)</seriesid>", url_read)
			series_name = findall(r"<SeriesName>(.*?)</SeriesName>", url_read)
			series_year = findall(r"<FirstAired>(19\d{2}|20\d{2})-\d{2}-\d{2}</FirstAired>", url_read)

			i = 0
			for iseries_year in series_year:
				if year == '':
					series_nb = 0
					break
				elif year == iseries_year:
					series_nb = i
					break
				i += 1

			backdrop = None
			if series_nb >= 0 and len(series_id) > series_nb and series_id[series_nb]:
				if series_name and len(series_name) > series_nb:
					# series_name_clean = self.UNAC(series_name[series_nb])
					series_name_clean = series_name[series_nb]
				else:
					series_name_clean = ""

				if self.PMATCH(self.title_safe, series_name_clean):
					if "thetvdb_api" not in globals():
						return False, "[ERROR : tvdb] API key not defined"

					url_tvdb = "https://thetvdb.com/api/{}/series/{}".format(thetvdb_api_key, series_id[series_nb])
					url_tvdb += "/{}".format(lng if "lng" in globals() and lng else "en")

					url_read = get(url_tvdb).text
					backdrop = findall(r"<backdrop>(.*?)</backdrop>", url_read)
					if backdrop and backdrop[0]:
						url_backdrop = "https://artworks.thetvdb.com/banners/{}".format(backdrop[0])
						callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)
						if exists(dwn_backdrop):
							return True, "[SUCCESS : tvdb] {} [{}-{}] => {} => {} => {}".format(
								self.title_safe, chkType, year, url_tvdbg, url_tvdb, url_backdrop
							)

					return False, "[SKIP : tvdb] {} [{}-{}] => {} (Not found)".format(
						self.title_safe, chkType, year, url_tvdbg
					)

			return False, "[SKIP : tvdb] {} [{}-{}] => {} (Not found)".format(
				self.title_safe, chkType, year, url_tvdbg
			)

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				return False, "No results found on tvdb"
			else:
				logger.error("tvdb HTTP error: " + str(e))
				return False, "HTTP error during tvdb search"

		except Exception as e:
			logger.error("tvdb search error: " + str(e))
			return False, "[ERROR : tvdb] {} => {} ({})".format(self.title_safe, url_tvdbg, str(e))

	def search_fanart(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""Download backdrop from FANART with full verification pipeline"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()
		fanart_api_key = api_key or fanart_api
		if not fanart_api_key:
			return False, "No API key"

		if not exists(dwn_backdrop):
			return (False, "[ERROR] File not created")

		url_maze = ""
		url_fanart = ""
		tvmaze_id = "-"
		chkType, fd = self.checkType(shortdesc, fulldesc)
		if not year:
			year = self._extract_year(fd)

		try:
			url_maze = "http://api.tvmaze.com/singlesearch/shows?q={}".format(self.title_safe)
			resp = get(url_maze, timeout=5)
			resp.raise_for_status()
			mj = resp.json()
			tvmaze_id = mj.get("externals", {}).get("thetvdb", "-")
		except RequestException as err:
			logger.error("TVMaze error: " + str(err))

		try:
			m_type = "tv"
			url_fanart = "https://webservice.fanart.tv/v3/{}/{}?api_key={}".format(m_type, tvmaze_id, fanart_api_key)
			resp = get(url_fanart, verify=False, timeout=5)
			resp.raise_for_status()
			fjs = resp.json()
			url = ""

			if "showbackground" in fjs and fjs["showbackground"]:
				url = fjs["showbackground"][0]["url"]
			elif "moviebackground" in fjs and fjs["moviebackground"]:
				url = fjs["moviebackground"][0]["url"]

			if url:
				callInThread(self.saveBackdrop, url, dwn_backdrop)
				msg = "[SUCCESS backdrop: fanart] {} [{}-{}] => {} => {} => {}".format(
					self.title_safe, chkType, year, url_maze, url_fanart, url
				)
				if exists(dwn_backdrop):
					return True, msg
			else:
				return False, f"[SKIP : fanart] {self.title_safe} [{chkType}-{year}] => {url_fanart} (Not found)"

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				return False, "No results found on fanart"
			else:
				logger.error("fanart HTTP error: " + str(e))
				return False, "HTTP error during fanart search"

		except Exception as e:
			logger.error("fanart search error: " + str(e))
			return False, "[ERROR : fanart] {} [{}-{}] => {} ({})".format(self.title_safe, chkType, year, url_maze, str(e))

	def search_omdb(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""OMDb NOT HAVE A backdrop Downloader using API: RETURN FALSE!!!"""
		return False, "[SKIP : omdb] {} [OMDb NOT HAVE A backdrop Downloader using API: RETURN FALSE!!!] => OMDb does not support backdrops.".format(
			title
		)

	def search_imdb(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""Download backdrop from IMDb media gallery using centralized request system"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()
		if not exists(dwn_backdrop):
			return (False, "[ERROR] File not created")

		chkType, fd = self.checkType(shortdesc, fulldesc)
		if not year:
			year = self._extract_year(fd)
		aka_info = self._extract_aka(fd)
		url_backdrop = ""
		try:
			# Extract metadata

			# Build search URL
			search_url = self._build_imdb_search_url(self.title_safe, aka_info)

			# Fetch search results
			try:
				# Make API request with retries
				retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
				adapter = HTTPAdapter(max_retries=retries)
				http = Session()
				http.mount("http://", adapter)
				http.mount("https://", adapter)
				response = http.get(search_url, headers=headers, timeout=(10, 20), verify=False)
				response.raise_for_status()
				results = self._parse_imdb_results(response.text)

				if not results and aka_info:
					fallback_url = "https://m.imdb.com/find?q={}".format(quoteEventName(self.title_safe))
					response = http.get(fallback_url, headers=headers, timeout=(10, 20), verify=False)
					response.raise_for_status()
					results = self._parse_imdb_results(response.text)

			except Exception as e:
				logger.error(f"IMDb search error: {str(e)}")
				return (False, f"[ERROR] IMDb connection: {str(e)}")

			# Find best match
			match = self._find_best_match(results, year, self.title_safe, aka_info)
			if not match or "imdb_id" not in match:
				return (False, f"[SKIP] No IMDb match for {self.title_safe}")

			# Open gallery page
			gallery_url = "https://www.imdb.com/title/{}/mediaindex/".format(match["imdb_id"])
			response = get(gallery_url, headers=headers, timeout=(10, 20), verify=False)
			response.raise_for_status()
			html = response.text.replace("&#39;", "'").replace("&quot;", '"')

			# Find backdrop image
			matches = findall(r'<img src="(https://m\.media-amazon\.com/images/.*?)"', html)
			if matches:
				url_backdrop = matches[0].split("._")[0] + ".jpg"
				callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)

				if exists(dwn_backdrop):
					return (True, "[SUCCESS] IMDb backdrop downloaded")

			return (False, f"[SKIP] Download failed for {self.title_safe}")

		except Exception as e:
			logger.error(f"IMDb backdrop processing error: {str(e)}")
			return (False, f"[ERROR] IMDb search: {str(e)}")

	def _build_imdb_search_url(self, title, aka):
		"""Construct IMDb search URL with AKA if available"""
		if aka and aka != title:
			return f"https://m.imdb.com/find?q={quoteEventName(title)}%20({quoteEventName(aka)})"
		return f"https://m.imdb.com/find?q={quoteEventName(title)}"

	def _parse_imdb_results(self, html_content):
		"""Parse IMDb search results page with IMDb ID"""
		pattern = compile(
			r'<a href="/title/(tt\d+)/".*?<img src="(.*?)".*?<span class="h3">\n(.*?)\n</span>.*?\((\d+)\)(\s\(.*?\))?(.*?)</a>',
			DOTALL
		)

		return [{
			"imdb_id": match[0],
			"url_backdrop": match[1],
			# "title": self.UNAC(match[2]),
			"title": match[2],
			"year": match[3],
			"aka": self._parse_aka_title(match[5])
		} for match in pattern.findall(html_content)]

	def search_programmetv_google(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""PROGRAMMETV backdrop Downloader not using API"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()
		if not exists(dwn_backdrop):
			return (False, "[ERROR] File not created")
		try:
			url_ptv = ""
			chkType, fd = self.checkType(shortdesc, fulldesc)

			if chkType.startswith("movie"):
				return False, f"[SKIP : programmetv-google] {self.title_safe} [{chkType}] => Skip movie title"

			url_ptv = f"site:programme-tv.net+{self.title_safe}"
			if channel and self.title_safe.find(channel.split()[0]) < 0:
				url_ptv += "+" + quoteEventName(channel)
			url_ptv = "https://www.google.com/search?q={}&tbm=isch&tbs=ift:jpg%2Cisz:m".format(url_ptv)
			default_headers = {"User-Agent": "Mozilla/5.0"}
			try:
				ff = get(url_ptv, stream=True, headers=headers, cookies={'CONSENT': 'YES+'}).text
			except NameError:
				ff = get(url_ptv, stream=True, headers=default_headers, cookies={'CONSENT': 'YES+'}).text

			ptv_id = 0
			plst = findall(r'\],\["https://www.programme-tv.net(.*?)",\d+,\d+]', ff)
			for backdroplst in plst:
				ptv_id += 1
				url_backdrop = f"https://www.programme-tv.net{backdroplst}"
				url_backdrop = sub(r"\\u003d", "=", url_backdrop)
				url_backdrop_size = findall(r'([\d]+)x([\d]+).*?([\w\.-]+).jpg', url_backdrop)
				if url_backdrop_size and url_backdrop_size[0]:
					# get_title = self.UNAC(url_backdrop_size[0][2].replace('-', ''))
					get_title = url_backdrop_size[0][2].replace('-', '')
					if self.title_safe == get_title:
						h_ori = float(url_backdrop_size[0][1])
						try:
							h_tar = 278.0
						except Exception:
							h_tar = 278.0
						ratio = h_ori / h_tar
						w_ori = float(url_backdrop_size[0][0])
						w_tar = int(w_ori / ratio)
						h_tar = int(h_tar)
						url_backdrop = sub(r'/\d+x\d+/', "/{}x{}/".format(w_tar, h_tar), url_backdrop)
						url_backdrop = sub(r'crop-from/top/', '', url_backdrop)
						callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)
						if exists(dwn_backdrop):
							return True, "[SUCCESS url_backdrop: programmetv-google] {} [{}] => Found self.title_safe : '{}' => {} => {} (initial size: {}) [{}]".format(
								self.title_safe, chkType, get_title, url_ptv, url_backdrop, url_backdrop_size, ptv_id
							)
			return False, "[SKIP : programmetv-google] {} [{}] => Not found [{}] => {}".format(
				self.title_safe, chkType, ptv_id, url_ptv
			)
		except Exception as e:
			return False, f"[ERROR : programmetv-google] {self.title_safe} [{chkType}] => {url_ptv} ({str(e)})"

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				return False, "No results found on programmetv-google"
			else:
				logger.error(f"programmetv-google HTTP error: {str(e)}")
				return False, "HTTP error during programmetv-google search"

	def search_molotov_google(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""MOLOTOV Backdrop Downloader not using API"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()
		if not exists(dwn_backdrop):
			return (False, "[ERROR] File not created")
		try:
			url_mgoo = ""
			chkType, fd = self.checkType(shortdesc, fulldesc)
			if chkType.startswith("movie"):
				return False, f"[SKIP : molotov-google] {self.title_safe} [{chkType}] => Skip movie title"

			# pchannel = self.UNAC(channel).replace(' ', '') if channel else ''
			pchannel = channel.replace(' ', '') if channel else ''
			url_mgoo = f"site:molotov.tv+{self.title_safe}"
			if channel and self.title_safe.find(channel.split()[0]) < 0:
				url_mgoo += "+" + quoteEventName(channel)
			url_mgoo = "https://www.google.com/search?q={}&tbm=isch".format(url_mgoo)

			default_headers = {"User-Agent": "Mozilla/5.0"}
			try:
				ff = get(url_mgoo, stream=True, headers=headers, cookies={'CONSENT': 'YES+'}).text
			except NameError:
				ff = get(url_mgoo, stream=True, headers=default_headers, cookies={'CONSENT': 'YES+'}).text

			plst = findall(r'https://www.molotov.tv/(.*?)"(?:.*?)?"(.*?)"', ff)
			molotov_table = [0, 0, None, None, 0]  # [title match, channel match, title, path, id]

			for pl in plst:
				get_path = "https://www.molotov.tv/{}".format(pl[0])
				# get_name = self.UNAC(pl[1])
				get_name = pl[1]
				get_title_match = findall(r'(.*?)[ ]+en[ ]+streaming', get_name)
				get_title = get_title_match[0] if get_title_match else ""
				get_channel = self.extract_channel(get_name)
				partialtitle = self.PMATCH(self.title_safe, get_title)
				partialchannel = self.PMATCH(pchannel, get_channel or '')

				if partialtitle > molotov_table[0]:
					molotov_table = [partialtitle, partialchannel, get_name, get_path, len(molotov_table)]

				if partialtitle == 100 and partialchannel == 100:
					break

			if molotov_table[0]:
				return self.handle_backdrop_result(molotov_table, headers if "headers" in locals() else default_headers, dwn_backdrop, "molotov")
			else:
				return self.handle_fallback(ff, pchannel, self.title_safe, headers if "headers" in locals() else default_headers, dwn_backdrop)

		except Exception as e:
			return False, f"[ERROR : molotov-google] {self.title_safe} => {str(e)}"

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				return False, "No results found on molotov-google"
			else:
				logger.error(f"molotov-google HTTP error: {str(e)}")
				return False, "HTTP error during molotov-google search"

	def extract_channel(self, get_name):
		get_channel = findall(r'(?:streaming|replay)?[ ]+sur[ ]+(.*?)[ ]+molotov.tv', get_name) or \
			findall(r'regarder[ ]+(.*?)[ ]+en', get_name)
		return get_channel[0].replace(' ', '') if get_channel else None
		# return self.UNAC(get_channel[0]).replace(' ', '') if get_channel else None

	def handle_backdrop_result(self, molotov_table, headers, dwn_backdrop, platform):
		ffm = get(molotov_table[3], stream=True, headers=headers).text

		pltt = findall(r'"https://fusion.molotov.tv/(.*?)/jpg" alt="(.*?)"', ffm)
		if len(pltt) > 0:
			url_backdrop = f"https://fusion.molotov.tv/{pltt[0][0]}/jpg"
			callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)
			if exists(dwn_backdrop):
				return True, f"[SUCCESS {platform}-google] Found backdrop for {self.title_safe} => {url_backdrop}"
		else:
			return False, f"[SKIP : {platform}-google] No suitable backdrop found."

	def handle_fallback(self, ff, pchannel, title_safe, headers, dwn_backdrop):
		plst = findall(r'\],\["https://(.*?)",\d+,\d+].*?"https://.*?","(.*?)"', ff)
		if plst:
			for pl in plst:
				if pl[1].startswith("Regarder"):
					url_backdrop = f"https://{pl[0]}"
					callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)
					if exists(dwn_backdrop):
						return True, f"[SUCCESS fallback] Found fallback backdrop for {title_safe} => {url_backdrop}"
		return False, "[SKIP : fallback] No suitable fallback found."

	def search_google(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""GOOGLE Backdrop Downloader not using API"""
		# self.title_safe = self.UNAC(title.replace("+", " ").strip())
		self.title_safe = title.replace("+", " ").strip()

		if not exists(dwn_backdrop):
			return (False, "[ERROR] File not created")

		try:
			chkType, fd = self.checkType(shortdesc, fulldesc)
			if not year:
				year = self._extract_year(fd)

			url_google = f'"{self.title_safe}"'
			if channel and self.title_safe.find(channel) < 0:
				url_google += f"+{quoteEventName(channel)}"
			if chkType.startswith("movie"):
				url_google += f"+{chkType[6:]}"
			if year:
				url_google += f"+{year}"

			def fetch_images(url):
				return get(url, stream=True, headers=headers, cookies={'CONSENT': 'YES+'}).text

			url_google = f"https://www.google.com/search?q={url_google}&tbm=isch&tbs=sbd:0"
			ff = fetch_images(url_google)

			backdroplst = findall(r'\],\["https://(.*?)",\d+,\d+]', ff)

			if not backdroplst:
				url_google = f"https://www.google.com/search?q={self.title_safe}&tbm=isch&tbs=ift:jpg%2Cisz:m"
				ff = fetch_images(url_google)
				backdroplst = findall(r'\],\["https://(.*?)",\d+,\d+]', ff)

			for pl in backdroplst:
				url_backdrop = f"https://{pl}"
				url_backdrop = sub(r"\\u003d", "=", url_backdrop)
				callInThread(self.saveBackdrop, url_backdrop, dwn_backdrop)
				if exists(dwn_backdrop):
					return True, f"[SUCCESS google] Found backdrop for {self.title_safe} => {url_backdrop}"

			return False, f"[SKIP : google] No backdrop found for {self.title_safe}"

		except Exception as e:
			return False, f"[ERROR : google] {self.title_safe} => {str(e)}"

		except HTTPError as e:
			if e.response is not None and e.response.status_code == 404:
				# Suppress 404 HTTP errors
				return False, "No results found on google"
			else:
				logger.error("programmetv-google HTTP error: " + str(e))
				return False, "HTTP error during google search"

	def search_elcinema(self, dwn_backdrop, title, shortdesc, fulldesc, year=None, channel=None, api_key=None):
		"""ElCinema does not support backdrops, fallback function"""
		return False, "[SKIP] No valid result"

	def saveBackdrop(self, url, filepath):
		"""Robust backdrop download with file locking"""
		if not url:
			logger.debug("Empty URL provided")
			return False

		# Create a lock for this specific file
		lock = threading.Lock()

		with lock:  # Only one thread can access this file
			# Check if file already exists and is valid
			if exists(filepath):
				try:
					with open(filepath, "rb") as f:
						if f.read(2) == b"\xFF\xD8" and getsize(filepath) > 1024:
							return True
					logger.warning("Removing corrupted file")
					remove(filepath)
				except Exception as e:
					logger.error(f"File check failed: {e}")
					if exists(filepath):
						remove(filepath)

			max_retries = 3

			for attempt in range(max_retries):
				try:
					headers = {
						"User-Agent": choice(AGENTS),
						"Accept": "image/jpeg",
						"Accept-Encoding": "gzip"
					}

					response = get(url, headers=headers, stream=True, timeout=(15, 30))
					response.raise_for_status()

					if "image/jpeg" not in response.headers.get("Content-Type", "").lower():
						raise ValueError(f"Invalid content type: {response.headers.get('Content-Type')}")

					# Write directly to final file (no .tmp)
					with open(filepath, "wb") as f:
						for chunk in response.iter_content(chunk_size=8192):
							if chunk:
								f.write(chunk)

					# Verify downloaded file
					with open(filepath, "rb") as f:
						if f.read(2) != b"\xFF\xD8" or getsize(filepath) < 1024:
							remove(filepath)
							raise ValueError("Invalid JPEG file")

					logger.debug(f"Successfully saved: {url}")
					return True

				except Exception as e:
					logger.debug(f"Attempt {attempt + 1} failed: {str(e)}")

					# Clean up partial file
					if exists(filepath):
						try:
							remove(filepath)
						except BaseException:
							pass

					sleep(2 * (attempt + 1))
					continue

			return False

	def resizeBackdrop(self, dwn_backdrop):
		try:
			img = Image.open(dwn_backdrop)
			width, height = img.size
			ratio = float(width) // float(height)
			new_height = int(isz.split(",")[1])
			new_width = int(ratio * new_height)
			try:
				rimg = img.resize((new_width, new_height), Image.LANCZOS)
			except BaseException:
				rimg = img.resize((new_width, new_height), Image.ANTIALIAS)
			img.close()
			rimg.save(dwn_backdrop)
			rimg.close()
		except Exception as e:
			print("ERROR:{}".format(e))

	def verifyBackdrop(self, dwn_backdrop):
		try:
			img = Image.open(dwn_backdrop)
			img.verify()
			if img.format == "JPEG":
				pass
			else:
				try:
					remove(dwn_backdrop)
				except BaseException:
					pass
				return False
		except Exception as e:
			print(e)
			try:
				remove(dwn_backdrop)
			except BaseException:
				pass
			return False
		return True

	def _extract_year(self, description):
		"""Helper to extract year from description"""
		try:
			year_matches = findall(r"19\d{2}|20\d{2}", description)
			return year_matches[0] if year_matches else ""
		except Exception:
			return ""

	def _extract_aka(self, description):
		"""Extract AKA titles from description"""
		try:
			aka_list = findall(r"\((.*?)\)", description)
			return next((a for a in aka_list if not a.isdigit()), None)
		except Exception:
			return None

	def _parse_aka_title(self, raw_text):
		"""Extract AKA title from result text"""
		aka_match = findall(r'aka <i>"(.*?)"</i>', raw_text)
		return aka_match[0] if aka_match else ""
		# return self.UNAC(aka_match[0]) if aka_match else ""

	def _find_best_match(self, results, target_year, original_title, aka):
		"""Find best matching result using scoring system"""
		best_match = None
		highest_score = 0

		for idx, result in enumerate(results):
			score = self._calculate_match_score(result, target_year, original_title, aka)
			if score > highest_score:
				highest_score = score
				best_match = {
					'url_backdrop': self._format_url_backdrop(result['backdrop']),
					'title': result['title'],
					'year': result['year'],
					'index': idx
				}

		return best_match if highest_score > 50 else None

	def _calculate_match_score(self, result, target_year, original_title, aka):
		"""Calculate score based on title similarity and year proximity"""
		score = 0
		result_title = result.get("title", "").lower()
		result_year = result.get("year")

		# Normalize original title (no year, lowercase)
		clean_title = sub(r"\b\d{4}\b", "", original_title.lower()).strip()

		if clean_title in result_title:
			score += 50

		if aka and aka.lower() in result_title:
			score += 30

		if target_year and result_year:
			if str(result_year) == str(target_year):
				score += 20
			elif abs(int(result_year) - int(target_year)) <= 1:
				score += 10

		return score

	def _format_url_backdrop(self, url):
		"""Ensure backdrop URL is correctly formatted"""
		if not url:
			return ""

		url = url.replace("\\/", "/")

		if url.startswith("//"):
			return "https:" + url

		return url

	def checkType(self, shortdesc, fulldesc):
		if shortdesc and shortdesc != '':
			fd = shortdesc.splitlines()[0]
		elif fulldesc and fulldesc != '':
			fd = fulldesc.splitlines()[0]
		else:
			fd = ''

		text = "{} {}".format(shortdesc or "", fulldesc or "").lower()

		tv_patterns = [
			r'\bseason\s*\d+\b',
			r'\bs\d+\s*e\d+\b',
			r'\bepisode\s*\d+\b',
			r'\bepisodio\s*\d+\b',
			r'\bstagione\s*\d+\b',
			r'\bep\.?\s*\d+\b',
			r'\bج\s*\d+\b',
			r'\bح\s*\d+\b',
			r'\bجزء\s*\d+\b',
			r'\bحلقة\s*\d+\b',
			r'\bالموسم\s*\d+\b',
			r'\bالحلقة\s*\d+\b',
			r'\bodc\.?\s*\d+\b',
			r'\bodcinek\s*\d+\b',
		]

		movie_patterns = [
			r'\bfilm\b',
			r'\bmovie\b',
			r'\bpel[íi]cula\b',
			r'\bcinema\b',
			r'\bcin[eé]ma\b',
			r'\bфильм\b',
			r'\bkino\b',
			r'\bfilma\b',
		]

		global srch
		srch = "multi"

		for pattern in tv_patterns:
			if compile(pattern, IGNORECASE).search(text):
				srch = "tv"
				return srch, fd

		for pattern in movie_patterns:
			if compile(pattern, IGNORECASE).search(text):
				srch = "movie"
				return srch, fd

		return srch, fd

	r"""
	# def checkType(self, shortdesc, fulldesc):
		# # Estrazione della prima riga della descrizione
		# fd = ""
		# if shortdesc and shortdesc.strip():
			# fd = shortdesc.splitlines()[0].strip()
		# elif fulldesc and fulldesc.strip():
			# fd = fulldesc.splitlines()[0].strip()

		# # Normalizzazione del testo per la comparazione
		# clean_text = self.UNAC(fd).lower()

		# # Liste di keywords aggiornate (2024)
		# movie_keywords = {
			# "film", "movie", "cine", "cinema", "película", "ταινία",
			# "фильм", "кино", "filma", "pelicula", "flim", "κινηματογράφος"
		# }

		# tv_keywords = {
			# "serie", "series", "episodio", "episode", "season", "staffel",
			# "doku", "show", "soap", "sitcom", "reality", "т/с", "м/с",
			# "сезон", "сериал", "serien", "épisode", "série", "folge"
		# }

		# # Sistemi di punteggio avanzato
		# movie_score = sum(20 if word in clean_text else 0 for word in movie_keywords)
		# tv_score = sum(15 if word in clean_text else 0 for word in tv_keywords)

		# # Rilevamento di pattern specifici
		# patterns = {
			# "movie": [
				# r"\b(?:19|20)\d{2}\b",  # Anno nel titolo
				# r"\bdirector's cut\b",
				# r"\bruntime:\s*\d+h?\s*\d+m\b"
			# ],
			# "tv": [
				# r"\bseason\s*\d+\b",
				# r"\bs\d+\s*e\d+\b",
				# r"\bepisodio\s*\d+\b",
				# r"\bstagione\s*\d+\b"
			# ]
		# }

		# # Aggiunta punti per pattern regex
		# for pattern in patterns["movie"]:
			# if search(pattern, fd, flags=I):
				# movie_score += 30

		# for pattern in patterns["tv"]:
			# if search(pattern, fd, flags=I):
				# tv_score += 25

		# # Soglie dinamiche basate sulla lunghezza del testo
		# threshold = max(40, len(clean_text) // 3)

		# # Determinazione finale
		# if movie_score > tv_score and movie_score > threshold:
			# srch = "movie"
		# elif tv_score > movie_score and tv_score > threshold:
			# srch = "tv"
		# else:

			# srch = "multi"

		# return srch, fd
	"""

	def UNAC(self, string):
		string = normalize('NFD', string)
		string = sub(r"u0026", "&", string)
		string = sub(r"u003d", "=", string)
		string = sub(r'[\u0300-\u036f]', '', string)  # Remove accents
		string = sub(r"[,!?\.\"]", ' ', string)       # Replace punctuation with space
		string = sub(r'\s+', ' ', string)             # Collapse multiple spaces
		return string.strip()

	def PMATCH(self, textA, textB):
		if not textB or textB == '' or not textA or textA == '':
			return 0
		if textA == textB:
			return 100
		if textA.replace(" ", "") == textB.replace(" ", ""):
			return 100
		if len(textA) > len(textB):
			lId = len(textA.replace(" ", ""))
		else:
			lId = len(textB.replace(" ", ""))
		textA = textA.split()
		cId = 0
		for id in textA:
			if id in textB:
				cId += len(id)
		cId = 100 * cId // lId
		return cId

	"""
	def PMATCH(self, textA, textB):
		if not textA or not textB:
			return 0
		if textA == textB or textA.replace(" ", "") == textB.replace(" ", ""):
			return 100

		textA = textA.split()
		common_chars = sum(len(word) for word in textA if word in textB)
		max_length = max(len(textA.replace(" ", "")), len(textB.replace(" ", "")))
		match_percentage = (100 * common_chars) // max_length
		return match_percentage
	"""
