"""
db_manager.py
数据库可视化管理工具
浏览器打开 http://localhost:5050
"""
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.paths import DB_PATH
from pathlib import Path

app = Flask(__name__)

# 支持的数据库列表
DB_FILES = {
    "default": DB_PATH,
    "Theresa": Path("data/chatbot_Theresa.db"),
    "shared": Path("data/chatbot_shared.db"),
}
# 动态扫描 accounts 目录下的 user_data.db
accounts_dir = Path("data/accounts")
if accounts_dir.exists():
    for user_dir in accounts_dir.iterdir():
        if user_dir.is_dir():
            for persona_dir in user_dir.iterdir():
                if persona_dir.is_dir():
                    db_path = persona_dir / "user_data.db"
                    if db_path.exists():
                        key = f"{user_dir.name}/{persona_dir.name}"
                        DB_FILES[key] = db_path

SELECTED_DB = "Theresa"  # 默认选中 Theresa 数据库

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>QQ Bot 数据库管理</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }
        h1 { color: #e94560; margin-bottom: 20px; font-size: 24px; }
        .nav {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .nav a {
            padding: 8px 16px;
            background: #16213e;
            color: #eee;
            text-decoration: none;
            border-radius: 6px;
            font-size: 14px;
            transition: background 0.2s;
        }
        .nav a:hover, .nav a.active { background: #e94560; }
        .toolbar {
            background: #16213e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        .toolbar label { font-size: 13px; color: #aaa; }
        .toolbar input[type="date"], .toolbar input[type="text"] {
            padding: 6px 10px;
            background: #0f3460;
            border: 1px solid #333;
            color: #eee;
            border-radius: 4px;
            font-size: 13px;
        }
        .toolbar button, .btn {
            padding: 6px 14px;
            background: #e94560;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            text-decoration: none;
        }
        .toolbar button:hover, .btn:hover { background: #ff6b6b; }
        .btn-sm { padding: 3px 10px; font-size: 12px; }
        .btn-clear {
            padding: 8px 20px;
            background: #e94560;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: #16213e;
            border-radius: 8px;
            overflow: hidden;
        }
        th {
            background: #0f3460;
            padding: 12px 8px;
            text-align: left;
            font-size: 13px;
            color: #e94560;
            white-space: nowrap;
        }
        td {
            padding: 10px 8px;
            border-bottom: 1px solid #1a1a2e;
            font-size: 13px;
            max-width: 250px;
            word-break: break-all;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        tr:hover { background: #1a1a3e; }
        td.detail-cell { cursor: pointer; }
        td.detail-cell:hover { color: #e94560; }
        .empty { text-align: center; padding: 40px; color: #666; }
        .stats { font-size: 13px; color: #aaa; margin-bottom: 10px; }
        .stats span { color: #e94560; font-weight: bold; }
        input[type="checkbox"] {
            width: 16px; height: 16px; cursor: pointer;
        }
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.active { display: flex; }
        .modal {
            background: #16213e;
            border-radius: 12px;
            padding: 25px;
            max-width: 700px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            position: relative;
        }
        .modal h2 { color: #e94560; margin-bottom: 15px; font-size: 18px; }
        .modal-close {
            position: absolute;
            top: 15px; right: 20px;
            font-size: 24px;
            cursor: pointer;
            color: #888;
        }
        .modal-close:hover { color: #e94560; }
        .modal-field {
            margin-bottom: 12px;
            padding: 10px;
            background: #1a1a2e;
            border-radius: 6px;
        }
        .modal-field .label {
            font-size: 12px;
            color: #e94560;
            margin-bottom: 4px;
        }
        .modal-field .value {
            font-size: 14px;
            word-break: break-all;
            white-space: pre-wrap;
        }
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-left: auto;
        }
        .auto-refresh label { font-size: 13px; color: #aaa; }
        .auto-refresh select {
            padding: 6px 10px;
            background: #0f3460;
            border: 1px solid #333;
            color: #eee;
            border-radius: 4px;
            font-size: 13px;
        }
        .live-dot {
            width: 8px; height: 8px;
            background: #4ecca3;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        .live-dot.paused { background: #666; animation: none; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        .last-update { font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <h1>📊 QQ Bot 数据库管理</h1>

    <div class="nav" style="margin-bottom: 10px;">
        {% for db_name in db_files %}
        <a href="/switch_db/{{ db_name }}" {% if db_name == selected_db %}class="active"{% endif %}>
            📁 {{ db_name }}
        </a>
        {% endfor %}
    </div>
    <div style="font-size: 12px; color: #888; margin-bottom: 15px;">当前数据库: <span style="color: #e94560;">{{ selected_db }}</span> ({{ db_files[selected_db] }})</div>

    <div class="nav">
        {% for t in tables %}
        <a href="/table/{{ t }}" {% if t == current_table %}class="active"{% endif %}>
            {{ t }} ({{ table_counts[t] }})
        </a>
        {% endfor %}
    </div>

    {% if current_table %}
    <form method="GET" action="/table/{{ current_table }}" class="toolbar">
        <label>开始:</label>
        <input type="date" name="start_date" value="{{ start_date }}">
        <label>结束:</label>
        <input type="date" name="end_date" value="{{ end_date }}">
        <label>关键词:</label>
        <input type="text" name="keyword" value="{{ keyword }}" placeholder="搜索...">
        <button type="submit">筛选</button>
        <a href="/table/{{ current_table }}" class="btn" style="background:#333;">重置</a>
        <div class="auto-refresh">
            <div class="live-dot paused" id="liveDot"></div>
            <label>刷新:</label>
            <select id="refreshSelect" onchange="startAutoRefresh()">
                <option value="0">关闭</option>
                <option value="3">3秒</option>
                <option value="5" selected>5秒</option>
                <option value="10">10秒</option>
            </select>
            <span class="last-update" id="lastUpdate"></span>
        </div>
    </form>

    <div class="stats">
        当前表: <span>{{ current_table }}</span> |
        显示: <span>{{ rows|length }}</span> 条 |
        总计: <span>{{ table_counts[current_table] }}</span> 条 |
        主键: <span>{{ pk_col }}</span>
    </div>

    {% if rows %}
    <form method="POST" action="/batch_delete/{{ current_table }}" id="batchForm"
          onsubmit="return confirm('确定删除选中的记录吗？')">
        <input type="hidden" name="start_date" value="{{ start_date }}">
        <input type="hidden" name="end_date" value="{{ end_date }}">
        <input type="hidden" name="keyword" value="{{ keyword }}">

        <div style="margin-bottom: 10px; display: flex; gap: 10px;">
            <button type="button" class="btn btn-sm" onclick="toggleAll()">全选/取消</button>
            <button type="submit" class="btn btn-sm" style="background:#ff6b6b;">删除选中</button>
            <button type="button" class="btn btn-sm" style="background:#333;"
                    onclick="clearAll()">清空全部</button>
        </div>

        <table>
            <tr>
                <th style="width:30px;"><input type="checkbox" id="checkAll" onclick="toggleAll()"></th>
                {% for col in columns %}
                <th>{{ col }}</th>
                {% endfor %}
                <th style="width:80px;">操作</th>
            </tr>
            {% for row in rows %}
            <tr>
                <td><input type="checkbox" name="ids" value="{{ row[pk_col] }}" class="row-check"></td>
                {% for col in columns %}
                <td class="detail-cell" onclick="showDetail({{ loop.index }})">
                    {{ (row[col]|string)[:80] if row[col] is not none else '' }}
                </td>
                {% endfor %}
                <td>
                    <a href="javascript:void(0)" onclick="showDetail({{ loop.index }})" class="btn btn-sm">详情</a>
                    <a href="javascript:void(0)" onclick="deleteSingle('{{ row[pk_col] }}')" class="btn btn-sm" style="background:#ff6b6b;">删除</a>
                </td>
            </tr>
            {% endfor %}
        </table>
    </form>

    {% for row in rows %}
    <div class="modal-overlay" id="detail-{{ loop.index }}" onclick="closeDetail({{ loop.index }})">
        <div class="modal" onclick="event.stopPropagation()">
            <span class="modal-close" onclick="closeDetail({{ loop.index }})">&times;</span>
            <h2>记录详情</h2>
            {% for col in columns %}
            <div class="modal-field">
                <div class="label">{{ col }}</div>
                <div class="value">{{ row[col] if row[col] is not none else '(空)' }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}

    {% else %}
    <div class="empty">暂无数据</div>
    {% endif %}
    {% endif %}

    <script>
        function toggleAll() {
            const checkAll = document.getElementById('checkAll');
            document.querySelectorAll('.row-check').forEach(cb => {
                cb.checked = checkAll.checked;
            });
        }
        function showDetail(index) {
            document.getElementById('detail-' + index).classList.add('active');
        }
        function closeDetail(index) {
            document.getElementById('detail-' + index).classList.remove('active');
        }
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active'));
            }
        });

        function deleteSingle(pkValue) {
            if (!confirm('确定删除这条记录吗？')) return;
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/delete/{{ current_table }}/' + pkValue;
            // 传递筛选参数
            const params = {
                start_date: '{{ start_date }}',
                end_date: '{{ end_date }}',
                keyword: '{{ keyword }}'
            };
            for (const [key, val] of Object.entries(params)) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = val;
                form.appendChild(input);
            }
            document.body.appendChild(form);
            form.submit();
        }

        function clearAll() {
            if (!confirm('确定清空 {{ current_table }} 的所有数据吗？此操作不可恢复！')) return;
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/clear/{{ current_table }}';
            document.body.appendChild(form);
            form.submit();
        }

        // ========== 自动刷新 ==========
        let refreshTimer = null;

        function startAutoRefresh() {
            stopAutoRefresh();
            const interval = parseInt(document.getElementById('refreshSelect').value);
            if (interval <= 0) {
                document.getElementById('liveDot').classList.add('paused');
                return;
            }
            document.getElementById('liveDot').classList.remove('paused');
            refreshTimer = setInterval(() => refreshData(), interval * 1000);
        }

        function stopAutoRefresh() {
            if (refreshTimer) {
                clearInterval(refreshTimer);
                refreshTimer = null;
            }
        }

        async function refreshData() {
            try {
                const resp = await fetch(window.location.href);
                const html = await resp.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                const newTable = doc.querySelector('table');
                const oldTable = document.querySelector('table');
                if (newTable && oldTable) {
                    oldTable.innerHTML = newTable.innerHTML;
                }

                const newStats = doc.querySelector('.stats');
                const oldStats = document.querySelector('.stats');
                if (newStats && oldStats) {
                    oldStats.innerHTML = newStats.innerHTML;
                }

                document.getElementById('lastUpdate').textContent =
                    '更新于 ' + new Date().toLocaleTimeString();
            } catch (e) {
                console.log('刷新失败:', e);
            }
        }

        startAutoRefresh();
    </script>
</body>
</html>
"""


def get_db():
    db_path = DB_FILES.get(SELECTED_DB, DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_tables():
    conn = get_db()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
    ).fetchall()]
    counts = {}
    for t in tables:
        try:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        except:
            counts[t] = 0
    conn.close()
    return tables, counts


def get_pk_and_time(table_name):
    """获取主键列名和时间列名"""
    conn = get_db()
    cols = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
    conn.close()

    pk_col = "id"
    time_col = None

    for c in cols:
        if c["pk"] > 0:
            pk_col = c["name"]

    time_candidates = ['timestamp', 'created_at', 'updated_at', 'last_accessed',
                       'last_seen', 'date', 'last_analyzed', 'time']
    col_names = [c["name"] for c in cols]
    for candidate in time_candidates:
        if candidate in col_names:
            time_col = candidate
            break

    return pk_col, time_col


@app.route("/")
def index():
    tables, counts = get_tables()
    return render_template_string(
        HTML_TEMPLATE, tables=tables, table_counts=counts,
        current_table=None, rows=[], columns=[], start_date="", end_date="", keyword="", pk_col="id",
        db_files=DB_FILES, selected_db=SELECTED_DB
    )

@app.route("/switch_db/<db_name>")
def switch_db(db_name):
    global SELECTED_DB
    if db_name in DB_FILES:
        SELECTED_DB = db_name
    return redirect(url_for("index"))


@app.route("/table/<table_name>")
def view_table(table_name):
    tables, counts = get_tables()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    keyword = request.args.get("keyword", "")

    conn = get_db()
    columns = [r[1] for r in conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()]
    pk_col, time_col = get_pk_and_time(table_name)

    query = f"SELECT * FROM [{table_name}]"
    conditions = []
    params = []

    if time_col and start_date:
        conditions.append(f"[{time_col}] >= ?")
        params.append(start_date)
    if time_col and end_date:
        conditions.append(f"[{time_col}] <= ?")
        params.append(end_date + " 23:59:59")

    if keyword:
        like_parts = []
        for col in columns:
            like_parts.append(f"CAST([{col}] AS TEXT) LIKE ?")
            params.append(f"%{keyword}%")
        conditions.append(f"({' OR '.join(like_parts)})")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY rowid DESC LIMIT 500"

    rows = conn.execute(query, params).fetchall()
    rows = [dict(r) for r in rows]
    conn.close()

    return render_template_string(
        HTML_TEMPLATE, tables=tables, table_counts=counts,
        current_table=table_name, rows=rows, columns=columns,
        start_date=start_date, end_date=end_date, keyword=keyword, pk_col=pk_col,
        db_files=DB_FILES, selected_db=SELECTED_DB
    )


@app.route("/delete/<table_name>/<path:pk_value>", methods=["POST"])
def delete_row(table_name, pk_value):
    pk_col, _ = get_pk_and_time(table_name)
    conn = get_db()
    conn.execute(f"DELETE FROM [{table_name}] WHERE [{pk_col}] = ?", (pk_value,))
    conn.commit()
    conn.close()
    return redirect(url_for("view_table", table_name=table_name,
                            start_date=request.form.get("start_date", ""),
                            end_date=request.form.get("end_date", ""),
                            keyword=request.form.get("keyword", "")))


@app.route("/batch_delete/<table_name>", methods=["POST"])
def batch_delete(table_name):
    pk_col, _ = get_pk_and_time(table_name)
    ids = request.form.getlist("ids")
    if ids:
        conn = get_db()
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM [{table_name}] WHERE [{pk_col}] IN ({placeholders})", ids)
        conn.commit()
        conn.close()
    return redirect(url_for("view_table", table_name=table_name,
                            start_date=request.form.get("start_date", ""),
                            end_date=request.form.get("end_date", ""),
                            keyword=request.form.get("keyword", "")))


@app.route("/clear/<table_name>", methods=["POST"])
def clear_table(table_name):
    conn = get_db()
    conn.execute(f"DELETE FROM [{table_name}]")
    conn.commit()
    conn.close()
    return redirect(url_for("view_table", table_name=table_name))


if __name__ == "__main__":
    print("=" * 40)
    print("数据库管理工具已启动")
    print("浏览器打开: http://localhost:5050")
    print("=" * 40)
    app.run(host="0.0.0.0", port=5050, debug=False)

# [0.0.4 PATCH FIX] Applied requested modifications here.
