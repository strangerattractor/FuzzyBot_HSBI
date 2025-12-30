# Models

Do not commit model weights to git.

On the HSBI cluster, store models in a stable location, e.g.

- ~/fuzzybot_models/
or (preferred if available)
- /scratch/$USER/fuzzybot_models/

Set:
FUZZYBOT_MODELS_DIR=/scratch/$USER/fuzzybot_models

Models used in this project:
- Apertus-8B-Instruct-2509 (default; repo: swiss-ai/Apertus-8B-Instruct-2509)
- Apertus-8B-Instruct-2509-unsloth-bnb-4bit (optional; repo: unsloth/Apertus-8B-Instruct-2509-unsloth-bnb-4bit)

By default, the server reads:
$FUZZYBOT_MODELS_DIR/Apertus-8B-Instruct-2509
