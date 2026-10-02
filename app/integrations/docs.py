"""Fill a Word template that has {{ fields }}.

render_docx("data/templates/retainer_agreement.docx", {"client_name": "Maria Lopez", ...}, "out/retainer.docx")
fields_in("data/templates/retainer_agreement.docx")  -> {"client_name", ...}
Templates are made by scripts/make_templates.py. Edit them in Word; keep each {{ field }} typed in one go.
"""
from pathlib import Path


def render_docx(template: str | Path, context: dict, out: str | Path) -> Path:
    from docxtpl import DocxTemplate

    doc = DocxTemplate(str(template))
    missing = fields_in(template) - set(context)
    if missing:
        raise ValueError(f"Missing fields: {sorted(missing)}")
    doc.render(context)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def fields_in(template: str | Path) -> set[str]:
    from docxtpl import DocxTemplate

    return set(DocxTemplate(str(template)).get_undeclared_template_variables())
