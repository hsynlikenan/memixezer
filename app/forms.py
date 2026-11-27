from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import DataRequired, ValidationError

from .services.users import MAX_BULK_USERS, parse_names


class BulkUserForm(FlaskForm):
    names = TextAreaField(
        "Display names (one per line)",
        validators=[DataRequired()],
        render_kw={"rows": 10, "placeholder": "Ali Məmmədov\nLeyla Həsənova"},
    )

    def validate_names(self, field):
        names = parse_names(field.data)
        if not names:
            raise ValidationError("Enter at least one name.")
        if len(names) > MAX_BULK_USERS:
            raise ValidationError(f"At most {MAX_BULK_USERS} accounts per batch (got {len(names)}).")
        if any(len(n) > 80 for n in names):
            raise ValidationError("Each name must be at most 80 characters.")

    @property
    def parsed_names(self) -> list[str]:
        return parse_names(self.names.data)
