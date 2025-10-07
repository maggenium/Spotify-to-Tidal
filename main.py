import requests
# Patch requests.get and requests.post to always use a timeout of 20 seconds if not specified
_original_get = requests.get
_original_post = requests.post

def _get_with_timeout(*args, **kwargs):
    if "timeout" not in kwargs:
        kwargs["timeout"] = 20
    return _original_get(*args, **kwargs)

def _post_with_timeout(*args, **kwargs):
    if "timeout" not in kwargs:
        kwargs["timeout"] = 20
    return _original_post(*args, **kwargs)

requests.get = _get_with_timeout
requests.post = _post_with_timeout
import json
from dotenv import load_dotenv
import os
import random
import webbrowser
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import base64
import hashlib
import time
import platform

load_dotenv()

# Spotify global variables
REDIRECT_URI = "http://127.0.0.1:8000/callback"
state = None # to store the state parameter for CSRF protection
SPOTIFY_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_RETRY_AFTER = 5  # default retry time for Spotify rate limiting

# Tidal global variables
TIDAL_REDIRECT_URI = "http://127.0.0.1:3000/callback"
TIDAL_BASE_URL = "https://openapi.tidal.com/v2"
randomOctetSequence = os.urandom(32)
codeVerifier = base64.urlsafe_b64encode(randomOctetSequence).decode("utf-8").rstrip("=")

## SPOTIFY

# Handles the redirect from Spotify after user authorization
class SpotifyAuthHandler(BaseHTTPRequestHandler):
    # overwrites do_GET method to handle the redirect from Spotify
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)
        if "code" in params and "state" in params:
            code = params["code"][0]
            returned_state = params["state"][0]
            if returned_state == state:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Spotify authorization successful!</h1>You can close this window and return to console.</body></html>")
                #print(f"Handler got authorization code: {code}")
                self.server.code = code
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Possible CSRF attack.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code or state parameter.")
            
    def log_message(self, format, *args):
        pass  # Suppress logging to console

# Opens the browser to let the user authorize the app
# Returns the authorization code or None if the user did not authorize
def spotifyGetUserAuthorizationCode():
    # open the browser to let the user authorize the app
    global state
    url = "https://accounts.spotify.com/authorize"
    scope = "playlist-read-private user-library-read"
    state = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
    params = {
        "client_id": os.getenv("SPOTIFY_CLIENT_ID"),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "scope": scope,
    }
    auth_url = f"{url}?{urllib.parse.urlencode(params)}"
    webbrowser.open(auth_url)    
     # Start local server to catch the redirect
    server = HTTPServer(("127.0.0.1", 8000), SpotifyAuthHandler)
    server.handle_request()  # Handles a single request, then exits
    return getattr(server, "code", None)

# Sends a request to Spotify to get an access token using the authorization code
# Returns the access token (else None)
def spotifyGetAccessToken(code):
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    clientIDnSecretStringBytes = f"{os.getenv('SPOTIFY_CLIENT_ID')}:{os.getenv('SPOTIFY_CLIENT_SECRET')}".encode("ascii")
    encodedClientIDnSecret = base64.b64encode(clientIDnSecretStringBytes).decode("ascii")
    headers = {
        "Authorization": f"Basic {encodedClientIDnSecret}",
        "Content-Type": "application/x-www-form-urlencoded"
        }
    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        token = response.json()["access_token"]
        #print("Token retrieved successfully. Response:")
        #print(json.dumps(response.json(), indent=2))
        return token
    else:
        print("Failed to retrieve Spotify access token. Error status code: ", response.status_code)
    return None

# Retrieves the user ID from Spotify using the access token
def spotifyGetUserID(token):
    url = f"{SPOTIFY_BASE_URL}/me"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["id"]
    else:
        print("Failed to retrieve user ID:", response.status_code)
        return None
    
