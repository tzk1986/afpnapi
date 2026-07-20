# Postman API 测试工具文档入口（统一目录）

版本：v1.30.76
发布日期：2026-07-20
文档定位：新人入口，总览目录、安装、配置、首次执行与报告查看。

本版新增重点（v1.30.76）：
- **Vite SPA 回放修复**：`_rewrite_js_imports` 新增静态 `import ... from` 和 `export ... from` 相对路径改写，修复 Vite 构建的 JS bundle 中 vendor chunk 在代理环境下 404 导致 SPA 页面灰屏

本版新增重点（v1.30.70）：
- **代理 JS 动态 import 改写**：`fetch_resource` 对 JS 内容改写 `import("./chunk.js")` 和 `new URL("./chunk.js", import.meta.url)` 为代理资源 URL，修复 Vite 构建应用 vendor chunk 404 导致页面无法渲染

本版新增重点（v1.30.69）：
- **回放计时器暂停同步**：暂停时计时器停止计时，恢复后继续；最终耗时与汇总均扣除暂停时长

本版新增重点（v1.30.68）：
- **UI 回放停止/暂停按钮修复**：停止按钮页面加载后即可用（不再依赖 `isRunning`）；`stopReplay()` 去掉 `isRunning` 守卫，始终执行清理；新增 `replayFinished` 标志区分"未完成"与"已结束"；引擎 `_waitForElement` 暂停时冻结超时计时

本版新增重点（v1.30.67）：
- **mypy 零错达成**：`ui_proxy_service.py` 中 `lambda m, an=..., ip=...:` 默认参数闭包改写为 `_make_replacer` 闭包工厂（mypy 8 → 0 错）；94 个源文件 mypy 全通过
- **开发阅读文档走查精简**（v1.30.66 内容）：852 → 524 行（-38%）；目录结构同步实际代码；测试总数 1217 → ~2100；report_server.py 路由数 33 → 38

本版新增重点（v1.30.65）：
- **代码质量优化**：ruff F401 清理 73 个未使用导入（跨 26 个文件）；修复 `report_export_service` 从 `utils/file_utils` 而非 `report_server_utils` 导入 `sanitize_export_name`（消除潜在运行时 ImportError）
- **类型注解修复**：`ui_proxy_service` 中 `_set_cookies` 类型从 `Dict[str,str]` 改为 `Dict[str,Any]` 以容纳 `list[str]`；`report_server` 中 `body` 标注为 `Union[str, bytes]` 匹配双返回类型；mypy 从 8 错降至 1 错

本版新增重点（v1.30.33）：
- **合成事件链接点击显式导航**：回放引擎使用 el.click() 派发合成事件，浏览器不会自动执行链接导航。修复后 click 链接时显式设置 location.href 跳转到链接目标，确保页面导航发生
- **click 拦截 href 转代理 URL**：早期脚本捕获阶段转换 target="_blank" 为 _self + href 改写为代理 URL
- **new_tab 三层拦截**：(1) 拦截 window.open；(2) click 事件捕获阶段转换；(3) click 执行前转换

本版新增重点（v1.30.24）：
- **el-select 下拉选择修复**：移除 type 操作中对 el-select 输入框的 Enter keyup 事件（会关闭下拉框），让录制的 click 步骤在保持下拉框打开状态下完成选项选择

本版新增重点（v1.30.23）：
- **选择器生成唯一性保障**：text 选择器增加页面全局唯一性校验，不唯一时自动降级 CSS 路径；dropdown 内元素 CSS 路径包含容器边界上下文，避免同文本多元素歧义

本版新增重点（v1.30.22）：
- **Element UI 下拉框自动选择**：回放引擎 type 操作后自动检测 el-select popper 并点击匹配选项，解决可搜索下拉框选择失败

本版新增重点（v1.30.21）：
- **SPA 导航计时器不重置**：从 `_proxy_url` 参数提取原始 target origin 做同域判断，Vue.js SPA 点击菜单不再刷新 iframe

本版新增重点（v1.30.0）：
- **SPA 导航不再刷新 iframe**：回放引擎在 SPA 内导航时不再重新加载 iframe，避免跳回第一步
- **用例编辑器拖拽排序**：拖拽步骤序号列即可重排序，点击行选中后可在选中位置插入步骤
- **元素未找到自动截图**：回放时元素未找到自动保存页面快照，超时从 30 秒缩短至 5 秒
- **录制器初始化**：打开 URL 时清除旧代理会话，确保从干净状态开始录制
- **fetch/XHR 拦截器锁定**：用 Object.defineProperty 防止后续脚本覆盖代理拦截器

本版新增重点（v1.29.59）：
- **日志目录统一**：`report_server.log` 从 `reports/` 移到 `logs/`，与无头执行日志统一目录，保留期改为 10 天自动清理
- **无头执行请求日志**：`logs/headless/exec_{job_id}.jsonl` 记录 Playwright 执行过程中的 API 请求（method/url/headers/status）
- **网络请求录制**：Chrome 插件录制时捕获 fetch/XHR 请求结构，回放时自动比对差异
- **SPA 404 修复**：pushState/replaceState 不再改写为代理 URL，window.location 补丁兜底

本版新增重点（v1.29.0）：
- **UI 报告存档**：执行报告统一存储到 `uireports/` 目录（不提交 git），首页新增"报告列表"按钮
- **报告列表页面**：`/ui-testing/reports` 可查看/删除报告，支持状态筛选（全部/通过/失败/执行中/已取消）和分页（10/20/50/全部）
- **进度条修复**：任务创建时即设置 steps_total，进度条百分比正确计算，整个执行周期内始终可见
- **导出报告按钮**：报告详情页新增"导出报告"按钮，触发浏览器打印转 PDF；回放页面"导出报告"改为"查看报告"

