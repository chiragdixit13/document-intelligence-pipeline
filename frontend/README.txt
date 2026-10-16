INVOICE INTELLIGENCE FRONTEND

1. Put index.html, style.css, and script.js together inside your frontend folder.
2. Start your existing backend from the directory containing api.py:
   uvicorn api:app --reload
3. Make sure FastAPI CORS allows your frontend's exact origin. VS Code Live Server commonly uses:
   http://127.0.0.1:5500
   http://localhost:5500
   Add whichever exact origin appears in the browser address bar.
4. Open index.html using VS Code Live Server.

Expected endpoints:
GET /invoices -> JSON array of invoice objects
POST /upload_pdf -> multipart field named "file"
POST /invoices/{invoice_id}/review -> JSON {"decision":"approved","reviewed_by":"Reviewer"}

This is a functional local prototype, not a secured production approval system. Add authentication and server-side permission checks before deployment.
