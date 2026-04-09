from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import uuid
import os
import threading
import time
import random

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'secret!'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

players = {}
BUSH_POSITIONS = [
    (50, 50), (150, 80), (250, 40), (350, 100), (450, 60),
    (550, 90), (650, 50), (750, 80), (80, 150), (180, 200),
    (280, 170), (380, 220), (480, 180), (580, 230), (680, 190),
    (100, 350), (200, 400), (300, 380), (500, 420), (700, 370)
]
bushes = [None] * 20

game_state = {
    'status': 'waiting',
    'seeker_id': None,
    'winner': None,
    'time_left': 30,
    'all_hidden_trigger': False
}
timer_thread = None
timer_running = False

npcs = []
npc_lock = threading.Lock()
npc_thread = None
npc_running = False
last_interaction = {}

def get_all_players_data():
    return [{'id': p['id'], 'name': p['name'], 'role': p['role'],
             'bush_index': p.get('bush_index', -1), 'isHidden': p['isHidden']}
            for p in players.values()]

def broadcast_state():
    data = {
        'players': get_all_players_data(),
        'game_state': {
            'status': game_state['status'],
            'seeker_id': game_state['seeker_id'],
            'winner': game_state['winner'],
            'time_left': game_state['time_left']
        },
        'npcs': npcs.copy(),
        'bushes': bushes.copy()
    }
    socketio.emit('game_state', data)

def check_all_hidden():
    if game_state['status'] != 'hiding_phase':
        return False
    if not game_state['seeker_id']:
        return False
    non_seekers = [p for p in players.values() if p['id'] != game_state['seeker_id']]
    if len(non_seekers) == 0:
        return False
    all_hidden = all(p['isHidden'] for p in non_seekers)
    if all_hidden and not game_state.get('all_hidden_trigger'):
        game_state['all_hidden_trigger'] = True
        stop_timer()
        game_state['status'] = 'playing'
        game_state['time_left'] = 0
        socketio.emit('server_message', {'text': '✅ Все спрятались! Водящий может искать.'})
        broadcast_state()
    return all_hidden

def end_game(winner_name, is_good_npc_win=False):
    stop_timer()
    game_state['status'] = 'gameover'
    game_state['winner'] = winner_name
    if is_good_npc_win:
        socketio.emit('server_message', {'text': f'😇 ДОБРЫЙ ХАГИ ВАГИ появился! Игра окончена! Все спрятавшиеся победили! 🏆'})
        socketio.emit('good_npc_appeared', {})
    broadcast_state()

def timer_loop():
    global timer_running
    while timer_running and game_state['status'] == 'hiding_phase' and game_state['time_left'] > 0:
        time.sleep(1)
        if not timer_running or game_state['status'] != 'hiding_phase':
            break
        game_state['time_left'] -= 1
        broadcast_state()
        if game_state['time_left'] <= 0:
            stop_timer()
            game_state['status'] = 'playing'
            socketio.emit('server_message', {'text': '⏰ Время пряток вышло! Водящий, ищи!'})
            broadcast_state()
            break

def start_timer(seconds):
    global timer_thread, timer_running
    stop_timer()
    game_state['time_left'] = seconds
    timer_running = True
    timer_thread = threading.Thread(target=timer_loop, daemon=True)
    timer_thread.start()

def stop_timer():
    global timer_running
    timer_running = False

def start_npc_movement():
    global npc_running, npc_thread
    stop_npc_movement()
    npc_running = True
    npc_thread = threading.Thread(target=update_npcs_loop, daemon=True)
    npc_thread.start()

def stop_npc_movement():
    global npc_running, npc_thread
    npc_running = False
    if npc_thread:
        npc_thread.join(timeout=0.5)
        npc_thread = None

