from __future__ import annotations

import argparse
import json
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ntu_mail_forward.classifier import Classifier, load_rules


CASES_FILE = ROOT / "tests" / "fixtures" / "classifier_rule_review.json"
BASELINE_PROBE = """
import json
import sys
from email.message import EmailMessage
from ntu_mail_forward.classifier import Classifier

classifier = Classifier()
decisions = []
for case in json.load(sys.stdin):
    message = EmailMessage()
    message['From'] = case['sender']
    message['Subject'] = case['subject']
    for name, value in case.get('headers', {}).items():
        message[name] = value
    message.set_content(case.get('body', ''))
    decisions.append(classifier.classify(message).decision)
json.dump(decisions, sys.stdout)
"""


def review_message(case: dict) -> EmailMessage:
    message = EmailMessage()
    message["From"] = case["sender"]
    message["Subject"] = case["subject"]
    for name, value in case.get("headers", {}).items():
        message[name] = value
    message.set_content(case.get("body", ""))
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description="以固定合成案例比較分類規則。")
    parser.add_argument("--baseline-root", type=Path, help="整理前受信任 checkout 的根目錄，會執行其中的分類器。")
    parser.add_argument("--rules", type=Path, default=ROOT / "classifier_rules.json")
    args = parser.parse_args()
    current = Classifier(load_rules(args.rules))
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    baseline_decisions = None
    if args.baseline_root is not None:
        result = subprocess.run(
            [sys.executable, "-c", BASELINE_PROBE],
            cwd=args.baseline_root,
            input=json.dumps(cases),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        baseline_decisions = json.loads(result.stdout)
    failures = 0
    changes = 0
    for index, case in enumerate(cases):
        message = review_message(case)
        after = current.classify(message).decision
        if after != case["after"]:
            print(f"失敗：{case['name']}，目前 {after}，預期 {case['after']}")
            failures += 1
        if baseline_decisions is not None:
            before = baseline_decisions[index]
            if before != case["before"]:
                print(f"失敗：{case['name']}，基底 {before}，預期 {case['before']}")
                failures += 1
            if before != after:
                print(f"變更：{case['name']}，{before} -> {after}")
                changes += 1
    if baseline_decisions is None:
        print(f"檢查 {len(cases)} 個案例，失敗 {failures} 個。")
    else:
        print(f"檢查 {len(cases)} 個案例，分類變更 {changes} 個，失敗 {failures} 個。")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
