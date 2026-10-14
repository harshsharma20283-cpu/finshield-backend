import os, tempfile
from db import connect, init_db
import core, seed as sd

c = connect(os.path.join(tempfile.mkdtemp(), 't.db')); init_db(c)
print('seeded', sd.seed(c), 'ads')
d = core.dashboard(c)
print({k: d[k] for k in ('total_advertisements', 'potentially_suspicious', 'high_risk', 'relationship_count')}, d['risk_distribution'])
print('campaigns:', [(x['member_count'], x['max_risk_score']) for x in core.campaigns(c)])
print('alerts:', len(core.list_alerts(c)), [a['reason'][:60] for a in core.list_alerts(c)[:3]])
bad = core.list_ads(c, page_size=100)['items']
print('LOW scams / HIGH benign check:')
for a in bad:
    if ('Never share' in a['text'] or 'Beware' in a['text'] or 'Fraud alert' in a['text']) and a['risk_category'] != 'LOW':
        print('  FALSE POSITIVE', a['risk_score'], a['text'][:60])
    if (' rent' in a['text'].lower() or 'bikau' in a['text'] or 'recover' in a['text']) and a['risk_category'] == 'LOW':
        print('  FALSE NEGATIVE', a['risk_score'], a['text'][:60])
new = core.analyze_and_store(c, 'SBI current account on rent? Earn Rs 3000 a day. WhatsApp 90000 11101')
x = core.detail(c, new)
print(x['risk_score'], x['risk_category'], [s['title'] for s in x['signals']], len(x['relationships']), 'rels')
print(core.campaign_detail(c, core.campaign_of(c, new))['member_count'], 'in its campaign')
print(core.set_review(c, new, 'escalated')['review_status'], core.add_note(c, new, 'check bank')['content'])
print(core.list_ads(c, q='rent', risk='HIGH')['total'], core.mark_alert(c, core.list_alerts(c)[0]['id'], True)['is_read'])
