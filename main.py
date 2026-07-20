import os
import sys
from pathlib import Path

import uvicorn


AGENTS_DIR = Path(__file__).resolve().parent / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
