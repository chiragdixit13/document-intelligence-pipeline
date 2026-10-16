from fastapi import FastAPI,Depends
from langchain_community.document_loaders import PyPDFLoader
import tempfile
from fastapi import UploadFile,File,HTTPException
import psycopg
import os
from dotenv import load_dotenv
from typing import Generator
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from invoice_processor import llm_process
app=FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



load_dotenv()
print("ENV loaded:", os.getenv("DB_PASSWORD") is not None)

connection = {
    "host": "localhost",
    "port": 5432,
    "dbname": "invoice_intelligence",
    "user": "postgres",
    "password": os.getenv("DB_PASSWORD")
}
def get_db():
    conn=psycopg.connect(**connection)
    print("Database connected successfully")
    try:
        yield conn
    finally:
        conn.close()
    

@app.get("/invoices/{invoice_id}")

def get_invoices(invoice_id:int,conn=Depends(get_db)):
    with conn.cursor() as cursor:
        cursor.execute("Select * from invoices where invoice_id=%s",(invoice_id,))
        columns = [column[0] for column in cursor.description]
            

        show=cursor.fetchone()

    if not show:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )
    return dict(zip(columns,show))





@app.get("/invoices")
def get_all_invoices(conn=Depends(get_db)):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM invoices
            ORDER BY invoice_id DESC
        """)

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        return [
            dict(zip(columns, row))
            for row in rows
        ]


    
@app.post("/upload_pdf")
async def upload(file: UploadFile=File(...),conn=Depends(get_db)):
    if file.content_type!=("application/pdf"):
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are allowed"
        )
     
    try:
        content=await file.read()
        temp_file=tempfile.NamedTemporaryFile(suffix=".pdf",delete=False)

        temp_file.write(content)
        name=temp_file.name
        loader=PyPDFLoader(name)
        temp_file.close()
        documents=loader.load()
        
        
        document="\n".join(doc.page_content for doc in documents)
        
        result = llm_process(document)
        if result.get("validation_status") == "failed":
            return result


        with conn.cursor() as cursor:

            cursor.execute("""
                INSERT INTO invoices (
                    invoice_number, vendor, amount, tax, total,
                    validation_status, approval_decision, approval_level,
                    reason, evidence, file, processed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING invoice_id
            """, (
                result["invoice_number"],
                result["vendor"],
                result["amount"],
                result["tax"],
                result["total"],
                result["validation_status"],
                "pending",
                result["approval_level"],
                result.get("reason"),
                Jsonb(result["evidence"]),
                file.filename,
                result["processed_at"]
            ))

            invoice_id = cursor.fetchone()[0]
        conn.commit()

        result["invoice_id"] = invoice_id
        
        return result
    
    except UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Invoice already exists")
    except Exception as e:
        if 'name' in locals() and os.path.exists(name):    
            os.remove(name)
        conn.rollback()
        raise HTTPException(status_code=500,detail="Invoice processing failed")
    finally:
        if 'name' in locals() and os.path.exists(name):
            os.remove(name)



class InvoiceReview(BaseModel):
    decision:str
    reviewed_by:str
@app.post("/invoices/{invoice_id}/review")
def review(invoice_id: int, review_data: InvoiceReview, conn=Depends(get_db)):
    if review_data.decision not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="Decision must be approved or rejected"
        )

    with conn.cursor() as cursor:
        # 1. Check the existing decision
        cursor.execute(
            "SELECT approval_decision FROM invoices WHERE invoice_id = %s",
            (invoice_id,)
        )
        existing = cursor.fetchone()

        # 2. Check whether the invoice exists
        if existing is None:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # 3. Prevent reviewing an already-reviewed invoice
        if existing[0] in ["approved", "rejected"]:
            raise HTTPException(
                status_code=409,
                detail="Invoice already reviewed"
            )

        # 4. Update the invoice
        cursor.execute("""
            UPDATE invoices
            SET approval_decision = %s,
                reviewed_by = %s,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE invoice_id = %s
            RETURNING invoice_id
        """, (
            review_data.decision,
            review_data.reviewed_by,
            invoice_id
        ))

    # 5. Save the changes
    conn.commit()

    return {
        "message": "Invoice reviewed successfully",
        "invoice_id": invoice_id,
        "decision": review_data.decision
    }
    

            
    

