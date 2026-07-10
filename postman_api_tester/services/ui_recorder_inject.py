"""录制器注入脚本生成器。

生成内联注入到代理页面的 JavaScript 代码，
负责事件捕获、选择器生成和与父页面的 postMessage 通信。
同时提供回放引擎 JS 生成（get_replayer_js）。
"""


def get_early_recorder_js() -> str:
    """返回早期注入的 JavaScript 代码（在 <head> 中，Vue.js 之前）。"""
    return _EARLY_RECORDER_JS


def get_recorder_js(origin: str = "") -> str:
    """返回完整的录制器 JavaScript 代码。"""
    code = _RECORDER_JS
    origin_decl = '\n  var _PROXY_ORIGIN = "' + origin + '";'
    code = code.replace("'use strict';", "'use strict';" + origin_decl, 1)
    return code


_EARLY_RECORDER_JS = r"""
(function() {
  'use strict';
  console.log('[EarlyRecorder] Script starting...');
  // 早期事件捕获器 — 在 Vue.js 等框架初始化之前捕获事件
  // 注入到 <head>，确保最先执行

  // 全局事件队列，主录制器脚本会消费这些事件
  window.__UI_RECORDER_EVENT_QUEUE = window.__UI_RECORDER_EVENT_QUEUE || [];
  console.log('[EarlyRecorder] Event queue initialized');

  // 录制状态（从 sessionStorage 恢复）
  // 使用全局变量，主脚本也能访问
  window.__UI_RECORDER_RECORDING = false;
  var _recordingActive = false;
  try {
    var _active = sessionStorage.getItem('_ui_rec_active');
    if (_active === '1') {
      _recordingActive = true;
      window.__UI_RECORDER_RECORDING = true;
      console.log('[EarlyRecorder] Recording active from sessionStorage');
    }
  } catch(e) {
    console.warn('[EarlyRecorder] sessionStorage access failed:', e);
  }

  // 监听来自父页面的控制消息（用于启动/停止录制）
  window.addEventListener('message', function(e) {
    console.log('[EarlyRecorder] Message received:', e.data);
    if (e.data && e.data.type === 'ui-recorder-control') {
      if (e.data.action === 'start') {
        _recordingActive = true;
        window.__UI_RECORDER_RECORDING = true;
        try {
          sessionStorage.setItem('_ui_rec_active', '1');
        } catch(e) {}
        console.log('[EarlyRecorder] Recording started via message, _recordingActive=', _recordingActive, 'global=', window.__UI_RECORDER_RECORDING);
      } else if (e.data.action === 'stop') {
        _recordingActive = false;
        window.__UI_RECORDER_RECORDING = false;
        try {
          sessionStorage.removeItem('_ui_rec_active');
        } catch(e) {}
        console.log('[EarlyRecorder] Recording stopped via message');
      }
    }
  });

  // 捕获事件并保存到队列
  function captureEvent(type, e) {
    console.log('[EarlyRecorder] captureEvent called:', type, 'recordingActive=', _recordingActive);
    if (!_recordingActive) {
      console.log('[EarlyRecorder] Event ignored (not recording)');
      return;
    }

    var el = e.target;
    if (!el || !el.tagName) {
      console.log('[EarlyRecorder] Event ignored (no valid target)');
      return;
    }

    console.log('[EarlyRecorder] Capturing event:', type, el.tagName, el.type);

    // 立即提取所有需要的数据（事件对象会被浏览器回收）
    var eventData = {
      type: type,
      timestamp: Date.now(),
      tagName: el.tagName.toLowerCase(),
      tagType: el.type || '',
      tagText: (el.textContent || '').trim().substring(0, 100),
      tagValue: el.value || '',
      tagChecked: el.checked || false,
      tagHref: el.href || '',
      tagName2: el.name || '',
      tagPlaceholder: el.placeholder || '',
      tagId: el.id || '',
      tagClass: el.className || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      testId: el.getAttribute('data-testid') || '',
      // 鼠标位置
      clientX: e.clientX || 0,
      clientY: e.clientY || 0,
      // 键盘按键
      key: e.key || '',
      ctrlKey: e.ctrlKey || false,
      shiftKey: e.shiftKey || false,
      altKey: e.altKey || false,
      metaKey: e.metaKey || false,
      // 页面信息
      pageUrl: location.href,
      pageTitle: document.title,
      // 元素引用（用于主脚本查找）
      _targetRef: el
    };

    window.__UI_RECORDER_EVENT_QUEUE.push(eventData);
    console.log('[EarlyRecorder] Event captured and queued:', type, el.tagName, 'queue length:', window.__UI_RECORDER_EVENT_QUEUE.length);
  }

  // 在 capture 阶段捕获所有事件（最先执行，框架无法阻止）
  var eventTypes = ['click', 'dblclick', 'input', 'change', 'submit', 'keydown'];
  var captureOptions = { capture: true, passive: true };

  for (var i = 0; i < eventTypes.length; i++) {
    (function(type) {
      window.addEventListener(type, function(e) {
        captureEvent(type, e);
      }, captureOptions);
    })(eventTypes[i]);
  }

  console.log('[EarlyRecorder] Early event capture installed, listeners:', eventTypes.join(', '));
})();
"""

