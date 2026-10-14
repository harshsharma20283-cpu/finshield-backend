import re
from extract import extract_entities

I = re.I
OFFER_WORDS = r'(?:available|sale|sell|selling|buy|give|dena|chahiye|dm|rate)'
# (slug, title, pattern, points, what an investigator should verify)
SIGNALS = [
    ('account_rent_sale', 'Account rent or sale offered',
     re.compile(r'(?=.*\b(?:current\s+|savings\s+|bank\s+|corporate\s+)?accounts?\b)(?=.*\b(?:rent|rental|sale|sell|selling|buy|available|bikau|kiraye|chahiye)\b)', I | re.S), 30,
     'Check whether the advertiser is asking people to hand over their own bank account.'),
    ('card_offered', 'Card offered or requested',
     re.compile(r'(?:\b' + OFFER_WORDS + r'\b.*\b(?:atm|debit|credit)\s*cards?\b|\b(?:atm|debit|credit)\s*cards?\b.*\b' + OFFER_WORDS + r'\b)', I | re.S), 20,
     'Confirm whether physical cards or card details are being traded.'),
    ('banking_kit', 'Passbook, KYC or net banking handed over',
     re.compile(r'\b(?:passbook|cheque\s*book|net\s*banking|kyc\s*(?:done|docs)|sim\s*card)\b', I), 10,
     'Account kits (passbook, net banking, KYC) are typical of mule account sales.'),
    ('easy_earnings', 'Daily or easy earnings promised',
     re.compile(r'\b(?:earn|kamao|commission|rozana|per\s+day|a\s+day|/day|daily)\b', I), 15,
     'Unrealistic daily earnings are a common lure.'),
    ('upfront_fee', 'Upfront fee or payment demanded',
     re.compile(r'\b(?:upfront|advance|registration\s+fee|processing\s+fee|token)\b', I), 10,
     'Check whether payment is requested before any service is delivered.'),
    ('recovery_for_fee', 'Recovery or refund service for a fee',
     re.compile(r'\b(?:recover|recovery|restore|refund)\b.*\b(?:wallets?|funds?|money|accounts?)\b', I | re.S), 30,
     'Recovery services that charge in advance are a known scam pattern.'),
]
WARN_RE = re.compile(r"\b(?:never|do not|don't|dont|avoid|beware|be careful|stay safe|fraud alert|warning|report)\b", I)
OFFER_SLUGS = {'account_rent_sale', 'card_offered', 'easy_earnings', 'recovery_for_fee'}


def label_for(score: int) -> str:
    return 'LOW' if score < 25 else 'MEDIUM' if score < 50 else 'HIGH' if score < 75 else 'CRITICAL'


def score_ad(text: str) -> dict:
    ents = extract_entities(text)
    sig = []
    for slug, title, pat, pts, rec in SIGNALS:
        m = pat.search(text)
        if m:
            sig.append({'signal_type': slug, 'title': title, 'contribution': pts, 'recommendation': rec,
                        'evidence': re.sub(r'\s+', ' ', m.group(0))[:80].strip()})
    for key, title, pts, vals in (('phone_present', 'Phone number present', 10, ents['phones']),
                                  ('upi_present', 'UPI ID present', 10, ents['upi_ids']),
                                  ('link_present', 'Link present', 5, ents['urls'])):
        if vals:
            sig.append({'signal_type': key, 'title': title, 'contribution': pts, 'evidence': vals[0],
                        'recommendation': 'Check this identifier against other advertisements.'})
    total = sum(s['contribution'] for s in sig)
    safety = bool(WARN_RE.search(text)) and not ({s['signal_type'] for s in sig} & OFFER_SLUGS)
    if safety:
        total = min(total, 10)
        sig = [{'signal_type': 'safety_notice', 'title': 'Safety notice (warns, does not sell)', 'contribution': 0,
                'evidence': WARN_RE.search(text).group(0), 'recommendation': 'No action needed.'}]
    for s in sig:
        s['explanation'] = f"{s['title']}: matched '{s['evidence']}' ({s['contribution']:+d} points)."
    total = min(total, 100)
    return {'risk_score': total, 'risk_category': label_for(total), 'signals': sig,
            'entities': ents, 'is_safety_notice': safety}