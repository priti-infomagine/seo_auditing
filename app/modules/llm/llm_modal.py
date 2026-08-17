"""


Reads all models from the output directory, prepares training
data as SEO audit examples with TEXT-based output (not JSON), creates an
Ollama Modelfile, and builds a custom fine-tuned model that audits meta
titles and descriptions.

The model is saved in Ollama's registry with a domain-based name.
The Modelfile and training data are saved in the project folder for evaluation.

Usage:
   
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from seo_prompts import MODELFILE_SYSTEM_PROMPT
from seo_rules import (
    ELEMENT_LABELS,
    audit_page,
    rules_to_prompt_text,
    rules_version,
)


SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

#url xtacted
def get_domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    domain = domain.replace("www.", "").replace(".", "_").replace("-", "_")
    return domain.lower()


def get_primary_domain_from_meta_files(output_dir: Path) -> str:
    """Get the primary domain from the most recently crawled meta_data.json.

    Uses the latest-modified file so the built model name lines up with the
    crawl that seo_agent.py loads by default (also the latest), keeping a
    site's data and its model aligned.
    """
    meta_files = sorted(
        output_dir.glob("*_meta_data.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not meta_files:
        return "seo_meta"

    latest_file = meta_files[0]
    domain_part = latest_file.name.replace("_meta_data.json", "")
    return domain_part


def _group_issues_by_element(issues: list[dict]) -> dict[str, list[dict]]:
    """Bucket audited issues by the page element they belong to."""
    grouped: dict[str, list[dict]] = {}
    for iss in issues:
        grouped.setdefault(iss["element"], []).append(iss)
    return grouped


def page_to_audit_example(page: dict) -> dict | None:
    """Convert a crawled page into an audit training example driven by SEO_RULES.

    Every issue is produced by seo_rules.audit_page (the single source of
    truth), so the example always reflects the CURRENT SEO rules. Adding a rule
    to seo_rules.py automatically appears in newly trained examples.
    """
    url = page.get("final_url") or page.get("url", "")

    if not url:
        return None

    issues = audit_page(page)
    grouped = _group_issues_by_element(issues)

    input_text = f"URL: {url}"
    for element in ELEMENT_LABELS:
        text = page.get(element, "") or ""
        input_text += f"\n{ELEMENT_LABELS[element]}: {text}"

    output_lines = []
    for element in ELEMENT_LABELS:
        label = ELEMENT_LABELS[element]
        elem_issues = grouped.get(element, [])
        if not elem_issues:
            output_lines.append(f"{label}: PASS - The {label.lower()} follows SEO best practices.")
        else:
            worst = min(elem_issues, key=lambda i: SEVERITY_RANK.get(i["severity"], 3))
            output_lines.append(f"{label}: {worst['severity'].upper()}")
            for iss in elem_issues:
                output_lines.append(f"- {iss['message']}")
            output_lines.append(f"Recommendation: Improve the {label.lower()} to follow SEO best practices.")

    output_text = "\n".join(output_lines)

    return {
        "messages": [
            {
                "role": "user",
                "content": f"Analyze the following page for SEO issues using the active SEO rules.\n\n{input_text}"
            },
            {
                "role": "assistant",
                "content": output_text
            }
        ]
    }


def get_latest_meta_file(output_dir: Path) -> Path | None:
    """Most recently modified *_meta_data.json (the crawl seo_agent.py loads)."""
    meta_files = sorted(
        output_dir.glob("*_meta_data.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return meta_files[0] if meta_files else None


def prepare_training_data(output_dir: Path, combined: bool = False) -> list[dict]:
    """Create audit examples from crawl data.

    By default (combined=False) this uses only the LATEST crawl, so each built
    model stays specific to the site named in its model tag.

    With combined=True it reads EVERY *_meta_data.json in the output dir and
    builds ONE model covering all crawled sites. Examples are de-duplicated by
    (url, title, description, h1, canonical) so the same page across runs is not
    repeated, and pages are shuffled into a stable order so no single site
    dominates the fine-tune.
    """
    meta_files = sorted(
        output_dir.glob("*_meta_data.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not meta_files:
        print(f"No *_meta_data.json files found in '{output_dir}'.")
        sys.exit(1)

    if combined:
        files_to_use = meta_files
        print(f"Combined training from ALL {len(files_to_use)} crawl files:")
        for mf in files_to_use:
            print(f"  - {mf.name}")
    else:
        files_to_use = [meta_files[0]]
        print(f"Training from latest crawl: {files_to_use[0].name}")

    training_examples = []
    seen: set[tuple] = set()
    for mf in files_to_use:
        try:
            with open(mf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {mf}: {e}")
            continue
        for page in data.get("pages", []):
            key = (
                page.get("final_url") or page.get("url", ""),
                page.get("meta_title", ""),
                page.get("meta_description", ""),
                page.get("h1", ""),
                page.get("canonical", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            example = page_to_audit_example(page)
            if example:
                training_examples.append(example)

    if not training_examples:
        print("No valid training examples found.")
        sys.exit(1)

    # Stable shuffle so combined training isn't ordered site-by-site (which
    # would bias the model toward the first file's site).
    ordered = sorted(training_examples, key=lambda ex: ex["messages"][0]["content"])
    return ordered


def create_modelfile(examples: list[dict], base_model: str = "llama3.2:3b", domain_name: str = "seo_meta") -> str:
    """Create an Ollama Modelfile with audit training examples.

    Uses the baked MASTER prompt (data sections removed), so there is a single
    source of truth with seo_agent.py.

    NOTE: Ollama Modelfile directives that carry multi-line content (SYSTEM,
    MESSAGE) MUST be wrapped in triple quotes, otherwise the parser only reads
    the first line and the rest of the prompt is silently discarded.
    """
    system_prompt = MODELFILE_SYSTEM_PROMPT + "\n\n" + rules_to_prompt_text()

    lines = [
        f"FROM {base_model}",
        "",
        "PARAMETER temperature 0.7",
        "PARAMETER num_ctx 8192",
        "",
        'SYSTEM """',
        system_prompt.rstrip("\n"),
        '"""',
    ]

    # A small, representative set of few-shot examples is enough for the model
    # to learn the output format. A combined (multi-site) model samples a spread
    # of pages across sites; keeping this small also keeps the fine-tune light
    # and the resulting model fast to run. We pick evenly spaced examples so no
    # single site dominates the shown shots.
    if len(examples) <= 12:
        shot_examples = examples
    else:
        step = len(examples) / 12
        shot_examples = [examples[int(i * step)] for i in range(12)]
    for example in shot_examples:
        messages = example.get("messages", [])
        if len(messages) < 2:
            continue
        user_msg = messages[0].get("content", "")
        assistant_msg = messages[1].get("content", "")
        if not user_msg.strip() or not assistant_msg.strip():
            continue
        lines.append("")
        lines.append('MESSAGE user """')
        lines.append(user_msg.rstrip("\n"))
        lines.append('"""')
        lines.append('MESSAGE assistant """')
        lines.append(assistant_msg.rstrip("\n"))
        lines.append('"""')

    return "\n".join(lines) + "\n"


