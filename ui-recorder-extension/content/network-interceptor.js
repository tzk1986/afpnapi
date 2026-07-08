/**
 * UI 录制器 — 网络请求拦截器（安全模式）
 * 仅拦截 fetch，仅捕获请求结构（method/url/headers/body），不读取响应体。
 * 通过 window.postMessage 将捕获数据发送给 content script。
 */
(function () {
  'use strict';

  if (window.__UI_RECORDER_NETWORK_INTERCEPTOR__) return;
  window.__UI_RECORDER_NETWORK_INTERCEPTOR__ = true;

  var MAX_CAPTURE = 200;
  var _count = 0;
  var POST_MSG_TYPE = '__UI_RECORDER_NETWORK__';

  function _isApiUrl(url) {
    if (!url || typeof url !== 'string') return false;
    try {
      var p = new URL(url, location.href).pathname;
      return p.indexOf('/api/') >= 0;
    } catch (e) {
      return url.indexOf('/api/') >= 0;
    }
  }

  function _headersToObj(headers) {
    var result = {};
    try {
      if (!headers) return result;
      if (typeof headers.forEach === 'function') {
        headers.forEach(function (v, k) { result[k] = v; });
      } else if (typeof headers === 'object' && !headers.forEach) {
        for (var k in headers) {
          if (headers.hasOwnProperty(k)) result[k] = headers[k];
        }
      }
    } catch (e) {}
    return result;
  }

  function _truncate(s, n) {
    if (!s) return '';
    return s.length > n ? s.substring(0, n) + '...' : s;
  }

  // ── 仅拦截 fetch，不动 XHR ──
  var _origFetch = window.fetch;

  window.fetch = function (url, opts) {
    // 快速判断是否需要捕获（不影响非 API 请求的性能）
    var reqUrl;
    try {
      reqUrl = typeof url === 'string' ? url : (url && url.href ? url.href : String(url));
    } catch (e) {
      return _origFetch.apply(this, arguments);
    }

    if (_count >= MAX_CAPTURE || !_isApiUrl(reqUrl)) {
      return _origFetch.apply(this, arguments);
    }

    // 捕获请求信息（不碰响应，不影响页面正常逻辑）
    _count++;
    var method = 'GET';
    var reqHeaders = {};
    var reqBody = '';
    var parsedPath = reqUrl;

    try {
      method = ((opts && opts.method) || 'GET').toUpperCase();
      reqHeaders = _headersToObj(opts && opts.headers);
      if (opts && opts.body && typeof opts.body === 'string') {
        reqBody = _truncate(opts.body, 2000);
      }
      parsedPath = new URL(reqUrl, location.href).pathname;
    } catch (e) {}

    var ts = Date.now();

    // 直接调用原始 fetch，不 clone 响应，不读响应体
    return _origFetch.apply(this, arguments).then(function (resp) {
      try {
        window.postMessage({
          type: POST_MSG_TYPE,
          data: {
            url: reqUrl,
            url_path: parsedPath,
            method: method,
            request_headers: reqHeaders,
            request_body: reqBody,
            response_status: resp.status,
            response_headers: {},
            response_body: '',
            response_content_type: '',
            timestamp: ts,
            duration_ms: Date.now() - ts,
          }
        }, '*');
      } catch (e) {}
      return resp;
    });
  };

  console.log('[UIRecorder] Network interceptor (safe mode) — fetch only, max', MAX_CAPTURE);
})();
