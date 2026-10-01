"""Synthetic RC5 paired regressions; no live research or legal-quality claims."""
from copy import deepcopy

import pytest

from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.research import ResearchDepth, ResearchObligationKind as Kind
from alr_tw.contracts.sources import EvidenceSpan, TrustStatus
from alr_tw.research.draft_workspace import review_draft
from alr_tw.research.service import _plan_obligations
from alr_tw.verification.claim_support import SectionRole, SupportStatus, _qualifier_omitted
from test_v014_drafting import draft
from test_v061_deterministic_grounding import _check
from test_v070_civil_analysis import _ready_service
from test_v1_rc4_citations import judgment
from alr_tw.research.citation_identity import judgment_name_equivalent


def two_citations(tmp_path, *, adjacent=False, same_binding=False):
    service, run_id, span, now = _ready_service(tmp_path)
    source = service.store.get_source(span.source_id)
    text = '受領人違反示範程序時，應負合成程序責任'
    other_source = source.model_copy(update={
        'source_id': 'synthetic-procedure-source', 'source_key': 'law:synthetic-procedure',
        'citation': '示範程序法第2條', 'normalized_text': text,
        'content_hash': EvidenceSpan.hash_text(text),
        'normalized_content_hash': EvidenceSpan.hash_text(text),
    })
    other_span = EvidenceSpan.from_exact_text(evidence_id='synthetic-procedure-evidence',
        source_id=other_source.source_id, section_id='article-2', section_type='law_text',
        exact_text=text, eligible_for_claim_support=True)
    service.store.save_source(run_id, other_source)
    service.store.save_evidence(run_id, other_span)
    run = service._run_with_server_refs(service.get_run(run_id))
    service.store.save_run(run)
    service._sync_snapshot_receipts(run, now=now)
    answer, bindings = draft(span.evidence_id)
    if same_binding:
        answer = answer[:-1] + '（示範程序法第2條）。'
        bindings[0]['evidence_ids'].append(other_span.evidence_id)
        bindings[0]['citation_occurrences'].append({'evidence_id': other_span.evidence_id,
            'citation_text': other_source.citation, 'start_offset': 0, 'end_offset': 1})
    else:
        answer += text + '（示範程序法第2條）。'
        bindings.append({'claim_id': 'claim-procedure', 'claim_text': text,
            'claim_type': 'law_rule', 'evidence_ids': [other_span.evidence_id],
            'issue_ids': ['issue-duty'], 'citation_occurrences': [{
                'evidence_id': other_span.evidence_id, 'citation_text': other_source.citation,
                'start_offset': 0, 'end_offset': 1}]})
    if adjacent:
        answer = answer.replace('（', '。參見（')
    for binding in bindings:
        for occurrence in binding['citation_occurrences']:
            occurrence['start_offset'] = answer.index(occurrence['citation_text']) + 1
            occurrence['end_offset'] = occurrence['start_offset'] + len(occurrence['citation_text'])
    return service, run_id, now, answer, bindings, other_source


@pytest.mark.parametrize('adjacent,same_binding', [(False, False), (True, False), (False, True)])
def test_multiple_offsets_are_proposed_together_without_mutation(tmp_path, adjacent, same_binding):
    service, run_id, now, answer, bindings, _ = two_citations(
        tmp_path, adjacent=adjacent, same_binding=same_binding)
    original = deepcopy(bindings)
    digest = service.store.validation_material_digest(run_id)
    assert not service.validate_answer(run_id, answer, 'before', now=now,
                                       claim_bindings=bindings)['safe_to_present']
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    proposals = review['citation_preparation']['proposals']
    assert [item['status'] for item in proposals] == ['proposed', 'proposed']
    assert not review['safe_to_present']
    assert bindings == original
    assert service.store.validation_material_digest(run_id) == digest
    for item in proposals:
        binding = next(b for b in bindings if b['claim_id'] == item['claim_id'])
        binding['citation_occurrences'][item['occurrence_index']] = item['proposed']
    result = service.validate_answer(run_id, answer, 'after', now=now, claim_bindings=bindings)
    assert result['safe_to_present'], result
    assert service.validate_answer(run_id, answer, 'after', now=now, claim_bindings=bindings) == result
    hidden = service.validate_answer(run_id, answer + '因此全部免責。', 'hidden', now=now,
                                     claim_bindings=bindings)
    assert not hidden['safe_to_present']


