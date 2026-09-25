// LexiGuard Frontend Application
// Real backend integration via FastAPI REST API

// State management
const state = {
  currentView: 'dashboard',
  currentLanguage: 'en',
  currentDocumentId: null,
  currentDocumentName: null,
  documents: [],
  clauses: [],
  signals: [],
  relationships: [],
  financialItems: [],
  entities: { dates: [], monetary_values: [], parties: [], obligations: [] },
  checklist: null,
  conversationHistory: [],
  genaiAvailable: false,
  loading: false,
};

const UI_TRANSLATIONS = {

  "en": {
    "app_title": "LexiGuard — Legal Document Intelligence",
    "dashboard": "Dashboard",
    "analyze": "Analyze",
    "ask": "Ask",
    "compare": "Compare",
    "workspace": "Workspace",
    "prepare": "Prepare",
    "reports": "Reports",
    "reminders": "Reminders & Calendar",
    "overview": "Overview",
    "attention_signals": "Attention Signals",
    "relationships": "Clause Relationships",
    "financial_compensation": "Financial & Compensation",
    "clauses": "Clauses",
    "consistency": "Consistency Engine",
    "view_source": "View Source Clause",
    "view_related": "View Related Clause",
    "explain_ai": "Explain with AI",
    "explain_again": "Explain Again",
    "export_report": "Export Report",
    "export_pdf": "Download PDF Report",
    "export_json": "Export JSON Data",
    "export_ics": "Export Calendar (.ics)",
    "no_results": "No corresponding provisions identified.",
    "insufficient_evidence": "Insufficient evidence in the uploaded document.",
    "potential_asymmetry": "Potential Asymmetry",
    "balanced_relationship": "Balanced Relationship",
    "missing_counterpart": "Missing Counterpart",
    "disclaimer_title": "Legal Disclaimer",
    "disclaimer_text": "LexiGuard provides document analysis and evidence-grounded explanations. It does not provide legal advice.",
    "hero_title": "Understand your legal documents",
    "hero_subtitle": "See the risks. Ask better questions. Stay protected.",
    "upload_title": "Drag & drop your document here",
    "upload_hint": "Supports PDF, DOCX, TXT up to 10MB",
    "browse_files": "Browse Files",
    "recent_documents": "Recent Documents",
    "documents": "Documents",
    "upload": "Upload",
    "open": "Open",
    "delete": "Delete",
    "pages": "Pages",
    "financial_items": "Financial Items",
    "generate_summary": "Generate Summary",
    "ai_summary": "AI Summary",
    "doc_map": "Document Map",
    "important_dates": "Important Dates",
    "key_obligations": "Key Obligations",
    "ask_title": "Ask a question about your document",
    "ask_placeholder": "Type your legal question here...",
    "send": "Send",
    "compare_docs": "Compare Documents",
    "orig_doc": "Original Document (Doc A)",
    "revised_doc": "Revised Document (Doc B)",
    "btn_compare": "Compare Documents",
    "added": "Added",
    "removed": "Removed",
    "modified": "Modified",
    "unchanged": "Unchanged",
    "prep_review": "Preparation & Review",
    "gen_checklist": "Generate Legal Review Checklist",
    "copy_clipboard": "Copy to Clipboard",
    "evidence_viewer": "Document Evidence Viewer",
    "doc_overview_title": "Document Understanding Overview",
    "risk_signals": "Risk Signals",
    "monetary_values": "Monetary Values",
    "contracting_parties": "Contracting Parties",
    "dates_temporal_title": "Important Dates & Temporal Obligations",
    "review": "Review",
    "confirm_obligation": "Confirm Obligation",
    "track_date": "Track Important Date",
    "view_in_doc": "View in document",
    "why_seeing_this": "WHY AM I SEEING THIS? ▼",
    "hide_explanation": "HIDE EXPLANATION ▲",
    "suggested_verification": "Suggested Verification Question",
    "general_review": "General Review",
    "payment_terms": "Payment Terms",
    "lawyer_questions": "Questions for Lawyer",
    "explanation_provenance": "EXPLANATION & PROVENANCE ▼",
    "source_clause": "Source Clause",
    "related_clause": "Related Clause",
    "related_counterpart": "Related Counterpart",
    "pg_abbrev": "Pg",
    "right_condition": "Right Condition",
    "left_condition": "Left Condition",
    "potential_conflict": "Potential Conflict",
    "no_relationships_detected": "No meaningful clause relationships were identified in this document.",
    "no_clauses_available": "No clauses available.",
    "no_changes_for_filter": "No changes found for the selected filter.",
    "generating": "Generating...",
    "explaining": "Explaining...",
    "ai_analysis_badge": "AI RELATIONSHIP ANALYSIS",
    "no_explanation_generated": "No detailed explanation generated.",
    "ai_error_badge": "AI EXPLANATION ERROR",
    "financial_change_label": "Financial Change",
    "relationship_impact_label": "Structural / Relationship Impact",
    "original_doc_a": "Original (Doc A)",
    "revised_doc_b": "Revised (Doc B)",
    "view_doc_a": "View A",
    "view_doc_b": "View B",
    "explain_change_ai": "Explain Change with AI",
    "no_signals_detected": "No attention signals or high-risk patterns detected in this document.",
    "none_detected": "None detected",
    "section": "Section",
    "page": "Page",
    "amount": "Amount",
    "currency": "Currency",
    "frequency": "Frequency",
    "effective_date": "Effective Date",
    "timing": "Payment Timing",
    "condition": "Condition",
    "not_specified": "Not specified",
    "no_financial_detected": "No financial or compensation items were detected.",
    "completeness_observation": "Completeness Observation",
    "supporting_citations": "Supporting Citations / Evidence:",
    "suggested_followup_label": "Suggested follow-up"
  }
};


function t(key) {
  const dict = UI_TRANSLATIONS['en'] || {};
  return dict[key] || key;
}

// Prevents hashchange re-entry when navigate() itself changes the hash
let _suppressNextHashChange = false;

// In-flight guard: prevents concurrent loadDocumentAnalysis for the same docId
let _analysisInFlight = null;

// Helper function to safely clear element contents
function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

// Helper function to create DOM elements with textContent (XSS defense)
function createElement(tag, options = {}, children = []) {
  const el = document.createElement(tag);
  if (options.className) el.className = options.className;
  if (options.text !== undefined && options.text !== null) el.textContent = String(options.text);
  if (options.attrs) {
    for (const [key, val] of Object.entries(options.attrs)) {
      el.setAttribute(key, val);
    }
  }
  const childList = Array.isArray(children) && children.length > 0 ? children : (options.children || []);
  for (const child of childList) {
    if (child) el.appendChild(child);
  }
  return el;
}

// HTTP Response handler with structured error extraction
async function handleResponse(res) {
  if (!res.ok) {
    let errorMsg = `Server error (${res.status})`;
    try {
      const data = await res.json();
      if (data && (data.detail || data.error)) {
        errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch (_) {}
    if (res.status === 413) errorMsg = 'Document exceeds the 10MB maximum supported file size.';
    if (res.status === 404) errorMsg = errorMsg || 'Requested document or resource not found.';
    if (res.status === 422) errorMsg = errorMsg || 'Invalid input or missing required field.';
    if (res.status === 500) errorMsg = errorMsg || 'An internal server error occurred on the backend.';
    throw new Error(errorMsg);
  }
  if (res.status === 204) return null;
  return await res.json();
}

// Real API Client talking to FastAPI endpoints
const API = {
  async getStatus() {
    try {
      const res = await fetch('/api/status');
      return await handleResponse(res);
    } catch (e) {
      console.warn('Status check failed:', e.message);
      return { status: 'offline', genai_available: false };
    }
  },
  async upload(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/documents/', {
      method: 'POST',
      body: formData,
    });
    return await handleResponse(res);
  },
  async listDocuments() {
    const res = await fetch('/api/documents/');
    return await handleResponse(res);
  },
  async getWorkspace() {
    const res = await fetch('/api/workspace');
    return await handleResponse(res);
  },
  async getDocument(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}`);
    return await handleResponse(res);
  },
  async getClauses(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/clauses`);
    return await handleResponse(res);
  },
  async getSignals(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/signals`);
    return await handleResponse(res);
  },
  async getEntities(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/entities`);
    return await handleResponse(res);
  },
  async getDashboard(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/dashboard`);
    return await handleResponse(res);
  },

  async generateSummary(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/summary`, {
      method: 'POST',
    });
    return await handleResponse(res);
  },
  async askQuestion(id, question, conversationHistory = []) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, conversation_history: conversationHistory }),
    });
    return await handleResponse(res);
  },
  async compare(docIdA, docIdB) {
    const res = await fetch('/api/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id_a: docIdA, document_id_b: docIdB }),
    });
    return await handleResponse(res);
  },
  async explainDiff(beforeText, afterText, sectionPath) {
    const res = await fetch('/api/compare/explain-diff', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        before_text: beforeText,
        after_text: afterText,
        section_path: sectionPath,
      }),
    });
    return await handleResponse(res);
  },
  async getChecklist(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/checklist`);
    return await handleResponse(res);
  },
  async deleteDocument(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    return await handleResponse(res);
  },
  async getEvidenceLocation(docId, clauseId, evidenceQuote = '') {
    let url = `/api/documents/${encodeURIComponent(docId)}/evidence/${encodeURIComponent(clauseId)}`;
    if (evidenceQuote) {
      url += `?evidence_quote=${encodeURIComponent(evidenceQuote)}`;
    }
    const res = await fetch(url);
    return await handleResponse(res);
  },
  async getRelationships(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/relationships`);
    return await handleResponse(res);
  },
  async explainRelationship(docId, relationshipId) {
    const res = await fetch(`/api/documents/${encodeURIComponent(docId)}/relationships/${encodeURIComponent(relationshipId)}/explain`, {
      method: 'POST',
    });
    return await handleResponse(res);
  },
  async getFinancialItems(id) {
    const res = await fetch(`/api/documents/${encodeURIComponent(id)}/financial`);
    return await handleResponse(res);
  },
  async explainFinancial(docId, itemId) {
    let url = `/api/documents/${encodeURIComponent(docId)}/financial/explain`;
    if (itemId) url += `?item_id=${encodeURIComponent(itemId)}`;
    const res = await fetch(url, { method: 'POST' });
    return await handleResponse(res);
  },
};

