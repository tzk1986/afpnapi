/**
 * UI 录制器 Background Service Worker
 * 管理录制会话，接收 content script 事件，POST 到 Flask 服务端
 */

// 录制状态
let recordingState = {
  active: false,
  sessionId: null,
  serverUrl: '',
  stepCount: 0,
  startTime: null,
};

// 初始化：从 storage 恢复 serverUrl
chrome.storage.local.get(['serverUrl'], (result) => {
  if (result.serverUrl) {
    recordingState.serverUrl = result.serverUrl;
  }
});

// 生成 session ID
function generateSessionId() {
  return 'rec_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8);
}

// 发送事件到 Flask 服务端
async function postEventToServer(eventType, data) {
  if (!recordingState.serverUrl || !recordingState.sessionId) return;

  const payload = {
    session_id: recordingState.sessionId,
    event_type: eventType,
    timestamp: Date.now(),
    data: data,
  };

  try {
    const response = await fetch(recordingState.serverUrl + '/api/ui-recorder/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      console.warn('[Background] POST event failed:', response.status);
    }
  } catch (err) {
    console.warn('[Background] POST event error:', err.message);
  }
}

// 启动录制
async function startRecording(serverUrl) {
  if (recordingState.active) return { ok: false, error: 'Already recording' };

  recordingState.serverUrl = serverUrl;
  recordingState.sessionId = generateSessionId();
  recordingState.active = true;
  recordingState.stepCount = 0;
  recordingState.startTime = Date.now();

  await chrome.storage.local.set({ serverUrl });

  // 通知服务端会话开始
  await postEventToServer('session_start', {
    session_id: recordingState.sessionId,
    start_time: recordingState.startTime,
  });

  // 向当前活动 tab 发送启动消息
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    try {
      await chrome.tabs.sendMessage(tab.id, {
        type: 'start',
        session_id: recordingState.sessionId,
      });
    } catch (e) {
      console.warn('[Background] Cannot send start to tab:', e.message);
    }
  }

  // 更新 badge
  chrome.action.setBadgeText({ text: 'REC' });
  chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });

  return { ok: true, session_id: recordingState.sessionId };
}

// 停止录制
async function stopRecording() {
  if (!recordingState.active) return { ok: false, error: 'Not recording' };

  // 通知所有 tab 停止录制
  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (tab.id) {
      try {
        await chrome.tabs.sendMessage(tab.id, { type: 'stop' });
      } catch (e) {
        // tab 可能没有 content script
      }
    }
  }

  // 通知服务端会话结束
  await postEventToServer('session_end', {
    session_id: recordingState.sessionId,
    end_time: Date.now(),
    total_steps: recordingState.stepCount,
    duration_ms: Date.now() - (recordingState.startTime || Date.now()),
  });

  recordingState.active = false;

  chrome.action.setBadgeText({ text: '' });

  return { ok: true, total_steps: recordingState.stepCount };
}

// 接收来自 content script 的消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'step' || msg.type === 'navigation') {
    if (!recordingState.active) return;

    recordingState.stepCount++;

    // 转发到服务端
    postEventToServer(msg.type, {
      ...msg.data,
      tab_id: sender.tab?.id,
      tab_url: sender.tab?.url,
      step_index: recordingState.stepCount,
    });

    sendResponse({ ok: true, step_index: recordingState.stepCount });
  }

  if (msg.type === 'get_state') {
    sendResponse({
      active: recordingState.active,
      session_id: recordingState.sessionId,
      server_url: recordingState.serverUrl,
      step_count: recordingState.stepCount,
      start_time: recordingState.startTime,
    });
  }

  if (msg.type === 'start_recording') {
    startRecording(msg.server_url).then(sendResponse);
    return true; // async response
  }

  if (msg.type === 'stop_recording') {
    stopRecording().then(sendResponse);
    return true;
  }
});

// 新 tab 创建时，如果正在录制，自动注入 content script 并启动
chrome.tabs.onCreated.addListener(async (tab) => {
  if (!recordingState.active) return;

  // 等待 tab 加载完成后发送启动消息
  chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo) {
    if (tabId === tab.id && changeInfo.status === 'complete') {
      chrome.tabs.onUpdated.removeListener(listener);
      chrome.tabs.sendMessage(tabId, {
        type: 'start',
        session_id: recordingState.sessionId,
      }).catch(() => {});

      // 记录新 tab 打开事件
      postEventToServer('step', {
        action: 'new_tab',
        tab_url: tab.url || '',
        page_url: tab.url || '',
        page_title: tab.title || '',
        step_index: ++recordingState.stepCount,
      });
    }
  });
});

// tab 导航完成时，自动启动录制
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!recordingState.active) return;
  if (changeInfo.status !== 'complete') return;

  chrome.tabs.sendMessage(tabId, {
    type: 'start',
    session_id: recordingState.sessionId,
  }).catch(() => {});
});
