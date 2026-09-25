import json
import time

import pytest

from src.contracts import validate_search_results


METADATA = {
    "tt-40": {
        "source": "tt-40.md",
        "title": "Thông tư 40/2021/TT-BTC",
        "doc_type": "legal",
        "url": "https://congbao.example/tt40.pdf",
        "doc_number": "40/2021/TT-BTC",
    }
}


class FakeClient:
    """Giả lập PageIndexClient: retrieval 'processing' một lần rồi 'completed'."""

    def __init__(self, fail_upload=(), raise_on_query=False, hang=False):
        self.fail_upload = set(fail_upload)
        self.raise_on_query = raise_on_query
        self.hang = hang
        self.polls = 0
        self.uploaded = []

    def submit_document(self, file_path):
        name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
        if name in self.fail_upload:
            raise RuntimeError("upload failed")
        self.uploaded.append(name)
        return {"doc_id": f"pi-{name}"}

    def is_retrieval_ready(self, doc_id):
        return True

    def submit_query(self, doc_id, query):
        if self.raise_on_query:
            raise RuntimeError("api down")
        if self.hang:
            time.sleep(5)
        return {"retrieval_id": f"r-{doc_id}"}

    def get_retrieval(self, retrieval_id):
        self.polls += 1
        if self.polls == 1:
            return {"status": "processing"}
        return {
            "status": "completed",
            "retrieved_nodes": [
                # Cấu trúc response thật: khoá "id", relevant_contents lồng list, physical_index.
                {"id": "0004", "title": "Điều 4. Nguyên tắc tính thuế",
                 "relevant_contents": [[{"section_title": "Điều 4. Nguyên tắc tính thuế",
                                         "physical_index": "<physical_index_3>",
                                         "relevant_content": "Doanh thu từ 100 triệu đồng trở xuống..."}]]},
                # Dạng phẳng theo tài liệu cũ vẫn phải parse được.
                {"node_id": "0020", "title": "Phụ lục I",
                 "relevant_contents": [{"page_index": 40, "relevant_content": "Phân phối, cung cấp hàng hóa: 1%; 0,5%"}]},
                {"id": "0099", "title": "Node rỗng", "relevant_contents": [[]]},
            ],
        }


@pytest.fixture
def pageindex(monkeypatch, tmp_path):
    import src.task8_pageindex_vectorless as pageindex

    pdf_dir = tmp_path / "legal"
    pdf_dir.mkdir()
    (pdf_dir / "tt-40.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(pageindex, "PAGEINDEX_API_KEY", "test-key")
    monkeypatch.setattr(pageindex, "LEGAL_PDF_DIR", pdf_dir)
    monkeypatch.setattr(pageindex, "CACHE_FILE", tmp_path / "pageindex_doc_ids.json")
    monkeypatch.setattr(pageindex, "POLL_INTERVAL", 0)
    monkeypatch.setattr(pageindex, "_legal_metadata", lambda: METADATA)
    return pageindex


def test_upload_caches_doc_ids_and_skips_already_uploaded(pageindex, monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(pageindex, "_client", lambda: client)

    assert pageindex.upload_documents() == {"tt-40": "pi-tt-40.pdf"}
    assert json.loads(pageindex.CACHE_FILE.read_text(encoding="utf-8")) == {"tt-40": "pi-tt-40.pdf"}
    pageindex.upload_documents()
    assert client.uploaded == ["tt-40.pdf"]


def test_failed_upload_is_not_cached(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "_client", lambda: FakeClient(fail_upload={"tt-40.pdf"}))
    assert pageindex.upload_documents() == {}
    assert not pageindex.CACHE_FILE.exists()


def test_search_polls_until_completed_and_returns_contract_results(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "_client", lambda: FakeClient())
    output = pageindex.pageindex_search("doanh thu bao nhiêu thì không nộp thuế", top_k=5)

    validate_search_results(output, top_k=5, expected_method="pageindex")
    assert [item["id"] for item in output] == ["pageindex::tt-40::0004", "pageindex::tt-40::0020"]
    first = output[0]
    assert first["metadata"]["url"] == "https://congbao.example/tt40.pdf"
    assert first["metadata"]["article"] == "Điều 4. Nguyên tắc tính thuế"
    assert first["metadata"]["page"] == 3
    assert first["content"].startswith("Điều 4. Nguyên tắc tính thuế\n")


def test_search_respects_top_k(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "_client", lambda: FakeClient())
    assert len(pageindex.pageindex_search("thuế", top_k=1)) == 1


def test_search_returns_empty_on_api_error(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "_client", lambda: FakeClient(raise_on_query=True))
    assert pageindex.pageindex_search("thuế", top_k=3) == []


def test_search_returns_empty_when_provider_hangs(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "_client", lambda: FakeClient(hang=True))
    monkeypatch.setattr(pageindex, "SEARCH_TIMEOUT", 0.2)
    started = time.monotonic()
    assert pageindex.pageindex_search("thuế", top_k=3) == []
    assert time.monotonic() - started < 3


def test_search_without_api_key_returns_empty(pageindex, monkeypatch):
    monkeypatch.setattr(pageindex, "PAGEINDEX_API_KEY", "")
    assert pageindex.pageindex_search("thuế", top_k=3) == []
