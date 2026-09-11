"""AgentForge Streamlit 前端 v2.0。

设计参考（2026-09 联网调研）：LangSmith/LangFuse 的"左侧导航 + 状态徽章 + 运行时间线 + 分栏详情"，
Dify 的"工作流/应用分页 + 运行面板"。
页面：发起研究 / 任务历史 / 知识库 / 实验对比 / 系统信息。
"""

from __future__ import annotations

import os
import time

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="AgentForge", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

STATUS_META = {
    "pending": ("排队中", "#f59e0b"),
    "running": ("执行中", "#3b82f6"),
    "paused": ("待确认", "#8b5cf6"),
    "completed": ("已完成", "#10b981"),
    "failed": ("失败", "#ef4444"),
    "canceled": ("已取消", "#6b7280"),
}

CSS = """
<style>
:root { --af-bg:#0f1115; --af-card:#171a21; --af-border:#262b36; --af-text:#e6e9ef; --af-muted:#9aa4b2; --af-accent:#6d8cff; }
.block-container { padding-top: 1.6rem; max-width: 1280px; }
.af-hero { background: linear-gradient(120deg,#1b2340 0%,#131722 60%,#10131a 100%); border:1px solid var(--af-border);
  border-radius:18px; padding:22px 26px; margin-bottom:18px; }
.af-hero h1 { margin:0; font-size:1.7rem; color:#fff; letter-spacing:.2px; }
.af-hero p { margin:6px 0 0; color:var(--af-muted); font-size:.95rem; }
.af-card { background:var(--af-card); border:1px solid var(--af-border); border-radius:14px; padding:16px 18px; margin-bottom:12px; }
.af-card h3 { margin:0 0 6px; font-size:1.02rem; color:#fff; }
.af-muted { color:var(--af-muted); font-size:.86rem; }
.af-badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:600; }
.af-timeline { border-left:2px solid #2b3242; margin:6px 0 0 6px; padding-left:14px; }
.af-timeline-item { position:relative; padding:4px 0 8px; color:#cfd6e2; font-size:.86rem; }
.af-timeline-item:before { content:''; position:absolute; left:-20px; top:10px; width:8px; height:8px; border-radius:50%; background:var(--af-accent); }
.af-kv { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed #232936; font-size:.88rem; }
.af-kv:last-child { border-bottom:none; }
.af-kv span:first-child { color:var(--af-muted); }
.af-source { background:#12161f; border:1px solid var(--af-border); border-left:3px solid var(--af-accent); border-radius:8px; padding:10px 12px; margin:6px 0; font-size:.85rem; color:#cdd5e1; }
[data-testid="stSidebar"] { background:#12151c; border-right:1px solid var(--af-border); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def api(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=kwargs.pop("timeout", 120), **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail") or response.json().get("error")
            except Exception:
                detail = response.text
            return {"_error": detail or f"HTTP {response.status_code}", "_status": response.status_code}
        return response.json()
    except requests.RequestException as exc:
        return {"_error": str(exc)}


def badge(status: str) -> str:
    label, color = STATUS_META.get(status, (status, "#6b7280"))
    return f'<span class="af-badge" style="background:{color}22;color:{color};border:1px solid {color}55">{label}</span>'


def hero() -> None:
    st.markdown(
        '<div class="af-hero"><h1>🤖 AgentForge</h1>'
        '<p>多 Agent 研究协作系统 · 规划 → 搜索 → 分析 → 撰写 → 审核 · 人机协同可暂停/恢复 · 全链路可观测</p></div>',
        unsafe_allow_html=True,
    )


def timeline(logs: list[str], limit: int = 12) -> None:
    items = "".join(f'<div class="af-timeline-item">{line}</div>' for line in (logs or [])[-limit:])
    st.markdown(f'<div class="af-timeline">{items or "<div class=af-timeline-item>暂无日志</div>"}</div>', unsafe_allow_html=True)


def render_report_tabs(task: dict) -> None:
    tab_report, tab_sources, tab_review, tab_metrics, tab_logs = st.tabs(
        ["📄 报告", "📎 来源", "🧪 审核历史", "📊 指标", "🧭 执行日志"]
    )
    with tab_report:
        report = task.get("final_report") or task.get("draft_report") or ""
        st.markdown(report or "（暂无报告）")
        if report:
            st.download_button("⬇️ 下载 Markdown", data=report, file_name=f"report_{task.get('id')}.md", mime="text/markdown")
    with tab_sources:
        search_results = task.get("search_results") or []
        if not search_results:
            st.info("暂无检索来源记录")
        for entry in search_results:
            with st.expander(f"❓ {entry.get('question','')}（{len(entry.get('documents') or [])} 条）"):
                for doc in entry.get("documents") or []:
                    st.markdown(
                        f'<div class="af-source"><b>{doc.get("title","来源")}</b><br/>{doc.get("content","")[:400]}...</div>',
                        unsafe_allow_html=True,
                    )
    with tab_review:
        history = task.get("review_history") or []
        if not history:
            st.info("暂无审核记录")
        for item in history:
            st.markdown(f"**第 {item.get('round')} 轮 · 评分 {item.get('score')}/10**")
            for suggestion in item.get("suggestions") or []:
                st.markdown(f"- {suggestion}")
            for issue in item.get("issues") or []:
                st.markdown(f"- ⚠️ {issue}")
    with tab_metrics:
        metrics = task.get("metrics") or {}
        if not metrics:
            st.info("暂无指标（任务未执行或为旧任务）")
        else:
            cols = st.columns(4)
            cols[0].metric("LLM 调用", metrics.get("llm_calls", 0))
            cols[1].metric("Tavily 调用", metrics.get("tavily_calls", 0))
            cols[2].metric("tokens(输入/输出)", f"{metrics.get('prompt_tokens') or 0} / {metrics.get('completion_tokens') or 0}")
            cols[3].metric("估算成本 ¥", metrics.get("estimated_cost_cny", 0))
            st.markdown("**节点耗时（毫秒）**")
            st.dataframe(metrics.get("node_latencies") or [], use_container_width=True, hide_index=True)
            st.caption(
                f"耗时 {metrics.get('elapsed_seconds', '-')}s ｜ JSON 解析失败 {metrics.get('json_parse_failures', 0)} ｜ "
                f"搜索明细 {metrics.get('search_by_backend')}"
            )
    with tab_logs:
        timeline(task.get("logs") or [], limit=60)


def render_task_detail(task: dict) -> None:
    st.markdown(
        f'<div class="af-card"><h3>{task.get("topic","")}</h3>'
        f'<div class="af-muted">任务 #{task.get("id")} · {badge(task.get("status",""))} · 审核 {task.get("review_rounds",0)} 轮</div></div>',
        unsafe_allow_html=True,
    )
    render_report_tabs(task)


def render_paused_editor(task: dict) -> None:
    st.warning("任务已暂停：请确认或编辑子问题后继续。")
    proposed = task.get("sub_questions") or []
    edited = st.text_area("子问题（每行一个）", value="\n".join(proposed), height=160)
    if st.button("▶️ 继续执行", type="primary"):
        questions = [line.strip() for line in edited.splitlines() if line.strip()]
        result = api("POST", f"/api/tasks/{task['id']}/resume", json={"sub_questions": questions})
        if "_error" in result:
            st.error(result["_error"])
        else:
            st.success("已恢复执行")
            st.rerun()


def page_new_research() -> None:
    hero()
    st.markdown('<div class="af-card"><h3>发起研究</h3><div class="af-muted">输入一个研究主题，系统会自动拆解、检索、分析、撰写并审核。</div></div>', unsafe_allow_html=True)
    topic = st.text_input("研究主题", placeholder="例如：2025 年大模型行业趋势分析")
    cols = st.columns(3)
    examples = ["RAG 与 Agent 的区别", "大模型应用工程师需要哪些能力", "向量数据库技术选型对比"]
    for col, example in zip(cols, examples):
        if col.button(example, use_container_width=True):
            topic = example

    if st.button("🚀 开始研究", type="primary", disabled=not topic.strip()):
        created = api("POST", "/api/tasks", json={"topic": topic})
        if "_error" in created:
            st.error(created["_error"])
            return
        task_id = created["data"]["id"]
        st.info(f"任务 #{task_id} 已创建")
        holder = st.empty()
        task = None
        for _ in range(150):
            task = api("GET", f"/api/tasks/{task_id}").get("data")
            if not task:
                break
            with holder.container():
                st.markdown(f'状态：{badge(task.get("status",""))}', unsafe_allow_html=True)
                timeline(task.get("logs") or [])
            if task.get("status") not in ("pending", "running"):
                break
            time.sleep(1.5)
        if not task:
            st.error("查询任务失败")
        elif task.get("status") == "paused":
            render_paused_editor(task)
        elif task.get("status") == "completed":
            st.success("研究完成")
            render_task_detail(task)
        elif task.get("status") == "failed":
            st.error(f"任务失败：{task.get('error')}")


def page_history() -> None:
    hero()
    tasks = api("GET", "/api/tasks").get("data") or []
    if not tasks:
        st.info("暂无历史任务")
        return
    statuses = ["全部"] + sorted({t.get("status") for t in tasks})
    selected_status = st.selectbox("按状态筛选", statuses)
    filtered = [t for t in tasks if selected_status == "全部" or t.get("status") == selected_status]
    for task in filtered:
        with st.expander(f"#{task['id']} · {task['topic']} · {task['status']}"):
            st.markdown(badge(task.get("status", "")), unsafe_allow_html=True)
            st.caption(f"创建：{task.get('created_at')} ｜ 完成：{task.get('completed_at') or '-'}")
            detail = api("GET", f"/api/tasks/{task['id']}").get("data")
            if detail:
                render_report_tabs(detail)


def page_kb() -> None:
    hero()
    stats = api("GET", "/api/kb/stats")
    if "_error" in stats:
        st.error(stats["_error"])
        return
    cols = st.columns(4)
    cols[0].metric("语料文档", stats.get("document_count", 0))
    cols[1].metric("索引分块", stats.get("collection_count", 0))
    cols[2].metric("集合", stats.get("collection", "-"))
    cols[3].metric("语料版本", stats.get("corpus_version", "-"))
    st.markdown("#### 📚 语料清单")
    st.dataframe(stats.get("documents") or [], use_container_width=True, hide_index=True)
    st.markdown("#### 🔍 检索预览")
    query = st.text_input("输入检索问题", placeholder="例如：RAG 的完整流程是什么？")
    if st.button("检索", disabled=not query.strip()):
        result = api("POST", "/api/kb/search", json={"query": query, "n_results": 3})
        if "_error" in result:
            st.error(result["_error"])
        else:
            for item in result.get("results") or []:
                st.markdown(f'<div class="af-source"><b>{item.get("title","")}</b><br/>{item.get("content","")[:500]}</div>', unsafe_allow_html=True)


def page_experiments() -> None:
    hero()
    payload = api("GET", "/api/experiments/live")
    if "_error" in payload:
        st.error(payload["_error"])
        return
    if not payload.get("available"):
        st.info("暂无实验数据（data/live_results.json 不存在）")
        return
    data = payload["data"]
    st.markdown("#### ⚖️ Ollama vs DeepSeek（真实运行记录）")
    for provider in ("ollama", "deepseek"):
        block = data.get(provider)
        if not block:
            continue
        totals = block.get("totals", {})
        cols = st.columns(4)
        cols[0].metric(f"{provider} 任务", totals.get("tasks", 0))
        cols[1].metric("Tavily 调用", totals.get("tavily_calls", 0))
        cols[2].metric("估算成本 ¥", totals.get("estimated_cost_cny", 0))
        cols[3].metric("tokens", f"{(totals.get('prompt_tokens') or 0)}/{(totals.get('completion_tokens') or 0)}")
        st.dataframe(block.get("records") or [], use_container_width=True, hide_index=True)
    st.caption(data.get("note", ""))


def page_system() -> None:
    hero()
    info = api("GET", "/api/system/info")
    if "_error" in info:
        st.error(info["_error"])
        return
    cols = st.columns(4)
    cols[0].metric("Provider", info.get("provider", "-"))
    cols[1].metric("模型", info.get("ollama_model", "-") if info.get("provider") == "ollama" else info.get("deepseek_model", "-"))
    cols[2].metric("记忆", "开启" if info.get("memory_enabled") else "关闭")
    cols[3].metric("人机协同", "开启" if info.get("human_review_enabled") else "关闭")
    st.markdown("#### 🧱 单任务硬上限")
    st.json(info.get("limits") or {})
    st.markdown("#### 💰 价格/授权状态")
    st.json(info.get("price_status") or {})
    st.markdown("#### 🧰 工具与 MCP")
    st.write(info.get("mcp_tools") or [])
    st.markdown("#### 🧬 Embedding")
    st.json(info.get("embedding") or {})


PAGE_KEYS = {
    "new": "🚀 发起研究",
    "history": "🗂️ 任务历史",
    "kb": "📚 知识库",
    "experiments": "⚖️ 实验对比",
    "system": "⚙️ 系统信息",
}
PAGE_TO_KEY = {value: key for key, value in PAGE_KEYS.items()}
_query_page = st.query_params.get("page", "new")
_options = list(PAGE_KEYS.values())
_default_index = _options.index(PAGE_KEYS.get(_query_page, _options[0]))

with st.sidebar:
    st.markdown('<div style="padding:6px 2px 12px"><b style="color:#fff;font-size:1.1rem">AgentForge</b><br/><span class="af-muted">v2.0 · 本地优先</span></div>', unsafe_allow_html=True)
    page = st.radio("导航", _options, index=_default_index, label_visibility="collapsed")
    if PAGE_TO_KEY.get(page) != _query_page:
        st.query_params["page"] = PAGE_TO_KEY.get(page, "new")
    st.divider()
    system = api("GET", "/api/system/info")
    if "_error" not in system:
        st.caption(f"Provider：{system.get('provider')}")
        st.caption(f"付费授权：{'允许' if system.get('paid_allowed') else '关闭'}")
    kb = api("GET", "/api/kb/stats")
    if "_error" not in kb:
        st.caption(f"知识库：{kb.get('collection_count', 0)} chunks")

if page.startswith("🚀"):
    page_new_research()
elif page.startswith("🗂️"):
    page_history()
elif page.startswith("📚"):
    page_kb()
elif page.startswith("⚖️"):
    page_experiments()
else:
    page_system()
