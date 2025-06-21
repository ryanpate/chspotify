# app.py
import os
import json
from flask import Flask, request, redirect, render_template_string, url_for, session
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
from flask_socketio import SocketIO

VOTES_FILE = 'votes.json'
USERS_FILE = 'users.json'

# ——— Configuration ———
CLIENT_ID     = os.environ['SPOTIFY_CLIENT_ID']
CLIENT_SECRET = os.environ['SPOTIFY_CLIENT_SECRET']
PLAYLIST_ID   = os.environ['SPOTIFY_PLAYLIST_ID']

# ——— Spotify setup (Client Credentials for metadata) ———
credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID,
                                              client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=credentials_manager)

# ——— OAuth Setup for Playback ———
app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']
SCOPE = 'streaming user-read-playback-state user-modify-playback-state'
REDIRECT_URI = os.environ['REDIRECT_URI']
oauth = SpotifyOAuth(client_id=CLIENT_ID,
                     client_secret=CLIENT_SECRET,
                     redirect_uri=REDIRECT_URI,
                     scope=SCOPE)

# ——— Fetch all tracks from the playlist ———
def fetch_playlist_tracks(pid):
    all_tracks = []
    results = sp.playlist_items(pid)
    while True:
        for item in results['items']:
            t = item['track']
            all_tracks.append({'id': t['id'], 'name': t['name'], 'artist': t['artists'][0]['name']})
        if results['next']:
            results = sp.next(results)
        else:
            break
    return all_tracks

tracks = fetch_playlist_tracks(PLAYLIST_ID)

# ——— Load or initialize votes ———
if os.path.exists(VOTES_FILE):
    with open(VOTES_FILE, 'r') as f:
        votes = json.load(f)
else:
    votes = {t['id']: {'like': 0, 'dislike': 0} for t in tracks}
for t in tracks:
    votes.setdefault(t['id'], {'like': 0, 'dislike': 0})
with open(VOTES_FILE, 'w') as f:
    json.dump(votes, f)

# ——— Load or initialize users ———
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
else:
    users = []
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

# ——— SocketIO setup ———
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/debug-redirect-uri')
def debug_uri():
    return oauth.redirect_uri

@app.route('/login')
def login():
    return redirect(oauth.get_authorize_url())

@app.route('/callback')
def callback():
    try:
        code = request.args.get('code')
        token_info = oauth.get_access_token(code)
        # Some spotipy versions return (token_info, state)
        if isinstance(token_info, tuple):
            token_info = token_info[0]
        session['token_info'] = token_info
        return redirect(url_for('index'))
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return f"<pre>Callback error:\\n{tb}</pre>", 500

@app.route('/', methods=['GET'])
def index():
    token_info = session.get('token_info')
    if not token_info:
        return '<p>Please <a href="{}">log in with Spotify</a> to play full tracks.</p>'.format(url_for('login'))
    access_token = token_info['access_token']
    embed_url = f"https://open.spotify.com/embed/playlist/{PLAYLIST_ID}"
    return render_template_string("""
<!doctype html>
<html><head>... rest of template ...""",
        access_token=access_token,
        PLAYLIST_ID=PLAYLIST_ID,
        tracks=tracks,
        votes=votes,
        users=users)

# ——— React endpoint ———
@app.route('/react', methods=['POST'])
def react():
    data = request.get_json()
    tid = data['track_id']
    act = data['action']
    voter = data.get('name')
    if tid not in votes or not voter:
        return ('', 400)
    if 'voters' not in votes[tid]:
        votes[tid]['voters'] = []
    if voter in votes[tid]['voters']:
        return ('', 403)
    votes[tid][act] += 1
    votes[tid]['voters'].append(voter)
    with open(VOTES_FILE, 'w') as f:
        json.dump(votes, f)
    socketio.emit('reaction_update', {'track_id': tid, 'action': act, 'count': votes[tid][act]})
    return ('', 204)

@app.route('/stats')
def stats():
    ...  # stats logic unchanged

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)
