from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from app import ROOT, create_runtime
from common.tools import render_evidence

cli = typer.Typer(help="知命：第一周塔罗 Agent 原型。支持真实模型及 demo 离线演示。")
console = Console()


@cli.command()
def draw(
    question: Annotated[str, typer.Option("--question", "-q")],
    spread: str = "three_card",
    seed: int | None = None,
    user: str = "local",
    provider: str | None = None,
    model: str | None = None,
    json_output: bool = False,
    mode: Annotated[str | None, typer.Option(help="single 或 multi；默认读取 config.yaml")] = None,
    root: Annotated[Path | None, typer.Option(hidden=True)] = None,
):
    """完成一次抽牌、查释义、校验和保存。"""
    try:
        runtime = create_runtime(
            root=root or ROOT,
            user_id=user,
            provider=provider,
            model_name=model,
            seed=seed,
            spread=spread,
            mode=mode,
        )
    except (ValueError, FileNotFoundError, ImportError) as exc:
        console.print(f"启动失败：{exc}", markup=False)
        raise typer.Exit(1) from None
    try:

        async def run_once():
            try:
                return await runtime.turn(question)
            finally:
                await runtime.close_model()

        outcome = asyncio.run(run_once())
        if json_output:
            print(outcome.model_dump_json(indent=2))
        else:
            console.print(outcome.text, markup=False)
            if outcome.data.get("reading_id"):
                console.print(f"记录编号：{outcome.data['reading_id']}", markup=False)
        if outcome.status not in ("submit_reading", "ask_user", "text", "crisis_support"):
            raise typer.Exit(1)
    finally:
        runtime.close()


@cli.command()
def chat(
    user: str = "local",
    provider: str | None = None,
    model: str | None = None,
    seed: int | None = None,
    mode: Annotated[str | None, typer.Option(help="single 或 multi；默认读取 config.yaml")] = None,
):
    """多轮对话；支持 /profile、/evidence、/new、/redraw、/forget、/quit。"""
    try:
        runtime = create_runtime(
            user_id=user, provider=provider, model_name=model, seed=seed, mode=mode
        )
    except (ValueError, FileNotFoundError, ImportError) as exc:
        console.print(f"启动失败：{exc}", markup=False)
        raise typer.Exit(1) from None
    model_label = getattr(runtime.model, "model", "demo（离线规则演示）")
    console.print(f"知命 · 第一周塔罗原型。运行模型：{model_label}", markup=False)

    async def interact():
        while True:
            try:
                text = console.input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text == "/quit":
                break
            if text == "/profile":
                console.print(
                    json.dumps(runtime.store.get_profile(user), ensure_ascii=False), markup=False
                )
                continue
            if text == "/evidence":
                output = runtime.session.state.get("output")
                console.print(
                    render_evidence(output) if output else "当前还没有已提交的解读。",
                    markup=False,
                )
                continue
            if text == "/forget":
                runtime.forget()
                console.print(
                    "已删除当前用户的画像、记录、缓存及本应用 trace，并清空会话上下文。",
                    markup=False,
                )
                continue
            if text == "/new":
                runtime.session.state.clear()
                runtime.session.cache.clear()
                console.print("下一条问题将开始新占卜。", markup=False)
                continue
            if text == "/redraw":
                question = runtime.session.state.get("question")
                if not question:
                    console.print("还没有可重抽的问题。", markup=False)
                    continue
                text = f"请重新抽一次，原问题是：{question}"
            outcome = await runtime.turn(text)
            console.print(outcome.text, markup=False)

    try:

        async def run_chat():
            try:
                await interact()
            finally:
                await runtime.close_model()

        asyncio.run(run_chat())
    finally:
        runtime.close()


if __name__ == "__main__":
    cli()
