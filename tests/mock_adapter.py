"""Protocol-3 deterministic adapter entrypoint used only for conformance."""

from async_rbench.profiles.conformance_mock.adapter import main


if __name__ == "__main__":
    raise SystemExit(main())
