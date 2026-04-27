# Body 类型选择与转换增强方案（补充实施方案）

**文档状态**：已决策收口（可实施）  
**涉及范围**：人工用例编辑 / 详情界面编辑的 Body 部分  
**关联约束**：编辑界面模式切换方案 - 章节 2.3.2 / 5.1  
**风险等级**：中-高（涉及多种数据格式转换）  
**创建日期**：2026-04-27

---

## 1. Postman Body 类型完整映射

### 1.1 支持的 Body 类型

| 类型 | 完整名称 | 编码格式 | 适用场景 | 可编辑性 |
|------|--------|--------|--------|--------|
| **none** | 无请求体 | N/A | GET / DELETE 等 | 固定（无） |
| **form-data** | 表单数据 | `multipart/form-data` | 文件上传、复杂表单 | **高** ✓ |
| **urlencoded** | URL编码表单 | `application/x-www-form-urlencoded` | 简单表单提交 | **高** ✓ |
| **raw** | 原始文本 | 用户自定义 | 自由格式（含子类型） | **高** ✓ |
| **binary** | 二进制 | 二进制流 | 上传二进制文件 | **低** ✗ |
| **graphql** | GraphQL 查询 | `application/json` | GraphQL API | **高** ✓ |
| **json** | JSON (raw子类型) | `application/json` | API 请求 | **高** ✓ |

### 1.2 Body 类型的 HTTP 头自动映射

| Body 类型 | 自动设置的 Content-Type | 说明 |
|----------|----------------------|------|
| none | （无） | 不发送 Content-Type |
| form-data | `multipart/form-data; boundary=----...` | 自动生成 boundary |
| urlencoded | `application/x-www-form-urlencoded` | 标准表单编码 |
| raw (JSON) | `application/json` | 需手动设置或自动检测 |
| raw (XML) | `application/xml` | 需手动设置 |
| raw (Text) | `text/plain` | 需手动设置 |
| binary | `application/octet-stream` | 可手动覆盖 |
| graphql | `application/json` | 固定 |

---

## 2. 编辑界面 Body 部分升级

### 2.1 当前结构（方案一阶段）

```
Body 编辑
├─ 类型选择：[无] [表单] [JSON] [原始文本]
├─ 表单模式下显示表单行
└─ JSON/原始文本模式下显示文本框
```

### 2.2 升级后完整结构

```
┌─────────────────────────────────────────┐
│       请求体编辑 (Body)                  │
├─────────────────────────────────────────┤
│ 类型选择：┌──────────────────────────┐  │
│          │ ⬜ 无    ⬜ form-data      │  │
│          │ ⬜ urlencoded  ⬜ raw    │  │
│          │ ⬜ binary  ⬜ GraphQL   │  │
│          └──────────────────────────┘  │
├─────────────────────────────────────────┤
│ [动态内容区 - 根据类型切换]              │
├─────────────────────────────────────────┤
│ ✓ 类型: form-data (multipart/form-data) │
│ ✓ 字符集: UTF-8                        │
│ ┌──────────┬────────────┬───────────┐ │
│ │   Key    │    Value   │   类型    │   │
│ ├──────────┼────────────┼───────────┤ │
│ │ field1   │ value1     │ Text   [✎] │ │
│ │ file     │ [选择文件]  │ File   [✎] │ │
│ │          │            │ Text   [×] │ │
│ └──────────┴────────────┴───────────┘ │
│ [+ 添加字段] [转为 Raw JSON] [批量编辑] │
└─────────────────────────────────────────┘
```

### 2.3 各类型编辑界面详细设计

#### 2.3.1 无请求体 (none)

```html
<div class="body-type-none">
  <div class="body-info">
    <p style="color: #64748b; font-size: 12px;">
      此请求不发送 Body。HTTP 方法通常为 GET / DELETE / HEAD。
    </p>
  </div>
</div>
```

**切换规则**：
- 切换到 none：清空所有 Body 数据，提示 "Body 已清空"
- 从 none 切到其他：默认创建空数据结构

#### 2.3.2 表单数据 (form-data)

