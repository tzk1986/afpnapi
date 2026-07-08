/**
 * UI 录制器 Popup 控制面板
 */

// 从 manifest 动态读取版本号，避免硬编码遗漏
(function() {
  const m = chrome.runtime.getManifest();
  const versionEl = document.getElementById('versionLabel');
  if (versionEl) versionEl.textContent = 'v' + m.version;
})();

const serverUrlInput = document.getElementById('serverUrl');
const btnStart = document.getElementById('btnStart');
const btnStop = document.getElementById('btnStop');
const statusDot = document.getElementById('statusDot');
const stateText = document.getElementById('stateText');
const stepCountEl = document.getElementById('stepCount');
const durationEl = document.getElementById('duration');
const sessionIdEl = document.getElementById('sessionId');
const statusMsg = document.getElementById('statusMsg');

let refreshTimer = null;

// 初始化：加载保存的 serverUrl 和当前状态
async function init() {
  const stored = await chrome.storage.local.get(['serverUrl']);
  if (stored.serverUrl) {
    serverUrlInput.value = stored.serverUrl;
  } else {
    serverUrlInput.value = 'http://localhost:5000';
  }

  await refreshState();
}

// 从 background 获取当前录制状态
async function refreshState() {
  try {
    const state = await chrome.runtime.sendMessage({ type: 'get_state' });
    if (!state) {
      // sendMessage 返回 undefined，说明 background 未就绪
      updateUI({ active: false });
      showMsg('background 未就绪，请重试', 'error');
      return;
    }
    updateUI(state);
  } catch (e) {
    updateUI({ active: false });
    showMsg('无法连接 background', 'error');
  }
}

// 根据状态更新 UI
function updateUI(state) {
  if (state.active) {
    statusDot.classList.add('active');
    stateText.textContent = '录制中';
    stateText.style.color = '#ef4444';
    btnStart.disabled = true;
    btnStop.disabled = false;
    serverUrlInput.disabled = true;
    stepCountEl.textContent = state.step_count || 0;
    sessionIdEl.textContent = (state.session_id || '').substring(0, 16) + '...';

    if (state.start_time) {
      const elapsed = Math.floor((Date.now() - state.start_time) / 1000);
      const min = Math.floor(elapsed / 60);
      const sec = elapsed % 60;
      durationEl.textContent = min + ':' + String(sec).padStart(2, '0');
    }

    // 定时刷新步骤数和时长
    if (!refreshTimer) {
      refreshTimer = setInterval(refreshState, 1000);
    }
  } else {
    statusDot.classList.remove('active');
    stateText.textContent = '未录制';
    stateText.style.color = '';
    btnStart.disabled = false;
    btnStop.disabled = true;
    serverUrlInput.disabled = false;
    sessionIdEl.textContent = '--';
    durationEl.textContent = '--';

    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }
}

// 开始录制
btnStart.addEventListener('click', async () => {
  const url = serverUrlInput.value.trim().replace(/\/+$/, '');
  if (!url) {
    showMsg('请输入服务端地址', 'error');
    return;
  }

  btnStart.disabled = true;
  showMsg('正在启动录制...');

  try {
    const result = await chrome.runtime.sendMessage({
      type: 'start_recording',
      server_url: url,
    });

    if (result && result.ok) {
      showMsg('录制已开始', 'success');
      await refreshState();
    } else {
      showMsg(result?.error || '启动失败', 'error');
      btnStart.disabled = false;
    }
  } catch (e) {
    showMsg('启动失败: ' + e.message, 'error');
    btnStart.disabled = false;
  }
});

// 停止录制
btnStop.addEventListener('click', async () => {
  btnStop.disabled = true;
  showMsg('正在停止录制...');

  try {
    const result = await chrome.runtime.sendMessage({ type: 'stop_recording' });

    if (result && result.ok) {
      showMsg('录制已停止，共 ' + result.total_steps + ' 步', 'success');
      stepCountEl.textContent = result.total_steps || 0;
      updateUI({ active: false });
    } else {
      showMsg(result?.error || '停止失败', 'error');
      btnStop.disabled = false;
    }
  } catch (e) {
    updateUI({ active: false });
    showMsg('停止请求已发送', 'success');
  }
});

function showMsg(text, type) {
  statusMsg.textContent = text;
  statusMsg.className = 'status-msg' + (type ? ' ' + type : '');
}

init();