# Retrieves all playlists of the signed in user from Spotify using the access token
# Returns a generator that yields playlists
def spotifyGetPlaylists(token):
    limit = 50
    offset = 0
    total = -1
    url = f"{SPOTIFY_BASE_URL}/me/playlists"
    headers = {"Authorization": f"Bearer {token}"}
    while (total == -1 or offset < total):
        params = {
            "limit": limit,
            "offset": offset
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            playlists = response.json()
            total = playlists["total"]
            offset += limit
            yield from playlists["items"]
        elif response.status_code == 429:
            waitTime = SPOTIFY_RETRY_AFTER
            print(f"Spotify rate limit exceeded. Retrying after {waitTime} seconds...")
            time.sleep(waitTime)
            return spotifyGetPlaylists(token)  # Retry the request
        else:
            print("Failed to retrieve playlists:", response.status_code)
            break
        
# Retrieves all tracks of a specific playlist from Spotify using the access token
# Returns a generator that yields tracks
def spotifyGetSpecificPlaylistTracks(token, playlistID):
    limit = 50
    offset = 0
    total = -1
    url = f"{SPOTIFY_BASE_URL}/playlists/{playlistID}/tracks"
    headers = {"Authorization": f"Bearer {token}"}
    while (total == -1 or offset < total):
        params = {
            "limit": limit,
            "offset": offset
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            total = data["total"]
            offset += limit
            yield from data["items"]
        elif response.status_code == 429:
            waitTime = SPOTIFY_RETRY_AFTER
            print(f"Spotify rate limit exceeded. Retrying after {waitTime} seconds...")
            time.sleep(waitTime)
            return spotifyGetSpecificPlaylistTracks(token, playlistID)
        else:
            print("Failed to retrieve playlist tracks:", response.status_code)
            print(f"Playlist: {playlistID}")
            break
    if total == 0:
        print(f"No tracks found in playlist {playlistID}.")
        
# def printPlaylist(token, playlists, search):
#     searchlist = [playlist for playlist in playlists if search.lower() in playlist["name"].lower()]
#     for item in searchlist:
#         tracks = list(spotifyGetSpecificPlaylistTracks(token, item["id"]))
#         print(f"App received tracks from playlist {item['name']}: {len(tracks)} tracks")
#         #print(json.dumps(tracks[0], indent=2))
#         for track in tracks:
#             print(f"{track['track']['name']} by {track['track']['artists'][0]['name']}")

def spotifyGetUserSavedTracks(token):
    limit = 50
    offset = 0
    total = -1
    url = f"{SPOTIFY_BASE_URL}/me/tracks"
    headers = {"Authorization": f"Bearer {token}"}
    while (total == -1 or offset < total):
        params = {
            "limit": limit,
            "offset": offset
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            total = data["total"]
            offset += limit
            yield from data["items"]
        elif response.status_code == 429:
            waitTime = SPOTIFY_RETRY_AFTER
            print(f"Spotify rate limit exceeded. Retrying after {waitTime} seconds...")
            time.sleep(waitTime)
            return spotifyGetUserSavedTracks(token)
        else:
            print("Failed to retrieve user saved tracks:", response.status_code)
            break
    if total == 0:
        print(f"No user saved tracks found.")

# Saves the playlists with tracks to a JSON file
# Each playlist is a dictionary with the playlist name and a list of tracks
# Returns None
def savePlaylistsToJson(token, filename, playlists):
    playlistsWithTracks = []
    for playlist in playlists:
        tracks = list(spotifyGetSpecificPlaylistTracks(token, playlist["id"]))
        print(f"App received tracks from playlist {playlist['name']}: {len(tracks)} tracks")
        playlistsWithTracks.append({
            "playlist_name": playlist["name"],
            "tracks": [
                {
                    "track_name": track["track"]["name"],
                    "artist_name": track["track"]["artists"]
                }
                for track in tracks if track.get("track") # if tracks is not None
            ]
        })
    userSavedTracks = list(spotifyGetUserSavedTracks(token))
    if userSavedTracks:
        tracks = userSavedTracks
        print(f"App received user's saved tracks: {len(tracks)} tracks")
        playlistsWithTracks.append({
            "playlist_name": "Spotify Liked Songs",
            "tracks": [
                {
                    "track_name": track["track"]["name"],
                    "artist_name": track["track"]["artists"]
                }
                for track in tracks if track.get("track") # if tracks is not None
            ]
        })
    with open(f"{filename}.json", "w") as f:
        json.dump(playlistsWithTracks, f, indent=2)
    print(f"Playlists saved to {filename}.json")

## TIDAL

# Handles the redirect from TIDAL after user authorization
class TidalAuthHandler(BaseHTTPRequestHandler):
    # overwrites do_GET method to handle the redirect from TIDAL
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)
        if "code" in params and "state" in params:
            code = params["code"][0]
            returned_state = params["state"][0]
            if returned_state == state:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Tidal authorization successful!</h1>You can close this window.</body></html>")
                #print(f"Handler got authorization code: {code}")
                self.server.code = code
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Possible CSRF attack.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code or state parameter.")
        
    def log_message(self, format, *args):
        pass  # Suppress logging to console

# Opens the browser to let the user authorize the app
# Returns the authorization code or None if the user did not authorize
def tidalGetUserAuthorizationCode():
    # open the browser to let the user authorize the app
    global state
    url = "https://login.tidal.com/authorize"
    scope = "user.read search.read playlists.write playlists.read"
    state = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
    codeChallengeS256Digest = hashlib.sha256(codeVerifier.encode("utf-8")).digest()
    codeChallenge = base64.urlsafe_b64encode(codeChallengeS256Digest).decode("utf-8").rstrip("=")
    params = {
        "response_type": "code",
        "client_id": os.getenv("TIDAL_CLIENT_ID"),
        "redirect_uri": TIDAL_REDIRECT_URI,
        "scope": scope,
        "code_challenge_method": "S256",
        "code_challenge": codeChallenge,
        "state": state
    }
    auth_url = f"{url}?{urllib.parse.urlencode(params)}"
    webbrowser.open(auth_url)
    print("Please authorize the app in your browser.")
    
     # Start local server to catch the redirect
    server = HTTPServer(("127.0.0.1", 3000), TidalAuthHandler)
    server.handle_request()  # Handles a single request, then exits
    return getattr(server, "code", None)

# Sends a request to TIDAL to get an access token using the authorization code
# Returns the access token and user ID in a list (else None)
def tidalGetAccessToken(code):
    url = "https://auth.tidal.com/v1/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("TIDAL_CLIENT_ID"),
        "code": code,
        "redirect_uri": TIDAL_REDIRECT_URI,
        "code_verifier": codeVerifier
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        token = response.json()["access_token"]
        userID = response.json()["user_id"]
        print("Token retrieved successfully.")
        # print(json.dumps(response.json(), indent=2))
        return token, userID
    else:
        print("Failed to retrieve token:", response.status_code)

# Sends a request to TIDAL to search for a track
# Returns all data of track search result (else None)
def tidalSearchForTrack(token, trackName, artistNames):
    query = urllib.parse.quote(f"{trackName} {' '.join(artistNames)}").replace("/", "%2F")
    # query = f"{trackName} {' '.join(artistNames)}".replace(" ", "%20").replace("'", "%27").replace("/", "%2F")
    url = f"{TIDAL_BASE_URL}/searchResults/{query}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "countryCode": "DE",
        "explicitFilter": "include",
        "include": ["tracks"]
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        if data:
            return data
        else:
            print(f"Critical search failure for '{query}'")
            print("No data returned.")
            return None
    elif response.status_code == 429:
        retryAfter = response.headers.get("Retry-After")
        if retryAfter:
            waitTime = int(retryAfter)
        else:
            waitTime = 5
        waitTime += 1
        print(f"Rate limit exceeded. Retrying after {waitTime} seconds...")
        time.sleep(waitTime)
        return tidalSearchForTrack(token, trackName, artistNames)
    else:
        print("Failed to search for track: ", response.status_code)
        print(json.dumps(response.json(), indent=2))
    return None

# Creates a TIDAL Playlist
# Returns the playlist ID if successful (else None)
def tidalCreatePlaylist(token, playlistName):
    url = f"{TIDAL_BASE_URL}/playlists"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "data" : {
            "attributes": {
                "accessType": "PUBLIC",
                "description": "Created with Spotify to Tidal migration script",
                "name": playlistName
            },
            "type": "playlists"
        }
    }
    response = requests.post(url, headers=headers, json=data) #send as data instead of json?
    if response.status_code == 201:
        print(f"Playlist '{playlistName}' created successfully.")
        return response.json()["data"]["id"]
    else:
        print("Failed to create playlist:", response.status_code)
        print(json.dumps(response.json(), indent=2))

# Fills a TIDAL playlist with tracks
# Returns None
def tidalFillPlaylistWithTracks(token, playlistId, trackIdList, playlistName=None):
    print(f"Adding {len(trackIdList)} tracks...")
    if trackIdList:
        url = f"{TIDAL_BASE_URL}/playlists/{playlistId}/relationships/items"
        headers = {"Authorization": f"Bearer {token}"}
        trackIdListSplit = [trackIdList[i:i + 20] for i in range(0, len(trackIdList), 20)]  # Split into chunks of 20
        for splitList in trackIdListSplit:
            data = {
                "data": [
                    {
                        "id": trackId,
                        "type": "tracks"
                    } for trackId in splitList
                ]
            }
            time.sleep(1) # to avoid rate limiting
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 201:
                if playlistName:
                    print(f"Tracks added to playlist {playlistName} successfully.")
                else:
                    print(f"Tracks added to playlist {playlistId} successfully.")
            else:
                print("Failed to add tracks to playlist:", response.status_code)
                print(json.dumps(response.json(), indent=2))
    else:
        print("No tracks found. 0 tracks were added.")


## MAIN EXECUTION
if __name__ == "__main__":
    
    input("Welcome to Spotify to TIDAL. Press any key to continue to Spotify login in browser: ")
    # Log in to Spotify and get playlists
    spotifyAuthorizationCode = spotifyGetUserAuthorizationCode()
    while(spotifyAuthorizationCode == None):
        cmdinput = input("Spotify authorization failed. Do you want to try again? (y/n)")
        match cmdinput:
            case "n" | "N":
                print("Exiting.")
                exit()
            case _:
                spotifyAuthorizationCode = spotifyGetUserAuthorizationCode()
            
    spotifyAccessToken = spotifyGetAccessToken(spotifyAuthorizationCode)
    if spotifyAccessToken == None:
        print("Spotify authorization failed. Exiting.")
        exit()

    print("Spotify login successful. Loading playlists (this may take a while)...")
    spotifyPlaylists = list(spotifyGetPlaylists(spotifyAccessToken))
    playlistNames = [playlist["name"] for playlist in spotifyPlaylists]
    print(f"App received the following playlists from Spotify:")
    for i in range(len(playlistNames)):
        print(f"{i} - {playlistNames[i]}")

    cmdinput = input("Do you want to import all playlists (1) or specific ones (2)?: ")
    whitelist = []
    blacklist = []
    match cmdinput:
        case "2": # select specific playlists
            cmdinput = input("Do you want to include (1) or exclude (2) specific playlists?: ")
            match cmdinput:
                case "1": # whitelist playlists
                    cmdinput = input("Enter the index numbers of the playlists you want to include (comma separated):\n")
                    whitelist = sorted(set(int(x.strip()) for x in cmdinput.split(",") if x.strip().isdigit() and int(x.strip()) < len(playlistNames)))
                case "2": # blacklist playlists
                    cmdinput = input("Enter the index numbers of the playlists you want to exclude (comma separated):\n")
                    blacklist = sorted(set(int(x.strip()) for x in cmdinput.split(",") if x.strip().isdigit() and int(x.strip()) < len(playlistNames)))
        case _:
            pass
            #continue, select all playlists default
            
    if (whitelist):
        print("\nThe following playlists have been selected for import:")
        for i in range(len(playlistNames)):
            if i in whitelist:
                print(f"{i} - {playlistNames[i]}")
        playlists = [playlist for i, playlist in enumerate(spotifyPlaylists) if i in whitelist]
    elif (blacklist):
        print("\nThe following playlists have been excluded from import:")
        for i in range(len(playlistNames)):
            if i in blacklist:
                print(f"{i} - {playlistNames[i]}")
                
        print("\nThe following playlists will be imported:")
        for i in range(len(playlistNames)):
            if i not in blacklist:
                print(f"{i} - {playlistNames[i]}")
        playlists = [playlist for i, playlist in enumerate(spotifyPlaylists) if i not in blacklist]
    else:
        print("\nAll playlists will be transferred.")
        playlists = spotifyPlaylists

    cmdinput = input("Continue? (y/n): ")
    if cmdinput.lower() != "y":
        print("Exiting.")
        exit()
    print("Loading tracks from Spotify playlists (this may take a while)...")
    savePlaylistsToJson(spotifyAccessToken, "playlists3", playlists)
    
    ## Load playlists from file
    loadedPlaylists = []
    with open("playlists3.json", "r") as f:
        loadedPlaylists = json.load(f)
    
    ## Log in to TIDAL, create playlists and fill them with tracks
    input("Press any key to continue to TIDAL login in browser: ")
    tidalAuthorizationCode = tidalGetUserAuthorizationCode()
    if tidalAuthorizationCode == None:
        print("TIDAL authorization failed. Exiting.")
        exit()
    [tidalAccessToken, userID] = tidalGetAccessToken(tidalAuthorizationCode)
    cmdinput = input("TIDAL login successful. Do you want to start transferring playlists now? (y/n): ")
    if cmdinput.lower() != "y":
        print("Exiting.")
        exit()
    for seconds in range(5, 0, -1):
        print(f"Starting transfer in {seconds}...", end="\r")
        time.sleep(1)
    abortOperation = False
    tracksNotFound = False
    for playlist in loadedPlaylists:
        tidalPlaylistId = tidalCreatePlaylist(tidalAccessToken, playlist["playlist_name"])
        print(f"Created Tidal playlist: {playlist['playlist_name']}")
        
        returnedTrackIdList = []
        for track in playlist["tracks"]:
            searchResult = tidalSearchForTrack(tidalAccessToken, 
                                               track["track_name"],
                                               [artist["name"] for artist in track["artist_name"]])
            if searchResult:
                if searchResult["data"]["relationships"]["tracks"]["data"]:
                    returnedTrackIdList.append(searchResult["data"]["relationships"]["tracks"]["data"][0]["id"])
                else:
                    print(f"No results found for '{track['track_name']}' by {', '.join([artist['name'] for artist in track['artist_name']])}")
                    # print("Search result:")
                    # print(json.dumps(searchResult, indent=2))
                    with open("tidal_not_found.txt", "a", encoding="utf-8") as f:
                        f.write(f"In playlist {playlist["playlist_name"]}: {track['track_name']} by {', '.join([artist['name'] for artist in track['artist_name']])}\n")
                    tracksNotFound = True
            else:
                print("Search failed for track:", track["track_name"])
                print("Playlist population aborted for playlist:", playlist["playlist_name"])
                abortOperation = True
                break
        tidalFillPlaylistWithTracks(tidalAccessToken, tidalPlaylistId, returnedTrackIdList, playlist["playlist_name"])
        if abortOperation:
            print("Aborting operation due to fundamental search error.")
            exit()
    print("Tidal playlist population completed.")
    if tracksNotFound:
        cmdinput = input("Some tracks were not found. Do you want to open the tidal_not_found.txt file? (y/n): ")
        if cmdinput.lower() == "y":
            if platform.system() == "Windows":
                os.startfile("tidal_not_found.txt")
            elif platform.system() == "Darwin":  # macOS
                os.system(f"open tidal_not_found.txt")
            elif platform.system() == "Linux":
                os.system(f"xdg-open tidal_not_found.txt")
        exit()
    input("Press Enter to exit.")
    
    
    # - Welcome message and asking the user to log in to Spotify to authorize the app
    # - (Enter to continue and redirect to Spotify login in browser)
    # - After login, ask user to close browser tab and return to console
    # - print out all playlists, INCLUDING LIKED SONGS, with index numbers
    # - Ask user if they want to migrate all playlists or only specific ones
    # - Ask if they want to include or exclude specific playlists
    # - Tell them to enter the index numbers of the playlists they want to include
    #   or exclude in migration (comma separated)
    # - Ask user to log in to Tidal to authorize the app
    # - (Enter to continue and redirect to Tidal login in browser)
    # - After login, ask user to close browser tab and return to console
    # - After short delay, start migration and print progress in console
    # - Print out a summary of the migration (number of playlists, number of tracks, number of tracks not found)
    # - Ask if they want to open the tidal_not_found.txt file in default text editor
    # - Tell them to press Enter to exit the app
    
    
    
    ## FURTHER DEVELOPMENT
    # + Make it user friendly (e.g. command line arguments)
    # + Import Spotify liked songs
    # - Give option to not import liked songs
    # - Use just first 2 artists for track search (to avoid issues with long artist lists)
    # - Add 429 too many requests handling for every request
    # - Add error handling
    # - Add blacklist/whitelist functionality
    # - Ask if the user wants to create a new playlist or fill an existing one if playlist already exists
    # - Make a UI
    #   - add a progress bar
    #   - make track search more verbose