```html
<div class="body-type-formdata">
  <div class="body-header">
    <span style="font-size: 12px; color: #64748b;">
      Content-Type: multipart/form-data
    </span>
    <button class="btn-helper" onclick="insertCommonFormFields()">
      📋 插入常见字段
    </button>
  </div>

  <table class="formdata-table">
    <thead>
      <tr>
        <th>Key</th>
        <th>Value / File</th>
        <th>Type</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody id="formdata-rows">
      <!-- 动态行 -->
      <tr class="kv-row" data-row-id="row-1">
        <td><input type="text" class="fd-key" value="username"></td>
        <td><input type="text" class="fd-value" value="user123"></td>
        <td>
          <select class="fd-type" onchange="switchFieldType(this)">
            <option value="text" selected>Text</option>
            <option value="file">File</option>
          </select>
        </td>
        <td><button onclick="removeFormDataRow(this)">×</button></td>
      </tr>
      <tr class="kv-row" data-row-id="row-2">
        <td><input type="text" class="fd-key" value="avatar"></td>
        <td>
          <input type="file" class="fd-file-input" style="display:none;">
          <button class="fd-file-btn" onclick="selectFile(this)">选择文件</button>
          <span class="fd-filename" style="margin-left:8px; font-size:12px;">avatar.png</span>
        </td>
        <td>
          <select class="fd-type">
            <option value="text">Text</option>
            <option value="file" selected>File</option>
          </select>
        </td>
        <td><button onclick="removeFormDataRow(this)">×</button></td>
      </tr>
    </tbody>
  </table>

  <div class="form-actions">
    <button onclick="addFormDataRow('text')">+ 添加文本字段</button>
    <button onclick="addFormDataRow('file')">+ 添加文件字段</button>
  </div>

  <!-- 转换选项 -->
  <div class="convert-options">
    <button onclick="convertFormDataToUrlencoded()">
      转为 URL 编码表单
    </button>
    <button onclick="convertToRawJson()">
      转为 Raw JSON
    </button>
  </div>
</div>
```

**特性**：
- 支持文本字段和文件字段混合
- 支持点号路径键名（如 `address.city`、`items.0.sku`），并按原键名透传请求
- 文件字段真实上传：前端选择文件后，经 `/api/proxy-request` 中转后以 multipart 方式转发目标接口
- 可转换为 URL 编码表单（仅文本字段）
- 自动设置 `multipart/form-data` 头

#### 2.3.3 URL 编码表单 (urlencoded)

```html
<div class="body-type-urlencoded">
  <div class="body-header">
    <span style="font-size: 12px; color: #64748b;">
      Content-Type: application/x-www-form-urlencoded
    </span>
  </div>

  <table class="urlencoded-table">
    <thead>
      <tr>
        <th>Key</th>
        <th>Value</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody id="urlencoded-rows">
      <!-- 动态行 -->
      <tr class="kv-row" data-row-id="row-1">
        <td><input type="text" class="ue-key" value="page"></td>
        <td><input type="text" class="ue-value" value="1"></td>
        <td><button onclick="removeUrlencodedRow(this)">×</button></td>
      </tr>
    </tbody>
  </table>

  <div class="form-actions">
    <button onclick="addUrlencodedRow()">+ 添加字段</button>
  </div>

  <!-- 转换选项 -->
  <div class="convert-options">
    <button onclick="convertUrlencodedToRaw()">
      转为 Raw JSON
    </button>
  </div>
</div>
```

**特性**：
- 仅支持文本键值对
- 自动处理 URL 编码（`&` 分隔，`=` 连接）
- 不支持文件上传
- 可转换为 Raw JSON（作为查询参数格式保留）

#### 2.3.4 原始文本 (raw)

```html
<div class="body-type-raw">
  <div class="body-header">
    <label>Content-Type (选择语言)：</label>
    <select id="raw-language" onchange="updateRawContentType()">
      <option value="json" selected>JSON</option>
      <option value="xml">XML</option>
      <option value="text">Text</option>
      <option value="html">HTML</option>
      <option value="javascript">JavaScript</option>
      <option value="custom">Custom</option>
    </select>
    <input type="text" id="raw-custom-type" placeholder="自定义 MIME 类型" 
           style="display:none; margin-left:8px; width:200px;">
  </div>

  <div class="raw-editor">
    <textarea id="raw-body-input" 
              placeholder='例如：{"name":"John","age":30}'
              style="width:100%; height:300px; font-family:monospace;"></textarea>
    <div class="raw-status">
      <span id="raw-char-count">字数: 0</span>
      <span id="raw-syntax-check" style="margin-left:16px;"></span>
    </div>
  </div>

  <!-- 格式化工具 -->
  <div class="raw-tools">
    <button onclick="prettifyRawBody()">🎨 格式化</button>
    <button onclick="minifyRawBody()">📦 压缩</button>
    <button onclick="validateRawBody()">✓ 校验</button>
  </div>
</div>
```

**特性**：
- 支持多种语言类型（JSON / XML / Text 等）
- 实时字数统计
- JSON/XML 格式化与校验
- 语法高亮、格式化、实时校验为必做能力

