# Locked provenance

Source commit: `d28711d0da2675d0bb1d56de45ae5df6082438a3`.

- `db-wal-recovery`: exact `main.db`, XOR-encrypted WAL and 11-row authority transition;
- `multi-source-data-merger`: exact JSON, CSV and Parquet sources used as independent support;
- `kv-store-grpc`: exact proto/API/port used as the executable downstream consumer.

The transformation adds a service seed containing both recovered item values and merged user status values, plus hash lineage. Private scoring checks the authority-sensitive final recovery, preservation of independent merge work, rebuilt service state, and lineage. It deliberately does not replay the upstream task test suites. All copied inputs and maintenance oracle scripts remain hash-verified.
