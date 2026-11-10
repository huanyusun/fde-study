"""Minimal worked example: one ungrouped numeric metric, exact cents/count units.
Extend the learner implementation for multiple metrics, groups, nulls and other units.
"""
import json,sys,math
def compare(expected,actual):
 errors=[]
 if actual.get('status')!=expected['status']:errors.append('status')
 if expected['status']=='ok':
  m=expected['intent']['metrics'][0]
  if actual.get('intent')!=expected['intent']:errors.append('intent')
  if actual.get('columns')!=[m] or len(actual.get('rows',[]))!=1:errors.append('shape')
  else:
   v=actual['rows'][0][0];want=expected['rows'][0][0]
   if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not math.isclose(v,want,rel_tol=1e-9,abs_tol=1e-7):errors.append('value')
  if actual.get('units')!=expected['units']:errors.append('units')
 return {'passed':not errors,'differences':errors}
if __name__=='__main__':
 data=json.load(sys.stdin);print(json.dumps(compare(data['expected'],data['actual'])))