#### 2.3.5 二进制 (binary)

```html
<div class="body-type-binary">
  <div class="body-info" style="padding: 16px; background: #f1f5f9; border-radius: 8px;">
    <p style="color: #64748b; margin: 0; font-size: 12px;">
      ⚠️ 二进制格式不支持在表单模式下编辑。
    </p>
    <p style="color: #64748b; margin: 8px 0 0 0; font-size: 12px;">
      若需编辑二进制数据，请：
    </p>
    <ul style="margin: 8px 0 0 16px; font-size: 12px; color: #64748b;">
      <li>切换到 Raw 模式并选择 Custom 类型</li>
      <li>直接上传二进制文件（建议用 form-data）</li>
      <li>使用 Base64 编码后在 Raw JSON 中传输</li>
    </ul>
  </div>
  
  <div class="binary-option" style="margin-top: 12px;">
    <button onclick="switchBodyType('formdata')">切换到 form-data 上传</button>
  </div>
</div>
```

**特性**：
- 不支持直接编辑
- 提示用户三种替代方案
- 快速切换按钮

#### 2.3.6 GraphQL (graphql)

```html
<div class="body-type-graphql">
  <div class="body-header">
    <span style="font-size: 12px; color: #64748b;">
      Content-Type: application/json
    </span>
    <span style="font-size: 12px; color: #2563eb; margin-left: 8px;">
      Auto Fetch
    </span>
  </div>

  <!-- 仿 Postman：左右双栏编辑 -->
  <div class="graphql-editor-split" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
    <div>
      <div style="font-size:12px;color:#334155;margin-bottom:6px;">QUERY</div>
      <textarea id="graphql-query" placeholder='query {
  user(id: "123") {
    name
    email
  }
}' style="height:240px;"></textarea>
    </div>
    <div>
      <div style="font-size:12px;color:#334155;margin-bottom:6px;">GRAPHQL VARIABLES</div>
      <textarea id="graphql-variables" placeholder='{"userId": "123"}' style="height:240px;"></textarea>
      <div class="hint" style="font-size: 12px; color: #94a3b8; margin-top: 8px;">
        Variables 必须是有效 JSON
      </div>
    </div>
  </div>

  <div class="graphql-tools">
    <button onclick="prettifyGraphQL()">🎨 格式化</button>
    <button onclick="validateGraphQL()">✓ 校验</button>
  </div>
</div>
```

**特性**：
- 仿 Postman 左右双栏（Query / Variables）编辑
- Query 语法高亮为必做
- Variables 必须是有效 JSON
- 自动合成 GraphQL 请求体格式

---

## 3. Body 类型转换矩阵

### 3.1 类型间转换规则

```
                    none  formdata  urlencoded  raw-json  raw-text  binary  graphql
none            ──────    清空      清空       {}       ""      警告     {}
formdata         清空   ──────      ✓转换      转换      转换     ✗警告    ✗不支持
urlencoded       清空     ✓转换    ──────      转换      转换     ✗警告    ✗不支持
raw-json          {}     ✓转换      ✓转换     ──────    ✗解析    Base64   ✗不支持
raw-text          ""     ✗不支持   ✗不支持    ✗解析     ──────   ✗警告    ✗不支持
binary           警告    ✗警告     ✗警告     Base64    ✗警告    ──────    ✗不支持
graphql           {}    ✗不支持   ✗不支持    ✗不支持  ✗不支持   ✗不支持   ──────

图例：
✓转换   = 可自动无损转换
✗不支持 = 不支持转换，切换时清空
✗警告   = 有损转换，切换前弹警告
✗解析   = 需要手动处理，切换前提示
──────  = 当前类型（无需转换）
```

### 3.2 具体转换规则

#### form-data → urlencoded
```javascript
function convertFormDataToUrlencoded() {
  const rows = getFormDataRows();
  const textRows = rows.filter(r => r.type === 'text');
  
  if (rows.some(r => r.type === 'file')) {
    showWarning('文件字段会被忽略，仅保留文本字段');
  }
  
  switchBodyType('urlencoded');
  textRows.forEach(r => addUrlencodedRow(r.key, r.value));
}
```

#### urlencoded → form-data
```javascript
function convertUrlencodedToFormData() {
  const rows = getUrlencodedRows();
  switchBodyType('formdata');
  rows.forEach(r => addFormDataRow('text', r.key, r.value));
}
```