def check_ollama_available() -> None:
    """Verify the ollama CLI exists and a server is reachable."""
    try:
        probe = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print("Error: the 'ollama' CLI is not installed or not on PATH.")
        print("Install it from https://ollama.com and run 'ollama serve' first.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: 'ollama list' timed out - is the Ollama server running?")
        print("Start it with: ollama serve")
        sys.exit(1)

    if probe.returncode != 0:
        print("Error: could not reach the Ollama server. Is 'ollama serve' running?")
        print(probe.stderr.strip() or "(no error message captured)")
        sys.exit(1)


def ensure_base_model(base_model: str) -> None:
    """Pull the base model if it is not already present."""
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if base_model not in result.stdout:
        print(f"Base model '{base_model}' not found locally. Pulling it now...")
        pull = subprocess.run(["ollama", "pull", base_model], capture_output=True, text=True)
        if pull.returncode != 0:
            print(f"Error: failed to pull base model '{base_model}':")
            print(pull.stderr.strip() or "(no error message captured)")
            sys.exit(1)
        print(f"Pulled '{base_model}'.")


def build_ollama_model(model_name: str, modelfile_path: Path) -> None:
    """Build the Ollama model using the Modelfile."""
    print(f"Building Ollama model '{model_name}'...")
    print("This may take a few minutes...")

    result = subprocess.run(
        ["ollama", "create", model_name, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error creating model: {result.stderr.strip() or '(no error message captured)'}")
        sys.exit(1)

    # Verify the model now appears in `ollama list`.
    verify = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if model_name.split(":")[0] not in verify.stdout:
        print(f"Warning: model '{model_name}' was created but does not appear in 'ollama list'.")
    else:
        print(f"Successfully created and registered model: {model_name}")
        print(f"\nTest it with: ollama run {model_name}")


COMBINED_MODEL_NAME = "seo-auditor-combined"


def main(argv: list[str] | None = None):
    # First CLI arg may be --combined; remaining positional args follow.
    args = list(argv) if argv is not None else sys.argv[1:]
    combined = "--combined" in args
    args = [a for a in args if a != "--combined"]

    output_dir = Path(args[0]) if args else Path("output")
    custom_model_name = args[1] if len(args) > 1 else None

    if not output_dir.exists():
        print(f"Error: Output directory '{output_dir}' does not exist.")
        sys.exit(1)

    check_ollama_available()

    if combined:
        # One model covering every crawled site.
        model_name = custom_model_name or COMBINED_MODEL_NAME
    else:
        domain_name = get_primary_domain_from_meta_files(output_dir)
        model_name = custom_model_name or f"seo-auditor-{domain_name}"

    print(f"Preparing training data from {output_dir}...")
    examples = prepare_training_data(output_dir, combined=combined)
    print(f"Loaded {len(examples)} training examples.")

    rule_ver = rules_version()
    print(f"Active SEO rules version: {rule_ver}")

    base_model = "llama3.2:3b"
    ensure_base_model(base_model)

    print(f"Creating Modelfile for model: {model_name}...")
    modelfile_content = create_modelfile(examples, base_model=base_model)

    # The Modelfile name carries the rules version, so a NEW rule set (new
    # rules_version) produces a NEW model file instead of silently overwriting
    # the previous one. The Ollama model name stays stable so seo_agent.py's
    # auto-detection (expected_model_for_crawl) keeps working unchanged.
    modelfile_path = output_dir / f"{model_name}_Modelfile_r{rule_ver}"
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)
    print(f"Modelfile saved to: {modelfile_path}")

    build_ollama_model(model_name, modelfile_path)

    print(f"\n{'='*60}")
    print(f"Model training complete!")
    print(f"Model name: {model_name}")
    print(f"Modelfile: {modelfile_path}")
    print(f"{'='*60}")
    print(f"\nTo test the model:")
    print(f"  ollama run {model_name}")
    print(f"\nExample prompt:")
    print(f"  Analyze the following Meta Title and Meta Description for SEO issues.")
    print(f"  URL: https://example.com/about")
    print(f"  Meta Title: About Us - Example Company")
    print(f"  Meta Description: This is a short description.")


def main_args(argv: list[str]) -> None:
    """Entry point callable from other scripts (e.g. run_agent.py) without
    touching the global sys.argv."""
    main(argv)


if __name__ == "__main__":
    main()
