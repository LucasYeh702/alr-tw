"""Synthetic positive/negative pairs for the RC4 citation boundary."""
from datetime import timedelta

import pytest

from alr_tw.contracts.sources import EvidenceSectionType, EvidenceSpan, MaterialType, TrustStatus
from alr_tw.research.citation_identity import judgment_name_equivalent
from alr_tw.research.draft_workspace import review_draft
from alr_tw.research.service import _citation_occurrence_reasons
from alr_tw.verification.claim_support import ClaimBinding
from test_v014_drafting import draft
from test_v070_civil_analysis import _ready_service

NAME = '臺灣示範法院113年度測字第1號'
ALIAS = '台灣示範法院113年測字第1號民事判決'


def judgment(source):
    return source.model_copy(update={
        'source_id': 'synthetic-judgment', 'source_key': 'judgment:synthetic',
        'material_type': MaterialType.JUDGMENT,
        'official_identifier': 'DEMO,113,測,1,20990101,1',
        'citation': NAME, 'title': NAME + '民事判決',
    })


@pytest.mark.parametrize('name', [NAME.replace('臺', '台'), NAME.replace('年度', '年'),
                                 ALIAS, NAME + '民事判決', NAME + '判決'])
def test_identity_alias_requires_same_document(tmp_path, name):
    service, _, span, _ = _ready_service(tmp_path)
    source = judgment(service.store.get_source(span.source_id))
    assert judgment_name_equivalent(name, source, {source.source_id: source})


@pytest.mark.parametrize('name', [
    ALIAS.replace('判決', '裁定'), ALIAS.replace('民事', '刑事'),
    ALIAS.replace('示範', '另一示範'), ALIAS.replace('113年', '112年'),
    ALIAS.replace('測字', '其他字'), ALIAS.replace('第1號', '第2號'),
    ALIAS + '已確定', ALIAS + '2099年1月1日', ALIAS.replace('年測', '年\n測'),
])
def test_identity_conflicts_or_unparsed_suffixes_never_disappear(tmp_path, name):
    service, _, span, _ = _ready_service(tmp_path)
    source = judgment(service.store.get_source(span.source_id))
    assert not judgment_name_equivalent(name, source, {source.source_id: source})


@pytest.mark.parametrize('change', ['different_document', 'different_content', 'missing_kind',
                                  'conflicting_title', 'bad_identifier', 'wrong_material', 'identifier_system'])
def test_identity_requires_unique_supported_metadata(tmp_path, change):
    service, _, span, _ = _ready_service(tmp_path)
    source = judgment(service.store.get_source(span.source_id))
    sources = {source.source_id: source}
    if change in {'different_document', 'different_content'}:
        other = source.model_copy(update={'source_id': 'synthetic-other', **(
            {'official_identifier': 'DEMO,113,測,1,20990102,1'}
            if change == 'different_document' else {'content_hash': EvidenceSpan.hash_text('不同合成文書')}
        )})
        sources[other.source_id] = other
    else:
        updates = {'missing_kind': {'title': NAME},
                   'conflicting_title': {'title': NAME.replace('第1號', '第2號') + '民事判決'},
                   'bad_identifier': {'official_identifier': 'incomplete'},
                   'wrong_material': {'material_type': MaterialType.LAW},
                   'identifier_system': {'official_identifier': 'TSTV,113,測,1,20990101,1',
                                         'citation': NAME + '刑事判決', 'title': NAME + '刑事判決'}}[change]
        source = source.model_copy(update=updates)
        sources[source.source_id] = source
    supplied = ALIAS.replace('民事', '刑事') if change == 'identifier_system' else ALIAS
    assert not judgment_name_equivalent(supplied, source, sources)


def adjacent(span, lead='參見'):
    answer, bindings = draft(span.evidence_id)
    answer = answer.replace('（', '。' + lead + '（')
    occurrence = bindings[0]['citation_occurrences'][0]
    occurrence['start_offset'] = answer.index(occurrence['citation_text'])
    occurrence['end_offset'] = occurrence['start_offset'] + len(occurrence['citation_text'])
    return answer, bindings


@pytest.mark.parametrize('lead', ['參見', '參照', '見', '依'])
def test_pure_adjacent_annotation_passes_full_gate_without_mutation(tmp_path, lead):
    service, run_id, span, now = _ready_service(tmp_path)
    answer, bindings = adjacent(span, lead)
    before = service.store.validation_material_digest(run_id)
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    assert not review['safe_to_present']
    assert service.store.validation_material_digest(run_id) == before
    result = service.validate_answer(run_id, answer, 'adjacent', now=now, claim_bindings=bindings)
    assert result['safe_to_present'], result
    assert service.validate_answer(run_id, answer, 'adjacent', now=now,
                                   claim_bindings=bindings) == result
    with pytest.raises(ValueError, match='OPERATION_REQUEST_MISMATCH'):
        service.validate_answer(run_id, answer + '無罪。', 'adjacent', now=now,
                                claim_bindings=bindings)


@pytest.mark.parametrize('kind', ['conclusion', 'inside_parentheses', 'intervening_claim',
                                 'paragraph', 'duplicate_claim', 'duplicate_binding',
                                 'partial_claim', 'two_citations', 'mismatched_parentheses'])
