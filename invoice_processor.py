from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
import os
from pydantic import BaseModel
import re
import json
from pathlib import Path
from datetime import datetime
import psycopg
from psycopg.types.json import Jsonb


class Invoice(BaseModel):
    invoice_number:str
    vendor:str
    amount:int
    tax:float
    total:float

def invoice_validation_result(invoices):
    required_fields=["invoice_number","vendor","amount","tax","total"]

    for field in required_fields:
        if field not in invoices or invoices[field] is None or invoices[field]=="":
            raise ValueError(f"Missing or empty field{field}")

    return True

# invoice_validation_result(invoice)


def amount_validation(amount,tax,total):
    if amount+tax!=total:
        raise ValueError("Amounts mismatch found")
    return True


# try:
#     result=amount_validation(invoice["amount"],invoice["tax"],invoice["total"])
#     print(result)
# except ValueError as e:
#     print(e)



# checks duplicate invoices entries

processed_invoices=set()

def check_duplicates(invoices):
    invoice_key=(invoices["vendor"],invoices["invoice_number"])
    if invoice_key in processed_invoices :
        raise ValueError("Duplicate invoice detected") 
    




# INCLUDE all  VALIDATIONS

def process_invoice(invoices):
    check_duplicates(invoices)
    invoice_validation_result(invoices)
    amount_validation(
        invoices["amount"],
        invoices["tax"],
        invoices["total"]
    )
    

    
    
    if invoices["total"]<=0:
        raise ValueError("Invoice total must be greater than zero")
    invoice_key = (invoices["vendor"], invoices["invoice_number"])
    processed_invoices.add(invoice_key)

    #  Approval giving

    if invoices["total"]<=10000:
        approval_level= "Auto Approval Eligible"
        reason="Total is within auto-approval limit"
    elif invoices["total"]<=50000:
        approval_level= "Manager Approval"
        reason="Manager approval is required"
    else:
        approval_level= "Finance Manager Approval"
        reason="Finance Manager approval is required"

    return {
        "invoice_number": invoices["invoice_number"],
        "amount": invoices["amount"],
        "vendor": invoices["vendor"],
        "tax": invoices["tax"],
        "total": invoices["total"],
        "validation_status": "valid",
        "message": f"Decision:{approval_level}",
        "approval_level":approval_level,
        "reason":reason,
        "processed_at":datetime.now().isoformat()
    }

# try:
#     result=process_invoice(invoices)
#     print(result)

# except ValueError as e:
#     print(e)    


def handle_invoice_result(invoices):
    try:
        result=process_invoice(invoices)
        return result
    except ValueError as e:
        return {
            "invoice_number":invoices.get("invoice_number"),
            "validation_status":"Needs review",
            "message": str(e)
        }


# pdf loader

def pdf_loading(pdf_path):  
    loader=PyPDFLoader(pdf_path)
    documents=loader.load()

    if not documents:
        raise ValueError("PDF contains no readable pages")
    
    all_text="\n".join(doc.page_content for doc in documents)
    if not all_text:
        raise ValueError("NO readable text.OCR needed")
    return all_text
         
def extract_amounts_from_text(all_text):
    amounts=re.findall(r'\d[\d,]*\.\d{2}',all_text)
    return [float(amount.replace(",","")) for amount in amounts]

def llm_process(all_text):
        llm = ChatOpenAI(
        model="gemma4:31b",
        base_url="https://ollama.com/v1",
        api_key=os.getenv("OLLAMA_API_KEY"),
        temperature=0
        )
        
        prompt=f""" 
        you have to extract the invoice_number ,vendor,amount,tax and total from the following given document content
        it should include all the followings . dont miss single entity

        Vendor: the company issuing the invoice.
        Customer: the company receiving the invoice.
        Amount: subtotal before tax.
        Tax: GST amount.
        Total: final amount due.

        the document content from where the given info to be extracted it is :{all_text}"""

        try:
            str_llm = llm.with_structured_output(Invoice, method="json_schema")
            result = str_llm.invoke(prompt)
            # print(result)
            # print(result.model_dump())

            extracted_invoice=result.model_dump()
            evidence={
                        "invoice_number_found":(
                            extracted_invoice["invoice_number"] in all_text
                        ),
                        "vendor_found":(
                            extracted_invoice["vendor"] in all_text
                        )
                    }
            print(evidence)
            amounts=extract_amounts_from_text(all_text)
            
            def value_check(extracted_invoice, amounts):
                return {
                    "amount_found": extracted_invoice["amount"] in amounts,
                    "tax_found": extracted_invoice["tax"] in amounts,
                    "total_found": extracted_invoice["total"] in amounts
                }
            value_check_result=value_check(extracted_invoice,amounts)
            evidence.update(value_check_result)
            processed=handle_invoice_result(extracted_invoice)
            processed["evidence"]=evidence
            return processed

        except (ValueError,KeyError)as e:
            print(f"Invoice validation Failed:{e}")
            return {
            "validation_status": "failed",
            "message": str(e)
        }