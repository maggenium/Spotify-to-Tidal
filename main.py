import requests
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

load_dotenv()

## SPOTIFY

REDIRECT_URI = "http://127.0.0.1:8000/callback"
state = None # global variable to store state
SPOTIFY_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_RETRY_AFTER = 5  # Default retry time for Spotify rate limiting

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
                self.wfile.write(b"<html><body><h1>Spotify authorization successful!</h1>You can close this window.</body></html>")
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

# Opens the browser to let the user authorize the app
# Returns the authorization code or None if the user did not authorize
def spotifyGetUserAuthorizationCode():
    # open the browser to let the user authorize the app
    global state
    url = "https://accounts.spotify.com/authorize"
    scope = "playlist-read-private"
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
    print("Please authorize the app in your browser.")
    
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
        print("Failed to retrieve token:", response.status_code)
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
                for track in tracks if track.get("track")
            ]
        })
    with open(f"{filename}.json", "w") as f:
        json.dump(playlistsWithTracks, f, indent=2)
    print(f"Playlists saved to {filename}.json")

# savePlaylistsToFile(playlists)


## TIDAL

TIDAL_REDIRECT_URI = "http://127.0.0.1:3000/callback"
TIDAL_BASE_URL = "https://openapi.tidal.com/v2"
randomOctetSequence = os.urandom(32)
codeVerifier = base64.urlsafe_b64encode(randomOctetSequence).decode("utf-8").rstrip("=")

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
# if __name__ == "__main__":
    
    # Log in to Spotify and get playlists
    spotifyAuthorizationCode = spotifyGetUserAuthorizationCode()
    #print(f"App received code: {spotifyAuthorizationCode}")
    spotifyAccessToken = spotifyGetAccessToken(spotifyAuthorizationCode)
    #print(f"App received access token: {spotifyAccessToken}")
    # spotifyUserID = spotifyGetUserID(spotifyAccessToken)
    #print(f"App received user ID: {spotifyUserID}")
    spotifyPlaylists = list(spotifyGetPlaylists(spotifyAccessToken))
    playlistNames = [playlist["name"] for playlist in spotifyPlaylists]
    print(f"App received playlists from Spotify: {playlistNames}")

    blacklist = ["Hörbuch Lesezeichen",
                "Shaved Fish LP",
                "Linkin Park 2024",
                "Wuma 2024",
                "2024 Januar 1 (keys: B, G, A, C#, C)",
                "to buy",
                "SPFDJ Hör Berlin Set",
                "Another Dimension"]
    playlists = [playlist for playlist in spotifyPlaylists if playlist["name"] not in blacklist]
    savePlaylistsToJson(spotifyAccessToken, "playlists3", playlists)
    # playlistNames = [playlist["name"] for playlist in playlists]
    # print(playlistNames)
    
    ## Load playlists from file
    loadedPlaylists = []
    with open("playlists3.json", "r") as f:
        loadedPlaylists = json.load(f)
    #!--------------
    # del loadedPlaylists[0:30] # ignores the first 30 playlists!
    #!--------------
    # playlistNames = [playlist["playlist_name"] for playlist in loadedPlaylists]
    # print(playlistNames)
    
    ## Log in to TIDAL, create playlists and fill them with tracks
    tidalAuthorizationCode = tidalGetUserAuthorizationCode()
    [tidalAccessToken, userID] = tidalGetAccessToken(tidalAuthorizationCode)
    abortOperation = False
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
            else:
                print("Search failed for track:", track["track_name"])
                print("Playlist population aborted for playlist:", playlist["playlist_name"])
                abortOperation = True
                break
        tidalFillPlaylistWithTracks(tidalAccessToken, tidalPlaylistId, returnedTrackIdList, playlist["playlist_name"])
        if abortOperation:
            print("Aborting operation due to fundamental search error.")
            break
    print("Tidal playlist population completed.")
    
    ## FURTHER DEVELOPMENT
    # - Make it user friendly (e.g. command line arguments)
    # - Add error handling
    # - Add blacklist/whitelist functionality
    # - Ask if the user wants to create a new playlist or fill an existing one if playlist already exists
    # - Make a UI
    #   - add a progress bar