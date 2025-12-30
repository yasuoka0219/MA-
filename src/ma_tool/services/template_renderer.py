"""Template rendering service with variable substitution"""
import hashlib
import hmac
from typing import Dict, Any, Optional
from jinja2 import Template as Jinja2Template, Environment, BaseLoader

from src.ma_tool.config import settings
from src.ma_tool.models.lead import Lead


class StringLoader(BaseLoader):
    def get_source(self, environment, template):
        return template, None, lambda: True


jinja_env = Environment(loader=StringLoader())


def generate_unsubscribe_token(lead_id: int) -> str:
    message = f"unsubscribe:{lead_id}"
    signature = hmac.new(
        settings.UNSUBSCRIBE_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return signature


def generate_unsubscribe_url(lead_id: int) -> str:
    token = generate_unsubscribe_token(lead_id)
    return f"{settings.BASE_URL}/unsubscribe/{lead_id}?token={token}"


def get_template_variables(lead: Lead, extra_vars: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    variables = {
        "lead_name": lead.name,
        "lead_email": lead.email,
        "lead_school_name": lead.school_name or "",
        "lead_graduation_year": lead.graduation_year,
        "unsubscribe_url": generate_unsubscribe_url(lead.id),
        "line_friend_add_url": settings.LINE_FRIEND_ADD_URL,
    }
    
    if extra_vars:
        variables.update(extra_vars)
    
    return variables


def render_template(template_str: str, variables: Dict[str, Any]) -> str:
    try:
        template = jinja_env.from_string(template_str)
        return template.render(**variables)
    except Exception:
        return template_str


def render_email_body(body_html: str, lead: Lead, extra_vars: Optional[Dict[str, Any]] = None) -> str:
    variables = get_template_variables(lead, extra_vars)
    rendered = render_template(body_html, variables)
    
    if "{{ unsubscribe_url }}" not in body_html and settings.BASE_URL:
        unsubscribe_footer = f'''
<hr style="margin-top: 40px; border: none; border-top: 1px solid #ccc;">
<p style="font-size: 12px; color: #666; text-align: center;">
    このメールの配信停止を希望される場合は<a href="{variables['unsubscribe_url']}">こちら</a>からお手続きください。
</p>
'''
        if "</body>" in rendered.lower():
            rendered = rendered.replace("</body>", f"{unsubscribe_footer}</body>")
            rendered = rendered.replace("</BODY>", f"{unsubscribe_footer}</BODY>")
        else:
            rendered += unsubscribe_footer
    
    return rendered


def render_subject(subject: str, lead: Lead, extra_vars: Optional[Dict[str, Any]] = None) -> str:
    variables = get_template_variables(lead, extra_vars)
    return render_template(subject, variables)
