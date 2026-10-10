"""Offline evidence for conservative input ceilings, without guessing API framing."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from evaluation.r2_cross_domain_v1.release import fresh

MODEL_DOCS = {
    'gpt-5-mini-2025-08-07': 'https://developers.openai.com/api/docs/models/gpt-5-mini.md',
    'gpt-4.1-mini-2025-04-14': 'https://developers.openai.com/api/docs/models/gpt-4.1-mini.md',
}


def read_model_document(path, model):
    content = Path(path).read_text(encoding='utf-8')
    if f'`{model}`' not in content or '| Chat Completions | `v1/chat/completions` | Supported |' not in content:
        raise ValueError('MODEL_DOCUMENT_MISMATCH')
    context = re.search(r'^- ([\d,]+) context window$', content, re.MULTILINE)
    if not context:
        raise ValueError('DOCUMENTED_CONTEXT_WINDOW_REQUIRED')
    prices = {}
    for label, key in [('Input','input_usd_per_million'), ('Cached input','cached_input_usd_per_million'),
                       ('Output','output_usd_per_million')]:
        found = re.search(r'^\| '+label+r' \| \$([\d.]+) \| 1M tokens \|$', content, re.MULTILINE)
        if not found:
            raise ValueError('DOCUMENTED_PRICE_REQUIRED')
        prices[key] = float(found[1])
    return {'input_token_ceiling': int(context[1].replace(',', '')), **prices}


def verified_input_bound(pricing, model):
    reference = pricing.get('model_document') or {}
    if (model not in MODEL_DOCS or reference.get('source_url') != MODEL_DOCS[model]
            or pricing.get('token_bound_method') != 'documented_context_window'
            or not fresh(pricing.get('checked_utc'))):
        raise ValueError('DOCUMENTED_TOKEN_BOUND_REQUIRED')
    path = Path(reference.get('path', '')).resolve()
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != reference.get('sha256'):
        raise ValueError('MODEL_DOCUMENT_HASH_MISMATCH')
    observed = read_model_document(path, model)
    if (pricing.get('input_token_ceiling') != observed['input_token_ceiling']
            or any(pricing.get(k) != v for k, v in observed.items())):
        raise ValueError('MODEL_DOCUMENT_PRICE_OR_BOUND_MISMATCH')
    return observed['input_token_ceiling']
