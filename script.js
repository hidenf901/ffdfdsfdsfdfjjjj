const socket = io();
let myId = null;
let currentPlayers = [];
let gameStatus = 'waiting';
let seekerId = null;
let winnerText = null;
let timeLeft = 0;
let npcs = [];
let bushes = [];

const BUSH_POSITIONS = [
    {x: 50, y: 50}, {x: 150, y: 80}, {x: 250, y: 40}, {x: 350, y: 100}, {x: 450, y: 60},
    {x: 550, y: 90}, {x: 650, y: 50}, {x: 750, y: 80}, {x: 80, y: 150}, {x: 180, y: 200},
    {x: 280, y: 170}, {x: 380, y: 220}, {x: 480, y: 180}, {x: 580, y: 230}, {x: 680, y: 190},
    {x: 100, y: 350}, {x: 200, y: 400}, {x: 300, y: 380}, {x: 500, y: 420}, {x: 700, y: 370}
];

const goodImage = new Image();
const evilImage = new Image();
goodImage.src = '/images/good_huggy_wugi.png';
evilImage.src = '/images/evil_huggy_wugi.png';

let onlineCount = 0;

// DOM элементы
const menu = document.getElementById('menu');
const gameScreen = document.getElementById('gameScreen');
const rulesModal = document.getElementById('rulesModal');
const playBtn = document.getElementById('playBtn');
const rulesBtn = document.getElementById('rulesBtn');
const exitMenuBtn = document.getElementById('exitMenuBtn');
const onlineCountSpan = document.getElementById('onlineCount');

// Меню
playBtn.onclick = () => {
    menu.style.display = 'none';
    gameScreen.style.display = 'block';
};

exitMenuBtn.onclick = () => {
    menu.style.display = 'flex';
    gameScreen.style.display = 'none';
    socket.emit('reset_game');
};

rulesBtn.onclick = () => {
    rulesModal.style.display = 'flex';
};

document.querySelector('.close-rules')?.onclick = () => {
    rulesModal.style.display = 'none';
};

// Получение онлайна
setInterval(() => {
    fetch('/api/players')
        .then(res => res.json())
        .then(data => {
            onlineCount = data.count;
            if (onlineCountSpan) onlineCountSpan.textContent = onlineCount;
        });
}, 2000);

// Игровая логика
const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const timerSpan = document.getElementById('timerSpan');

function showNpcPopup(type) {
    const popup = document.createElement('div');
    popup.className = 'npc-popup';
    const imgSrc = type === 'good' ? '/images/good_huggy_wugi.png' : '/images/evil_huggy_wugi.png';
    const title = type === 'good' ? '😇 ДОБРЫЙ ХАГИ ВАГИ' : '😈 ЗЛОЙ ХАГИ ВАГИ';
    popup.innerHTML = `
        <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,0.9);border-radius:30px;padding:20px;text-align:center;z-index:2000;">
            <img src="${imgSrc}" style="max-width:250px;border-radius:20px;">
            <h2 style="color:white;">${title}</h2>
            <button onclick="this.parentElement.remove()">Закрыть</button>
        </div>
    `;
    document.body.appendChild(popup);
    setTimeout(() => {
        if (popup.parentElement) popup.remove();
    }, 5000);
}

socket.on('good_npc_appeared', () => showNpcPopup('good'));
socket.on('evil_npc_encounter', (data) => showNpcPopup('evil'));

function getMousePos(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY
    };
}

function getBushIndex(x, y) {
    for (let i = 0; i < BUSH_POSITIONS.length; i++) {
        const bush = BUSH_POSITIONS[i];
        const dx = bush.x - x;
        const dy = bush.y - y;
        if (Math.sqrt(dx * dx + dy * dy) < 30) return i;
    }
    return -1;
}

