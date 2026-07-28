"""MVP smoke test: LangExtract -> DeepSeek (via OpenAI-compatible provider).

Per langextract/docs/LANGExtract_Specification.md section 3.4 method 2
(explicit ModelConfig) and 3.2 (OpenAI provider needs langextract[openai]).
DeepSeek exposes an OpenAI-compatible /chat/completions endpoint, so we
route through provider="openai" with base_url overridden.
"""

from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import langextract as lx
from langextract.core.data import ExampleData, Extraction
from langextract.factory import ModelConfig

ROOT = pathlib.Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

if not API_KEY:
    raise SystemExit("ERROR: DEEPSEEK_API_KEY not set in langextract_src/.env")

MOCK_TEXT = (
    "Patient John Carter was prescribed Metformin 500mg twice daily for "
    "type 2 diabetes. He was also given Lisinopril 10mg once daily in the "
    "morning for hypertension."
)

PROMPT_DESCRIPTION = (
    "Extract medications with their dosage, frequency, and the condition "
    "they treat. Use exact text from the source for extraction_text."
)

EXAMPLES = [
    ExampleData(
        text="Aspirin 100mg daily for hypertension.",
        extractions=[
            Extraction(
                extraction_class="medication",
                extraction_text="Aspirin",
                attributes={
                    "dosage": "100mg",
                    "frequency": "daily",
                    "indication": "hypertension",
                },
            ),
        ],
    ),
]

config = ModelConfig(
    model_id="deepseek-chat",
    provider="openai",
    provider_kwargs={"api_key": API_KEY, "base_url": BASE_URL},
)


def main() -> None:
    print("=" * 60)
    print("LangExtract MVP test -> DeepSeek (deepseek-chat)")
    print("=" * 60)
    print(f"Input text: {MOCK_TEXT}\n")

    result = lx.extract(
        text_or_documents=MOCK_TEXT,
        prompt_description=PROMPT_DESCRIPTION,
        examples=EXAMPLES,
        config=config,
        use_schema_constraints=False,  # DeepSeek: plain JSON mode, no strict json_schema
    )

    print(f"document_id: {result.document_id}")
    print(f"extractions found: {len(result.extractions)}\n")

    for i, ext in enumerate(result.extractions):
        print(f"  [{i}] class={ext.extraction_class!r} text={ext.extraction_text!r}")
        print(f"      char_interval={ext.char_interval}")
        print(f"      alignment_status={ext.alignment_status}")
        print(f"      attributes={ext.attributes}")

    if not result.extractions:
        print("  (no extractions returned)")

    # --- persist: JSONL + HTML visualization (io.py:85-141, visualization.py) ---
    output_dir = ROOT / "output"
    lx.io.save_annotated_documents(
        [result], output_dir=output_dir, output_name="extraction_results.jsonl"
    )
    jsonl_path = output_dir / "extraction_results.jsonl"
    print(f"\nSaved JSONL: {jsonl_path}")

    html = lx.visualize(str(jsonl_path))
    html_content = html.data if hasattr(html, "data") else html
    html_path = output_dir / "visualization.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"Saved HTML:  {html_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
