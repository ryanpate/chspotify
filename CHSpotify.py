# Patch eventlet for SSL and socket before any other imports
import eventlet
eventlet.monkey_patch()
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
    return render_template_string('''
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CH Worship New Song Review</title>
  <style>
    body { background-color: #121212; color: #e0e0e0; font-family: Arial, sans-serif; margin:0; padding:20px; }
    h1, h2 { color:#ffffff; margin-bottom:20px; }
    .container { max-width:900px; margin:0 auto; }
    #player { width:100%; height:80px; margin-bottom:20px; }
    label, select, button { margin-right:10px; vertical-align:middle; }
    ul { list-style:none; padding:0; }
    li { background:#1e1e1e; padding:10px; margin-bottom:10px; border-radius:4px; display:flex; align-items:center; }
    .track-info { flex:1; overflow-wrap:anywhere; }
    .vote-actions { display:flex; align-items:center; gap:10px; }
    button.vote-btn { background:#3f51b5; color:#fff; border:none; padding:8px 12px; border-radius:4px; cursor:pointer; }
    button.vote-btn:hover { background:#303f9f; }
  </style>
  <script src="https://sdk.scdn.co/spotify-player.js"></script>
</head>
<body>
  <div class="container">
    <div id="player"></div>
    <script>
      window.onSpotifyWebPlaybackSDKReady = () => {
        const token = "{{ access_token }}";
        window.player = new Spotify.Player({
          name: 'CH Spotify Web Player',
          getOAuthToken: cb => { cb(token); }
        });
        window.player.connect();
      };
      function playTrack(track_id) {
        window.player.play({
          spotify_uri: 'spotify:track:' + track_id,
          position_ms: 0
        });
      }
    </script>
    <!-- Spotify Embed for visual playlist -->
    <iframe src="https://open.spotify.com/embed/playlist/{{ PLAYLIST_ID }}"
            width="100%" height="380"
            frameborder="0" allowtransparency="true" allow="encrypted-media">
    </iframe>
    <h1>CH Worship New Song Review</h1>
    <p><a href="/stats" style="color:#3f51b5; text-decoration:none;">View Statistics →</a></p>
    <label for="user-select">Your Name:</label>
    <select id="user-select">
      <option value="" disabled selected>Select your name</option>
      {% for user in users %}
        <option value="{{ user }}">{{ user }}</option>
      {% endfor %}
    </select>
    <button id="update-users-btn">Update Users</button>
    <h2>Vote for Your Favorite Tracks</h2>
    <ul>
      {% for track in tracks %}
        <li>
          <button class="vote-btn" onclick="playTrack('{{ track.id }}')">▶️ Play</button>
          <div class="track-info">{{ track.name }} — {{ track.artist }}</div>
          <div class="vote-actions">
            <button class="vote-btn" onclick="react('{{ track.id }}', 'like')">👍 Like</button>
            <strong id="like-{{ track.id }}">{{ votes[track.id]['like'] }}</strong>
            <button class="vote-btn" onclick="react('{{ track.id }}', 'dislike')">👎 Dislike</button>
            <strong id="dislike-{{ track.id }}">{{ votes[track.id]['dislike'] }}</strong>
          </div>
        </li>
      {% endfor %}
    </ul>
  </div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
<script>
  var socket = io();
  socket.on('reaction_update', function(data) {
    var el = document.getElementById(data.action + '-' + data.track_id);
    if (el) el.innerText = data.count;
  });
  function react(track_id, action) {
    var name = document.getElementById('user-select').value;
    if (!name) { alert('Please select a user before voting.'); return; }
    fetch('/react', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({track_id: track_id, action: action, name: name})
    }).then(response => {
      if (response.status === 403) alert('You have already voted for this song.');
      else if (response.status !== 204) alert('Error: ' + response.statusText);
    });
  }
  document.getElementById('update-users-btn').addEventListener('click', function() {
    var pin = prompt('Enter PIN to update users:');
    if (pin !== '2006') { alert('Incorrect PIN'); return; }
    window.location = '/users';
  });
</script>
</body>
</html>
''',
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


# ——— Statistics endpoint ———
@app.route('/stats', methods=['GET'])
def stats():
    # Compute top 10 lists
    liked     = sorted(tracks, key=lambda t: votes[t['id']]['like'],    reverse=True)[:10]
    disliked  = sorted(tracks, key=lambda t: votes[t['id']]['dislike'], reverse=True)[:10]
    # Some tracks may have no popularity key
    popular   = sorted(tracks, key=lambda t: t.get('popularity', 0),    reverse=True)[:10]

    # Prepare data for Plotly
    liked_labels    = [f"{t['name']} — {t['artist']}" for t in liked]
    liked_values    = [votes[t['id']]['like'] for t in liked]
    disliked_labels = [f"{t['name']} — {t['artist']}" for t in disliked]
    disliked_values = [votes[t['id']]['dislike'] for t in disliked]
    popular_labels  = [f"{t['name']} — {t['artist']}" for t in popular]
    popular_values  = [t.get('popularity', 0) for t in popular]

    return render_template_string('''
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Statistics – CH Worship Review</title>
  <style>
    body { background:#121212; color:#e0e0e0; font-family:Arial,sans-serif; padding:20px; margin:0; }
    .container { max-width:900px; margin:0 auto; }
    h1 { color:#fff; margin-bottom:20px; }
    a { color:#3f51b5; text-decoration:none; }
    .chart-container { margin-bottom: 60px; }
    .charts-grid { display: grid; grid-template-columns: repeat(2, 1fr); grid-gap: 40px; }
    .chart-span2 { grid-column: span 2; }
  </style>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
  <div class="container">
    <h1>🎵 Voting Statistics</h1>
    <p><a href="/">← Back to Voting</a></p>
    <button id="reset-btn">Reset All Stats</button>
    <div class="charts-grid">
      <div id="chart-likes" class="chart-container"></div>
      <div id="chart-dislikes" class="chart-container"></div>
      <div id="chart-popularity" class="chart-container chart-span2"></div>
    </div>
  </div>
<script>
  var likedLabels    = {{ liked_labels|tojson }};
  var likedValues    = {{ liked_values|tojson }};
  var dislikedLabels = {{ disliked_labels|tojson }};
  var dislikedValues = {{ disliked_values|tojson }};
  var popularLabels  = {{ popular_labels|tojson }};
  var popularValues  = {{ popular_values|tojson }};

  // generate distinct colors
  var likedN = likedLabels.length;
  var likedColors = likedLabels.map((_,i) => `hsl(${i*360/likedN},70%,50%)`);
  var dislikedN = dislikedLabels.length;
  var dislikedColors = dislikedLabels.map((_,i) => `hsl(${i*360/dislikedN},70%,50%)`);
  var popularN = popularLabels.length;
  var popularColors = popularLabels.map((_,i) => `hsl(${i*360/popularN},70%,50%)`);

  var layout = {
    paper_bgcolor: '#121212',
    plot_bgcolor: '#121212',
    font: { color: '#e0e0e0' },
    height: 450,
    margin: { t: 30, b: 100, l: 50, r: 20 }
  };

  Plotly.newPlot('chart-likes', [{
    x: likedLabels,
    y: likedValues,
    type: 'bar',
    marker: { color: likedColors }
  }], Object.assign({}, layout, {title:'Top 10 Likes'}));

  Plotly.newPlot('chart-dislikes', [{
    x: dislikedLabels,
    y: dislikedValues,
    type: 'bar',
    marker: { color: dislikedColors }
  }], Object.assign({}, layout, {title:'Top 10 Dislikes'}));

  Plotly.newPlot('chart-popularity', [{
    x: popularLabels,
    y: popularValues,
    type: 'bar',
    marker: { color: popularColors }
  }], Object.assign({}, layout, {title:'Top 10 Spotify Popularity'}));

  document.getElementById('reset-btn').addEventListener('click', function() {
    var pin = prompt('Enter reset PIN:');
    if (pin !== '2006') { alert('Incorrect PIN'); return; }
    fetch('/reset', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pin: pin})
    }).then(response => {
      if (response.status === 403) {
        alert('Invalid PIN');
      } else {
        location.reload();
      }
    });
  });
</script>
</body>
</html>
''',
    liked_labels=liked_labels,
    liked_values=liked_values,
    disliked_labels=disliked_labels,
    disliked_values=disliked_values,
    popular_labels=popular_labels,
    popular_values=popular_values
)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8000)
