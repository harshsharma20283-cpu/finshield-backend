import re, uuid
from db import now_iso
from scoring import score_ad

HIGH = ('HIGH', 'CRITICAL')
LIMITS = 'Rules-based triage indicator, not proof of fraud. Findings need human review.'
RECS = {'LOW': 'No action needed. Keep monitoring.',
        'MEDIUM': 'Review the flagged signals and verify the contact details.',
        'HIGH': 'Prioritise for review. Check linked ads and the shared identifiers.',
        'CRITICAL': 'Escalate for review. Check linked ads and the shared identifiers.'}
ETYPE = {'phones': 'phone', 'upi_ids': 'upi_id', 'urls': 'url'}
REVIEW = {'unreviewed', 'under_review', 'escalated', 'closed'}


def nid():
    return uuid.uuid4().hex


def _tokens(t):
    return set(re.findall(r'[a-z0-9]+', t.lower()))


def analyze_and_store(db, text, source=None, source_url=None, image_filename=None, ocr_text=None,
                      ocr_status='not_requested', is_seed=False, created_at=None):
    full = (text + '\n' + ocr_text) if ocr_text else text
    res = score_ad(full)
    ad_id, ts = nid(), created_at or now_iso()
    warnings = []
    ents = [(ETYPE[k], v) for k, vals in res['entities'].items() for v in vals]
    if not ents:
        warnings.append('No phone, UPI ID or link was found, so linking to other ads is limited.')
    if image_filename and ocr_status in ('unavailable', 'failed'):
        warnings.append('Image text could not be read, so only the typed text was scored.')
    db.execute('INSERT INTO ads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (ad_id, text, source, source_url, int(is_seed), 'complete', 'unreviewed', res['risk_score'],
                res['risk_category'], ts, image_filename, ocr_text, ocr_status, LIMITS,
                RECS[res['risk_category']], ts, '\n'.join(warnings)))
    for et, v in ents:
        db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?,?,?)', (nid(), ad_id, et, v, v, v, 'regex', 1.0))
    for s in res['signals']:
        db.execute('INSERT INTO signals VALUES(?,?,?,?,?,?,?,?)',
                   (nid(), ad_id, s['signal_type'], s['title'], s['explanation'], s['evidence'],
                    s['contribution'], s.get('recommendation')))
    _link(db, ad_id, ents, full, res['risk_score'])
    _alerts(db, ad_id, res, ents, ts)
    db.commit()
    return ad_id


def _link(db, ad_id, ents, text, risk):
    """Each new ad links to the EARLIEST ad sharing an identifier (star shape, so graphs stay readable)."""
    linked = set()
    for et, v in ents:
        row = db.execute('SELECT e.ad_id FROM entities e JOIN ads a ON a.id=e.ad_id WHERE e.entity_type=? AND '
                         'e.normalized_value=? AND e.ad_id<>? ORDER BY a.created_at, a.id LIMIT 1',
                         (et, v, ad_id)).fetchone()
        if row:
            linked.add(row['ad_id'])
            db.execute('INSERT INTO relationships VALUES(?,?,?,?,?,?,?)',
                       (nid(), ad_id, row['ad_id'], 'shared_' + et, v,
                        f'Both ads contain the same {et.replace("_", " ")} {v}.', None))
    mine, best = _tokens(text), (0.0, None)
    for r in db.execute('SELECT id, text FROM ads WHERE id<>?', (ad_id,)):
        other = _tokens(r['text'])
        sim = len(mine & other) / len(mine | other) if mine | other else 0
        if sim > best[0]:
            best = (sim, r['id'])
    if best[1] and best[0] >= 0.85 and best[1] not in linked and risk >= 25:
        db.execute('INSERT INTO relationships VALUES(?,?,?,?,?,?,?)',
                   (nid(), ad_id, best[1], 'text_similarity', f'{best[0]:.2f}',
                    'The ad text is almost identical to another ad.', round(best[0], 2)))


