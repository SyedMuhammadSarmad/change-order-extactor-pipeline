import argparse
from pathlib import Path
from dotenv import load_dotenv
from .pipeline import ChangeOrderPipeline


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract Change Order PDF/Text to JSON")
    parser.add_argument("input_path", help="Path to input .pdf or .txt file")
    parser.add_argument("--provider", default="auto", help="'auto', 'gemini', or 'offline'")
    parser.add_argument("-o", "--output", help="Optional output JSON file path")
    args = parser.parse_args()

    pipeline = ChangeOrderPipeline(provider=args.provider)
    result = pipeline.extract_file(args.input_path)
    json_output = result.model_dump_json(indent=2)

    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"Saved validated JSON to {args.output} (confidence={result.overall_confidence})")
    else:
        print(json_output)


if __name__ == "__main__":
    main()