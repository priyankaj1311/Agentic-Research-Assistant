from __future__ import annotations

"""
Agentic Research Assistant — entry point.

Usage:
    python main.py "Your complex research question here"
    python main.py --query "How is generative AI changing customer service in banking?"
    python main.py --output report.md "What are the major risks of LLMs in finance?"
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from app.utils.logging import get_logger
from app.workflow.research_workflow import ResearchWorkflow

logger = get_logger(__name__)


async def run_research(query: str, output_path: str | None = None) -> str:
    """Execute the full research pipeline and return the final Markdown report."""
    start = time.monotonic()

    workflow = ResearchWorkflow(
        timeout=600,  # 10-minute hard timeout
    )

    logger.info("Starting research", query=query[:120])

    try:
        report: str = await workflow.run(user_query=query)
    except Exception as exc:
        logger.error("Research workflow failed", error=str(exc))
        raise

    elapsed = time.monotonic() - start
    logger.info("Research complete", elapsed_secs=round(elapsed, 1))

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Report saved", path=output_path)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Research Assistant — autonomous multi-step research with citations"
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Research question (can also be passed via --query)",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Research question",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Save the final report to this file path (Markdown)",
    )
    args = parser.parse_args()

    query = args.query or args.question
    if not query:
        parser.print_help()
        sys.exit(1)

    report = asyncio.run(run_research(query.strip(), output_path=args.output))

    # Print to stdout if no output file specified
    if not args.output:
        print("\n" + "=" * 80)
        print(report)
        print("=" * 80 + "\n")
    else:
        print(f"\nReport saved to: {args.output}\n")


if __name__ == "__main__":
    main()
