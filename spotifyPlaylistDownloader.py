import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from pytube import Search, YouTube

import os
import subprocess
from threading import Thread

from pathvalidate import sanitize_filepath

from configparser import ConfigParser

config = ConfigParser()

config['CLIENT'] = {}
config['CLIENT']['secret'] = 'acb150396d934d25bde0c63992286593'
config['CLIENT']['id'] = '90524a6b28a649f2b9af403237ecf98b'

config['FILE'] = {}
config['FILE']['extension'] = '.mp3'

config['SEARCH'] = {}
config['SEARCH']['skip_downloaded_tracks'] = '1'
config['SEARCH']['include_artists_in_search'] = '1'
config['SEARCH']['min_seconds'] = '-10'
config['SEARCH']['max_seconds'] = '10'
config['SEARCH']['max_searches_tries'] = '100'

configPath = os.path.splitext(__file__)[0]+'.ini'

if not os.path.exists(configPath):
	with open(configPath, 'w') as f:
		f.write(
f"""; not working? try those instructions below:
; https://developer.spotify.com/dashboard -> create app -> name anything you want
; -> Redirect URIs = https://localhost:8888/callback (the port doesn't matter)
; -> get client secret and client id
; -> paste them to their corresponding variables
; still not working? maybe youtube, spotify or the modules changed something and now it won't work. Look for someone to update the code and my apologies :/
[CLIENT]
secret = {config['CLIENT']['secret']}
id = {config['CLIENT']['id']}

[FILE]
; which extension to convert to
extension = {config['FILE']['extension']}

[SEARCH]
; if a track on spotify is 5:00 but on youtube is 3:00 this is useful. It's also useful if the search finds a completly wrong video with unrelated time
; recommended to be true
skip_downloaded_tracks = {config['SEARCH']['skip_downloaded_tracks']}

; recommended to be true; Self explanatory, basically search on youtube would be "track_name artist1, artist2, artist3, artist4[...]"
include_artists_in_search = {config['SEARCH']['include_artists_in_search']}

; put 1 if no check (recommended to change depending of the playlist, some musics might have a extended version on spotify/youtube)
min_seconds = {config['SEARCH']['min_seconds']}

; put -1 if no check (same recommendation of above)
max_seconds = {config['SEARCH']['max_seconds']}

; DEFAULT: {config['SEARCH']['max_searches_tries']}; Amount of searches tries allowed. If the track is not found on youtube it will be skipped
max_searches_tries = {config['SEARCH']['max_searches_tries']}
""")
else:
	config.read(configPath)

CLIENT_SECRET = config['CLIENT']['secret']
CLIENT_ID = config['CLIENT']['id']

FILE_EXTENSION = config['FILE']['extension']

SKIP_DOWNLOADED_TRACKS = bool(int(config['SEARCH']['skip_downloaded_tracks']))
INCLUDE_ARTISTS_IN_SEARCH = bool(int(config['SEARCH']['include_artists_in_search']))
MIN_SECONDS = int(config['SEARCH']['min_seconds'])
MAX_SECONDS = int(config['SEARCH']['max_seconds'])
MAX_SEARCHES_TRIES = int(config['SEARCH']['max_searches_tries'])

spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(CLIENT_ID, CLIENT_SECRET))

class Time:
	def __init__(self, time: float | int, timeType: str='seconds'):
		"""
		time is the time number itself, timeType is the type of this variable

		type could be: 'seconds', 'milliseconds', 'minutes', 'hours'
		"""

		self.milliseconds = 0
		self.seconds = 0
		self.minutes = 0
		self.hours = 0

		if timeType == 'seconds':
			self.seconds = time
		elif timeType == 'milliseconds':
			self.milliseconds = time
		elif timeType == 'minutes':
			self.minutes = time
		elif timeType == 'hours':
			self.hours = time

		self.parseTime()
	
	def parseTime(self):
		newSeconds = self.milliseconds//1000
		self.milliseconds -= 1000*newSeconds
		
		self.seconds += newSeconds
		
		newMinutes = self.seconds//60
		self.seconds -= 60 * newMinutes
		
		self.minutes += newMinutes
		
		newHours = self.minutes//60
		self.minutes -= 60 * newHours
		
		self.hours += newHours

	def representWithLeftZero(self, time: int|float):
		if time < 10:
			repr = f'0{time}'
		else:
			repr = str(time)
		
		return repr

	def representSecondsWithMilliseconds(self):
		out = f'{self.representWithLeftZero(self.seconds)}'
		
		if self.milliseconds:
			return f'{out}.{self.representWithLeftZero(self.milliseconds)}'
		
		return out

	def toSeconds(self):
		return self.hours*3600+self.minutes*60+self.seconds+self.milliseconds/1000

	def __repr__(self):
		minutesRepr = self.representWithLeftZero(self.minutes)

		if self.hours:
			return f'{self.representWithLeftZero(self.hours)}:{minutesRepr}:{self.representSecondsWithMilliseconds()}'
		elif self.minutes:
			return f'{minutesRepr}:{self.representSecondsWithMilliseconds()}'
		else:
			return self.representSecondsWithMilliseconds()

