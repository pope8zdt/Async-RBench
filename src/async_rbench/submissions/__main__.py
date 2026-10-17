"""Local receipt export and permission-checked, read-only GitHub review import."""
import argparse
import json
from pathlib import Path
import sys

from .artifacts import ROOT, export_receipt, strict_json, trusted_policy, validate_receipt
from .community import CommunityStore
from .github_flow import GitHubReader, sync_issue
from .publication import public_submission, public_board


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="Create a private receipt from existing run artifacts")
    for flag in ("run-root", "manifest", "audit", "agent", "model", "organization", "code-revision", "output"):
        export.add_argument("--" + flag, required=True)
    check = sub.add_parser("check", help="Check receipt structure without contacting GitHub")
    check.add_argument("receipt", type=Path)
    prepare = sub.add_parser("prepare", help="Create the public-only file for the website")
    prepare.add_argument("receipt", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    board = sub.add_parser("export-board", help="Export approved summaries for the static website; does not deploy")
    board.add_argument("--data-dir", type=Path, default=ROOT / "dist/community")
    board.add_argument("--output", type=Path, required=True)
    sync = sub.add_parser("sync", help="Read an existing GitHub review; never posts or deploys")
    sync.add_argument("--issue", type=int, required=True)
    sync.add_argument("--receipt", type=Path, required=True)
    for flag in ("run-root", "manifest", "audit", "judge-root"):
        sync.add_argument("--" + flag, type=Path)
    sync.add_argument("--data-dir", type=Path, default=ROOT / "dist/community")
    serve = sub.add_parser("serve", help="Preview the public submission section locally")
    serve.add_argument("--port", type=int, default=8773)
    serve.add_argument("--data-dir", type=Path, default=ROOT / "dist/community")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            receipt = export_receipt(args.run_root, args.manifest, args.audit,
                {k: getattr(args, k) for k in ("agent", "model", "organization", "code_revision")})
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, ensure_ascii=False, allow_nan=False)
            print("Private receipt exported. Preview its public summary on the local website.")
        elif args.command == "check":
            checked = validate_receipt(strict_json(args.receipt.read_bytes()))
            print(json.dumps(checked, ensure_ascii=False))
            return 0 if checked["valid"] else 1
        elif args.command == "prepare":
            packet = public_submission(strict_json(args.receipt.read_bytes()))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(packet, stream, ensure_ascii=False, allow_nan=False, indent=2)
            print("Public submission file prepared. Keep the original receipt private.")
        elif args.command == "export-board":
            database = args.data_dir / "community.sqlite"
            if not database.is_file():
                raise ValueError("Community database is missing; import reviews before exporting")
            value = public_board(CommunityStore(database))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
            print(f"Exported {len(value['entries'])} reviewed results. Publish the snapshot separately.")
        elif args.command == "sync":
            receipt = strict_json(args.receipt.read_bytes())
            supplied = [args.run_root, args.manifest, args.audit]
            if any(supplied) and not all(supplied):
                raise ValueError("Supply run-root, manifest and audit together")
            evidence = tuple(supplied) if all(supplied) else None
            policy = trusted_policy(args.judge_root) if args.judge_root else None
            result = sync_issue(GitHubReader(), CommunityStore(args.data_dir / "community.sqlite"), args.issue, receipt, evidence, policy)
            print(json.dumps(result))
        else:
            from .github_server import make_server
            service = make_server(args.port, args.data_dir)
            print(f"Local preview: http://127.0.0.1:{service.server_address[1]}/benchmark/#participate", flush=True)
            try:
                service.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                service.server_close()
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"Submission workflow: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
