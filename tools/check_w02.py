"""Read-only W2 precheck; exit zero means ready for review, never course pass."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform"))
from fde_product.w02_natural_checker import precheck
from fde_product.interview_extraction import Workspace, CheckError

ROLE_NAMES = {'ROLE-ZHOU':'老周', 'ROLE-LIN':'小林', 'ROLE-CHEN':'陈姐'}
LEADS = {'COMPARISON_REQUIRED':'还没有本人同题对照', 'CURRENT_MODEL_REQUIRED':'对照运行不是当前版本',
         'EXTRACTION_REQUIRED':'还没有可用的提取运行', 'LIVE_EXTRACTION_REQUIRED':'缺本人实际调用模型的提取',
         'HASH_MISMATCH':'文件与运行记录的快照不一致', 'W1_IDS_MISSING':'W2 fit-gap 少了 W1 的条目编号',
         'RUN_LIMIT_EXCEEDED':'运行记录过多'}


def issue_text(issue, options):
    code, path, step = issue.get('code', ''), issue.get('path', ''), issue.get('next_step', '')
    if code == 'REQUIRED_ROLES_MISSING':
        names = [ROLE_NAMES.get(x, x) for x in path.split(',') if x]
        return f"缺必访角色：{'、'.join(names)}。{step}"
    documents = {options.get('business_model'):'业务模型说明', options.get('interview_notes'):'访谈与核查记录',
                 options.get('knowledge_config'):'知识配置', options.get('w1_fit_gap'):'W1 的 fit-gap',
                 options.get('w2_fit_gap'):'W2 的 fit-gap'}
    # A path without a slash is the checker's own label, which the lead already says.
    where = f'（{path}）' if '/' in path else ''
    if path in documents and code == 'SOURCE_NOT_FOUND':
        return f"缺{' ' if documents[path][0].isascii() else ''}{documents[path]}（{path}）：{step}"
    if path in documents and code == 'EMPTY_DOCUMENT':
        return f'{documents[path]}是空的（{path}）：{step}'
    if code in LEADS:
        return f'{LEADS[code]}{where}：{step}'
    return f'{code}（{path}）：{step}'


def summary_lines(result):
    """Chinese recap for a learner; the JSON above stays the full result."""
    if result['status'] == 'ready_for_review':
        return ['预检结果：结构可供审阅，这不代表作业通过']
    rows = list(dict.fromkeys(issue_text(x, result['options']) for x in result['issues']))
    return [f'预检结果：还差 {len(rows)} 项，暂不能提交', *[f'{i}. {text}' for i, text in enumerate(rows, 1)],
            '全部项和说明见上方 JSON。']


def show_summary(result):
    try:
        print('\n'.join(summary_lines(result)), file=sys.stderr)
    except Exception:
        pass  # The recap must never change the result.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', default=str(ROOT))
    p.add_argument('--run', action='append', help='采用的知识对照 run.json；可重复，省略时只查默认目录下一层。')
    p.add_argument('--config', default='customer/w02/knowledge.json')
    p.add_argument('--w1-fit-gap', default='artifacts/w01/product_fit_gap.json')
    p.add_argument('--w2-fit-gap')
    p.add_argument('--output', help='可选新报告路径，相对于客户仓库；不覆盖已有文件。')
    a = p.parse_args()
    try:
        result = precheck(a.workspace, knowledge_config=a.config, runs=a.run,
                          w1_fit_gap=a.w1_fit_gap, w2_fit_gap=a.w2_fit_gap)
        if a.output:
            Workspace(a.workspace).write(a.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        show_summary(result)
        return int(result['status'] != 'ready_for_review')
    except CheckError as e:
        print(json.dumps({'status':'error', 'code':e.code, 'path':e.location}, ensure_ascii=False), flush=True)
        try:
            print(f'预检结果：没能运行完（{e.code}，{e.location}），暂不能提交\n按上方 JSON 里的错误和路径处理后再运行一次。', file=sys.stderr)
        except Exception:
            pass
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
