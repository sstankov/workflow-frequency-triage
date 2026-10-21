"""Shared artifact encoding, including spreadsheet formula protection."""
import csv
import hashlib
import json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def write_csv(path,records):
    if not records:
        path.write_text('flow_id\n',encoding='utf-8')
        return
    with path.open('w',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            values = {k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in record.items()}
            # Quoting alone does not prevent spreadsheet formula execution.
            values = {k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in values.items()}
            writer.writerow(values)