def update_npcs_loop():
    global npc_running
    while npc_running:
        time.sleep(0.1)
        with npc_lock:
            for npc in npcs:
                npc['x'] += npc['vx']
                npc['y'] += npc['vy']
                if npc['x'] < 25:
                    npc['x'] = 25
                    npc['vx'] = abs(npc['vx'])
                if npc['x'] > 775:
                    npc['x'] = 775
                    npc['vx'] = -abs(npc['vx'])
                if npc['y'] < 25:
                    npc['y'] = 25
                    npc['vy'] = abs(npc['vy'])
                if npc['y'] > 475:
                    npc['y'] = 475
                    npc['vy'] = -abs(npc['vy'])
            
            now = time.time()
            for sid, p in players.items():
                if p['id'] == game_state['seeker_id']:
                    continue
                if not p.get('isHidden'):
                    continue
                bush_x, bush_y = BUSH_POSITIONS[p.get('bush_index', 0)]
                for npc in npcs:
                    key = f"{p['id']}_{npc['type']}"
                    if key in last_interaction and now - last_interaction[key] < 2.0:
                        continue
                    dx = bush_x - npc['x']
                    dy = bush_y - npc['y']
                    if (dx*dx + dy*dy) < 900:
                        last_interaction[key] = now
                        if npc['type'] == 'good':
                            end_game("😇 ДОБРЫЙ ХАГИ ВАГИ", is_good_npc_win=True)
                            return
                        elif npc['type'] == 'evil':
                            if p['isHidden']:
                                p['isHidden'] = False
                                old_bush = p.get('bush_index')
                                if old_bush is not None and bushes[old_bush] == p['id']:
                                    bushes[old_bush] = None
                                p['bush_index'] = -1
                                socketio.emit('server_message', {'text': f'💀 Злой Хаги Ваги выгнал {p["name"]} из куста!'})
                                socketio.emit('evil_npc_encounter', {'player_name': p['name']})
                                broadcast_state()
                                if game_state['status'] == 'playing':
                                    remaining_hidden = any(pl['isHidden'] for pl in players.values() if pl['id'] != game_state['seeker_id'])
                                    if not remaining_hidden:
                                        end_game(players[game_state['seeker_id']]['name'])
            broadcast_state()

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    player_id = str(uuid.uuid4())[:8]
    players[sid] = {
        'id': player_id,
        'name': f'Гость_{player_id[:4]}',
        'role': 'hider',
        'bush_index': -1,
        'isHidden': False
    }
    emit('your_id', players[sid]['id'], room=sid)
    if len(players) == 1 and game_state['status'] == 'waiting':
        game_state['seeker_id'] = players[sid]['id']
        players[sid]['role'] = 'seeker'
    broadcast_state()
    socketio.emit('server_message', {'text': f'✨ {players[sid]["name"]} присоединился к игре!'})

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in players:
        name = players[sid]['name']
        bush_idx = players[sid].get('bush_index')
        if bush_idx is not None and bush_idx >= 0 and bushes[bush_idx] == players[sid]['id']:
            bushes[bush_idx] = None
        del players[sid]
        if game_state['status'] == 'waiting' and not game_state['seeker_id'] and players:
            first_sid = next(iter(players.keys()))
            players[first_sid]['role'] = 'seeker'
            game_state['seeker_id'] = players[first_sid]['id']
        broadcast_state()
        socketio.emit('server_message', {'text': f'👋 {name} покинул игру'})

@socketio.on('set_name')
def handle_set_name(data):
    sid = request.sid
    if sid in players:
        new_name = data.get('name', '').strip()[:12] if data else ''
        if new_name:
            old_name = players[sid]['name']
            players[sid]['name'] = new_name
            socketio.emit('server_message', {'text': f'{old_name} теперь называется {new_name}'})
            broadcast_state()

@socketio.on('hide_in_bush')
def handle_hide_in_bush(data):
    sid = request.sid
    if sid not in players:
        return
    p = players[sid]
    bush_index = data.get('bush_index')
    
    if game_state['status'] != 'hiding_phase':
        socketio.emit('server_message', {'text': 'Сейчас нельзя прятаться'}, room=sid)
        return
    if p['id'] == game_state['seeker_id']:
        socketio.emit('server_message', {'text': 'Ты водящий, не можешь прятаться!'}, room=sid)
        return
    if p['isHidden']:
        socketio.emit('server_message', {'text': 'Ты уже спрятался!'}, room=sid)
        return
    if bush_index is None or bush_index < 0 or bush_index >= 20:
        return
    if bushes[bush_index] is not None:
        socketio.emit('server_message', {'text': 'Этот куст уже занят! Выбери другой.'}, room=sid)
        return
    
    p['bush_index'] = bush_index
    p['isHidden'] = True
    bushes[bush_index] = p['id']
    broadcast_state()
    socketio.emit('server_message', {'text': f'🌿 {p["name"]} спрятался в кусте {bush_index + 1}!'})
    check_all_hidden()