#### formdata/urlencoded → raw-json
```javascript
function convertToRawJson() {
  const rows = currentBodyType === 'formdata' 
    ? getFormDataRows().filter(r => r.type === 'text')
    : getUrlencodedRows();
  
  const jsonObj = {};
  rows.forEach(r => {
    jsonObj[r.key] = tryParseValue(r.value);
  });
  
  switchBodyType('raw');
  setRawLanguage('json');
  setRawContent(JSON.stringify(jsonObj, null, 2));
}
```

#### raw-json → form-data/urlencoded
```javascript
function convertFromRawJson(targetType) {
  try {
    const content = getRawContent();
    const obj = JSON.parse(content);
    
    if (targetType === 'formdata') {
      switchBodyType('formdata');
      Object.entries(obj).forEach(([k, v]) => {
        addFormDataRow('text', k, String(v));
      });
    } else if (targetType === 'urlencoded') {
      switchBodyType('urlencoded');
      Object.entries(obj).forEach(([k, v]) => {
        addUrlencodedRow(k, String(v));
      });
    }
  } catch (e) {
    showError('JSON 解析失败，无法转换: ' + e.message);
  }
}
```

#### binary ↔ 任何格式
```javascript
function convertFromBinary(targetType) {
  showWarning(
    '二进制数据无法直接转换。\n' +
    '请选择:\n' +
    '1. 用 Base64 编码后在 Raw 中粘贴\n' +
    '2. 用 form-data 重新上传文件'
  );
  // 不执行转换
}
```

---

## 4. 发送请求时的 Body 处理

### 4.1 发送前数据规范化

```javascript
async function sendManualRequest() {
  // 1. 获取当前 Body 类型
  const bodyType = getSelectedBodyType();
  
  // 2. 根据类型序列化 Body
  let body = null;
  let contentType = null;
  
  switch (bodyType) {
    case 'none':
      body = null;
      break;
      
    case 'formdata':
      // 表单数据需要特殊处理（multipart）
      const formRows = getFormDataRows();
      const formData = new FormData();
      for (const row of formRows) {
        if (row.type === 'file') {
          // 文件需要从 input[type=file] 获取
          const fileInput = row.fileElement;
          if (fileInput.files.length > 0) {
            formData.append(row.key, fileInput.files[0]);
          }
        } else {
          formData.append(row.key, row.value);
        }
      }
      body = formData;  // 保持 FormData 对象，浏览器会自动设置边界
      contentType = null;  // 浏览器自动设置
      break;
      
    case 'urlencoded':
      const ueRows = getUrlencodedRows();
      const params = new URLSearchParams();
      for (const row of ueRows) {
        params.append(row.key, row.value);
      }
      body = params.toString();
      contentType = 'application/x-www-form-urlencoded';
      break;
      
    case 'raw':
      body = getRawContent();
      contentType = getCurrentRawContentType();
      break;
      
    case 'binary':
      showError('二进制类型无法直接在编辑器中发送');
      return;
      
    case 'graphql':
      const query = getGraphQLQuery();
      const variables = getGraphQLVariables();
      body = JSON.stringify({ query, variables });
      contentType = 'application/json';
      break;
  }
  
  // 3. 调用代理请求
  // form-data / binary 走 multipart 上送，确保文件真实上传；其他类型走 JSON
  if (bodyType === 'formdata' || bodyType === 'binary') {
    const relayForm = new FormData();
    relayForm.append('request_meta', JSON.stringify({
      method: getMethod(),
      url: getUrl(),
      headers: mergeHeaders(getHeaders(), contentType),
      params: getParams(),
      body_type: bodyType,
      text_fields: extractTextFieldsFromBody(bodyType),
      file_field_order: extractFileFieldOrder(),
    }));
    appendFilesToRelayForm(relayForm);

    await fetch('/api/proxy-request', {
      method: 'POST',
      body: relayForm,
    });
  } else {
    await proxyRequest({
      method: getMethod(),
      url: getUrl(),
      headers: mergeHeaders(getHeaders(), contentType),
      params: getParams(),
      body_type: bodyType,
      body: body,
    });
  }
}

function mergeHeaders(userHeaders, autoContentType) {
  const merged = { ...userHeaders };
  
  // 自动 Content-Type 优先级：用户手设 > 自动推断
  if (!merged['Content-Type'] && autoContentType) {
    merged['Content-Type'] = autoContentType;
  }
  
  return merged;
}
```

### 4.2 后端接收与处理

