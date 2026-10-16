const API_URL = "http://127.0.0.1:8000";
const $ = id => document.getElementById(id);
let invoices = [];
let currentView = "all";

function makeCell(value, className = "") {
  const td = document.createElement("td");
  td.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  if (className) td.className = className;
  return td;
}
function badge(value) {
  const span = document.createElement("span");
  const raw = String(value ?? "unknown");
  const normalized = raw.toLowerCase();
  span.className = "badge " + (["pending","approved","rejected","valid","failed","invalid"].includes(normalized) ? normalized : "neutral");
  span.textContent = raw;
  return span;
}
function updateCounts() {
  $("total-count").textContent = invoices.length;
  $("pending-count").textContent = invoices.filter(i => String(i.approval_decision ?? "pending").toLowerCase() === "pending").length;
  $("approved-count").textContent = invoices.filter(i => String(i.approval_decision ?? "").toLowerCase() === "approved").length;
  $("rejected-count").textContent = invoices.filter(i => String(i.approval_decision ?? "").toLowerCase() === "rejected").length;
}
function render() {
  const q = $("search").value.trim().toLowerCase();
  const filter = $("status-filter").value;
  const shown = invoices.filter(i => {
    const decision = String(i.approval_decision ?? "pending").toLowerCase();
    const matchesText = [i.invoice_id, i.invoice_number, i.vendor]
      .some(v => String(v ?? "").toLowerCase().includes(q));
    const matchesStatus = filter === "all" || decision === filter;
    const matchesView = currentView !== "history" || ["approved", "rejected"].includes(decision);
    return matchesText && matchesStatus && matchesView;
  });
  const tbody = $("invoice-rows");
  tbody.replaceChildren();
  if (!shown.length) {
    const tr = document.createElement("tr");
    const td = makeCell(invoices.length ? "No matching invoices." : "No invoices yet. Upload a PDF to get started.", "empty");
    td.colSpan = 7; tr.appendChild(td); tbody.appendChild(tr); return;
  }
  shown.forEach(i => {
    const tr = document.createElement("tr");
    tr.appendChild(makeCell(i.invoice_id));
    tr.appendChild(makeCell(i.invoice_number));
    tr.appendChild(makeCell(i.vendor, "vendor"));
    const total = i.total == null ? "—" : "₹" + Number(i.total).toLocaleString("en-IN", {minimumFractionDigits:2, maximumFractionDigits:2});
    tr.appendChild(makeCell(total, "money"));
    const val = document.createElement("td"); val.appendChild(badge(i.validation_status)); tr.appendChild(val);
    const decision = String(i.approval_decision ?? "pending").toLowerCase();
    const dec = document.createElement("td"); dec.appendChild(badge(decision)); tr.appendChild(dec);
    const action = document.createElement("td");
    if (["approved","rejected"].includes(decision)) {
      const done = document.createElement("span"); done.className = "badge neutral"; done.textContent = "Reviewed"; action.appendChild(done);
    } else if (decision === "pending") {
      const box = document.createElement("div"); box.className = "actions";
      const yes = document.createElement("button"); yes.className = "action approve"; yes.textContent = "Approve"; yes.type = "button";
      const no = document.createElement("button"); no.className = "action reject"; no.textContent = "Reject"; no.type = "button";
      yes.addEventListener("click", () => review(i.invoice_id, "approved", yes, no));
      no.addEventListener("click", () => review(i.invoice_id, "rejected", yes, no));
      box.append(yes, no); action.appendChild(box);
    } else action.textContent = "—";
    tr.appendChild(action); tbody.appendChild(tr);
  });
}
async function loadInvoices() {
  $("notice").className = "notice"; $("notice").textContent = "Loading invoices…"; $("refresh").disabled = true;
  try {
    const response = await fetch(`${API_URL}/invoices`);
    if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error("/invoices must return a JSON array.");
    invoices = data; updateCounts(); render();
    $("notice").textContent = `${invoices.length} invoice(s) loaded.`;
    $("api-state").textContent = "● API connected"; $("api-state").style.color = "#16845b";
  } catch (e) {
    console.error(e); $("notice").className = "notice error";
    $("notice").textContent = "Could not load invoices. Check FastAPI and CORS.";
    $("api-state").textContent = "● API unavailable"; $("api-state").style.color = "#c24141";
    $("invoice-rows").replaceChildren();
    const tr = document.createElement("tr"), td = makeCell("Could not retrieve invoices. See browser console for details.", "empty");
    td.colSpan = 7; tr.appendChild(td); $("invoice-rows").appendChild(tr);
  } finally { $("refresh").disabled = false; }
}
async function review(id, decision, yes, no) {
  const reviewer = prompt("Reviewer name:");
  if (!reviewer || !reviewer.trim()) return;
  if (!confirm(`Confirm ${decision} for invoice ${id}?`)) return;
  yes.disabled = no.disabled = true;
  try {
    const response = await fetch(`${API_URL}/invoices/${encodeURIComponent(id)}/review`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({decision, reviewed_by: reviewer.trim()})
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Review failed (${response.status})`);
    alert(`Invoice ${id} ${decision} successfully.`); await loadInvoices();
  } catch (e) { alert(e.message || "Review failed."); yes.disabled = no.disabled = false; }
}
$("upload-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = $("pdf-file").files[0];
  if (!file) return uploadMessage("Choose a PDF first.", true);
  if (!(file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))) return uploadMessage("Only PDF files are allowed.", true);
  const form = new FormData(); form.append("file", file);
  $("upload-btn").disabled = true; uploadMessage("Uploading and processing PDF…");
  try {
    const response = await fetch(`${API_URL}/upload_pdf`, {method:"POST", body:form});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Upload failed (${response.status})`);
    if (result.invoice_id !== undefined) {
      uploadMessage(`Processed and saved. Invoice ID: ${result.invoice_id}`);
      $("upload-form").reset(); $("file-name").textContent = "No file selected"; await loadInvoices();
    } else uploadMessage(result.message || result.detail || "The processor did not save this invoice. Check its validation result.", true);
  } catch (e) { uploadMessage(e.message || "Upload failed. Check API and CORS.", true); }
  finally { $("upload-btn").disabled = false; }
});
function uploadMessage(message, error = false) {
  $("upload-message").textContent = message;
  $("upload-message").className = "show" + (error ? " error" : "");
}
$("pdf-file").addEventListener("change", () => $("file-name").textContent = $("pdf-file").files[0]?.name || "No file selected");
$("search").addEventListener("input", render);
$("refresh").addEventListener("click", loadInvoices);
function setInvoiceView(view, filter = "all") {
  currentView = view;
  $("status-filter").value = filter;
  render();
  $("invoices").scrollIntoView({ behavior: "smooth", block: "start" });
}