本版新增重点（v1.28.0）：
- **报告页面实时轮询**：执行中自动每 2 秒刷新进度，显示进度条、实时统计数据、步骤状态更新；右上角手动刷新按钮
- **无头执行自动导航**：修复无界面模式下缺少 navigate 步骤导致元素找不到的问题，引擎自动跳转到 base_url
- **设置响应格式修复**：前端 JS 正确提取 `resp.data` 而非整个响应体
- **执行按钮读取设置默认模式**：不再硬编码浏览器回放，尊重用户在设置页面选择的默认执行模式

本版新增重点（v1.26.0）：
- **UI 测试无头浏览器执行（Phase 2）**：新增 Playwright 无头浏览器执行模式，后台线程自动执行步骤（无需打开回放页面）；支持失败截图、步骤级进度上报；执行结果 HTML 报告页面（可打印）；Playwright 为可选依赖，通过 `UI_HEADLESS_ENABLED=true` 启用。
- **导出报告优化**：回放页面的"导出报告"按钮从原始 JSON 改为样式化 HTML 报告页面，包含状态徽章、统计卡片、步骤详情表格。

本版新增重点（v1.25.0）：
- **UI 测试回放执行框架（Phase 1）**：编辑器新增"▶ 执行"按钮，创建执行任务后跳转到回放页面；回放页面通过 iframe 代理加载目标页面，注入回放引擎 JS 逐步执行操作（click/type/navigate/wait/assert 等）；执行结果实时上报并持久化为 JSON 报告；支持暂停/继续/停止控制、步骤进度显示、执行历史列表。

本版新增重点（v1.24.4）：
- **UI 测试体验优化**：编辑器步骤描述从 element_info 自动生成（录制数据无需手动补充描述）；首页"查看"从系统 alert 升级为 Modal 弹窗（步骤表格展示）；录制器导出改为文件下载（不再新页面显示 JSON）；新增"导入到 UI 测试"一键导入按钮；报告中心首页新增录制器跳转链接。
- **回放执行框架方案补充**：方案文档新增完整验证测试用例矩阵（Phase 1-3 共 50+ 测试场景）和日志功能设计（30+ 日志事件、字段规范、调试排查指引、采样策略）。

本版新增重点（v1.24.3）：
- **Web UI 自动化测试模块**：服务端反向代理 + iframe 注入录制器，无需安装 Chrome 扩展即可录制页面操作（点击、输入、导航等），生成可回放的自动化测试用例。
- **日志文件支持**：通过 `LOG_FILE` 环境变量配置 RotatingFileHandler，所有日志同时输出到控制台和文件，便于排查错误。
- **SPA 代理修复**：HTML URL 改写跳过 `<script>` 内容，修复 Vue/React 等 SPA 页面在 iframe 代理中无法加载的问题；注入 fetch/XHR 拦截器重定向 API 调用（支持相对路径和所有 HTTP 方法）。

本版新增重点（v1.23.0）：
- **Collection 编辑器文件上传**：formdata 模式支持 Text/File 类型切换，binary 模式支持文件选择，执行时自动上传文件并构建 multipart 请求。

本版新增重点（v1.21.0）：
- **缓存命中验证**：ad-hoc 页面新增"重复次数"配置，同一接口重复执行 N 次（1~10），报告中展示每次响应时间对比，用于验证服务端缓存是否生效。

本版新增重点（v1.20.15）：
- **合并 v1.20.13 + v1.20.14**：Collection 编辑器快捷键体系（Ctrl+S/D/N/F/1~6/Enter 等 11 项快捷键 + 帮助面板）+ 竞品调研文档；WCAG 无障碍增强（ARIA 角色/标签）+ executor 异常类型细化（2→7 类）+ config.py `_env_int()` 安全规范化。

本版新增重点（v1.20.14）：
- **WCAG 无障碍增强 + 异常诊断优化 + 配置安全规范化**：Collection 编辑器添加 ARIA 角色/标签（tablist/tab/aria-live/aria-label），executor 异常类型从 2 类细化为 7 类，config.py 新增 `_env_int()` 安全读取函数统一规范化 18 处 int 转换。

本版新增重点（v1.20.12）：
- **测试代码质量优化**：修复 `test_report_lock_service.py` 中 `lock._count` 不存在的属性引用，补充 12 个"不抛异常即通过"测试的注释说明，增强 3 个测试的断言覆盖。

本版新增重点（v1.20.11）：
- **Preview/代码生成 disabled 过滤修复**：Collection 编辑器 Request Preview 和代码生成功能现在正确过滤 disabled 的 Headers/Params，预览不再显示被禁用的条目。

本版新增重点（v1.20.10）：
- **缺陷修复 + 安全增强**：编辑器 Headers/Params disabled 勾选未生效修复，复选框布局错位修复，URL netloc 正则校验增强（防 CRLF 注入），重复 DOM ID 修复，未使用导入清理。

本版新增重点（v1.20.9）：
- **竞品借鉴三项改进**：Headers/Params 批量文本编辑模式（`key: value` 格式，`#` 注释禁用行），报告详情页 JSONPath 响应过滤器（支持 `$.data[*].name`、`..id` 等语法），响应体文本搜索与高亮（🔍 搜索栏 + Enter/F3 导航 + 匹配计数）。

本版新增重点（v1.20.8）：
- **消除重复代码**：executor._extract_message_and_err_code 委托到 response_parser.extract_msg_errcode（28→3 行），analytics_utils._to_bool 复用 report_server_utils.to_bool，config.py 22 处布尔解析模式统一为 _env_bool() 辅助函数（400→363 行，-9%）。

本版新增重点（v1.20.7）：
- **代码走查精简**：回退 request_builder 5 个过度抽象的 `_build_*_body` 函数及分派字典为内联 if-elif，回退 executor `_prepare_request_context`（6-tuple 返回值）为内联代码，修复 services/__init__.py BOM 语法错误，补充 report_patch_service pop() 副作用注释。
- **全量走查**：审查 84 个源文件、55 个短小单次调用私有函数，确认无其他过度抽象。

