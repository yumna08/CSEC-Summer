from app.core.tracing import tracer


def test_tracing_is_disabled_without_configuration():
    assert tracer.enabled is False
    with tracer.node("test.node") as metadata:
        metadata["latency_ms"] = 1.0
    tracer.record_model_call("generate", "test-model", 1.0)
    tracer.flush()
