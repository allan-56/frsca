import json
import os
import sys
import yaml
import re

# Mocking the verification logic since we can't run a full Kyverno cluster here
class KyvernoPolicyEngine:
    def __init__(self, policy_dir):
        self.policies = []
        for f in os.listdir(policy_dir):
            if f.endswith(".yaml"):
                with open(os.path.join(policy_dir, f)) as pf:
                    self.policies.append(yaml.safe_load(pf))

    def evaluate(self, predicate_json, resource_kind="InferenceService"):
        """Evaluates policies against a given predicate JSON.
           If predicate_json is None, it simulates missing attestations.
        """
        violations = []
        for policy in self.policies:
            rules = policy.get("spec", {}).get("rules", [])
            for rule in rules:
                # Check if rule applies to resource kind
                matched = False
                match_block = rule.get("match", {}).get("any", [])
                for m in match_block:
                    if resource_kind in m.get("resources", {}).get("kinds", []):
                        matched = True
                        break

                if not matched:
                    continue

                # If no attestations are provided (S5 scenario), it's a violation for verifyImages
                if predicate_json is None:
                    violations.append(f"Policy '{policy['metadata']['name']}' rule '{rule['name']}' failed: No attestations found.")
                    continue

                # Check conditions in verifyImages -> attestations -> conditions
                verify_images = rule.get("verifyImages", [])
                for verify_image in verify_images:
                    attestations = verify_image.get("attestations", [])
                    for attestation in attestations:
                        # Check if predicate type matches
                        pred_type = attestation.get("predicateType")
                        if pred_type != predicate_json.get("predicateType"):
                            continue # Skip non-matching predicate types

                        conditions = attestation.get("conditions", [])
                        for condition in conditions:
                            all_conditions = condition.get("all", [])
                            for cond in all_conditions:
                                key_path = cond.get("key") # e.g. {{ predicate.mlSpecifics.datasets[0].uri }}
                                operator = cond.get("operator")
                                expected_value = cond.get("value")

                                # Extract value from predicate using simple JSON path logic
                                actual_value = self._extract_value(predicate_json, key_path)

                                if not self._check_condition(actual_value, operator, expected_value):
                                    violations.append(f"Policy '{policy['metadata']['name']}' rule '{rule['name']}' failed: {key_path} ({actual_value}) {operator} {expected_value}")
        return violations

    def _extract_value(self, data, key_path):
        # Remove {{ }} and 'predicate.' prefix
        path = key_path.strip("{} ").replace("predicate.", "")

        # Handle simple array indexing [0]
        parts = []
        for p in path.split("."):
            if "[" in p and "]" in p:
                name, index = p[:-1].split("[")
                parts.append(name)
                parts.append(int(index))
            else:
                parts.append(p)

        current = data.get("predicate", {})
        try:
            for p in parts:
                if isinstance(current, list) and isinstance(p, int):
                    current = current[p]
                elif isinstance(current, dict):
                    current = current.get(p)
                else:
                    return None
            return current
        except (IndexError, AttributeError, TypeError):
            return None

    def _check_condition(self, actual, operator, expected):
        if actual is None:
            return False

        if operator == "Equals":
            return actual == expected
        elif operator == "GreaterThan":
            try:
                return float(actual) > float(expected)
            except:
                return False
        elif operator == "PatternMatch":
            # Simple wildcard conversion
            pattern = str(expected).replace("*", ".*")
            try:
                return re.match(pattern, str(actual)) is not None
            except:
                return False
        return False

