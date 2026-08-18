"""AgentForge Streamlit 前端。"""

from __future__ import annotations

import os
import time

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="AgentForge", page_icon="🤖", layout="wide")
st.title("🤖 AgentForge — 多 Agent 智能研究协作系统")


def create_task(topic: str) -> int | None:
    try:
        resp = requests.post(f"{API_URL}/api/tasks", json={"topic": topic}, timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]["id"]
    except requests.RequestException as exc:
        st.error(f"提交任务失败：{exc}")
        return None


def fetch_task(task_id: int) -> dict | None:
    try:
        resp = requests.get(f"{API_URL}/api/tasks/{task_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()["data"]
    except requests.RequestException as exc:
        st.error(f"查询任务失败：{exc}")
        return None


tab_new, tab_history = st.tabs(["发起研究", "任务历史"])

with tab_new:
    topic = st.text_input("研究主题", placeholder="例如：2025 年大模型行业趋势分析")
    if st.button("开始研究", type="primary", disabled=not topic.strip()):
        task_id = create_task(topic)
        if task_id is not None:
            st.info(f"任务已提交，ID = {task_id}，正在执行……")
            placeholder = st.empty()
            task = fetch_task(task_id)
            max_polls = 150  # 约 5 分钟保护，避免无限轮询
            polls = 0
            while task and task["status"] in ("pending", "running") and polls < max_polls:
                placeholder.markdown(
                    f"**状态**：{task['status']}  \n"
                    + "\n".join(f"- {line}" for line in (task.get("logs") or [])[-6:])
                )
                time.sleep(2)
                polls += 1
                task = fetch_task(task_id)
            if task and task["status"] in ("pending", "running"):
                placeholder.warning("任务执行时间较长，仍在后台运行，可稍后到「任务历史」查看")

            if task and task["status"] == "completed":
                placeholder.success("任务完成")
                report = task.get("final_report") or ""
                st.markdown("### 研究报告")
                st.markdown(report)
                with st.expander("过程详情"):
                    st.json(
                        {
                            "子问题": task.get("sub_questions"),
                            "审核轮次": task.get("review_rounds"),
                            "审核历史": task.get("review_history"),
                        }
                    )
            elif task and task["status"] == "failed":
                placeholder.error(f"任务失败：{task.get('error')}")

with tab_history:
    if st.button("刷新列表"):
        st.rerun()
    try:
        resp = requests.get(f"{API_URL}/api/tasks", timeout=10)
        resp.raise_for_status()
        tasks = resp.json()["data"]
    except requests.RequestException as exc:
        st.error(f"获取任务列表失败：{exc}")
        tasks = []

    if not tasks:
        st.write("暂无历史任务。")
    else:
        for t in tasks:
            with st.expander(f"#{t['id']} · {t['topic']} · {t['status']}"):
                st.write(f"创建时间：{t.get('created_at')}")
                if t.get("completed_at"):
                    st.write(f"完成时间：{t.get('completed_at')}")
                if t.get("logs"):
                    st.write("执行日志：")
                    for line in t["logs"]:
                        st.write(f"- {line}")