// DOM Elements cache
const els = {
  navLinks: document.querySelectorAll('.nav-link'),
  views: document.querySelectorAll('.view'),
  uploadZone: document.getElementById('upload-zone'),
  fileInput: document.getElementById('file-upload'),
  uploadBtnTrigger: document.getElementById('upload-btn-trigger'),
  docsGrid: document.getElementById('documents-grid'),
  workspaceGrid: document.getElementById('workspace-documents-grid'),
  workspaceTotalDocs: document.getElementById('workspace-total-docs'),
  globalLoading: document.getElementById('global-loading'),
  srAnnouncer: document.getElementById('sr-announcer'),
  srAlert: document.getElementById('sr-alert'),

  // System status
  statusDot: document.getElementById('genai-status-dot'),
  statusText: document.getElementById('genai-status-text'),

  // Analyze view
  docTitle: document.getElementById('doc-title'),
  docMeta: document.getElementById('doc-meta'),
  statAttention: document.getElementById('stat-attention'),
  statDates: document.getElementById('stat-dates'),
  statObligations: document.getElementById('stat-obligations'),
  docMapTree: document.getElementById('doc-map-tree'),
  tabBtns: document.querySelectorAll('.tab-btn'),
  tabPanels: document.querySelectorAll('.tab-panel'),
  signalsList: document.getElementById('signals-list'),
  relationshipsList: document.getElementById('relationships-list'),
  btnGenSummary: document.getElementById('btn-gen-summary'),
  summaryContent: document.getElementById('summary-content'),
  entitiesGrid: document.getElementById('entities-grid'),
  clauseSearch: document.getElementById('clause-search'),
  clauseBrowser: document.getElementById('clause-browser'),

  // Modals
  sourceModal: document.getElementById('source-modal'),
  modalCloseBtn: document.getElementById('modal-close'),

  // Evidence Viewer Modal
  evidenceModal: document.getElementById('evidence-modal'),
  evidenceModalClose: document.getElementById('evidence-modal-close'),
  evidenceStatusBadge: document.getElementById('evidence-status-badge'),
  evidencePanelPath: document.getElementById('evidence-panel-path'),
  evidencePanelPage: document.getElementById('evidence-panel-page'),
  evidencePanelQuoteText: document.getElementById('evidence-panel-quote-text'),
  evidencePanelFallbackMsg: document.getElementById('evidence-panel-fallback-msg'),
  evidenceViewerContainer: document.getElementById('evidence-viewer-container'),

  // Chat
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatHistory: document.getElementById('chat-history'),

  // Compare view
  compareDocA: document.getElementById('compare-doc-a'),
  compareDocB: document.getElementById('compare-doc-b'),
  btnRunCompare: document.getElementById('btn-run-compare'),
  compareResults: document.getElementById('compare-results'),
  diffAdded: document.getElementById('diff-added'),
  diffRemoved: document.getElementById('diff-removed'),
  diffModified: document.getElementById('diff-modified'),
  diffUnchanged: document.getElementById('diff-unchanged'),
  diffContainer: document.getElementById('diff-container'),

  // Analyze view empty/error/main containers
  analyzeMainContent: document.getElementById('analyze-main-content'),
  analyzeEmptyState: document.getElementById('analyze-empty-state'),
  analyzeErrorState: document.getElementById('analyze-error-state'),
  analyzeErrorTitle: document.getElementById('analyze-error-title'),
  analyzeErrorMsg: document.getElementById('analyze-error-msg'),
  btnEmptyGoDashboard: document.getElementById('btn-empty-go-dashboard'),
  btnErrorGoDashboard: document.getElementById('btn-error-go-dashboard'),

  // Prepare view
  btnGenChecklist: document.getElementById('btn-gen-checklist'),
  btnCopyChecklist: document.getElementById('btn-copy-checklist'),
  checklistContent: document.getElementById('checklist-content'),
};

// Accessibility Announcement
function announceToScreenReader(message, isAlert = false) {
  if (isAlert && els.srAlert) {
    els.srAlert.textContent = message;
  } else if (els.srAnnouncer) {
    els.srAnnouncer.textContent = message;
  }
}

// Display error banner to user
function showErrorToast(message) {
  announceToScreenReader(`Error: ${message}`, true);
  alert(`LexiGuard Notice: ${message}`);
}

// Global Loading State
function setLoadingState(isLoading, message = 'Loading...') {
  state.loading = isLoading;
  if (isLoading) {
    document.getElementById('loading-message').textContent = message;
    els.globalLoading.classList.remove('hidden');
    announceToScreenReader(message);
  } else {
    els.globalLoading.classList.add('hidden');
  }
}

// Hash Routing Helper Functions
function parseHash() {
  const hash = window.location.hash || '';

  const raw = hash.replace(/^#+\/*\s*/, '').trim();
  if (!raw) {
    return { view: 'dashboard', docId: null };
  }

  const [path, queryString] = raw.split('?');
  const rawView = (path || '').toLowerCase().trim();

  let docId = null;
  if (queryString) {
    const params = new URLSearchParams(queryString);
    docId = params.get('doc') || params.get('document_id');
  }

  const validViews = ['dashboard', 'workspace', 'analyze', 'ask', 'compare', 'prepare'];
  const view = validViews.includes(rawView) ? rawView : 'dashboard';
  return { view, docId };
}

function buildHash(viewId, docId) {
  const docViews = ['analyze', 'ask', 'prepare'];
  if (docViews.includes(viewId) && docId) {
    return `#/${viewId}?doc=${encodeURIComponent(docId)}`;
  }
  return `#/${viewId}`;
}

// Navigation & Router
function navigate(viewId, params = {}, updateHash = true) {
  if (typeof viewId === 'string') {
    let clean = viewId.replace(/^#+\/*\s*/, '').trim();
    if (clean.includes('?')) clean = clean.split('?')[0];
    viewId = clean.toLowerCase().trim();
  }
  const validViews = ['dashboard', 'workspace', 'analyze', 'ask', 'compare', 'prepare'];
  if (!validViews.includes(viewId)) viewId = 'dashboard';

  console.debug("[LexiGuard] navigate:", viewId);

  state.currentView = viewId;

  if (params.docId !== undefined) {
    state.currentDocumentId = params.docId;
  }

  // 1. Activate target view section immediately in DOM
  const viewsList = document.querySelectorAll('.view');
  viewsList.forEach(v => {
    const isActive = v.id === viewId;
    v.classList.toggle('active-view', isActive);
    v.classList.toggle('hidden', !isActive);
    v.style.display = isActive ? 'block' : 'none';
  });

  els.views = viewsList;

  // 2. Update URL hash after view section is active
  const targetHash = buildHash(viewId, state.currentDocumentId);
  if (updateHash && window.location.hash !== targetHash) {
    _suppressNextHashChange = true;
    window.location.hash = targetHash;
  }

  // Toggle nav link highlights
  els.navLinks.forEach(l => {
    if (l.dataset.view === viewId) l.classList.add('active');
    else l.classList.remove('active');
  });

  updateNavState();
  announceToScreenReader(`Navigated to ${viewId} view`);

  // Handle specific view renders
  if (viewId === 'dashboard') {
    renderDashboard();
  } else if (viewId === 'workspace') {
    renderWorkspace();
  } else if (viewId === 'analyze') {
    if (state.currentDocumentId) {
      loadDocumentAnalysis(state.currentDocumentId);
    } else {
      renderAnalyzeEmptyState();
    }
  } else if (viewId === 'ask') {
    renderAskView();
  } else if (viewId === 'compare') {
    renderCompareSelectors();
  } else if (viewId === 'prepare') {
    renderPrepareView();
  }
}

function showAnalyzeMainContent() {
  console.debug('[LexiGuard] showAnalyzeMainContent()');
  if (els.analyzeMainContent) {
    els.analyzeMainContent.classList.remove('hidden');
    els.analyzeMainContent.style.display = '';
  }
  if (els.analyzeEmptyState) els.analyzeEmptyState.classList.add('hidden');
  if (els.analyzeErrorState) els.analyzeErrorState.classList.add('hidden');
}

function renderAnalyzeEmptyState() {
  console.debug('[LexiGuard] renderAnalyzeEmptyState()');
  if (els.analyzeMainContent) els.analyzeMainContent.classList.add('hidden');
  if (els.analyzeEmptyState) els.analyzeEmptyState.classList.remove('hidden');
  if (els.analyzeErrorState) els.analyzeErrorState.classList.add('hidden');
}

function renderAnalyzeErrorState(errorMessage) {
  console.debug('[LexiGuard] renderAnalyzeErrorState():', errorMessage);
  if (els.analyzeMainContent) els.analyzeMainContent.classList.add('hidden');
  if (els.analyzeEmptyState) els.analyzeEmptyState.classList.add('hidden');
  if (els.analyzeErrorState) {
    els.analyzeErrorState.classList.remove('hidden');
    if (els.analyzeErrorMsg) {
      els.analyzeErrorMsg.textContent = errorMessage || 'The requested document could not be found or has been deleted.';
    }
  } else {
    console.error('[LexiGuard] #analyze-error-state element not found in DOM.');
  }
}

function renderAskView() {
  if (!state.currentDocumentId) {
    clearElement(els.chatHistory);
    const emptyBox = createElement('div', { className: 'chat-empty-state' }, [
      createElement('h2', { text: 'No document selected' }),
      createElement('p', { text: 'Select or upload a document from Documents to ask questions.' }),
      createElement('button', {
        className: 'btn btn-primary mt-4',
        text: 'Go to Documents',
      })
    ]);
    const btn = emptyBox.querySelector('button');
    if (btn) btn.addEventListener('click', () => navigate('dashboard'));
    els.chatHistory.appendChild(emptyBox);
  }
}

function renderPrepareView() {
  if (!state.currentDocumentId) {
    clearElement(els.checklistContent);
    const emptyBox = createElement('div', { className: 'empty-state' }, [
      createElement('p', { text: 'No document selected. Select a document from Documents to generate a review checklist.' }),
      createElement('button', {
        className: 'btn btn-primary mt-4',
        text: 'Go to Documents',
      })
    ]);
    const btn = emptyBox.querySelector('button');
    if (btn) btn.addEventListener('click', () => navigate('dashboard'));
    els.checklistContent.appendChild(emptyBox);
  } else if (!state.checklist) {
    clearElement(els.checklistContent);
    els.checklistContent.appendChild(
      createElement('div', { className: 'empty-state' }, [
        createElement('p', { text: 'Click "Generate Legal Review Checklist" to create a custom preparation guide based on this document.' })
      ])
    );
  }
}

function handleRouteFromHash() {
  if (_suppressNextHashChange) {
    _suppressNextHashChange = false;
    console.debug('[LexiGuard] hashchange suppressed (triggered by navigate())');
    return;
  }

  const route = parseHash();
  console.debug('[LexiGuard] handleRouteFromHash: view=', route.view, 'docId=', route.docId);

  if (route.docId) {
    state.currentDocumentId = route.docId;
  }

  navigate(route.view, { docId: route.docId || state.currentDocumentId }, false);
}

// Update Nav Disabled states
function updateNavState() {
  const hasDoc = Boolean(state.currentDocumentId);
  const docNavIds = ['nav-analyze', 'nav-ask', 'nav-prepare'];
  docNavIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.setAttribute('aria-disabled', !hasDoc ? 'true' : 'false');
  });
}

