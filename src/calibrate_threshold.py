"""
Hiệu chỉnh SCORE_THRESHOLD cho fallback của Task 9.

Chạy dense search cho câu hỏi trong domain (golden dataset) và ngoài domain,
lấy best cosine score gốc của mỗi câu, rồi chọn ngưỡng tách hai nhóm tốt nhất.
Kết quả lưu vào group_project/evaluation/threshold_calibration.json làm evidence.

    python -m src.calibrate_threshold
"""

import json
from pathlib import Path

from .task5_semantic_search import semantic_search


EVALUATION_DIR = Path(__file__).parent.parent / "group_project" / "evaluation"
GOLDEN_PATH = EVALUATION_DIR / "golden_dataset.json"
OUTPUT_PATH = EVALUATION_DIR / "threshold_calibration.json"

# Ngoài domain hẳn + sát domain nhưng ngoài phạm vi hộ kinh doanh.
OUT_OF_DOMAIN_QUERIES = [
    "Thủ tục ly hôn thuận tình gồm những bước nào?",
    "Giá vàng hôm nay là bao nhiêu?",
    "Cách nấu phở bò ngon tại nhà?",
    "Đội tuyển Việt Nam đá trận tiếp theo khi nào?",
    "Thủ tục thành lập công ty cổ phần cần bao nhiêu cổ đông?",
    "Thuế thu nhập doanh nghiệp của công ty TNHH là bao nhiêu phần trăm?",
]


def best_dense_score(query: str) -> float:
    results = semantic_search(query, top_k=1)
    return results[0]["score"] if results else 0.0


def choose_threshold(in_scores: list[float], out_scores: list[float]) -> tuple[float, float]:
    """Ngưỡng t (in >= t, out < t) có accuracy cao nhất; hoà thì lấy giữa khoảng trống."""
    candidates = sorted(set(in_scores + out_scores))
    best = (-1.0, 0.0)
    for low, high in zip([0.0] + candidates, candidates + [1.0]):
        threshold = (low + high) / 2
        correct = sum(s >= threshold for s in in_scores) + sum(s < threshold for s in out_scores)
        accuracy = correct / (len(in_scores) + len(out_scores))
        if accuracy > best[0]:
            best = (accuracy, threshold)
    return best[1], best[0]


def main() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    in_domain = [item["question"] for item in golden]
    if not in_domain:
        raise SystemExit("golden_dataset.json chưa có câu hỏi.")

    rows = [(q, "in", best_dense_score(q)) for q in in_domain]
    rows += [(q, "out", best_dense_score(q)) for q in OUT_OF_DOMAIN_QUERIES]
    in_scores = [score for _, group, score in rows if group == "in"]
    out_scores = [score for _, group, score in rows if group == "out"]
    threshold, accuracy = choose_threshold(in_scores, out_scores)

    for question, group, score in sorted(rows, key=lambda row: row[2], reverse=True):
        marker = "" if (score >= threshold) == (group == "in") else "  <-- sai phía"
        print(f"{score:.4f}  {group:<3}  {question[:70]}{marker}")
    print(f"\nin-domain  min/mean: {min(in_scores):.4f} / {sum(in_scores) / len(in_scores):.4f}")
    print(f"out-domain max/mean: {max(out_scores):.4f} / {sum(out_scores) / len(out_scores):.4f}")
    print(f"Đề xuất SCORE_THRESHOLD={threshold:.3f} (accuracy {accuracy:.0%})")

    OUTPUT_PATH.write_text(json.dumps({
        "threshold": round(threshold, 4),
        "accuracy": accuracy,
        "rows": [{"question": q, "group": g, "best_dense_score": s} for q, g, s in rows],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
