# SlothFlow AI

**Do less. Get more done.** SlothFlow is a local-first productivity app that turns an unstructured brain dump into a reviewable task plan, stores tasks locally, and provides a daily reset view.

Built as a Hacktoberfest DEV challenge MVP.

## Features

- Brain dump → draft task plan with priorities and time estimates.
- Optional local AI via Ollama; works without Ollama using a deterministic fallback.
- Review and select tasks before saving.
- SQLite task list with completion and deletion.
- Daily reset summary of open tasks and estimated time.
- Responsive UI, API validation, and automated tests.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

The app works immediately in offline-rules mode. It does not require an API key.

## Enable local AI (optional)

1. Install [Ollama](https://ollama.com/).
2. Pull a model, for example:

   ```bash
   ollama pull qwen2.5:3b
   ```

3. Ensure Ollama is running, then start SlothFlow:

   ```bash
   export OLLAMA_MODEL=qwen2.5:3b
   uvicorn app:app --reload
   ```

The app sends the brain dump to the local Ollama server at `http://127.0.0.1:11434`. If the server is unavailable or returns invalid output, the built-in rules engine is used instead. Task storage uses a local SQLite file.

## Run tests

```bash
pytest -q
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | App and local AI status |
| POST | `/api/plan` | Convert text into draft tasks |
| GET | `/api/tasks` | List saved tasks |
| POST | `/api/tasks` | Save a task |
| PATCH | `/api/tasks/{id}` | Mark a task `todo` or `done` |
| DELETE | `/api/tasks/{id}` | Delete a task |
| GET | `/api/reset` | Summary of open tasks |

Example plan request:

```json
{
  "text": "Finish project report by tomorrow. Prepare for interview."
}
```

## Privacy and limitations

- This is a local-first prototype, not a hosted multi-user service.
- Brain dumps are sent to the configured Ollama endpoint only when it is reachable; otherwise, the fallback runs in the app process.
- Saved tasks live in `slothflow.db` on the machine running the server.
- AI-generated plans can be wrong or incomplete. Review all suggested tasks before saving.
- Do not expose this development server directly to the public internet without adding authentication, rate limits, and deployment hardening.

## Challenge submission checklist

- [ ] Run the app and tests.
- [ ] Add screenshots and a short screen recording to the repository.
- [ ] Publish a DEV post describing the tedious task, the solution, the stack, and a real demo.
- [ ] Link the repository and demo in the challenge submission.

## License

MIT
