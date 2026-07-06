"""录制器注入脚本生成器。

生成内联注入到代理页面的 JavaScript 代码，
负责事件捕获、选择器生成和与父页面的 postMessage 通信。
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

  function sendEvent(data) {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: 'ui-recorder-event', data: data }, '*');
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

    // 链接拦截：阻止默认导航，通知父页面加载新代理 URL
    var link = el.closest('a');
    if (link && link.href) {
      e.preventDefault();
      e.stopPropagation();
      sendEvent({
        action: 'click',
        selector: SelectorEngine.generate(el),
        value: '',
        element_info: getElementInfo(el),
        page_url: location.href,
        page_title: document.title
      });
      // 通知父页面导航
      window.parent.postMessage({
        type: 'ui-recorder-navigate',
        url: link.href
      }, '*');
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
    inputBuffer.value = isPassword ? '{{password}}' : (el.value || el.textContent || '');
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

  // 表单提交
  function handleSubmit(e) {
    if (!recording) return;
    e.preventDefault();
    sendEvent({
      action: 'submit',
      selector: SelectorEngine.generate(e.target),
      value: '',
      element_info: getElementInfo(e.target),
      page_url: location.href,
      page_title: document.title
    });
    // 通知父页面表单已提交
    window.parent.postMessage({ type: 'ui-recorder-form-submit', form_action: e.target.action || '' }, '*');
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
