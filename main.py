from invoice_processor import (
    llm_process,
    pdf_loading,
    processed_invoices
)
from pathlib import Path
from datetime import datetime
import json
import psycopg
from psycopg.types.json import Jsonb


# multiple pdfs function

def pdf_paths():
    return list(Path("invoices").glob("*.pdf"))

#
def process_pdf(pdf_path):

    pdf_text=pdf_loading(pdf_path)
    result=llm_process(pdf_text)

    result["file"]=str(pdf_path)
    return result


processed_invoices.clear()
batch_result=[]
for pdf_path in pdf_paths():

    try:
        response=process_pdf(pdf_path)
        print(response)
        batch_result.append(response)    
    except Exception as e:
        batch_result.append({
            "file":str(pdf_path),
            "validation_status":"failed",
            "message":str(e)
        })
        print(f"Failed to process{pdf_path}:{e}") 


print("\n-----BATCH SUMMARY-----")   
print("total processed",len(batch_result))  



for status in ["Auto Approval Eligible","Manager Approval","Finance Manager Approval","Needs review","failed"]:
    count=sum(
        1 for result in batch_result
        if result.get("validation_status")==status

    )
    print(f"{status.title()}:{count}")
    if status in["Manager Approval","Finance Manager Approval"] and count>0:
            review=input(f"{status}- type Approve or reject:").lower().strip()
            if review=="approve":
                decision="Approved"
                decision_by=status
                
            elif review=="reject":
                decision="Rejected"
                decision_by=status

            else:
                print("Invalid response. Decision unchanged")
                continue
            if status=="Manager Approval":
                decision_by="Manager"
            else:
                decision_by="Finance Manager"

                  

            for result in batch_result:
                if result.get("validation_status")==status:
                    result["approval_level"]=status
                    result["validation_status"]=decision
                    result["approval_decision"]=decision
                    result["reviewed_by"]=decision_by
                    result["reviewed_at"]=datetime.now().isoformat()

print(batch_result)


with open("invoice_results.json","w")as file:

    json.dump(batch_result,file,indent=4)                    
                

connection={"host":"localhost",
            "port":5432,
            "dbname":"invoice_intelligence",
            "user":"postgres",
            "password":"1234"}    

conn=psycopg.connect(**connection)
print("Postgresql connected successfully")

cursor=conn.cursor()
for result in batch_result:
        cursor.execute( """
            INSERT INTO invoices (
                    invoice_number,
                    vendor,
                    amount,
                    tax,
                    total,
                    validation_status,
                    approval_decision,
                    approval_level,
                    reviewed_by,
                    reviewed_at,
                    reason,
                    evidence,
                    file,
                    processed_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s

                )
                ON CONFLICT (vendor, invoice_number) DO NOTHING
                """,
                (
                    result.get("invoice_number"),
                    result.get("vendor"),
                    result.get("amount"),
                    result.get("tax"),
                    result.get("total"),
                    result.get("validation_status", "Needs review"),
                    result.get("approval_decision"),
                    result.get("approval_level"),
                    result.get("reviewed_by"),
                    result.get("reviewed_at"),
                    result.get("reason", result.get("message", "No reason provided")),
                    Jsonb(result.get("evidence", {})),
                    result.get("file"),
                    result.get("processed_at")
                    
                )
            )
        conn.commit()
        print("invoice inserted successfully")
