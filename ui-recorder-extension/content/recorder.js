/**
 * UI 录制器 Content Script
 * 监听页面 DOM 事件，生成操作步骤并发送到 background.js
 */

// 从代理 URL 中提取真实目标 URL（处理早期脚本未注入时的情况）
function _getTargetUrl() {
  try {
    const href = window.location.href;
    const u = new URL(href);
    // 检查是否为代理 URL
    if (u.pathname.startsWith('/ui-testing/proxy')) {
      const proxyUrl = u.searchParams.get('url');
      if (proxyUrl) {
        return decodeURIComponent(proxyUrl);
      }
    }
    // 不是代理 URL，直接返回
    return href;
  } catch (e) {
    return window.location.href;
  }
}

class UIRecorder {
  constructor() {
    this.recording = false;
    this.sessionId = null;
    this.inputBuffer = { element: null, value: '', timer: null };
    this.lastUrl = _getTargetUrl();
    this.boundHandlers = {};
    this._heartbeatTimer = null;
    this._pendingSteps = [];
    this._pushStatePatched = false;
  }

  start(sessionId) {
    if (this.recording) return;
    this.sessionId = sessionId;
    this.recording = true;
    this.lastUrl = _getTargetUrl();

    const events = [
      ['click', this.handleClick, true],
      ['dblclick', this.handleDblClick, true],
      ['input', this.handleInput, true],
      ['change', this.handleChange, true],
      ['submit', this.handleSubmit, true],
      ['keydown', this.handleKeydown, true],
    ];
    events.forEach(([evt, fn, capture]) => {
      const bound = fn.bind(this);
      document.addEventListener(evt, bound, capture);
      this.boundHandlers[evt] = bound;
    });

    this._onPopStateBound = this._onPopState.bind(this);
    this._onHashChangeBound = this._onHashChange.bind(this);
    window.addEventListener('popstate', this._onPopStateBound);
    window.addEventListener('hashchange', this._onHashChangeBound);

    this._patchHistoryAPI();
    this._startHeartbeat();
    this._showIndicator();
    console.log('[UIRecorder] Recording started, session:', sessionId);
  }

  stop() {
    if (!this.recording) return;
    this.recording = false;

    Object.entries(this.boundHandlers).forEach(([evt, fn]) => {
      document.removeEventListener(evt, fn, true);
    });
    this.boundHandlers = {};

    if (this._onPopStateBound) {
      window.removeEventListener('popstate', this._onPopStateBound);
    }
    if (this._onHashChangeBound) {
      window.removeEventListener('hashchange', this._onHashChangeBound);
    }

    this._stopHeartbeat();
    clearTimeout(this.inputBuffer.timer);
    this.inputBuffer = { element: null, value: '', timer: null };

    this._hideIndicator();
    console.log('[UIRecorder] Recording stopped');
  }

  // ── 点击事件 ──
  handleClick(event) {
    if (!this.recording) return;
    const el = event.target;
    console.log('[UIRecorder] Click captured:', el.tagName, el.id || el.className || '');
    if (el.closest('[data-recorder-ignore]')) return;
    if (el.closest('#ui-recorder-indicator')) return;

    this.sendStep({
      action: 'click',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: this.getElementInfo(el),
      page_url: _getTargetUrl(),
      page_title: document.title,
      coordinates: { x: event.clientX, y: event.clientY },
      // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
      // 修复完成后请注释或删除此字段
      actual_url: el.href || (el.closest('a')?.href) || (el.closest('form')?.action) || '',
    });
  }

  handleDblClick(event) {
    if (!this.recording) return;
    const el = event.target;
    if (el.closest('[data-recorder-ignore]')) return;

    this.sendStep({
      action: 'dblclick',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: this.getElementInfo(el),
      page_url: _getTargetUrl(),
      page_title: document.title,
      // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
      // 修复完成后请注释或删除此字段
      actual_url: el.href || (el.closest('a')?.href) || (el.closest('form')?.action) || '',
    });
  }

