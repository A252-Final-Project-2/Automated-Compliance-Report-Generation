from flask import Blueprint

# Initialize the Blueprint
module3_bp = Blueprint('module3', __name__, template_folder='templates')

# IMPORT ROUTES AT THE BOTTOM
# This is crucial so that module3_bp is created before routes.py tries to use it
try:
	from . import routes
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
	raise