from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

OTLP_ENDPOINT = "https://otel.confident-ai.com"
CONFIDENT_API_KEY = "confident_us_org_PMRdgeaia9gkBQdnI8wbReG+tOatxXjodmK8AdYuNTg="

# Setup OpenTelemetry
if not isinstance(trace.get_tracer_provider(), TracerProvider):
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
else:
    tracer_provider = trace.get_tracer_provider()

exporter = OTLPSpanExporter(
    endpoint=f"{OTLP_ENDPOINT}/v1/traces",
    headers={"x-confident-api-key": CONFIDENT_API_KEY},
)

span_processor = BatchSpanProcessor(span_exporter=exporter)
tracer_provider.add_span_processor(span_processor)
tracer = trace.get_tracer("deepeval_tracer")

with tracer.start_as_current_span("confident-llm-span") as span:
    span.set_attribute("confident.trace.name", "example-trace")
    span.set_attribute("confident.span.type", "llm")
    span.set_attribute("confident.llm.model", "gpt-4o")
    span.set_attribute("confident.span.input", "What is the capital of France?")
    span.set_attribute("confident.span.output", "Paris")

print("Finished tracing, flushing...")
tracer_provider.force_flush()
print("Flushed!")