class Track:
	def __init__(self, name: str, artists: str, duration_ms: float):
		self.name = name
		self.artists = artists
		
		self.duration = Time(duration_ms, 'milliseconds')
		
		self.duration.seconds = round(self.duration.seconds+self.duration.milliseconds/1000)
		self.duration.milliseconds = 0
		self.duration.parseTime()

class Playlist:
	def __init__(self, playlistId: str):
		self.name: str = spotify.playlist(playlistId, 'name')['name']

		playlistJSON: dict = spotify.playlist_tracks(playlistId)
		self.total: int = playlistJSON['total']

		self.tracks: list[Track] = []
		while len(self.tracks) != self.total:
			for item in playlistJSON['items']:
				artists = ''
				for artist in item['track']['artists']:
					artists += f'{artist["name"]}, '
				artists = artists[:-2]

				self.tracks.append(Track(item['track']['name'], artists, item['track']['duration_ms']))
			
			playlistJSON: dict = spotify.next(playlistJSON)

def convertFileSilently(fileName: str, newFileName: str, deleteOriginalFile: bool=False):
	subprocess.run([
		'ffmpeg',
		'-i', fileName,
		'-hide_banner',
		'-loglevel', 'error',
		newFileName,
	])

	if deleteOriginalFile:
		os.remove(fileName)

def downloadPlaylistTracks(playlistId: str, outputPath: str):
	try:
		playlist = Playlist(playlistId)
	except spotipy.exceptions.SpotifyException:
		print('ERROR: Playlist not found(if this is a private playlist, make it public)')
		quit()

	playlistPath = sanitize_filepath(os.path.join(outputPath, playlist.name))
	if not os.path.exists(playlistPath): os.makedirs(playlistPath, exist_ok=True)

	conversionThreads = []
	tracksDownloaded = 0
	video = None
	for track in playlist.tracks:
		if SKIP_DOWNLOADED_TRACKS and os.path.exists(os.path.join(playlistPath, track.name+FILE_EXTENSION)):
			print(f'Skipping \"{track.name}\" since it is already downloaded')
			tracksDownloaded += 1
			continue
		
		print(f'Playlist: {playlist.name}\nDownloading: {track.name}\nArtists: {track.artists}\nDuration: {track.duration}')
		
		if INCLUDE_ARTISTS_IN_SEARCH:
			search = Search(track.name + ' ' + track.artists)
		else:
			search = Search(track.name)
		

		resultIndex = 0
		resultOffset = 0
		while True:
			if len(search.results) == resultIndex:
				resultOffset = resultIndex
				search.get_next_results()

			realResultIndex = resultIndex - resultOffset

			video = YouTube(search.results[realResultIndex].watch_url, use_oauth=True, allow_oauth_cache=True)

			if resultIndex >= MAX_SEARCHES_TRIES:
				print(f'WARNING: could not find {track.name} on YouTube, see missedTracks.txt for all the tracks that could not be found')
				
				with open('missedTracks.txt', 'a') as f:
					f.write(f'{track.name} - {track.artists} - {track.duration}\n')
				
				break

			if MIN_SECONDS != 1 and video.length < MIN_SECONDS+track.duration.toSeconds():
				print(f'skipping search \"{video.title}\" #{resultIndex} since length is below allowed')
				resultIndex += 1
				continue
		
			if MAX_SECONDS != -1 and video.length > MAX_SECONDS+track.duration.toSeconds():
				print(f'skipping search \"{video.title}\" #{resultIndex} since length is above allowed')
				resultIndex += 1
				continue
			
			print('Track found!')
			video = video.streams.first()
			video.download(playlistPath)
			videoName = video.default_filename
			
			conversionThreads.append(Thread(target=convertFileSilently, args=(
				os.path.join(playlistPath, videoName),
				os.path.join( playlistPath, sanitize_filepath(track.name)+FILE_EXTENSION ),
				True
			)))
			conversionThreads[-1].start()

			tracksDownloaded += 1
			print(f'Done {tracksDownloaded}/{playlist.total}')
			break

	i = 0
	while conversionThreads:
		if not conversionThreads[i].is_alive():
			conversionThreads.pop(i)
			i -= 1
		
		if len(conversionThreads)-1 == i:
			conversionThreads[i].join()
			break

		i += 1

if __name__ == '__main__':
	import sys
	
	if len(sys.argv) >= 2:
		playlistId = sys.argv[1]
	else:
		print('NOTE: you can pass those arguments instead of using input requesting, for example: python spotifyPlaylistDownloader "myPlaylistId" "myOutputPath"')
		playlistId = input("Playlist id: ")
	
	if len(sys.argv) >= 3:
		outputPath = sys.argv[2]
	else:
		outputPath = input("Output path(blank if actual directory. Playlist directory name does not need to be included here): ")

	downloadPlaylistTracks(playlistId, outputPath)

	print(f"Finished downloading tracks.\nRemember: some might not be the same as the spotify version since it might not be on youtube with a similar name or might not even be in it")
	input('press ENTER to continue...')