本版新增重点（v1.20.6）：
- **代码质量重构**：report_patch_service.patch_report_result 重构（114→87 行，-24%），request_builder.set_request_body 重构（78→40 行，-49%），executor.execute_test 重构（209→167 行，-20%），总计提取 10 个辅助函数，重构 401 行代码。
- **测试覆盖强化**：report_patch_service 辅助函数测试覆盖（+12 项），总计 1983 个测试。

本版新增重点（v1.20.5）：
- **测试覆盖强化**：test_proxy_routes 模块测试覆盖（+7 项，覆盖昨晚重构的辅助函数），url_utils 模块测试覆盖（+12 项），总计 1971 个测试。

本版新增重点（v1.20.3）：
- **代码重构 + 测试覆盖强化**：request_builder.build_request_kwargs 重构（109→30 行，-72%），test_proxy_routes.re_request_api 重构（131→100 行，-24%），新增 assertions 模块测试（35 项），新增 report_meta_repository 模块测试（22 项），总计 1952 个测试。

本版新增重点（v1.20.2）：
- **请求/响应对比视图**：Collection 编辑器新增并排对比功能，支持选择 2 次请求历史，对比 URL/Headers/Body/Response 差异，LCS 算法行级高亮，6 个 Tab 切换。

本版新增重点（v1.19.1）：
- **JSON tree 搜索修复**：修复子串匹配问题，搜索"测试"现在能正确高亮"测试部"、"测试用例"等包含关键字的所有文本。

本版新增重点（v1.19.0）：
- **JSON tree 搜索功能**：Collection 编辑器响应体 JSON tree 顶部新增搜索框，输入关键字实时高亮匹配节点，自动展开包含匹配项的父节点，支持上一个/下一个跳转（▲▼按钮或 Enter/Shift+Enter），匹配计数显示。
- **测试覆盖强化**：新增 12 个单元测试（report_engine），总计 1805 个测试。
- **安全加固**：所有报告相关 API 端点添加输入长度验证（report_name: 255, case_id: 100, exclusion_key: 500），防止超长字符串攻击。

本版新增重点（v1.18.3）：
- **JSON 层级缩进修复**：Collection 编辑器响应体 JSON tree 和请求 body preview 根据嵌套深度递进缩进（每层 2 空格），闭合括号与开头对齐。

本版新增重点（v1.18.2）：
- **代码质量重构**：统一原子写入实现，`checkpoint_manager.py` 复用 `atomic_write_json()` 消除重复代码。
- **测试覆盖强化**：新增 66 个单元测试（html_reporter 39 项 + execution_helpers 27 项），总计 1793 个测试。
- **安全加固**：路由错误信息脱敏，500 错误使用 `type(exc).__name__` 替代 `str(exc)`，防止内部实现泄露。

本版新增重点（v1.17.0）：
- **安全修复**：serve_report 目录穿越漏洞修复（CWE-22）；config 数值配置添加上下限保护，防止环境变量注入。
- **代码质量提升**：report_server_utils DRY 重构；base_handler 日志格式统一；编辑器键盘快捷键；首页报告计数与加载占位。
- **测试覆盖强化**：新增 62 个单元测试（report_utils/logging_utils/models），总计 1292 个测试。