// Sidebar navigation: Dashboard, All Invoices, Pending Reviews, and Review History.
document.querySelectorAll(".sidebar nav a").forEach(link => {
  link.addEventListener("click", event => {
    event.preventDefault();
    document.querySelectorAll(".sidebar nav a").forEach(item => item.classList.remove("active"));
    link.classList.add("active");

    const filter = link.dataset.filter;
    if (filter === "pending") setInvoiceView("all", "pending");
    else if (filter === "reviewed" || filter === "history") setInvoiceView("history", "all");
    else if (link.getAttribute("href") === "#invoices") setInvoiceView("all", "all");
    else {
      currentView = "all";
      $("status-filter").value = "all";
      render();
      $("dashboard").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

// Keep the history view active while using the status dropdown.
$("status-filter").addEventListener("change", render);
// Make the four summary cards filter the table when clicked.
const summaryCards = document.querySelectorAll(".stats .card");
const summaryFilters = ["all", "pending", "approved", "rejected"];
summaryCards.forEach((card, index) => {
  card.style.cursor = "pointer";
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");
  const activate = () => {
    document.querySelectorAll(".sidebar nav a").forEach(item => item.classList.remove("active"));
    setInvoiceView("all", summaryFilters[index] || "all");
  };
  card.addEventListener("click", activate);
  card.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
    }
  });
});

if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.querySelectorAll(".card").forEach(card => {
    card.addEventListener("pointermove", event => {
      if (event.pointerType !== "mouse") return;
      const r = card.getBoundingClientRect(), x = (event.clientX-r.left)/r.width, y = (event.clientY-r.top)/r.height;
      card.style.transform = `perspective(850px) rotateX(${(0.5-y)*7}deg) rotateY(${(x-0.5)*7}deg) translateY(-4px)`;
    });
    card.addEventListener("pointerleave", () => card.style.transform = "");
  });
}
loadInvoices();