```python
@app.route('/api/proxy-request', methods=['POST'])
def proxy_request():
    """
    接收前端转发的请求
    Body 可能是：
      - None
      - JSON 字符串
      - URL 编码字符串
      - FormData 二进制流（需要 requests-toolbelt 处理）
    """
    # 兼容两种输入：
    # 1) application/json（none/urlencoded/raw/graphql）
    # 2) multipart/form-data（form-data/binary，含真实文件）
    if request.content_type and request.content_type.startswith('multipart/form-data'):
      meta = json.loads(request.form.get('request_meta', '{}'))
      method = meta.get('method')
      url = meta.get('url')
      headers = meta.get('headers', {})
      params = meta.get('params', {})
      text_fields = meta.get('text_fields', [])
      file_field_order = meta.get('file_field_order', [])

      files = []
      for field_name in file_field_order:
        f = request.files.get(field_name)
        if f:
          files.append((field_name, (f.filename, f.stream, f.mimetype or 'application/octet-stream')))

      data_fields = [(it['key'], it['value']) for it in text_fields]

      # multipart 透传：不强行写 Content-Type，交由 requests 自动生成 boundary
      headers.pop('Content-Type', None)
      request_kwargs = dict(data=data_fields, files=files)
    else:
      data = request.get_json(silent=True) or {}
      method = data.get('method')
      url = data.get('url')
      headers = data.get('headers', {})
      params = data.get('params', {})
      request_kwargs = dict(data=data.get('body'))
    
    # 注意：FormData 在前端会自动编码，但传到后端需要特殊处理
    # 一般情况下，我们建议前端先序列化为 JSON，后端再反序列化
    
    # 如果前端传的是 FormData，浏览器会自动转为 multipart 二进制
    # 后端需要用 request.data 和 request.files 接收
    
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
          **request_kwargs,
            timeout=(config.REQUEST_CONNECT_TIMEOUT, config.REQUEST_READ_TIMEOUT),
        )
        
        return jsonify({
            'status_code': resp.status_code,
            'elapsed_ms': int(resp.elapsed.total_seconds() * 1000),
            'response_headers': dict(resp.headers),
            'response_body': resp.text,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

---

## 5. 完整的风险规避方案

### 5.1 数据转换风险

| 风险 | 原因 | 规避方案 |
|------|------|--------|
| 类型转换数据丢失 | formdata 含文件转 urlencoded | 转换前提示 "文件字段会被忽略" |
| 嵌套对象转表单失败 | JSON `{a:{b:1}}` 转表单格式 | 使用点号路径 `a.b` 或二级表头 |
| 编码错误 | 特殊字符在 URL 编码时出错 | 使用 `URLSearchParams` 自动编码 |
| 类型推断失败 | Value `"123"` 应为 number | 在表单中显示类型提示或类型选择器 |
| GraphQL 语法错误 | 用户输入无效 GraphQL Query | 在提交前校验，显示错误位置 |

### 5.2 UI 交互风险

| 风险 | 原因 | 规避方案 |
|------|------|--------|
| 文件字段未选择 | form-data 中文件为空 | 发送前检查，提示 "文件未选择" |
| 超大文件上传卡顿 | 在编辑器中处理 MB 级文件 | 限制文件大小预览 5MB，超过提示"无法预览"，但仍允许真实上传 |
| 类型快速切换丢失编辑 | 用户在 A 类型编辑，切到 B 再切回 | 记录编辑历史或弹出确认对话框 |
| 混淆 Body 和 Params | 用户在 Body 中填 URL 参数 | UI 上明确分离，使用不同颜色/区块 |

### 5.3 性能风险

| 风险 | 原因 | 规避方案 |
|------|------|--------|
| 大 JSON 解析阻塞 | Body 超过 10MB | 限制编辑器只支持 10MB 以内，超过提示"过大" |
| FormData 行渲染卡顿 | 文件表单 200+ 行 | 限制最多 100 行，使用虚拟滚动 |
| 频繁格式化 JSON | 用户点"格式化"频繁 | 添加节流（300ms）与后台 Worker 校验 |

### 5.4 安全风险

| 风险 | 原因 | 规避方案 |
|------|------|--------|
| 敏感数据明文显示 | Body 含密码/Token | 在 Raw JSON 中检测常见敏感关键字，打 `[敏感]` 徽章 |
| 文件路径穿越 | 文件选择器允许任意路径 | 使用原生 `<input type="file">`，浏览器沙盒限制 |
| 注入攻击 | GraphQL Query 含特殊字符 | GraphQL 在解析时会自动转义，无需特殊处理 |
| XML 外部实体 (XXE) | Raw XML 含外部引用 | 提示用户 "XML 中禁止外部实体引用" |

### 5.5 兼容性风险

| 风险 | 原因 | 规避方案 |
|------|------|--------|
| 旧浏览器不支持 FormData | IE 11 等 | 降级方案：FormData 转 URL 编码 |
| 二进制文件无法在浏览器编辑 | 浏览器安全限制 | 不支持直接编辑，仅提示"请用 form-data 上传" |
| 跨域 CORS 限制 | /api/proxy-request 的 CORS | 后端添加 CORS 头允许跨域 |

### 5.6 约束冲突风险

| 冲突点 | 当前约束 | 新方案影响 | 规避 |
|-------|---------|---------|------|
| 敏感字段替换 | details.json 中敏感头替换为 `***` | 表单编辑时敏感字段可见 | 编辑时显示 `[敏感]` 徽章，保存时仍替换 |
| Body 大小限制 | 未定义 | 编辑器需要限制 Body 大小 | 新增配置项 `MAX_BODY_SIZE_FOR_EDIT` 默认 10MB |
| 模板外置约束 | 所有 UI 在 templates/ | Body 类型选择 JS 逻辑位置 | 所有 Body 类型处理逻辑在模板内实现 |

---

## 6. 实现要点

### 6.1 新增 HTML 结构（补充）

```html
<!-- Body 类型选择器 -->
<div class="body-type-selector">
  <label>Body 类型：</label>
  <div class="type-buttons">
    <button class="type-btn" data-type="none" onclick="switchBodyType('none')">
      无
    </button>
    <button class="type-btn" data-type="formdata" onclick="switchBodyType('formdata')">
      form-data
    </button>
    <button class="type-btn" data-type="urlencoded" onclick="switchBodyType('urlencoded')">
      x-www-form-urlencoded
    </button>
    <button class="type-btn" data-type="raw" onclick="switchBodyType('raw')">
      raw
    </button>
    <button class="type-btn" data-type="binary" onclick="switchBodyType('binary')">
      binary
    </button>
    <button class="type-btn" data-type="graphql" onclick="switchBodyType('graphql')">
      GraphQL
    </button>
  </div>