_RECORDER_JS = r"""
(function() {
  'use strict';

  // ====== 选择器引擎（内联版）======
  var SelectorEngine = {
    generate: function(el) {
      var strategies = [
        function() { return SelectorEngine.byTestId(el); },
        function() { return SelectorEngine.byAriaRole(el); },
        function() { return SelectorEngine.byText(el); },
        function() { return SelectorEngine.byId(el); },
        function() { return SelectorEngine.byNameAttr(el); },
        function() { return SelectorEngine.byCssShort(el); },
        function() { return SelectorEngine.byXPath(el); }
      ];
      var primary = null;
      for (var i = 0; i < strategies.length; i++) {
        var result = strategies[i]();
        if (result) { primary = result; break; }
      }
      if (!primary) primary = SelectorEngine.byXPath(el);
      var fallbackCss = (SelectorEngine.byId(el) || SelectorEngine.byCssShort(el) || {}).selector || '';
      var fallbackXpath = (SelectorEngine.byXPath(el) || {}).selector || '';
      return { primary: primary.selector, strategy: primary.strategy, fallback_css: fallbackCss, fallback_xpath: fallbackXpath };
    },
    byTestId: function(el) {
      var id = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy');
      if (id) return { selector: '[data-testid="' + id + '"]', strategy: 'test-id' };
      return null;
    },
    byAriaRole: function(el) {
      var role = el.getAttribute('role') || SelectorEngine._inferRole(el);
      var name = (el.getAttribute('aria-label') || (el.textContent || '').trim().substring(0, 50)).trim();
      if (role && name) return { selector: 'role=' + role + '[name="' + name + '"]', strategy: 'role' };
      return null;
    },
    byText: function(el) {
      var text = (el.textContent || '').trim();
      if (text && text.length > 0 && text.length <= 50 && el.children.length === 0) {
        return { selector: 'text="' + text.replace(/"/g, '\\"') + '"', strategy: 'text' };
      }
      return null;
    },
    byId: function(el) {
      if (el.id && !/^\d/.test(el.id) && el.id.indexOf(':') === -1) {
        return { selector: '#' + SelectorEngine._escapeCss(el.id), strategy: 'id' };
      }
      return null;
    },
    byNameAttr: function(el) {
      var name = el.getAttribute('name');
      if (name) return { selector: '[name="' + name + '"]', strategy: 'name' };
      return null;
    },
    byCssShort: function(el) {
      var path = [];
      var current = el;
      while (current && current !== document.body && current !== document.documentElement) {
        var segment = current.tagName.toLowerCase();
        if (current.id) {
          segment = '#' + SelectorEngine._escapeCss(current.id);
          path.unshift(segment);
          break;
        }
        var classList = current.classList;
        if (classList && classList.length > 0) {
          var classes = Array.from(classList).slice(0, 2).map(function(c) { return '.' + SelectorEngine._escapeCss(c); }).join('');
          segment += classes;
        }
        var parent = current.parentElement;
        if (parent) {
          var siblings = Array.from(parent.children).filter(function(c) { return c.tagName === current.tagName; });
          if (siblings.length > 1) {
            var index = siblings.indexOf(current) + 1;
            segment += ':nth-of-type(' + index + ')';
          }
        }
        path.unshift(segment);
        current = current.parentElement;
        var candidate = path.join(' > ');
        try { if (document.querySelectorAll(candidate).length === 1) break; } catch(e) { break; }
      }
      var selector = path.join(' > ');
      return selector ? { selector: selector, strategy: 'css' } : null;
    },
    byXPath: function(el) {
      var parts = [];
      var current = el;
      while (current && current.nodeType === Node.ELEMENT_NODE) {
        var index = 0;
        var sibling = current.previousSibling;
        while (sibling) {
          if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === current.tagName) index++;
          sibling = sibling.previousSibling;
        }
        var tagName = current.tagName.toLowerCase();
        var part = index > 0 ? tagName + '[' + (index + 1) + ']' : tagName;
        parts.unshift(part);
        current = current.parentNode;
        if (current === document) break;
      }
      return { selector: '/' + parts.join('/'), strategy: 'xpath' };
    },
    _inferRole: function(el) {
      var tag = el.tagName.toLowerCase();
      var type = (el.type || '').toLowerCase();
      if (tag === 'button') return 'button';
      if (tag === 'a') return 'link';
      if (tag === 'input' && ['text','password','email','search','tel','url','number'].indexOf(type) >= 0) return 'textbox';
      if (tag === 'input' && type === 'checkbox') return 'checkbox';
      if (tag === 'input' && type === 'radio') return 'radio';
      if (tag === 'select') return 'combobox';
      if (tag === 'textarea') return 'textbox';
      if (tag === 'img') return 'img';
      if (tag === 'nav') return 'navigation';
      if (tag === 'form') return 'form';
      return null;
    },
    _escapeCss: function(str) {
      if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(str);
      return str.replace(/([^\w-])/g, '\\$1');
    }
  };

  // ====== 录制器 ======
  var recording = false;
  var inputBuffer = { element: null, value: '', timer: null, isPassword: false };

  // 会话管理 — 跨页面导航保持同一录制会话
  var _sessionId = 'rec_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  var _isResumed = false;
  try {
    var _stored = sessionStorage.getItem('_ui_rec_session_id');
    var _active = sessionStorage.getItem('_ui_rec_active');
    if (_stored && _active === '1') {
      _sessionId = _stored;
      recording = true;
      _isResumed = true;
      console.log('[UIRecorder] Resumed session:', _sessionId);
    }
  } catch(e) {}

  // ====== 事件队列处理器 ======
  // 消费早期注入脚本捕获的事件
  var _queueProcessed = 0;
  console.log('[UIRecorder] Queue processor initializing');

  function _processEventQueue() {
    if (!window.__UI_RECORDER_EVENT_QUEUE) {
      console.log('[UIRecorder] Queue processor: no queue found');
      return;
    }
    var queue = window.__UI_RECORDER_EVENT_QUEUE;

    // 使用全局录制状态（早期脚本设置）
    var isRecording = recording || (window.__UI_RECORDER_RECORDING === true);

    if (queue.length > _queueProcessed) {
      console.log('[UIRecorder] Queue processor: found', queue.length - _queueProcessed, 'new events, recording=', isRecording);
    }

    while (_queueProcessed < queue.length) {
      var eventData = queue[_queueProcessed];
      _queueProcessed++;

      if (!isRecording) {
        console.log('[UIRecorder] Queue processor: skipping event (not recording)');
        continue;
      }

      console.log('[UIRecorder] Queue processor: processing event', eventData.type, eventData.tagName);

      // 使用缓存的元素引用
      var el = eventData._targetRef;
      if (!el || !el.tagName) {
        console.log('[UIRecorder] Queue processor: skipping (no valid element)');
        continue;
      }

      // 检查元素是否仍在 DOM 中（Vue 可能已重新渲染）
      if (!document.contains(el)) {
        console.log('[UIRecorder] Queue processor: element removed from DOM, skipping');
        continue;
      }

      // 根据事件类型分发处理
      if (eventData.type === 'click') {
        console.log('[UIRecorder] Queue processor: handling click');
        _handleCapturedClick(eventData, el);
      } else if (eventData.type === 'dblclick') {
        console.log('[UIRecorder] Queue processor: handling dblclick');
        _handleCapturedDblClick(eventData, el);
      } else if (eventData.type === 'input') {
        console.log('[UIRecorder] Queue processor: handling input');
        _handleCapturedInput(eventData, el);
      } else if (eventData.type === 'change') {
        console.log('[UIRecorder] Queue processor: handling change');
        _handleCapturedChange(eventData, el);
      } else if (eventData.type === 'submit') {
        console.log('[UIRecorder] Queue processor: handling submit');
        _handleCapturedSubmit(eventData, el);
      } else if (eventData.type === 'keydown') {
        console.log('[UIRecorder] Queue processor: handling keydown');
        _handleCapturedKeydown(eventData, el);
      }
    }
  }

  // 每 100ms 处理一次队列
  setInterval(_processEventQueue, 100);
  console.log('[UIRecorder] Queue processor started (100ms interval)');

  // 从缓存的事件数据重建元素信息
  function _buildElementInfo(eventData) {
    return {
      tag: eventData.tagName,
      text: eventData.tagText,
      type: eventData.tagType,
      href: eventData.tagHref,
      name: eventData.tagName2,
      placeholder: eventData.tagPlaceholder,
      visible: true,  // 假设可见
      aria_label: eventData.ariaLabel,
      test_id: eventData.testId
    };
  }

  function _sendToServer(payload) {
    try { origFetch('/api/ui-recorder/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true
    }); } catch(e) {}
  }

  function sendEvent(data) {
    console.log('[UIRecorder] sendEvent called:', data.action, 'recording=', recording, 'hasParent=', !!(window.parent && window.parent !== window));
    if (window.parent && window.parent !== window) {
      console.log('[UIRecorder] Sending via postMessage to parent');
      window.parent.postMessage({ type: 'ui-recorder-event', data: data }, '*');
    } else {
      console.log('[UIRecorder] Sending via _sendToServer');
      _sendToServer({
        session_id: _sessionId,
        event_type: 'step',
        timestamp: Date.now(),
        data: data
      });
    }
  }

  function getElementInfo(el) {
    return {
      tag: el.tagName.toLowerCase(),
      text: (el.textContent || '').trim().substring(0, 100),
      type: el.type || '',
      href: el.href || '',
      name: el.name || '',
      placeholder: el.placeholder || '',
      visible: el.offsetParent !== null,
      aria_label: el.getAttribute('aria-label') || '',
      test_id: el.getAttribute('data-testid') || ''
    };
  }

  // 刷新 inputBuffer：在 click/submit 前先发送挂起的输入步骤
  function _flushInputBuffer() {
    if (inputBuffer.element && inputBuffer.value) {
      clearTimeout(inputBuffer.timer);
      sendEvent({
        action: 'type',
        selector: SelectorEngine.generate(inputBuffer.element),
        value: inputBuffer.value,
        element_info: getElementInfo(inputBuffer.element),
        page_url: location.href,
        page_title: document.title,
        input_type: inputBuffer.element.type || 'text',
        is_password: inputBuffer.isPassword || false
      });
    }
    clearTimeout(inputBuffer.timer);
    inputBuffer = { element: null, value: '', timer: null, isPassword: false };
  }

  // 处理队列中的点击事件
  function _handleCapturedClick(eventData, el) {
    _flushInputBuffer();

    // 链接点击
    var link = el.closest('a');
    if (link && link.href) {
      // 检查是否是 target="_blank" 链接
      var target = link.getAttribute('target') || '';
      if (target === '_blank') {
        console.log('[UIRecorder] New tab link clicked:', link.href);
        sendEvent({
          action: 'new_tab',
          selector: SelectorEngine.generate(el),
          value: link.href,
          element_info: _buildElementInfo(eventData),
          page_url: eventData.pageUrl,
          page_title: eventData.pageTitle
        });
        // 通知父页面导航到新 URL
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({ type: 'ui-recorder-navigate', url: link.href, new_tab: true }, '*');
        }
        // 阻止默认行为（避免真正打开新标签页）
        return;
      }

      sendEvent({
        action: 'click',
        selector: SelectorEngine.generate(el),
        value: '',
        element_info: _buildElementInfo(eventData),
        page_url: eventData.pageUrl,
        page_title: eventData.pageTitle
      });
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'ui-recorder-navigate', url: link.href }, '*');
      }
      return;
    }

    sendEvent({
      action: 'click',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: _buildElementInfo(eventData),
      page_url: eventData.pageUrl,
      page_title: eventData.pageTitle,
      coordinates: { x: eventData.clientX, y: eventData.clientY }
    });
  }

  // 处理队列中的双击事件
  function _handleCapturedDblClick(eventData, el) {
    sendEvent({
      action: 'dblclick',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: _buildElementInfo(eventData),
      page_url: eventData.pageUrl,
      page_title: eventData.pageTitle
    });
  }

  // 处理队列中的输入事件
  function _handleCapturedInput(eventData, el) {
    if (!el.matches('input, textarea, [contenteditable]')) return;

    var isPassword = eventData.tagType === 'password';
    clearTimeout(inputBuffer.timer);
    inputBuffer.element = el;
    inputBuffer.value = eventData.tagValue;
    inputBuffer.isPassword = isPassword;

    inputBuffer.timer = setTimeout(function() {
      sendEvent({
        action: 'type',
        selector: SelectorEngine.generate(inputBuffer.element),
        value: inputBuffer.value,
        element_info: getElementInfo(inputBuffer.element),
        page_url: location.href,
        page_title: document.title,
        input_type: inputBuffer.element.type || 'text',
        is_password: inputBuffer.isPassword
      });
      inputBuffer = { element: null, value: '', timer: null, isPassword: false };
    }, 500);
  }

  // 处理队列中的 change 事件
  function _handleCapturedChange(eventData, el) {
    if (el.tagName === 'SELECT') {
      var selectedOption = el.options[el.selectedIndex];
      sendEvent({
        action: 'select',
        selector: SelectorEngine.generate(el),
        value: eventData.tagValue,
        element_info: Object.assign(_buildElementInfo(eventData), { selected_text: selectedOption ? selectedOption.text : '' }),
        page_url: eventData.pageUrl,
        page_title: eventData.pageTitle
      });
    }
    if (eventData.tagType === 'checkbox') {
      sendEvent({
        action: eventData.tagChecked ? 'check' : 'uncheck',
        selector: SelectorEngine.generate(el),
        value: String(eventData.tagChecked),
        element_info: _buildElementInfo(eventData),
        page_url: eventData.pageUrl,
        page_title: eventData.pageTitle
      });
    }
    if (eventData.tagType === 'radio') {
      sendEvent({
        action: 'select_radio',
        selector: SelectorEngine.generate(el),
        value: eventData.tagValue,
        element_info: _buildElementInfo(eventData),
        page_url: eventData.pageUrl,
        page_title: eventData.pageTitle
      });
    }
  }

  // 处理队列中的 submit 事件
  function _handleCapturedSubmit(eventData, el) {
    _flushInputBuffer();
    sendEvent({
      action: 'submit',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: _buildElementInfo(eventData),
      page_url: eventData.pageUrl,
      page_title: eventData.pageTitle
    });
  }

  // 处理队列中的 keydown 事件
  function _handleCapturedKeydown(eventData, el) {
    var specialKeys = ['Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Delete', 'Backspace'];
    if (specialKeys.indexOf(eventData.key) === -1) return;
    if (eventData.key === 'Enter' && el.matches('input, textarea')) return;
    sendEvent({
      action: 'keypress',
      selector: SelectorEngine.generate(el),
      value: eventData.key,
      element_info: _buildElementInfo(eventData),
      page_url: eventData.pageUrl,
      page_title: eventData.pageTitle,
      modifiers: { ctrl: eventData.ctrlKey, shift: eventData.shiftKey, alt: eventData.altKey, meta: eventData.metaKey }
    });
  }

  // 点击事件（备用，直接监听）
  function handleClick(e) {
    console.log('[UIRecorder] handleClick triggered, recording=', recording, 'target=', e.target.tagName, 'type=', e.target.type);
    if (!recording) return;
    var el = e.target;
    if (!el || !el.tagName) return;

    _flushInputBuffer();

    // 链接点击：录制事件后允许自然导航（href 已被代理改写）
    var link = el.closest('a');
    if (link && link.href) {
      sendEvent({
        action: 'click',
        selector: SelectorEngine.generate(el),
        value: '',
        element_info: getElementInfo(el),
        page_url: location.href,
        page_title: document.title
      });
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'ui-recorder-navigate', url: link.href }, '*');
      }
      return;
    }

    // 表单提交按钮特殊处理
    if (el.type === 'submit' || (el.tagName === 'BUTTON' && el.closest('form'))) {
      // 不阻止默认，让 submit 事件处理
    }

    sendEvent({
      action: 'click',
      selector: SelectorEngine.generate(el),
      value: '',
      element_info: getElementInfo(el),
      page_url: location.href,
      page_title: document.title,
      coordinates: { x: e.clientX, y: e.clientY }
    });
  }

  // 双击事件
  function handleDblClick(e) {
    if (!recording) return;
    sendEvent({
      action: 'dblclick',
      selector: SelectorEngine.generate(e.target),
      value: '',
      element_info: getElementInfo(e.target),
      page_url: location.href,
      page_title: document.title
    });
  }

  // 输入事件（防抖 500ms）
  function handleInput(e) {
    console.log('[UIRecorder] handleInput triggered, recording=', recording, 'target=', e.target.tagName, 'type=', e.target.type);
    if (!recording) return;
    var el = e.target;
    if (!el.matches('input, textarea, [contenteditable]')) return;

    var isPassword = el.type === 'password';
    clearTimeout(inputBuffer.timer);
    inputBuffer.element = el;
    inputBuffer.value = el.value || el.textContent || '';
    inputBuffer.isPassword = isPassword;

    inputBuffer.timer = setTimeout(function() {
      sendEvent({
        action: 'type',
        selector: SelectorEngine.generate(inputBuffer.element),
        value: inputBuffer.value,
        element_info: getElementInfo(inputBuffer.element),
        page_url: location.href,
        page_title: document.title,
        input_type: inputBuffer.element.type || 'text',
        is_password: inputBuffer.isPassword
      });
      inputBuffer = { element: null, value: '', timer: null, isPassword: false };
    }, 500);
  }

  // 下拉选择 + checkbox/radio
  function handleChange(e) {
    if (!recording) return;
    var el = e.target;
    if (el.tagName === 'SELECT') {
      var selectedOption = el.options[el.selectedIndex];
      sendEvent({
        action: 'select',
        selector: SelectorEngine.generate(el),
        value: el.value,
        element_info: Object.assign(getElementInfo(el), { selected_text: selectedOption ? selectedOption.text : '' }),
        page_url: location.href,
        page_title: document.title
      });
    }
    if (el.type === 'checkbox') {
      sendEvent({
        action: el.checked ? 'check' : 'uncheck',
        selector: SelectorEngine.generate(el),
        value: String(el.checked),
        element_info: getElementInfo(el),
        page_url: location.href,
        page_title: document.title
      });
    }
    if (el.type === 'radio') {
      sendEvent({
        action: 'select_radio',
        selector: SelectorEngine.generate(el),
        value: el.value,
        element_info: getElementInfo(el),
        page_url: location.href,
        page_title: document.title
      });
    }
  }

  // 表单提交 — 录制事件后允许自然提交（action 已被代理改写）
  function handleSubmit(e) {
    if (!recording) return;
    _flushInputBuffer();
    sendEvent({
      action: 'submit',
      selector: SelectorEngine.generate(e.target),
      value: '',
      element_info: getElementInfo(e.target),
      page_url: location.href,
      page_title: document.title
    });
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: 'ui-recorder-form-submit', form_action: e.target.action || '' }, '*');
    }
  }

  // 键盘事件（特殊键）
  function handleKeydown(e) {
    if (!recording) return;
    var specialKeys = ['Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Delete', 'Backspace'];
    if (specialKeys.indexOf(e.key) === -1) return;
    if (e.key === 'Enter' && e.target.matches('input, textarea')) return;
    sendEvent({
      action: 'keypress',
      selector: SelectorEngine.generate(e.target),
      value: e.key,
      element_info: getElementInfo(e.target),
      page_url: location.href,
      page_title: document.title,
      modifiers: { ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey, meta: e.metaKey }
    });
  }

  // 判断 URL 是否需要通过代理转发
  function _shouldProxy(url) {
    if (typeof url !== 'string' || !url) return false;
    if (url.indexOf('/ui-testing/') === 0) return false;
    if (url.indexOf('/api/') === 0) return false;
    if (url.indexOf('data:') === 0 || url.indexOf('blob:') === 0) return false;
    if (_PROXY_ORIGIN && url.indexOf(_PROXY_ORIGIN) === 0) return true;
    if (url.charAt(0) === '/' && url.charAt(1) !== '/') return true;
    if (url.indexOf('http://') === 0 || url.indexOf('https://') === 0) {
      if (_PROXY_ORIGIN && url.indexOf(_PROXY_ORIGIN) !== 0) return false;
    }
    return false;
  }

  function _toProxyUrl(url) {
    if (_PROXY_ORIGIN && url.charAt(0) === '/' && url.charAt(1) !== '/') {
      return '/ui-testing/proxy-resource?url=' + encodeURIComponent(_PROXY_ORIGIN + url);
    }
    return '/ui-testing/proxy-resource?url=' + encodeURIComponent(url);
  }

  // 拦截 fetch：重定向原始服务器 API 调用 + 录制
  var origFetch = window.fetch;
  window.fetch = function(url, opts) {
    if (_shouldProxy(url)) {
      arguments[0] = _toProxyUrl(typeof url === 'string' ? url : String(url));
    }
    if (recording && url && typeof url === 'string') {
      sendEvent({
        action: 'api_call',
        selector: null,
        value: url,
        element_info: { tag: 'fetch', method: (opts && opts.method) || 'GET' },
        page_url: location.href,
        page_title: document.title
      });
    }
    return origFetch.apply(this, arguments);
  };

  // 拦截 XMLHttpRequest：重定向原始服务器 API 调用
  var _OrigXHR = window.XMLHttpRequest;
  var origOpen = _OrigXHR.prototype.open;
  var origSend = _OrigXHR.prototype.send;
  _OrigXHR.prototype.open = function(method, url) {
    this._uiRecorderMethod = method;
    this._uiRecorderUrl = url;
    return origOpen.apply(this, arguments);
  };
  _OrigXHR.prototype.send = function() {
    var url = this._uiRecorderUrl;
    if (_shouldProxy(url)) {
      var proxyUrl = _toProxyUrl(typeof url === 'string' ? url : String(url));
      origOpen.call(this, this._uiRecorderMethod || 'GET', proxyUrl);
    }
    return origSend.apply(this, arguments);
  };

  // 拦截 window.open：录制新标签页打开
  var origWindowOpen = window.open;
  window.open = function(url, target, features) {
    if (recording && url) {
      console.log('[UIRecorder] window.open intercepted:', url, 'target:', target);
      sendEvent({
        action: 'new_tab',
        selector: null,
        value: url,
        element_info: { tag: 'window.open', target: target || '' },
        page_url: location.href,
        page_title: document.title
      });
      // 通知父页面导航到新 URL
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'ui-recorder-navigate', url: url, new_tab: true }, '*');
      }
      // 返回一个模拟的窗口对象（避免脚本报错）
      return { closed: false, close: function() {}, focus: function() {}, postMessage: function() {} };
    }
    return origWindowOpen.apply(this, arguments);
  };

  // 监听来自父页面的控制消息
  window.addEventListener('message', function(e) {
    console.log('[UIRecorder] Received message:', e.data.type, e.data.action);
    if (e.data && e.data.type === 'ui-recorder-control') {
      if (e.data.action === 'start') {
        recording = true;
        // 同步到全局变量（早期脚本也使用）
        window.__UI_RECORDER_RECORDING = true;
        // 保存录制状态到 sessionStorage，页面导航后自动恢复
        try {
          sessionStorage.setItem('_ui_rec_session_id', _sessionId);
          sessionStorage.setItem('_ui_rec_active', '1');
        } catch(e) {}
        console.log('[UIRecorder] Recording started, recording=', recording, 'global=', window.__UI_RECORDER_RECORDING, 'session=', _sessionId);
      } else if (e.data.action === 'stop') {
        recording = false;
        window.__UI_RECORDER_RECORDING = false;
        clearTimeout(inputBuffer.timer);
        inputBuffer = { element: null, value: '', timer: null, isPassword: false };
        // 清除录制状态
        try {
          sessionStorage.removeItem('_ui_rec_session_id');
          sessionStorage.removeItem('_ui_rec_active');
        } catch(e) {}
        console.log('[UIRecorder] Recording stopped');
      }
    }
  });

  console.log('[UIRecorder] Script initialized, _PROXY_ORIGIN=', _PROXY_ORIGIN, 'recording=', recording);

  // 使用被动事件监听器，确保即使 Vue 调用 preventDefault 也能捕获
  var eventOptions = { capture: true, passive: true };

  // 绑定到 window（最高层级，最先捕获）
  window.addEventListener('click', handleClick, eventOptions);
  window.addEventListener('dblclick', handleDblClick, eventOptions);
  window.addEventListener('input', handleInput, eventOptions);
  window.addEventListener('change', handleChange, eventOptions);
  window.addEventListener('submit', handleSubmit, eventOptions);
  window.addEventListener('keydown', handleKeydown, eventOptions);
  console.log('[UIRecorder] Event listeners attached to window');

  // 同时绑定到 document 和 document.body 以确保兼容性
  document.addEventListener('click', handleClick, eventOptions);
  document.addEventListener('dblclick', handleDblClick, eventOptions);
  document.addEventListener('input', handleInput, eventOptions);
  document.addEventListener('change', handleChange, eventOptions);
  document.addEventListener('submit', handleSubmit, eventOptions);
  document.addEventListener('keydown', handleKeydown, eventOptions);
  console.log('[UIRecorder] Event listeners attached to document');

  // 测试：直接在 body 上绑定，看是否能捕获
  if (document.body) {
    document.body.addEventListener('click', function(e) {
      console.log('[UIRecorder] Body click captured, target=', e.target.tagName);
    }, { capture: true, passive: true });
    console.log('[UIRecorder] Test listener attached to body');
  }

  // 通知父页面录制器已就绪
  window.parent.postMessage({ type: 'ui-recorder-ready' }, '*');
  console.log('[UIRecorder] Injected and ready');
})();
"""


