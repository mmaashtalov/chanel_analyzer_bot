from app.evidence.corroboration import DocumentSignal, assess_claim_corroboration


def doc(eid: str, source: str, source_type: str, url: str, text: str, content_hash: str) -> DocumentSignal:
    return DocumentSignal(eid, source, source_type, url, content_hash, content_hash, text)


def test_identical_documents_form_one_cluster() -> None:
    result = assess_claim_corroboration("c1", (
        doc("e1", "s1", "telegram", "https://t.me/a/1", "Ростех начал испытания БПЛА", "same"),
        doc("e2", "s2", "rss", "https://example.org/a", "Ростех начал испытания БПЛА", "same"),
    ))
    assert result.independent_cluster_count == 1
    assert result.independence_score == 0.5
    assert "Нет двух независимо подтверждающих кластеров." in result.caveats


def test_distinct_sources_form_independent_clusters() -> None:
    result = assess_claim_corroboration("c2", (
        doc("e1", "s1", "telegram", "https://t.me/a/1", "Ростех сообщил об испытаниях", "h1"),
        doc("e2", "s2", "rss", "https://news.example.org/b", "ОАК опубликовала данные производства", "h2"),
    ))
    assert result.independent_cluster_count == 2
    assert result.independence_score == 1.0
    assert result.corroboration_score > 0.65


def test_same_domain_is_not_independent() -> None:
    result = assess_claim_corroboration("c3", (
        doc("e1", "s1", "rss", "https://example.org/a", "Первая заметка", "h1"),
        doc("e2", "s2", "web", "https://example.org/b", "Другая заметка", "h2"),
    ))
    assert result.independent_cluster_count == 1
    assert result.clusters[0].reason == "same_upstream_domain"


def test_no_documents_has_zero_scores() -> None:
    result = assess_claim_corroboration("c4", ())
    assert result.independence_score == 0.0
    assert result.corroboration_score == 0.0
    assert result.document_count == 0