def campaigns(db):
    ads = {r['id']: r for r in db.execute('SELECT id, created_at, risk_score, risk_category FROM ads')}
    parent = {i: i for i in ads}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in db.execute('SELECT source_ad_id s, target_ad_id t FROM relationships'):
        if r['s'] in parent and r['t'] in parent:
            parent[find(r['s'])] = find(r['t'])
    groups = {}
    for i in ads:
        groups.setdefault(find(i), []).append(i)
    out = []
    for g in groups.values():
        if len(g) < 2 or max(ads[i]['risk_score'] for i in g) < 25:
            continue
        g.sort(key=lambda i: (ads[i]['created_at'], i))
        out.append({'id': 'cluster-' + g[0][:8], 'label': f'Potentially coordinated cluster ({len(g)} ads)',
                    'member_count': len(g), 'high_risk_count': sum(ads[i]['risk_category'] in HIGH for i in g),
                    'max_risk_score': max(ads[i]['risk_score'] for i in g), 'member_ids': g})
    out.sort(key=lambda c: (-c['member_count'], c['id']))
    return out


def campaign_of(db, ad_id):
    return next((c['id'] for c in campaigns(db) if ad_id in c['member_ids']), None)


def _alerts(db, ad_id, res, ents, ts):
    cid = campaign_of(db, ad_id)

    def add(key, atype, sev, reason):
        db.execute('INSERT OR IGNORE INTO alerts VALUES(?,?,?,?,?,?,?,?,?)',
                   (nid(), key, atype, sev, ad_id, cid, reason, 0, ts))
    if res['risk_category'] in HIGH:
        top = ', '.join(s['title'] for s in res['signals'][:2])
        add('high:' + ad_id, 'high_risk_score', res['risk_category'],
            f"New ad scored {res['risk_category']} ({res['risk_score']}). Main signals: {top}.")
    for et, v in ents:
        n = db.execute('SELECT COUNT(DISTINCT ad_id) FROM entities WHERE entity_type=? AND normalized_value=?',
                       (et, v)).fetchone()[0]
        if n in (3, 5, 10, 20):
            add(f'rep:{et}:{v}:{n}', 'repeated_entity', 'HIGH' if n >= 5 else 'MEDIUM',
                f'{et.replace("_", " ").title()} {v} now appears in {n} ads. Repeated identifiers are leads, not proof.')


def _rel(r):
    return {k: r[k] for k in ('id', 'source_ad_id', 'target_ad_id', 'relationship_type', 'evidence',
                              'explanation', 'similarity_score')}


def summary(db, r):
    return {'id': r['id'], 'is_seed': bool(r['is_seed']), 'text': r['text'], 'source': r['source'],
            'source_url': r['source_url'], 'analysis_status': r['analysis_status'],
            'review_status': r['review_status'], 'risk_score': r['risk_score'], 'risk_category': r['risk_category'],
            'created_at': r['created_at'],
            'entity_count': db.execute('SELECT COUNT(*) FROM entities WHERE ad_id=?', (r['id'],)).fetchone()[0],
            'related_count': db.execute('SELECT COUNT(*) FROM relationships WHERE source_ad_id=? OR target_ad_id=?',
                                        (r['id'], r['id'])).fetchone()[0]}


def relationships_of(db, ad_id):
    return [_rel(r) for r in db.execute('SELECT * FROM relationships WHERE source_ad_id=? OR target_ad_id=?', (ad_id, ad_id))]


def detail(db, ad_id):
    r = db.execute('SELECT * FROM ads WHERE id=?', (ad_id,)).fetchone()
    if not r:
        return None
    d = summary(db, r)
    d.update(image_filename=r['image_filename'], ocr_text=r['ocr_text'], ocr_status=r['ocr_status'],
             limitations=r['limitations'], recommendation=r['recommendation'], analyzed_at=r['analyzed_at'],
             missing_data_warnings=[w for w in (r['warnings'] or '').split('\n') if w], anomalies=[],
             entities=[{k: e[k] for k in ('id', 'entity_type', 'raw_value', 'normalized_value', 'source_text',
                                          'extraction_method', 'confidence')}
                       for e in db.execute('SELECT * FROM entities WHERE ad_id=?', (ad_id,))],
             signals=[{k: s[k] for k in ('id', 'signal_type', 'title', 'explanation', 'evidence', 'contribution',
                                         'recommendation')}
                      for s in db.execute('SELECT * FROM signals WHERE ad_id=? ORDER BY contribution DESC', (ad_id,))],
             notes=[{k: n[k] for k in ('id', 'content', 'created_at')}
                    for n in db.execute('SELECT * FROM notes WHERE ad_id=? ORDER BY created_at DESC', (ad_id,))],
             relationships=relationships_of(db, ad_id))
    return d