def test_adjacent_annotation_cannot_hide_claims_or_guess_associations(tmp_path, kind):
    service, run_id, span, now = _ready_service(tmp_path)
    answer, bindings = adjacent(span)
    occurrence = bindings[0]['citation_occurrences'][0]
    if kind == 'conclusion':
        answer = answer[:-1] + '，因此無罪。'
    elif kind == 'inside_parentheses':
        answer = answer.replace('）。', '且無罪）。')
    elif kind == 'intervening_claim':
        answer = answer.replace('。參見', '。另有未支持主張。參見')
    elif kind == 'paragraph':
        answer = answer.replace('。參見', '。\n參見')
    elif kind == 'duplicate_claim':
        answer = bindings[0]['claim_text'] + '。' + answer
    elif kind == 'duplicate_binding':
        bindings.append({**bindings[0], 'claim_id': 'another'})
    elif kind == 'partial_claim':
        bindings[0]['claim_text'] = '應負合成測試責任'
    elif kind == 'two_citations':
        answer = answer[:-1] + '（' + occurrence['citation_text'] + '）。'
    else:
        answer = answer.replace('）。', ').')
    occurrence['start_offset'] = answer.index(occurrence['citation_text'])
    occurrence['end_offset'] = occurrence['start_offset'] + len(occurrence['citation_text'])
    result = service.validate_answer(run_id, answer, 'negative', now=now, claim_bindings=bindings)
    assert not result['safe_to_present']
    assert result['answer_text'] is None


def test_adjacent_offset_proposal_then_new_operation_strict_revalidation(tmp_path):
    service, run_id, span, now = _ready_service(tmp_path)
    answer, bindings = adjacent(span)
    occurrence = bindings[0]['citation_occurrences'][0]
    occurrence['start_offset'] += 2
    occurrence['end_offset'] += 2
    assert not service.validate_answer(run_id, answer, 'before', now=now,
                                       claim_bindings=bindings)['safe_to_present']
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    proposal = review['citation_preparation']['proposals'][0]
    assert proposal['status'] == 'proposed'
    bindings[0]['citation_occurrences'] = [proposal['proposed']]
    assert service.validate_answer(run_id, answer, 'after', now=now,
                                   claim_bindings=bindings)['safe_to_present']


@pytest.mark.parametrize('with_adjacent', [False, True])
def test_judgment_equivalence_flows_through_preparation_and_strict_validation(tmp_path, with_adjacent):
    service, run_id, span, now = _ready_service(tmp_path)
    source = judgment(service.store.get_source(span.source_id))
    evidence = span.model_copy(update={'evidence_id': 'synthetic-court-evidence',
                                      'source_id': source.source_id, 'section_type': EvidenceSectionType.COURT_REASONING})
    service.store.save_source(run_id, source)
    service.store.save_evidence(run_id, evidence)
    run = service._run_with_server_refs(service.get_run(run_id))
    service.store.save_run(run)
    service._sync_snapshot_receipts(run, now=now)
    answer, bindings = draft(evidence.evidence_id)
    old = bindings[0]['citation_occurrences'][0]['citation_text']
    answer = answer.replace(old, ALIAS)
    if with_adjacent:
        answer = answer.replace('（', '。參見（')
    bindings[0]['claim_type'] = 'court_view'
    bindings[0]['citation_occurrences'] = [{'evidence_id': evidence.evidence_id,
        'citation_text': ALIAS, 'start_offset': answer.index(ALIAS),
        'end_offset': answer.index(ALIAS) + len(ALIAS)}]
    parsed = [ClaimBinding.model_validate(b) for b in bindings]
    assert not _citation_occurrence_reasons(answer, parsed,
        evidence_by_id={evidence.evidence_id: evidence}, sources={source.source_id: source})
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    assert review['citation_preparation']['proposals'][0]['status'] == 'unchanged'
    result = service.validate_answer(run_id, answer, 'alias', now=now, claim_bindings=bindings)
    assert result['safe_to_present'], result


@pytest.mark.parametrize('expired', [True, False])
def test_new_annotation_path_does_not_bypass_eligibility(tmp_path, expired):
    service, run_id, span, now = _ready_service(tmp_path)
    answer, bindings = adjacent(span)
    if expired:
        now += timedelta(days=2)
        with pytest.raises(ValueError, match='RESEARCH_RUN_EXPIRED'):
            service.validate_answer(run_id, answer, 'expired', now=now, claim_bindings=bindings)
    else:
        # A different ineligible source cannot be laundered through a pure citation.
        old = service.store.get_source(span.source_id)
        source = old.model_copy(update={'source_id': 'ineligible-source',
                                        'trust_status': TrustStatus.VERIFICATION_FAILED})
        service.store.save_source(run_id, source)
        other = span.model_copy(update={'source_id': source.source_id, 'evidence_id': 'ineligible-span'})
        service.store.save_evidence(run_id, other)
        bindings[0]['evidence_ids'] = [other.evidence_id]
        bindings[0]['citation_occurrences'][0]['evidence_id'] = other.evidence_id
        assert not service.validate_answer(run_id, answer, 'ineligible', now=now,
                                           claim_bindings=bindings)['safe_to_present']


def test_position_preparation_preserves_ambiguous_binding_context(tmp_path):
    service, run_id, span, now = _ready_service(tmp_path)
    answer, bindings = adjacent(span)
    occurrence = bindings[0]['citation_occurrences'][0]
    bindings[0]['citation_occurrences'].append(dict(occurrence))
    review = review_draft(service.store, run_id, answer, bindings, now=now)
    assert all(item['status'] == 'requires_revision'
               for item in review['citation_preparation']['proposals'])
    assert not service.validate_answer(run_id, answer, 'duplicate-occurrence', now=now,
                                       claim_bindings=bindings)['safe_to_present']
