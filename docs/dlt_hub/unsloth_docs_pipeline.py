"""Unsloth_Core Documentation Pipeline.

Loads all project documentation markdown files into DuckDB for querying.
Each .md file becomes a row with path, section, title, content, and metadata.
"""

from pathlib import Path

import dlt

DOCS_ROOT = Path(__file__).resolve().parent.parent  # ../docs/


@dlt.resource(table_name="documents", write_disposition="replace", primary_key="path")
def unsloth_docs():
    """Yield each markdown file as a document row."""
    for md_file in sorted(DOCS_ROOT.rglob("*.md")):
        relative = md_file.relative_to(DOCS_ROOT)
        parts = relative.parts
        content = md_file.read_text(encoding="utf-8")
        yield {
            "path": str(relative),
            "section": parts[0] if len(parts) > 1 else "root",
            "filename": md_file.name,
            "title": _extract_title(content) or md_file.stem,
            "size_bytes": md_file.stat().st_size,
            "line_count": len(content.splitlines()),
            "content": content,
        }


def _extract_title(content: str) -> str | None:
    """Extract first H1 heading from markdown content."""
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


@dlt.source
def unsloth_docs_source():
    """Source wrapping the unsloth_docs resource."""
    return unsloth_docs()


def load_unsloth_docs():
    """Entry point for __deployment__.py."""
    pipeline = dlt.pipeline(
        pipeline_name="unsloth_docs_pipeline",
        destination="warehouse",
        dataset_name="unsloth_docs",
    )
    load_info = pipeline.run(unsloth_docs_source())
    print(f"Load info: {load_info}")

    dataset = pipeline.dataset()
    docs_table = dataset.documents
    df = docs_table.df()
    total = len(df)
    print(f"\nTotal documents loaded: {total}")
    print(f"Sections: {df['section'].value_counts().to_dict()}")
    return load_info


if __name__ == "__main__":
    load_unsloth_docs()