socket.on('game_state', (data) => {
    currentPlayers = data.players;
    gameStatus = data.game_state.status;
    seekerId = data.game_state.seeker_id;
    winnerText = data.game_state.winner;
    timeLeft = data.game_state.time_left;
    npcs = data.npcs || [];
    bushes = data.bushes || [];
    updateUI();
    drawCanvas();
    if (timeLeft !== undefined && gameStatus === 'hiding_phase') {
        timerSpan.textContent = `⏱️ ${timeLeft} с`;
    } else {
        timerSpan.textContent = '';
    }
});

socket.on('server_message', (msg) => addLog(msg.text));
socket.on('connect', () => addLog('🔌 Подключено к серверу'));
socket.on('your_id', (id) => { myId = id; });

function addLog(text) {
    const logDiv = document.getElementById('logMessages');
    if (!logDiv) return;
    const p = document.createElement('div');
    p.innerHTML = `🕒 ${new Date().toLocaleTimeString()} ${text}`;
    logDiv.prepend(p);
    if (logDiv.children.length > 8) logDiv.removeChild(logDiv.lastChild);
}

function updateUI() {
    const statusDiv = document.getElementById('statusLabel');
    if (!statusDiv) return;
    if (gameStatus === 'waiting') statusDiv.innerHTML = '🏕️ МЕНЮ / Ожидание игроков <span id="timerSpan" class="timer"></span>';
    else if (gameStatus === 'hiding_phase') statusDiv.innerHTML = `🕒 ФАЗА ПРЯТОК (${timeLeft} с) | Водящий ждёт <span id="timerSpan" class="timer">⏱️ ${timeLeft} с</span>`;
    else if (gameStatus === 'playing') statusDiv.innerHTML = `🎲 ИГРА ИДЕТ | Водит: ${currentPlayers.find(p => p.id === seekerId)?.name || 'никто'} <span id="timerSpan" class="timer"></span>`;
    else if (gameStatus === 'gameover') statusDiv.innerHTML = `🏆 ИГРА ОКОНЧЕНА: ${winnerText || '—'} <span id="timerSpan" class="timer"></span>`;

    const playersContainer = document.getElementById('playersList');
    if (playersContainer) {
        if (currentPlayers.length === 0) playersContainer.innerHTML = '👥 Нет игроков...';
        else {
            playersContainer.innerHTML = currentPlayers.map(p => {
                let roleIcon = p.id === seekerId ? '🔍 водит' : (p.isHidden ? '🌳 в кусте' : '👀 ищет куст');
                return `<span class="player-badge">${p.name} (${roleIcon})</span>`;
            }).join('');
        }
    }
}