</div>

<!-- Body 内容容器 -->
<div id="body-content-container">
  <!-- 动态内容根据类型切换 -->
</div>
```

### 6.2 新增 JavaScript 核心函数（补充）

```javascript
// Body 类型管理
let currentBodyType = 'none';
let bodyDataCache = {};  // 缓存各类型的数据，支持切换时恢复

function switchBodyType(newType) {
  // 1. 校验转换可行性
  if (!canConvert(currentBodyType, newType)) {
    showWarning(`无法从 ${currentBodyType} 转换到 ${newType}`);
    return;
  }
  
  // 2. 保存当前类型的数据
  bodyDataCache[currentBodyType] = getCurrentBodyData();
  
  // 3. 尝试转换
  const converted = convertBodyData(currentBodyType, newType);
  
  // 4. 更新 UI
  currentBodyType = newType;
  renderBodyEditor(newType, converted);
  
  // 5. 更新按钮状态
  updateBodyTypeButtons(newType);
}

// 各类型的数据获取函数
function getFormDataRows() { }
function getUrlencodedRows() { }
function getRawContent() { }
function getCurrentRawContentType() { }
function getGraphQLQuery() { }
function getGraphQLVariables() { }

// 各类型的数据设置函数
function setFormDataRows(rows) { }
function setUrlencodedRows(rows) { }
function setRawContent(content) { }
function setRawLanguage(lang) { }

// 转换函数
function convertBodyData(fromType, toType) {
  const converters = {
    'formdata_to_urlencoded': convertFormDataToUrlencoded,
    'formdata_to_raw': convertFormDataToRaw,
    'urlencoded_to_formdata': convertUrlencodedToFormData,
    'urlencoded_to_raw': convertUrlencodedToRaw,
    'raw_to_formdata': convertRawToFormData,
    'raw_to_urlencoded': convertRawToUrlencoded,
  };
  
  const key = `${fromType}_to_${toType}`;
  return converters[key]?.() || null;
}

function canConvert(fromType, toType) {
  const allowed = {
    'none': ['formdata', 'urlencoded', 'raw', 'graphql'],
    'formdata': ['none', 'urlencoded', 'raw'],
    'urlencoded': ['none', 'formdata', 'raw'],
    'raw': ['none', 'formdata', 'urlencoded'],
    'binary': ['none'],
    'graphql': ['none'],
  };
  
  return allowed[fromType]?.includes(toType) ?? false;
}
```

### 6.3 CSS 样式新增（补充）

```css
.body-type-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.type-buttons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.type-btn {
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  transition: all 0.2s;
}

.type-btn.active {
  background: #3b82f6;
  color: #fff;
  border-color: #3b82f6;
  font-weight: 600;
}