def list_ads(db, q=None, risk=None, review_status=None, page=1, page_size=12):
    where, args = ['1=1'], []
    if q:
        where.append('text LIKE ?'); args.append(f'%{q}%')
    if risk:
        where.append('risk_category=?'); args.append(risk.upper())
    if review_status:
        where.append('review_status=?'); args.append(review_status)
    w = ' AND '.join(where)
    total = db.execute(f'SELECT COUNT(*) FROM ads WHERE {w}', args).fetchone()[0]
    rows = db.execute(f'SELECT * FROM ads WHERE {w} ORDER BY created_at DESC, id LIMIT ? OFFSET ?',
                      args + [page_size, (page - 1) * page_size]).fetchall()
    return {'items': [summary(db, r) for r in rows], 'total': total, 'page': page, 'page_size': page_size}


def alert_dict(r):
    return {'id': r['id'], 'alert_type': r['alert_type'], 'severity': r['severity'],
            'advertisement_id': r['advertisement_id'], 'campaign_id': r['campaign_id'], 'reason': r['reason'],
            'is_read': bool(r['is_read']), 'created_at': r['created_at']}


def list_alerts(db, unread_only=False, limit=None):
    sql = 'SELECT * FROM alerts' + (' WHERE is_read=0' if unread_only else '') + ' ORDER BY created_at DESC, rowid DESC'
    if limit:
        sql += f' LIMIT {int(limit)}'
    return [alert_dict(r) for r in db.execute(sql)]


def dashboard(db):
    one = lambda sql: db.execute(sql).fetchone()[0]
    dist = {k: 0 for k in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')}
    for r in db.execute('SELECT risk_category, COUNT(*) n FROM ads GROUP BY risk_category'):
        dist[r['risk_category']] = r['n']
    recent = db.execute('SELECT * FROM ads ORDER BY created_at DESC LIMIT 6').fetchall()
    return {'total_advertisements': one('SELECT COUNT(*) FROM ads'),
            'potentially_suspicious': one("SELECT COUNT(*) FROM ads WHERE risk_category<>'LOW'"),
            'high_risk': one("SELECT COUNT(*) FROM ads WHERE risk_category IN ('HIGH','CRITICAL')"),
            'relationship_count': one('SELECT COUNT(*) FROM relationships'),
            'seed_advertisement_count': one('SELECT COUNT(*) FROM ads WHERE is_seed=1'),
            'risk_distribution': dist, 'recent_advertisements': [summary(db, r) for r in recent],
            'recent_alerts': list_alerts(db, limit=5), 'campaign_activity': campaigns(db)[:6]}


def campaign_detail(db, cid):
    c = next((x for x in campaigns(db) if x['id'] == cid), None)
    if not c:
        return None
    ids = c['member_ids']
    ph = ','.join('?' * len(ids))
    ads = db.execute(f'SELECT * FROM ads WHERE id IN ({ph}) ORDER BY created_at', ids).fetchall()
    rels = db.execute(f'SELECT * FROM relationships WHERE source_ad_id IN ({ph}) AND target_ad_id IN ({ph})', ids + ids)
    return dict(c, advertisements=[summary(db, r) for r in ads], relationships=[_rel(r) for r in rels])


def set_review(db, ad_id, status):
    if status not in REVIEW or not db.execute('SELECT 1 FROM ads WHERE id=?', (ad_id,)).fetchone():
        return None
    db.execute('UPDATE ads SET review_status=? WHERE id=?', (status, ad_id))
    db.commit()
    return detail(db, ad_id)


def add_note(db, ad_id, content):
    if not db.execute('SELECT 1 FROM ads WHERE id=?', (ad_id,)).fetchone():
        return None
    n = {'id': nid(), 'content': content.strip(), 'created_at': now_iso()}
    db.execute('INSERT INTO notes VALUES(?,?,?,?)', (n['id'], ad_id, n['content'], n['created_at']))
    db.commit()
    return n


def mark_alert(db, alert_id, is_read):
    db.execute('UPDATE alerts SET is_read=? WHERE id=?', (int(is_read), alert_id))
    db.commit()
    r = db.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone()
    return alert_dict(r) if r else None