// Refresh System Status (Gemini Available)
async function refreshStatus() {
  const status = await API.getStatus();
  state.genaiAvailable = Boolean(status.genai_available);
  if (els.statusDot && els.statusText) {
    if (state.genaiAvailable) {
      els.statusDot.className = 'status-dot online';
      els.statusText.textContent = `AI Ready (${status.gemini_model || 'Gemini'})`;
    } else {
      els.statusDot.className = 'status-dot fallback';
      els.statusText.textContent = 'Fallback Mode (Rules Only)';
    }
  }
}

// ── Dashboard View ────────────────────────────────────────────────────────────

// ── Dashboard View ────────────────────────────────────────────────────────────

async function renderDashboard() {
  setLoadingState(true, 'Fetching documents...');
  try {
    const docs = await API.listDocuments();
    state.documents = docs || [];
    if (!els.docsGrid) return;
    clearElement(els.docsGrid);

    if (state.documents.length === 0) {
      els.docsGrid.appendChild(
        createElement('p', { className: 'empty-state', text: 'No uploaded documents found. Drag & drop a file above to begin.' })
      );
      return;
    }

    const recentDocs = state.documents.slice(0, 6);
    recentDocs.forEach(doc => {
      const card = createElement('div', {
        className: 'doc-card',
        attrs: { role: 'button', tabindex: '0' },
      });

      const cardHeader = createElement('div', { className: 'doc-card-header' });
      const title = createElement('h3', { text: doc.filename });

      const delBtn = createElement('button', {
        className: 'btn-delete-doc',
        text: `✕ ${t('delete')}`,
        attrs: { 'aria-label': `Delete ${doc.filename}` },
      });
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDeleteDoc(doc.document_id, doc.filename);
      });

      cardHeader.appendChild(title);
      cardHeader.appendChild(delBtn);

      const createdDate = doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Recent';
      const metaRow = createElement('div', { className: 'doc-card-meta' }, [
        createElement('span', { text: `${doc.page_count || 1} ${t('pages')}` }),
        createElement('span', { text: `${doc.clause_count || 0} ${t('clauses')}` }),
        createElement('span', { className: 'badge-signal-count', text: `${doc.signal_count || 0} Risks` }),
        createElement('span', { text: createdDate }),
      ]);

      card.appendChild(cardHeader);
      card.appendChild(metaRow);

      card.addEventListener('click', () => handleDocSelect(doc.document_id, doc.filename));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleDocSelect(doc.document_id, doc.filename);
        }
      });

      els.docsGrid.appendChild(card);
    });
  } catch (err) {
    console.error('Dashboard render error:', err);
    showErrorToast(`Failed to load documents: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

// ── Workspace View ────────────────────────────────────────────────────────────

async function renderWorkspace() {
  setLoadingState(true, 'Fetching workspace documents...');
  try {
    const workspaceDocs = await API.getWorkspace();
    state.documents = workspaceDocs || [];
    const grid = els.workspaceGrid || document.getElementById('workspace-documents-grid');
    if (!grid) return;
    clearElement(grid);

    const totalEl = els.workspaceTotalDocs || document.getElementById('workspace-total-docs');
    if (totalEl) totalEl.textContent = String(state.documents.length);

    if (state.documents.length === 0) {
      grid.appendChild(
        createElement('p', { className: 'empty-state', text: 'No documents in workspace. Upload a document from Dashboard to begin.' })
      );
      return;
    }

    state.documents.forEach(doc => {
      const card = createElement('div', {
        className: 'doc-card workspace-doc-card',
        attrs: { role: 'button', tabindex: '0' },
      });

      const cardHeader = createElement('div', { className: 'doc-card-header' });
      const titleWrap = createElement('div', {}, [
        createElement('h3', { text: doc.filename }),
        createElement('span', { className: 'doc-type-badge', text: doc.document_type || 'General Legal/Business Document' })
      ]);

      const actionsWrap = createElement('div', { className: 'doc-card-actions', attrs: { style: 'display: flex; gap: 8px; align-items: center;' } });
      const openBtn = createElement('button', {
        className: 'btn btn-secondary btn-sm',
        text: t('open'),
      });
      openBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDocSelect(doc.document_id, doc.filename);
      });

      const delBtn = createElement('button', {
        className: 'btn-delete-doc',
        text: `✕ ${t('delete')}`,
        attrs: { 'aria-label': `Delete ${doc.filename}` },
      });
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        handleDeleteDoc(doc.document_id, doc.filename);
      });

      actionsWrap.appendChild(openBtn);
      actionsWrap.appendChild(delBtn);

      cardHeader.appendChild(titleWrap);
      cardHeader.appendChild(actionsWrap);

      const createdDate = doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'Recent';
      const metaRow = createElement('div', { className: 'doc-card-meta mt-2' }, [
        createElement('span', { text: `${doc.page_count || 1} ${t('pages')}` }),
        createElement('span', { text: `${doc.clause_count || 0} ${t('clauses')}` }),
        createElement('span', { className: 'badge-signal-count', text: `${doc.attention_signal_count || doc.signal_count || 0} Risks` }),
        createElement('span', { text: `${doc.relationship_count || 0} Relationships` }),
        createElement('span', { text: `${doc.financial_item_count || 0} ${t('financial_items')}` }),
        createElement('span', { text: createdDate }),
      ]);

      card.appendChild(cardHeader);
      card.appendChild(metaRow);

      card.addEventListener('click', () => handleDocSelect(doc.document_id, doc.filename));

      grid.appendChild(card);
    });
  } catch (err) {
    console.error('Workspace render error:', err);
    showErrorToast(`Failed to load workspace: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

async function handleDeleteDoc(docId, filename) {
  if (!confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
    return;
  }
  setLoadingState(true, 'Deleting document...');
  try {
    await API.deleteDocument(docId);
    if (state.currentDocumentId === docId) {
      state.currentDocumentId = null;
      state.currentDocumentName = null;
      updateNavState();
    }
    if (state.currentView === 'workspace') {
      await renderWorkspace();
    } else {
      await renderDashboard();
    }
    announceToScreenReader(`Deleted document ${filename}`);
  } catch (err) {
    showErrorToast(`Failed to delete document: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

function handleDocSelect(docId, filename) {
  console.debug("[LexiGuard] DOCUMENT CLICKED:", docId, filename);
  if (state.currentDocumentId !== docId) {
    state.conversationHistory = []; // Reset conversation context when document changes
  }
  state.currentDocumentId = docId;
  state.currentDocumentName = filename;
  updateNavState();
  navigate('analyze', { docId });
}

// ── Analyze View ─────────────────────────────────────────────────────────────

async function loadDocumentAnalysis(docId) {
  if (!docId) {
    renderAnalyzeEmptyState();
    return;
  }

  // Prevent concurrent renders for the same docId (e.g. from double-navigate)
  if (_analysisInFlight === docId) {
    console.debug('[LexiGuard] loadDocumentAnalysis already in-flight for', docId, '— skipping duplicate call');
    return;
  }
  _analysisInFlight = docId;

  console.debug('[LexiGuard] loadDocumentAnalysis start | docId:', docId);
  setLoadingState(true, 'Analyzing legal document...');

  try {
    // Parallel fetch document details, clauses, signals, entities, relationships, financial, dashboard
    console.debug('[LexiGuard] Fetching document data...');
    const [doc, clauses, signals, entities, relationships, financialItems, dashboard] = await Promise.all([
      API.getDocument(docId),
      API.getClauses(docId),
      API.getSignals(docId),
      API.getEntities(docId),
      API.getRelationships(docId).catch(() => []),
      API.getFinancialItems(docId).catch(() => []),
      API.getDashboard(docId).catch(() => null),
    ]);

    console.debug('[LexiGuard] API responses received:',
      '| doc:', doc?.filename,
      '| clauses:', clauses?.length,
      '| signals:', signals?.length,
      '| relationships:', relationships?.length,
      '| financial:', financialItems?.length,
      '| entities.dates:', entities?.dates?.length,
      '| dashboard:', dashboard?.document_type
    );

    // Verify required elements are present before rendering
    if (!els.docTitle || !els.docMeta) {
      throw new Error('Analyze DOM elements missing — check #doc-title and #doc-meta in index.html');
    }

    showAnalyzeMainContent();

    state.currentDocumentId = doc.document_id;
    state.currentDocumentName = doc.filename;
    state.clauses = Array.isArray(clauses) ? clauses : [];
    state.signals = Array.isArray(signals) ? signals : [];
    state.relationships = Array.isArray(relationships) ? relationships : [];
    state.financialItems = Array.isArray(financialItems) ? financialItems : [];
    state.entities = (entities && typeof entities === 'object')
      ? entities
      : { dates: [], monetary_values: [], parties: [], obligations: [] };
    updateNavState();

    // Update Header
    els.docTitle.textContent = doc.filename || 'Document';
    clearElement(els.docMeta);
    els.docMeta.appendChild(createElement('span', { text: `${doc.page_count ?? 0} Pages` }));
    els.docMeta.appendChild(document.createTextNode(' • '));
    els.docMeta.appendChild(createElement('span', { text: `${doc.clause_count ?? 0} Clauses` }));

    // Update Stats Bar
    if (els.statAttention) els.statAttention.textContent = String(state.signals.length);
    if (els.statDates) els.statDates.textContent = String((state.entities.dates || []).length);
    if (els.statObligations) els.statObligations.textContent = String((state.entities.obligations || []).length);

    // Build Document Map
    console.debug('[LexiGuard] renderDocumentMap, clauses count:', state.clauses.length);
    renderDocumentMap(state.clauses);

    // Render Overview & Entities
    console.debug('[LexiGuard] renderOverviewEntities');
    renderOverviewEntities(doc, state.entities, dashboard);

    // Render Signals List
    console.debug('[LexiGuard] renderSignalsList, signals count:', state.signals.length);
    renderSignalsList(state.signals);

    // Render Relationships List
    console.debug('[LexiGuard] renderRelationshipsList, relationships count:', state.relationships.length);
    renderRelationshipsList(state.relationships);

    // Render Financial List
    console.debug('[LexiGuard] renderFinancialList, financial count:', state.financialItems.length);
    renderFinancialList(state.financialItems);

    // Render Clauses Browser
    console.debug('[LexiGuard] renderClausesBrowser, clauses count:', state.clauses.length);
    renderClausesBrowser(state.clauses);

    // Reset summary container
    if (els.summaryContent) {
      clearElement(els.summaryContent);
      els.summaryContent.appendChild(
        createElement('p', { className: 'empty-text', text: "Click 'Generate Summary' to get an AI-powered overview of this document." })
      );
    }

    switchTab('tab-overview');
    console.debug('[LexiGuard] Analyze render complete.');

  } catch (err) {
    console.error('[LexiGuard] Error in loadDocumentAnalysis:', err);
    state.currentDocumentId = null;
    updateNavState();
    renderAnalyzeErrorState(err.message);
  } finally {
    _analysisInFlight = null;
    setLoadingState(false);
  }
}

function renderDocumentMap(clauses) {
  clearElement(els.docMapTree);
  if (!clauses.length) {
    els.docMapTree.appendChild(createElement('li', { text: 'No structure detected' }));
    return;
  }

  // Deduplicate sections
  const sectionsMap = new Map();
  clauses.forEach(c => {
    const path = c.metadata.section_path || c.metadata.heading || 'General';
    if (!sectionsMap.has(path)) {
      sectionsMap.set(path, c);
    }
  });

  sectionsMap.forEach((clause, path) => {
    const li = createElement('li', { className: 'map-item' });
    const btn = createElement('button', {
      className: 'map-link',
      text: path,
      attrs: { 'aria-label': `Jump to ${path}` },
    });
    btn.addEventListener('click', () => {
      switchTab('tab-clauses');
      els.clauseSearch.value = path;
      filterClauses(path);
    });
    li.appendChild(btn);
    els.docMapTree.appendChild(li);
  });
}

function renderOverviewEntities(doc, entities, dashboard) {
  const container = document.getElementById('dashboard-overview-container');
  if (container) {
    clearElement(container);
    if (dashboard) {
      container.appendChild(buildDashboardElement(dashboard));
    }
  }

  clearElement(els.entitiesGrid);

  const cardDates = createEntitySection(t('important_dates'), entities.dates);
  const cardMoney = createEntitySection(t('monetary_values'), entities.monetary_values);
  const cardParties = createEntitySection(t('contracting_parties'), entities.parties);
  const cardObligations = createEntitySection(t('key_obligations'), entities.obligations);

  els.entitiesGrid.appendChild(cardDates);
  els.entitiesGrid.appendChild(cardMoney);
  els.entitiesGrid.appendChild(cardParties);
  els.entitiesGrid.appendChild(cardObligations);
}

function buildDashboardElement(dash) {
  const root = createElement('div', { className: 'dashboard-card-grid' });

  // Overview Header Card
  const overviewCard = createElement('div', { className: 'panel-section dashboard-overview-card' }, [
    createElement('div', { className: 'section-heading-row' }, [
      createElement('h2', { text: t('doc_overview_title') }),
      createElement('span', { className: 'doc-type-badge', text: dash.document_type || 'General Legal/Business Document' }),
    ]),
    createElement('div', { className: 'summary-stats-bar mt-3' }, [
      createElement('div', { className: 'stat-pill' }, [createElement('span', { className: 'stat-value', text: String(dash.clause_count || 0) }), document.createTextNode(' ' + t('clauses'))]),
      createElement('div', { className: 'stat-pill' }, [createElement('span', { className: 'stat-value', text: String(dash.signal_count || 0) }), document.createTextNode(' ' + t('risk_signals'))]),
      createElement('div', { className: 'stat-pill' }, [createElement('span', { className: 'stat-value', text: String(dash.important_date_count || 0) }), document.createTextNode(' ' + t('important_dates'))]),
      createElement('div', { className: 'stat-pill' }, [createElement('span', { className: 'stat-value', text: String(dash.monetary_reference_count || 0) }), document.createTextNode(' ' + t('monetary_values'))]),
    ])
  ]);
  root.appendChild(overviewCard);

  // Categorized Temporal Obligations Section
  if (dash.important_dates && dash.important_dates.length > 0) {
    const datesCard = createElement('div', { className: 'panel-section mt-4' });
    datesCard.appendChild(createElement('h2', { text: t('dates_temporal_title') }));
    const ul = createElement('ul', { className: 'temporal-dates-list' });

    dash.important_dates.forEach(tItem => {
      const typeBadgeClass = (tItem.context_type || 'temporal').toLowerCase().replace(/_/g, '-');
      const item = createElement('li', { className: 'temporal-date-item' }, [
        createElement('div', { className: 'temporal-header' }, [
          createElement('span', { className: `context-badge badge-${typeBadgeClass}`, text: (tItem.context_type || 'obligation').replace(/_/g, ' ').toUpperCase() }),
          createElement('strong', { className: 'temporal-date', text: tItem.date }),
          createElement('span', { className: 'temporal-path', text: `${tItem.section_path || t('source_clause')} · ${t('pg_abbrev')} ${tItem.page || 1}` }),
        ]),
        createElement('p', { className: 'temporal-desc', text: tItem.description }),
      ]);
      ul.appendChild(item);
    });
    datesCard.appendChild(ul);
    root.appendChild(datesCard);
  }

  return root;
}

function createEntitySection(titleText, items) {
  const box = createElement('div', { className: 'entity-box' });
  box.appendChild(createElement('h3', { text: titleText }));

  if (!items || items.length === 0) {
    box.appendChild(createElement('p', { className: 'empty-text', text: t('none_detected') }));
    return box;
  }

  const ul = createElement('ul', { className: 'entity-list' });
  items.forEach(item => {
    ul.appendChild(createElement('li', { text: item }));
  });
  box.appendChild(ul);
  return box;
}


function renderSignalsList(signals) {
  clearElement(els.signalsList);

  if (!signals || signals.length === 0) {
    els.signalsList.appendChild(
      createElement('p', { className: 'empty-state', text: t('no_signals_detected') })
    );
    return;
  }

  signals.forEach(sig => {
    const sevClass = (sig.severity || 'INFORMATIONAL').toLowerCase().replace(/\s+/g, '-');
    const card = createElement('div', { className: `signal-card signal-${sevClass}` });

    const header = createElement('div', { className: 'signal-header' });
    const metaRow = createElement('div', { className: 'signal-meta-row' }, [
      createElement('span', { className: 'signal-badge', text: `[${sig.severity}]` }),
      createElement('span', { className: 'signal-location', text: `${sig.section_path || t('section')} · ${t('pg_abbrev')} ${sig.page || 1}` }),
    ]);

    const title = createElement('div', { className: 'signal-title', text: sig.plain_explanation || sig.category });

    const toggleBtn = createElement('button', {
      className: 'signal-expand-btn',
      text: t('why_seeing_this'),
      attrs: { 'aria-expanded': 'false' },
    });

    header.appendChild(metaRow);
    header.appendChild(title);
    header.appendChild(toggleBtn);

    const body = createElement('div', { className: 'signal-body' });
    body.appendChild(createElement('p', { text: sig.plain_explanation }));

    if (sig.evidence_text) {
      body.appendChild(createElement('blockquote', { className: 'evidence-quote', text: `"${sig.evidence_text}"` }));
    }

    if (sig.question_to_ask) {
      const qBox = createElement('div', { className: 'lawyer-question-box' }, [
        createElement('strong', { text: `${t('suggested_verification')}: ` }),
        createElement('span', { text: sig.question_to_ask }),
      ]);
      body.appendChild(qBox);
    }

    const viewEvidenceBtn = createElement('button', {
      className: 'btn btn-view-evidence mt-2 me-2',
      text: `🔍 ${t('view_in_doc')}`,
      attrs: { 'aria-label': `View cited evidence in document for ${sig.section_path || 'Clause'}` },
    });
    viewEvidenceBtn.addEventListener('click', () => {
      openEvidenceViewer(
        sig.document_id || state.currentDocumentId,
        sig.clause_id,
        sig.page || 1,
        sig.evidence_text,
        sig.section_path
      );
    });

    const viewClauseBtn = createElement('button', {
      className: 'btn btn-secondary btn-sm mt-2',
      text: t('view_source'),
    });
    viewClauseBtn.addEventListener('click', () => {
      openSourceModal(sig.section_path || 'Clause', sig.page || 1, sig.evidence_text || 'Source text unavailable.');
    });

    const btnGroup = createElement('div', { className: 'signal-actions mt-2' }, [
      viewEvidenceBtn,
      viewClauseBtn,
    ]);
    body.appendChild(btnGroup);

    toggleBtn.addEventListener('click', () => {
      const isExpanded = toggleBtn.getAttribute('aria-expanded') === 'true';
      toggleBtn.setAttribute('aria-expanded', String(!isExpanded));
      if (!isExpanded) {
        body.classList.add('expanded');
        toggleBtn.textContent = t('hide_explanation');
      } else {
        body.classList.remove('expanded');
        toggleBtn.textContent = t('why_seeing_this');
      }
    });

    card.appendChild(header);
    card.appendChild(body);
    els.signalsList.appendChild(card);
  });
}

function renderRelationshipsList(relationships) {
  if (!els.relationshipsList) return;
  clearElement(els.relationshipsList);

  if (!relationships || relationships.length === 0) {
    els.relationshipsList.appendChild(
      createElement('p', { className: 'empty-state', text: t('no_relationships_detected') })
    );
    return;
  }

  relationships.forEach(rel => {
    const statusClass = (rel.relationship_status || 'MISSING_COUNTERPART').toLowerCase().replace(/_/g, '-');
    const card = createElement('div', { className: `relationship-card rel-${statusClass}` });

    const header = createElement('div', { className: 'rel-header' });
    const formattedType = (rel.relationship_type || 'RELATIONSHIP').replace(/_/g, ' ');
    // Map relationship_status to translation keys for localized badge text
    const REL_STATUS_KEY_MAP = {
      'BALANCED': 'balanced_relationship',
      'BALANCED_RELATIONSHIP': 'balanced_relationship',
      'POTENTIAL_ASYMMETRY': 'potential_asymmetry',
      'MISSING_COUNTERPART': 'missing_counterpart',
      'MISSING': 'missing_counterpart',
      'RIGHT_CONDITION': 'right_condition',
      'LEFT_CONDITION': 'left_condition',
      'POTENTIAL_CONFLICT': 'potential_conflict',
    };
    const _statusKey = (rel.relationship_status || 'MISSING_COUNTERPART').toUpperCase().replace(/ /g, '_');
    const localizedRelBadge = REL_STATUS_KEY_MAP[_statusKey]
      ? t(REL_STATUS_KEY_MAP[_statusKey])
      : (rel.relationship_status || 'MISSING COUNTERPART').replace(/_/g, ' ');
    const metaRow = createElement('div', { className: 'rel-meta-row' }, [
      createElement('span', { className: `rel-badge rel-badge-${statusClass}`, text: localizedRelBadge }),
      createElement('span', { className: 'rel-type-label', text: formattedType }),
      createElement('span', { className: 'rel-location', text: `${rel.source_section_path || t('source_clause')} · ${t('pg_abbrev')} ${rel.source_page || 1}` }),
    ]);

    const titleText = rel.plain_explanation || formattedType;
    const title = createElement('div', { className: 'rel-title', text: titleText });

    const toggleBtn = createElement('button', {
      className: 'rel-expand-btn',
      text: t('explanation_provenance'),
      attrs: { 'aria-expanded': 'false' },
    });

    header.appendChild(metaRow);
    header.appendChild(title);
    header.appendChild(toggleBtn);

    const body = createElement('div', { className: 'rel-body' });
    body.appendChild(createElement('p', { className: 'rel-explanation-text', text: rel.plain_explanation }));

    // Source Clause Evidence
    if (rel.source_excerpt) {
      const srcBox = createElement('div', { className: 'rel-evidence-box' }, [
        createElement('strong', { className: 'rel-evidence-label', text: `${t('source_clause')} (${rel.source_section_path || t('section')} · ${t('pg_abbrev')} ${rel.source_page || 1}):` }),
        createElement('blockquote', { className: 'evidence-quote', text: `"${rel.source_excerpt}"` }),
      ]);
      body.appendChild(srcBox);
    }

    // Related Clause Evidence (ONLY if related_clause_id and related_excerpt exist)
    if (rel.related_clause_id && rel.related_excerpt) {
      const relBox = createElement('div', { className: 'rel-evidence-box mt-2' }, [
        createElement('strong', { className: 'rel-evidence-label', text: `${t('related_counterpart')} (${rel.related_section_path || t('section')} · ${t('pg_abbrev')} ${rel.related_page || 1}):` }),
        createElement('blockquote', { className: 'evidence-quote', text: `"${rel.related_excerpt}"` }),
      ]);
      body.appendChild(relBox);
    }

    if (rel.question_to_ask) {
      const qBox = createElement('div', { className: 'lawyer-question-box mt-2' }, [
        createElement('strong', { text: `${t('suggested_verification')}: ` }),
        createElement('span', { text: rel.question_to_ask }),
      ]);
      body.appendChild(qBox);
    }

    // Button Actions Group
    const btnGroup = createElement('div', { className: 'rel-actions mt-3' });

    // ALWAYS show View Source Clause button
    const viewSourceBtn = createElement('button', {
      className: 'btn btn-view-evidence me-2',
      text: `🔍 ${t('view_source')}`,
      attrs: { 'aria-label': `View source clause in document for ${rel.source_section_path || 'Clause'}` },
    });
    viewSourceBtn.addEventListener('click', () => {
      openEvidenceViewer(
        rel.document_id || state.currentDocumentId,
        rel.source_clause_id,
        rel.source_page || 1,
        rel.source_excerpt || '',
        rel.source_section_path || t('source_clause')
      );
    });
    btnGroup.appendChild(viewSourceBtn);

    // ONLY show View Related Clause button if related_clause_id is NOT null/undefined!
    if (rel.related_clause_id) {
      const viewRelatedBtn = createElement('button', {
        className: 'btn btn-secondary me-2',
        text: `🔍 ${t('view_related')}`,
        attrs: { 'aria-label': `View related counterpart clause in document for ${rel.related_section_path || 'Clause'}` },
      });
      viewRelatedBtn.addEventListener('click', () => {
        openEvidenceViewer(
          rel.document_id || state.currentDocumentId,
          rel.related_clause_id,
          rel.related_page || 1,
          rel.related_excerpt || '',
          rel.related_section_path || t('related_clause')
        );
      });
      btnGroup.appendChild(viewRelatedBtn);
    }

    body.appendChild(btnGroup);

    toggleBtn.addEventListener('click', () => {
      const isExpanded = toggleBtn.getAttribute('aria-expanded') === 'true';
      toggleBtn.setAttribute('aria-expanded', String(!isExpanded));
      if (!isExpanded) {
        body.classList.add('expanded');
        toggleBtn.textContent = t('hide_explanation');
      } else {
        body.classList.remove('expanded');
        toggleBtn.textContent = t('explanation_provenance');
      }
    });

    card.appendChild(header);
    card.appendChild(body);
    els.relationshipsList.appendChild(card);
  });
}

function renderClausesBrowser(clauses) {
  clearElement(els.clauseBrowser);

  if (!clauses || clauses.length === 0) {
    els.clauseBrowser.appendChild(
      createElement('p', { className: 'empty-state', text: t('no_clauses_available') })
    );
    return;
  }

  clauses.forEach(clause => {
    const item = createElement('div', { className: 'clause-item' });
    const meta = createElement('div', { className: 'clause-meta' }, [
      createElement('span', { className: 'clause-path', text: clause.metadata.section_path || clause.metadata.heading || 'Clause' }),
      createElement('span', { className: 'clause-type-badge', text: clause.metadata.clause_type || 'general' }),
      createElement('span', { text: `${t('page')} ${clause.metadata.page || 1}` }),
    ]);

    const text = createElement('div', { className: 'clause-text', text: clause.text });

    item.appendChild(meta);
    item.appendChild(text);
    els.clauseBrowser.appendChild(item);
  });
}

function renderFinancialList(items) {
  const container = document.getElementById('financial-list');
  if (!container) return;
  clearElement(container);

  if (!items || !items.length) {
    container.appendChild(
      createElement('p', { className: 'empty-state', text: t('no_financial_detected') })
    );
    return;
  }

  items.forEach(item => {
    const card = createElement('div', { className: 'financial-card' });

    const header = createElement('div', { className: 'financial-header' });
    const title = createElement('div', { className: 'financial-title' }, [
      createElement('span', { text: formatFinancialType(item.item_type) }),
      createElement('span', { className: 'badge-financial', text: item.item_type }),
    ]);

    const btnSource = createElement('button', {
      className: 'btn btn-secondary btn-xs',
      text: t('view_source'),
      attrs: { 'aria-label': `View source clause for ${item.item_type}` },
    });
    btnSource.addEventListener('click', () => {
      openEvidenceViewer(
        state.currentDocumentId,
        item.clause_id,
        item.page || 1,
        item.evidence_text || item.amount || '',
        item.section_path || 'Compensation'
      );
    });

    header.appendChild(title);
    header.appendChild(btnSource);
    card.appendChild(header);

    const detailsGrid = createElement('div', { className: 'financial-details' });
    detailsGrid.appendChild(createDetailItem(t('amount'), item.amount || t('not_specified')));
    detailsGrid.appendChild(createDetailItem(t('currency'), item.currency || t('not_specified')));
    detailsGrid.appendChild(createDetailItem(t('frequency'), item.frequency || t('not_specified')));
    if (item.effective_date) detailsGrid.appendChild(createDetailItem(t('effective_date'), item.effective_date));
    if (item.payment_timing) detailsGrid.appendChild(createDetailItem(t('timing'), item.payment_timing));
    if (item.condition) detailsGrid.appendChild(createDetailItem(t('condition'), item.condition));
    detailsGrid.appendChild(createDetailItem(t('section'), item.section_path || 'General'));
    detailsGrid.appendChild(createDetailItem(t('page'), `${t('page')} ${item.page || 1}`));

    card.appendChild(detailsGrid);

    if (item.completeness_note) {
      card.appendChild(createElement('div', {
        className: 'financial-completeness-note',
        text: `⚠️ ${t('completeness_observation')}: ${item.completeness_note}`
      }));
    }

    if (item.evidence_text) {
      card.appendChild(createElement('div', {
        className: 'financial-evidence-excerpt',
        text: `"${item.evidence_text}"`
      }));
    }

    container.appendChild(card);
  });
}

function createDetailItem(label, value) {
  return createElement('div', { className: 'financial-detail-item' }, [
    createElement('span', { className: 'financial-detail-label', text: label }),
    createElement('span', { className: 'financial-detail-value', text: value })
  ]);
}

function formatFinancialType(type) {
  if (!type) return 'Financial Item';
  return type.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase());
}


function filterClauses(query) {
  const term = query.toLowerCase().trim();
  const items = els.clauseBrowser.querySelectorAll('.clause-item');
  items.forEach(item => {
    const text = item.textContent.toLowerCase();
    if (!term || text.includes(term)) {
      item.classList.remove('hidden');
    } else {
      item.classList.add('hidden');
    }
  });
}

function switchTab(tabId) {
  els.tabBtns.forEach(btn => {
    const isSelected = btn.id === tabId;
    btn.setAttribute('aria-selected', String(isSelected));
    btn.classList.toggle('active', isSelected);
  });

  els.tabPanels.forEach(panel => {
    const isTarget = panel.getAttribute('aria-labelledby') === tabId;
    panel.classList.toggle('hidden', !isTarget);
    panel.classList.toggle('active', isTarget);
  });
}

function openSourceModal(path, page, text) {
  document.getElementById('modal-source-path').textContent = path || 'Clause Source';
  document.getElementById('modal-source-page').textContent = `Page ${page || 1}`;
  document.getElementById('modal-source-text').textContent = text || '';
  els.sourceModal.showModal();
}

async function openEvidenceViewer(docId, clauseId, fallbackPage = 1, evidenceQuote = '', sectionPath = 'Clause') {
  if (!els.evidenceModal) return;

  // Reset modal elements
  if (els.evidenceStatusBadge) {
    els.evidenceStatusBadge.textContent = 'Locating evidence...';
    els.evidenceStatusBadge.className = 'grounding-badge grounding-supported';
  }
  if (els.evidencePanelPath) els.evidencePanelPath.textContent = sectionPath || 'Clause';
  if (els.evidencePanelPage) els.evidencePanelPage.textContent = `Page ${fallbackPage || 1}`;
  if (els.evidencePanelQuoteText) els.evidencePanelQuoteText.textContent = evidenceQuote || '(Loading quote...)';
  if (els.evidencePanelFallbackMsg) {
    els.evidencePanelFallbackMsg.classList.add('hidden');
    clearElement(els.evidencePanelFallbackMsg);
  }
  clearElement(els.evidenceViewerContainer);

  // Loading indicator inside viewer container
  const loadingBox = createElement('div', { className: 'loading-overlay' }, [
    createElement('div', { className: 'spinner' }),
    createElement('p', { text: 'Loading document page & verifying evidence...' }),
  ]);
  els.evidenceViewerContainer.appendChild(loadingBox);

  try {
    els.evidenceModal.showModal();
  } catch (_) {}

  let locData = null;
  if (docId && clauseId) {
    try {
      locData = await API.getEvidenceLocation(docId, clauseId, evidenceQuote);
    } catch (err) {
      console.warn('[LexiGuard] getEvidenceLocation failed:', err.message);
    }
  }

  clearElement(els.evidenceViewerContainer);

  if (!locData || locData.match_status === 'location_unavailable') {
    // Safe State C / Invalid state: Evidence location unavailable
    if (els.evidenceStatusBadge) {
      els.evidenceStatusBadge.textContent = '⚠️ Evidence Location Unavailable';
      els.evidenceStatusBadge.className = 'grounding-badge grounding-insufficient-evidence';
    }
    if (els.evidencePanelFallbackMsg) {
      els.evidencePanelFallbackMsg.textContent = 'The specified clause or document location could not be located.';
      els.evidencePanelFallbackMsg.classList.remove('hidden');
    }
    const emptyStateCard = createElement('div', { className: 'empty-state-card mt-4' }, [
      createElement('h3', { text: 'Evidence Location Unavailable' }),
      createElement('p', { text: 'The cited document page or clause provenance is missing, invalid, or belongs to another document.' }),
    ]);
    els.evidenceViewerContainer.appendChild(emptyStateCard);
    return;
  }

  const pageNum = locData.page_number || fallbackPage || 1;
  const pathStr = locData.section_path || sectionPath || 'Clause';
  const quoteStr = locData.evidence_quote || evidenceQuote || '';
  const matchStatus = locData.match_status;
  const fileType = (locData.file_type || 'pdf').toLowerCase();
  const clauseText = locData.clause_text || quoteStr;

  if (els.evidencePanelPath) els.evidencePanelPath.textContent = pathStr;
  if (els.evidencePanelPage) els.evidencePanelPage.textContent = `Page ${pageNum}`;
  if (els.evidencePanelQuoteText) els.evidencePanelQuoteText.textContent = quoteStr || clauseText || '(No quote text)';

  // Configure status badge & fallback messages
  if (matchStatus === 'exact_highlight_available') {
    if (els.evidenceStatusBadge) {
      els.evidenceStatusBadge.textContent = `✓ Exact Match Highlighted (Page ${pageNum})`;
      els.evidenceStatusBadge.className = 'grounding-badge grounding-strong';
    }
    if (els.evidencePanelFallbackMsg) els.evidencePanelFallbackMsg.classList.add('hidden');
  } else {
    // Page-level navigation fallback
    if (els.evidenceStatusBadge) {
      els.evidenceStatusBadge.textContent = `ℹ Cited Page Located (Page ${pageNum})`;
      els.evidenceStatusBadge.className = 'grounding-badge grounding-supported';
    }
    if (els.evidencePanelFallbackMsg) {
      els.evidencePanelFallbackMsg.textContent = 'Cited Page Located — Exact text match unavailable on page.';
      els.evidencePanelFallbackMsg.classList.remove('hidden');
    }
  }

  // Render PDF Iframe or Structured Text View
  if (fileType === 'pdf') {
    const iframe = createElement('iframe', {
      className: 'evidence-pdf-iframe',
      attrs: {
        src: `/api/documents/${encodeURIComponent(docId)}/file#page=${pageNum}`,
        title: `Document Evidence Viewer - Page ${pageNum}`,
      },
    });
    iframe.onerror = () => renderTextViewer(clauseText, quoteStr, matchStatus);
    els.evidenceViewerContainer.appendChild(iframe);
  } else {
    renderTextViewer(clauseText, quoteStr, matchStatus);
  }
}

