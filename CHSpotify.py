# app.py
import os
from flask import Flask, request, redirect, render_template_string
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from flask_socketio import SocketIO
import json
from flask import session, url_for
from spotipy.oauth2 import SpotifyOAuth
VOTES_FILE = 'votes.json'
USERS_FILE = 'users.json'

# ——— Configuration ———
CLIENT_ID     = os.getenv('SPOTIFY_CLIENT_ID',     'b6fa778f43324f3c9b4cff6b63c82258')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '849cde0f5fee483cbeee5bad9cfb0872')
PLAYLIST_ID = os.getenv('SPOTIFY_PLAYLIST_ID',
                        '3fe3KZXMfVt2HUoMxJdsPF')

# ——— Spotify setup (Client Credentials) ———
credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID,
                                              client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=credentials_manager)

# ——— Fetch all tracks from the playlist at startup ———
def fetch_playlist_tracks(pid):
    all_tracks = []
    results = sp.playlist_items(pid)
    while True:
        for item in results['items']:
            t = item['track']
            all_tracks.append({
                'id':         t['id'],
                'name':       t['name'],
                'artist':     t['artists'][0]['name'],
                'popularity': t.get('popularity', 0)
            })
        if results['next']:
            results = sp.next(results)
        else:
            break
    return all_tracks

tracks = fetch_playlist_tracks(PLAYLIST_ID)
# Load or initialize persistent votes
if os.path.exists(VOTES_FILE):
    with open(VOTES_FILE, 'r') as f:
        votes = json.load(f)
else:
    votes = {t['id']: {'like': 0, 'dislike': 0} for t in tracks}
# Ensure every track has an entry
for t in tracks:
    if t['id'] not in votes:
        votes[t['id']] = {'like': 0, 'dislike': 0}
# Save initial state
with open(VOTES_FILE, 'w') as f:
    json.dump(votes, f)

# Load or initialize user list
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
else:
    users = []
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

# ——— Flask app ———
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Session & OAuth configuration
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecret')
SCOPE = 'streaming user-read-playback-state user-modify-playback-state'
REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:8000/callback')
oauth = SpotifyOAuth(client_id=CLIENT_ID,
                     client_secret=CLIENT_SECRET,
                     redirect_uri=REDIRECT_URI,
                     scope=SCOPE)

@app.route('/login')
def login():
    auth_url = oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect(url_for('index'))

@app.route('/', methods=['GET'])
def index():
    token_info = session.get('token_info', None)
    if not token_info:
        return render_template_string('''
          <p>Please <a href="{{ url_for('login') }}">log in with Spotify</a> to play full tracks.</p>
      ''')
    access_token = token_info['access_token']

    return render_template_string('''
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CH Worship New Song Review</title>
  <style>
    body {
      background-color: #121212;
      color: #e0e0e0;
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 20px;
    }
    h1, h2 {
      color: #ffffff;
      margin-bottom: 20px;
    }
    .container {
      max-width: 900px;
      margin: 0 auto;
    }
    ul {
      list-style: none;
      padding: 0;
    }
    li {
      background-color: #1e1e1e;
      padding: 10px;
      margin-bottom: 10px;
      border-radius: 4px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    button {
      background-color: #3f51b5;
      color: #ffffff;
      border: none;
      padding: 8px 12px;
      border-radius: 4px;
      cursor: pointer;
    }
    button:hover {
      background-color: #303f9f;
    }
    .track-info {
      flex: 1;
      overflow-wrap: anywhere;
    }
    .vote-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div id="player"></div>
    <script src="https://sdk.scdn.co/spotify-player.js"></script>
    <script>
      window.onSpotifyWebPlaybackSDKReady = () => {
        const token = "{{ access_token }}";
        const player = new Spotify.Player({
          name: 'CH Spotify Web Player',
          getOAuthToken: cb => { cb(token); }
        });
        player.connect().then(success => {
          if (success) {
            player.play({
              spotify_uri: 'spotify:playlist:{{ PLAYLIST_ID }}',
              playerInstance: player
            });
          }
        });
      };
    </script>
    <h1>CH Worship New Song Review</h1>
    <p><a href="/stats" style="color:#3f51b5; text-decoration:none;">View Statistics →</a></p>

    <label for="user-select">Your Name:</label>
    <select id="user-select">
      <option value="" disabled selected>Select User Name</option>
      {% for user in users %}
        <option value="{{ user }}">{{ user }}</option>
      {% endfor %}
    </select>
    <button id="update-users-btn">Update Users</button>
    <h2>Vote for Your Favorite Tracks</h2>
    <ul>
      {% for track in tracks %}
        <li>
          <div class="track-info">{{ track.name }} — {{ track.artist }}</div>
          <div class="vote-actions">
            <button onclick="react('{{ track.id }}', 'like')">👍 Like</button>
            <strong id="like-{{ track.id }}">{{ votes[track.id]['like'] }} </strong>
            <button onclick="react('{{ track.id }}', 'dislike')">👎 Dislike</button>
            <strong id="dislike-{{ track.id }}">{{ votes[track.id]['dislike'] }} </strong>
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
    if (el) {
      el.innerText = data.count;
    }
  });
  function react(track_id, action) {
    var name = document.getElementById('user-select').value;
    if (!name) {
      alert('Please select a user before voting.');
      return;
    }
    fetch('/react', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({track_id: track_id, action: action, name: name})
    }).then(response => {
      if (response.status === 403) {
        alert('You have already voted for this song.');
      } else if (response.status !== 204) {
        alert('Error: ' + response.statusText);
      }
    });
  }
  document.getElementById('update-users-btn').addEventListener('click', function() {
    var pin = prompt('Enter PIN to update users:');
    if (pin !== '2006') {
      alert('Incorrect PIN');
      return;
    }
    window.location = '/users';
  });
</script>
</body>
</html>
''', access_token=access_token, PLAYLIST_ID=PLAYLIST_ID, tracks=tracks, votes=votes, users=users)