  // ── 输入事件（防抖 500ms 合并连续输入） ──
  handleInput(event) {
    if (!this.recording) return;
    const el = event.target;
    if (!el.matches('input, textarea, [contenteditable]')) return;
    if (el.closest('[data-recorder-ignore]')) return;

    const isPassword = el.type === 'password';

    clearTimeout(this.inputBuffer.timer);
    this.inputBuffer.element = el;
    this.inputBuffer.value = el.value || el.textContent || '';
    this.inputBuffer.isPassword = isPassword;

    this.inputBuffer.timer = setTimeout(() => {
      this.sendStep({
        action: 'type',
        selector: SelectorEngine.generate(this.inputBuffer.element),
        value: this.inputBuffer.value,
        element_info: this.getElementInfo(this.inputBuffer.element),
        page_url: _getTargetUrl(),
        page_title: document.title,
        input_type: this.inputBuffer.element.type || 'text',
        is_password: this.inputBuffer.isPassword,
        // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
        // 修复完成后请注释或删除此字段
        actual_url: (this.inputBuffer.element.closest('form')?.action) || '',
      });
      this.inputBuffer = { element: null, value: '', timer: null };
    }, 500);
  }

  // ── 下拉选择 + checkbox/radio ──
  handleChange(event) {
    if (!this.recording) return;
    const el = event.target;
    if (el.closest('[data-recorder-ignore]')) return;

    if (el.tagName === 'SELECT') {
      const selectedOption = el.options[el.selectedIndex];
      this.sendStep({
        action: 'select',
        selector: SelectorEngine.generate(el),
        value: el.value,
        element_info: {
          ...this.getElementInfo(el),
          selected_text: selectedOption ? selectedOption.text : '',
        },
        page_url: _getTargetUrl(),
        page_title: document.title,
        // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
        // 修复完成后请注释或删除此字段
        actual_url: (el.closest('form')?.action) || '',
      });
    }

    if (el.type === 'checkbox') {
      this.sendStep({
        action: el.checked ? 'check' : 'uncheck',
        selector: SelectorEngine.generate(el),
        value: String(el.checked),
        element_info: this.getElementInfo(el),
        page_url: _getTargetUrl(),
        page_title: document.title,
        // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
        // 修复完成后请注释或删除此字段
        actual_url: (el.closest('form')?.action) || '',
      });
    }

    if (el.type === 'radio') {
      this.sendStep({
        action: 'select_radio',
        selector: SelectorEngine.generate(el),
        value: el.value,
        element_info: this.getElementInfo(el),
        page_url: _getTargetUrl(),
        page_title: document.title,
        // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
        // 修复完成后请注释或删除此字段
        actual_url: (el.closest('form')?.action) || '',
      });
    }
  }

  // ── 表单提交 ──
  handleSubmit(event) {
    if (!this.recording) return;
    this.sendStep({
      action: 'submit',
      selector: SelectorEngine.generate(event.target),
      value: '',
      element_info: this.getElementInfo(event.target),
      page_url: _getTargetUrl(),
      page_title: document.title,
      // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
      // 修复完成后请注释或删除此字段
      actual_url: event.target.action || (event.target.closest('form')?.action) || '',
    });
  }

  // ── 键盘事件（仅特殊键） ──
  handleKeydown(event) {
    if (!this.recording) return;
    const specialKeys = ['Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Delete', 'Backspace'];
    if (!specialKeys.includes(event.key)) return;
    if (event.target.closest('[data-recorder-ignore]')) return;
    // 输入框内的 Enter 由 submit 事件处理
    if (event.key === 'Enter' && event.target.matches('input, textarea')) return;

    this.sendStep({
      action: 'keypress',
      selector: SelectorEngine.generate(event.target),
      value: event.key,
      element_info: this.getElementInfo(event.target),
      page_url: _getTargetUrl(),
      page_title: document.title,
      modifiers: {
        ctrl: event.ctrlKey,
        shift: event.shiftKey,
        alt: event.altKey,
        meta: event.metaKey,
      },
      // TODO: 调试用 — 记录实际请求地址，用于回放时比对验证
      // 修复完成后请注释或删除此字段
      actual_url: (event.target.closest('form')?.action) || '',
    });
  }

