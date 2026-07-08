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

// 从代理 URL 中提取真实目标 URL
function _extractTargetUrl(url) {
  if (!url) return url;
  try {
    const u = new URL(url);
    // 检查是否为代理 URL（包含 /ui-testing/proxy 或 /ui-testing/proxy-resource）
    if (u.pathname.startsWith('/ui-testing/proxy')) {
      const proxyUrl = u.searchParams.get('url');
      if (proxyUrl) {
        // 递归处理嵌套代理
        return _extractTargetUrl(decodeURIComponent(proxyUrl));
      }
    }
    // 不是代理 URL，直接返回
    return url;
  } catch (e) {
    // URL 解析失败，返回原始 URL
    return url;
  }
}

// 持久化状态到 local storage（Service Worker 被杀后可恢复）
function _persistState() {
  try {
    chrome.storage.local.set({
      _recState: {
        active: recordingState.active,
        sessionId: recordingState.sessionId,
        serverUrl: recordingState.serverUrl,
        stepCount: recordingState.stepCount,
        startTime: recordingState.startTime,
      }
    });
  } catch (e) {
    console.warn('[Background] _persistState error:', e.message);
  }
}

// 初始化：从 local storage 恢复 serverUrl，录制状态一律从零开始
chrome.storage.local.get(['serverUrl'], (result) => {
  if (result.serverUrl) {
    recordingState.serverUrl = result.serverUrl;
  }
  // 强制清除所有残留的录制状态（包括可能的脏数据）
  chrome.storage.local.remove('_recState');
  chrome.action.setBadgeText({ text: '' });
  console.log('[Background] Initialized fresh, serverUrl:', recordingState.serverUrl);
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
  console.log('[Background] Active tab:', tab?.id, tab?.url);
  if (tab?.id) {
    try {
      const resp = await chrome.tabs.sendMessage(tab.id, {
        type: 'start',
        session_id: recordingState.sessionId,
      });
      console.log('[Background] Content script start response:', resp);
    } catch (e) {
      console.warn('[Background] Cannot send start to tab:', tab.id, e.message);
      // 尝试注入 content script 后重试
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content/selector-engine.js', 'content/recorder.js'],
        });
        await new Promise(r => setTimeout(r, 200));
        const resp2 = await chrome.tabs.sendMessage(tab.id, {
          type: 'start',
          session_id: recordingState.sessionId,
        });
        console.log('[Background] Content script start response (after inject):', resp2);
      } catch (e2) {
        console.warn('[Background] Inject + retry failed:', e2.message);
      }
    }
  }

  // 更新 badge
  chrome.action.setBadgeText({ text: 'REC' });
  chrome.action.setBadgeBackgroundColor({ color: '#ef4444' });

  _persistState();

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

  _persistState();

  return { ok: true, total_steps: recordingState.stepCount };
}

// 接收来自 content script 的消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'heartbeat') {
    sendResponse({ active: recordingState.active, session_id: recordingState.sessionId });
    return true;
  }

  if (msg.type === 'step' || msg.type === 'navigation') {
    if (!recordingState.active) {
      sendResponse({ ok: false, error: 'not_recording' });
      return true;
    }
    recordingState.stepCount++;
    _persistState();
    postEventToServer(msg.type, { ...msg.data, tab_id: sender.tab?.id, tab_url: sender.tab?.url, step_index: recordingState.stepCount });
    sendResponse({ ok: true, step_index: recordingState.stepCount });
    return true;
  }

  if (msg.type === 'check_recording') {
    sendResponse({ active: recordingState.active, session_id: recordingState.sessionId });
    return true;
  }

  if (msg.type === 'get_state') {
    sendResponse({
      active: recordingState.active,
      session_id: recordingState.sessionId,
      server_url: recordingState.serverUrl,
      step_count: recordingState.stepCount,
      start_time: recordingState.startTime,
    });
    return true;
  }

  if (msg.type === 'start_recording') {
    startRecording(msg.server_url).then(function(r) { sendResponse(r); }).catch(function(e) {
      console.error('[Background] startRecording error:', e);
      sendResponse({ ok: false, error: e.message || String(e) });
    });
    return true;
  }

  if (msg.type === 'stop_recording') {
    const wasSessionId = recordingState.sessionId;
    const wasStepCount = recordingState.stepCount;
    const wasStartTime = recordingState.startTime;
    recordingState.active = false;
    chrome.action.setBadgeText({ text: '' });
    _persistState();

    postEventToServer('session_end', {
      session_id: wasSessionId,
      end_time: Date.now(),
      total_steps: wasStepCount,
    }).catch(function() {});

    chrome.tabs.query({}).then(function(tabs) {
      tabs.forEach(function(tab) {
        if (tab.id) chrome.tabs.sendMessage(tab.id, { type: 'stop' }).catch(function() {});
      });
    }).catch(function() {});

    sendResponse({
      ok: true,
      total_steps: wasStepCount,
      session_id: wasSessionId,
      start_time: wasStartTime,
    });
    return true;
  }

  sendResponse({ ok: false, error: 'unknown_message' });
  return true;
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
        page_url: _extractTargetUrl(tab.url) || '',
        page_title: tab.title || '',
        step_index: ++recordingState.stepCount,
      });
      _persistState();
    }
  });
});

// tab 导航完成时，确保 content script 存在并启动录制
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!recordingState.active) return;
  if (changeInfo.status !== 'complete') return;

  // 跳过 chrome:// 和 edge:// 等内部页面
  const url = tab.url || '';
  if (!url.startsWith('http://') && !url.startsWith('https://')) return;

  try {
    // 先尝试发送消息，如果 content script 不存在会报错
    await chrome.tabs.sendMessage(tabId, {
      type: 'start',
      session_id: recordingState.sessionId,
    });
  } catch (e) {
    // content script 不存在，注入后重试
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['content/selector-engine.js', 'content/recorder.js'],
      });
      await new Promise(r => setTimeout(r, 200));
      await chrome.tabs.sendMessage(tabId, {
        type: 'start',
        session_id: recordingState.sessionId,
      });
      console.log('[Background] Injected + started on tab:', tabId, url);
    } catch (e2) {
      console.warn('[Background] Failed to inject on tab:', tabId, e2.message);
    }
  }
});

// 扩展安装/更新时，注入到所有已打开的 tab
chrome.runtime.onInstalled.addListener(async () => {
  const tabs = await chrome.tabs.query({ url: ['http://*/*', 'https://*/*'] });
  for (const tab of tabs) {
    if (!tab.id) continue;
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content/selector-engine.js', 'content/recorder.js'],
      });
    } catch (e) {
      // 忽略无法注入的 tab
    }
  }
  console.log('[Background] Content scripts injected into', tabs.length, 'tabs');
});