@app.route('/react', methods=['POST'])
def react():
    data = request.get_json()
    track_id = data.get('track_id')
    action = data.get('action')
    name = data.get('name')
    # Track voters per track
    if track_id not in votes:
        return ('Invalid track', 400)
    if 'voters' not in votes[track_id]:
        votes[track_id]['voters'] = []
    if name in votes[track_id]['voters']:
        return ('Already voted', 403)
    if action in ['like', 'dislike']:
        votes[track_id][action] += 1
        votes[track_id]['voters'].append(name)
        # Persist updated votes
        with open(VOTES_FILE, 'w') as f:
            json.dump(votes, f)
        socketio.emit('reaction_update', {
            'track_id': track_id,
            'action': action,
            'count': votes[track_id][action]
        })
        return ('', 204)
    return ('Invalid action', 400)
# User management routes
@app.route('/users', methods=['GET'])
def manage_users():
    return render_template_string('''
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>User Management</title>
  <style>
    body { background:#121212; color:#e0e0e0; font-family:Arial,sans-serif; padding:20px; margin:0; }
    .container { max-width:600px; margin:0 auto; }
    h1 { color:#fff; margin-bottom:20px; }
    ul { list-style:none; padding:0; }
    li { background:#1e1e1e; margin-bottom:10px; padding:10px; border-radius:4px; display:flex; justify-content:space-between; }
    button { background:#3f51b5; color:#fff; border:none; padding:6px 10px; border-radius:4px; cursor:pointer; }
    button:hover { background:#303f9f; }
    .actions { display:flex; gap:10px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>User Management</h1>
    <p><a href="/" style="color:#3f51b5; text-decoration:none;">← Back to Voting</a></p>
    <ul>
      {% for u in users %}
        <li>
          <span>{{ u }}</span>
          <div class="actions">
            <button onclick="editUser('{{ u }}')">Edit</button>
            <button onclick="deleteUser('{{ u }}')">Delete</button>
          </div>
        </li>
      {% endfor %}
    </ul>
    <button id="add-user-btn">Add User</button>
  </div>
<script>
  function addUser() {
    var name = prompt('Enter new user name:');
    if (!name) return;
    fetch('/users/add', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name: name})
    }).then(() => location.reload());
  }
  function editUser(oldName) {
    var newName = prompt('Edit name:', oldName);
    if (!newName || newName === oldName) return;
    fetch('/users/edit', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({old: oldName, new: newName})
    }).then(() => location.reload());
  }
  function deleteUser(name) {
    if (!confirm('Delete ' + name + '?')) return;
    fetch('/users/delete', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({name: name})
    }).then(() => location.reload());
  }
  document.getElementById('add-user-btn').addEventListener('click', addUser);
</script>
</body>
</html>
''', users=users)

@app.route('/users/add', methods=['POST'])
def add_user():
    data = request.get_json()
    name = data.get('name', '').strip()
    if name and name not in users:
        users.append(name)
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
        return ('', 204)
    return ('Invalid or duplicate', 400)

@app.route('/users/edit', methods=['POST'])
def edit_user():
    data = request.get_json()
    old = data.get('old')
    new = data.get('new', '').strip()
    if old in users and new:
        idx = users.index(old)
        users[idx] = new
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
        return ('', 204)
    return ('Invalid', 400)

@app.route('/users/delete', methods=['POST'])
def delete_user():
    data = request.get_json()
    name = data.get('name')
    if name in users:
        users.remove(name)
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
        return ('', 204)
    return ('Invalid', 400)


# --- Statistics Page ---
@app.route('/stats', methods=['GET'])
def stats():
    # Compute top lists
    liked     = sorted(tracks, key=lambda t: votes[t['id']]['like'],    reverse=True)[:10]
    disliked  = sorted(tracks, key=lambda t: votes[t['id']]['dislike'], reverse=True)[:10]
    popular   = sorted(tracks, key=lambda t: t['popularity'],           reverse=True)[:10]

    # Prepare data for Plotly
    liked_labels    = [f"{t['name']} — {t['artist']}" for t in liked]
    liked_values    = [votes[t['id']]['like'] for t in liked]
    disliked_labels = [f"{t['name']} — {t['artist']}" for t in disliked]
    disliked_values = [votes[t['id']]['dislike'] for t in disliked]
    popular_labels  = [f"{t['name']} — {t['artist']}" for t in popular]
    popular_values  = [t['popularity'] for t in popular]

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
    .chart-container {
      margin-bottom: 60px;
    }
    .charts-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      grid-gap: 40px;
    }
    .chart-span2 {
      grid-column: span 2;
    }
  </style>
  <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
  <div class="container">
    <h1>Voting Statistics</h1>
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
    if (pin !== '2006') {
      alert('Incorrect PIN');
      return;
    }
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


# --- Reset Stats Endpoint ---
@app.route('/reset', methods=['POST'])
def reset_stats():
    data = request.get_json()
    pin = data.get('pin')
    if pin != '2006':
        return ('Invalid PIN', 403)
    # Clear all vote counts and voters
    for t in tracks:
        votes[t['id']] = {'like': 0, 'dislike': 0, 'voters': []}
    # Persist reset
    with open(VOTES_FILE, 'w') as f:
        json.dump(votes, f)
    return ('', 204)

if __name__ == '__main__':
    # Accessible on your local network
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)