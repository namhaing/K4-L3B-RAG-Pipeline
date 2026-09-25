"""
A/B evaluation: Config A (dense-only) vs Config B (hybrid dense + BM25 + RRF).

Hai config dùng cùng golden dataset, generator, prompt, top_k và evaluator; chỉ khác
retrieval strategy (tham số use_reranking của _generate). Chấm bằng RAGAS 4 metric:
faithfulness, answer relevancy, context recall, context precision (có reference).

    python group_project/evaluation/run_eval.py                # chạy đủ hai config
    python group_project/evaluation/run_eval.py --limit 3      # thử nhanh 3 câu
    python group_project/evaluation/run_eval.py --skip-ragas   # chỉ generate + đo latency

Yêu cầu: đã index (python -m src.task4_chunking_indexing) và có OPENAI_API_KEY cho
evaluator. Output ghi cạnh file này:
    eval_results_A.json, eval_results_B.json  từng câu: answer, contexts, điểm, latency, token
    eval_results.csv                          gộp hai config, mỗi dòng một câu
    eval_summary.json                         trung bình metric, latency, token, run info
"""

import argparse
import asyncio
import csv
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import src.task10_generation as generation  # noqa: E402
from src.task4_chunking_indexing import (  # noqa: E402
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKING_METHOD,
    EMBEDDING_MODEL,
    get_collection,
)
from src.task9_retrieval_pipeline import SCORE_THRESHOLD  # noqa: E402


GOLDEN_PATH = EVALUATION_DIR / "golden_dataset.json"
CONFIGS = {
    "A": {"name": "dense-only", "use_reranking": False},
    "B": {"name": "hybrid + RRF", "use_reranking": True},
}
METRICS = ("faithfulness", "answer_relevancy", "context_recall", "context_precision")
EVAL_LLM_MODEL = os.getenv("EVAL_LLM_MODEL", "gpt-4o-mini")
EVAL_EMBEDDING_MODEL = os.getenv("EVAL_EMBEDDING_MODEL", "text-embedding-3-small")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().lower()


def context_hit(expected_context: str, contexts: list[str], probe_chars: int = 60) -> bool:
    """Chẩn đoán rẻ không cần LLM: đầu đoạn expected_context có nằm trong chunk nào không."""
    probe = _normalize(expected_context)[:probe_chars]
    return bool(probe) and any(probe in _normalize(context) for context in contexts)


def generate_rows(config: str, items: list[dict], top_k: int) -> list[dict]:
    use_reranking = CONFIGS[config]["use_reranking"]
    rows = []
    for index, item in enumerate(items, 1):
        usage_before = dict(generation.LLM_USAGE)
        started = time.perf_counter()
        result = generation._generate(item["question"], top_k=top_k, use_reranking=use_reranking)
        latency = time.perf_counter() - started

        # Khi LLM từ chối, sources rỗng nhưng "retrieved" vẫn giữ chunk đã truy xuất;
        # chấm context recall/precision trên đó để đo retrieval, không phạt oan.
        sources = result["sources"] or result.get("retrieved", [])
        contexts = [source["content"] for source in sources]
        row = {
            "id": index,
            "config": config,
            "question": item["question"],
            "expected_answer": item["expected_answer"],
            "expected_context": item["expected_context"],
            "answer": result["answer"],
            "contexts": contexts,
            "source_ids": [source["id"] for source in sources],
            "retrieval_source": result["retrieval_source"],
            "refused": result["retrieval_source"] == "none" or generation.REFUSAL_MESSAGE in result["answer"],
            "citations": generation.extract_citations(result["answer"]),
            "context_hit": context_hit(item["expected_context"], contexts),
            "latency_s": round(latency, 3),
            "input_tokens": generation.LLM_USAGE["input_tokens"] - usage_before["input_tokens"],
            "output_tokens": generation.LLM_USAGE["output_tokens"] - usage_before["output_tokens"],
        }
        rows.append(row)
        print(
            f"  [{config}] {index:>2}/{len(items)}  {latency:5.1f}s  "
            f"hit={'Y' if row['context_hit'] else 'N'}  {item['question'][:60]}",
            flush=True,
        )
    return rows


def build_metrics():
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms.base import llm_factory
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecisionWithReference,
        ContextRecall,
        Faithfulness,
    )

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    llm = llm_factory(EVAL_LLM_MODEL, client=client)
    embeddings = embedding_factory("openai", model=EVAL_EMBEDDING_MODEL, client=client)
    return {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_recall": ContextRecall(llm=llm),
        "context_precision": ContextPrecisionWithReference(llm=llm),
    }


async def _score_row(row: dict, metrics: dict, semaphore: asyncio.Semaphore) -> None:
    question, answer, contexts = row["question"], row["answer"], row["contexts"]
    reference = row["expected_answer"]
    calls = {"answer_relevancy": lambda: metrics["answer_relevancy"].ascore(
        user_input=question, response=answer)}
    if contexts:
        calls["faithfulness"] = lambda: metrics["faithfulness"].ascore(
            user_input=question, response=answer, retrieved_contexts=contexts)
        calls["context_recall"] = lambda: metrics["context_recall"].ascore(
            user_input=question, retrieved_contexts=contexts, reference=reference)
        calls["context_precision"] = lambda: metrics["context_precision"].ascore(
            user_input=question, reference=reference, retrieved_contexts=contexts)
    else:
        # Không có context (safe refusal): không có gì để trung thành; recall/precision = 0.
        row["faithfulness"] = None
        row["context_recall"] = 0.0
        row["context_precision"] = 0.0

    async def run(name, call):
        async with semaphore:
            try:
                value = (await call()).value
                row[name] = None if value is None or math.isnan(float(value)) else round(float(value), 4)
            except Exception as error:  # một metric lỗi không làm hỏng cả lượt chạy
                row[name] = None
                row.setdefault("metric_errors", {})[name] = f"{type(error).__name__}: {error}"[:300]

    await asyncio.gather(*(run(name, call) for name, call in calls.items()))