function renderTextViewer(clauseText, quoteStr, matchStatus) {
  clearElement(els.evidenceViewerContainer);
  const textViewer = createElement('div', { className: 'evidence-text-viewer' });

  if (matchStatus === 'exact_highlight_available' && quoteStr && clauseText) {
    const quoteTrim = quoteStr.trim();
    let matchIdx = clauseText.indexOf(quoteTrim);
    if (matchIdx === -1) {
      matchIdx = clauseText.toLowerCase().indexOf(quoteTrim.toLowerCase());
    }

    if (matchIdx !== -1) {
      const matchLen = quoteTrim.length;
      const beforeStr = clauseText.substring(0, matchIdx);
      const matchedStr = clauseText.substring(matchIdx, matchIdx + matchLen);
      const afterStr = clauseText.substring(matchIdx + matchLen);

      if (beforeStr) textViewer.appendChild(document.createTextNode(beforeStr));
      const markEl = createElement('mark', { className: 'evidence-highlight', text: matchedStr });
      textViewer.appendChild(markEl);
      if (afterStr) textViewer.appendChild(document.createTextNode(afterStr));

      els.evidenceViewerContainer.appendChild(textViewer);
      setTimeout(() => markEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
      return;
    }
  }

  textViewer.appendChild(document.createTextNode(clauseText || quoteStr || 'No text content available.'));
  els.evidenceViewerContainer.appendChild(textViewer);
}

// ── Q&A View ──────────────────────────────────────────────────────────────────

async function handleQuestionSubmit(e) {
  e.preventDefault();
  const questionText = els.chatInput.value.trim();
  if (!questionText) return;
  if (!state.currentDocumentId) {
    showErrorToast('Please select or upload a document first before asking questions.');
    return;
  }

  // Append user message cleanly
  if (els.chatHistory.querySelector('.chat-empty-state')) {
    clearElement(els.chatHistory);
  }

  const userMsgBox = createElement('div', { className: 'message msg-user' }, [
    createElement('p', { text: questionText }),
  ]);
  els.chatHistory.appendChild(userMsgBox);
  els.chatInput.value = '';
  els.chatHistory.scrollTop = els.chatHistory.scrollHeight;

  // Append loading placeholder
  const loadingMsgBox = createElement('div', { className: 'message msg-ai loading-msg' }, [
    createElement('p', { text: 'Retrieving evidence & validating citations...' }),
  ]);
  els.chatHistory.appendChild(loadingMsgBox);
  els.chatHistory.scrollTop = els.chatHistory.scrollHeight;

  try {
    const response = await API.askQuestion(state.currentDocumentId, questionText, state.conversationHistory);
    els.chatHistory.removeChild(loadingMsgBox);

    // Save to conversation history
    state.conversationHistory.push({ role: 'user', content: questionText });
    state.conversationHistory.push({ role: 'assistant', content: response.answer });

    const aiMsgBox = createElement('div', { className: 'message msg-ai' });
    aiMsgBox.appendChild(createElement('p', { text: response.answer }));

    // Grounding Status Badge
    // Explicit enum → CSS class map (avoids fragile string-replace derivation).
    const GROUNDING_CSS = {
      'STRONGLY GROUNDED':    'grounding-strong',
      'SUPPORTED':            'grounding-supported',
      'LIMITED EVIDENCE':     'grounding-limited',
      'INSUFFICIENT EVIDENCE':'grounding-insufficient-evidence',
    };
    const statusText = response.grounding_status || 'INSUFFICIENT EVIDENCE';
    const statusClass = GROUNDING_CSS[statusText] || 'grounding-insufficient-evidence';
    const badge = createElement('span', {
      className: `grounding-badge ${statusClass}`,
      text: `✓ ${statusText}`,
    });
    aiMsgBox.appendChild(badge);

    // Citations / Evidence
    if (response.evidences && response.evidences.length > 0) {
      const citeBox = createElement('div', { className: 'citations-box' });
      citeBox.appendChild(createElement('strong', { text: t('supporting_citations') }));
      const citeList = createElement('ul', { className: 'citation-list' });

      response.evidences.forEach(ev => {
        const viewBtn = createElement('button', {
          className: 'btn btn-view-evidence btn-sm mt-1',
          text: `🔍 ${t('view_in_doc')}`,  
          attrs: { 'aria-label': `View citation in document for ${ev.section_path || 'Clause'}` },
        });
        viewBtn.addEventListener('click', () => {
          openEvidenceViewer(
            state.currentDocumentId,
            ev.clause_id,
            ev.page || 1,
            ev.quoted_text,
            ev.section_path
          );
        });

        const item = createElement('li', { className: 'citation-item mb-2' }, [
          createElement('span', { className: 'cite-path', text: `${ev.section_path || t('source_clause')} (${t('pg_abbrev')} ${ev.page || 1})` }),
          createElement('blockquote', { className: 'cite-quote', text: `"${ev.quoted_text}"` }),
          viewBtn,
        ]);
        citeList.appendChild(item);
      });
      citeBox.appendChild(citeList);
      aiMsgBox.appendChild(citeBox);
    }

    if (response.suggested_followup) {
      const followup = createElement('div', { className: 'followup-box' }, [
        createElement('em', { text: `${t('suggested_followup_label')}: ${response.suggested_followup}` }),
      ]);
      aiMsgBox.appendChild(followup);
    }

    els.chatHistory.appendChild(aiMsgBox);
    els.chatHistory.scrollTop = els.chatHistory.scrollHeight;
  } catch (err) {
    if (loadingMsgBox.parentNode) els.chatHistory.removeChild(loadingMsgBox);
    showErrorToast(`Q&A Error: ${err.message}`);
  }
}

// ── Compare View ─────────────────────────────────────────────────────────────

async function renderCompareSelectors() {
  try {
    const docs = await API.listDocuments();
    state.documents = docs || [];

    clearElement(els.compareDocA);
    clearElement(els.compareDocB);

    els.compareDocA.appendChild(createElement('option', { attrs: { value: '' }, text: 'Select Document A (Original)...' }));
    els.compareDocB.appendChild(createElement('option', { attrs: { value: '' }, text: 'Select Document B (Revised)...' }));

    state.documents.forEach(doc => {
      let dateStr = '';
      if (doc.created_at) {
        try {
          const d = new Date(doc.created_at);
          dateStr = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
        } catch (_) {
          dateStr = '';
        }
      }
      const clausesStr = `${doc.clause_count || 0} clauses`;
      const metaStr = [dateStr, clausesStr].filter(Boolean).join(' · ');
      const labelText = metaStr ? `${doc.filename} (${metaStr})` : doc.filename;

      const optA = createElement('option', { attrs: { value: doc.document_id }, text: labelText });
      const optB = createElement('option', { attrs: { value: doc.document_id }, text: labelText });
      if (state.currentDocumentId === doc.document_id) {
        optA.selected = true;
      }
      els.compareDocA.appendChild(optA);
      els.compareDocB.appendChild(optB);
    });

    updateCompareButtonState();
  } catch (err) {
    showErrorToast(`Failed to load document selectors: ${err.message}`);
  }
}

function updateCompareButtonState() {
  const valA = els.compareDocA.value;
  const valB = els.compareDocB.value;
  els.btnRunCompare.disabled = !valA || !valB || valA === valB;
}

async function handleRunCompare() {
  const docIdA = els.compareDocA.value;
  const docIdB = els.compareDocB.value;
  if (!docIdA || !docIdB) return;

  setLoadingState(true, 'Comparing legal documents...');
  try {
    const result = await API.compare(docIdA, docIdB);
    els.compareResults.classList.remove('hidden');

    els.diffAdded.textContent = String(result.added ? result.added.length : 0);
    els.diffRemoved.textContent = String(result.removed ? result.removed.length : 0);
    els.diffModified.textContent = String(result.modified ? result.modified.length : 0);
    els.diffUnchanged.textContent = String(result.unchanged_count || 0);

    renderDiffCards(result, 'all');
  } catch (err) {
    showErrorToast(`Comparison failed: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

function renderDiffCards(result, filter = 'all') {
  clearElement(els.diffContainer);

  let items = [];
  if (filter === 'all' || filter === 'added') {
    (result.added || []).forEach(d => items.push({ ...d, type: 'ADDED' }));
  }
  if (filter === 'all' || filter === 'removed') {
    (result.removed || []).forEach(d => items.push({ ...d, type: 'REMOVED' }));
  }
  if (filter === 'all' || filter === 'modified') {
    (result.modified || []).forEach(d => items.push({ ...d, type: 'MODIFIED' }));
  }

  if (items.length === 0) {
    els.diffContainer.appendChild(
      createElement('p', { className: 'empty-state', text: t('no_changes_for_filter') })
    );
    return;
  }

  const docIdA = result.document_id_a;
  const docIdB = result.document_id_b;

  items.forEach(diff => {
    const card = createElement('div', { className: `diff-card diff-${diff.type.toLowerCase()}` });

    const header = createElement('div', { className: 'diff-header' }, [
      createElement('div', { className: 'diff-badges-group' }, [
        createElement('span', { className: `diff-badge badge-${diff.type.toLowerCase()}`, text: diff.type }),
        diff.change_category ? createElement('span', { className: 'badge-financial', text: diff.change_category }) : null,
      ].filter(Boolean)),
      createElement('span', { className: 'diff-path', text: diff.section_path_b || diff.section_path_a || 'Clause' }),
    ]);

    card.appendChild(header);

    if (diff.diff_summary) {
      card.appendChild(createElement('div', { className: 'diff-summary-text', text: diff.diff_summary }));
    }

    if (diff.financial_change) {
      card.appendChild(createElement('div', {
        className: 'financial-completeness-note mt-2 mb-2',
        text: `💰 ${t('financial_change_label')}: ${diff.financial_change}`
      }));
    }

    if (diff.relationship_change) {
      card.appendChild(createElement('div', {
        className: 'rel-verification-box mt-2 mb-2',
        text: `🔗 ${t('relationship_impact_label')}: ${diff.relationship_change}`
      }));
    }

    const contentBox = createElement('div', { className: 'diff-content-grid' });

    if (diff.text_a) {
      const beforeBox = createElement('div', { className: 'diff-text-box before-box' }, [
        createElement('strong', { text: `${t('original_doc_a')} · ${t('pg_abbrev')} ${diff.page_a || 1}:` }),
        createElement('p', { text: diff.text_a }),
      ]);
      contentBox.appendChild(beforeBox);
    }

    if (diff.text_b) {
      const afterBox = createElement('div', { className: 'diff-text-box after-box' }, [
        createElement('strong', { text: `${t('revised_doc_b')} · ${t('pg_abbrev')} ${diff.page_b || 1}:` }),
        createElement('p', { text: diff.text_b }),
      ]);
      contentBox.appendChild(afterBox);
    }

    card.appendChild(contentBox);

    // View A and View B Evidence Buttons
    const actionRow = createElement('div', { className: 'diff-actions-row mt-2' });

    if (diff.clause_id_a) {
      const btnViewA = createElement('button', {
        className: 'btn btn-secondary btn-xs me-2',
        text: t('view_doc_a'),
        attrs: { 'aria-label': 'View clause in Document A evidence viewer' }
      });
      btnViewA.addEventListener('click', () => {
        openEvidenceViewer(docIdA, diff.clause_id_a, diff.page_a || 1, diff.text_a || '', diff.section_path_a || 'Doc A');
      });
      actionRow.appendChild(btnViewA);
    }

    if (diff.clause_id_b) {
      const btnViewB = createElement('button', {
        className: 'btn btn-secondary btn-xs me-2',
        text: t('view_doc_b'),
        attrs: { 'aria-label': 'View clause in Document B evidence viewer' }
      });
      btnViewB.addEventListener('click', () => {
        openEvidenceViewer(docIdB, diff.clause_id_b, diff.page_b || 1, diff.text_b || '', diff.section_path_b || 'Doc B');
      });
      actionRow.appendChild(btnViewB);
    }

    if (diff.type === 'MODIFIED' && diff.text_a && diff.text_b) {
      const explainBtn = createElement('button', {
        className: 'btn btn-secondary btn-sm me-2',
        text: t('explain_change_ai'),
      });
      const explanationContainer = createElement('div', { className: 'explain-diff-container hidden mt-2' });

      explainBtn.addEventListener('click', async () => {
        explainBtn.disabled = true;
        explainBtn.textContent = 'Explaining...';
        try {
          const res = await API.explainDiff(diff.text_a, diff.text_b, diff.section_path_b || diff.section_path_a || 'Section');
          clearElement(explanationContainer);
          explanationContainer.appendChild(createElement('p', { text: res.explanation }));
          explanationContainer.classList.remove('hidden');
        } catch (err) {
          showErrorToast(`Failed to explain diff: ${err.message}`);
        } finally {
          explainBtn.disabled = false;
          explainBtn.textContent = t('explain_change_ai');
        }
      });

      actionRow.appendChild(explainBtn);
      card.appendChild(actionRow);
      card.appendChild(explanationContainer);
    } else if (actionRow.children.length > 0) {
      card.appendChild(actionRow);
    }

    els.diffContainer.appendChild(card);
  });
}

// ── Prepare / Checklist View ─────────────────────────────────────────────────

async function handleGenerateChecklist() {
  if (!state.currentDocumentId) {
    showErrorToast('Please select or upload a document first to generate a checklist.');
    return;
  }

  setLoadingState(true, 'Generating legal review checklist...');
  try {
    const checklist = await API.getChecklist(state.currentDocumentId);
    state.checklist = checklist;
    renderChecklist(checklist);
    els.btnCopyChecklist.classList.remove('hidden');
  } catch (err) {
    showErrorToast(`Failed to generate checklist: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

function renderChecklist(checklist) {
  clearElement(els.checklistContent);

  if (!checklist || !checklist.items || checklist.items.length === 0) {
    els.checklistContent.appendChild(
      createElement('p', { className: 'empty-state', text: 'No checklist items generated.' })
    );
    return;
  }

  const container = createElement('div', { className: 'checklist-items-container' });

  // Group by category
  const categoriesMap = new Map();
  checklist.items.forEach(item => {
    const cat = item.category || 'general_review';
    if (!categoriesMap.has(cat)) categoriesMap.set(cat, []);
    categoriesMap.get(cat).push(item);
  });

  categoriesMap.forEach((items, category) => {
    const catNorm = category.toLowerCase().trim().replace(/_/g, ' ');
    const CAT_MAP = {
      'general': 'general_review',
      'general review': 'general_review',
      'payment': 'payment_terms',
      'payment terms': 'payment_terms',
      'lawyer_questions': 'lawyer_questions',
      'lawyer questions': 'lawyer_questions',
      'questions for lawyer': 'lawyer_questions',
      'obligations': 'key_obligations',
      'key obligations': 'key_obligations',
      'dates': 'important_dates',
      'important dates': 'important_dates',
      'review': 'review'
    };
    const mappedKey = CAT_MAP[catNorm] || category.toLowerCase().replace(/\s+/g, '_');
    const localizedCategory = t(mappedKey) || category;
    const catSection = createElement('div', { className: 'checklist-category-section' });
    catSection.appendChild(createElement('h3', { className: 'category-title', text: localizedCategory }));

    const ul = createElement('ul', { className: 'checklist-ul' });
    items.forEach((item, idx) => {
      const li = createElement('li', { className: 'checklist-item' });

      const checkbox = createElement('input', {
        attrs: { type: 'checkbox', id: `chk-${category}-${idx}` },
      });
      if (item.done) checkbox.checked = true;

      let rawText = item.item;
      let displayItemText = rawText;

      // Handle item prefixes like "Review: ", "Confirm obligation: ", "Track important date: "
      const prefixMatch = rawText.match(/^(Review|Confirm obligation|Track important date):\s*(.*)/i);
      if (prefixMatch) {
        const origPrefix = prefixMatch[1].toLowerCase();
        let prefixKey = 'review';
        if (origPrefix.includes('confirm')) prefixKey = 'confirm_obligation';
        else if (origPrefix.includes('track')) prefixKey = 'track_date';

        const locPrefix = t(prefixKey);
        const restOfText = prefixMatch[2];
        displayItemText = `${locPrefix}: ${restOfText}`;
      }

      const label = createElement('label', {
        attrs: { for: `chk-${category}-${idx}` },
        text: displayItemText,
      });

      li.appendChild(checkbox);
      li.appendChild(label);

      if (item.clause_reference) {
        const refSpan = createElement('span', { className: 'clause-ref-tag', text: ` (Ref: ${item.clause_reference})` });
        li.appendChild(refSpan);
      }

      ul.appendChild(li);
    });

    catSection.appendChild(ul);
    container.appendChild(catSection);
  });

  els.checklistContent.appendChild(container);
}

function handleCopyChecklist() {
  if (!state.checklist || !state.checklist.items) return;

  const lines = ['# Legal Review Checklist\n'];
  state.checklist.items.forEach(item => {
    const ref = item.clause_reference ? ` (Ref: ${item.clause_reference})` : '';
    lines.push(`- [ ] [${item.category}] ${item.item}${ref}`);
  });

  const textToCopy = lines.join('\n');
  navigator.clipboard.writeText(textToCopy).then(
    () => alert('Checklist copied to clipboard as markdown!'),
    () => alert('Failed to copy to clipboard.')
  );
}

// ── Global Upload Handlers ────────────────────────────────────────────────────

async function handleFiles(files) {
  if (!files || !files.length) return;
  const file = files[0];
  setLoadingState(true, `Uploading & analyzing "${file.name}"...`);

  try {
    const doc = await API.upload(file);
    state.currentDocumentId = doc.document_id;
    state.currentDocumentName = doc.filename;
    updateNavState();
    navigate('analyze', { docId: doc.document_id });
    announceToScreenReader(`Successfully uploaded and analyzed ${doc.filename}`);
  } catch (err) {
    console.error('Upload error:', err);
    showErrorToast(`Upload failed: ${err.message}`);
  } finally {
    setLoadingState(false);
  }
}

// ── Initialization & Event Listeners ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Route initial view from URL hash immediately
  handleRouteFromHash();

  // Check system status in background
  refreshStatus();

  // Listen for hash changes (browser back/forward & direct URL hash edits)
  window.addEventListener('hashchange', handleRouteFromHash);

  // Wire empty/error state buttons
  if (els.btnEmptyGoDashboard) {
    els.btnEmptyGoDashboard.addEventListener('click', () => navigate('dashboard'));
  }
  if (els.btnErrorGoDashboard) {
    els.btnErrorGoDashboard.addEventListener('click', () => navigate('dashboard'));
  }

  // Navigation Links
  els.navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(link.dataset.view, { docId: state.currentDocumentId });
    });
  });

  // Tab Buttons in Analyze view
  els.tabBtns.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.id));
  });

  // Clause Search Filter
  if (els.clauseSearch) {
    els.clauseSearch.addEventListener('input', (e) => filterClauses(e.target.value));
  }

  // Generate Summary Button
  if (els.btnGenSummary) {
    els.btnGenSummary.addEventListener('click', async () => {
      if (!state.currentDocumentId) return;
      setLoadingState(true, 'Generating AI Summary...');
      try {
        const summaryRes = await API.generateSummary(state.currentDocumentId);
        clearElement(els.summaryContent);
        els.summaryContent.appendChild(createElement('p', { text: summaryRes.summary }));
        if (summaryRes.genai_used === false) {
          els.summaryContent.appendChild(
            createElement('small', { className: 'fallback-note', text: ' (Generated via deterministic rule engine fallback)' })
          );
        }
      } catch (err) {
        showErrorToast(`Failed to generate summary: ${err.message}`);
      } finally {
        setLoadingState(false);
      }
    });
  }

  // Q&A Chat Form
  els.chatForm.addEventListener('submit', handleQuestionSubmit);

  // Compare Selectors & Run
  els.compareDocA.addEventListener('change', updateCompareButtonState);
  els.compareDocB.addEventListener('change', updateCompareButtonState);
  els.btnRunCompare.addEventListener('click', handleRunCompare);

  document.querySelectorAll('.diff-filters .filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.diff-filters .filter-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      // re-render diffs with selected filter
      if (state.lastCompareResult) {
        renderDiffCards(state.lastCompareResult, e.target.dataset.filter);
      }
    });
  });

  // Prepare / Checklist Buttons
  els.btnGenChecklist.addEventListener('click', handleGenerateChecklist);
  els.btnCopyChecklist.addEventListener('click', handleCopyChecklist);

  // Modal Close Listeners
  els.modalCloseBtn.addEventListener('click', () => els.sourceModal.close());
  els.sourceModal.addEventListener('click', (e) => {
    if (e.target === els.sourceModal) els.sourceModal.close();
  });

  if (els.evidenceModalClose && els.evidenceModal) {
    els.evidenceModalClose.addEventListener('click', () => els.evidenceModal.close());
    els.evidenceModal.addEventListener('click', (e) => {
      if (e.target === els.evidenceModal) els.evidenceModal.close();
    });
  }

  // Upload Zone Drag & Drop
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    els.uploadZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, false);
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    els.uploadZone.addEventListener(eventName, () => els.uploadZone.classList.add('dragover'), false);
  });
  ['dragleave', 'drop'].forEach(eventName => {
    els.uploadZone.addEventListener(eventName, () => els.uploadZone.classList.remove('dragover'), false);
  });

  els.uploadZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    handleFiles(files);
  });

  els.uploadBtnTrigger.addEventListener('click', (e) => {
    e.stopPropagation();
    els.fileInput.click();
  });
  els.uploadZone.addEventListener('click', () => els.fileInput.click());
  els.fileInput.addEventListener('change', function () {
    handleFiles(this.files);
  });
});