function drawCanvas() {
    if (!ctx) return;
    ctx.clearRect(0, 0, 800, 500);

    for (let i = 0; i < 30; i++) {
        ctx.beginPath();
        ctx.arc(70 + (i * 57) % 700, 70 + Math.floor(i / 4) * 60, 25, 0, Math.PI * 2);
        ctx.fillStyle = '#3d7a32';
        ctx.fill();
    }

    for (let i = 0; i < BUSH_POSITIONS.length; i++) {
        const bush = BUSH_POSITIONS[i];
        const isOccupied = bushes[i] !== null;

        ctx.beginPath();
        ctx.ellipse(bush.x, bush.y, 22, 28, 0, 0, Math.PI * 2);
        ctx.fillStyle = isOccupied ? '#2d6a1f' : '#3c8c2a';
        ctx.fill();
        ctx.fillStyle = '#1e4a12';
        ctx.beginPath();
        ctx.ellipse(bush.x - 5, bush.y - 5, 10, 12, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.ellipse(bush.x + 5, bush.y - 5, 10, 12, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#f7e6b2';
        ctx.font = "bold 14px monospace";
        ctx.fillText(`${i + 1}`, bush.x - 7, bush.y - 15);

        if (isOccupied) {
            ctx.fillStyle = '#ffd966';
            ctx.font = "16px monospace";
            ctx.fillText("🌿", bush.x - 8, bush.y + 5);
        }
    }

    if (npcs) {
        npcs.forEach(npc => {
            if (npc.type === 'good' && goodImage.complete && goodImage.naturalWidth > 0) {
                ctx.drawImage(goodImage, npc.x - 25, npc.y - 25, 50, 50);
            } else if (npc.type === 'evil' && evilImage.complete && evilImage.naturalWidth > 0) {
                ctx.drawImage(evilImage, npc.x - 25, npc.y - 25, 50, 50);
            }
        });
    }

    const seeker = currentPlayers.find(p => p.id === seekerId);
    if (seeker && (gameStatus === 'playing' || gameStatus === 'hiding_phase')) {
        ctx.fillStyle = '#ffbb77';
        ctx.beginPath();
        ctx.arc(400, 250, 22, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#5a3a1a';
        ctx.font = "bold 24px monospace";
        ctx.fillText("🔍", 388, 258);
        ctx.fillStyle = 'white';
        ctx.font = "12px monospace";
        ctx.fillText(seeker.name, 375, 225);
    }

    if (gameStatus === 'hiding_phase') {
        ctx.font = "bold 18px monospace";
        ctx.fillStyle = "#fff9c4";
        ctx.fillText(`⏱️ Прячьтесь! Кликни по кусту! Осталось ${timeLeft} секунд`, 20, 50);
        if (seekerId === myId) ctx.fillText("Ты водящий, жди окончания таймера", 20, 85);
    } else if (gameStatus === 'playing' && seekerId === myId) {
        ctx.font = "bold 18px monospace";
        ctx.fillStyle = "#fff9c4";
        ctx.fillText("🔎 ТЫ ВОДИШЬ! Ищи кликом по кусту", 20, 50);
    } else if (gameStatus === 'playing' && seekerId !== myId) {
        let me = currentPlayers.find(p => p.id === myId);
        if (me && me.isHidden) ctx.fillText("🌿 Ты спрятался в кусте, тебя ищут", 20, 50);
        else if (me) ctx.fillText("👀 Ты ещё не спрятался! Скорее выбирай куст!", 20, 50);
    }

    if (gameStatus === 'gameover' && winnerText) {
        ctx.font = "28px bold monospace";
        ctx.fillStyle = "#ffea80";
        ctx.shadowBlur = 6;
        ctx.fillText(winnerText, 200, 250);
    }
}

canvas.addEventListener('click', (e) => {
    const pos = getMousePos(e);
    const bushIndex = getBushIndex(pos.x, pos.y);
    if (bushIndex === -1) return;

    if (gameStatus === 'hiding_phase') {
        let me = currentPlayers.find(p => p.id === myId);
        if (!me) return;
        if (me.id === seekerId) {
            addLog("Ты водящий, не можешь прятаться!");
            return;
        }
        if (me.isHidden) {
            addLog("Ты уже спрятался!");
            return;
        }
        socket.emit('hide_in_bush', { bush_index: bushIndex });
    } else if (gameStatus === 'playing' && seekerId === myId) {
        socket.emit('seek', { bush_index: bushIndex });
    }
});

document.getElementById('setNameBtn')?.addEventListener('click', () => {
    let newName = document.getElementById('nickInput').value.trim();
    if (newName) socket.emit('set_name', { name: newName });
});
document.getElementById('startGameBtn')?.addEventListener('click', () => socket.emit('start_game'));
document.getElementById('resetGameBtn')?.addEventListener('click', () => socket.emit('reset_game'));
document.getElementById('seekBtn')?.addEventListener('click', () => {
    if (gameStatus === 'playing' && seekerId === myId) addLog("Кликни по кусту на карте, чтобы найти игрока");
    else if (gameStatus !== 'playing') addLog("Поиск доступен только после окончания времени пряток");
    else if (seekerId !== myId) addLog("Ты не водишь, не можешь искать");
});

setInterval(() => drawCanvas(), 50);