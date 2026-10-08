"""A durable, immutable cloud claim for the existing SOC window."""

import json
import re
from datetime import datetime, timezone
from evaluation.finalization.cloud_window import GitHubAPI, REPOSITORY, CloudError
from evaluation.soc_traces_v1.release import WINDOW

TAG = "vinsoc-window-" + WINDOW


class SocCloudStore:
    def __init__(self, api, implementation_sha, run_id):
        if (
            type(api) is not GitHubAPI
            or not re.fullmatch("[0-9a-f]{40}", implementation_sha)
            or not re.fullmatch("[0-9]{1,24}", run_id)
        ):
            raise ValueError("SOC_CLOUD_IDENTITY_INVALID")
        self.api, self.sha, self.run_id = api, implementation_sha, run_id
        self.prefix = "/repos/" + REPOSITORY
        self.claimed = False

    def exists(self):
        return self.api.request("GET", self.prefix + "/git/ref/tags/" + TAG) is not None

    def claim(self, release):
        if self.exists():
            raise ValueError("SOC_SCOPE_ALREADY_CONSUMED")
        marker = {
            "window": WINDOW,
            "release_sha256": release["release_sha256"],
            "implementation_sha": self.sha,
            "run_id": self.run_id,
            "consumed": True,
            "state": "claimed_no_resume_if_runner_lost",
        }
        tag = self.api.request(
            "POST",
            self.prefix + "/git/tags",
            {
                "tag": TAG,
                "message": json.dumps(marker, sort_keys=True),
                "object": self.sha,
                "type": "commit",
                "tagger": {
                    "name": "VinSOC SOC runner",
                    "email": "noreply@github.com",
                    "date": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        if not isinstance(tag, dict) or not re.fullmatch("[0-9a-f]{40}", tag.get("sha", "")):
            raise ValueError("SOC_CLOUD_CLAIM_RESPONSE_INVALID")
        # GitHub creates a ref only once. A competing runner cannot replace it.
        self.api.request(
            "POST", self.prefix + "/git/refs", {"ref": "refs/tags/" + TAG, "sha": tag["sha"]}
        )
        self.claimed = True