.type-btn:hover:not(.active) {
  border-color: #94a3b8;
  background: #f8fafc;
}

.formdata-table, .urlencoded-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 12px;
}

.formdata-table th, .urlencoded-table th {
  background: #f1f5f9;
  padding: 8px;
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  color: #334155;
  border: 1px solid #e2e8f0;
}

.formdata-table td, .urlencoded-table td {
  padding: 8px;
  border: 1px solid #e2e8f0;
}

.fd-key, .fd-value, .ue-key, .ue-value {
  width: 100%;
  padding: 6px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  font-size: 12px;
}

.fd-type, .body-header select {
  padding: 4px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  font-size: 12px;
}

.body-info {
  padding: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  color: #0c4a6e;
  font-size: 12px;
}

.raw-editor textarea {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Courier New', monospace;
  resize: vertical;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  padding: 12px;
}

.raw-status {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.raw-tools, .graphql-tools, .form-actions, .convert-options {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.raw-tools button, .graphql-tools button, 
.form-actions button, .convert-options button {
  padding: 6px 12px;
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.raw-tools button:hover, .graphql-tools button:hover,
.form-actions button:hover, .convert-options button:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
}

.graphql-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  border-bottom: 2px solid #e2e8f0;
}

.tab-btn {
  padding: 8px 16px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 12px;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
}

.tab-btn.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

.tab-content textarea {
  width: 100%;
  height: 200px;
  padding: 12px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  resize: vertical;
}
```

---

## 7. 测试策略补充

### 7.1 单元测试（数据转换）

```javascript
// 测试案例
test('formdata -> urlencoded 转换', () => {
  const formData = [
    { key: 'name', value: 'John', type: 'text' },
    { key: 'file', value: null, type: 'file' },
  ];
  const urlencoded = convertFormDataToUrlencoded(formData);
  expect(urlencoded).toEqual([
    { key: 'name', value: 'John' },
  ]);
});

test('raw JSON -> formdata 转换', () => {
  const json = '{"age":30,"active":true}';
  const formdata = convertRawToFormData(json);
  expect(formdata).toEqual([
    { key: 'age', value: '30', type: 'text' },
    { key: 'active', value: 'true', type: 'text' },
  ]);
});

test('urlencoded -> raw JSON 转换保留类型', () => {
  const urlencoded = [
    { key: 'page', value: '1' },
    { key: 'name', value: 'test' },
  ];
  const json = convertUrlencodedToRaw(urlencoded);
  const parsed = JSON.parse(json);
  expect(parsed.page).toBe(1);  // 自动转为数字
  expect(parsed.name).toBe('test');  // 保持字符串
});
```

### 7.2 集成测试（交互）

```javascript
// 流程测试
test('完整编辑流程：formdata -> 编辑 -> 转 raw -> 发送', async () => {
  // 1. 初始化为 formdata
  switchBodyType('formdata');
  addFormDataRow('text', 'username', 'admin');
  addFormDataRow('file', 'avatar', null);
  
  // 2. 转换到 raw
  switchBodyType('raw');
  expect(getSelectedBodyType()).toBe('raw');
  const rawContent = getRawContent();
  expect(rawContent).toContain('"username":"admin"');
  
  // 3. 修改 raw 内容
  setRawContent('{"username":"root","age":30}');
  
  // 4. 发送请求
  await sendManualRequest();
  // 验证请求体正确发送
});
```

### 7.3 端到端测试（冒烟）

```powershell
# 测试场景
1. 新增人工用例 - form-data 模式
   - 添加文本字段 + 文件字段
   - 转换到 urlencoded（检查文件被忽略）
   - 发送请求 → 验证成功

2. 编辑人工用例 - 从 raw JSON 转到 form-data
   - 编辑现有 JSON 人工用例
   - 切换到 form-data 模式
   - 验证 JSON 被正确解析为表单行
   - 修改数据后发送 → 验证修改生效

3. GraphQL 查询测试
   - 新增 GraphQL 类型的人工用例
   - 输入有效 Query + Variables
   - 验证发送时能正确格式化为 JSON

4. 大数据处理测试
   - 创建超过 10MB 的 Body
   - 验证编辑器提示 "过大，建议直接编辑 raw"
```

---

## 8. 文档与配置更新

### 8.1 新增配置项（config.py）

```python
# Body 编辑配置
BODY_TYPE_OPTIONS = [
    'none', 'form-data', 'urlencoded', 'raw', 'binary', 'graphql'
]
MAX_BODY_SIZE_FOR_EDIT = int(os.environ.get("MAX_BODY_SIZE_FOR_EDIT", "10485760"))  # 10MB
MAX_FORMDATA_ROWS = int(os.environ.get("MAX_FORMDATA_ROWS", "100"))
MAX_FORMDATA_FILE_SIZE = int(os.environ.get("MAX_FORMDATA_FILE_SIZE", "104857600"))  # 100MB
RAW_BODY_SYNTAX_HIGHLIGHT_ENABLED = str(os.environ.get("RAW_BODY_SYNTAX_HIGHLIGHT_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}
GRAPHQL_VALIDATION_ENABLED = str(os.environ.get("GRAPHQL_VALIDATION_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}
RAW_EDITOR_SYNTAX_HIGHLIGHT = str(os.environ.get("RAW_EDITOR_SYNTAX_HIGHLIGHT", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}
RAW_EDITOR_REALTIME_VALIDATE = str(os.environ.get("RAW_EDITOR_REALTIME_VALIDATE", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}
```

### 8.2 约束文档更新清单

**开发阅读文档.md - 新增约束**
```
28. 人工用例 Body 编辑约束：
    - Body 支持 6 种类型（none/formdata/urlencoded/raw/binary/graphql）
    - 类型间转换遵循转换矩阵（章节 3.1），无损转换前无需确认，有损转换前需弹确认
    - Body 大小限制由 config.py 的 MAX_BODY_SIZE_FOR_EDIT 统一管理（默认 10MB）
    - 发送请求时 Content-Type 自动从 Body 类型推断，用户手设的 Header 优先级更高
    - form-data 中的文件字段在编辑器中不实际上传，仅记录文件名供显示
```

**操作手册.md - 新增章节**
```
4.6 编辑人工用例的 Body 类型
- 介绍 6 种 Body 类型的含义与适用场景
- 演示各类型的编辑界面与转换方式
- 说明"大数据"提示与处理建议
```

---

## 9. 实施优先级与里程碑

### 优先级划分

```
P0 必做（第一阶段）：
  ├─ Body 类型选择器 UI 与 switchBodyType() 函数
  ├─ 四种基础类型编辑界面：none / formdata / urlencoded / raw
  ├─ 类型间基础转换（JSON ↔ 表单）
  └─ 发送请求时的 Body 序列化处理

P1 应做（第二阶段）：
  ├─ 文件上传支持（form-data）
  ├─ 类型转换数据丢失时的确认弹窗
  ├─ 大 Body 检测与警告
  └─ Raw 模式的格式化/校验工具

P2 可做（第三阶段）：
  ├─ GraphQL 专用编辑器（Query + Variables 分离）
  ├─ 二进制模式的降级方案
  ├─ Raw 模式的语法高亮（可选）
  └─ Body 历史记录与撤销支持
```

### 交付里程碑

```
阶段 1（2-3 天）：核心 Body 类型支持
  ├─ 实现 P0 必做项
  └─ 端到端测试（formdata/urlencoded/raw 三种模式）

阶段 2（2-3 天）：完善交互与工具
  ├─ 实现 P1 应做项
  ├─ 集成人工用例编辑流程
  └─ 冒烟测试验证所有转换路径

阶段 3（1 天）：收尾与文档同步
  ├─ 实现 P2 可做项（可选）
  ├─ 约束文档同步更新
  └─ 操作手册增加 Body 类型说明
```

---

## 10. 关键决策点

### 10.1 已确认决策

- [x] Body 类型列表采用完整 Postman 方案：none / form-data / x-www-form-urlencoded / raw / binary / GraphQL
- [x] form-data 支持点号路径键名（如 `address.city`）
- [x] 文件上传采用真实上传链路（前端文件 -> `/api/proxy-request` -> 目标接口）
- [x] GraphQL 编辑器采用仿 Postman 双栏界面（Query + GraphQL Variables）
- [x] Raw 模式语法高亮、格式化、实时校验均为必做

### 10.2 进入实施前的固定执行项

1. `/api/proxy-request` 完成 JSON 与 multipart 双协议兼容。
2. `templates/report_view.html` 完成 Body 六类型编辑器与类型切换矩阵。
3. Raw 编辑器接入语法高亮、格式化、实时校验（JSON/XML/GraphQL Variables）。
4. GraphQL 编辑器切换为仿 Postman 双栏布局。
5. 完成运行时回归：`/health`、`/`、`/report-view`、`/api/report-results?include_excluded=true/false`、`/api/manual-cases` add/update/delete、`/api/export-collection`。

---

**文档完成于：2026-04-27**  
**版本：v1.2.0-body-types-locked**  
**状态：已锁定，可开始实施**
