import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv
from .pipeline import ChangeOrderPipeline


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract Change Order PDF/Text to JSON")
    parser.add_argument("input_path", help="Path to input .pdf or .txt file")
    parser.add_argument(
        "--provider",
        choices=["auto", "gemini", "offline"],
        default=None,
        help="Directly select 'auto', 'gemini', or 'offline'",
    )
    parser.add_argument("-o", "--output", help="Optional output JSON file path")
    args = parser.parse_args()

    provider = args.provider
    if provider is None and sys.stdin.isatty():
        print("\nSelect extraction provider:", file=sys.stderr)
        print("  [1] Gemini API (Multimodal LLM)", file=sys.stderr)
        print("  [2] Offline Hybrid (Local Regex + Heuristics)", file=sys.stderr)
        choice = input("Enter choice [1/2] (press Enter for auto): ").strip()
        if choice == "1":
            provider = "gemini"
        elif choice == "2":
            provider = "offline"
        else:
            provider = "auto"
    elif provider is None:
        provider = "auto"

    pipeline = ChangeOrderPipeline(provider=provider)
    result = pipeline.extract_file(args.input_path)
    json_output = result.model_dump_json(indent=2)

    input_stem = Path(args.input_path).stem
    output_path = Path(args.output) if args.output else Path("outputs") / f"{input_stem}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_output, encoding="utf-8")

    print(json_output)
    print(
        f"\nSaved validated JSON to {output_path} "
        f"(provider={result.provider_used}, confidence={result.overall_confidence})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()