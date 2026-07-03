/**
 * UI 录制器 Content Script
 * 监听页面 DOM 事件，生成操作步骤并发送到 background.js
 */
class UIRecorder {
  constructor() {
    this.recording = false;
    this.sessionId = null;
    this.inputBuffer = { element: null, value: '', timer: null };
    this.lastUrl = location.href;
    this.boundHandlers = {};
  }

  start(sessionId) {
    if (this.recording) return;
    this.sessionId = sessionId;
    this.recording = true;
    this.lastUrl = location.href;

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

    window.addEventListener('popstate', this._onPopState.bind(this));
    window.addEventListener('hashchange', this._onHashChange.bind(this));

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

    clearTimeout(this.inputBuffer.timer);
    this.inputBuffer = { element: null, value: '', timer: null };

    this._hideIndicator();
    console.log('[UIRecorder] Recording stopped');
  }

  // ── 点击事件 ──
  handleClick(event) {
    if (!this.recording) return;
    const el = event.target;
    if (el.closest('[data-recorder-ignore]')) return;
    if (el.closest('#ui-recorder-indicator')) return;

    this.sendStep({
      action: 'click',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: this.getElementInfo(el),
      page_url: location.href,
      page_title: document.title,
      coordinates: { x: event.clientX, y: event.clientY },
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
      page_url: location.href,
      page_title: document.title,
    });
  }

  // ── 输入事件（防抖 500ms 合并连续输入） ──
  handleInput(event) {
    if (!this.recording) return;
    const el = event.target;
    if (!el.matches('input, textarea, [contenteditable]')) return;
    if (el.closest('[data-recorder-ignore]')) return;

    // 密码字段不记录值
    const isPassword = el.type === 'password';

    clearTimeout(this.inputBuffer.timer);
    this.inputBuffer.element = el;
    this.inputBuffer.value = isPassword ? '{{password}}' : (el.value || el.textContent || '');
    this.inputBuffer.isPassword = isPassword;

    this.inputBuffer.timer = setTimeout(() => {
      this.sendStep({
        action: 'type',
        selector: SelectorEngine.generate(this.inputBuffer.element),
        value: this.inputBuffer.value,
        element_info: this.getElementInfo(this.inputBuffer.element),
        page_url: location.href,
        page_title: document.title,
        input_type: this.inputBuffer.element.type || 'text',
        is_password: this.inputBuffer.isPassword,
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
        page_url: location.href,
        page_title: document.title,
      });
    }

    if (el.type === 'checkbox') {
      this.sendStep({
        action: el.checked ? 'check' : 'uncheck',
        selector: SelectorEngine.generate(el),
        value: String(el.checked),
        element_info: this.getElementInfo(el),
        page_url: location.href,
        page_title: document.title,
      });
    }

    if (el.type === 'radio') {
      this.sendStep({
        action: 'select_radio',
        selector: SelectorEngine.generate(el),
        value: el.value,
        element_info: this.getElementInfo(el),
        page_url: location.href,
        page_title: document.title,
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
      page_url: location.href,
      page_title: document.title,
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
      page_url: location.href,
      page_title: document.title,
      modifiers: {
        ctrl: event.ctrlKey,
        shift: event.shiftKey,
        alt: event.altKey,
        meta: event.metaKey,
      },
    });
  }

  // ── 页面导航 ──
  _onPopState() {
    if (!this.recording) return;
    this._sendNavigation('history_back_forward', this.lastUrl, location.href);
    this.lastUrl = location.href;
  }

  _onHashChange(event) {
    if (!this.recording) return;
    this._sendNavigation('hash_change', event.oldURL, event.newURL);
    this.lastUrl = location.href;
  }

  _sendNavigation(trigger, fromUrl, toUrl) {
    chrome.runtime.sendMessage({
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
    });
  }

  // ── 发送步骤到 background ──
  sendStep(data) {
    chrome.runtime.sendMessage({
      type: 'step',
      session_id: this.sessionId,
      timestamp: Date.now(),
      data: data,
    });
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
    window._uiRecorder.start(msg.session_id);
    sendResponse({ ok: true });
  } else if (msg.type === 'stop') {
    window._uiRecorder.stop();
    sendResponse({ ok: true });
  } else if (msg.type === 'status') {
    sendResponse({ recording: window._uiRecorder.recording, session_id: window._uiRecorder.sessionId });
  }
});
