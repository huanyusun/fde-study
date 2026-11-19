"""校验并速览 cleaning_rules.yaml。用法:
.venv/bin/python downloads/w04/scripts/check_rules.py [规则文件路径]
默认校验 artifacts/w04/cleaning_rules.yaml
"""
import json
import sys
from pathlib import Path

import yaml
from jsonschema import validate

rules_path = Path(sys.argv[1] if len(sys.argv) > 1 else 'artifacts/w04/cleaning_rules.yaml')
schema_path = Path('contracts/w04/cleaning_rules.schema.json')

rules = yaml.safe_load(rules_path.read_text(encoding='utf-8'))
schema = json.loads(schema_path.read_text(encoding='utf-8'))

validate(rules, schema)
print(f'[OK] {rules_path} 通过 cleaning_rules.schema.json 校验')

tc = rules['tag_cleaning']
print(f"\n== tag_cleaning")
print(f"  delimiters: {tc['delimiters']}")
print(f"  legal_tags_source: {tc['legal_tags_source']}")
for key in ('hyphenated_tag_handling', 'unknown_tag_handling', 'note_extraction'):
    print(f"  {key}: {tc[key][:60]}...")

print(f"\n== invalid_values ({len(rules['invalid_values'])} 条)")
for item in rules['invalid_values']:
    print(f"  {item['source_fields']} 值={item['values']} -> {item['action']}")

print(f"\n== abnormal_records ({len(rules['abnormal_records'])} 条)")
for item in rules['abnormal_records']:
    print(f"  {item['rule_id']:<24} {item['action']:<12} {item['reason_code']}")

print(f"\n== raw_preservation")
for key in ('original_files', 'notes', 'quarantine'):
    print(f"  {key}: {rules['raw_preservation'][key][:60]}...")