async def score_rows(rows: list[dict], concurrency: int) -> None:
    metrics = build_metrics()
    semaphore = asyncio.Semaphore(concurrency)
    await asyncio.gather(*(_score_row(row, metrics, semaphore) for row in rows))


def _mean(values: list) -> float | None:
    numbers = [value for value in values if value is not None]
    return round(statistics.fmean(numbers), 4) if numbers else None


def summarize(rows: list[dict]) -> dict:
    latencies = sorted(row["latency_s"] for row in rows)
    summary = {metric: _mean([row.get(metric) for row in rows]) for metric in METRICS}
    scored = [summary[metric] for metric in METRICS if summary[metric] is not None]
    summary["average"] = round(statistics.fmean(scored), 4) if scored else None
    summary.update({
        "questions": len(rows),
        "refusals": sum(row["refused"] for row in rows),
        "context_hit_rate": round(sum(row["context_hit"] for row in rows) / len(rows), 4),
        "latency_mean_s": round(statistics.fmean(latencies), 3),
        "latency_p50_s": round(statistics.median(latencies), 3),
        "latency_max_s": latencies[-1],
        "input_tokens_mean": round(statistics.fmean(row["input_tokens"] for row in rows), 1),
        "output_tokens_mean": round(statistics.fmean(row["output_tokens"] for row in rows), 1),
    })
    return summary


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def write_outputs(results: dict[str, list[dict]], summary: dict) -> None:
    for config, rows in results.items():
        path = EVALUATION_DIR / f"eval_results_{config}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = [
        "config", "id", "question", "faithfulness", "answer_relevancy", "context_recall",
        "context_precision", "context_hit", "refused", "retrieval_source", "citations",
        "latency_s", "input_tokens", "output_tokens", "source_ids", "answer",
    ]
    with (EVALUATION_DIR / "eval_results.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for rows in results.values():
            for row in rows:
                writer.writerow({
                    **row,
                    "citations": " ".join(map(str, row["citations"])),
                    "source_ids": " ".join(row["source_ids"]),
                })

    (EVALUATION_DIR / "eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def print_report(summary: dict) -> None:
    configs = summary["configs"]
    if "A" in configs and "B" in configs:
        print("\n| Metric | Config A | Config B | Delta B-A |\n|---|---:|---:|---:|")
        for metric in (*METRICS, "average", "context_hit_rate", "latency_mean_s"):
            a, b = configs["A"].get(metric), configs["B"].get(metric)
            delta = f"{b - a:+.4f}" if a is not None and b is not None else "N/A"
            print(f"| {metric} | {a if a is not None else 'N/A'} | {b if b is not None else 'N/A'} | {delta} |")

    worst = sorted(
        (row for rows in summary.pop("_rows").values() for row in rows),
        key=lambda row: statistics.fmean([row.get(m) or 0.0 for m in METRICS]),
    )[:5]
    print("\nWorst performers (điểm trung bình 4 metric thấp nhất):")
    for row in worst:
        scores = " ".join(f"{m[:5]}={row.get(m)}" for m in METRICS)
        print(f"  [{row['config']}] #{row['id']} hit={row['context_hit']} {scores}  {row['question'][:70]}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--configs", nargs="+", choices=sorted(CONFIGS), default=sorted(CONFIGS))
    parser.add_argument("--top-k", type=int, default=generation.TOP_K)
    parser.add_argument("--limit", type=int, help="chỉ chạy N câu đầu để thử nhanh")
    parser.add_argument("--concurrency", type=int, default=4, help="số lời gọi RAGAS song song")
    parser.add_argument("--skip-ragas", action="store_true", help="chỉ generate và đo latency")
    args = parser.parse_args()

    items = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))[: args.limit]
    if get_collection().count() == 0:
        raise SystemExit("ChromaDB trống. Chạy trước: python -m src.task4_chunking_indexing")
    if not args.skip_ragas and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("RAGAS evaluator cần OPENAI_API_KEY trong .env (hoặc chạy với --skip-ragas).")

    results = {}
    for config in args.configs:
        print(f"\nGenerate Config {config} ({CONFIGS[config]['name']}), {len(items)} câu, top_k={args.top_k}")
        results[config] = generate_rows(config, items, args.top_k)
        if not args.skip_ragas:
            print(f"Chấm RAGAS Config {config} ...", flush=True)
            asyncio.run(score_rows(results[config], args.concurrency))

    summary = {
        "run": {
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": _git_commit(),
            "golden_dataset_size": len(items),
            "top_k": args.top_k,
            "generator": f"{generation.LLM_PROVIDER}/{generation.LLM_MODEL or generation.DEFAULT_MODELS[generation.LLM_PROVIDER]}",
            "evaluator": None if args.skip_ragas else f"RAGAS {_ragas_version()} / {EVAL_LLM_MODEL} + {EVAL_EMBEDDING_MODEL}",
            "embedding_model": EMBEDDING_MODEL,
            "chunking": f"{CHUNKING_METHOD}, size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}",
            "score_threshold": SCORE_THRESHOLD,
        },
        "configs": {config: {"name": CONFIGS[config]["name"], **summarize(rows)} for config, rows in results.items()},
    }
    write_outputs(results, summary)
    summary["_rows"] = results
    print_report(summary)
    print(f"\nĐã lưu kết quả vào {EVALUATION_DIR}")


def _ragas_version() -> str:
    try:
        import ragas

        return ragas.__version__
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