  // ── 拦截 history.pushState / replaceState（SPA 路由） ──
  _patchHistoryAPI() {
    if (this._pushStatePatched) return;
    this._pushStatePatched = true;

    const self = this;
    const origPush = history.pushState;
    const origReplace = history.replaceState;

    history.pushState = function (...args) {
      const beforeUrl = _getTargetUrl();
      const result = origPush.apply(this, args);
      const afterUrl = _getTargetUrl();
      if (self.recording && beforeUrl !== afterUrl) {
        self._sendNavigation('pushState', beforeUrl, afterUrl);
        self.lastUrl = afterUrl;
      }
      return result;
    };

    history.replaceState = function (...args) {
      const beforeUrl = _getTargetUrl();
      const result = origReplace.apply(this, args);
      const afterUrl = _getTargetUrl();
      if (self.recording && beforeUrl !== afterUrl) {
        self._sendNavigation('replaceState', beforeUrl, afterUrl);
        self.lastUrl = afterUrl;
      }
      return result;
    };

    console.log('[UIRecorder] History API patched for SPA navigation');
  }

  // ── 心跳机制：防止 Service Worker 在录制期间被杀 ──
  _startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatTimer = setInterval(() => {
      if (!this.recording) return;
      try {
        chrome.runtime.sendMessage({ type: 'heartbeat', session_id: this.sessionId }, () => {
          if (chrome.runtime.lastError) {
            console.warn('[UIRecorder] Heartbeat error:', chrome.runtime.lastError.message);
          }
        });
      } catch (e) {
        console.warn('[UIRecorder] Heartbeat exception:', e.message);
      }
    }, 15000);
  }

  _stopHeartbeat() {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
  }

  // ── 页面导航 ──
  _onPopState() {
    if (!this.recording) return;
    this._sendNavigation('history_back_forward', this.lastUrl, _getTargetUrl());
    this.lastUrl = _getTargetUrl();
  }

  _onHashChange(event) {
    if (!this.recording) return;
    this._sendNavigation('hash_change', event.oldURL, event.newURL);
    this.lastUrl = _getTargetUrl();
  }

  _sendNavigation(trigger, fromUrl, toUrl) {
    const msg = {
      type: 'navigation',
      session_id: this.sessionId,
      timestamp: Date.now(),
      data: {
        action: 'navigate',
        trigger: trigger,
        from_url: fromUrl,
        to_url: toUrl,
        is_new_tab: false,
        is_new_window: false,
        page_url: toUrl,
        page_title: document.title,
      },
    };
    this._sendMessageWithRetry(msg, 0);
  }

  // ── 发送步骤到 background（带重试和队列） ──
  sendStep(data) {
    const msg = {
      type: 'step',
      session_id: this.sessionId,
      timestamp: Date.now(),
      data: data,
    };
    this._sendMessageWithRetry(msg, 0);
  }

  _sendMessageWithRetry(msg, attempt) {
    const maxRetries = 3;
    try {
      chrome.runtime.sendMessage(msg, (response) => {
        if (chrome.runtime.lastError) {
          const errMsg = chrome.runtime.lastError.message || '';
          console.warn(`[UIRecorder] sendStep error (attempt ${attempt + 1}):`, errMsg, 'action:', msg.data?.action);
          if (attempt < maxRetries) {
            const delay = (attempt + 1) * 500;
            setTimeout(() => this._sendMessageWithRetry(msg, attempt + 1), delay);
          } else {
            this._pendingSteps.push(msg);
            console.warn('[UIRecorder] Step queued for later, pending count:', this._pendingSteps.length);
          }
        } else {
          this._flushPendingSteps();
        }
      });
    } catch (e) {
      console.warn('[UIRecorder] sendStep exception:', e.message);
      if (attempt < maxRetries) {
        setTimeout(() => this._sendMessageWithRetry(msg, attempt + 1), 1000);
      } else {
        this._pendingSteps.push(msg);
      }
    }
  }

  _flushPendingSteps() {
    if (this._pendingSteps.length === 0) return;
    const pending = this._pendingSteps.splice(0);
    console.log('[UIRecorder] Flushing pending steps:', pending.length);
    for (const msg of pending) {
      this._sendMessageWithRetry(msg, 0);
    }
  }

  getElementInfo(el) {
    return {
      tag: el.tagName.toLowerCase(),
      text: (el.textContent || '').trim().substring(0, 100),
      type: el.type || '',
      href: el.href || '',
      name: el.name || '',
      placeholder: el.placeholder || '',
      visible: el.offsetParent !== null,
      aria_label: el.getAttribute('aria-label') || '',
      test_id: el.getAttribute('data-testid') || '',
    };
  }

  // ── 录制状态指示器 ──
  _showIndicator() {
    if (document.getElementById('ui-recorder-indicator')) return;
    const div = document.createElement('div');
    div.id = 'ui-recorder-indicator';
    div.setAttribute('data-recorder-ignore', 'true');
    div.style.cssText = 'position:fixed;top:8px;right:8px;z-index:2147483647;background:#ef4444;color:#fff;padding:4px 12px;border-radius:4px;font-size:12px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.2);display:flex;align-items:center;gap:6px;';
    div.innerHTML = '<span style="display:inline-block;width:8px;height:8px;background:#fff;border-radius:50%;animation:ui-rec-pulse 1s infinite;"></span> 录制中';
    const style = document.createElement('style');
    style.textContent = '@keyframes ui-rec-pulse{0%,100%{opacity:1}50%{opacity:0.3}}';
    div.appendChild(style);
    document.documentElement.appendChild(div);
  }

  _hideIndicator() {
    const el = document.getElementById('ui-recorder-indicator');
    if (el) el.remove();
  }
}