@pytest.mark.parametrize('problem', ['wrong_source', 'ineligible', 'expired', 'duplicate', 'outside_window'])
def test_batch_does_not_launder_invalid_or_ambiguous_context(tmp_path, problem):
    service, run_id, now, answer, bindings, source = two_citations(tmp_path, adjacent=True)
    occurrence = bindings[1]['citation_occurrences'][0]
    if problem == 'wrong_source':
        occurrence['evidence_id'] = bindings[0]['evidence_ids'][0]
    elif problem in {'ineligible', 'expired'}:
        from datetime import timedelta
        source = source.model_copy(update={'trust_status': TrustStatus.VERIFICATION_FAILED}
            if problem == 'ineligible' else {'fetched_at': now - timedelta(days=2), 'verified_at': now - timedelta(days=2),
                  'expires_at': now - timedelta(seconds=1)})
        source = source.model_copy(update={'source_id': 'synthetic-invalid-source'})
        service.store.save_source(run_id, source)
        old = service.store.get_evidence(occurrence['evidence_id'])
        invalid = old.model_copy(update={'evidence_id': 'synthetic-invalid-evidence',
                                         'source_id': source.source_id})
        service.store.save_evidence(run_id, invalid)
        bindings[1]['evidence_ids'] = [invalid.evidence_id]
        occurrence['evidence_id'] = invalid.evidence_id
    elif problem == 'duplicate':
        bindings.append({**deepcopy(bindings[1]), 'claim_id': 'duplicate'})
    else:
        occurrence['start_offset'] += 30
        occurrence['end_offset'] += 30
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    assert all(item['proposed'] is None for item in review['citation_preparation']['proposals'])
    assert not service.validate_answer(run_id, answer, 'bad', now=now,
                                       claim_bindings=bindings)['safe_to_present']


CLAIM = '條件甲成立且沒有例外乙時，可以採取措施丙。'
EXTRA = '另一獨立事項丁原則上採取措施戊，惟仍應審查條件己。'


def test_independent_qualifiers_do_not_change_complete_claim_support():
    assert not _qualifier_omitted(CLAIM, CLAIM)
    assert not _qualifier_omitted(CLAIM, CLAIM + EXTRA)
    for evidence in [CLAIM, CLAIM + EXTRA, EXTRA + CLAIM]:
        assert _check(CLAIM, evidence).support_status is SupportStatus.SUPPORTED


@pytest.mark.parametrize('claim,evidence', [
    ('當事人可以採取措施丙。', '除非条件乙成立，當事人可以採取措施丙。'),
    ('當事人可以採取措施丙，但天氣晴朗。', '當事人原則上可以採取措施丙，但條件乙成立者除外。'),
    ('當事人原則上可以採取措施丙。', '當事人原則上可以採取措施丙，但條件乙成立者除外。'),
    ('當事人可以採取措施丙。', '當事人可以採取措施丙。但條件乙成立者除外。'),
    (CLAIM, CLAIM + '其例外仍應核對条件己。'),
    (CLAIM, CLAIM + '其他事項原則上採取措施戊。'),
    (CLAIM, CLAIM + EXTRA + CLAIM),
])
def test_missing_or_unclear_qualifier_never_authorizes(claim, evidence):
    result = _check(claim, evidence)
    assert result.support_status in {SupportStatus.OVERSTATED, SupportStatus.NEEDS_REVIEW}
    assert result.review_required


def test_preserved_complete_qualified_clause_and_other_guards():
    qualified = '當事人原則上可以採取措施丙，但條件乙成立者除外。'
    assert _check(qualified, qualified).support_status is SupportStatus.SUPPORTED
    assert _check(CLAIM, CLAIM + EXTRA, role=SectionRole.PARTY_ARGUMENT).support_status is SupportStatus.ROLE_ERROR
    assert _check('當事人得採取措施丙', '當事人不得採取措施丙').support_status is SupportStatus.CONTRADICTED
    assert _check('應於30日內提出', '應於10日內提出').support_status is SupportStatus.UNSUPPORTED


