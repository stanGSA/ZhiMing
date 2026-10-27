"""Actionable, sanitized failure outcomes shared by every divination system."""

from harness.models import TurnOutcome


def failure(session, status, reason, text, *, retryable=True):
    state = session.state
    kept = [facts.get("values", {}) for facts in state.get("specialist_facts", {}).values()]
    drawn = bool(
        state.get("tarot_drawn")
        or state.get("tarot_result")
        or any(f.get("tarot_result") for f in kept)
    )
    calculated = bool(
        state.get("calculations")
        or state.get("bazi_id")
        or state.get("chart_id")
        or any(f.get("calculations") or f.get("bazi_id") or f.get("chart_id") for f in kept)
    )
    retained = (
        "已有牌面和计算已保留。"
        if drawn and calculated
        else ("已有牌面已保留。" if drawn else "已有计算已保留。" if calculated else "")
    )
    return TurnOutcome(
        status=status,
        text=text + retained,
        data={
            "failure": {
                "reason": reason,
                "retryable": retryable,
                "retained_cards": drawn,
                "retained_calculations": calculated,
            }
        },
    )


def model_failure(session, exc):
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    if code in ("context_length_exceeded", "max_context_length_exceeded"):
        return failure(
            session,
            "model_error",
            "context_limit",
            "对话超过模型上下文容量；请开启新对话或缩小问题范围。",
            retryable=False,
        )
    if status in (401, 403):
        return failure(
            session,
            "model_error",
            "authorization",
            "模型服务认证失败，请检查所选服务的密钥和访问权限。",
            retryable=False,
        )
    if status == 429:
        return failure(
            session,
            "model_error",
            "rate_limit",
            "模型服务限流或额度不足；请稍后重试，或检查服务额度。",
        )
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
        return failure(session, "model_error", "provider_timeout", "模型服务响应超时，请稍后重试。")
    if status is not None and status >= 500:
        return failure(
            session, "model_error", "provider_unavailable", "模型服务暂时不可用，请稍后重试。"
        )
    return failure(
        session, "model_error", "model_call_failed", "模型调用失败，请检查模型配置和网络后重试。"
    )
