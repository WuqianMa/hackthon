from collections import defaultdict
from bankrec.sources import Sources as BaseSources, Group
from bankrec.io import rows, cents, is_data_file, table, norm


class Sources(BaseSources):
    @staticmethod
    def text_advice(text):
        ref, dt, curr, entries = BaseSources.text_advice(text)
        if 'Subject:' in text:
            for e in entries:
                if e['reason'] and e['paid'] != e['gross']:
                    e['paid'] = e['gross'] - e['paid']
        return ref, dt, curr, entries

    def load_batches(self, phase):
        super().load_batches(phase)
        groups = {}
        for f in sorted((phase/'payment_runs').glob('*.csv')):
            if not is_data_file(f):
                continue
            for n, r in enumerate(rows(f),2):
                if r['run_type'] == 'transfers':
                    continue
                key = 'transfer-unit:' + r['debtor_account_id'] + ':' + r['end_to_end_id']
                if key not in groups:
                    groups[key] = Group(key, 'payment_runs', str(f.relative_to(phase)),r['execution_date'],r['currency'],
                        -cents(r['transfer_amount']),r['debtor_account_id'],r['debtor_account_id'].split('-')[0],[],
                        {r['run_id'],r['end_to_end_id']})
                groups[key].entries.append({'doc':r['document_number'],'paid':abs(cents(r['document_amount'])),
                    'credit':cents(r['document_amount'])<0,'name':r['beneficiary'],'iban':r['beneficiary_iban'],
                    'side':'AP','reason':'','source':str(f.relative_to(phase)),'line':n})
        for g in groups.values():
            self.add(g)
        # Confirming debits can consolidate beneficiaries sharing a maturity date.
        # Execution date identifies file preparation; invoice due dates define this level.
        due_index=defaultdict(set)
        invoices=table(phase,'ap_invoices',required=False)
        for invoice in rows(invoices) if invoices else ():
            due_index[(norm(invoice['supplier_invoice_number']),norm(invoice['supplier_name']),invoice['currency'])].add(invoice['due_date'])
        maturities={}
        for g in groups.values():
            dates=[]
            for e in g.entries:
                if e['credit']:
                    continue
                known=due_index.get((norm(e['doc']),norm(e['name']),g.currency),())
                if len(known)==1:
                    dates.extend(known)
            if not dates:
                continue
            maturity=max(dates)
            run=sorted(r for r in g.refs if '-' not in r)[0]
            key='maturity:'+g.account+':'+run+':'+maturity
            if key not in maturities:
                maturities[key]=Group(key,'payment_runs',g.source,maturity,g.currency,0,g.account,g.entity,[],{run})
            maturities[key].cash+=g.cash
            maturities[key].entries.extend(g.entries)
        for g in maturities.values():
            self.add(g)
