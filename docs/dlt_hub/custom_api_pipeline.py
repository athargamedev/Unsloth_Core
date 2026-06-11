"""Custom API dlt pipeline.

Allows loading dynamic endpoints from any REST API into a local DuckDB warehouse.
"""

import argparse

import dlt
from dlt.hub import run
from dlt.sources.rest_api import rest_api_source


def build_rest_source(api_name: str, base_url: str, endpoint: str, primary_key: str = "id"):
    """Helper to construct a dynamic rest_api_source for the target endpoint."""
    # Ensure base_url has trailing slash if needed
    if not base_url.endswith("/"):
        base_url += "/"

    return rest_api_source(
        {
            "client": {
                "base_url": base_url,
            },
            "resources": [
                {
                    "name": endpoint,
                    "endpoint": endpoint,
                    "primary_key": primary_key,
                }
            ],
        }
    )


@run.pipeline("custom_api_pipeline")
def load_custom_api(
    api_name: str = "JSONPlaceholder",
    base_url: str = "https://jsonplaceholder.typicode.com/",
    endpoint: str = "posts",
    primary_key: str = "id",
):
    """Load custom API data into the DuckDB warehouse."""
    pipeline = dlt.pipeline(
        pipeline_name=f"{api_name.lower()}_pipeline",
        destination="warehouse",  # Resolves to DuckDB per config.toml
        dataset_name=api_name.lower(),
    )

    source = build_rest_source(api_name, base_url, endpoint, primary_key)
    load_info = pipeline.run(source)
    print(load_info)
    return load_info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a dynamic dlt pipeline to load any REST API into DuckDB."
    )
    parser.add_argument(
        "--api-name", default="JSONPlaceholder", help="Name of the API (e.g. JSONPlaceholder)"
    )
    parser.add_argument(
        "--base-url",
        default="https://jsonplaceholder.typicode.com/",
        help="Base URL of the REST API",
    )
    parser.add_argument(
        "--endpoint", default="posts", help="Endpoint/data path to load (e.g. posts)"
    )
    parser.add_argument("--primary-key", default="id", help="Primary key for deduplication")

    args = parser.parse_args()
    load_custom_api(
        api_name=args.api_name,
        base_url=args.base_url,
        endpoint=args.endpoint,
        primary_key=args.primary_key,
    )