本版新增重点（v1.16.0）：
- **代码生成扩展至 41 种语言**：新增 Dart（http 库）和 Rust（reqwest）代码生成器，总计 41 种语言/格式，覆盖主流后端与移动端技术栈。
- **响应元信息行**：Response 面板顶部新增 Status/Time/Size/Content-Type/Server 五项元信息，一眼掌握响应关键指标。
- **二进制/图片响应预览**：图片类型响应（image/*）自动以 base64 内联预览；PDF 等二进制类型给出明确提示，不再显示乱码。

本版新增重点（v1.15.0）：
- **代码片段生成（39 种语言/格式）**：编辑器 Tab 栏新增复制图标按钮，支持 Shell(cURL/HTTPie/Wget)、Python(Requests/http.client)、JavaScript(fetch/Axios/jQuery/XHR)、Node.js(Fetch/Axios/HTTP/Request/Unirest)、Java(OkHttp/java.net.http/Unirest/AsyncHttp)、Go、C#(HttpClient/RestSharp)、C(Libcurl)、PHP(cURL/HTTP v1/v2)、Ruby、R(httr)、Kotlin(OkHttp)、Swift、Objective-C、Clojure、OCaml、PowerShell、Raw/HTTP、HTTPie CLI/Desktop、HAR，按语言家族分组缩进下拉。
- **响应格式化（5 种格式）**：Response 面板新增格式下拉（Raw/JSON/YAML/XML/HTML），即时切换，复制按钮同步格式输出。
- **请求预览**：Body Tab 新增 Code/Preview 切换，Preview 展示完整 HTTP 请求报文（URL/Header/Body 均替换为实际变量值），可一键关闭。

本版新增重点（v1.14.1）：
- **约束走查修正**：开发阅读文档完成重复/冲突/分类检查，修正 7 项问题；历史版本号 v1.8.0~v1.8.4 修正为 v1.5.0~v1.8.0 以保证单调递增；favicon 约束移至正确章节。

本版新增重点（v1.14.0）：
- **代码质量重构**：提取 `atomic_write_json()` 消除 4 处重复原子写入模式；提取 `get_report_or_error()` 消除 8+ 处重复报告查找模式；统一 `retry_routes` 两个重试函数为 `_dispatch_retry()` 参数化分发。

本版新增重点（v1.13.0）：
- **跨 scope 变量覆盖提示**：设置面板和编辑器自动补全中显示全局/环境/预设变量间的覆盖关系，标注最终生效来源（绿色加粗）及生效值，解决同名变量冲突不透明问题。
- **补全下拉增强**：被覆盖变量显示"⚡被覆盖"标记 + 来源详情行，变量值过长时支持横向滚动。

本版新增重点（v1.12.0）：
- **多环境变量管理**：全局变量支持多环境作用域（shared + 按环境分组），首页右上角齿轮按钮打开设置面板，支持环境增删、行内编辑（Hoppscotch 风格）、显示/隐藏切换。
- **变量覆盖顺序**：执行时变量合并优先级为 initial_variables > 环境变量 > 全局共享变量（shared），同名 key 后者覆盖前者。
- **可视化编辑器集成**：Collection 编辑器自动加载全局/环境变量，执行和导出时自动合并嵌入。
- **变量函数帮助入口**：设置面板新增"变量函数"Tab，展示 6 个内置函数的语法和示例。

本版新增重点（v1.10.0）：
- **断言引擎扩展**：新增 4 种断言操作符 — `regex`（正则匹配）、`length_eq`（数组/字符串长度）、`type`（类型检查）、`schema`（JSON Schema 验证，需安装 jsonschema）。总计支持 13 种操作符。

本版新增重点（v1.11.0）：
- **变量函数**：支持 `{{timestamp()}}`、`{{uuid()}}`、`{{random_int(1,100)}}`、`{{date()}}`、`{{datetime()}}` 等内置函数，由 `ENABLE_VARIABLE_FUNCTIONS` 控制。
- **全局变量持久化**：`GLOBAL_VARIABLES_FILE` 配置指定 JSON 文件路径后，执行结束自动保存提取的变量，下次执行自动加载。
- **全局变量 CRUD 路由**：`GET/POST/DELETE /api/global-variables` 接口，支持 Web UI 管理持久化变量。

本版新增重点（v1.9.0）：
- **并发执行引擎**：基于 ThreadPoolExecutor + 依赖感知分批调度，`ENABLE_CONCURRENT=true` 启用后接口按变量依赖拓扑排序并行执行，预期 5-10x 提速；默认关闭保持串行兼容。
- **线程安全改造**：PostmanTestReport、VariableContext、ConcurrentProgressTracker 均加锁保护，支持多线程并发写入不丢数据。

本版新增重点（v1.8.1）：
- **测试覆盖强化**：补充 collection_editor_routes 路由层 19 个测试用例，覆盖全部 4 个路由函数的成功/错误路径和 12 个错误码。

本版新增重点（v1.8.0）：
- **接口管理增强**：可视化编辑器新增 7 项接口管理能力——空白接口新增、接口复制（跨分组/批量/右键）、cURL 导入（支持 20+ 高级参数）、HAR 导入（响应 body 自动提取变量到 x_extract）、Postman 代码片段导入（自动检测 Python/JS/Go/Java/cURL）、新建文件夹（无限嵌套/拖拽移动/重命名/删除）、接口跨文件夹拖拽（单选/多选批量移动）。
- **统一导入入口**：侧边栏新增下拉菜单统一 5 种导入方式，右键菜单支持快速复制/删除/跨分组复制。

本版新增重点（v1.7.0）：
- **变量自动补全**：编辑器中输入 `{{` 自动弹出可用变量列表（预置变量/运行时变量/提取规则），支持键盘导航、实时过滤、点击或回车插入，自动闭合 `}}`。

本版新增重点（v1.6.0）：
- **可视化编辑器执行结果页内展示**：点击"执行"后弹出模态框实时显示进度（百分比/完成数/总数），完成后展示结果摘要并提供查看报告链接，关闭弹窗后编辑器状态完整保留，不再跳转页面。
- **接口拖拽排序**：可视化编辑器左侧接口列表支持拖拽调整顺序，导出和执行均按页面显示顺序进行。
- **Body 变量替换修复**：当 raw body 包含 `{{variable}}` 占位符（非有效 JSON）时，变量替换后自动重新解析为 JSON 对象，避免接口返回 400。

本版新增重点（v1.5.0）：
- **Collection 可视化编辑器**：导入 Postman Collection JSON 后在线编辑接口参数、Headers、Body、x_extract 配置；支持单接口发送（Send）→ 查看响应 → JSON 树点击生成 x_extract 的完整调试闭环。
- **运行时变量池**：Send 后自动执行 x_extract 提取变量，后续请求自动替换 `{{变量}}`，支持预置变量与运行时变量合并。
- **批量选择删除**：导入后可勾选不需要的接口批量删除，方便导出精简后的 Collection。
- **变量依赖分析增强**：以表格形式展示变量生产接口→消费接口的流向关系，可点击跳转。
- **统一错误码体系**：80 处 API 错误全部编码（`CE_/COL_/JOB_/RPT_/HTTP_/COM_` 前缀），前端显示 `[错误码] 提示信息`，操作手册新增错误码速查表。

本版新增重点（v1.3.2）：
- **安全加固**：修复 XSS（html_reporter.py 全面转义 + Jinja2 模板化）、XML 注入（JUnit 导出转义）、SSRF（URL 协议白名单 + `PROXY_ALLOWED_HOSTS` 域名白名单）。
- **代码质量精细化**：消除 adhoc/collection 7 个重复函数（统一至 `utils/collection_utils.py`）；统一 `_json_error()` 至 `base_handler.json_error()`；修复 `report_export_service.py` 逆向依赖；并发锁加固（缓存锁 + RLock + 线程异常捕获）。
- **Jinja2 模板外置**：`_generate_index_html()` 从 600 行 f-string 重构为 `templates/report_index.html` Jinja2 模板渲染。
- **死代码清理**：删除 `core/pipeline.py`（占位实现）及无引用模块。

本版新增重点（v1.3.1）：
- **子目录报告生成与访问**：`output_dir` 自动创建为 `reports/` 子目录；报告中心支持递归扫描子目录中的报告；原始 HTML 可正确访问子目录下的报告文件。
- **报告扫描排除目录**：新增 `REPORT_SCAN_EXCLUDE_DIRS` 配置（默认 `"old"`），报告中心自动排除指定目录下的历史报告，保持列表整洁。
- **已知问题修复**：修复 `PostmanTestReport` 运行时未定义（循环导入规避）；修复 `send_from_directory` 在子目录场景下因 `secure_filename` 扁平化路径导致的 404；根目录新增兼容启动器 `report_server.py`。

本版新增重点（v1.3.0）：
- **5 阶段代码质量精细化重构收官**：
  1. Phase 3 路由深度提取：`postman_api_tester/report_server.py` 从 1324 行缩减至 272 行，全部 33 条路由的业务逻辑提取至 `handlers/` 下 9 个独立模块（`server_routes`、`job_routes`、`retry_routes`、`export_routes`、`test_proxy_routes`、`report_meta_routes`、`report_result_routes`、`collection_routes`、`page_routes`），report_server.py 仅保留路由装饰器与单行委托调用。
  2. Phase 4 类型检查全量合规：`mypy --strict` 全项目通过，修复 15 处类型错误；handlers/ 目录独立通过 strict 检查。
  3. Phase 5 测试覆盖补齐：新增 42 个 handler 单元测试，总计 79 个测试全部通过；覆盖 server/export/test-proxy/retry/job/report-meta 路由的正常路径与异常路径。
- 同时保留分析洞察图表可视化（Chart.js 六大图表）、响应时间记录与展示、一键重试全部失败用例、多环境配置切换、JSONPath 断言规则、JUnit XML 报告导出、首页报告列表筛选增强，并保持与现有任务队列、报告三件套、历史对比、导出与人工用例能力完全兼容。

v1.2.1 实施补充：已落地 1.1（断点恢复/部分成功报告/断言严格模式）与 1.3（报告列表摘要懒加载/结果分块渲染/流式导出接口）；同时新增导出通道三态策略（`auto` / `legacy` / `stream`）与阈值自动分流，默认配置下保持旧行为兼容。

v1.2.3 实施补充：新增结构化日志事件字典与日志字段规范文档；健康检查 `/health` 扩展返回日志告警快照（`log_alert`），支持基于 ERROR 速率阈值的轻量监控。

v1.2.4 文档补充：`开发阅读文档.md` 已完成约束去重归并（合并重复条目、统一编号结构、阶段化历史记录），关联文档口径同步更新。

关联文档：

- `postman_api_tester/操作手册.md`：需要完整操作步骤、报告中心说明、故障排查时继续阅读。
- `postman_api_tester/快速命令参考.md`：需要快速执行命令、参数优先级、常见命令示例时优先查看。
- `postman_api_tester/最终交付清单.md`：需要打包交付、对外移交、验收范围时查看。
- `postman_api_tester/开发阅读文档.md`：需要修改代码、确认约束边界、同步开发基线时查看。
- `postman_api_tester/日志事件字典.md`：需要按 `event` 维度建立检索/看板时查看。
- `postman_api_tester/日志字段规范.md`：需要统一日志字段与告警阈值口径时查看。

本文档用于交付给其他测试同学时，作为统一入口说明。

## 0. 程序目录结构（新人先看）

下面是当前项目中和接口测试、报告中心最相关的目录与文件：

```text
d:/tangzk/py/seldom-api-testing/
├─ postman_api_tester/               # 核心测试模块与文档目录（包内主实现）
│  ├─ __main__.py                    # 包级启动入口（python -m postman_api_tester）
│  ├─ postman_api_tester.py          # 主执行入口，负责解析 Postman、发请求、生成报告
│  ├─ report_server.py               # 报告中心路由装配（Flask 路由装饰器与单行委托）
│  ├─ report_server_app.py           # 报告服务应用工厂与生命周期管理
│  ├─ report_server_config.py        # 配置读取工具函数
│  ├─ config.py                      # 地址、Token、超时、报告目录等集中配置
│  ├─ core/                          # 核心执行层（报告生成、执行管道、断点恢复、类型定义）
│  ├─ handlers/                      # 路由编排层（server/job/retry/export/test-proxy/report-meta/report-result/collection/page）
│  ├─ services/                      # 领域服务层（导出、重试、列表、判定、锁、提交等）
│  ├─ utils/                         # 通用工具层（URL、请求构建、脱敏、缓存、解析）
│  ├─ models.py                      # 共享数据模型与结构定义
│  ├─ report_repository.py           # 报告仓储（列表缓存、报告发现）
│  ├─ report_meta_repository.py      # 元数据读写仓储
│  ├─ report_job_store.py            # 任务状态内存存储
│  ├─ assertions.py                  # JSONPath 断言引擎（需 ENABLE_ASSERTIONS=true）
│  ├─ run_test_and_open.py           # 交互式快速启动脚本
│  ├─ README.md                      # 文档总入口（本文）
│  ├─ 操作手册.md                    # 完整操作说明
│  ├─ 快速命令参考.md                # 常用命令速查
│  ├─ 开发阅读文档.md                # 开发约束与版本基线
│  └─ 最终交付清单.md                # 交付时的文件清单
├─ templates/                        # 外置 HTML 模板（报告首页、数据视图等）
├─ reports/                          # 默认报告输出目录（html/details/meta）
├─ logs/                             # 日志目录（统一 10 天自动清理）
│  ├─ report_server.log                  # 回放日志、网络比对日志、导航日志
│  └─ headless/                          # 无头执行请求日志（JSONL 格式）
├─ uploaded_collections/             # 报告中心上传执行时保存的 Collection 与导出文件
├─ requirements.txt                  # 依赖安装入口
├─ allow_report_server_firewall.ps1  # Windows 防火墙放通 5000 端口脚本
├─ sample_api_collection.json        # 示例 Collection
├─ _smoke_test.py                    # 冒烟测试脚本（验证核心能力是否正常）
├─ test_data/                        # 冒烟测试与验证脚本
├─ tests/                            # pytest 单元测试（79 个测试）
└─ 其他业务/测试目录                  # 如 api_object/、test_dir/ 等
```

建议新人先建立下面这层认知：

- `postman_api_tester/` 是测试执行核心和文档中心。
- `python -m postman_api_tester` 启动报告服务（通过包级 `__main__.py` 入口）。
- `templates/` 是报告中心页面模板，页面显示问题优先看这里。
- `reports/` 是测试执行后的默认产物目录，报告中心默认也从这里读数据。
- `logs/` 是日志目录，包含回放日志（`report_server.log`）和无头执行请求日志（`headless/exec_{job_id}.jsonl`），统一 10 天自动清理。
- `uploaded_collections/` 是通过报告中心网页上传执行时产生的中间文件目录。

### 0.1 调用路径总览（目录迁移后）

1. 服务启动路径：`python -m postman_api_tester` -> `__main__.py` -> `postman_api_tester/report_server.py`。
2. 路由处理路径：`report_server.py` 路由 -> `handlers/*`（参数校验与编排）-> `services/*`（业务能力）-> `report_repository.py` / `report_meta_repository.py` / `report_job_store.py`（仓储与状态）。
3. 通用能力路径：`handlers/services` 共享依赖 `utils/*`（URL 合并、请求体构建、响应解析、脱敏、缓存）。
4. 执行链路路径：任务入队与重试由 `handlers/job_routes.py` 编排，最终调用 `postman_api_tester.py` 的 `run_postman_tests()` 生成报告三件套。

## 1. 文档位置统一

当前与 Postman API 测试工具相关的文档（不含报告产物）已统一放在本目录：

- README.md（本文，交付入口）
- 开发阅读文档.md（开发前必读 + 约束汇总 + 更新命令）
- 操作手册.md（完整手册）
- 快速命令参考.md（常用命令速查）
- 最终交付清单.md（交付说明）

### 文档阅读顺序

如果你是第一次接手这个项目，建议按下面顺序阅读：

1. `README.md`
	先建立目录结构、安装步骤、首次执行和报告查看的整体认知。
2. `操作手册.md`
	在已经知道整体路径后，继续看完整操作流程、报告中心说明和故障排查。
3. `快速命令参考.md`
	在实际执行时，直接查常用命令、参数写法和优先级规则。
4. `最终交付清单.md`
	在需要打包给其他同学、做交付说明或验收时查看。
5. `开发阅读文档.md`
	只有在准备改代码、调整默认行为或确认约束边界时再进入这份文档。

## 2. 一步一步安装（给新同学）

### 第 0 步：先把代码拉到本地

如果是 Git 仓库拉取，建议放到固定开发目录，例如：

```powershell
git clone <你的仓库地址> d:\tangzk\py\seldom-api-testing
cd d:\tangzk\py\seldom-api-testing
```

如果不是 Git 拉取，而是直接收到压缩包，也建议解压到类似目录后再执行下面步骤。

### 第 1 步：准备 Python

要求：Python 3.10 及以上。

### 第 2 步：进入项目目录

```powershell
cd d:\tangzk\py\seldom-api-testing
```

### 第 3 步：安装依赖

```powershell
pip install -r requirements.txt
```

### 第 4 步：配置地址、Token、报告路径

编辑文件：`postman_api_tester/config.py`

关键配置：

- `BASE_URL`：默认目标服务地址
- `TOKEN`：默认认证 token（可空）
- `REPORT_OUTPUT_DIR`：报告输出目录（可空，空时默认 `项目根目录/reports`）
- `ENABLE_SELECTIVE_RUN`：是否启用“导入后仅执行已选接口”能力
- `ENABLE_ADHOC_RUN`：是否启用首页“新增接口测试”独立页面入口
- `ADHOC_MAX_ITEMS`：单次 ad-hoc 任务允许录入的最大接口数
- `ADHOC_DEFAULT_COLLECTION_NAME`：ad-hoc 临时任务默认集合名称
- `REPORT_EXPORT_DEFAULT_SCOPE`：报告导出默认范围（`full` / `report_only`）
- `REPORT_EXPORT_CHANNEL_MODE`：导出通道模式（`auto` / `legacy` / `stream`）
- `REPORT_EXPORT_STREAM_THRESHOLD`：自动分流阈值（总接口数 >= 阈值时优先走流式）
- `ENABLE_RESPONSE_TIME`：是否记录并展示每接口响应时间（默认 `True`）
- `ENABLE_RETRY_FAILURES`：是否在报告页启用"一键重试失败用例"按钮（默认 `True`）
- `ENABLE_JUNIT_EXPORT`：是否启用 JUnit XML 导出链接（默认 `True`）
- `ENABLE_REPORT_LIST_FILTER`：是否启用首页报告列表筛选面板（默认 `True`）
- `ENABLE_REPORT_ANALYTICS`：是否启用“分析洞察”页签及 analytics 接口（默认 `True`）
- `REPORT_ANALYTICS_TOP_N_DEFAULT` / `REPORT_ANALYTICS_TOP_N_MAX`：分析 TopN 默认值与上限
- `REPORT_ANALYTICS_TREND_LIMIT_DEFAULT` / `REPORT_ANALYTICS_TREND_LIMIT_MAX`：趋势序列默认值与上限
- `REPORT_ANALYTICS_ENABLE_SAMPLES`：是否默认返回错误样本（默认 `False`）
- `REPORT_ANALYTICS_HISTOGRAM_BUCKETS`：响应时间直方图桶边界（默认 `0,50,100,200,500,1000,3000,5000`）
- `QUALITY_SCORE_FAILED_PENALTY` / `QUALITY_SCORE_ERROR_PENALTY` / `QUALITY_SCORE_SLOW_PENALTY` / `QUALITY_SCORE_ASSERTION_MISSING_PENALTY`：质量评分扣分项阈值
- `ENABLE_ASSERTIONS`：是否启用 JSONPath 断言校验（默认 `False`，需显式开启）
- `ASSERTIONS_ENGINE`：断言引擎类型（默认 `jsonpath`）
- `ENVIRONMENTS`：多环境配置字典（键为环境名，值为 `{base_url, token}`），通过环境变量 `ENVIRONMENTS_JSON` 注入 JSON
- `DEFAULT_ENV_NAME`：默认激活的环境名称
- `ENABLE_CHECKPOINT_RECOVERY`：是否启用断点恢复（默认 `False`）
- `CHECKPOINT_FLUSH_EVERY_N`：每执行 N 条写入一次 checkpoint（默认 `1`）
- `CHECKPOINT_DIR`：checkpoint 目录（空则默认 `reports/checkpoints`）
- `ENABLE_ASSERTION_STRICT_MODE`：断言引擎异常是否严格判定为失败（默认 `False`）
- `LOG_LEVEL`：日志级别（`DEBUG/INFO/WARNING/ERROR`）
- `LOG_FORMAT`：日志格式（`structured/json`）
- `LOG_SAMPLE_RATE`：高频日志采样率（默认 `0.1`）
- `LOG_ALERT_ERROR_WINDOW_SECONDS`：ERROR 速率统计窗口（秒，默认 `300`）
- `LOG_ALERT_ERROR_RATE_THRESHOLD_PER_MIN`：ERROR 告警阈值（每分钟，默认 `10`）
示例：

```python
BASE_URL = "http://10.50.11.130:11000"
TOKEN = ""
REPORT_OUTPUT_DIR = r"D:\api-test-reports"
```

建议按下面顺序配置：

1. 先改 `BASE_URL`，确保指向当前测试环境。
2. 如果接口必须登录，再决定是直接填 `TOKEN`，还是留空让程序自动登录获取。
3. 如果团队希望把报告统一输出到固定目录，再改 `REPORT_OUTPUT_DIR`。
4. 如需调整请求等待时间，可继续看 `REQUEST_CONNECT_TIMEOUT` 和 `REQUEST_READ_TIMEOUT`。

如果不想改代码文件，也可以用环境变量临时覆盖：

```powershell
$env:POSTMAN_BASE_URL = "http://10.50.11.130:11000"
$env:POSTMAN_TOKEN = "your_token"
python -m postman_api_tester.postman_api_tester "sample_api_collection.json"
```

## 3. 一步一步执行测试

推荐新人的最短上手路径：

1. 先修改 `postman_api_tester/config.py` 中的 `BASE_URL`。
2. 准备一个可执行的 `*.postman.json` 文件。
3. 用命令行跑一次测试，确认能生成报告。
4. 再启动 `report_server.py` 查看结果和失败详情。

### 方式 A：命令行执行（推荐）

```powershell
python -m postman_api_tester.postman_api_tester "支付（UPS）.postman.json"
```

如果只是第一次验证环境是否打通，建议直接用示例文件或一份最小 Collection 先跑通，不要一开始就执行几百个接口。

可选完整参数：

```powershell
python -m postman_api_tester.postman_api_tester <postman_file> [base_url] [output_dir] [token] [results_per_page]
```

说明：

- `output_dir`：本次执行临时覆盖报告目录
- `results_per_page`：报告分页大小

### 方式 B：交互式快速执行

```powershell
python postman_api_tester/run_test_and_open.py
```

脚本会引导你选择：

1. Postman 文件
2. base_url
3. 报告输出目录
4. 每页条数

执行完会自动打开报告中心。

## 4. 查看报告（正式使用）

### 启动报告中心

```powershell
python -m postman_api_tester
```

访问：

- 本机：`http://127.0.0.1:5000`
- 局域网：`http://你的IP:5000`

页面里常见入口含义：

- `报告中心首页`：查看历史报告、删除报告、做差异对比。
- `上传并执行`：支持先解析集合接口，再选择“全量执行”或“仅执行已选接口”。
- `新增接口测试`：在首页点击入口按钮后进入独立页面，录入接口（名称/目录/方法/URL/Headers/Params/Body）并执行生成报告，无需先准备完整 Collection 文件。支持多环境下拉选择与 JSONPath 断言配置（需 `ENABLE_ASSERTIONS=true`）。
- `数据视图`：按接口逐条查看请求头、参数、响应体、错误信息；报告页带响应时间列（耗时 ms）与 avg/max/p95 统计汇总。
- `分析洞察`：在单报告页新增 analytics 页签，查看状态/方法/目录分布、响应时间直方图、错误分类、建议、质量评分、覆盖率与历史趋势；受 `ENABLE_REPORT_ANALYTICS` 控制。
- `报告对比`：分析洞察页签内支持选择左右两份报告进行成功率、平均响应、失败数、错误数与质量分差异对比；数据来自 `/api/report-analytics-compare`。
- `人工用例编辑器`：按三段式流程新增/编辑人工用例（先发送请求，再确认 PASSED/FAILED，再保存）。
- `编辑器切换与 Body 选择`：mc 与 er 双编辑器互相隔离，Body 类型切换互不污染；支持 none/raw/urlencoded/formdata/graphql/binary 切换。
- `导入执行一致性`：针对导出后二次导入场景，`request.url` 仅含 `raw`（缺少 `path`）时也可被正确解析并执行，避免“预览 2 条、执行 1 条”。
- `导出参数完整性`：导出人工用例时保留完整请求参数（headers/params/body/body_mode/body_data），避免导入后请求体为空或参数缺失。
- `结果行内排除`：在结果列表直接执行“排除/取消排除”，无需先打开详情弹窗。
- `详情人工判定`：结果详情支持“标记成功/标记失败/恢复自动结果”，可在不重发请求时修正状态并回写 summary。
- `实际URL去重`：当配置 URL 已含 query 且 params 也有同名参数时，详情“实际请求 URL”按去重合并规则展示，不再重复拼接。
- `原始 HTML`：打开生成时的原始静态报告。
- `查看元数据`：查看当前报告的结构化摘要与结果索引。
- `导出最新 JSON`：支持按全量导出或仅导出“本次报告涉及接口”。
- `导出范围选择`：`full` 适合完整回归；`report_only` 适合最小复现。本次报告已覆盖全量时，两者导出内容可能一致，页面会提示“范围等价”。
- `一键重试失败用例`：报告页工具栏点击"重试失败用例"，后端自动重跑所有 FAILED/ERROR 接口并生成新报告，无需手动重新上传集合。
- `导出通道策略`：支持 `auto` / `legacy` / `stream` 三态。`auto` 按阈值自动分流（大报告优先流式），流式失败会自动回退旧接口；`legacy` 强制旧接口；`stream` 强制流式接口。

### 4.1 分析洞察速览（2.1）

当 `ENABLE_REPORT_ANALYTICS=true` 时，单报告页会显示“分析洞察”页签，并启用以下接口：

- `GET /api/report-analytics/<report_name>`：返回单报告 analytics 聚合结果。
- `GET /api/report-analytics-compare?left=...&right=...`：返回左右报告 analytics 快照与差异值。

页面可查看的重点信息：

- 基础分布：状态分布、方法分布、目录 TopN。
- 性能分布：响应时间直方图、avg/p50/p95/p99/max。
- 故障诊断：错误分类占比、高频错误、按类别生成的修复建议。
- 质量评分：总分、稳定性分、性能分、断言完整性分与扣分明细。
- 覆盖率：执行覆盖率、人工覆盖率、未覆盖接口 TopN。
- 趋势与对比：最近同集合报告趋势，以及左右报告 delta 对比。

如需灰度关闭，可通过环境变量临时覆盖：

```powershell
$env:ENABLE_REPORT_ANALYTICS = "false"
python -m postman_api_tester
```
- `一键重试失败用例`：报告页工具栏点击"重试失败用例"，后端自动重跑所有 FAILED/ERROR 接口并生成新报告，无需手动重新上传集合。
- `JUnit XML 导出`：报告页工具栏提供"导出 JUnit XML"链接，下载 JUnit 格式报告，可接入 Jenkins/GitLab CI 等 CI/CD 管线展示测试结果。
- `响应时间展示`：数据视图结果列表新增"耗时(ms)"列，底部汇总区显示 avg/max/p95 响应时间。
- `首页列表筛选`：首页报告列表支持按通过状态、最低通过率、日期范围快速筛选，一键重置。
- `多环境切换`：首页上传表单与 ad-hoc 页面支持切换已配置的测试环境，`base_url` 与 `token` 跟随环境切换。配置项 `ENVIRONMENTS` 可通过环境变量 `ENVIRONMENTS_JSON` 注入 JSON 格式字典。
ad-hoc 直接新增接口测试补充：

- 无需先上传 Collection 文件，首页点击“打开新增接口测试页”后，在独立页面录入 1..N 条接口即可入队执行。
- URL 支持绝对 `http/https` 地址、`{{baseUrl}}/...` / `{{base_url}}/...` 变量地址，或配合 `base_url` 的相对路径。
- 单次任务接口数量上限由 `postman_api_tester/config.py` 的 `ADHOC_MAX_ITEMS` 控制，默认集合名由 `ADHOC_DEFAULT_COLLECTION_NAME` 提供。
- 后端通过 `/api/run-ad-hoc-tests` 接收 JSON 请求，内部会先生成临时 Collection 文件到 `uploaded_collections/`，再复用既有任务队列与状态轮询链路。

补充说明：

- 人工用例“发送请求”由后端代理接口处理，仅允许 `http/https` 协议。
- 编辑重试接口 `/re-request-api` 与代理接口口径一致，均仅允许 `http/https` 协议。
- 代理请求超时统一读取 `postman_api_tester/config.py`（`REQUEST_CONNECT_TIMEOUT`、`REQUEST_READ_TIMEOUT`）。

运行验证脚本（可复用）：

- `python test_data/smoke_report_server_20260427.py`

### 报告目录配置一致性

报告中心读取目录优先级：

1. 环境变量 `POSTMAN_REPORTS_DIR`
2. 环境变量 `REPORTS_DIR`
3. `postman_api_tester/config.py` 中 `REPORT_OUTPUT_DIR`
4. 默认 `项目根目录/reports`

这样可以保证“测试执行输出目录”和“报告中心读取目录”一致。

## 5. 打包给其他测试同学的建议

建议打包内容：

- `postman_api_tester/`
- `report_server.py`
- `allow_report_server_firewall.ps1`
- `requirements.txt`
- 需要执行的 `*.postman.json`

首次交付时让对方按本文档第 2、3、4 节逐步执行即可。

## 6. 新人第一次使用的推荐顺序

如果你是第一次接手这个项目，建议按下面顺序操作：

1. 先看本文第 0 节目录结构，知道“测试执行”和“报告查看”分别在哪。
2. 再改 `postman_api_tester/config.py` 的 `BASE_URL` / `TOKEN` / `REPORT_OUTPUT_DIR`。
3. 执行 `pip install -r requirements.txt` 安装依赖。
4. 用一份最小 `*.postman.json` 跑命令行测试。
5. 确认 `reports/` 或你配置的目录下生成了 `.html`、`_details.json`、`_meta.json` 三件套。
6. 启动 `python -m postman_api_tester`，再从浏览器进入报告中心查看结果。
7. 若要给其他机器访问，再执行 `allow_report_server_firewall.ps1`。

## 7. 常见问题

- 报告中心看不到最新报告：确认 `REPORT_OUTPUT_DIR` 与报告中心读取目录一致。
- 局域网打不开：执行 `allow_report_server_firewall.ps1` 放通 5000 端口。
- 中文乱码：PowerShell 先执行 `$env:PYTHONIOENCODING="utf-8"`。

## 8. 开发维护说明

> **约束记录维护提示**：`postman_api_tester/开发阅读文档.md` 中的「约束更新记录」必须按记录时间升序维护（同日按时分秒排序）；新增记录前需先走查本文件及四份关联文档，发现乱序、拼接、重复时必须先恢复排序与结构，再追加新记录。详见 `开发阅读文档.md` 约束 44。