@socketio.on('start_game')
def handle_start_game():
    global npcs, bushes
    if game_state['status'] != 'waiting':
        socketio.emit('server_message', {'text': 'Игра уже запущена'}, room=request.sid)
        return
    if len(players) < 2:
        socketio.emit('server_message', {'text': 'Нужно минимум 2 игрока'}, room=request.sid)
        return
    
    bushes = [None] * 20
    
    if not game_state['seeker_id']:
        first_sid = next(iter(players.keys()))
        game_state['seeker_id'] = players[first_sid]['id']
        players[first_sid]['role'] = 'seeker'
    
    for sid, p in players.items():
        if p['id'] == game_state['seeker_id']:
            p['role'] = 'seeker'
            p['isHidden'] = False
            p['bush_index'] = -1
        else:
            p['role'] = 'hider'
            p['isHidden'] = False
            p['bush_index'] = -1
    
    game_state['status'] = 'hiding_phase'
    game_state['winner'] = None
    game_state['all_hidden_trigger'] = False
    game_state['time_left'] = 30
    
    with npc_lock:
        npcs = []
        if random.random() < 0.01:
            npcs.append({
                'type': 'good',
                'x': random.randint(100, 700),
                'y': random.randint(100, 400),
                'vx': random.uniform(-2, 2),
                'vy': random.uniform(-2, 2)
            })
            socketio.emit('server_message', {'text': '😇 Редкий шанс! Добрый Хаги Ваги появился!'})
        else:
            npcs.append({
                'type': 'evil',
                'x': random.randint(100, 700),
                'y': random.randint(100, 400),
                'vx': random.uniform(-2, 2),
                'vy': random.uniform(-2, 2)
            })
    start_npc_movement()
    
    broadcast_state()
    start_timer(30)
    socketio.emit('server_message', {'text': '🕒 Игра началась! 30 секунд чтобы спрятаться!'})

@socketio.on('seek')
def handle_seek(data):
    sid = request.sid
    if sid not in players:
        return
    seeker = players[sid]
    if game_state['status'] != 'playing':
        socketio.emit('server_message', {'text': 'Поиск начнётся после окончания времени пряток'}, room=sid)
        return
    if seeker['id'] != game_state['seeker_id']:
        socketio.emit('server_message', {'text': 'Только водящий может искать!'}, room=sid)
        return
    
    bush_index = data.get('bush_index')
    if bush_index is None or bush_index < 0 or bush_index >= 20:
        return
    
    player_id = bushes[bush_index]
    if player_id:
        for sid2, p in players.items():
            if p['id'] == player_id and p['isHidden']:
                p['isHidden'] = False
                bushes[bush_index] = None
                p['bush_index'] = -1
                remaining_hidden = any(pl['isHidden'] for pl in players.values() if pl['id'] != game_state['seeker_id'])
                socketio.emit('server_message', {'text': f'🔎 {seeker["name"]} нашёл {p["name"]} в кусте {bush_index + 1}!'})
                broadcast_state()
                if not remaining_hidden:
                    end_game(seeker['name'])
                return
    socketio.emit('server_message', {'text': 'Мимо! В этом кусте никого нет.'}, room=sid)

@socketio.on('reset_game')
def handle_reset():
    global game_state, npcs, bushes
    stop_timer()
    stop_npc_movement()
    with npc_lock:
        npcs = []
    bushes = [None] * 20
    game_state = {
        'status': 'waiting',
        'seeker_id': None,
        'winner': None,
        'time_left': 30,
        'all_hidden_trigger': False
    }
    for sid, p in players.items():
        p['isHidden'] = False
        p['role'] = 'hider'
        p['bush_index'] = -1
    if players:
        first_sid = next(iter(players.keys()))
        players[first_sid]['role'] = 'seeker'
        game_state['seeker_id'] = players[first_sid]['id']
    broadcast_state()
    socketio.emit('server_message', {'text': '🔄 Игра сброшена в меню'})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/players')
def get_players():
    return jsonify({'count': len(players), 'players': list(players.values())})

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    os.makedirs('static/images', exist_ok=True)
    port = int(os.environ.get('PORT', 5001))
    print(f"🚀 Сервер запущен на порту {port}")
    print("😈 Злой Хаги Ваги 99% | 😇 Добрый 1%")
    socketio.run(app, host='0.0.0.0', port=port, debug=False)