@pytest.mark.parametrize('name,accepted', [
    ('台灣示範法院示範分院113年測字第1號民事判決', True),
    ('台灣示範法院其他分院113年測字第1號民事判決', False),
    ('台灣示範法院113年測字第1號民事判決', False),
    ('台灣示範法院示範分院113年測字第1號民事裁定', False),
])
def test_branch_court_identity_is_preserved(tmp_path, name, accepted):
    service, _, span, _ = _ready_service(tmp_path)
    source = judgment(service.store.get_source(span.source_id))
    source = source.model_copy(update={
        'citation': source.citation.replace('法院', '法院示範分院'),
        'title': source.title.replace('法院', '法院示範分院')})
    assert judgment_name_equivalent(name, source, {source.source_id: source}) is accepted


@pytest.mark.parametrize('query,judgment,law', [
    ('請整理法院如何處理甲類契約的爭議', True, False),
    ('法院通常怎麼認定示範義務', True, False),
    ('法院實務上如何解釋示範契約', True, False),
    ('請查示範責任法第七條', False, True),
    ('請查示範責任法第7條', False, True),
    ('法院辦公時間與地址', False, True),
    ('甲詞有兩種法律解釋', False, True),
    ('依示範責任法第7條，法院如何處理甲類契約', True, True),
    ('示範法院113年度測字第1號', True, False),
])
def test_bounded_practice_routing(query, judgment, law):
    kinds = {o.kind for o in _plan_obligations(query, mode=DataMode.OFFICIAL_ONLY,
        depth=ResearchDepth.QUICK, as_of_date=None, include_counter_authority=False)}
    assert (Kind.JUDGMENT_RECALL in kinds) is judgment
    assert (Kind.JUDGMENT_OFFICIAL_VERIFICATION in kinds) is judgment
    assert (Kind.LAW_RESEARCH in kinds) is law
    assert Kind.COUNTER_AUTHORITY not in kinds


@pytest.mark.parametrize('extra,accepted', [(EXTRA, True), ('但仍應核對條件己。', False)])
def test_qualifiers_reach_full_answer_gate(tmp_path, extra, accepted):
    service, run_id, old, now = _ready_service(tmp_path)
    text = CLAIM + extra
    source = service.store.get_source(old.source_id).model_copy(update={
        'source_id': 'synthetic-qualifier-source', 'source_key': 'law:synthetic-qualifier',
        'normalized_text': text, 'content_hash': EvidenceSpan.hash_text(text),
        'normalized_content_hash': EvidenceSpan.hash_text(text)})
    evidence = EvidenceSpan.from_exact_text(evidence_id='synthetic-qualifier-evidence',
        source_id=source.source_id, section_id='article-7', section_type='law_text',
        exact_text=text, eligible_for_claim_support=True)
    service.store.save_source(run_id, source)
    service.store.save_evidence(run_id, evidence)
    run = service._run_with_server_refs(service.get_run(run_id))
    service.store.save_run(run)
    service._sync_snapshot_receipts(run, now=now)
    answer = CLAIM.rstrip('。') + '（示範責任法第7條）。'
    start = answer.index(source.citation)
    bindings = [{'claim_id': 'qualifier', 'claim_type': 'law_rule', 'claim_text': CLAIM.rstrip('。'),
        'evidence_ids': [evidence.evidence_id], 'issue_ids': ['issue-duty'],
        'citation_occurrences': [{'evidence_id': evidence.evidence_id,
            'citation_text': source.citation, 'start_offset': start,
            'end_offset': start + len(source.citation)}]}]
    result = service.validate_answer(run_id, answer, 'qualifier-gate', now=now,
                                     claim_bindings=bindings)
    assert result['safe_to_present'] is accepted, result
    if not accepted:
        assert result['answer_text'] is None


def test_routing_preserves_original_input_and_budget_without_execution(tmp_path):
    from alr_tw.research.service import ResearchService
    from alr_tw.storage.sqlite_store import SqliteStore
    service = ResearchService(SqliteStore(tmp_path / 'cache'), research_max_http_requests=3)
    query = '法院如何處理甲類契約中不得收取30元的爭議？'
    run = service.create_run(query, mode=DataMode.SYNTHETIC, depth=ResearchDepth.QUICK,
                             include_counter_authority=False)
    assert run.query == query
    assert run.budget.max_http_requests == 3
    assert Kind.JUDGMENT_RECALL in {item.kind for item in run.obligations}
