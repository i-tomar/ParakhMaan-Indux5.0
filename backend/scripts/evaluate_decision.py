"""Decision-level evaluation of the full engine + default DecisionPolicy on the held-out test split.

    python scripts/evaluate_decision.py      # run from backend/, needs ../datasets/prepared/manifest.json

Writes storage/reports/eval_decision.json. Real images only. This is the number a line operator sees:
how many good parts are rejected or sent to review, and how many defective parts are accepted.
"""
import json, sys, collections, cv2
sys.path.insert(0, '.')
from app.services.inference.engine import engine
from app.services.line.decision import decide
recs = json.load(open('../datasets/prepared/manifest.json'))['records']
per = collections.defaultdict(lambda: collections.Counter())
for r in recs:
    if r['split'] not in ('test', 'unknown_test'):
        continue
    res = engine.inspect(cv2.imread('../' + r['path']), r['category'], None, want_heatmap=False)
    d = decide(res['detections'], None, res['exposure_ok'])['decision']
    kind = 'good' if r['kind'] == 'good' else ('unknown' if r['split'] == 'unknown_test' else 'known')
    per[r['category']][(kind, d)] += 1
def summary(c):
    g = sum(v for (k, _), v in c.items() if k == 'good'); b = sum(v for (k, _), v in c.items() if k != 'good')
    return {'good': g, 'good_accepted': c[('good', 'ACCEPT')], 'good_review': c[('good', 'MANUAL_REVIEW')], 'good_rejected': c[('good', 'REJECT')],
            'defective': b, 'defective_rejected': sum(v for (k, d), v in c.items() if k != 'good' and d == 'REJECT'),
            'defective_review': sum(v for (k, d), v in c.items() if k != 'good' and d == 'MANUAL_REVIEW'),
            'defective_accepted_escape': sum(v for (k, d), v in c.items() if k != 'good' and d == 'ACCEPT'),
            'unknown_escape': c[('unknown', 'ACCEPT')], 'unknown_total': sum(v for (k, _), v in c.items() if k == 'unknown')}
tot = collections.Counter()
for c in per.values(): tot.update(c)
s = summary(tot)
s['false_reject_rate'] = round(s['good_rejected'] / s['good'], 4)
s['good_sent_to_review_rate'] = round(s['good_review'] / s['good'], 4)
s['escape_rate'] = round(s['defective_accepted_escape'] / s['defective'], 4)
s['auto_reject_rate_on_defective'] = round(s['defective_rejected'] / s['defective'], 4)
report = {'data': 'real images, MVTec AD held-out test + unknown_test splits; full engine (YOLO-seg + anomaly + fusion) and default DecisionPolicy; no golden reference',
          'overall': s, 'per_product': {k: summary(v) for k, v in sorted(per.items())}}
json.dump(report, open('storage/reports/eval_decision.json', 'w'), indent=1)
print(json.dumps(s, indent=1))
