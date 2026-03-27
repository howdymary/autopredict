"""AutoPredict package.

The repo currently ships both:
- a modern nested package under ``autopredict/``
- legacy flat modules at the repository root

Extending ``__path__`` lets the packaged CLI and imports resolve those legacy
modules as ``autopredict.agent``, ``autopredict.market_env``, and
``autopredict.run_experiment`` during the migration.
"""

from pathlib import Path
from pkgutil import extend_path

__version__ = "0.1.0"

__path__ = extend_path(__path__, __name__)
_legacy_module_dir = Path(__file__).resolve().parent.parent
if str(_legacy_module_dir) not in __path__:
    __path__.append(str(_legacy_module_dir))
