"""Backend-owned LLM provider adapters."""

from eurogas_nexus.llm.deepseek import (
    DEEPSEEK_DEFAULT_MODEL,
    DeepSeekCallResult,
    invoke_deepseek,
    test_deepseek_connection,
)

__all__ = [
    "DEEPSEEK_DEFAULT_MODEL",
    "DeepSeekCallResult",
    "invoke_deepseek",
    "test_deepseek_connection",
]
