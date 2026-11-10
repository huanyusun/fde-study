"""Call the standard Agent, then the learner's deterministic subprocess judge."""
import subprocess,json,uuid
from pathlib import Path
from .common import read,dump,new_output

def judge(command,expected,actual,cwd=None):
 if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):raise ValueError('JUDGE_COMMAND_REQUIRED')
 r=subprocess.run(command,input=json.dumps({'expected':expected,'actual':actual},ensure_ascii=False),text=True,capture_output=True,timeout=30,cwd=cwd)
 if r.returncode:raise ValueError('JUDGE_FAILED: '+r.stderr[-1500:])
 try:result=json.loads(r.stdout)
 except ValueError:raise ValueError('JUDGE_JSON_REQUIRED') from None
 if not isinstance(result,dict) or type(result.get('passed')) is not bool or not isinstance(result.get('differences'),list):raise ValueError('JUDGE_RESULT_CONTRACT_INVALID')
 return result

def run_cases(project,cases_path,command,out,cwd=None):
 from .agent import MetricsAgent
 cases=read(cases_path)
 if not isinstance(cases,list) or not cases:raise ValueError('TEST_CASES_REQUIRED')
 if len({c['id'] for c in cases})!=len(cases):raise ValueError('CASE_IDS_MUST_BE_UNIQUE')
 out=new_output(out);agent=MetricsAgent(project,out/'traces');results=[]
 # Missing judge fails before spending model tokens or taking the output name.
 judge(command,cases[0]['expected'],cases[0]['expected'],cwd)
 out.mkdir(parents=True,exist_ok=False)
 for case in cases:
  actual=agent.ask(case['question']);comparison=judge(command,case['expected'],actual,cwd)
  results.append({'id':case['id'],'question':case['question'],'expected':case['expected'],'actual':actual,'comparison':comparison})
  dump(out/'metric_test_report.json',{'contract_version':'w03-0.1.0','complete':False,'cases':results})
 report={'contract_version':'w03-0.1.0','complete':True,'passed':sum(x['comparison']['passed'] for x in results),'total':len(results),'cases':results};dump(out/'metric_test_report.json',report);return report