def run_tests():
    engine = KyvernoPolicyEngine("frsca-ml/policy/kyverno")
    results = {}

    print("--- Running Attack Scenarios Validation ---")

    # Scenario S3: Unapproved Data
    print("\n[S3] Testing Unapproved Data Rejection...")
    s3_predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "mlSpecifics": {
                "datasets": [{"uri": "s3://bad-bucket/data.csv"}],
                "metrics": {"accuracy": 0.9},
                "environment": {"frameworkVersion": "2.1.0"}
            },
            "runDetails": {"builder": {"id": "frsca-training-task"}}
        }
    }
    violations = engine.evaluate(s3_predicate)

    # We expect 'require-dataset-provenance' to fail
    if any("require-dataset-provenance" in v for v in violations):
        print("PASS: Unapproved data was correctly rejected.")
        results["S3"] = "PASS"
    else:
        print(f"FAIL: Unapproved data was NOT rejected. Violations: {violations}")
        results["S3"] = "FAIL"

    # Scenario S8: Vulnerable Framework (Version < 2.0)
    print("\n[S8] Testing Vulnerable Framework Rejection...")
    s8_predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "mlSpecifics": {
                "datasets": [{"uri": "s3://approved-data-bucket/data.csv"}],
                "metrics": {"accuracy": 0.9},
                "environment": {"frameworkVersion": "1.5.0"}
            },
            "runDetails": {"builder": {"id": "frsca-training-task"}}
        }
    }
    violations = engine.evaluate(s8_predicate)

    # We expect 'require-model-provenance' to fail (framework check)
    if any("require-model-provenance" in v for v in violations) and \
       any("frameworkVersion" in v for v in violations):
        print("PASS: Vulnerable framework version was correctly rejected.")
        results["S8"] = "PASS"
    else:
        print(f"FAIL: Vulnerable framework was NOT rejected. Violations: {violations}")
        results["S8"] = "FAIL"

    # Scenario S8/Metric Failure: Low Accuracy
    print("\n[Metric Check] Testing Low Accuracy Rejection...")
    low_acc_predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-evaluation/v0.1",
        "predicate": {
            "evaluationSpecifics": {
                "passed": True,
                "metrics": {"accuracy": 0.5}
            }
        }
    }
    violations = engine.evaluate(low_acc_predicate)
    if any("require-evaluation-provenance" in v for v in violations):
        print("PASS: Low accuracy was correctly rejected.")
        results["MetricCheck"] = "PASS"
    else:
        print(f"FAIL: Low accuracy was NOT rejected. Violations: {violations}")
        results["MetricCheck"] = "FAIL"

    # Scenario S5: Manual Bypass (No Attestations)
    print("\n[S5] Testing Manual Bypass (No Attestations)...")
    violations = engine.evaluate(None) # Simulate no attestations found
    if len(violations) > 0:
        print(f"PASS: Missing attestations rejected. Count: {len(violations)}")
        results["S5"] = "PASS"
    else:
        print("FAIL: Missing attestations were allowed!")
        results["S5"] = "FAIL"

    # Valid Scenario
    print("\n[Valid] Testing Valid Predicate...")
    valid_predicate = {
        "predicateType": "https://frsca.dev/provenance/ml-training/v0.2",
        "predicate": {
            "mlSpecifics": {
                "datasets": [{"uri": "s3://approved-data-bucket/data.csv"}],
                "metrics": {"accuracy": 0.95},
                "environment": {"frameworkVersion": "2.1.0"}
            },
            "runDetails": {"builder": {"id": "frsca-training-task"}}
        }
    }

    violations = engine.evaluate(valid_predicate)

    # We expect dataset-provenance to PASS (no violation).
    # We expect model-provenance to PASS (framework version OK).

    relevant_violations = [v for v in violations if "require-dataset-provenance" in v or "require-model-provenance" in v]

    if not relevant_violations:
        print("PASS: Valid dataset predicate accepted by policies.")
        results["Valid"] = "PASS"
    else:
        print(f"FAIL: Valid predicate rejected. Violations: {relevant_violations}")
        results["Valid"] = "FAIL"

    # Summary
    print("\n--- Summary ---")
    print(json.dumps(results, indent=2))

    if all(v == "PASS" for v in results.values()):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
