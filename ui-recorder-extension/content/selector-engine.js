/**
 * 多策略选择器生成引擎
 * 优先级：test-id > ARIA role > id > name > text（唯一性校验） > CSS 短路径 > XPath
 *
 * 关键改进：
 * 1. text 选择器增加唯一性校验（document.querySelectorAll 必须只匹配1个元素）
 * 2. CSS 路径在 dropdown/popover 容器内时包含容器上下文，避免同文本多元素歧义
 */
class SelectorEngine {
  static generate(el) {
    const strategies = [
      () => this.byTestId(el),
      () => this.byAriaRole(el),
      () => this.byId(el),
      () => this.byNameAttr(el),
      () => this.byText(el),
      () => this.byCssShort(el),
      () => this.byXPath(el),
    ];

    let primary = null;
    for (const strategy of strategies) {
      const result = strategy();
      if (result) {
        primary = result;
        break;
      }
    }
    if (!primary) {
      primary = this.byXPath(el);
    }

    const fallbackCss = (this.byId(el) || this.byCssShort(el) || {}).selector || '';
    const fallbackXpath = (this.byXPath(el) || {}).selector || '';

    return {
      primary: primary.selector,
      strategy: primary.strategy,
      fallback_css: fallbackCss,
      fallback_xpath: fallbackXpath,
    };
  }

  static byTestId(el) {
    const id = el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('data-cy');
    if (id) return { selector: `[data-testid="${id}"]`, strategy: 'test-id' };
    return null;
  }

  static byAriaRole(el) {
    const role = el.getAttribute('role') || this._inferRole(el);
    const name = (el.getAttribute('aria-label') || (el.textContent || '').trim().substring(0, 50)).trim();
    if (role && name) return { selector: `role=${role}[name="${name}"]`, strategy: 'role' };
    return null;
  }

  static byText(el) {
    const text = (el.textContent || '').trim();
    if (!text || text.length === 0 || text.length > 50 || el.children.length !== 0) return null;
    const selector = `text="${text.replace(/"/g, '\\"')}"`;
    // 唯一性校验：text 选择器必须在页面上只匹配1个元素
    let matchCount = 0;
    const all = document.querySelectorAll('*');
    for (let i = 0; i < all.length; i++) {
      if (all[i].children.length === 0 && (all[i].textContent || '').trim() === text) {
        matchCount++;
        if (matchCount > 1) break;
      }
    }
    if (matchCount === 1) return { selector, strategy: 'text' };
    // 文本不唯一，降级到 CSS 路径
    return null;
  }

  static byId(el) {
    if (el.id && !/^\d/.test(el.id) && !el.id.includes(':')) {
      return { selector: `#${this._escapeCss(el.id)}`, strategy: 'id' };
    }
    return null;
  }

  static byNameAttr(el) {
    const name = el.getAttribute('name');
    if (name) return { selector: `[name="${name}"]`, strategy: 'name' };
    return null;
  }

  /** 检测元素是否在 dropdown/popover 容器内 */
  static _isInDropdownContext(el) {
    let current = el;
    while (current && current !== document.body) {
      const cls = current.className || '';
      if (typeof cls === 'string') {
        const dropdownPatterns = [
          'el-select-dropdown', 'el-dropdown-menu', 'el-picker-panel',
          'ant-select-dropdown', 'ant-dropdown-menu', 'ant-picker-panel',
          'popover', 'tooltip', 'menu', 'dropdown',
          '[role="listbox"]', '[role="menu"]', '[role="dialog"]'
        ];
        for (const pattern of dropdownPatterns) {
          if (pattern.startsWith('[')) {
            if (current.matches && current.matches(pattern)) return true;
          } else {
            if (cls.indexOf(pattern) >= 0) return true;
          }
        }
      }
      current = current.parentElement;
    }
    return false;
  }

  static byCssShort(el) {
    const path = [];
    let current = el;
    let stoppedEarly = false;

    // 如果在 dropdown/popover 内，先收集到容器边界的路径
    const inDropdown = this._isInDropdownContext(el);
    let dropdownBoundary = null;
    if (inDropdown) {
      let tmp = el;
      while (tmp && tmp !== document.body) {
        const cls = tmp.className || '';
        if (typeof cls === 'string' && (
          cls.indexOf('el-select-dropdown') >= 0 ||
          cls.indexOf('el-dropdown-menu') >= 0 ||
          cls.indexOf('ant-select-dropdown') >= 0 ||
          cls.indexOf('ant-dropdown-menu') >= 0 ||
          (tmp.getAttribute('role') || '').match(/^(listbox|menu|dialog)$/)
        )) {
          dropdownBoundary = tmp;
          break;
        }
        tmp = tmp.parentElement;
      }
    }

    while (current && current !== document.body && current !== document.documentElement) {
      let segment = current.tagName.toLowerCase();
      if (current.id) {
        segment = `#${this._escapeCss(current.id)}`;
        path.unshift(segment);
        stoppedEarly = true;
        break;
      }
      const classList = current.classList;
      if (classList && classList.length > 0) {
        const classes = Array.from(classList).slice(0, 2).map(c => `.${this._escapeCss(c)}`).join('');
        segment += classes;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
        if (siblings.length > 1) {
          const index = siblings.indexOf(current) + 1;
          segment += `:nth-of-type(${index})`;
        }
      }
      path.unshift(segment);
      // 到达 dropdown 边界时停止向上追溯
      if (dropdownBoundary && current === dropdownBoundary) {
        stoppedEarly = true;
        break;
      }
      current = current.parentElement;
      const candidate = path.join(' > ');
      try {
        if (document.querySelectorAll(candidate).length === 1) {
          stoppedEarly = true;
          break;
        }
      } catch (e) {
        break;
      }
    }
    const selector = path.join(' > ');
    return selector ? { selector, strategy: 'css' } : null;
  }

  static byXPath(el) {
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      let index = 0;
      let sibling = current.previousSibling;
      while (sibling) {
        if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === current.tagName) index++;
        sibling = sibling.previousSibling;
      }
      const tagName = current.tagName.toLowerCase();
      const part = index > 0 ? `${tagName}[${index + 1}]` : tagName;
      parts.unshift(part);
      current = current.parentNode;
      if (current === document) break;
    }
    return { selector: '/' + parts.join('/'), strategy: 'xpath' };
  }

  static _inferRole(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'input' && type === 'text') return 'textbox';
    if (tag === 'input' && type === 'password') return 'textbox';
    if (tag === 'input' && type === 'email') return 'textbox';
    if (tag === 'input' && type === 'search') return 'searchbox';
    if (tag === 'input' && type === 'checkbox') return 'checkbox';
    if (tag === 'input' && type === 'radio') return 'radio';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'img') return 'img';
    if (tag === 'nav') return 'navigation';
    if (tag === 'main') return 'main';
    if (tag === 'form') return 'form';
    return null;
  }

  static _escapeCss(str) {
    if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(str);
    return str.replace(/([^\w-])/g, '\\$1');
  }
}

if (typeof window !== 'undefined') {
  window.SelectorEngine = SelectorEngine;
}
