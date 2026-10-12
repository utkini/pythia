from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from openai import BadRequestError
from pythia.schemas import ReelMetadata
from pythia.services.openai_analyzer import AnalysisError, OpenAIAnalyzer


def analyzer_with_response(raw='{"summary":"test"}', refusal=None, finish='stop'):
    analyzer = object.__new__(OpenAIAnalyzer)
    analyzer._vision_model = 'test-model'
    response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=raw, refusal=refusal), finish_reason=finish,
    )])
    create = AsyncMock(return_value=response)
    analyzer._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return analyzer, create


async def test_invalid_model_response_logs_fields_without_content(capsys):
    analyzer, _ = analyzer_with_response('{"summary":"private-text","screen_text":null}')
    with pytest.raises(AnalysisError, match='invalid_response_schema'):
        await analyzer.analyse(ReelMetadata(shortcode='a', url='https://example.com'), 'private-transcript', [])
    output = capsys.readouterr().out
    assert 'screen_text' in output
    assert 'private-text' not in output
    assert 'private-transcript' not in output


async def test_api_error_logs_status_not_body(capsys):
    analyzer, create = analyzer_with_response()
    create.side_effect = BadRequestError('private-message', response=httpx.Response(
        400, request=httpx.Request('POST', 'https://api.openai.com/v1/chat/completions'),
        headers={'x-request-id':'req-test'},
    ), body={'message':'private-body'})
    with pytest.raises(AnalysisError, match='api_status_error'):
        await analyzer.analyse(ReelMetadata(shortcode='a', url='https://example.com'), '', [])
    output = capsys.readouterr().out
    assert '400' in output
    assert 'req-test' in output
    assert 'private-message' not in output
    assert 'private-body' not in output


@pytest.mark.parametrize(('refusal','finish','message'), [
    ('refused', 'stop', 'declined'), (None, 'length', 'incomplete'),
])
async def test_refusal_and_truncation_are_distinguished(refusal, finish, message):
    analyzer, _ = analyzer_with_response(refusal=refusal, finish=finish)
    with pytest.raises(AnalysisError, match=message):
        await analyzer.analyse(ReelMetadata(shortcode='a', url='https://example.com'), '', [])
