"""Immutable GitHub checkpoints for the single-case query demo."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from evaluation.finalization.cloud_window import REPOSITORY


class QueryCloudError(ValueError):
    pass


class QueryDemoGitHubStore:
    def __init__(self, api, *, implementation_sha, run_id):
        if (not re.fullmatch(r'[0-9a-f]{40}', implementation_sha)
                or not re.fullmatch(r'[0-9]{1,24}', str(run_id))):
            raise QueryCloudError('CLOUD_IDENTITY_INVALID')
        self.api = api
        self.implementation_sha = implementation_sha
        self.run_id = str(run_id)
        self.prefix = '/repos/'+REPOSITORY
        self.tag_prefix = None
        self.claimed = False

    @staticmethod
    def _tag_component(window_id):
        if not re.fullmatch(r'text2sql-integration-20261008-demo-[A-Za-z0-9_-]+', window_id):
            raise QueryCloudError('CLOUD_WINDOW_ID_INVALID')
        return 'vinsoc-query-demo-'+window_id

    def _exists(self, tag):
        return self.api.request('GET', self.prefix+'/git/ref/tags/'+tag) is not None

    def _tag(self, name, data):
        message = json.dumps(data, sort_keys=True, separators=(',', ':'))
        if len(message.encode('utf-8')) > 16384:
            raise QueryCloudError('REMOTE_CHECKPOINT_TOO_LARGE')
        value = {'tag':name, 'message':message, 'object':self.implementation_sha, 'type':'commit',
                 'tagger':{'name':'VinSOC guarded query demo', 'email':'noreply@github.com',
                           'date':datetime.now(timezone.utc).isoformat()}}
        tag = self.api.request('POST', self.prefix+'/git/tags', value)
        if not isinstance(tag, dict) or not re.fullmatch(r'[0-9a-f]{40,64}', tag.get('sha','')):
            raise QueryCloudError('REMOTE_TAG_RESPONSE_INVALID')
        self.api.request('POST', self.prefix+'/git/refs', {'ref':'refs/tags/'+name, 'sha':tag['sha']})

    def claim(self, window_id, release_sha256):
        if not re.fullmatch(r'[0-9a-f]{64}', release_sha256):
            raise QueryCloudError('CLOUD_RELEASE_IDENTITY_INVALID')
        tag = self._tag_component(window_id)
        if self._exists(tag):
            raise QueryCloudError('WINDOW_ALREADY_USED')
        self._tag(tag, {'window_id':window_id, 'release_sha256':release_sha256,
                        'implementation_sha':self.implementation_sha, 'run_id':self.run_id,
                        'consumed':True})
        self.tag_prefix = tag
        self.claimed = True

    def checkpoint(self, request_number, phase, event):
        if not self.claimed:
            raise QueryCloudError('REMOTE_CLAIM_REQUIRED')
        if type(request_number) is not int or not 1 <= request_number <= 8 or phase not in ('begin','end'):
            raise QueryCloudError('REMOTE_CHECKPOINT_INVALID')
        if not isinstance(event, dict) or 'request' in event or 'response' in event:
            raise QueryCloudError('REMOTE_CHECKPOINT_INVALID')
        name = f'{self.tag_prefix}-request-{request_number}-{phase}'
        self._tag(name, {'run_id':self.run_id, 'request_number':request_number,
                         'phase':phase, 'event':event})
