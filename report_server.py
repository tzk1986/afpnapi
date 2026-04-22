#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""报告服务端，支持历史报告浏览、单报告查询、分页、详情与局域网访问。"""

import json
import logging
import os
import re
import socket
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from flask import Flask, jsonify, redirect, render_template, render_template_string, request, send_from_directory, url_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent


def resolve_reports_dir() -> Path:
    env_dir = (os.environ.get("POSTMAN_REPORTS_DIR") or os.environ.get("REPORTS_DIR") or "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    try:
        from postman_api_tester import config as cfg
        cfg_dir = getattr(cfg, "REPORT_OUTPUT_DIR", "").strip()
        if cfg_dir:
            return Path(cfg_dir).expanduser().resolve()
    except Exception:
        pass

    return (PROJECT_ROOT / "reports").resolve()


REPORTS_DIR = resolve_reports_dir()
UPLOADS_DIR = (PROJECT_ROOT / "uploaded_collections").resolve()
EXPORTS_DIR = (UPLOADS_DIR / "exports").resolve()

RUN_JOBS: Dict[str, Dict[str, Any]] = {}
RUN_JOBS_LOCK = threading.Lock()

# 按报告名维护独立写锁，防止并发回写同一报告时产生竞争
REPORT_WRITE_LOCKS: Dict[str, threading.Lock] = {}
_REPORT_WRITE_LOCKS_META = threading.Lock()


def get_report_write_lock(report_name: str) -> threading.Lock:
    with _REPORT_WRITE_LOCKS_META:
        if report_name not in REPORT_WRITE_LOCKS:
            REPORT_WRITE_LOCKS[report_name] = threading.Lock()
        return REPORT_WRITE_LOCKS[report_name]


app = Flask(__name__, template_folder=str((PROJECT_ROOT / "templates").resolve()))

# 模板渲染模式：
# - inline（默认）：沿用内嵌模板，行为与历史版本一致
# - external：优先使用 templates/*.html，失败时自动降级 inline
_TEMPLATE_MODE = str(os.environ.get("REPORT_TEMPLATE_MODE", "inline")).strip().lower() or "inline"


def render_with_fallback(template_name: str, inline_template: str, **context: Any):
    if _TEMPLATE_MODE == "external":
        try:
            return render_template(template_name, **context)
        except Exception as exc:
            logger.error("外置模板渲染失败，自动降级 inline: %s (%s)", template_name, exc)
    return render_template_string(inline_template, **context)

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Postman 报告中心</title>
    <style>
        body { font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f3f6fb; color: #1f2937; }
        .page { max-width: 1240px; margin: 0 auto; padding: 24px; }
        .hero { background: linear-gradient(135deg, #0f172a, #1d4ed8); color: #fff; border-radius: 18px; padding: 24px 28px; box-shadow: 0 18px 48px rgba(15, 23, 42, 0.2); }
        .hero h1 { margin: 0 0 10px; font-size: 28px; }
        .hero p { margin: 6px 0; opacity: 0.92; }
        .panel { background: #fff; margin-top: 20px; border-radius: 16px; padding: 20px; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08); }
        .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }
        .toolbar input, .toolbar select, .toolbar button { padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 10px; font-size: 14px; }
        .toolbar button { background: #1d4ed8; color: #fff; border: none; cursor: pointer; }
        .toolbar button.secondary { background: #fff; color: #1d4ed8; border: 1px solid #93c5fd; }
        .toolbar button:hover { opacity: 0.92; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 12px 10px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
        th { color: #475569; font-size: 13px; }
        tr:hover { background: #f8fafc; }
        .summary { display: flex; gap: 10px; flex-wrap: wrap; }
        .tag { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; background: #e0f2fe; color: #075985; }
        .actions a { margin-right: 10px; color: #1d4ed8; text-decoration: none; }
        .report-link { color: #0f172a; font-weight: 700; text-decoration: none; }
        .report-link:hover { color: #1d4ed8; }
        .compare { margin-top: 18px; }
        .compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
        .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px; }
        .metric { font-size: 26px; font-weight: 700; margin-top: 8px; }
        .diff-list { margin-top: 18px; border-top: 1px solid #e5e7eb; padding-top: 18px; }
        .diff-item { padding: 12px 0; border-bottom: 1px solid #e5e7eb; }
        .diff-item:last-child { border-bottom: none; }
        .status-up { color: #15803d; }
        .status-down { color: #b91c1c; }
        .muted { color: #64748b; }
        .empty { padding: 32px 12px; text-align: center; color: #64748b; }
        .upload-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
        .field { display: flex; flex-direction: column; gap: 6px; }
        .field label { font-size: 12px; color: #334155; }
        .field input { padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 10px; font-size: 14px; }
        .run-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
        .run-status { margin-top: 14px; padding: 10px 12px; border-radius: 10px; background: #f8fafc; color: #334155; border: 1px solid #e2e8f0; }
        .run-status.success { background: #ecfdf5; color: #166534; border-color: #86efac; }
        .run-status.error { background: #fef2f2; color: #991b1b; border-color: #fca5a5; }
    </style>
</head>
<body>
    <div class="page">
        <section class="hero">
            <h1>Postman 报告中心 1.0.2</h1>
            <p>当前主机: {{ host_name }}</p>
            <p>本机访问: <a style="color:#bfdbfe;" href="{{ self_url }}">{{ self_url }}</a></p>
            <p>局域网访问: <a style="color:#bfdbfe;" href="{{ lan_url }}">{{ lan_url }}</a></p>
        </section>

        <section class="panel">
            <h3 style="margin-top:0;">上传并执行 Postman JSON</h3>
            <div class="upload-grid">
                <div class="field">
                    <label for="collectionFile">JSON 文件</label>
                    <input id="collectionFile" type="file" accept=".json,application/json">
                </div>
                <div class="field">
                    <label for="baseUrlInput">基础 URL（可选）</label>
                    <input id="baseUrlInput" type="text" placeholder="例如: https://api.example.com">
                </div>
                <div class="field">
                    <label for="tokenInput">Token（可选）</label>
                    <input id="tokenInput" type="text" placeholder="手动 token，填写后跳过自动登录">
                </div>
                <div class="field">
                    <label for="outputDirInput">报告输出目录（可选）</label>
                    <input id="outputDirInput" type="text" placeholder="默认使用服务端配置的 reports 目录">
                </div>
                <div class="field">
                    <label for="reportNameInput">报告名称（可选）</label>
                    <input id="reportNameInput" type="text" placeholder="例如: 本次回归测试报告.html（留空则自动命名）">
                </div>
                <div class="field">
                    <label for="resultsPerPageInput">报告分页大小（1-100）</label>
                    <input id="resultsPerPageInput" type="number" min="1" max="100" value="30">
                </div>
            </div>
            <div class="run-actions">
                <button id="runJobBtn" onclick="startRunPostmanJob()">上传并执行</button>
            </div>
            <div id="runStatus" class="run-status">上传 JSON 后可直接执行，执行完成后会提示刷新页面查看最新报告。</div>
        </section>

        <section class="panel">
            <div class="toolbar">
                <input id="searchInput" type="text" placeholder="搜索报告名、集合名、源文件" oninput="renderReports()">
                <button class="secondary" onclick="window.location.href='/'">刷新列表</button>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>选择</th>
                        <th>报告</th>
                        <th>集合 / 来源</th>
                        <th>摘要</th>
                        <th>生成时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="reportTable"></tbody>
            </table>
        </section>

        <section class="panel compare">
            <div class="toolbar">
                <select id="leftReport"></select>
                <select id="rightReport"></select>
                <button onclick="compareReports()">开始对比</button>
            </div>
            <div id="compareResult" class="empty">选择两份报告后即可查看差异。</div>
        </section>
    </div>

<script>
const reports = {{ reports_json|safe }};
let runJobTimer = null;

function escapeHtml(value) {
    return String(value || '').replace(/[&<>\"]/g, (s) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s]));
}

function reportOptionLabel(report) {
    return `${report.report_name} | ${report.summary.passed}/${report.summary.total}`;
}

function renderSelects(filtered = reports) {
    const left = document.getElementById('leftReport');
    const right = document.getElementById('rightReport');
    left.innerHTML = '';
    right.innerHTML = '';
    filtered.forEach((report) => {
        const optionLeft = document.createElement('option');
        optionLeft.value = report.report_name;
        optionLeft.textContent = reportOptionLabel(report);
        left.appendChild(optionLeft);

        const optionRight = document.createElement('option');
        optionRight.value = report.report_name;
        optionRight.textContent = reportOptionLabel(report);
        right.appendChild(optionRight);
    });
    if (filtered.length > 1) {
        left.selectedIndex = 1;
        right.selectedIndex = 0;
    }
}

function renderReports() {
    const query = document.getElementById('searchInput').value.trim().toLowerCase();
    const filtered = reports.filter((report) => {
        const text = [report.report_name, report.collection_name, report.source_file].join(' ').toLowerCase();
        return text.includes(query);
    });
    const tbody = document.getElementById('reportTable');
    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">没有匹配的报告。</td></tr>';
        renderSelects([]);
        return;
    }
    tbody.innerHTML = filtered.map((report) => `
        <tr>
            <td><input type="radio" name="reportPick" onclick="pickReport('${report.report_name}')"></td>
            <td>
                <a class="report-link" href="/report-view?name=${encodeURIComponent(report.report_name)}" target="_blank">${escapeHtml(report.report_name)}</a>
                <div class="muted">主机: ${escapeHtml(report.host_name || '-')}</div>
            </td>
            <td>${escapeHtml(report.collection_name || '-')}<div class="muted">${escapeHtml(report.source_file || '-')}</div></td>
            <td>
                <div class="summary">
                    <span class="tag">总计 ${report.summary.total}</span>
                    <span class="tag">通过 ${report.summary.passed}</span>
                    <span class="tag">失败 ${report.summary.failed}</span>
                    <span class="tag">错误 ${report.summary.error}</span>
                </div>
            </td>
            <td>${escapeHtml(report.generated_at || '-')}</td>
            <td class="actions">
                <a href="/report-view?name=${encodeURIComponent(report.report_name)}" target="_blank">查看数据</a>
                <a href="/reports/${encodeURIComponent(report.report_name)}" target="_blank">原始HTML</a>
                <a href="/api/report-meta/${encodeURIComponent(report.report_name)}" target="_blank">元数据</a>
            </td>
        </tr>
    `).join('');
    renderSelects(filtered);
}

function pickReport(reportName) {
    document.getElementById('rightReport').value = reportName;
}

async function compareReports() {
    const left = document.getElementById('leftReport').value;
    const right = document.getElementById('rightReport').value;
    if (!left || !right) {
        document.getElementById('compareResult').innerHTML = '<div class="empty">至少需要两份报告。</div>';
        return;
    }
    if (left === right) {
        document.getElementById('compareResult').innerHTML = '<div class="empty">请选择两份不同的报告进行对比。</div>';
        return;
    }
    const response = await fetch(`/api/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`);
    const data = await response.json();
    const metrics = `
        <div class="compare-grid">
            <div class="card"><div class="muted">基准报告</div><div class="metric">${escapeHtml(data.left.report_name)}</div></div>
            <div class="card"><div class="muted">当前报告</div><div class="metric">${escapeHtml(data.right.report_name)}</div></div>
            <div class="card"><div class="muted">成功率变化</div><div class="metric ${data.summary.success_rate_delta >= 0 ? 'status-up' : 'status-down'}">${data.summary.success_rate_delta_text}</div></div>
            <div class="card"><div class="muted">新增接口</div><div class="metric">${data.summary.added_count}</div></div>
            <div class="card"><div class="muted">移除接口</div><div class="metric">${data.summary.removed_count}</div></div>
            <div class="card"><div class="muted">状态变化</div><div class="metric">${data.summary.changed_count}</div></div>
        </div>
    `;
    const changed = data.changed.map((item) => `
        <div class="diff-item">
            <strong>${escapeHtml(item.name)}</strong>
            <div class="muted">${escapeHtml(item.method)} ${escapeHtml(item.url)}</div>
            <div>${escapeHtml(item.before_status)} -> ${escapeHtml(item.after_status)}，状态码 ${escapeHtml(String(item.before_status_code))} -> ${escapeHtml(String(item.after_status_code))}</div>
        </div>
    `).join('') || '<div class="empty">没有状态变化的接口。</div>';
    const added = data.added.map((item) => `
        <div class="diff-item"><strong>${escapeHtml(item.name)}</strong><div class="muted">${escapeHtml(item.method)} ${escapeHtml(item.url)}</div></div>
    `).join('') || '<div class="empty">没有新增接口。</div>';
    const removed = data.removed.map((item) => `
        <div class="diff-item"><strong>${escapeHtml(item.name)}</strong><div class="muted">${escapeHtml(item.method)} ${escapeHtml(item.url)}</div></div>
    `).join('') || '<div class="empty">没有移除接口。</div>';

    document.getElementById('compareResult').innerHTML = `
        ${metrics}
        <div class="diff-list"><h3>状态变化</h3>${changed}</div>
        <div class="diff-list"><h3>新增接口</h3>${added}</div>
        <div class="diff-list"><h3>移除接口</h3>${removed}</div>
    `;
}

function setRunStatus(text, level = '') {
    const statusEl = document.getElementById('runStatus');
    statusEl.textContent = text;
    statusEl.className = `run-status${level ? ' ' + level : ''}`;
}

async function startRunPostmanJob() {
    const fileInput = document.getElementById('collectionFile');
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
        setRunStatus('请先选择要上传的 Postman JSON 文件。', 'error');
        return;
    }

    const runButton = document.getElementById('runJobBtn');
    runButton.disabled = true;
    setRunStatus('正在上传并创建执行任务，请稍候...');

    const formData = new FormData();
    formData.append('collection_file', file);
    formData.append('base_url', document.getElementById('baseUrlInput').value.trim());
    formData.append('token', document.getElementById('tokenInput').value.trim());
    formData.append('output_dir', document.getElementById('outputDirInput').value.trim());
    formData.append('report_name', document.getElementById('reportNameInput').value.trim());
    formData.append('results_per_page', document.getElementById('resultsPerPageInput').value.trim());

    try {
        const response = await fetch('/api/run-postman', {
            method: 'POST',
            body: formData,
        });
        let data = {};
        const rawText = await response.text();
        try {
            data = rawText ? JSON.parse(rawText) : {};
        } catch (_e) {
            data = { error: rawText || '服务返回了非 JSON 响应。' };
        }
        if (!response.ok) {
            throw new Error(data.error || '任务创建失败');
        }
        setRunStatus(`任务已启动（${data.job_id}），正在执行...`);
        watchRunPostmanJob(data.job_id);
    } catch (error) {
        runButton.disabled = false;
        setRunStatus(`启动失败: ${error.message || error}`, 'error');
    }
}

function watchRunPostmanJob(jobId) {
    if (runJobTimer) {
        clearInterval(runJobTimer);
        runJobTimer = null;
    }

    const runButton = document.getElementById('runJobBtn');

    const fetchStatus = async () => {
        try {
            const response = await fetch(`/api/run-postman-status/${encodeURIComponent(jobId)}`);
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || '获取任务状态失败');
            }

            if (data.status === 'queued') {
                setRunStatus(`任务排队中（${jobId}），请稍候...`);
                return;
            }
            if (data.status === 'running') {
                const total = Number(data.total || 0);
                const completed = Number(data.completed || 0);
                const percent = Number(data.percent || 0);
                const progressText = total > 0 ? ` ${completed}/${total} (${percent}%)` : '';
                const currentText = data.current_name ? `，当前接口: ${data.current_name}` : '';
                setRunStatus(`任务执行中（${jobId}）${progressText}${currentText}`);
                return;
            }
            if (data.status === 'success') {
                clearInterval(runJobTimer);
                runJobTimer = null;
                runButton.disabled = false;
                const reportHint = data.report_name ? `最新报告: ${data.report_name}。` : '';
                setRunStatus(`执行完成。${reportHint}正在跳转到最新报告数据页...`, 'success');
                setTimeout(() => {
                    window.location.href = '/latest';
                }, 600);
                return;
            }

            clearInterval(runJobTimer);
            runJobTimer = null;
            runButton.disabled = false;
            setRunStatus(`执行失败: ${data.message || '未知错误'}`, 'error');
        } catch (error) {
            clearInterval(runJobTimer);
            runJobTimer = null;
            runButton.disabled = false;
            setRunStatus(`任务状态查询失败: ${error.message || error}`, 'error');
        }
    };

    fetchStatus();
    runJobTimer = setInterval(fetchStatus, 3000);
}

renderReports();
</script>
</body>
</html>
"""

REPORT_VIEW_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ report_name }} - 报告数据视图</title>
    <style>
        body { font-family: "Microsoft YaHei", sans-serif; margin: 0; background: #f3f6fb; color: #0f172a; }
        .page { max-width: 1320px; margin: 0 auto; padding: 24px; }
        .hero { background: linear-gradient(135deg, #0f172a, #2563eb); color: #fff; border-radius: 20px; padding: 24px 28px; box-shadow: 0 18px 44px rgba(15, 23, 42, 0.18); }
        .hero h1 { margin: 0 0 8px; font-size: 28px; word-break: break-all; }
        .hero p { margin: 4px 0; opacity: 0.92; }
        .hero a { color: #bfdbfe; }
        .summary-grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-top: 18px; }
        .summary-card { background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 14px; padding: 12px 14px; }
        .summary-card .label { font-size: 12px; opacity: 0.85; }
        .summary-card .value { font-size: 24px; font-weight: 700; margin-top: 6px; }
        .panel { background: #fff; margin-top: 20px; border-radius: 18px; padding: 20px; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08); }
        .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }
        .toolbar input, .toolbar select, .toolbar button { padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 14px; }
        .toolbar button { border: none; cursor: pointer; background: #2563eb; color: #fff; }
        .toolbar button.secondary { background: #fff; color: #2563eb; border: 1px solid #93c5fd; }
        .toolbar .hint { color: #64748b; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
        th { color: #475569; font-size: 13px; background: #f8fafc; }
        tr:hover { background: #f0f9ff; }
        .status { display: inline-block; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
        .status-passed { background: #dcfce7; color: #166534; }
        .status-failed { background: #fee2e2; color: #991b1b; }
        .status-error { background: #ffedd5; color: #9a3412; }
        .url { color: #1d4ed8; font-family: Consolas, monospace; }
        .msg-td { cursor: pointer; }
        .msg-td:hover { background: #fff8e1 !important; }
        .msg-td.expanded { white-space: normal !important; overflow: visible !important; max-width: none !important; word-break: break-word; background: #fff8e1 !important; }
        .msg-failed { color: #991b1b; }
        td.errcode-td { white-space: normal; overflow: visible; text-overflow: clip; max-width: none; word-break: break-all; }
        td.td-op { white-space: normal; overflow: visible; max-width: none; }
        .empty { padding: 30px 12px; text-align: center; color: #64748b; }
        .pagination { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; margin-top: 16px; }
        .pagination button { padding: 8px 12px; border-radius: 10px; border: 1px solid #cbd5e1; background: #fff; cursor: pointer; }
        .pagination button.active { background: #0f172a; color: #fff; border-color: #0f172a; }
        .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
        .pager-info { text-align: center; color: #64748b; margin-top: 4px; }
        .detail-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.48); display: none; align-items: center; justify-content: center; padding: 20px; }
        .detail-mask.show { display: flex; }
        .detail-dialog { width: min(1100px, 100%); max-height: 90vh; overflow: auto; background: #fff; border-radius: 18px; padding: 20px; box-shadow: 0 18px 44px rgba(15, 23, 42, 0.24); }
        .detail-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; margin-bottom: 16px; }
        .detail-head h3 { margin: 0 0 6px; }
        .detail-head button { border: none; background: #e2e8f0; padding: 8px 12px; border-radius: 10px; cursor: pointer; }
        .detail-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
        .detail-card { border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px; background: #f8fafc; }
        .detail-card h4 { margin: 0 0 10px; font-size: 14px; }
        pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: Consolas, monospace; font-size: 12px; color: #0f172a; }
        .muted { color: #64748b; }
        .loading { text-align: center; padding: 24px; color: #64748b; }
        /* 编辑重试 */
        .retry-btn { background: #f59e0b; color: #fff; border: none; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; margin-left: 8px; }
        .retry-btn:hover { background: #d97706; }
        .edit-retry-panel { background: #fffbeb; border: 1px solid #fde68a; border-radius: 14px; padding: 16px; margin-top: 16px; }
        .edit-retry-panel h4 { margin: 0 0 12px; font-size: 14px; color: #92400e; }
        .edit-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        .edit-row label { min-width: 72px; font-size: 13px; color: #475569; }
        .edit-row input[type=text], .edit-row select { flex: 1; min-width: 160px; padding: 8px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; }
        .edit-row textarea { flex: 1; min-width: 200px; height: 80px; padding: 8px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 12px; font-family: Consolas, monospace; resize: vertical; }
        .edit-row textarea.error { border-color: #ef4444; background: #fff1f2; }
        .edit-actions { display: flex; gap: 10px; margin-top: 4px; }
        .edit-actions button { padding: 8px 18px; border-radius: 8px; border: none; cursor: pointer; font-size: 13px; }
        .btn-send { background: #2563eb; color: #fff; }
        .btn-send:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-cancel { background: #e2e8f0; color: #374151; }
        .retry-result-box { margin-top: 12px; padding: 10px 14px; border-radius: 10px; font-size: 13px; }
        .retry-result-box.ok { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .retry-result-box.fail { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        /* retry_history */
        .history-toggle { font-size: 12px; color: #2563eb; cursor: pointer; border: none; background: none; padding: 4px 0; text-decoration: underline; }
        .history-list { margin-top: 8px; border-left: 3px solid #fde68a; padding-left: 12px; }
        .history-item { font-size: 12px; margin-bottom: 6px; color: #374151; }
        .retried-badge { display: inline-block; background: #fef9c3; color: #854d0e; border: 1px solid #fde68a; border-radius: 999px; font-size: 11px; padding: 2px 8px; margin-left: 6px; vertical-align: middle; }
    </style>
</head>
<body>
    <div class="page">
        <section class="hero">
            <h1>{{ report_name }}</h1>
            <p>集合: {{ collection_name or '-' }}</p>
            <p>来源文件: {{ source_file or '-' }}</p>
            <p>生成时间: {{ generated_at or '-' }}</p>
            <p>
                <a href="/">返回报告中心</a>
                |
                <a href="/reports/{{ report_name }}" target="_blank">打开原始 HTML</a>
                |
                <a href="/api/report-meta/{{ report_name }}" target="_blank">查看元数据</a>
            </p>
            <div class="summary-grid">
                <div class="summary-card"><div class="label">总计</div><div class="value" id="sum-total">{{ summary.total }}</div></div>
                <div class="summary-card"><div class="label">通过</div><div class="value" id="sum-passed">{{ summary.passed }}</div></div>
                <div class="summary-card"><div class="label">失败</div><div class="value" id="sum-failed">{{ summary.failed }}</div></div>
                <div class="summary-card"><div class="label">错误</div><div class="value" id="sum-error">{{ summary.error }}</div></div>
                <div class="summary-card"><div class="label">成功率</div><div class="value" id="sum-rate">{{ summary.success_rate }}</div></div>
                <div class="summary-card"><div class="label">耗时</div><div class="value">{{ summary.duration }}</div></div>
            </div>
        </section>

        <section class="panel">
            <div class="toolbar">
                <input id="queryInput" type="text" placeholder="按接口名称或路径搜索" />
                <input id="messageInput" type="text" placeholder="按 message 搜索" />
                <input id="errCodeInput" type="text" placeholder="按 errCode 搜索" />
                <select id="statusSelect">
                    <option value="all">全部结果</option>
                    <option value="PASSED">成功</option>
                    <option value="FAILED">失败</option>
                    <option value="ERROR">错误</option>
                </select>
                <select id="pageSizeSelect">
                    <option value="20" selected>20 条/页</option>
                    <option value="30">30 条/页</option>
                    <option value="50">50 条/页</option>
                    <option value="100">100 条/页</option>
                </select>
                <button onclick="reloadResults(1)">查询</button>
                <button class="secondary" onclick="resetFilters()">重置</button>
                <button class="secondary" onclick="exportLatestCollection()">导出最新 JSON</button>
                <label class="hint" style="display:flex;align-items:center;gap:6px;">
                    <input id="includeAuthExport" type="checkbox" style="width:14px;height:14px;">
                    导出包含 token/authorization
                </label>
                <span class="hint">默认 20 条/页，最高 100 条/页</span>
            </div>
            <div id="resultTableContainer" class="loading">加载报告数据中...</div>
            <div id="pagerInfo" class="pager-info"></div>
            <div id="pagination" class="pagination"></div>
        </section>
    </div>

    <div id="detailMask" class="detail-mask" onclick="closeDetail(event)">
        <div class="detail-dialog">
            <div class="detail-head">
                <div>
                    <h3 id="detailTitle">接口详情</h3>
                    <div id="detailMeta" class="muted"></div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;">
                    <button id="editRetryBtn" class="retry-btn" style="display:none;" onclick="openEditRetry()">编辑重试</button>
                    <button onclick="closeDetail()">关闭</button>
                </div>
            </div>
            <div id="detailBody" class="loading">加载详情中...</div>
            <div id="editRetryPanel" style="display:none;"></div>
        </div>
    </div>

<script>
const reportName = {{ report_name_json|safe }};

function escapeHtml(value) {
    return String(value || '').replace(/[&<>\"]/g, (s) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s]));
}

function formatJson(value) {
    if (value === null || value === undefined || value === '') {
        return '无';
    }
    if (typeof value === 'string') {
        return value;
    }
    return JSON.stringify(value, null, 2);
}

function currentFilters() {
    return {
        query: document.getElementById('queryInput').value.trim(),
        messageQuery: document.getElementById('messageInput').value.trim(),
        errCodeQuery: document.getElementById('errCodeInput').value.trim(),
        status: document.getElementById('statusSelect').value,
        pageSize: document.getElementById('pageSizeSelect').value
    };
}

async function reloadResults(page = 1) {
    const filters = currentFilters();
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(filters.pageSize),
        query: filters.query,
        message_query: filters.messageQuery,
        err_code_query: filters.errCodeQuery,
        status: filters.status
    });
    document.getElementById('resultTableContainer').innerHTML = '<div class="loading">加载报告数据中...</div>';
    const response = await fetch(`/api/report-results/${encodeURIComponent(reportName)}?${params.toString()}`);
    const data = await response.json();
    renderResults(data);
}

function renderResults(data) {
    if (!data.items || data.items.length === 0) {
        document.getElementById('resultTableContainer').innerHTML = '<div class="empty">没有匹配的数据。</div>';
        document.getElementById('pagerInfo').textContent = `第 ${data.page} 页 / 共 ${data.total_pages} 页，匹配 ${data.total} 条`;
        document.getElementById('pagination').innerHTML = '';
        return;
    }

    const rows = data.items.map((item) => `
        <tr>
            <td title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</td>
            <td title="${escapeHtml(item.folder || '-')}">${escapeHtml(item.folder || '-')}</td>
            <td>${escapeHtml(item.method)}</td>
            <td title="${escapeHtml(item.url)}"><span class="url">${escapeHtml(item.url)}</span></td>
            <td><span class="status status-${item.status.toLowerCase()}">${escapeHtml(item.status)}</span></td>
            <td>${item.status_code === null || item.status_code === undefined ? '-' : escapeHtml(String(item.status_code))}</td>
            <td class="msg-td ${item.status === 'FAILED' || item.status === 'ERROR' ? 'msg-failed' : ''}" title="点击展开/收起" onclick="toggleMsg(this)">${escapeHtml(item.message || '-')}</td>
            <td class="errcode-td">${escapeHtml(item.err_code || '-')}</td>
            <td class="td-op"><button onclick="openDetail(${item.index})" ${item.detail_available ? '' : 'disabled'}>${item.detail_available ? '详情' : '无详情'}</button></td>
        </tr>
    `).join('');

    document.getElementById('resultTableContainer').innerHTML = `
        <table>
            <colgroup>
                <col style="width:12%">
                <col style="width:9%">
                <col style="width:80px">
                <col style="width:20%">
                <col style="width:72px">
                <col style="width:60px">
                <col>
                <col style="width:140px">
                <col style="width:72px">
            </colgroup>
            <thead>
                <tr>
                    <th>接口名称</th>
                    <th>文件夹</th>
                    <th>方法</th>
                    <th>路径</th>
                    <th>状态</th>
                    <th>状态码</th>
                    <th>结果说明</th>
                    <th>errCode</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;

    document.getElementById('pagerInfo').textContent = `第 ${data.page} 页 / 共 ${data.total_pages} 页，匹配 ${data.total} 条，当前每页 ${data.page_size} 条`;
    renderPagination(data.page, data.total_pages);
}

function toggleMsg(td) {
    td.classList.toggle('expanded');
    td.title = td.classList.contains('expanded') ? '点击收起' : '点击展开/收起完整内容';
}

function renderPagination(page, totalPages) {
    const container = document.getElementById('pagination');
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    const buttons = [];
    buttons.push(`<button onclick="reloadResults(${page - 1})" ${page <= 1 ? 'disabled' : ''}>上一页</button>`);
    const start = Math.max(1, page - 4);
    const end = Math.min(totalPages, start + 8);
    for (let index = start; index <= end; index += 1) {
        buttons.push(`<button class="${index === page ? 'active' : ''}" onclick="reloadResults(${index})">${index}</button>`);
    }
    buttons.push(`<button onclick="reloadResults(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>下一页</button>`);
    container.innerHTML = buttons.join('');
}

async function openDetail(index) {
    const mask = document.getElementById('detailMask');
    const body = document.getElementById('detailBody');
    const editPanel = document.getElementById('editRetryPanel');
    const editBtn = document.getElementById('editRetryBtn');
    body.innerHTML = '<div class="loading">加载详情中...</div>';
    editPanel.style.display = 'none';
    editPanel.innerHTML = '';
    editBtn.style.display = 'none';
    mask.classList.add('show');
    // 记录当前详情 index 供 openEditRetry 使用
    mask.dataset.currentIndex = String(index);

    const response = await fetch(`/api/report-result-detail/${encodeURIComponent(reportName)}/${index}`);
    const data = await response.json();

    document.getElementById('detailTitle').textContent = (data.name || '接口详情') +
        (data.retried ? '<span class="retried-badge">已重试</span>' : '');
    document.getElementById('detailTitle').innerHTML = (data.name || '接口详情') +
        (data.retried ? ' <span class="retried-badge">已重试</span>' : '');
    document.getElementById('detailMeta').textContent =
        `${data.method || '-'} | ${data.url || '-'} | ${data.status || '-'} | 状态码 ${data.status_code ?? '-'}`;

    // 所有有 detail_available 或者只要有 url 的都可以重试
    if (data.url) {
        editBtn.style.display = '';
    }

    if (!data.detail_available) {
        body.innerHTML = '<div class="empty">该报告没有可用的请求/响应详情数据。</div>';
        // 即便无详情也允许编辑 URL/参数后重试
        mask.dataset.currentData = JSON.stringify(data);
        return;
    }

    // retry_history 区块
    let historyHtml = '';
    const history = data.retry_history || [];
    if (history.length > 0) {
        const items = history.map((h, i) => `
            <div class="history-item">
                第 ${i + 1} 次（原始/上次）：
                <span class="status status-${(h.status || '').toLowerCase()}">${escapeHtml(h.status || '-')}</span>
                状态码 ${h.status_code ?? '-'} &nbsp;|&nbsp; ${escapeHtml(h.message || '-')}
            </div>
        `).join('');
        historyHtml = `
            <div style="margin-top:12px;">
                <button class="history-toggle" onclick="toggleHistory(this)">▶ 查看重试历史（${history.length} 次）</button>
                <div class="history-list" style="display:none;">${items}</div>
            </div>`;
    }

    body.innerHTML = `
        <div class="detail-grid">
            <div class="detail-card">
                <h4>请求头</h4>
                <pre>${escapeHtml(formatJson(data.request_info.headers))}</pre>
            </div>
            <div class="detail-card">
                <h4>查询参数</h4>
                <pre>${escapeHtml(formatJson(data.request_info.params))}</pre>
            </div>
            <div class="detail-card">
                <h4>请求体</h4>
                <pre>${escapeHtml(formatJson(data.request_info.body))}</pre>
            </div>
            <div class="detail-card">
                <h4>响应头</h4>
                <pre>${escapeHtml(formatJson(data.response_info.headers))}</pre>
            </div>
            <div class="detail-card" style="grid-column: 1 / -1;">
                <h4>响应体</h4>
                <pre>${escapeHtml(formatJson(data.response_info.body))}</pre>
            </div>
        </div>
        ${historyHtml}
    `;

    // 缓存当前 data 供 openEditRetry 读取初始值
    mask.dataset.currentData = JSON.stringify(data);
}

function toggleHistory(btn) {
    const list = btn.nextElementSibling;
    const open = list.style.display !== 'none';
    list.style.display = open ? 'none' : 'block';
    btn.textContent = (open ? '▶' : '▼') + btn.textContent.slice(1);
}

function openEditRetry() {
    const mask = document.getElementById('detailMask');
    const panel = document.getElementById('editRetryPanel');
    const rawData = mask.dataset.currentData || '{}';
    const data = (() => { try { return JSON.parse(rawData); } catch(e) { return {}; } })();

    const reqInfo = data.request_info || {};
    const methodOptions = ['GET','POST','PUT','DELETE','PATCH'].map(m =>
        `<option value="${m}" ${m === (data.method || 'GET') ? 'selected' : ''}>${m}</option>`
    ).join('');

    panel.style.display = '';
    panel.innerHTML = `
        <div class="edit-retry-panel">
            <h4>编辑重试参数</h4>
            <div class="edit-row">
                <label>Method</label>
                <select id="er-method">${methodOptions}</select>
            </div>
            <div class="edit-row">
                <label>URL</label>
                <input type="text" id="er-url" value="${escapeHtml(data.url || '')}" style="font-family:Consolas;font-size:12px;" />
            </div>
            <div class="edit-row">
                <label>Token</label>
                <input type="text" id="er-token" placeholder="留空则使用原始 Headers 中的认证" />
            </div>
            <div class="edit-row">
                <label>Headers</label>
                <textarea id="er-headers">${escapeHtml(formatJson(reqInfo.headers || {}))}</textarea>
            </div>
            <div class="edit-row">
                <label>Params</label>
                <textarea id="er-params">${escapeHtml(formatJson(reqInfo.params || {}))}</textarea>
            </div>
            <div class="edit-row">
                <label>Body</label>
                <textarea id="er-body">${escapeHtml(formatJson(reqInfo.body !== undefined ? reqInfo.body : null))}</textarea>
            </div>
            <div class="edit-row">
                <label>期望状态码</label>
                <input type="text" id="er-expected-status" value="${escapeHtml(String(data.expected_status || 200))}" style="max-width:80px;" />
            </div>
            <div class="edit-row">
                <label></label>
                <label style="min-width:auto;"><input type="checkbox" id="er-save" checked> 回写到报告</label>
            </div>
            <div class="edit-actions">
                <button class="btn-send" id="er-send-btn" onclick="sendRetry()">发送</button>
                <button class="btn-cancel" onclick="cancelEditRetry()">取消</button>
            </div>
            <div id="er-result" style="display:none;"></div>
        </div>
    `;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function cancelEditRetry() {
    const panel = document.getElementById('editRetryPanel');
    panel.style.display = 'none';
    panel.innerHTML = '';
}

function parseJsonField(id) {
    const el = document.getElementById(id);
    const val = (el.value || '').trim();
    el.classList.remove('error');
    if (!val || val === '无') return [true, null];
    try {
        return [true, JSON.parse(val)];
    } catch(e) {
        el.classList.add('error');
        return [false, null];
    }
}

async function sendRetry() {
    const mask = document.getElementById('detailMask');
    const rawData = mask.dataset.currentData || '{}';
    const data = (() => { try { return JSON.parse(rawData); } catch(e) { return {}; } })();
    const resultIndex = parseInt(mask.dataset.currentIndex, 10);

    const url = (document.getElementById('er-url').value || '').trim();
    if (!url) { alert('URL 不能为空'); return; }

    const [hOk, headers] = parseJsonField('er-headers');
    const [pOk, params]  = parseJsonField('er-params');
    const [bOk, bodyVal] = parseJsonField('er-body');
    if (!hOk || !pOk || !bOk) { alert('Headers / Params / Body 中有 JSON 格式错误，请检查红色输入框。'); return; }

    const method = document.getElementById('er-method').value;
    const token = (document.getElementById('er-token').value || '').trim();
    const expectedStatus = parseInt(document.getElementById('er-expected-status').value, 10) || 200;
    const saveToReport = document.getElementById('er-save').checked;

    const btn = document.getElementById('er-send-btn');
    btn.disabled = true;
    btn.textContent = '请求中...';
    const resultDiv = document.getElementById('er-result');
    resultDiv.style.display = '';
    resultDiv.className = 'retry-result-box';
    resultDiv.textContent = '正在发送请求...';

    try {
        const resp = await fetch('/re-request-api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url, method,
                headers: headers || {},
                params: params || {},
                body: bodyVal,
                token,
                expected_status: expectedStatus,
                save_to_report: saveToReport,
                report_name: reportName,
                result_index: resultIndex,
                name: data.name || url,
                folder: data.folder || '',
                item_path: data.item_path || [],
            })
        });
        const result = await resp.json();

        const isPass = result.status === 'PASSED';
        resultDiv.className = 'retry-result-box ' + (isPass ? 'ok' : 'fail');
        resultDiv.innerHTML = `
            <strong>${escapeHtml(result.status)}</strong>
            &nbsp;|&nbsp; 状态码: ${result.status_code ?? '-'}
            &nbsp;|&nbsp; ${escapeHtml(result.message || '-')}
            ${result.saved ? '<br><small>✓ 已回写到报告</small>' : ''}
        `;

        // 刷新 summary 卡片
        if (result.new_summary && result.new_summary.total !== undefined) {
            const s = result.new_summary;
            document.getElementById('sum-total').textContent  = s.total  ?? '';
            document.getElementById('sum-passed').textContent = s.passed ?? '';
            document.getElementById('sum-failed').textContent = s.failed ?? '';
            document.getElementById('sum-error').textContent  = s.error  ?? '';
            document.getElementById('sum-rate').textContent   = s.success_rate ?? '';
        }

        // 更新列表行（状态、状态码、结果说明）
        if (saveToReport) {
            reloadResults();
        }

        // 更新弹窗 detailMeta 和标题徽标
        document.getElementById('detailTitle').innerHTML =
            escapeHtml(data.name || '接口详情') + ' <span class="retried-badge">已重试</span>';
        document.getElementById('detailMeta').textContent =
            `${method} | ${url} | ${result.status} | 状态码 ${result.status_code ?? '-'}`;

        // 更新 currentData 以便二次重试时能看到最新状态
        const updated = { ...data, ...result, retry_history: (data.retry_history || []) };
        mask.dataset.currentData = JSON.stringify(updated);

    } catch(e) {
        resultDiv.className = 'retry-result-box fail';
        resultDiv.textContent = '请求失败: ' + String(e);
    } finally {
        btn.disabled = false;
        btn.textContent = '发送';
    }
}

function closeDetail(event) {
    if (event && event.target && event.target.id !== 'detailMask') {
        return;
    }
    document.getElementById('detailMask').classList.remove('show');
    const panel = document.getElementById('editRetryPanel');
    if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
    const editBtn = document.getElementById('editRetryBtn');
    if (editBtn) { editBtn.style.display = 'none'; }
}

function resetFilters() {
    document.getElementById('queryInput').value = '';
    document.getElementById('messageInput').value = '';
    document.getElementById('errCodeInput').value = '';
    document.getElementById('statusSelect').value = 'all';
    document.getElementById('pageSizeSelect').value = '20';
    reloadResults(1);
}

async function exportLatestCollection() {
    try {
        const includeAuth = document.getElementById('includeAuthExport').checked;
        const response = await fetch('/api/export-collection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ report_name: reportName, include_auth: includeAuth })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || '导出失败');
        }

        const warningText = (data.warnings && data.warnings.length)
            ? `\n\n未精确定位 ${data.skipped_count} 条，详情请查看控制台。`
            : '';
        alert(
            `导出完成！\n文件: ${data.file_name}\n包含认证头: ${data.include_auth ? '是' : '否'}\n更新接口: ${data.updated_count}\n跳过接口: ${data.skipped_count}${warningText}`
        );
        if (data.warnings && data.warnings.length) {
            console.warn('Export warnings:', data.warnings);
        }
        if (data.download_url) {
            window.open(data.download_url, '_blank');
        }
    } catch (error) {
        alert('导出失败: ' + (error.message || error));
    }
}

document.getElementById('queryInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        reloadResults(1);
    }
});

document.getElementById('messageInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        reloadResults(1);
    }
});

document.getElementById('errCodeInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        reloadResults(1);
    }
});

document.getElementById('statusSelect').addEventListener('change', () => reloadResults(1));
document.getElementById('pageSizeSelect').addEventListener('change', () => reloadResults(1));

reloadResults(1);
</script>
</body>
</html>
"""


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_total_report_file(path: Path) -> bool:
    name = path.name.lower()
    return "_page_" not in name


def is_total_report_name(report_name: str) -> bool:
    return "_page_" not in str(report_name or "").lower()


def report_meta_files() -> List[Path]:
    if not REPORTS_DIR.exists():
        return []
    return [path for path in sorted(REPORTS_DIR.glob("*_meta.json"), reverse=True) if is_total_report_file(path)]


def legacy_postman_html_files() -> List[Path]:
    if not REPORTS_DIR.exists():
        return []
    return [path for path in sorted(REPORTS_DIR.glob("*.html"), reverse=True) if is_total_report_file(path)]


def load_report_meta(meta_path: Path) -> Dict[str, Any]:
    with meta_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if "summary" not in data:
        data["summary"] = {}
    return data


def load_legacy_postman_report(report_path: Path) -> Dict[str, Any]:
    content = report_path.read_text(encoding="utf-8")
    results_match = re.search(r"let\s+allResults\s*=\s*(\[.*?\]);", content, re.S)
    total_match = re.search(r"<label>总计</label>\s*<span>(\d+)</span>", content)
    passed_match = re.search(r"<label>✓ 通过</label>\s*<span>(\d+)</span>", content)
    failed_match = re.search(r"<label>✗ 失败</label>\s*<span>(\d+)</span>", content)
    error_match = re.search(r"<label>! 错误</label>\s*<span>(\d+)</span>", content)
    rate_match = re.search(r"<label>成功率</label>\s*<span>([^<]+)</span>", content)
    duration_match = re.search(r"<label>耗时</label>\s*<span>([^<]+)</span>", content)
    time_match = re.search(r"开始:\s*([^|<]+)\s*\|\s*结束:\s*([^<]+)", content)

    raw_results = json.loads(results_match.group(1)) if results_match else []
    results = [
        {
            "key": " | ".join([
                item.get("folder", "") or "-",
                item.get("name", "") or "-",
                item.get("method", "") or "-",
                item.get("url", "") or "-",
            ]),
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "method": item.get("method", ""),
            "url": item.get("url", ""),
            "status": item.get("status", ""),
            "status_code": item.get("status_code"),
            "message": item.get("message", ""),
            "err_code": item.get("err_code", ""),
        }
        for item in raw_results
    ]

    generated_at = time_match.group(2).strip() if time_match else ""
    return {
        "report_name": report_path.name,
        "generated_at": generated_at,
        "host_name": "legacy-html",
        "collection_name": "",
        "source_file": str(report_path),
        "summary": {
            "total": int(total_match.group(1)) if total_match else len(results),
            "passed": int(passed_match.group(1)) if passed_match else len([item for item in results if item.get("status") == "PASSED"]),
            "failed": int(failed_match.group(1)) if failed_match else len([item for item in results if item.get("status") == "FAILED"]),
            "error": int(error_match.group(1)) if error_match else len([item for item in results if item.get("status") == "ERROR"]),
            "success_rate": rate_match.group(1).strip() if rate_match else "0.00%",
            "duration": duration_match.group(1).strip() if duration_match else "",
            "start_time": time_match.group(1).strip() if time_match else "",
            "end_time": time_match.group(2).strip() if time_match else "",
        },
        "details_file": f"{report_path.stem}_details.json",
        "results": results,
        "meta_file": "",
        "legacy": True,
    }


import time as _time

# 报告列表简单 TTL 缓存（30 秒），避免每次首页请求都全量读取 meta 文件
_REPORTS_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_REPORTS_CACHE_TTL = 30  # 秒


def _invalidate_reports_cache() -> None:
    """新报告生成或回写时主动失效缓存。"""
    _REPORTS_CACHE["ts"] = 0.0


def list_reports() -> List[Dict[str, Any]]:
    _now = _time.monotonic()
    if _REPORTS_CACHE["data"] is not None and (_now - _REPORTS_CACHE["ts"]) < _REPORTS_CACHE_TTL:
        return list(_REPORTS_CACHE["data"])

    reports: List[Dict[str, Any]] = []
    seen_report_names = set()

    for meta_path in report_meta_files():
        try:
            report = load_report_meta(meta_path)
            report["meta_file"] = meta_path.name
            reports.append(report)
            seen_report_names.add(report.get("report_name"))
        except Exception as exc:
            reports.append({
                "report_name": meta_path.name,
                "generated_at": "",
                "host_name": "",
                "collection_name": "",
                "source_file": "",
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "success_rate": "0%"},
                "load_error": str(exc),
                "results": [],
            })

    for html_path in legacy_postman_html_files():
        if html_path.name in seen_report_names:
            continue
        try:
            reports.append(load_legacy_postman_report(html_path))
        except Exception:
            continue

    # Final guard: regardless of data source, do not expose paged child reports.
    reports = [item for item in reports if is_total_report_name(item.get("report_name", ""))]

    reports.sort(key=lambda item: item.get("generated_at", ""), reverse=True)

    _REPORTS_CACHE["data"] = reports
    _REPORTS_CACHE["ts"] = _time.monotonic()
    return list(reports)


def find_report(report_name: str) -> Dict[str, Any]:
    for report in list_reports():
        if report.get("report_name") == report_name:
            return report
    raise FileNotFoundError(report_name)


def map_results(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["key"]: item for item in report.get("results", [])}


def compare_report_data(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_map = map_results(left)
    right_map = map_results(right)
    left_keys = set(left_map.keys())
    right_keys = set(right_map.keys())

    added_keys = sorted(right_keys - left_keys)
    removed_keys = sorted(left_keys - right_keys)
    common_keys = sorted(left_keys & right_keys)
    changed: List[Dict[str, Any]] = []

    for key in common_keys:
        before = left_map[key]
        after = right_map[key]
        if before.get("status") != after.get("status") or before.get("status_code") != after.get("status_code"):
            changed.append({
                "key": key,
                "name": after.get("name") or before.get("name"),
                "folder": after.get("folder") or before.get("folder"),
                "method": after.get("method") or before.get("method"),
                "url": after.get("url") or before.get("url"),
                "before_status": before.get("status"),
                "after_status": after.get("status"),
                "before_status_code": before.get("status_code"),
                "after_status_code": after.get("status_code"),
            })

    left_rate = _to_rate(left.get("summary", {}).get("success_rate", "0%"))
    right_rate = _to_rate(right.get("summary", {}).get("success_rate", "0%"))
    delta = right_rate - left_rate

    return {
        "left": left,
        "right": right,
        "summary": {
            "added_count": len(added_keys),
            "removed_count": len(removed_keys),
            "changed_count": len(changed),
            "success_rate_delta": round(delta, 2),
            "success_rate_delta_text": f"{delta:+.2f}%",
        },
        "added": [right_map[key] for key in added_keys],
        "removed": [left_map[key] for key in removed_keys],
        "changed": changed,
    }


def _to_rate(value: str) -> float:
    try:
        return float(str(value).replace("%", ""))
    except ValueError:
        return 0.0


def normalize_status_filter(value: str) -> Optional[str]:
    normalized = str(value or "").strip().upper()
    if normalized in {"", "ALL", "RESULT", "全部", "结果"}:
        return None
    if normalized in {"PASSED", "SUCCESS", "成功"}:
        return "PASSED"
    if normalized in {"FAILED", "FAIL", "失败"}:
        return "FAILED"
    if normalized in {"ERROR", "错误"}:
        return "ERROR"
    return None


def clamp_page_size(value: Any) -> int:
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        page_size = 20
    return max(1, min(page_size, 100))


def clamp_page(value: Any) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        page = 1
    return max(1, page)


def clamp_run_results_per_page(value: Any) -> int:
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        page_size = 30
    return max(1, min(page_size, 100))


try:
    from postman_api_tester import config as _cfg
    _RUN_JOBS_MAX = int(getattr(_cfg, "RUN_JOBS_MAX", 200))
except Exception:
    _RUN_JOBS_MAX = 200  # 最多保留的任务条数


def _evict_old_jobs() -> None:
    """已在 RUN_JOBS_LOCK 持有下调用：超出上限时清理最早完成的任务。"""
    if len(RUN_JOBS) <= _RUN_JOBS_MAX:
        return
    terminal_statuses = {"success", "failed"}
    finished = [
        jid for jid, job in RUN_JOBS.items()
        if job.get("status") in terminal_statuses
    ]
    # 按写入顺序保留最新一半已完成任务
    to_evict = finished[: max(0, len(finished) - _RUN_JOBS_MAX // 2)]
    for jid in to_evict:
        del RUN_JOBS[jid]


def set_run_job(job_id: str, **updates: Any) -> None:
    with RUN_JOBS_LOCK:
        RUN_JOBS[job_id] = {**RUN_JOBS.get(job_id, {}), **updates}
        _evict_old_jobs()


def get_run_job(job_id: str) -> Optional[Dict[str, Any]]:
    with RUN_JOBS_LOCK:
        job = RUN_JOBS.get(job_id)
        return dict(job) if job else None


def run_postman_job(
    job_id: str,
    postman_file: str,
    base_url: Optional[str],
    output_dir: str,
    token: Optional[str],
    report_name: Optional[str],
    source_original_file: Optional[str],
    results_per_page: int,
) -> None:
    set_run_job(job_id, status="running", message="正在执行接口测试...")
    try:
        from postman_api_tester.postman_api_tester import run_postman_tests

        def on_progress(progress: Dict[str, Any]) -> None:
            total = int(progress.get("total") or 0)
            completed = int(progress.get("completed") or 0)
            percent = int(progress.get("percent") or 0)
            current_name = str(progress.get("current_name") or "")
            current_method = str(progress.get("current_method") or "")
            current_url = str(progress.get("current_url") or "")

            message = "正在执行接口测试..."
            if total > 0:
                message = f"正在执行接口测试: {completed}/{total} ({percent}%)"
                if current_name:
                    message = f"{message}，当前接口: {current_name}"

            set_run_job(
                job_id,
                status="running",
                message=message,
                total=total,
                completed=completed,
                percent=percent,
                current_name=current_name,
                current_method=current_method,
                current_url=current_url,
                last_status=str(progress.get("last_status") or ""),
            )

        report = run_postman_tests(
            postman_file=postman_file,
            base_url=base_url,
            output_dir=output_dir,
            token=token,
            report_name=report_name,
            source_original_file=source_original_file,
            results_per_page=results_per_page,
            progress_callback=on_progress,
        )
        set_run_job(
            job_id,
            status="success",
            message="执行完成，请刷新页面查看最新报告。",
            report_name=os.path.basename(str(report.generated_report_file or "")),
            report_meta_name=os.path.basename(str(report.generated_meta_file or "")),
        )
        # 新报告已生成，主动失效首页报告列表缓存
        _invalidate_reports_cache()
    except Exception as exc:
        set_run_job(job_id, status="failed", message=str(exc))


def load_report_details_map(report: Dict[str, Any]) -> Dict[str, Any]:
    details_file = str(report.get("details_file") or "").strip()
    if not details_file:
        return {}
    details_path = REPORTS_DIR / details_file
    if not details_path.exists():
        return {}
    try:
        with details_path.open("r", encoding="utf-8") as file:
            details = json.load(file)
        return details if isinstance(details, dict) else {}
    except Exception:
        return {}


def _sanitize_export_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").split("/")[-1]
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized).strip(' .')
    return normalized or "collection"


def _apply_token_to_headers(headers: Dict[str, Any], token: str) -> Dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        return dict(headers or {})

    fixed_headers = dict(headers or {})
    auth_key = None
    for key in list(fixed_headers.keys()):
        lower_key = str(key).lower()
        if lower_key == "authorization":
            auth_key = key
        if lower_key == "token":
            fixed_headers.pop(key)
    if auth_key:
        fixed_headers[auth_key] = f"Bearer {token}"
    else:
        fixed_headers["token"] = token
    return fixed_headers


def _strip_auth_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in (headers or {}).items():
        lower_key = str(key).lower()
        if lower_key in {"authorization", "token", "access_token", "auth_token"}:
            continue
        cleaned[key] = value
    return cleaned


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _merge_url_with_params(raw_url: str, params: Dict[str, Any]) -> str:
    raw_url = str(raw_url or "").strip()
    if not params:
        return raw_url

    split = urlsplit(raw_url)
    existing_pairs = parse_qsl(split.query, keep_blank_values=True)
    merged = {key: value for key, value in existing_pairs}
    for key, value in (params or {}).items():
        merged[str(key)] = "" if value is None else str(value)

    new_query = urlencode(merged, doseq=False)
    return urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))


def _set_request_url(request_obj: Dict[str, Any], raw_url: str, params: Dict[str, Any]) -> None:
    merged_url = _merge_url_with_params(raw_url, params)
    url_obj = request_obj.get("url")
    if isinstance(url_obj, dict):
        request_obj["url"]["raw"] = merged_url
        request_obj["url"]["query"] = [
            {"key": str(key), "value": "" if value is None else str(value)}
            for key, value in (params or {}).items()
        ]
    else:
        request_obj["url"] = merged_url


def _set_request_headers(request_obj: Dict[str, Any], headers: Dict[str, Any]) -> None:
    request_obj["header"] = [
        {"key": str(key), "value": "" if value is None else str(value)}
        for key, value in (headers or {}).items()
    ]


def _set_request_body(request_obj: Dict[str, Any], body: Any) -> None:
    if body is None:
        request_obj.pop("body", None)
        return

    if isinstance(body, (dict, list)):
        request_obj["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, ensure_ascii=False),
            "options": {"raw": {"language": "json"}},
        }
        return

    request_obj["body"] = {
        "mode": "raw",
        "raw": str(body),
    }


def _item_by_path(collection_data: Dict[str, Any], item_path: List[int]) -> Optional[Dict[str, Any]]:
    if not isinstance(item_path, list) or not item_path:
        return None

    items = collection_data.get("item")
    if not isinstance(items, list):
        return None

    current: Optional[Dict[str, Any]] = None
    for depth, index in enumerate(item_path):
        if not isinstance(index, int) or index < 0 or index >= len(items):
            return None
        current = items[index]
        if depth < len(item_path) - 1:
            child_items = current.get("item") if isinstance(current, dict) else None
            if not isinstance(child_items, list):
                return None
            items = child_items
    if not isinstance(current, dict):
        return None
    if "request" not in current:
        return None
    return current


def _iter_request_items(items: List[Dict[str, Any]], folder: str = "") -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "request" in item:
            request = item.get("request") or {}
            flattened.append({
                "item": item,
                "name": str(item.get("name", "")),
                "folder": folder,
                "method": str(request.get("method", "")).upper(),
            })
            continue
        children = item.get("item")
        if isinstance(children, list):
            next_folder = str(item.get("name", ""))
            flattened.extend(_iter_request_items(children, next_folder))
    return flattened


def _find_item_fallback(collection_data: Dict[str, Any], result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = collection_data.get("item")
    if not isinstance(items, list):
        return None

    candidates = _iter_request_items(items)
    name = str(result.get("name", ""))
    method = str(result.get("method", "")).upper()
    folder = str(result.get("folder", ""))

    exact = [
        row for row in candidates
        if row["name"] == name and row["method"] == method and row["folder"] == folder
    ]
    if len(exact) == 1:
        return exact[0]["item"]

    loose = [row for row in candidates if row["name"] == name and row["method"] == method]
    if len(loose) == 1:
        return loose[0]["item"]
    return None


def export_collection_with_latest_params(report: Dict[str, Any], include_auth: bool = False) -> Dict[str, Any]:
    source_file = str(report.get("source_file") or "").strip()
    if not source_file:
        raise ValueError("报告中缺少 source_file，无法导出。")

    source_path = Path(source_file)
    if not source_path.exists():
        raise FileNotFoundError(f"找不到原始上传文件: {source_file}")

    with source_path.open("r", encoding="utf-8") as f:
        collection_data = json.load(f)

    details_map = load_report_details_map(report)
    updated_count = 0
    skipped_count = 0
    warnings: List[str] = []

    for index, result in enumerate(report.get("results", [])):
        detail = details_map.get(str(index)) or {}
        request_info = detail.get("request_info") or {}

        item = _item_by_path(collection_data, result.get("item_path") or [])
        if item is None:
            item = _find_item_fallback(collection_data, result)
            if item is None:
                skipped_count += 1
                warnings.append(f"索引 {index} 无法定位到原始请求: {result.get('name', '-')}")
                continue

        request_obj = item.setdefault("request", {})
        if not isinstance(request_obj, dict):
            skipped_count += 1
            warnings.append(f"索引 {index} 的 request 结构异常: {result.get('name', '-')}")
            continue

        method = str(result.get("method") or request_obj.get("method") or "GET").upper()
        url = str(result.get("url") or request_obj.get("url") or "").strip()
        headers = dict(request_info.get("headers") or {})
        if not include_auth:
            headers = _strip_auth_headers(headers)
        params = dict(request_info.get("params") or {})
        body = request_info.get("body")

        request_obj["method"] = method
        _set_request_url(request_obj, url, params)
        _set_request_headers(request_obj, headers)
        _set_request_body(request_obj, body)
        updated_count += 1

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    preferred_name = report.get("source_original_file") or source_path.name
    source_name = _sanitize_export_name(preferred_name)
    stem = Path(source_name).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_name = f"{stem}_latest_{timestamp}.json"
    export_path = EXPORTS_DIR / export_name

    with export_path.open("w", encoding="utf-8") as f:
        json.dump(collection_data, f, indent=2, ensure_ascii=False)

    return {
        "file_name": export_name,
        "file_path": str(export_path),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "warnings": warnings,
    }


def filter_report_results(
    report: Dict[str, Any],
    keyword: str,
    status_filter: Optional[str],
    message_keyword: str,
    err_code_keyword: str,
) -> List[Dict[str, Any]]:
    lowered_keyword = str(keyword or "").strip().lower()
    lowered_message_keyword = str(message_keyword or "").strip().lower()
    lowered_err_code_keyword = str(err_code_keyword or "").strip().lower()
    details_map = load_report_details_map(report)
    filtered_items: List[Dict[str, Any]] = []

    for index, item in enumerate(report.get("results", [])):
        if status_filter and item.get("status") != status_filter:
            continue
        if lowered_keyword:
            search_text = " ".join([
                str(item.get("name", "")),
                str(item.get("url", "")),
                str(item.get("folder", "")),
                str(item.get("key", "")),
            ]).lower()
            if lowered_keyword not in search_text:
                continue
        if lowered_message_keyword:
            message_text = str(item.get("message", "")).lower()
            if lowered_message_keyword not in message_text:
                continue
        if lowered_err_code_keyword:
            err_code_text = str(item.get("err_code", "")).lower()
            if lowered_err_code_keyword not in err_code_text:
                continue
        filtered_items.append({
            "index": index,
            "name": item.get("name", ""),
            "folder": item.get("folder", ""),
            "method": item.get("method", ""),
            "url": item.get("url", ""),
            "status": item.get("status", ""),
            "status_code": item.get("status_code"),
            "message": item.get("message", ""),
            "err_code": item.get("err_code", ""),
            "detail_available": str(index) in details_map,
        })
    return filtered_items


def paginate_items(items: List[Dict[str, Any]], page: int, page_size: int) -> Dict[str, Any]:
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _extract_msg_errcode(body: Any) -> tuple:
    """从响应 JSON body 中提取 message 和 errCode（兼容嵌套 data 层）。"""
    if not isinstance(body, dict):
        return "", ""

    def pick(obj: dict, keys: List[str]) -> str:
        for key in keys:
            val = obj.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    msg_keys = ["message", "msg", "error_message", "errorMessage", "errMsg"]
    err_keys = ["errCode", "errcode", "errorCode", "error_code", "code"]

    message = pick(body, msg_keys)
    err_code = pick(body, err_keys)

    nested = body.get("data")
    if isinstance(nested, dict):
        if not message:
            message = pick(nested, msg_keys)
        if not err_code:
            err_code = pick(nested, err_keys)

    return message, err_code


def _compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """根据结果列表重新计算 summary（不含 duration/start_time/end_time）。"""
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASSED")
    failed = sum(1 for r in results if r.get("status") == "FAILED")
    error = sum(1 for r in results if r.get("status") == "ERROR")
    rate = f"{(passed / total * 100):.2f}%" if total > 0 else "0.00%"
    return {"total": total, "passed": passed, "failed": failed, "error": error, "success_rate": rate}


def patch_report_result(
    report_name: str,
    result_index: int,
    new_result_fields: Dict[str, Any],
    new_request_info: Dict[str, Any],
    new_response_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    原子写回 _meta.json 和 _details.json：
    - 将 result_index 处的旧结果追加到 retry_history 后再覆盖
    - 重新计算 summary（保留 duration/time 字段不变）
    - 返回更新后的 summary
    """
    lock = get_report_write_lock(report_name)
    with lock:
        try:
            report = find_report(report_name)
        except FileNotFoundError:
            return {}

        meta_file_name = str(report.get("meta_file") or "").strip()
        if not meta_file_name:
            return {}

        meta_path = REPORTS_DIR / meta_file_name
        if not meta_path.exists():
            return {}

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        results: List[Dict[str, Any]] = meta.get("results", [])
        if result_index < 0 or result_index >= len(results):
            return {}

        # 保留旧结果到 retry_history
        old_result = dict(results[result_index])
        old_history: List[Dict[str, Any]] = old_result.pop("retry_history", [])
        retry_history = old_history + [old_result]

        # 构造写入 meta 的新结果（不含 request_info/response_info 避免 meta 膨胀）
        merged = {
            "name": old_result.get("name", ""),
            "folder": old_result.get("folder", ""),
            "method": new_result_fields.get("method", old_result.get("method", "")),
            "url": new_result_fields.get("url", old_result.get("url", "")),
            "item_path": new_result_fields.get("item_path", old_result.get("item_path", [])),
            "expected_status": new_result_fields.get("expected_status", old_result.get("expected_status", 200)),
            **new_result_fields,
            "retry_history": retry_history,
            "retried": True,
        }
        merged["key"] = " | ".join([
            merged.get("folder", "") or "-",
            merged.get("name", "") or "-",
            merged.get("method", "") or "-",
            merged.get("url", "") or "-",
        ])
        results[result_index] = merged
        meta["results"] = results

        # 重算 summary，保留不可重算的时间字段
        new_stats = _compute_summary(results)
        old_summary = meta.get("summary", {})
        meta["summary"] = {
            **old_summary,
            "total": new_stats["total"],
            "passed": new_stats["passed"],
            "failed": new_stats["failed"],
            "error": new_stats["error"],
            "success_rate": new_stats["success_rate"],
        }

        # 原子写 meta
        tmp_meta = meta_path.with_suffix(".tmp")
        with tmp_meta.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(str(tmp_meta), str(meta_path))

        # 原子写 details
        details_file_name = str(report.get("details_file") or "").strip()
        if details_file_name:
            details_path = REPORTS_DIR / details_file_name
            details: Dict[str, Any] = {}
            if details_path.exists():
                try:
                    with details_path.open("r", encoding="utf-8") as f:
                        details = json.load(f)
                except Exception:
                    pass
            details[str(result_index)] = {
                "request_info": new_request_info,
                "response_info": new_response_info,
            }
            tmp_details = details_path.with_suffix(".tmp")
            with tmp_details.open("w", encoding="utf-8") as f:
                json.dump(details, f, indent=2, ensure_ascii=False)
            os.replace(str(tmp_details), str(details_path))

        return meta["summary"]


def build_result_detail(report: Dict[str, Any], result_index: int) -> Dict[str, Any]:
    results = report.get("results", [])
    if result_index < 0 or result_index >= len(results):
        raise IndexError(result_index)

    result = dict(results[result_index])
    details_map = load_report_details_map(report)
    detail = details_map.get(str(result_index))
    response = {
        "index": result_index,
        "name": result.get("name", ""),
        "folder": result.get("folder", ""),
        "method": result.get("method", ""),
        "url": result.get("url", ""),
        "item_path": result.get("item_path", []),
        "expected_status": result.get("expected_status", 200),
        "status": result.get("status", ""),
        "status_code": result.get("status_code"),
        "message": result.get("message", ""),
        "err_code": result.get("err_code", ""),
        "retried": result.get("retried", False),
        "retry_history": result.get("retry_history", []),
        "detail_available": bool(detail),
        "request_info": {"headers": {}, "params": {}, "body": None},
        "response_info": {"headers": {}, "body": None},
    }
    if detail:
        response["request_info"] = detail.get("request_info") or {"headers": {}, "params": {}, "body": None}
        response["response_info"] = detail.get("response_info") or {"headers": {}, "body": None}
    return response


@app.route("/health")
def health():
    """健康检查端点，供负载均衡或监控系统探测服务存活状态。"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route("/")
def index():
    reports = list_reports()
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
    return render_with_fallback(
        "index.html",
        INDEX_TEMPLATE,
        host_name=socket.gethostname(),
        self_url=f"http://127.0.0.1:{port}",
        lan_url=f"http://{get_local_ip()}:{port}",
        reports_json=json.dumps(reports, ensure_ascii=False),
    )


@app.route("/report-view")
def report_view():
    report_name = request.args.get("name", "")
    if not report_name:
        reports = list_reports()
        if reports:
            return redirect(url_for("report_view", name=reports[0]["report_name"]))
        return redirect(url_for("index"))

    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return render_with_fallback(
            "report_not_found.html",
            "<h3>报告不存在</h3><p>{{ name }}</p>",
            name=report_name,
        ), 404

    return render_with_fallback(
        "report_view.html",
        REPORT_VIEW_TEMPLATE,
        report_name=report.get("report_name", ""),
        report_name_json=json.dumps(report.get("report_name", ""), ensure_ascii=False),
        collection_name=report.get("collection_name", ""),
        source_file=report.get("source_file", ""),
        generated_at=report.get("generated_at", ""),
        summary=report.get("summary", {}),
    )


@app.route("/reports/<path:filename>")
def serve_report(filename: str):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/exports/<path:filename>")
def serve_export(filename: str):
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)


@app.route("/api/reports")
def api_reports():
    return jsonify(list_reports())


@app.route("/api/export-collection", methods=["POST"])
def api_export_collection():
    payload = request.get_json(silent=True) or {}
    report_name = str(payload.get("report_name", "")).strip()
    include_auth = _to_bool(payload.get("include_auth"), default=False)
    if not report_name:
        return jsonify({"error": "report_name 不能为空"}), 400

    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    try:
        exported = export_collection_with_latest_params(report, include_auth=include_auth)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "report_name": report_name,
        "file_name": exported["file_name"],
        "download_url": f"/exports/{exported['file_name']}",
        "updated_count": exported["updated_count"],
        "skipped_count": exported["skipped_count"],
        "include_auth": include_auth,
        "warnings": exported["warnings"],
    })


@app.route("/api/report-meta/<path:report_name>")
def api_report_detail(report_name: str):
    try:
        return jsonify(find_report(report_name))
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404


@app.route("/api/report-results/<path:report_name>")
def api_report_results(report_name: str):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    page = clamp_page(request.args.get("page", 1))
    page_size = clamp_page_size(request.args.get("page_size", 20))
    keyword = request.args.get("query", "")
    message_keyword = request.args.get("message_query", "")
    err_code_keyword = request.args.get("err_code_query", "")
    status_filter = normalize_status_filter(request.args.get("status", "all"))
    filtered_items = filter_report_results(report, keyword, status_filter, message_keyword, err_code_keyword)
    paged = paginate_items(filtered_items, page, page_size)
    paged.update({
        "report_name": report.get("report_name", ""),
        "query": keyword,
        "message_query": message_keyword,
        "err_code_query": err_code_keyword,
        "status": status_filter or "all",
    })
    return jsonify(paged)


@app.route("/api/report-result-detail/<path:report_name>/<int:result_index>")
def api_report_result_detail(report_name: str, result_index: int):
    try:
        report = find_report(report_name)
    except FileNotFoundError:
        return jsonify({"error": f"报告不存在: {report_name}"}), 404

    try:
        return jsonify(build_result_detail(report, result_index))
    except IndexError:
        return jsonify({"error": f"结果索引不存在: {result_index}"}), 404


@app.route("/api/compare")
def api_compare():
    left_name = request.args.get("left", "")
    right_name = request.args.get("right", "")
    if not left_name or not right_name:
        return jsonify({"error": "left 和 right 参数不能为空"}), 400
    try:
        left = find_report(left_name)
        right = find_report(right_name)
    except FileNotFoundError as exc:
        return jsonify({"error": f"报告不存在: {exc}"}), 404
    return jsonify(compare_report_data(left, right))


@app.route("/test-token", methods=["POST"])
def test_token():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", "")).strip()
    if not token:
        return jsonify({"success": False, "message": "token 不能为空"}), 400
    return jsonify({"success": True, "message": "已接收 token，可用于重新请求。"})


@app.route("/re-request-api", methods=["POST"])
def re_request_api():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    method = str(payload.get("method", "GET")).upper()
    headers = dict(payload.get("headers") or {})
    params = dict(payload.get("params") or {})
    body = payload.get("body")
    token = str(payload.get("token", "")).strip()
    # 回写相关字段（可选，不影响原有不传这几个字段的调用路径）
    save_to_report = bool(payload.get("save_to_report", False))
    rpt_name = str(payload.get("report_name", "")).strip()
    rpt_index_raw = payload.get("result_index")
    try:
        rpt_index: Optional[int] = int(rpt_index_raw) if rpt_index_raw is not None else None
    except (TypeError, ValueError):
        rpt_index = None
    expected_status = int(payload.get("expected_status") or 200)

    if not url:
        return jsonify({"error": "url 不能为空"}), 400

    if token:
        header_key = None
        for existing_key in list(headers.keys()):
            if existing_key.lower() == "authorization":
                header_key = existing_key
            if existing_key.lower() == "token":
                headers.pop(existing_key)
        if header_key:
            headers[header_key] = f"Bearer {token}"
        else:
            headers["token"] = token

    try:
        response = requests.request(method=method, url=url, headers=headers, params=params, json=body, timeout=60)
        try:
            response_body: Any = response.json()
        except ValueError:
            response_body = response.text

        # 应用与执行层一致的业务判定规则
        response_message, err_code = _extract_msg_errcode(response_body)
        status_code_ok = response.status_code == expected_status
        normalized_msg = str(response_message or "").strip().lower()
        message_ok = normalized_msg == "" or normalized_msg == "success"

        if status_code_ok and message_ok:
            result_status = "PASSED"
            result_message = response_message
        else:
            result_status = "FAILED"
            if not status_code_ok:
                result_message = f"期望状态码: {expected_status}, 实际: {response.status_code}; message: {response_message}"
            else:
                result_message = f"message 不满足成功条件(应为空或 success), 实际返回: {response_message}"

        new_request_info = {"headers": headers, "params": params, "body": body}
        new_response_info = {"headers": dict(response.headers), "body": response_body}

        result_fields = {
            "method": method,
            "url": url,
            "item_path": payload.get("item_path", []),
            "expected_status": expected_status,
            "status": result_status,
            "status_code": response.status_code,
            "message": result_message,
            "err_code": err_code,
        }

        new_summary: Dict[str, Any] = {}
        if save_to_report and rpt_name and rpt_index is not None:
            new_summary = patch_report_result(rpt_name, rpt_index, result_fields, new_request_info, new_response_info)

        return jsonify({
            "name": payload.get("name", url),
            "folder": payload.get("folder", ""),
            "method": method,
            "url": url,
            **result_fields,
            "request_info": new_request_info,
            "response_info": new_response_info,
            "new_summary": new_summary,
            "saved": bool(new_summary),
        })
    except Exception as exc:
        return jsonify({
            "name": payload.get("name", url),
            "folder": payload.get("folder", ""),
            "method": method,
            "url": url,
            "status": "ERROR",
            "status_code": None,
            "message": str(exc),
            "err_code": "",
            "request_info": {"headers": headers, "params": params, "body": body},
            "response_info": {"headers": {}, "body": str(exc)},
            "new_summary": {},
            "saved": False,
        })


@app.route("/api/run-postman", methods=["POST"])
def api_run_postman():
    collection_file = request.files.get("collection_file")
    if not collection_file or not str(collection_file.filename or "").strip():
        return jsonify({"error": "请先上传 Postman JSON 文件。"}), 400

    original_name = str(collection_file.filename or "").strip()
    if not original_name.lower().endswith(".json"):
        return jsonify({"error": "仅支持上传 .json 文件。"}), 400

    # 清洗原始文件名：仅保留合法字符，防止路径穿越和注入风险
    import re as _re
    _safe_name = _re.sub(r'[^\w\u4e00-\u9fff\-. ()（）【】]', '_', original_name).strip('. ')
    original_name = _safe_name if _safe_name else "collection.json"

    base_url = str(request.form.get("base_url", "")).strip() or None
    # 校验 base_url 格式，防止 SSRF：仅允许 http/https，禁止 file://、ftp:// 等
    if base_url is not None:
        from urllib.parse import urlparse as _urlparse
        _parsed = _urlparse(base_url)
        if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
            return jsonify({"error": "base_url 格式无效，仅支持 http/https 协议。"}), 400
    token = str(request.form.get("token", "")).strip() or None
    output_dir = str(request.form.get("output_dir", "")).strip() or str(REPORTS_DIR)
    report_name = str(request.form.get("report_name", "")).strip() or None
    results_per_page = clamp_run_results_per_page(request.form.get("results_per_page", 30))

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix or ".json"
    job_id = uuid.uuid4().hex
    saved_file = UPLOADS_DIR / f"{job_id}{suffix}"
    collection_file.save(str(saved_file))

    set_run_job(
        job_id,
        id=job_id,
        status="queued",
        message="任务已创建，等待执行。",
        total=0,
        completed=0,
        percent=0,
        current_name="",
        file_name=original_name,
        saved_file=str(saved_file),
        output_dir=output_dir,
        report_name=report_name or "",
    )

    worker = threading.Thread(
        target=run_postman_job,
        args=(job_id, str(saved_file), base_url, output_dir, token, report_name, original_name, results_per_page),
        daemon=True,
    )
    worker.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "任务已启动，请稍后查看执行状态。",
    })


@app.route("/api/run-postman-status/<path:job_id>")
def api_run_postman_status(job_id: str):
    job = get_run_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在。"}), 404
    return jsonify(job)


@app.route("/latest")
def latest_report():
    reports = list_reports()
    if not reports:
        return redirect(url_for("index"))
    return redirect(url_for("report_view", name=reports[0]["report_name"]))


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("REPORT_SERVER_PORT", "5000"))
    host = os.environ.get("REPORT_SERVER_HOST", "0.0.0.0")
    print(f"报告目录: {REPORTS_DIR}")
    logger.info("报告服务启动: http://127.0.0.1:%d", port)
    logger.info("局域网访问地址: http://%s:%d", get_local_ip(), port)
    try:
        from waitress import serve
        logger.info("使用 waitress WSGI 服务器（生产模式）")
        serve(app, host=host, port=port)
    except ImportError:
        logger.warning("waitress 未安装，降级使用 Flask 开发服务器（建议 pip install waitress）")
        app.run(host=host, port=port, debug=False)
