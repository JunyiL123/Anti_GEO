from __future__ import annotations

import json
from pathlib import Path

from anti_geo.audit.models import CitationRecord


def append_record(record: CitationRecord, log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{record.run_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_record_to_dict(record)) + "\n")
    return path


def load_records(log_path: Path) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    if not log_path.exists():
        return records
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        records.append(
            CitationRecord(
                run_id=row["run_id"],
                timestamp=row["timestamp"],
                engine=row["engine"],
                query=row["query"],
                paraphrase_of=row.get("paraphrase_of"),
                response_text=row.get("response_text", ""),
                cited_domains=row.get("cited_domains", []),
                cited_urls=row.get("cited_urls", []),
            )
        )
    return records


def _record_to_dict(record: CitationRecord) -> dict:
    return {
        "run_id": record.run_id,
        "timestamp": record.timestamp,
        "engine": record.engine,
        "query": record.query,
        "paraphrase_of": record.paraphrase_of,
        "response_text": record.response_text,
        "cited_domains": record.cited_domains,
        "cited_urls": record.cited_urls,
    }