// 全局实例
window._uiRecorder = new UIRecorder();

// 监听来自 background 的控制消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'start') {
    console.log('[UIRecorder] Received start message, session:', msg.session_id);
    window._uiRecorder.start(msg.session_id);
    sendResponse({ ok: true });
  } else if (msg.type === 'stop') {
    console.log('[UIRecorder] Received stop message');
    window._uiRecorder.stop();
    sendResponse({ ok: true });
  } else if (msg.type === 'status') {
    sendResponse({ recording: window._uiRecorder.recording, session_id: window._uiRecorder.sessionId });
  }
});

// 页面加载后主动检查录制状态 — 确保导航后自动恢复录制
console.log('[UIRecorder] Content script loaded on:', _getTargetUrl());
try {
  chrome.runtime.sendMessage({ type: 'check_recording' }, (response) => {
    if (chrome.runtime.lastError) {
      console.warn('[UIRecorder] check_recording error:', chrome.runtime.lastError.message);
      // Service Worker 可能还没就绪，延迟重试
      setTimeout(() => {
        try {
          chrome.runtime.sendMessage({ type: 'check_recording' }, (resp2) => {
            if (chrome.runtime.lastError) return;
            if (resp2 && resp2.active && resp2.session_id) {
              console.log('[UIRecorder] Auto-resuming recording (retry):', resp2.session_id);
              window._uiRecorder.start(resp2.session_id);
            }
          });
        } catch (e) {}
      }, 500);
      return;
    }
    if (response && response.active && response.session_id) {
      console.log('[UIRecorder] Auto-resuming recording:', response.session_id);
      window._uiRecorder.start(response.session_id);
    } else {
      console.log('[UIRecorder] No active recording');
    }
  });
} catch (e) {
  console.warn('[UIRecorder] check_recording exception:', e.message);
}