def get_replayer_js(origin: str = "") -> str:
    """返回完整的回放引擎 JavaScript 代码。"""
    code = _REPLAYER_JS
    origin_decl = '\n  var _REPLAY_ORIGIN = "' + origin + '";'
    code = code.replace("'use strict';", "'use strict';" + origin_decl, 1)
    return code


_REPLAYER_JS = r"""
(function() {
  'use strict';

  // ====== 选择器引擎（回放模式，仅查找）======
  var SelectorEngine = {
    find: function(selectorStr, selectorObj) {
      if (!selectorStr && !selectorObj) return null;
      var primary = '';
      var fallbackCss = '';
      var fallbackXpath = '';
      if (typeof selectorStr === 'string' && selectorStr) {
        primary = selectorStr;
      } else if (selectorObj) {
        primary = selectorObj.primary || '';
        fallbackCss = selectorObj.fallback_css || '';
        fallbackXpath = selectorObj.fallback_xpath || '';
      }
      var el = SelectorEngine._tryFind(primary);
      if (el) return { element: el, strategy: 'primary' };
      if (fallbackCss) {
        el = SelectorEngine._tryFind(fallbackCss);
        if (el) return { element: el, strategy: 'fallback_css' };
      }
      if (fallbackXpath) {
        el = SelectorEngine._tryXpath(fallbackXpath);
        if (el) return { element: el, strategy: 'fallback_xpath' };
      }
      return null;
    },
    _tryFind: function(selector) {
      console.log('[ReplayEngine] _tryFind called with:', typeof selector, JSON.stringify(selector).substring(0, 80));
      if (!selector) return null;
      try {
        var startsWithSlash = selector.indexOf('/') === 0;
        console.log('[ReplayEngine] _tryFind startsWithSlash:', startsWithSlash, 'selector:', selector.substring(0, 20));
        if (startsWithSlash) return SelectorEngine._tryXpath(selector);
        // Playwright role 选择器: role=button[name="登录"]
        var roleMatch = selector.match(/^role=(\w+)(?:\[name=["']?([^"'\]]+)["']?\])?$/);
        if (roleMatch) {
          var role = roleMatch[1].toLowerCase();
          var name = roleMatch[2] || '';
          var all = document.querySelectorAll('*');
          for (var i = 0; i < all.length; i++) {
            var el = all[i];
            var elRole = (el.getAttribute('role') || el.tagName || '').toLowerCase();
            if (elRole !== role && el.tagName.toLowerCase() !== role) continue;
            if (name) {
              var elName = (el.getAttribute('name') || el.getAttribute('aria-label') || el.textContent || '').trim();
              if (elName.indexOf(name) < 0) continue;
            }
            return el;
          }
          return null;
        }
        if (selector.indexOf('text=') === 0) {
          var text = selector.substring(5).replace(/^["']|["']$/g, '');
          console.log('[ReplayEngine] _tryFind text selector:', text);

          // 优先在日期选择器中查找（处理日期控件）
          var datePickerContainers = document.querySelectorAll('.el-picker-panel, .el-date-picker, .el-month-table, .el-year-table, [class*="calendar"], [class*="datepicker"], [class*="date-picker"]');
          if (datePickerContainers.length > 0) {
            console.log('[ReplayEngine] Found date picker containers:', datePickerContainers.length);
            for (var c = 0; c < datePickerContainers.length; c++) {
              var container = datePickerContainers[c];
              if (container.offsetParent === null) continue; // 跳过隐藏容器
              var cells = container.querySelectorAll('td, [class*="cell"], [class*="day"], [class*="date"]');
              for (var k = 0; k < cells.length; k++) {
                var cell = cells[k];
                if ((cell.textContent || '').trim() === text && cell.offsetParent !== null) {
                  console.log('[ReplayEngine] Found date cell in date picker');
                  return cell;
                }
              }
            }
          }

          // 全局查找（原有逻辑）
          var all2 = document.querySelectorAll('*');
          for (var j = 0; j < all2.length; j++) {
            if (all2[j].children.length === 0 && (all2[j].textContent || '').trim() === text) return all2[j];
          }
          return null;
        }
        console.log('[ReplayEngine] _tryFind falling back to querySelector');
        return document.querySelector(selector);
      } catch(e) {
        console.error('[ReplayEngine] _tryFind ERROR:', e.message);
        return null;
      }
    },
    _tryXpath: function(xpath) {
      if (!xpath) return null;
      try {
        console.log('[ReplayEngine] _tryXpath:', xpath, 'doc ready:', document.readyState);
        var result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        console.log('[ReplayEngine] _tryXpath result:', result ? result.singleNodeValue : 'null');
        return result.singleNodeValue || null;
      } catch(e) {
        console.error('[ReplayEngine] _tryXpath ERROR:', e.message, 'xpath:', xpath);
        return null;
      }
    }
  };

  // ====== 网络请求比对器 ======
  var NetworkComparator = {
    recorded: [],
    _installed: false,

    init: function(networkRequests) {
      this.recorded = networkRequests || [];
      if (this.recorded.length === 0 || this._installed) return;
      this._installed = true;
      this._interceptFetch();
      this._interceptXHR();
      console.log('[NetworkComparator] Installed, recorded requests:', this.recorded.length);
    },

    _interceptFetch: function() {
      var self = this;
      var orig = window.fetch;
      window.fetch = function(url, opts) {
        var reqUrl = typeof url === 'string' ? url : (url && url.href ? url.href : String(url));
        var method = (opts && opts.method) || 'GET';
        var reqHeaders = {};
        if (opts && opts.headers) {
          try {
            if (typeof opts.headers.forEach === 'function') {
              opts.headers.forEach(function(v, k) { reqHeaders[k] = v; });
            } else if (typeof opts.headers === 'object') {
              for (var k in opts.headers) { if (opts.headers.hasOwnProperty(k)) reqHeaders[k] = opts.headers[k]; }
            }
          } catch(e) {}
        }
        return orig.apply(this, arguments).then(function(resp) {
          self._onRequest(reqUrl, method.toUpperCase(), reqHeaders, resp.status);
          return resp;
        });
      };
    },

    _interceptXHR: function() {
      var self = this;
      var origOpen = XMLHttpRequest.prototype.open;
      var origSend = XMLHttpRequest.prototype.send;
      var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

      XMLHttpRequest.prototype.open = function(method, url) {
        this.__nc_method = (method || 'GET').toUpperCase();
        this.__nc_url = typeof url === 'string' ? url : String(url);
        this.__nc_headers = {};
        return origOpen.apply(this, arguments);
      };

      XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if (this.__nc_headers) this.__nc_headers[name] = value;
        return origSetHeader.apply(this, arguments);
      };

      XMLHttpRequest.prototype.send = function(body) {
        var xhr = this;
        xhr.addEventListener('loadend', function() {
          if (xhr.__nc_url) {
            self._onRequest(xhr.__nc_url, xhr.__nc_method, xhr.__nc_headers || {}, xhr.status);
          }
        });
        return origSend.apply(this, arguments);
      };
    },

    _getPath: function(url) {
      try {
        var u = new URL(url, location.href);
        return u.pathname;
      } catch(e) {
        return url;
      }
    },

    _findMatch: function(url, method) {
      var path = this._getPath(url);
      for (var i = 0; i < this.recorded.length; i++) {
        var rec = this.recorded[i];
        var recPath = rec.url_path || this._getPath(rec.url);
        if (recPath === path && rec.method === method) {
          return rec;
        }
      }
      return null;
    },

    _compareHeaders: function(recordedHeaders, actualHeaders) {
      var diffs = [];
      var skipRe = /^(host|cookie|connection|content-length|accept-encoding|sec-|x-forwarded|x-real-ip|referer|user-agent|origin)/i;
      var actualLower = {};
      for (var k in actualHeaders) {
        if (actualHeaders.hasOwnProperty(k)) actualLower[k.toLowerCase()] = actualHeaders[k];
      }
      for (var key in recordedHeaders) {
        if (!recordedHeaders.hasOwnProperty(key)) continue;
        if (skipRe.test(key)) continue;
        var lowerKey = key.toLowerCase();
        var actualVal = actualLower[lowerKey];
        if (actualVal === undefined || actualVal === null) {
          diffs.push({ key: key, type: 'missing', recorded: recordedHeaders[key], actual: null });
        } else if (recordedHeaders[key] !== actualVal) {
          diffs.push({ key: key, type: 'changed', recorded: recordedHeaders[key], actual: actualVal });
        }
      }
      return diffs;
    },

    _onRequest: function(url, method, actualHeaders, status) {
      var match = this._findMatch(url, method);
      if (!match) return;

      var headerDiffs = this._compareHeaders(match.headers || {}, actualHeaders);
      var statusMatch = match.response_status === status;

      if (headerDiffs.length > 0 || !statusMatch) {
        var detail = {
          url: url,
          method: method,
          header_diffs: headerDiffs,
          recorded_status: match.response_status,
          actual_status: status,
        };
        console.warn('[NetworkComparator] Mismatch:', url, detail);
        if (typeof ReplayEngine !== 'undefined' && ReplayEngine._sendLog) {
          ReplayEngine._sendLog('network_mismatch', '请求结构与录制不一致: ' + method + ' ' + url, detail, 'warn');
        }
      }
    }
  };

  // ====== 回放引擎 ======
  var ReplayEngine = {
    steps: [],
    options: {},
    currentIndex: -1,
    running: false,
    paused: false,
    stopped: false,
    startTime: 0,
    results: [],
    jobId: '',
    _currentTimeoutId: null,

    init: function(steps, options) {
      console.log('[ReplayEngine] init called, steps from parent:', steps ? steps.length : 0);
      // 检查是否有保存的回放状态（跨页面导航后恢复）
      var savedState = null;
      try {
        var saved = sessionStorage.getItem('_ui_replay_state');
        if (saved) {
          savedState = JSON.parse(saved);
          console.log('[ReplayEngine] Found saved state, currentIndex:', savedState.currentIndex, 'total steps:', savedState.steps.length);
        } else {
          console.log('[ReplayEngine] No saved state found in sessionStorage');
        }
      } catch(e) {
        console.error('[ReplayEngine] Failed to load saved state:', e);
      }

      if (savedState && savedState.steps && savedState.steps.length > 0) {
        // 恢复保存的状态
        this.steps = savedState.steps;
        this.options = savedState.options || {};
        this.jobId = savedState.jobId || '';
        this.currentIndex = savedState.currentIndex || -1;
        this.results = savedState.results || [];
        this.running = false;
        this.paused = false;
        this.stopped = false;
        console.log('[ReplayEngine] Resumed from saved state, continuing from step', this.currentIndex + 1, 'of', this.steps.length);
      } else {
        // 正常初始化
        this.steps = steps || [];
        this.options = options || {};
        this.jobId = options.job_id || '';
        this.currentIndex = -1;
        this.running = false;
        this.paused = false;
        this.stopped = false;
        this.results = [];
        console.log('[ReplayEngine] Normal init, starting from step 0');
      }

      if (options.network_requests && options.network_requests.length > 0) {
        NetworkComparator.init(options.network_requests);
      }
      var timeout = this.options.timeout || 5000;
      console.log('[ReplayEngine] init — steps:', this.steps.length, 'timeout:', timeout, 'delay:', this.options.delay_between_steps, 'jobId:', this.jobId, 'currentIndex:', this.currentIndex);
      if (typeof this._sendLog === 'function') try { this._sendLog('replay_init', '回放引擎初始化', { steps: this.steps.length, timeout: timeout, delay: this.options.delay_between_steps, resumed: !!savedState }, 'info'); } catch(e) {}
      this._notifyParent('ready', { step_count: this.steps.length, current_index: this.currentIndex, resumed: !!savedState });
    },

    start: function() {
      console.log('[ReplayEngine] start called, running:', this.running, 'currentIndex:', this.currentIndex, 'total steps:', this.steps.length);
      if (this.running) return;
      this.running = true;
      this.paused = false;
      this.stopped = false;
      this.startTime = Date.now();
      console.log('[ReplayEngine] Starting execution from step', this.currentIndex + 1);
      this._executeNext();
    },

    pause: function() {
      this.paused = true;
      this._notifyParent('paused', { index: this.currentIndex });
    },

    resume: function() {
      if (!this.paused) return;
      this.paused = false;
      this._executeNext();
    },

    stop: function() {
      this.stopped = true;
      this.running = false;
      this.paused = false;
      if (this._currentTimeoutId) {
        clearTimeout(this._currentTimeoutId);
        this._currentTimeoutId = null;
      }
      this._notifyParent('stopped', {
        index: this.currentIndex,
        results: this.results
      });
    },

    _executeNext: function() {
      var self = this;
      // 检查停止标志（内部标志 + 父页面设置的全局标志）
      if (this.stopped || !this.running || (window.__REPLAY_STOP__ === true)) {
        if (window.__REPLAY_STOP__ === true) {
          console.log('[ReplayEngine] Global stop flag detected, stopping...');
          this.stop();
        }
        return;
      }
      if (this.paused) return;

      this.currentIndex++;
      if (this.currentIndex >= this.steps.length) {
        this._finishAll();
        return;
      }

      // 保存当前状态，以防下一步导致页面导航
      self._saveState();

      var step = this.steps[this.currentIndex];
      var stepStart = Date.now();

      this._notifyParent('step_start', {
        index: this.currentIndex,
        action: step.action,
        total: this.steps.length
      });
      if (typeof this._sendLog === 'function') try { this._sendLog('step_start', step.action + ' step ' + this.currentIndex, { action: step.action }); } catch(e) {}

      var delay = this.options.delay_between_steps || 500;
      if (this.currentIndex === 0) delay = 0;

      self._currentTimeoutId = setTimeout(function() {
        if (self.stopped || !self.running) return;
        self._executeStep(step, self.currentIndex, stepStart);
      }, delay);
    },

    _executeStep: function(step, index, stepStart) {
      var self = this;
      var timeout = this.options.timeout || 5000;
      var action = step.action || '';
      console.log('[ReplayEngine] _executeStep', index, action, 'selector:', JSON.stringify(step.selector || '').substring(0, 100));
      var result = {
        index: index,
        action: action,
        selector: step.selector || null,
        value: step.value || '',
        status: 'passed',
        duration_ms: 0,
        timestamp: new Date().toISOString(),
        current_url: location.href,
        error: ''
      };

      // navigate 和 wait 不需要查找元素
      if (action === 'navigate') {
        result.duration_ms = Date.now() - stepStart;
        self.results.push(result);
        self._notifyParent('step_complete', result);
        self._notifyParent('navigate', { url: step.value || '' });
        return;
      }

      // new_tab 动作：模拟打开新标签页（实际是在 iframe 中导航）
      if (action === 'new_tab') {
        result.duration_ms = Date.now() - stepStart;
        self.results.push(result);
        self._notifyParent('step_complete', result);
        // 通知父页面导航到新 URL（标记为新标签页）
        self._notifyParent('navigate', { url: step.value || '', new_tab: true });
        console.log('[ReplayEngine] new_tab action: navigating to', step.value);
        return;
      }

      // date_select 动作：处理日期选择器
      if (action === 'date_select') {
        // 等待日期输入框出现
        self._waitForElement(step, timeout, function(dateInput) {
          if (!dateInput) {
            result.status = 'failed';
            result.error = '日期输入框未找到';
            result.duration_ms = Date.now() - stepStart;
            self.results.push(result);
            self._notifyParent('step_complete', result);
            self._executeNext();
            return;
          }

          try {
            // 直接设置日期值（比点击更可靠）
            var dateValue = step.value || '';
            console.log('[ReplayEngine] date_select: setting value', dateValue, 'on', dateInput.tagName, dateInput.type);

            // 聚焦并设置值
            dateInput.focus();
            dateInput.value = dateValue;

            // 触发完整的事件序列，确保框架响应
            dateInput.dispatchEvent(new Event('focus', { bubbles: true }));
            dateInput.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
            dateInput.dispatchEvent(new Event('change', { bubbles: true }));

            // 对于有日期选择器的输入框，也尝试点击打开选择器
            if (dateInput.type === 'date' || dateInput.type === 'datetime-local' || (dateInput.className || '').indexOf('date') >= 0) {
              dateInput.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
              dateInput.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            }

            result.status = 'passed';
            result.duration_ms = Date.now() - stepStart;
            self.results.push(result);
            self._notifyParent('step_complete', result);
            console.log('[ReplayEngine] date_select completed successfully');
          } catch(e) {
            result.status = 'error';
            result.error = e.message;
            result.duration_ms = Date.now() - stepStart;
            self.results.push(result);
            self._notifyParent('step_complete', result);
          }
          self._executeNext();
        });
        return;
      }

      if (action === 'wait') {
        var ms = parseInt(step.value, 10) || 1000;
        setTimeout(function() {
          if (self.stopped || !self.running) return;
          result.duration_ms = Date.now() - stepStart;
          self.results.push(result);
          self._notifyParent('step_complete', result);
          self._executeNext();
        }, ms);
        return;
      }

      // assert_url / assert_title 不需要元素
      if (action === 'assert_url') {
        var match = location.href === step.value || location.href.indexOf(step.value) >= 0;
        result.status = match ? 'passed' : 'failed';
        if (!match) result.error = 'URL 不匹配: 期望包含 "' + step.value + '", 实际 "' + location.href + '"';
        result.duration_ms = Date.now() - stepStart;
        self.results.push(result);
        self._notifyParent('step_complete', result);
        self._executeNext();
        return;
      }

      if (action === 'assert_title') {
        var titleMatch = (document.title || '').indexOf(step.value || '') >= 0;
        result.status = titleMatch ? 'passed' : 'failed';
        if (!titleMatch) result.error = '标题不匹配: 期望包含 "' + step.value + '", 实际 "' + document.title + '"';
        result.duration_ms = Date.now() - stepStart;
        self.results.push(result);
        self._notifyParent('step_complete', result);
        self._executeNext();
        return;
      }

      // 需要查找元素的 action
      self._waitForElement(step, timeout, function(el) {
        // 停止时也要调用 _executeNext() 保证执行链不断裂
        var wasStopped = self.stopped || !self.running;

        if (!el) {
          result.status = 'failed';
          result.error = '元素未找到 (超时 ' + timeout + 'ms): ' + JSON.stringify(step.selector || '');
          result.duration_ms = Date.now() - stepStart;
          // 截图当前页面状态
          self._captureScreenshot(function(screenshotData) {
            result.screenshot = screenshotData || null;
            self.results.push(result);
            self._notifyParent('step_complete', result);
            if (typeof self._sendLog === 'function') try { self._sendLog('element_not_found', '元素未找到', { selector: step.selector, timeout: timeout }, 'warn'); } catch(e) {}
            // 元素未找到时记录错误并继续执行后续步骤
            self._executeNext();
          });
          return;
        }

        // 如果已停止，不执行操作但仍推进
        if (wasStopped) {
          self._executeNext();
          return;
        }

        self._highlightElement(el);

        // 保存 action 执行前的 URL，用于延迟检测 SPA 导航
        self._actionStartUrl = location.href;

        try {
          var actionResult = self._executeAction(action, el, step.value);
          if (actionResult === false) {
            result.status = 'failed';
            result.error = '断言失败';
          }
        } catch(e) {
          result.status = 'error';
          result.error = e.message || String(e);
        }

        result.duration_ms = Date.now() - stepStart;
        self.results.push(result);
        self._notifyParent('step_complete', result);
        if (typeof self._sendLog === 'function') try { self._sendLog('step_complete', result.status, { status: result.status, duration_ms: result.duration_ms }, result.status === 'passed' ? 'info' : 'warn'); } catch(e) {}

        // SPA 导航通常是异步的（API 返回后 pushState），延迟检测 URL 变化
        if (action === 'click' || action === 'submit' || action === 'dblclick') {
          var urlBefore = self._actionStartUrl || location.href;
          setTimeout(function() {
            if (self.stopped) return;
            if (location.href !== urlBefore) {
              self._notifyParent('navigate', { url: location.href });
            }
          }, 2000);
        }
        self._executeNext();
      });
    },

    _executeAction: function(action, el, value) {
      var urlBefore = location.href;
      var result = true;
      switch (action) {
        case 'click':
          // 对于日期输入框，使用鼠标事件触发，确保日期选择器弹出
          if (el.tagName === 'INPUT' && (el.type === 'date' || el.type === 'datetime-local' || el.getAttribute('class') || '').indexOf('date') >= 0) {
            console.log('[ReplayEngine] Clicking date input, dispatching mouse events');
            el.focus();
            el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
          } else {
            el.click();
          }
          break;
        case 'dblclick':
          el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
          break;
        case 'type':
          // 确保操作的是真实 input 元素（SPA 框架可能有 wrapper）
          var inputEl = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' ? el : el.querySelector('input, textarea');
          if (!inputEl) inputEl = el;
          inputEl.focus();
          inputEl.value = value || '';
          // Vue/Element UI 需要完整的事件序列才能更新响应式数据
          inputEl.dispatchEvent(new Event('focus', { bubbles: true, composed: true }));
          inputEl.dispatchEvent(new InputEvent('input', {
            bubbles: true, composed: true, cancelable: true,
            inputType: 'insertText', data: value || ''
          }));
          // compositionend 触发 Vue 的 IME 更新
          inputEl.dispatchEvent(new CompositionEvent('compositionend', {
            bubbles: true, composed: true, data: value || ''
          }));
          inputEl.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
          // 强制触发 keyup 让某些框架捕获输入
          inputEl.dispatchEvent(new KeyboardEvent('keyup', {
            bubbles: true, composed: true, key: 'Enter'
          }));
          break;
        case 'select':
          el.value = value || '';
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'check':
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'uncheck':
          el.checked = false;
          el.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        case 'submit':
          var form = el.tagName === 'FORM' ? el : el.closest('form');
          if (form) form.submit();
          break;
        case 'keypress':
          el.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keyup', { key: value, bubbles: true }));
          break;
        case 'wait_for':
          return el ? true : false;
        case 'assert_visible':
          return el && el.offsetParent !== null;
        case 'assert_text':
          var text = (el.textContent || '').trim();
          return text.indexOf(value || '') >= 0;
        default:
          break;
      }
      // 检测 SPA 导航：如果 URL 发生变化，通知父页面更新 iframe
      var urlAfter = location.href;
      if (urlAfter !== urlBefore) {
        this._notifyParent('navigate', { url: urlAfter });
      }
      return result;
    },

    _waitForElement: function(step, timeout, callback) {
      var self = this;
      var selector = step.selector;
      var start = Date.now();
      var interval = 200;
      var attempts = 0;
      var selectorStr = typeof selector === 'string' ? selector : (selector ? selector.primary : 'null');
      console.log('[ReplayEngine] _waitForElement selector:', JSON.stringify(selectorStr), 'action:', step.action);

      function check() {
        attempts++;
        var found = SelectorEngine.find(typeof selector === 'string' ? selector : '', selector);
        if (found && found.element) {
          console.log('[ReplayEngine] element found after', attempts, 'attempts, strategy:', found.strategy);
          if (typeof self._sendLog === 'function') try { self._sendLog('element_found', '元素已找到', { attempts: attempts, strategy: found.strategy }); } catch(e) {}
          callback(found.element);
          return;
        }
        if (Date.now() - start >= timeout) {
          console.log('[ReplayEngine] element NOT found after', attempts, 'attempts, timed out');
          callback(null);
          return;
        }
        // 停止时也要调用 callback 保证执行链不断裂
        if (self.stopped || !self.running || (window.__REPLAY_STOP__ === true)) {
          console.log('[ReplayEngine] stopped during wait, canceling');
          callback(null);
          return;
        }
        if (attempts <= 3) console.log('[ReplayEngine] attempt', attempts, 'failed, retrying...');
        self._currentTimeoutId = setTimeout(check, interval);
      }
      check();
    },

    _saveState: function() {
      // 保存当前回放状态到 sessionStorage，用于跨页面导航后恢复
      try {
        var state = {
          steps: this.steps,
          options: this.options,
          jobId: this.jobId,
          currentIndex: this.currentIndex,
          results: this.results
        };
        sessionStorage.setItem('_ui_replay_state', JSON.stringify(state));
        console.log('[ReplayEngine] State saved to sessionStorage, currentIndex:', this.currentIndex, 'total steps:', this.steps.length, 'results:', this.results.length);
      } catch(e) {
        console.error('[ReplayEngine] Failed to save state:', e);
      }
    },

    _highlightElement: function(el) {
      if (!el || !el.style) return;
      var origOutline = el.style.outline;
      var origTransition = el.style.transition;
      el.style.transition = 'outline 0.15s';
      el.style.outline = '3px solid #3b82f6';
      setTimeout(function() {
        el.style.outline = '3px solid #ef4444';
        setTimeout(function() {
          el.style.outline = origOutline;
          el.style.transition = origTransition;
        }, 300);
      }, 300);
    },

    _captureScreenshot: function(callback) {
      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({
            type: 'ui-replay-screenshot',
            data: { step_index: this.currentIndex }
          }, '*');
        }
        if (callback) callback(null);
      } catch(e) {
        if (callback) callback(null);
      }
    },

    _finishAll: function() {
      this.running = false;
      var passed = 0, failed = 0;
      for (var i = 0; i < this.results.length; i++) {
        if (this.results[i].status === 'passed') passed++;
        else failed++;
      }
      var duration = Date.now() - this.startTime;
      if (typeof this._sendLog === 'function') try { this._sendLog('all_complete', (failed > 0 ? 'failed' : 'passed'), { passed: passed, failed: failed, duration_ms: duration }); } catch(e) {}
      this._notifyParent('all_complete', {
        status: failed > 0 ? 'failed' : 'passed',
        total_steps: this.steps.length,
        passed: passed,
        failed: failed,
        duration_ms: duration,
        results: this.results
      });
      // 清除保存的回放状态
      try {
        sessionStorage.removeItem('_ui_replay_state');
        console.log('[ReplayEngine] Saved state cleared');
      } catch(e) {}
    },

    _notifyParent: function(eventType, data) {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({
          type: 'ui-replay-' + eventType,
          data: data || {}
        }, '*');
      }
    },

    _sendLog: function(event, message, detail, level) {
      if (!this.jobId) return;
      try {
        fetch('/api/ui-testing/replay-log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            job_id: this.jobId,
            step_index: this.currentIndex,
            event: event,
            message: message,
            detail: detail || {},
            level: level || 'info'
          })
        }).catch(function() {});
      } catch(e) {}
    }
  };

  // 监听来自父页面的控制消息
  window.addEventListener('message', function(e) {
    if (!e.data || !e.data.type) return;
    if (e.data.type !== 'ui-replay-control') return;

    var action = e.data.action;
    if (action === 'init') {
      ReplayEngine.init(e.data.steps || [], e.data.options || {});
    } else if (action === 'start') {
      ReplayEngine.start();
    } else if (action === 'pause') {
      ReplayEngine.pause();
    } else if (action === 'resume') {
      ReplayEngine.resume();
    } else if (action === 'stop') {
      ReplayEngine.stop();
    }
  });

  // 等待 DOM 完全加载后再通知父页面
  function _replayReady() {
    window.parent.postMessage({ type: 'ui-replay-ready' }, '*');
    console.log('[ReplayEngine] Injected and ready');
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    _replayReady();
  } else {
    window.addEventListener('DOMContentLoaded', _replayReady);
  }
})();
"""
