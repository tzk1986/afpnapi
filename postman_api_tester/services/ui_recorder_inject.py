"""录制器注入脚本生成器。

生成内联注入到代理页面的 JavaScript 代码，
负责事件捕获、选择器生成和与父页面的 postMessage 通信。
同时提供回放引擎 JS 生成（get_replayer_js）。
"""


def get_recorder_js(origin: str = "") -> str:
    """返回完整的录制器 JavaScript 代码。"""
    code = _RECORDER_JS
    origin_decl = '\n  var _PROXY_ORIGIN = "' + origin + '";'
    code = code.replace("'use strict';", "'use strict';" + origin_decl, 1)
    return code


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

  function _sendToServer(payload) {
    try { origFetch('/api/ui-recorder/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true
    }); } catch(e) {}
  }

  function sendEvent(data) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: 'ui-recorder-event', data: data }, '*');
    } else {
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

  // 点击事件
  function handleClick(e) {
    if (!recording) return;
    var el = e.target;
    if (!el || !el.tagName) return;

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

  // 监听来自父页面的控制消息
  window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'ui-recorder-control') {
      if (e.data.action === 'start') {
        recording = true;
        console.log('[UIRecorder] Recording started');
      } else if (e.data.action === 'stop') {
        recording = false;
        clearTimeout(inputBuffer.timer);
        inputBuffer = { element: null, value: '', timer: null, isPassword: false };
        console.log('[UIRecorder] Recording stopped');
      }
    }
  });

  // 绑定事件（capture 阶段，确保先于页面脚本）
  document.addEventListener('click', handleClick, true);
  document.addEventListener('dblclick', handleDblClick, true);
  document.addEventListener('input', handleInput, true);
  document.addEventListener('change', handleChange, true);
  document.addEventListener('submit', handleSubmit, true);
  document.addEventListener('keydown', handleKeydown, true);

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

    init: function(steps, options) {
      this.steps = steps || [];
      this.options = options || {};
      this.jobId = options.job_id || '';
      this.currentIndex = -1;
      this.running = false;
      this.paused = false;
      this.stopped = false;
      this.results = [];
      this._notifyParent('ready', { step_count: this.steps.length });
    },

    start: function() {
      if (this.running) return;
      this.running = true;
      this.paused = false;
      this.stopped = false;
      this.startTime = Date.now();
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
      this._notifyParent('stopped', {
        index: this.currentIndex,
        results: this.results
      });
    },

    _executeNext: function() {
      var self = this;
      if (this.stopped || !this.running) return;
      if (this.paused) return;

      this.currentIndex++;
      if (this.currentIndex >= this.steps.length) {
        this._finishAll();
        return;
      }

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

      setTimeout(function() {
        if (self.stopped || !self.running) return;
        self._executeStep(step, self.currentIndex, stepStart);
      }, delay);
    },

    _executeStep: function(step, index, stepStart) {
      var self = this;
      var timeout = this.options.timeout || 30000;
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
          self.results.push(result);
          self._notifyParent('step_complete', result);
          if (typeof self._sendLog === 'function') try { self._sendLog('element_not_found', '元素未找到', { selector: step.selector, timeout: timeout }, 'warn'); } catch(e) {}
          self._executeNext();
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
          el.click();
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
      console.log('[ReplayEngine] _waitForElement selector:', JSON.stringify(typeof selector === 'string' ? selector : (selector ? selector.primary : 'null')));

      function check() {
        attempts++;
        var found = SelectorEngine.find(typeof selector === 'string' ? selector : '', selector);
        if (found && found.element) {
          console.log('[ReplayEngine] element found after', attempts, 'attempts');
          if (typeof self._sendLog === 'function') try { self._sendLog('element_found', '元素已找到', { attempts: attempts }); } catch(e) {}
          callback(found.element);
          return;
        }
        if (Date.now() - start >= timeout) {
          console.log('[ReplayEngine] element NOT found after', attempts, 'attempts, timed out');
          callback(null);
          return;
        }
        // 停止时也要调用 callback 保证执行链不断裂
        if (self.stopped || !self.running) {
          console.log('[ReplayEngine] stopped during wait, canceling');
          callback(null);
          return;
        }
        if (attempts <= 3) console.log('[ReplayEngine] attempt', attempts, 'failed, retrying...');
        setTimeout(check, interval);
      }
      check();
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
