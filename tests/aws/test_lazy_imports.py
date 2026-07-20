"""Lazy-import guard for the AWS adapters (INV-4, AT-10), mirroring the Kafka test.

Importing the AWS adapter modules, the fan-out, and the store factory must pull in
no cloud SDK, so test collection, the in-memory smoke, and every Phase 1 test stay
offline. The SDK is imported only inside the run path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "CII_TRANSPORT_BOOTSTRAP_SERVERS"}
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_importing_aws_adapters_pulls_in_no_cloud_sdk() -> None:
    code = (
        "import sys\n"
        "import climate_index.adapters.aws\n"
        "import climate_index.adapters.aws.iceberg_store\n"
        "import climate_index.adapters.aws.dynamo_store\n"
        "import climate_index.adapters.aws.dynamo_reader\n"
        "import climate_index.adapters.aws.s3_raw_store\n"
        "import climate_index.adapters.aws._keys\n"
        "import climate_index.adapters.aws._dynamo\n"
        "import climate_index.adapters.composite\n"
        "import climate_index.store_factory\n"
        "import climate_index.consumer\n"
        "import climate_index.processor\n"
        "roots = ('boto3', 'botocore', 'pyiceberg', 'pyarrow')\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in roots]\n"
        "assert not bad, bad\n"
    )
    result = _run(["-c", code])
    assert result.returncode == 0, result.stderr
