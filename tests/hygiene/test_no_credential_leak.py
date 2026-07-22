"""No test fixture leaves fake credentials in the environment for other tests.

The AWS adapter tests put fake credentials in ``os.environ`` because the
adapters read them from there. When that assignment was session-scoped it stayed
set for every later test in the run, and ``tests/unit/test_pre_deploy_gate.py``
handed its whole environment to a subprocess running ``terraform init`` against
the real ``infra/`` tree. The AWS provider validated the token it found and got a
403 from STS, so two gate tests failed for a reason that had nothing to do with
the gate, in full runs only, while passing in isolation.

This module is the standing guard against that returning. It lives outside
``tests/aws`` deliberately: the credential fixture is autouse inside that
package, so a guard placed there would always see the values it is meant to
catch. pytest walks test directories in name order, so ``tests/hygiene`` runs
after ``tests/aws`` and observes exactly what that package left behind.

It checks for the fake sentinel values rather than for AWS variables in general.
A blanket "no ``AWS_*`` in the environment" assertion would fail for anyone who
runs the suite on a machine with real credentials configured, which is a normal
thing to have and not a defect. What is never legitimate is this project's own
placeholder surviving the test that needed it.
"""

from __future__ import annotations

import os

# The sentinel values tests/aws/conftest.py assigns. Kept as literals rather than
# imported from that conftest, so this guard still fails if the fixture is
# rewritten to leak under a different name.
FAKE_CREDENTIAL_VALUES = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SECURITY_TOKEN": "testing",
    "AWS_SESSION_TOKEN": "testing",
}


def test_fake_aws_credentials_do_not_outlive_the_tests_that_set_them() -> None:
    leaked = {
        key: value for key, value in FAKE_CREDENTIAL_VALUES.items() if os.environ.get(key) == value
    }
    assert not leaked, (
        "fake AWS credentials are still set after the AWS tests finished: "
        f"{sorted(leaked)}. They are scoped to a single test on purpose; anything "
        "still set here is handed to every later test, including subprocesses."
    )


def test_the_guard_would_notice_a_leak() -> None:
    """The check above passes by absence, so pin that it can actually fail."""
    prior = os.environ.get("AWS_ACCESS_KEY_ID")
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    try:
        leaked = [
            key for key, value in FAKE_CREDENTIAL_VALUES.items() if os.environ.get(key) == value
        ]
        assert "AWS_ACCESS_KEY_ID" in leaked
    finally:
        if prior is None:
            os.environ.pop("AWS_ACCESS_KEY_ID", None)
        else:
            os.environ["AWS_ACCESS_KEY_ID"] = prior
