import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from app.config import settings
import json
from app.models.schemas import DocumentOverview, Clause, RiskSignal
from app.models.relationship import ClauseRelationship
from app.models.financial import FinancialItem

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                page_count INTEGER,
                clause_count INTEGER,
                signal_count INTEGER,
                dates TEXT,
                monetary_values TEXT,
                parties TEXT,
                genai_available BOOLEAN,
                created_at TEXT,
                processing_status TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clauses (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                metadata TEXT NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_signals (
                id TEXT PRIMARY KEY,
                clause_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                category TEXT,
                severity TEXT,
                matched_pattern TEXT,
                evidence_text TEXT,
                section_path TEXT,
                page INTEGER,
                plain_explanation TEXT,
                question_to_ask TEXT,
                FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE,
                FOREIGN KEY (clause_id) REFERENCES clauses (id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clause_relationships (
                relationship_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                relationship_status TEXT NOT NULL,
                confidence TEXT,
                title TEXT,
                explanation TEXT,
                verification_question TEXT,
                source_clause_id TEXT NOT NULL,
                source_section_path TEXT,
                source_page INTEGER,
                source_excerpt TEXT,
                related_clause_id TEXT,
                related_section_path TEXT,
                related_page INTEGER,
                related_excerpt TEXT,
                FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_items (
                item_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                amount TEXT,
                currency TEXT,
                frequency TEXT,
                condition TEXT,
                effective_date TEXT,
                payment_timing TEXT,
                clause_id TEXT NOT NULL,
                section_path TEXT,
                page INTEGER,
                evidence_text TEXT,
                completeness_note TEXT,
                FOREIGN KEY (document_id) REFERENCES documents (document_id) ON DELETE CASCADE
            )
        ''')
        conn.commit()

def save_document(doc: DocumentOverview) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO documents 
            (document_id, filename, page_count, clause_count, signal_count, dates, monetary_values, parties, genai_available, created_at, processing_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                filename=excluded.filename,
                page_count=excluded.page_count,
                clause_count=excluded.clause_count,
                signal_count=excluded.signal_count,
                dates=excluded.dates,
                monetary_values=excluded.monetary_values,
                parties=excluded.parties,
                genai_available=excluded.genai_available,
                created_at=excluded.created_at,
                processing_status=excluded.processing_status
        ''', (
            doc.document_id,
            doc.filename,
            doc.page_count,
            doc.clause_count,
            doc.signal_count,
            json.dumps(doc.dates),
            json.dumps(doc.monetary_values),
            json.dumps(doc.parties),
            doc.genai_available,
            doc.created_at.isoformat(),
            doc.processing_status
        ))
        conn.commit()
    return doc.document_id

def save_clause(clause: Clause) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO clauses (id, document_id, metadata, text)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                document_id=excluded.document_id,
                metadata=excluded.metadata,
                text=excluded.text
        ''', (
            clause.id,
            clause.metadata.document_id,
            clause.metadata.model_dump_json(),
            clause.text
        ))
        conn.commit()

def save_risk_signal(signal: RiskSignal) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO risk_signals 
            (id, clause_id, document_id, category, severity, matched_pattern, evidence_text, section_path, page, plain_explanation, question_to_ask)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                clause_id=excluded.clause_id,
                document_id=excluded.document_id,
                category=excluded.category,
                severity=excluded.severity,
                matched_pattern=excluded.matched_pattern,
                evidence_text=excluded.evidence_text,
                section_path=excluded.section_path,
                page=excluded.page,
                plain_explanation=excluded.plain_explanation,
                question_to_ask=excluded.question_to_ask
        ''', (
            str(signal.id),
            signal.clause_id,
            signal.document_id,
            signal.category,
            signal.severity.value,
            signal.matched_pattern,
            signal.evidence_text,
            signal.section_path,
            signal.page,
            signal.plain_explanation,
            signal.question_to_ask
        ))
        conn.commit()

def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM documents WHERE document_id = ?', (doc_id,))
        row = cursor.fetchone()
        if row:
            doc_dict = dict(row)
            doc_dict['dates'] = json.loads(doc_dict['dates'])
            doc_dict['monetary_values'] = json.loads(doc_dict['monetary_values'])
            doc_dict['parties'] = json.loads(doc_dict['parties'])
            doc_dict['genai_available'] = bool(doc_dict['genai_available'])
            return doc_dict
        return None

def get_clauses(doc_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM clauses WHERE document_id = ?', (doc_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            clause = dict(r)
            clause['metadata'] = json.loads(clause['metadata'])
            result.append(clause)
        return result

def get_clause_by_id(clause_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM clauses WHERE id = ?', (clause_id,))
        row = cursor.fetchone()
        if row:
            clause = dict(row)
            clause['metadata'] = json.loads(clause['metadata'])
            return clause
        return None

def get_risk_signals(doc_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM risk_signals WHERE document_id = ?', (doc_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_document(doc_id: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM financial_items WHERE document_id = ?', (doc_id,))
        cursor.execute('DELETE FROM clause_relationships WHERE document_id = ?', (doc_id,))
        cursor.execute('DELETE FROM risk_signals WHERE document_id = ?', (doc_id,))
        cursor.execute('DELETE FROM clauses WHERE document_id = ?', (doc_id,))
        cursor.execute('DELETE FROM documents WHERE document_id = ?', (doc_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

def list_documents() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM documents')
        rows = cursor.fetchall()
        result = []
        for r in rows:
            doc_dict = dict(r)
            doc_dict['dates'] = json.loads(doc_dict['dates'])
            doc_dict['monetary_values'] = json.loads(doc_dict['monetary_values'])
            doc_dict['parties'] = json.loads(doc_dict['parties'])
            doc_dict['genai_available'] = bool(doc_dict['genai_available'])
            result.append(doc_dict)
        return result

def list_workspace_documents() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                d.*,
                (SELECT COUNT(*) FROM risk_signals r WHERE r.document_id = d.document_id) as signal_cnt,
                (SELECT COUNT(*) FROM clause_relationships rel WHERE rel.document_id = d.document_id) as rel_cnt,
                (SELECT COUNT(*) FROM financial_items f WHERE f.document_id = d.document_id) as fin_cnt
            FROM documents d
            ORDER BY d.created_at DESC
        ''')
        rows = cursor.fetchall()
        result = []
        for r in rows:
            doc_dict = dict(r)
            doc_dict['dates'] = json.loads(doc_dict['dates']) if doc_dict.get('dates') else []
            doc_dict['monetary_values'] = json.loads(doc_dict['monetary_values']) if doc_dict.get('monetary_values') else []
            doc_dict['parties'] = json.loads(doc_dict['parties']) if doc_dict.get('parties') else []
            doc_dict['genai_available'] = bool(doc_dict.get('genai_available', False))
            
            sig_cnt = doc_dict.pop('signal_cnt', 0)
            rel_cnt = doc_dict.pop('rel_cnt', 0)
            fin_cnt = doc_dict.pop('fin_cnt', 0)
            
            doc_dict['attention_signal_count'] = sig_cnt
            doc_dict['signal_count'] = sig_cnt
            doc_dict['relationship_count'] = rel_cnt
            doc_dict['financial_item_count'] = fin_cnt
            result.append(doc_dict)
        return result


def save_relationships(doc_id: str, relationships: List[ClauseRelationship]) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Delete existing relationships for clean overwrite
        cursor.execute('DELETE FROM clause_relationships WHERE document_id = ?', (doc_id,))
        for rel in relationships:
            cursor.execute('''
                INSERT INTO clause_relationships (
                    relationship_id, document_id, relationship_type, relationship_status,
                    confidence, title, explanation, verification_question,
                    source_clause_id, source_section_path, source_page, source_excerpt,
                    related_clause_id, related_section_path, related_page, related_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                rel.relationship_id,
                rel.document_id,
                rel.relationship_type.value if hasattr(rel.relationship_type, 'value') else rel.relationship_type,
                rel.relationship_status.value if hasattr(rel.relationship_status, 'value') else rel.relationship_status,
                rel.confidence,
                rel.title,
                rel.plain_explanation,
                rel.question_to_ask,
                rel.source_clause_id,
                rel.source_section_path,
                rel.source_page,
                rel.source_excerpt,
                rel.related_clause_id,
                rel.related_section_path,
                rel.related_page,
                rel.related_excerpt
            ))
        conn.commit()

def get_relationships(doc_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM clause_relationships WHERE document_id = ?', (doc_id,))
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d['plain_explanation'] = d.pop('explanation', '')
            d['question_to_ask'] = d.pop('verification_question', '')
            results.append(d)
        return results

def get_relationship_by_id(relationship_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM clause_relationships WHERE relationship_id = ?', (relationship_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d['plain_explanation'] = d.pop('explanation', '')
            d['question_to_ask'] = d.pop('verification_question', '')
            return d
        return None


def save_financial_items(doc_id: str, items: List[FinancialItem]) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM financial_items WHERE document_id = ?', (doc_id,))
        for item in items:
            cursor.execute('''
                INSERT INTO financial_items (
                    item_id, document_id, item_type, amount, currency,
                    frequency, condition, effective_date, payment_timing,
                    clause_id, section_path, page, evidence_text, completeness_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.item_id,
                item.document_id,
                item.item_type,
                item.amount,
                item.currency,
                item.frequency,
                item.condition,
                item.effective_date,
                item.payment_timing,
                item.clause_id,
                item.section_path,
                item.page,
                item.evidence_text,
                item.completeness_note
            ))
        conn.commit()


def get_financial_items(doc_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM financial_items WHERE document_id = ? ORDER BY page ASC, item_id ASC', (doc_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_financial_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM financial_items WHERE item_id = ?', (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

