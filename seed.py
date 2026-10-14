import random
from datetime import datetime, timedelta, timezone
from db import connect, init_db
from core import analyze_and_store

BANKS = ['SBI', 'HDFC', 'ICICI', 'Axis', 'PNB', 'Kotak', 'Canara', 'Bank of Baroda']
AMT = [2000, 2500, 3000, 4000, 5000]
G1 = ['{b} current account on rent? Earn Rs {a} a day. Just give account and ATM card. WhatsApp {p}, UPI {u}',
      'Bhai {b} account kiraye pe chahiye, rozana Rs {a} kamao. Passbook aur net banking chahiye. DM {p}',
      'URGENT: savings account rent par lete hain, commission Rs {a} per day, KYC done account only. Call {p}',
      'Earn without any work! Give your {b} account for rent, payment daily on UPI {u}. Contact {p}',
      'Account rent karo aur ghar baithe kamao. {b} ya {b} chalega, Rs {a} per day. {p}']
G2 = ['{b} ATM card + passbook + cheque book set available, ready account. DM {p} for rate',
      'Bank account bikau hai {b}, net banking set hai, sirf Rs {a}. t.me/cardkit_hub or {p}',
      'Selling fresh {b} debit card with sim linked, KYC done. WhatsApp {p}']
G3 = ['Crypto recovery agent can restore frozen wallets after an upfront fee. UPI {u}. WhatsApp {p}',
      'Lost money in a scam? We recover funds, registration fee Rs {a}, pay on UPI {u}',
      'Refund guaranteed for blocked bank account, processing fee Rs {a}. Pay {u} and share screenshot']
G4 = ['Current account for GST firms available, {b}, ready docs. Rs {a} per account. Call {p}',
      'Corporate current account on sale with GST and KYC done, {b}. Pay token Rs 500 on {u}. {p}']
SINGLE = ['Need quick Rs 5000? Rent your savings account for a week, earn daily. Telegram t.me/quickrentzone',
          'Sell your old bank account, we pay cash today. Call 90000 44404',
          'Credit card limit sale, 50 percent off! UPI offers@oksbi pay Rs 999 advance',
          'Bank account chahiye, per day Rs 2500 commission, WhatsApp 90000 55505',
          'Debit card with net banking available, serious buyers only. 90000 66606',
          'Account rent karo aur ghar baithe kamao, DM karo']
BENIGN = ['{b} has launched a new savings account with zero balance. Visit your nearest branch to know more.',
          'Enable spending alerts in the mobile app. Never share OTP, PIN, or CVV with anyone.',
          'Beware of fake KYC calls. Banks never ask for your card number over the phone.',
          'Compare fixed deposit rates this month. Terms and conditions apply.',
          'Apply for a home loan online. Check eligibility on the official {b} website.',
          'Reminder: update your KYC at the branch with original documents.',
          'Fraud alert: do not share your UPI PIN. Report suspicious messages to your bank.',
          'Open a current account for your business by meeting a relationship manager at the branch.',
          'Credit card annual fee waiver on spends above Rs 50,000. Offer valid till month end.',
          'Tips to protect your bank account from phishing: never click unknown links.']
GANGS = [(G1, '90000 11101', 'earn.fast@upi', 9), (G2, '90000 22202', None, 7),
         (G3, '90000 33303', 'quickcash.hub@okaxis', 5), (G4, '90000 44404', 'gst.current@ybl', 6)]


def build():
    r, out = random.Random(11), []
    for tpl, p, u, n in GANGS:
        for i in range(n):
            t = tpl[i % len(tpl)].format(b=r.choice(BANKS), a=r.choice(AMT), p=p, u=u or '')
            out.append(t if u or '{u}' not in tpl[i % len(tpl)] else t)
    out += SINGLE
    for i in range(28):
        out.append(BENIGN[i % len(BENIGN)].format(b=BANKS[i % len(BANKS)]) + ('' if i < 10 else f' ({BANKS[i % 8]} notice)'))
    r.shuffle(out)
    return out


def seed(db):
    if db.execute('SELECT 1 FROM ads WHERE is_seed=1').fetchone():
        return 0
    texts, base = build(), datetime.now(timezone.utc) - timedelta(hours=60)
    rng, t = random.Random(5), base
    for text in texts:
        t += timedelta(minutes=rng.randint(20, 90))
        analyze_and_store(db, text, source=rng.choice(['Instagram', 'Telegram', 'WhatsApp']), is_seed=True,
                          created_at=t.isoformat(timespec='seconds'))
    return len(texts)


if __name__ == '__main__':
    c = connect(); init_db(c); print('seeded', seed(c))
