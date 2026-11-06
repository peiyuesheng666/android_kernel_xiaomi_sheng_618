#!/usr/bin/env python3
"""Reject full ROM builds until the current device inputs pass validation."""
import json
from pathlib import Path
from validation_inputs import fingerprint

report_file = Path(__file__).resolve().parents[1] / 'reports/lineage-validation.json'
assert report_file.is_file(), 'Run validate_lineage.sh before the full ROM build'
report = json.loads(report_file.read_text())
assert report['validation_passed'], 'Fix the failed validation targets first'
assert report.get('validated_inputs') == fingerprint(), 'Device/BSP inputs changed; repeat validation'
print('Current device/BSP inputs match the successful validation receipt')
