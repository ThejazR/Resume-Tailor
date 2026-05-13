"""CLI orchestrator: tailor resume to a JD and send via MCP email server.

Usage:
    python -m src.main --jd path/to/jd.txt
    cat jd.txt | python -m src.main --jd-stdin
    python -m src.main --jd jd.txt --yes        # skip confirm prompt
"""
import argparse
import sys

from src import customizer, email_extractor, guardrail, mcp_client, pdf_writer, rag


def _read_jd(args: argparse.Namespace) -> str:
    if args.jd_stdin:
        return sys.stdin.read().strip()
    if args.jd:
        with open(args.jd, "r", encoding="utf-8") as f:
            return f.read().strip()
    raise SystemExit("Provide --jd <file>, --jd-stdin, or run with no args for interactive mode.")


def _read_jd_interactive() -> str | None:
    """Prompt user to paste a JD. Returns None if they want to quit."""
    print()
    print("Paste a JOB DESCRIPTION below.")
    print("  - Finish by typing 'END' on its own line and pressing Enter.")
    print("  - Type 'exit' or 'quit' on its own line to leave the tool.")
    print()
    lines: list[str] = []
    while True:
        try:
            line = input("> " if not lines else "")
        except EOFError:
            break
        stripped = line.strip().lower()
        if stripped in {"exit", "quit"}:
            return None
        if stripped == "end":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _preview(recipient: str, subject: str, resume_text: str, pdf_path, body: str) -> None:
    print("\n" + "=" * 72)
    print(f"To:       {recipient}")
    print(f"Subject:  {subject}")
    print(f"Attach:   {pdf_path}")
    print("-" * 72)
    print("Email body preview:")
    print(body)
    print("-" * 72)
    print("Tailored resume preview (first 30 lines):")
    for line in resume_text.splitlines()[:30]:
        print(f"  {line}")
    print("=" * 72)


def _run_once(jd_text: str, auto_yes: bool) -> None:
    print("[1/6] Validating input is a job description...")
    try:
        guardrail.assert_job_description(jd_text)
    except guardrail.NotAJobDescription as e:
        print(f"REJECTED: {e}")
        return

    print("[2/6] Extracting recipient + company from JD...")
    try:
        recipient, company = email_extractor.extract_recipient(jd_text)
    except email_extractor.NoRecipientFound as e:
        print(f"ABORT: {e}")
        return
    print(f"      recipient={recipient}  company={company or '?'}")

    print("[3/6] Retrieving relevant resume chunks from Qdrant...")
    chunks = rag.retrieve(jd_text, k=8)
    if not chunks:
        print("ABORT: no resume chunks returned. Run `python -m src.ingest` first.")
        return

    print("[4/6] Tailoring resume with phi4-mini...")
    resume_text = customizer.tailor(chunks, jd_text)

    print("[5/6] Composing email body with phi4-mini...")
    subject, body = customizer.compose_email_body(jd_text, company)

    pdf_path = pdf_writer.render(resume_text, company)
    print(f"      wrote {pdf_path}")

    _preview(recipient, subject, resume_text, pdf_path, body)

    if not auto_yes:
        confirm = input("Send this email? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Not sent. Tailored resume kept at:", pdf_path)
            return

    print("[6/6] Sending via MCP email server...")
    result = mcp_client.send_via_mcp(recipient, subject, body, str(pdf_path))
    print(f"      {result}")


def _interactive_loop(auto_yes: bool) -> None:
    print("=" * 72)
    print("Resume Tailoring Tool — interactive mode")
    print("This tool ONLY tailors your resume to job descriptions.")
    print("Any other request will be refused.")
    print("=" * 72)
    while True:
        jd_text = _read_jd_interactive()
        if jd_text is None:
            print("Goodbye.")
            return
        if not jd_text:
            print("(empty input — try again)")
            continue
        try:
            _run_once(jd_text, auto_yes)
        except KeyboardInterrupt:
            print("\n(interrupted)")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tailor your resume to a job description and email it."
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--jd", help="Path to job description text file.")
    src.add_argument("--jd-stdin", action="store_true", help="Read JD from stdin.")
    parser.add_argument(
        "--yes", action="store_true", help="Skip the confirm-before-send prompt."
    )
    args = parser.parse_args()

    if not args.jd and not args.jd_stdin:
        _interactive_loop(args.yes)
        return

    jd_text = _read_jd(args)
    try:
        _run_once(jd_text, args.yes)
    except guardrail.NotAJobDescription as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
